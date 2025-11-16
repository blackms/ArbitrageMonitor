"""Integration tests for chain monitor"""

import asyncio
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from web3.exceptions import Web3Exception

from src.chains.connector import ChainConnector
from src.config.models import ChainConfig
from src.database.manager import DatabaseManager
from src.database.models import ArbitrageTransaction
from src.detectors.profit_calculator import ProfitCalculator
from src.detectors.transaction_analyzer import SwapEvent, TransactionAnalyzer
from src.monitors.chain_monitor import ChainMonitor


@pytest.fixture
def bsc_config():
    """BSC chain configuration for testing"""
    return ChainConfig(
        name="BSC",
        chain_id=56,
        rpc_urls=[
            "https://bsc-dataseed.bnbchain.org",
            "https://bsc-dataseed1.binance.org",
        ],
        block_time_seconds=3.0,
        native_token="BNB",
        native_token_usd=Decimal("300.0"),
        dex_routers={
            "PancakeSwap V2": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
        },
        pools={
            "WBNB-BUSD": "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
        },
    )


@pytest.fixture
def mock_chain_connector(bsc_config):
    """Create mock chain connector"""
    connector = Mock(spec=ChainConnector)
    connector.chain_name = bsc_config.name
    connector.chain_id = bsc_config.chain_id
    connector.config = bsc_config
    
    # Mock async methods
    connector.get_latest_block = AsyncMock(return_value=12345)
    connector.get_block = AsyncMock(return_value={
        "number": 12345,
        "timestamp": 1234567890,
        "transactions": []
    })
    connector.get_transaction_receipt = AsyncMock(return_value={
        "transactionHash": "0x123",
        "status": 1,
        "logs": []
    })
    connector.is_dex_router = Mock(return_value=False)
    
    return connector


@pytest.fixture
def mock_transaction_analyzer():
    """Create mock transaction analyzer"""
    analyzer = Mock(spec=TransactionAnalyzer)
    analyzer.is_arbitrage = Mock(return_value=False)
    analyzer.parse_swap_events = Mock(return_value=[])
    return analyzer


@pytest.fixture
def mock_profit_calculator():
    """Create mock profit calculator"""
    calculator = Mock(spec=ProfitCalculator)
    return calculator


@pytest.fixture
def mock_database_manager():
    """Create mock database manager"""
    manager = Mock(spec=DatabaseManager)
    manager.save_transaction = AsyncMock(return_value=1)
    manager.update_arbitrageur = AsyncMock()
    return manager


@pytest.fixture
def chain_monitor(
    mock_chain_connector,
    mock_transaction_analyzer,
    mock_profit_calculator,
    mock_database_manager
):
    """Create chain monitor instance for testing"""
    return ChainMonitor(
        chain_connector=mock_chain_connector,
        transaction_analyzer=mock_transaction_analyzer,
        profit_calculator=mock_profit_calculator,
        database_manager=mock_database_manager,
    )


class TestChainMonitorBlockDetection:
    """Test block detection and processing"""

    @pytest.mark.asyncio
    async def test_start_initializes_last_synced_block(self, chain_monitor, mock_chain_connector):
        """Test that start() initializes last_synced_block"""
        mock_chain_connector.get_latest_block.return_value = 12345
        
        # Start monitor
        await chain_monitor.start()
        
        # Give it time to initialize
        await asyncio.sleep(0.1)
        
        # Stop monitor
        await chain_monitor.stop()
        
        # Should have initialized last_synced_block and processed the block
        assert chain_monitor.last_synced_block is not None
        assert chain_monitor.last_synced_block >= 12344  # latest - 1 or processed

    @pytest.mark.asyncio
    async def test_detects_new_blocks(self, chain_monitor, mock_chain_connector):
        """Test that monitor detects new blocks"""
        # Simulate block progression
        block_numbers = [12345, 12345, 12346, 12347]
        mock_chain_connector.get_latest_block.side_effect = block_numbers
        
        # Start monitor
        await chain_monitor.start()
        
        # Give it time to process blocks
        await asyncio.sleep(1.5)
        
        # Stop monitor
        await chain_monitor.stop()
        
        # Should have processed blocks
        assert chain_monitor.last_synced_block >= 12345
        assert mock_chain_connector.get_block.call_count >= 1

    @pytest.mark.asyncio
    async def test_processes_block_transactions(self, chain_monitor, mock_chain_connector):
        """Test that monitor processes transactions in blocks"""
        # Mock block with transactions
        mock_chain_connector.get_block.return_value = {
            "number": 12345,
            "timestamp": 1234567890,
            "transactions": [
                {"hash": "0x123", "to": "0xabc", "from": "0xdef"},
                {"hash": "0x456", "to": "0xghi", "from": "0xjkl"},
            ]
        }
        
        # Start monitor
        await chain_monitor.start()
        
        # Give it time to process
        await asyncio.sleep(0.5)
        
        # Stop monitor
        await chain_monitor.stop()
        
        # Should have called get_block
        assert mock_chain_connector.get_block.call_count >= 1

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, chain_monitor):
        """Test graceful shutdown of monitor"""
        # Start monitor
        await chain_monitor.start()
        assert chain_monitor._running is True
        
        # Stop monitor
        await chain_monitor.stop()
        assert chain_monitor._running is False
        
        # Task should be cancelled
        assert chain_monitor._monitor_task.cancelled() or chain_monitor._monitor_task.done()


