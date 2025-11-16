"""Base chain connector with RPC connection management and circuit breaker"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from web3 import Web3
from web3.exceptions import Web3Exception
from web3.types import BlockData, TxReceipt

from src.config.models import ChainConfig
from src.monitoring import metrics

logger = structlog.get_logger()


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failures detected, stop calling
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """Circuit breaker for RPC endpoint"""

    failure_threshold: int = 5
    timeout_seconds: int = 60
    failure_count: int = 0
    state: CircuitState = CircuitState.CLOSED
    last_failure_time: float = 0.0

    def record_success(self) -> None:
        """Record successful call"""
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            logger.info("circuit_breaker_closed", state=self.state.value)

    def record_failure(self) -> None:
        """Record failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold and self.state == CircuitState.CLOSED:
            self.state = CircuitState.OPEN
            logger.warning(
                "circuit_breaker_opened",
                state=self.state.value,
                failure_count=self.failure_count,
            )

    def can_attempt(self) -> bool:
        """Check if call can be attempted"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed
            if time.time() - self.last_failure_time >= self.timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                logger.info("circuit_breaker_half_open", state=self.state.value)
                return True
            return False

        # HALF_OPEN state - allow one attempt
        return True


class ChainConnector(ABC):
    """Base class for blockchain connectors with RPC failover and circuit breaker"""

    def __init__(self, config: ChainConfig):
        self.config = config
        self.chain_name = config.name
        self.chain_id = config.chain_id
        self.rpc_urls = config.rpc_urls
        self.current_rpc_index = 0

        # Initialize Web3 connection
        self.w3: Optional[Web3] = None
        self._circuit_breakers: Dict[str, CircuitBreaker] = {
            url: CircuitBreaker() for url in self.rpc_urls
        }
        self._connect()

    def _connect(self) -> None:
        """Establish connection to RPC endpoint"""
        rpc_url = self.rpc_urls[self.current_rpc_index]
        try:
            self.w3 = Web3(Web3.HTTPProvider(rpc_url))
            if self.w3.is_connected():
                logger.info(
                    "rpc_connected",
                    chain=self.chain_name,
                    rpc_url=rpc_url,
                    index=self.current_rpc_index,
                )
            else:
                raise ConnectionError(f"Failed to connect to {rpc_url}")
        except Exception as e:
            logger.error(
                "rpc_connection_failed",
                chain=self.chain_name,
                rpc_url=rpc_url,
                error=str(e),
            )
            raise

    def _failover(self) -> bool:
        """Attempt failover to next RPC endpoint"""
        original_index = self.current_rpc_index

        # Try all available RPC endpoints
        for _ in range(len(self.rpc_urls)):
            self.current_rpc_index = (self.current_rpc_index + 1) % len(self.rpc_urls)
            rpc_url = self.rpc_urls[self.current_rpc_index]

            # Check circuit breaker
            circuit_breaker = self._circuit_breakers[rpc_url]
            if not circuit_breaker.can_attempt():
                logger.debug(
                    "rpc_circuit_breaker_open",
                    chain=self.chain_name,
                    rpc_url=rpc_url,
                )
                continue

            try:
                self._connect()
                if self.w3 and self.w3.is_connected():
                    logger.info(
                        "rpc_failover_success",
                        chain=self.chain_name,
                        from_index=original_index,
                        to_index=self.current_rpc_index,
                        rpc_url=rpc_url,
                    )
                    circuit_breaker.record_success()
                    return True
            except Exception as e:
                logger.warning(
                    "rpc_failover_attempt_failed",
                    chain=self.chain_name,
                    rpc_url=rpc_url,
                    error=str(e),
                )
                circuit_breaker.record_failure()
                continue

        logger.error(
            "rpc_failover_exhausted",
            chain=self.chain_name,
            attempted_endpoints=len(self.rpc_urls),
        )
        return False

    async def _retry_with_failover(
        self, operation: str, func, *args, max_retries: int = 3, **kwargs
    ) -> Any:
        """Execute operation with retry and automatic failover"""
        last_error = None

        for attempt in range(max_retries):
            start_time = time.time()
            try:
                # Check circuit breaker for current endpoint
                current_rpc_url = self.rpc_urls[self.current_rpc_index]
                circuit_breaker = self._circuit_breakers[current_rpc_url]

                if not circuit_breaker.can_attempt():
                    logger.debug(
                        "rpc_circuit_breaker_blocking",
                        chain=self.chain_name,
                        operation=operation,
                        rpc_url=current_rpc_url,
                    )
                    # Try failover immediately
                    if not self._failover():
                        raise ConnectionError("All RPC endpoints unavailable")
                    continue

                # Execute operation
                result = func(*args, **kwargs)
                
                # Record success metrics
                latency = time.time() - start_time
                metrics.chain_rpc_latency.labels(
                    chain=self.chain_name,
                    endpoint=current_rpc_url,
                    method=operation
                ).observe(latency)
                
                circuit_breaker.record_success()
                return result

            except (Web3Exception, ConnectionError, TimeoutError) as e:
                last_error = e
                current_rpc_url = self.rpc_urls[self.current_rpc_index]
                circuit_breaker = self._circuit_breakers[current_rpc_url]
                circuit_breaker.record_failure()
                
                # Record error metrics
                error_type = type(e).__name__
                metrics.chain_rpc_errors.labels(
                    chain=self.chain_name,
                    error_type=error_type
                ).inc()

                logger.warning(
                    "rpc_operation_failed",
                    chain=self.chain_name,
                    operation=operation,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                    rpc_url=current_rpc_url,
                )

                # Attempt failover
                if attempt < max_retries - 1:
                    if self._failover():
                        # Exponential backoff
                        await asyncio.sleep(2**attempt)
                        continue
                    else:
                        # No healthy endpoints available
                        break

        # All retries exhausted
        logger.error(
            "rpc_operation_failed_all_retries",
            chain=self.chain_name,
            operation=operation,
            max_retries=max_retries,
            error=str(last_error),
        )
        raise last_error

    async def get_latest_block(self) -> int:
        """Get latest block number from chain"""
        return await self._retry_with_failover(
            "get_latest_block",
            lambda: self.w3.eth.block_number,
        )

    async def get_block(self, block_number: int, full_transactions: bool = True) -> BlockData:
        """Get block data by block number"""
        return await self._retry_with_failover(
            "get_block",
            lambda: self.w3.eth.get_block(block_number, full_transactions=full_transactions),
        )

    async def get_transaction_receipt(self, tx_hash: str) -> TxReceipt:
        """Get transaction receipt by hash"""
        return await self._retry_with_failover(
            "get_transaction_receipt",
            lambda: self.w3.eth.get_transaction_receipt(tx_hash),
        )

    def get_dex_routers(self) -> Dict[str, str]:
        """Get DEX router addresses for this chain"""
        return self.config.dex_routers

    def get_pools(self) -> Dict[str, str]:
        """Get pool addresses for this chain"""
        return self.config.pools

    def is_dex_router(self, address: str) -> bool:
        """Check if address is a known DEX router"""
        normalized_address = Web3.to_checksum_address(address)
        return normalized_address in self.config.dex_routers.values()

    @abstractmethod
    def get_chain_specific_config(self) -> Dict[str, Any]:
        """Get chain-specific configuration (implemented by subclasses)"""
        pass
