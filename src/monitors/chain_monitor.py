"""Chain monitor for orchestrating block processing and transaction analysis"""

import asyncio
import time
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Coroutine, Dict, Optional

import structlog

from src.chains.connector import ChainConnector
from src.database.manager import DatabaseManager
from src.database.models import ArbitrageTransaction
from src.detectors.profit_calculator import ProfitCalculator
from src.detectors.transaction_analyzer import TransactionAnalyzer
from src.monitoring import metrics

logger = structlog.get_logger()


class ChainMonitor:
    """
    Orchestrates blockchain monitoring, transaction analysis, and data persistence.
    
    Responsibilities:
    - Poll for new blocks every 1 second
    - Process all transactions in each block
    - Filter transactions targeting DEX routers
    - Analyze transactions for arbitrage patterns
    - Calculate profit and persist to database
    - Update arbitrageur profiles
    """

    def __init__(
        self,
        chain_connector: ChainConnector,
        transaction_analyzer: TransactionAnalyzer,
        profit_calculator: ProfitCalculator,
        database_manager: DatabaseManager,
        broadcast_callback: Optional[Callable[[Dict[str, Any]], Coroutine]] = None,
    ):
        """
        Initialize chain monitor.
        
        Args:
            chain_connector: ChainConnector instance for blockchain interaction
            transaction_analyzer: TransactionAnalyzer for detecting arbitrage
            profit_calculator: ProfitCalculator for profit calculations
            database_manager: DatabaseManager for data persistence
            broadcast_callback: Optional callback for broadcasting transactions via WebSocket
        """
        self.chain_connector = chain_connector
        self.transaction_analyzer = transaction_analyzer
        self.profit_calculator = profit_calculator
        self.database_manager = database_manager
        self.broadcast_callback = broadcast_callback
        
        self.chain_name = chain_connector.chain_name
        self.chain_id = chain_connector.chain_id
        
        # Track last synced block
        self.last_synced_block: Optional[int] = None
        
        # Control flags
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        self._logger = logger.bind(
            component="chain_monitor",
            chain=self.chain_name,
            chain_id=self.chain_id,
        )

    async def start(self) -> None:
        """Start monitoring the blockchain"""
        if self._running:
            self._logger.warning("chain_monitor_already_running")
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        self._logger.info("chain_monitor_started")

    async def stop(self) -> None:
        """Stop monitoring gracefully"""
        if not self._running:
            self._logger.warning("chain_monitor_not_running")
            return
        
        self._running = False
        
        # Cancel the monitor task
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                self._logger.info("chain_monitor_task_cancelled")
        
        self._logger.info("chain_monitor_stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop that polls for new blocks"""
        self._logger.info("chain_monitor_loop_started")
        
        try:
            while self._running:
                try:
                    # Get latest block number
                    latest_block = await self.chain_connector.get_latest_block()
                    
                    # Initialize last_synced_block if not set
                    if self.last_synced_block is None:
                        self.last_synced_block = latest_block - 1
                        self._logger.info(
                            "chain_monitor_initialized",
                            starting_block=self.last_synced_block,
                        )
                    
                    # Process new blocks
                    if latest_block > self.last_synced_block:
                        blocks_behind = latest_block - self.last_synced_block
                        
                        # Update blocks_behind metric
                        metrics.chain_blocks_behind.labels(chain=self.chain_name).set(blocks_behind)
                        
                        self._logger.debug(
                            "new_blocks_detected",
                            latest_block=latest_block,
                            last_synced=self.last_synced_block,
                            blocks_behind=blocks_behind,
                        )
                        
                        # Process blocks sequentially
                        for block_number in range(self.last_synced_block + 1, latest_block + 1):
                            if not self._running:
                                break
                            
                            await self._process_block(block_number)
                            self.last_synced_block = block_number
                    
                    # Poll every 1 second
                    await asyncio.sleep(1.0)
                    
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self._logger.error(
                        "chain_monitor_loop_error",
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    # Continue monitoring despite errors
                    await asyncio.sleep(1.0)
        
        except asyncio.CancelledError:
            self._logger.info("chain_monitor_loop_cancelled")
        finally:
            self._logger.info("chain_monitor_loop_exited")

    async def _process_block(self, block_number: int) -> None:
        """
        Process all transactions in a block.
        
        Args:
            block_number: Block number to process
        """
        try:
            # Get block data with full transactions
            block = await self.chain_connector.get_block(block_number, full_transactions=True)
            
            transactions = block.get("transactions", [])
            
            self._logger.debug(
                "processing_block",
                block_number=block_number,
                transaction_count=len(transactions),
            )
            
            # Filter and process transactions
            for tx in transactions:
                if not self._running:
                    break
                
                # Filter transactions targeting DEX routers
                to_address = tx.get("to")
                if to_address and self.chain_connector.is_dex_router(to_address):
                    await self._process_transaction(tx, block)
            
            self._logger.debug(
                "block_processed",
                block_number=block_number,
                transaction_count=len(transactions),
            )
        
        except Exception as e:
            self._logger.error(
                "block_processing_error",
                block_number=block_number,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Continue processing despite errors

    async def _process_transaction(self, transaction: dict, block: dict) -> None:
        """
        Process a single transaction through the analysis pipeline.
        
        Args:
            transaction: Transaction data
            block: Block data containing the transaction
        """
        tx_hash = transaction.get("hash")
        if isinstance(tx_hash, bytes):
            tx_hash = tx_hash.hex()
        
        try:
            # Get transaction receipt
            receipt = await self.chain_connector.get_transaction_receipt(tx_hash)
            
            # Check if transaction is arbitrage
            if not self.transaction_analyzer.is_arbitrage(receipt, transaction):
                return
            
            # Parse swap events
            swap_events = self.transaction_analyzer.parse_swap_events(receipt)
            
            if not swap_events or len(swap_events) < 2:
                self._logger.warning(
                    "arbitrage_insufficient_swap_events",
                    tx_hash=tx_hash,
                    swap_count=len(swap_events) if swap_events else 0,
                )
                return
            
            # Calculate profit
            profit_data = self.profit_calculator.calculate_profit(swap_events, receipt)
            
            # Extract transaction details
            from_address = transaction.get("from", "")
            block_number = transaction.get("blockNumber", 0)
            block_timestamp = datetime.fromtimestamp(block.get("timestamp", 0))
            
            # Determine strategy based on swap count
            swap_count = len(swap_events)
            if swap_count == 2:
                strategy = "2-hop"
            elif swap_count == 3:
                strategy = "3-hop"
            elif swap_count == 4:
                strategy = "4-hop"
            else:
                strategy = f"{swap_count}-hop"
            
            # Extract pools and tokens involved
            pools_involved = list(set(swap.pool_address for swap in swap_events))
            # For tokens, we'd need additional logic to extract token addresses
            # For now, use empty list as placeholder
            tokens_involved = []
            
            # Create ArbitrageTransaction object
            arb_transaction = ArbitrageTransaction(
                chain_id=self.chain_id,
                tx_hash=tx_hash,
                from_address=from_address,
                block_number=block_number,
                block_timestamp=block_timestamp,
                gas_price_gwei=profit_data.gas_cost.gas_price_gwei if profit_data else Decimal("0"),
                gas_used=profit_data.gas_cost.gas_used if profit_data else 0,
                gas_cost_native=profit_data.gas_cost.gas_cost_native if profit_data else Decimal("0"),
                gas_cost_usd=profit_data.gas_cost.gas_cost_usd if profit_data else Decimal("0"),
                swap_count=swap_count,
                strategy=strategy,
                profit_gross_usd=profit_data.gross_profit_usd if profit_data else None,
                profit_net_usd=profit_data.net_profit_usd if profit_data else None,
                pools_involved=pools_involved,
                tokens_involved=tokens_involved,
                detected_at=datetime.utcnow(),
            )
            
            # Save transaction to database
            await self.database_manager.save_transaction(arb_transaction)
            
            # Update arbitrageur profile
            tx_data = {
                "success": receipt.get("status", 0) == 1,
                "profit_usd": profit_data.net_profit_usd if profit_data else Decimal("0"),
                "gas_spent_usd": profit_data.gas_cost.gas_cost_usd if profit_data else Decimal("0"),
                "gas_price_gwei": profit_data.gas_cost.gas_price_gwei if profit_data else Decimal("0"),
                "strategy": strategy,
            }
            
            await self.database_manager.update_arbitrageur(
                from_address,
                self.chain_id,
                tx_data,
            )
            
            # Update metrics
            metrics.transactions_detected.labels(chain=self.chain_name).inc()
            if profit_data and profit_data.net_profit_usd:
                metrics.total_profit_detected_usd.labels(chain=self.chain_name).inc(
                    float(profit_data.net_profit_usd)
                )
            
            self._logger.info(
                "arbitrage_transaction_processed",
                tx_hash=tx_hash,
                from_address=from_address,
                swap_count=swap_count,
                strategy=strategy,
                profit_usd=float(profit_data.net_profit_usd) if profit_data else 0.0,
            )
            
            # Broadcast transaction via WebSocket if callback is available
            if self.broadcast_callback:
                try:
                    transaction_data = asdict(arb_transaction)
                    await self.broadcast_callback(transaction_data)
                except Exception as e:
                    self._logger.error(
                        "failed_to_broadcast_transaction",
                        tx_hash=tx_hash,
                        error=str(e),
                    )
        
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._logger.error(
                "transaction_processing_error",
                tx_hash=tx_hash,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Continue processing despite errors
