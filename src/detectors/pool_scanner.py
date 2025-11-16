"""Pool scanner for detecting arbitrage opportunities through pool imbalances"""

import asyncio
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

import structlog
from web3 import Web3

from src.cache.manager import CacheManager
from src.chains.connector import ChainConnector
from src.config.models import ChainConfig
from src.database.manager import DatabaseManager
from src.database.models import Opportunity
from src.monitoring import metrics

logger = structlog.get_logger()


# Uniswap V2-style pool ABI (getReserves function)
POOL_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"},
        ],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    }
]


@dataclass
class PoolReserves:
    """Pool reserve data"""

    pool_address: str
    pool_name: str
    reserve0: int
    reserve1: int
    block_timestamp: int


@dataclass
class ImbalanceData:
    """Pool imbalance calculation results"""

    imbalance_pct: Decimal
    profit_potential_usd: Decimal
    profit_potential_native: Decimal
    optimal_reserve0: Decimal
    optimal_reserve1: Decimal


class PoolScanner:
    """
    Scans liquidity pools for imbalances that could be exploited for arbitrage.
    
    Uses CPMM (Constant Product Market Maker) formula to detect pool imbalances
    and calculate profit potential.
    """

    def __init__(
        self,
        chain_connector: ChainConnector,
        config: ChainConfig,
        database_manager: Optional[DatabaseManager] = None,
        cache_manager: Optional[CacheManager] = None,
        scan_interval_seconds: float = 3.0,
        imbalance_threshold_pct: float = 5.0,
        swap_fee_pct: float = 0.3,
        small_opp_min_usd: float = 10000.0,
        small_opp_max_usd: float = 100000.0,
        broadcast_callback: Optional[Callable[[Dict[str, Any]], Coroutine]] = None,
    ):
        """
        Initialize pool scanner.
        
        Args:
            chain_connector: Chain connector for RPC calls
            config: Chain configuration with pool addresses
            database_manager: Optional database manager for persisting opportunities
            cache_manager: Optional cache manager for caching opportunities
            scan_interval_seconds: Seconds between pool scans (default 3 for BSC, 2 for Polygon)
            imbalance_threshold_pct: Minimum imbalance percentage to detect (default 5%)
            swap_fee_pct: DEX swap fee percentage (default 0.3%)
            small_opp_min_usd: Minimum profit for small opportunity classification (default $10K)
            small_opp_max_usd: Maximum profit for small opportunity classification (default $100K)
            broadcast_callback: Optional callback for broadcasting opportunities via WebSocket
        """
        self.chain_connector = chain_connector
        self.config = config
        self.database_manager = database_manager
        self.cache_manager = cache_manager
        self.scan_interval_seconds = scan_interval_seconds
        self.imbalance_threshold_pct = Decimal(str(imbalance_threshold_pct))
        self.swap_fee_pct = Decimal(str(swap_fee_pct))
        self.small_opp_min_usd = Decimal(str(small_opp_min_usd))
        self.small_opp_max_usd = Decimal(str(small_opp_max_usd))
        self.broadcast_callback = broadcast_callback
        
        self.chain_name = config.name
        self.chain_id = config.chain_id
        self.pools = config.pools
        
        self._logger = logger.bind(
            component="pool_scanner",
            chain=self.chain_name,
        )
        self._running = False
        self._scan_task: Optional[asyncio.Task] = None
        self._small_opportunity_count = 0

    async def get_pool_reserves(self, pool_address: str, pool_name: str) -> Optional[PoolReserves]:
        """
        Query pool reserves using getReserves() function.
        
        Args:
            pool_address: Pool contract address
            pool_name: Pool name for logging
            
        Returns:
            PoolReserves object or None if query fails
        """
        try:
            # Create contract instance
            checksum_address = Web3.to_checksum_address(pool_address)
            contract = self.chain_connector.w3.eth.contract(
                address=checksum_address,
                abi=POOL_ABI
            )
            
            # Call getReserves()
            reserves = contract.functions.getReserves().call()
            
            reserve0 = reserves[0]
            reserve1 = reserves[1]
            block_timestamp = reserves[2]
            
            self._logger.debug(
                "pool_reserves_fetched",
                pool_name=pool_name,
                pool_address=pool_address,
                reserve0=reserve0,
                reserve1=reserve1,
            )
            
            return PoolReserves(
                pool_address=pool_address,
                pool_name=pool_name,
                reserve0=reserve0,
                reserve1=reserve1,
                block_timestamp=block_timestamp,
            )
            
        except Exception as e:
            self._logger.warning(
                "pool_reserves_fetch_failed",
                pool_name=pool_name,
                pool_address=pool_address,
                error=str(e),
            )
            return None

    def is_small_opportunity(self, profit_usd: Decimal) -> bool:
        """
        Check if opportunity qualifies as a small opportunity.
        
        Small opportunities are those with profit between $10K-$100K,
        targeting small traders with limited capital.
        
        Args:
            profit_usd: Profit potential in USD
            
        Returns:
            True if opportunity is classified as small, False otherwise
        """
        return self.small_opp_min_usd <= profit_usd <= self.small_opp_max_usd

    def calculate_imbalance(
        self,
        reserve0: int,
        reserve1: int,
    ) -> Optional[ImbalanceData]:
        """
        Calculate pool imbalance using CPMM invariant formula.
        
        CPMM formula: k = x * y (constant product)
        Optimal reserves: optimal_x = optimal_y = sqrt(k)
        Imbalance: max(|reserve0 - optimal_x| / optimal_x, |reserve1 - optimal_y| / optimal_y) * 100
        
        Args:
            reserve0: Reserve amount for token0
            reserve1: Reserve amount for token1
            
        Returns:
            ImbalanceData object or None if reserves are zero
        """
        if reserve0 == 0 or reserve1 == 0:
            self._logger.warning(
                "pool_reserves_zero",
                reserve0=reserve0,
                reserve1=reserve1,
            )
            return None
        
        # Calculate pool invariant k = reserve0 * reserve1
        k = Decimal(reserve0) * Decimal(reserve1)
        
        # Calculate optimal reserves: optimal_x = optimal_y = sqrt(k)
        k_sqrt = Decimal(math.sqrt(float(k)))
        optimal_reserve0 = k_sqrt
        optimal_reserve1 = k_sqrt
        
        # Calculate imbalance percentage for each reserve
        imbalance0_pct = abs(Decimal(reserve0) - optimal_reserve0) / optimal_reserve0 * 100
        imbalance1_pct = abs(Decimal(reserve1) - optimal_reserve1) / optimal_reserve1 * 100
        
        # Take maximum imbalance
        imbalance_pct = max(imbalance0_pct, imbalance1_pct)
        
        # Calculate profit potential accounting for swap fee
        # Profit = imbalance amount - swap fee
        # Simplified: profit ≈ imbalance_pct - swap_fee_pct (as percentage of pool size)
        # Convert to actual profit in tokens
        if imbalance_pct > self.swap_fee_pct:
            # Profit potential is the excess imbalance after fees
            profit_pct = imbalance_pct - self.swap_fee_pct
            
            # Calculate profit in token1 (assuming token1 is stablecoin)
            # Profit = (profit_pct / 100) * reserve1
            profit_native = (profit_pct / 100) * Decimal(reserve1)
            
            # Convert to USD (assuming token1 is stablecoin, so 1:1 with USD)
            # For native token pairs, we'd need price conversion
            # Simplified: assume reserve1 is in stablecoin units (18 decimals)
            profit_usd = profit_native / Decimal(10**18)
        else:
            profit_native = Decimal("0")
            profit_usd = Decimal("0")
        
        return ImbalanceData(
            imbalance_pct=imbalance_pct,
            profit_potential_usd=profit_usd,
            profit_potential_native=profit_native,
            optimal_reserve0=optimal_reserve0,
            optimal_reserve1=optimal_reserve1,
        )

    async def scan_pools(self) -> List[Opportunity]:
        """
        Scan all configured pools for imbalances.
        
        Returns:
            List of detected opportunities
        """
        opportunities = []
        
        # Get current block number
        try:
            block_number = await self.chain_connector.get_latest_block()
        except Exception as e:
            self._logger.error(
                "failed_to_get_block_number",
                error=str(e),
            )
            return opportunities
        
        # Scan each pool
        for pool_name, pool_address in self.pools.items():
            reserves = await self.get_pool_reserves(pool_address, pool_name)
            
            if reserves is None:
                continue
            
            # Calculate imbalance
            imbalance_data = self.calculate_imbalance(
                reserves.reserve0,
                reserves.reserve1,
            )
            
            if imbalance_data is None:
                continue
            
            # Check if imbalance exceeds threshold
            if imbalance_data.imbalance_pct >= self.imbalance_threshold_pct:
                opportunity = Opportunity(
                    chain_id=self.chain_id,
                    pool_name=pool_name,
                    pool_address=pool_address,
                    imbalance_pct=imbalance_data.imbalance_pct,
                    profit_usd=imbalance_data.profit_potential_usd,
                    profit_native=imbalance_data.profit_potential_native,
                    reserve0=Decimal(reserves.reserve0),
                    reserve1=Decimal(reserves.reserve1),
                    block_number=block_number,
                    detected_at=datetime.utcnow(),
                    captured=False,
                )
                
                opportunities.append(opportunity)
                
                # Track small opportunity count
                is_small = self.is_small_opportunity(imbalance_data.profit_potential_usd)
                if is_small:
                    self._small_opportunity_count += 1
                
                # Update metrics
                metrics.opportunities_detected.labels(chain=self.chain_name).inc()
                
                self._logger.info(
                    "opportunity_detected",
                    pool_name=pool_name,
                    pool_address=pool_address,
                    imbalance_pct=float(imbalance_data.imbalance_pct),
                    profit_usd=float(imbalance_data.profit_potential_usd),
                    is_small_opportunity=is_small,
                    block_number=block_number,
                )
                
                # Save to database if manager is available
                if self.database_manager:
                    try:
                        opportunity_id = await self.database_manager.save_opportunity(opportunity)
                        opportunity.id = opportunity_id
                        
                        # Cache the opportunity if cache manager is available
                        if self.cache_manager:
                            try:
                                await self.cache_manager.cache_opportunity(opportunity, ttl=300)
                            except Exception as cache_error:
                                self._logger.warning(
                                    "failed_to_cache_opportunity",
                                    pool_name=pool_name,
                                    error=str(cache_error),
                                )
                    except Exception as e:
                        self._logger.error(
                            "failed_to_save_opportunity",
                            pool_name=pool_name,
                            error=str(e),
                        )
                
                # Broadcast opportunity via WebSocket if callback is available
                if self.broadcast_callback:
                    try:
                        opportunity_data = asdict(opportunity)
                        await self.broadcast_callback(opportunity_data)
                    except Exception as e:
                        self._logger.error(
                            "failed_to_broadcast_opportunity",
                            pool_name=pool_name,
                            error=str(e),
                        )
        
        return opportunities

    def get_small_opportunity_count(self) -> int:
        """
        Get the count of small opportunities detected.
        
        Returns:
            Number of small opportunities detected since scanner started
        """
        return self._small_opportunity_count

    async def start(self) -> None:
        """Start pool scanning loop"""
        if self._running:
            self._logger.warning("pool_scanner_already_running")
            return
        
        self._running = True
        self._small_opportunity_count = 0  # Reset counter on start
        self._scan_task = asyncio.create_task(self._scan_loop())
        
        self._logger.info(
            "pool_scanner_started",
            scan_interval_seconds=self.scan_interval_seconds,
            imbalance_threshold_pct=float(self.imbalance_threshold_pct),
            small_opp_range=f"${float(self.small_opp_min_usd)}-${float(self.small_opp_max_usd)}",
        )

    async def stop(self) -> None:
        """Stop pool scanning loop"""
        if not self._running:
            return
        
        self._running = False
        
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        
        self._logger.info("pool_scanner_stopped")

    async def _scan_loop(self) -> None:
        """Internal scanning loop"""
        while self._running:
            try:
                await self.scan_pools()
            except Exception as e:
                self._logger.error(
                    "pool_scan_error",
                    error=str(e),
                )
            
            # Wait for next scan interval
            await asyncio.sleep(self.scan_interval_seconds)