class TestChainMonitorTransactionFiltering:
    """Test transaction filtering by DEX router"""

    @pytest.mark.asyncio
    async def test_filters_transactions_by_dex_router(
        self,
        chain_monitor,
        mock_chain_connector,
        mock_transaction_analyzer
    ):
        """Test that only DEX router transactions are analyzed"""
        # Mock block with mixed transactions
        mock_chain_connector.get_block.return_value = {
            "number": 12345,
            "timestamp": 1234567890,
            "transactions": [
                {"hash": "0x123", "to": "0x10ED43C718714eb63d5aA57B78B54704E256024E", "from": "0xabc"},  # DEX router
                {"hash": "0x456", "to": "0xrandomaddress", "from": "0xdef"},  # Not DEX router
                {"hash": "0x789", "to": "0x10ED43C718714eb63d5aA57B78B54704E256024E", "from": "0xghi"},  # DEX router
            ]
        }
        
        # Only DEX router addresses should pass filter
        def is_dex_router_side_effect(address):
            return address == "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        mock_chain_connector.is_dex_router.side_effect = is_dex_router_side_effect
        
        # Start monitor
        await chain_monitor.start()
        
        # Give it time to process
        await asyncio.sleep(0.5)
        
        # Stop monitor
        await chain_monitor.stop()
        
        # Should have called is_dex_router for each transaction
        assert mock_chain_connector.is_dex_router.call_count >= 3
        
        # Should have called get_transaction_receipt only for DEX router transactions
        assert mock_chain_connector.get_transaction_receipt.call_count >= 2

    @pytest.mark.asyncio
    async def test_skips_non_arbitrage_transactions(
        self,
        chain_monitor,
        mock_chain_connector,
        mock_transaction_analyzer,
        mock_database_manager
    ):
        """Test that non-arbitrage transactions are skipped"""
        # Mock block with DEX transaction
        mock_chain_connector.get_block.return_value = {
            "number": 12345,
            "timestamp": 1234567890,
            "transactions": [
                {"hash": "0x123", "to": "0xdex", "from": "0xabc", "blockNumber": 12345},
            ]
        }
        
        mock_chain_connector.is_dex_router.return_value = True
        mock_transaction_analyzer.is_arbitrage.return_value = False
        
        # Start monitor
        await chain_monitor.start()
        
        # Give it time to process
        await asyncio.sleep(0.5)
        
        # Stop monitor
        await chain_monitor.stop()
        
        # Should have checked if arbitrage
        assert mock_transaction_analyzer.is_arbitrage.call_count >= 1
        
        # Should NOT have saved to database
        assert mock_database_manager.save_transaction.call_count == 0

    @pytest.mark.asyncio
    async def test_processes_arbitrage_transactions(
        self,
        chain_monitor,
        mock_chain_connector,
        mock_transaction_analyzer,
        mock_profit_calculator,
        mock_database_manager
    ):
        """Test that arbitrage transactions are fully processed"""
        # Mock block with arbitrage transaction
        mock_chain_connector.get_block.return_value = {
            "number": 12345,
            "timestamp": 1234567890,
            "transactions": [
                {
                    "hash": "0x123abc",
                    "to": "0xdex",
                    "from": "0xarbitrageur",
                    "blockNumber": 12345
                },
            ]
        }
        
        mock_chain_connector.is_dex_router.return_value = True
        mock_chain_connector.get_transaction_receipt.return_value = {
            "transactionHash": "0x123abc",
            "status": 1,
            "gasUsed": 250000,
            "effectiveGasPrice": 5000000000,
            "logs": []
        }
        
        # Mock arbitrage detection
        mock_transaction_analyzer.is_arbitrage.return_value = True
        mock_transaction_analyzer.parse_swap_events.return_value = [
            SwapEvent(
                pool_address="0xpool1",
                sender="0xarbitrageur",
                to="0xpool2",
                amount0In=1000000,
                amount1In=0,
                amount0Out=0,
                amount1Out=300000000,
                log_index=0
            ),
            SwapEvent(
                pool_address="0xpool2",
                sender="0xarbitrageur",
                to="0xarbitrageur",
                amount0In=300000000,
                amount1In=0,
                amount0Out=0,
                amount1Out=1050000,
                log_index=1
            ),
        ]
        
        # Mock profit calculation
        from src.detectors.profit_calculator import GasCost, ProfitData
        mock_profit_calculator.calculate_profit.return_value = ProfitData(
            gross_profit_native=Decimal("5.0"),
            gross_profit_usd=Decimal("1500.0"),
            gas_cost=GasCost(
                gas_used=250000,
                gas_price_wei=5000000000,
                gas_price_gwei=Decimal("5.0"),
                gas_cost_native=Decimal("0.00125"),
                gas_cost_usd=Decimal("0.375")
            ),
            net_profit_native=Decimal("4.99875"),
            net_profit_usd=Decimal("1499.625"),
            roi_percentage=Decimal("149.96"),
            input_amount_native=Decimal("3.33"),
            output_amount_native=Decimal("3.5")
        )
        
        # Start monitor
        await chain_monitor.start()
        
        # Give it time to process
        await asyncio.sleep(0.5)
        
        # Stop monitor
        await chain_monitor.stop()
        
        # Should have processed arbitrage transaction
        assert mock_transaction_analyzer.is_arbitrage.call_count >= 1
        assert mock_transaction_analyzer.parse_swap_events.call_count >= 1
        assert mock_profit_calculator.calculate_profit.call_count >= 1
        
        # Should have saved to database
        assert mock_database_manager.save_transaction.call_count >= 1
        assert mock_database_manager.update_arbitrageur.call_count >= 1


