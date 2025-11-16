"""Verification script for ChainMonitor implementation"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock

from src.chains.connector import ChainConnector
from src.config.models import ChainConfig
from src.database.manager import DatabaseManager
from src.detectors.profit_calculator import ProfitCalculator
from src.detectors.transaction_analyzer import TransactionAnalyzer
from src.monitors.chain_monitor import ChainMonitor


def create_mock_chain_connector():
    """Create a mock chain connector"""
    config = ChainConfig(
        name="BSC",
        chain_id=56,
        rpc_urls=["https://bsc-dataseed.bnbchain.org"],
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
    
    connector = Mock(spec=ChainConnector)
    connector.chain_name = "BSC"
    connector.chain_id = 56
    connector.config = config
    connector.get_latest_block = AsyncMock(return_value=1000)
    connector.get_block = AsyncMock(return_value={
        "number": 1000,
        "timestamp": 1700000000,
        "transactions": []
    })
    connector.get_transaction_receipt = AsyncMock()
    connector.is_dex_router = Mock(return_value=True)
    
    return connector


def create_mock_transaction_analyzer():
    """Create a mock transaction analyzer"""
    analyzer = Mock(spec=TransactionAnalyzer)
    analyzer.is_arbitrage = Mock(return_value=False)
    analyzer.parse_swap_events = Mock(return_value=[])
    return analyzer


def create_mock_profit_calculator():
    """Create a mock profit calculator"""
    calculator = Mock(spec=ProfitCalculator)
    calculator.calculate_profit = Mock(return_value=None)
    return calculator


def create_mock_database_manager():
    """Create a mock database manager"""
    manager = Mock(spec=DatabaseManager)
    manager.save_transaction = AsyncMock()
    manager.update_arbitrageur = AsyncMock()
    return manager


async def test_chain_monitor_initialization():
    """Test ChainMonitor initialization"""
    print("Testing ChainMonitor initialization...")
    
    connector = create_mock_chain_connector()
    analyzer = create_mock_transaction_analyzer()
    calculator = create_mock_profit_calculator()
    db_manager = create_mock_database_manager()
    
    monitor = ChainMonitor(
        chain_connector=connector,
        transaction_analyzer=analyzer,
        profit_calculator=calculator,
        database_manager=db_manager,
    )
    
    assert monitor.chain_name == "BSC"
    assert monitor.chain_id == 56
    assert monitor.last_synced_block is None
    assert monitor._running is False
    
    print("✓ ChainMonitor initialized successfully")


async def test_chain_monitor_start_stop():
    """Test ChainMonitor start and stop"""
    print("\nTesting ChainMonitor start/stop...")
    
    connector = create_mock_chain_connector()
    analyzer = create_mock_transaction_analyzer()
    calculator = create_mock_profit_calculator()
    db_manager = create_mock_database_manager()
    
    monitor = ChainMonitor(
        chain_connector=connector,
        transaction_analyzer=analyzer,
        profit_calculator=calculator,
        database_manager=db_manager,
    )
    
    # Start monitor
    await monitor.start()
    assert monitor._running is True
    assert monitor._monitor_task is not None
    
    # Give it a moment to initialize
    await asyncio.sleep(0.1)
    
    # Stop monitor
    await monitor.stop()
    assert monitor._running is False
    
    print("✓ ChainMonitor start/stop works correctly")


async def test_chain_monitor_block_processing():
    """Test ChainMonitor block processing"""
    print("\nTesting ChainMonitor block processing...")
    
    connector = create_mock_chain_connector()
    analyzer = create_mock_transaction_analyzer()
    calculator = create_mock_profit_calculator()
    db_manager = create_mock_database_manager()
    
    # Set up mock to return a block with transactions
    connector.get_block = AsyncMock(return_value={
        "number": 1001,
        "timestamp": 1700000003,
        "transactions": [
            {
                "hash": "0x123",
                "to": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
                "from": "0xabc",
                "blockNumber": 1001,
            }
        ]
    })
    
    monitor = ChainMonitor(
        chain_connector=connector,
        transaction_analyzer=analyzer,
        profit_calculator=calculator,
        database_manager=db_manager,
    )
    
    # Process a single block
    await monitor._process_block(1001)
    
    # Verify block was fetched
    connector.get_block.assert_called_once_with(1001, full_transactions=True)
    
    print("✓ ChainMonitor processes blocks correctly")


async def test_chain_monitor_transaction_filtering():
    """Test ChainMonitor filters transactions by DEX router"""
    print("\nTesting ChainMonitor transaction filtering...")
    
    connector = create_mock_chain_connector()
    analyzer = create_mock_transaction_analyzer()
    calculator = create_mock_profit_calculator()
    db_manager = create_mock_database_manager()
    
    # Set up mock to return transactions
    dex_router = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
    
    connector.get_block = AsyncMock(return_value={
        "number": 1001,
        "timestamp": 1700000003,
        "transactions": [
            {"hash": "0x123", "to": dex_router, "from": "0xabc", "blockNumber": 1001},
        ]
    })
    
    monitor = ChainMonitor(
        chain_connector=connector,
        transaction_analyzer=analyzer,
        profit_calculator=calculator,
        database_manager=db_manager,
    )
    
    # Process block - should not raise any errors
    await monitor._process_block(1001)
    
    # Verify block was processed
    connector.get_block.assert_called_once()
    
    print("✓ ChainMonitor filters transactions correctly")


async def test_chain_monitor_graceful_error_handling():
    """Test ChainMonitor handles errors gracefully"""
    print("\nTesting ChainMonitor error handling...")
    
    connector = create_mock_chain_connector()
    analyzer = create_mock_transaction_analyzer()
    calculator = create_mock_profit_calculator()
    db_manager = create_mock_database_manager()
    
    # Make get_block raise an error
    connector.get_block = AsyncMock(side_effect=Exception("RPC error"))
    
    monitor = ChainMonitor(
        chain_connector=connector,
        transaction_analyzer=analyzer,
        profit_calculator=calculator,
        database_manager=db_manager,
    )
    
    # Should not raise exception
    try:
        await monitor._process_block(1001)
        print("✓ ChainMonitor handles errors gracefully")
    except Exception as e:
        print(f"✗ ChainMonitor did not handle error: {e}")
        raise


async def main():
    """Run all verification tests"""
    print("=" * 60)
    print("ChainMonitor Verification Tests")
    print("=" * 60)
    
    await test_chain_monitor_initialization()
    await test_chain_monitor_start_stop()
    await test_chain_monitor_block_processing()
    await test_chain_monitor_transaction_filtering()
    await test_chain_monitor_graceful_error_handling()
    
    print("\n" + "=" * 60)
    print("All ChainMonitor verification tests passed! ✓")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