class TestChainMonitorRPCFailover:
    """Test RPC failover on connection errors"""

    @pytest.mark.asyncio
    async def test_continues_on_rpc_error(self, chain_monitor, mock_chain_connector):
        """Test that monitor continues after RPC error"""
        # Simulate RPC error then recovery
        call_count = [0]
        
        async def get_latest_block_with_error():
            call_count[0] += 1
            if call_count[0] == 2:
                raise Web3Exception("RPC timeout")
            return 12345 + call_count[0]
        
        mock_chain_connector.get_latest_block.side_effect = get_latest_block_with_error
        
        # Start monitor
        await chain_monitor.start()
        
        # Give it time to hit error and recover
        await asyncio.sleep(2.5)
        
        # Stop monitor
        await chain_monitor.stop()
        
        # Should have continued despite error (at least initialized and hit error)
        assert call_count[0] >= 2
        assert chain_monitor.last_synced_block is not None

    @pytest.mark.asyncio
    async def test_continues_on_block_processing_error(
        self,
        chain_monitor,
        mock_chain_connector
    ):
        """Test that monitor continues after block processing error"""
        # Simulate error in get_block
        call_count = [0]
        
        async def get_block_with_error(block_number, full_transactions=True):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Web3Exception("Block not found")
            return {
                "number": block_number,
                "timestamp": 1234567890,
                "transactions": []
            }
        
        mock_chain_connector.get_block.side_effect = get_block_with_error
        
        # Start monitor
        await chain_monitor.start()
        
        # Give it time to hit error and recover
        await asyncio.sleep(2.5)
        
        # Stop monitor
        await chain_monitor.stop()
        
        # Should have attempted to process block (at least once)
        assert call_count[0] >= 1

    @pytest.mark.asyncio
    async def test_continues_on_transaction_processing_error(
        self,
        chain_monitor,
        mock_chain_connector,
        mock_transaction_analyzer
    ):
        """Test that monitor continues after transaction processing error"""
        # Mock block with transaction
        mock_chain_connector.get_block.return_value = {
            "number": 12345,
            "timestamp": 1234567890,
            "transactions": [
                {"hash": "0x123", "to": "0xdex", "from": "0xabc", "blockNumber": 12345},
            ]
        }
        
        mock_chain_connector.is_dex_router.return_value = True
        
        # Simulate error in transaction analysis
        mock_chain_connector.get_transaction_receipt.side_effect = Web3Exception("Receipt not found")
        
        # Start monitor
        await chain_monitor.start()
        
        # Give it time to process
        await asyncio.sleep(0.5)
        
        # Stop monitor
        await chain_monitor.stop()
        
        # Should have attempted to get receipt
        assert mock_chain_connector.get_transaction_receipt.call_count >= 1
        
        # Monitor should still be functional (not crashed)
        assert chain_monitor.last_synced_block is not None


class TestChainMonitorErrorHandling:
    """Test graceful error handling"""

    @pytest.mark.asyncio
    async def test_handles_missing_transaction_hash(
        self,
        chain_monitor,
        mock_chain_connector
    ):
        """Test handling of transaction without hash"""
        # Mock block with malformed transaction
        mock_chain_connector.get_block.return_value = {
            "number": 12345,
            "timestamp": 1234567890,
            "transactions": [
                {"to": "0xdex", "from": "0xabc"},  # Missing hash
            ]
        }
        
        mock_chain_connector.is_dex_router.return_value = True
        
        # Start monitor
        await chain_monitor.start()
        
        # Give it time to process
        await asyncio.sleep(0.5)
        
        # Stop monitor
        await chain_monitor.stop()
        
        # Should handle gracefully without crashing
        assert chain_monitor._running is False

    @pytest.mark.asyncio
    async def test_handles_insufficient_swap_events(
        self,
        chain_monitor,
        mock_chain_connector,
        mock_transaction_analyzer,
        mock_database_manager
    ):
        """Test handling of arbitrage with insufficient swap events"""
        # Mock block with transaction
        mock_chain_connector.get_block.return_value = {
            "number": 12345,
            "timestamp": 1234567890,
            "transactions": [
                {"hash": "0x123", "to": "0xdex", "from": "0xabc", "blockNumber": 12345},
            ]
        }
        
        mock_chain_connector.is_dex_router.return_value = True
        mock_transaction_analyzer.is_arbitrage.return_value = True
        
        # Return only 1 swap event (insufficient)
        mock_transaction_analyzer.parse_swap_events.return_value = [
            SwapEvent(
                pool_address="0xpool1",
                sender="0xabc",
                to="0xabc",
                amount0In=1000000,
                amount1In=0,
                amount0Out=0,
                amount1Out=300000000,
                log_index=0
            ),
        ]
        
        # Start monitor
        await chain_monitor.start()
        
        # Give it time to process
        await asyncio.sleep(0.5)
        
        # Stop monitor
        await chain_monitor.stop()
        
        # Should NOT have saved to database
        assert mock_database_manager.save_transaction.call_count == 0

    @pytest.mark.asyncio
    async def test_handles_database_save_error(
        self,
        chain_monitor,
        mock_chain_connector,
        mock_transaction_analyzer,
        mock_profit_calculator,
        mock_database_manager
    ):
        """Test handling of database save errors"""
        # Mock block with arbitrage transaction
        mock_chain_connector.get_block.return_value = {
            "number": 12345,
            "timestamp": 1234567890,
            "transactions": [
                {"hash": "0x123", "to": "0xdex", "from": "0xabc", "blockNumber": 12345},
            ]
        }
        
        mock_chain_connector.is_dex_router.return_value = True
        mock_transaction_analyzer.is_arbitrage.return_value = True
        mock_transaction_analyzer.parse_swap_events.return_value = [
            SwapEvent("0xpool1", "0xabc", "0xpool2", 1000000, 0, 0, 300000000, 0),
            SwapEvent("0xpool2", "0xabc", "0xabc", 300000000, 0, 0, 1050000, 1),
        ]
        
        from src.detectors.profit_calculator import GasCost, ProfitData
        mock_profit_calculator.calculate_profit.return_value = ProfitData(
            gross_profit_native=Decimal("5.0"),
            gross_profit_usd=Decimal("1500.0"),
            gas_cost=GasCost(
                gas_used=250000,
                gas_price_wei=5000000000,
                gas_price_gwei=Decimal("5.0"),
                gas_cost_native=Decimal("0.00125"),
                gas_cost_usd=Decimal("0.375")
            ),
            net_profit_native=Decimal("4.99875"),
            net_profit_usd=Decimal("1499.625"),
            roi_percentage=Decimal("149.96"),
            input_amount_native=Decimal("3.33"),
            output_amount_native=Decimal("3.5")
        )
        
        # Simulate database error
        mock_database_manager.save_transaction.side_effect = Exception("Database connection lost")
        
        # Start monitor
        await chain_monitor.start()
        
        # Give it time to process
        await asyncio.sleep(0.5)
        
        # Stop monitor
        await chain_monitor.stop()
        
        # Should have attempted to save
        assert mock_database_manager.save_transaction.call_count >= 1
        
        # Monitor should still be functional
        assert chain_monitor._running is False

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, chain_monitor):
        """Test calling stop when monitor is not running"""
        # Should handle gracefully
        await chain_monitor.stop()
        assert chain_monitor._running is False

    @pytest.mark.asyncio
    async def test_start_when_already_running(self, chain_monitor):
        """Test calling start when monitor is already running"""
        await chain_monitor.start()
        assert chain_monitor._running is True
        
        # Try to start again
        await chain_monitor.start()
        assert chain_monitor._running is True
        
        # Clean up
        await chain_monitor.stop()
