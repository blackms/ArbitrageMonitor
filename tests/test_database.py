"""Integration tests for database manager

These tests require a PostgreSQL test database to be running.
To run these tests, ensure you have a PostgreSQL instance with:
- Database: arbitrage_monitor_test
- User: monitor
- Password: password
- Host: localhost
- Port: 5432

You can set up a test database with Docker:
docker run --name postgres-test -e POSTGRES_DB=arbitrage_monitor_test \
    -e POSTGRES_USER=monitor -e POSTGRES_PASSWORD=password \
    -p 5432:5432 -d postgres:15

Or skip these tests with: pytest -m "not integration"
"""

import asyncio
import os
from datetime import datetime
from decimal import Decimal

import pytest

from src.database import (
    Arbitrageur,
    ArbitrageurFilters,
    ArbitrageTransaction,
    DatabaseManager,
    Opportunity,
    OpportunityFilters,
    TransactionFilters,
)


# Test database URL - can be overridden with TEST_DATABASE_URL environment variable
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://monitor:password@localhost:5432/arbitrage_monitor_test"
)

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture
async def db_manager():
    """Create database manager for testing"""
    manager = DatabaseManager(TEST_DATABASE_URL, min_pool_size=2, max_pool_size=5)
    
    try:
        await manager.connect()
        await manager.initialize_schema()
        
        # Insert test chain data
        async with manager.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chains (name, chain_id, rpc_primary, block_time_seconds, 
                                   native_token, native_token_usd)
                VALUES ('BSC', 56, 'https://bsc-dataseed.bnbchain.org', 3.0, 'BNB', 300.0),
                       ('Polygon', 137, 'https://polygon-rpc.com', 2.0, 'MATIC', 0.8)
                ON CONFLICT (chain_id) DO NOTHING
                """
            )
        
        yield manager
    finally:
        # Cleanup
        if manager.pool:
            async with manager.pool.acquire() as conn:
                await conn.execute("TRUNCATE opportunities, transactions, arbitrageurs, chain_stats CASCADE")
        await manager.disconnect()


def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require database)"
    )


@pytest.mark.asyncio
async def test_connection_pooling(db_manager):
    """Test connection pool initialization"""
    assert db_manager.pool is not None
    assert db_manager.get_pool_size() >= db_manager.min_pool_size
    assert db_manager.get_pool_size() <= db_manager.max_pool_size


@pytest.mark.asyncio
async def test_save_opportunity(db_manager):
    """Test saving opportunity to database"""
    opportunity = Opportunity(
        chain_id=56,
        pool_name="WBNB-BUSD",
        pool_address="0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
        imbalance_pct=Decimal("7.5"),
        profit_usd=Decimal("15000.50"),
        profit_native=Decimal("50.0"),
        reserve0=Decimal("1000000.0"),
        reserve1=Decimal("300000000.0"),
        block_number=12345678,
        detected_at=datetime.utcnow(),
    )
    
    opportunity_id = await db_manager.save_opportunity(opportunity)
    assert opportunity_id > 0
    
    # Verify saved
    opportunities = await db_manager.get_opportunities(
        OpportunityFilters(chain_id=56, limit=1)
    )
    assert len(opportunities) == 1
    assert opportunities[0].pool_name == "WBNB-BUSD"
    assert opportunities[0].profit_usd == Decimal("15000.50")


@pytest.mark.asyncio
async def test_save_transaction(db_manager):
    """Test saving arbitrage transaction to database"""
    transaction = ArbitrageTransaction(
        chain_id=56,
        tx_hash="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        from_address="0xabcdef1234567890abcdef1234567890abcdef12",
        block_number=12345678,
        block_timestamp=datetime.utcnow(),
        gas_price_gwei=Decimal("5.0"),
        gas_used=250000,
        gas_cost_native=Decimal("0.00125"),
        gas_cost_usd=Decimal("0.375"),
        swap_count=3,
        strategy="3-hop",
        profit_gross_usd=Decimal("1500.0"),
        profit_net_usd=Decimal("1499.625"),
        pools_involved=["0xpool1", "0xpool2", "0xpool3"],
        tokens_involved=["WBNB", "BUSD", "USDT"],
        detected_at=datetime.utcnow(),
    )
    
    transaction_id = await db_manager.save_transaction(transaction)
    assert transaction_id > 0
    
    # Verify saved
    transactions = await db_manager.get_transactions(
        TransactionFilters(chain_id=56, limit=1)
    )
    assert len(transactions) == 1
    assert transactions[0].tx_hash == transaction.tx_hash
    assert transactions[0].swap_count == 3
    assert transactions[0].strategy == "3-hop"


@pytest.mark.asyncio
async def test_save_transaction_duplicate(db_manager):
    """Test saving duplicate transaction updates existing record"""
    transaction = ArbitrageTransaction(
        chain_id=56,
        tx_hash="0xduplicate1234567890abcdef1234567890abcdef1234567890abcdef12345678",
        from_address="0xabcdef1234567890abcdef1234567890abcdef12",
        block_number=12345678,
        block_timestamp=datetime.utcnow(),
        gas_price_gwei=Decimal("5.0"),
        gas_used=250000,
        gas_cost_native=Decimal("0.00125"),
        gas_cost_usd=Decimal("0.375"),
        swap_count=2,
        strategy="2-hop",
        pools_involved=["0xpool1", "0xpool2"],
        tokens_involved=["WBNB", "BUSD"],
        detected_at=datetime.utcnow(),
    )
    
    # Save first time
    tx_id_1 = await db_manager.save_transaction(transaction)
    
    # Update with profit data
    transaction.profit_gross_usd = Decimal("1000.0")
    transaction.profit_net_usd = Decimal("999.625")
    
    # Save again (should update)
    tx_id_2 = await db_manager.save_transaction(transaction)
    
    # Should return same ID
    assert tx_id_1 == tx_id_2
    
    # Verify updated
    transactions = await db_manager.get_transactions(
        TransactionFilters(chain_id=56, limit=10)
    )
    matching = [t for t in transactions if t.tx_hash == transaction.tx_hash]
    assert len(matching) == 1
    assert matching[0].profit_net_usd == Decimal("999.625")


@pytest.mark.asyncio
async def test_update_arbitrageur_new(db_manager):
    """Test creating new arbitrageur profile"""
    address = "0x1234567890123456789012345678901234567890"
    chain_id = 56
    
    tx_data = {
        "success": True,
        "profit_usd": Decimal("500.0"),
        "gas_spent_usd": Decimal("10.0"),
        "gas_price_gwei": Decimal("5.0"),
        "strategy": "2-hop",
    }
    
    await db_manager.update_arbitrageur(address, chain_id, tx_data)
    
    # Verify created
    arbitrageurs = await db_manager.get_arbitrageurs(
        ArbitrageurFilters(chain_id=56)
    )
    assert len(arbitrageurs) >= 1
    
    arb = next((a for a in arbitrageurs if a.address == address), None)
    assert arb is not None
    assert arb.total_transactions == 1
    assert arb.successful_transactions == 1
    assert arb.total_profit_usd == Decimal("500.0")
    assert arb.preferred_strategy == "2-hop"


@pytest.mark.asyncio
async def test_update_arbitrageur_existing(db_manager):
    """Test updating existing arbitrageur profile"""
    address = "0x9876543210987654321098765432109876543210"
    chain_id = 56
    
    # First transaction
    tx_data_1 = {
        "success": True,
        "profit_usd": Decimal("500.0"),
        "gas_spent_usd": Decimal("10.0"),
        "gas_price_gwei": Decimal("5.0"),
        "strategy": "2-hop",
    }
    await db_manager.update_arbitrageur(address, chain_id, tx_data_1)
    
    # Second transaction
    tx_data_2 = {
        "success": True,
        "profit_usd": Decimal("750.0"),
        "gas_spent_usd": Decimal("15.0"),
        "gas_price_gwei": Decimal("6.0"),
        "strategy": "3-hop",
    }
    await db_manager.update_arbitrageur(address, chain_id, tx_data_2)
    
    # Verify updated
    arbitrageurs = await db_manager.get_arbitrageurs(
        ArbitrageurFilters(chain_id=56)
    )
    arb = next((a for a in arbitrageurs if a.address == address), None)
    
    assert arb is not None
    assert arb.total_transactions == 2
    assert arb.successful_transactions == 2
    assert arb.total_profit_usd == Decimal("1250.0")
    assert arb.total_gas_spent_usd == Decimal("25.0")
    # Average gas price: (5.0 + 6.0) / 2 = 5.5
    assert abs(arb.avg_gas_price_gwei - Decimal("5.5")) < Decimal("0.01")


@pytest.mark.asyncio
async def test_get_opportunities_with_filters(db_manager):
    """Test querying opportunities with various filters"""
    # Create test opportunities
    for i in range(5):
        opp = Opportunity(
            chain_id=56,
            pool_name=f"Pool-{i}",
            pool_address=f"0xpool{i:040d}",
            imbalance_pct=Decimal(f"{5 + i}.0"),
            profit_usd=Decimal(f"{10000 + i * 5000}.0"),
            profit_native=Decimal(f"{30 + i * 10}.0"),
            reserve0=Decimal("1000000.0"),
            reserve1=Decimal("300000000.0"),
            block_number=12345678 + i,
            detected_at=datetime.utcnow(),
        )
        await db_manager.save_opportunity(opp)
    
    # Test min_profit filter
    opportunities = await db_manager.get_opportunities(
        OpportunityFilters(chain_id=56, min_profit=Decimal("20000.0"))
    )
    assert len(opportunities) >= 3
    assert all(o.profit_usd >= Decimal("20000.0") for o in opportunities)
    
    # Test max_profit filter
    opportunities = await db_manager.get_opportunities(
        OpportunityFilters(chain_id=56, max_profit=Decimal("15000.0"))
    )
    assert len(opportunities) >= 1
    assert all(o.profit_usd <= Decimal("15000.0") for o in opportunities)
    
    # Test limit
    opportunities = await db_manager.get_opportunities(
        OpportunityFilters(chain_id=56, limit=2)
    )
    assert len(opportunities) == 2


@pytest.mark.asyncio
async def test_get_transactions_with_filters(db_manager):
    """Test querying transactions with various filters"""
    address1 = "0xaddr1000000000000000000000000000000000001"
    address2 = "0xaddr2000000000000000000000000000000000002"
    
    # Create test transactions
    for i in range(3):
        tx = ArbitrageTransaction(
            chain_id=56,
            tx_hash=f"0xtx{i:062d}",
            from_address=address1 if i < 2 else address2,
            block_number=12345678 + i,
            block_timestamp=datetime.utcnow(),
            gas_price_gwei=Decimal("5.0"),
            gas_used=250000,
            gas_cost_native=Decimal("0.00125"),
            gas_cost_usd=Decimal("0.375"),
            swap_count=2 + i,
            strategy=f"{2 + i}-hop",
            profit_net_usd=Decimal(f"{1000 + i * 500}.0"),
            pools_involved=[f"0xpool{j}" for j in range(2 + i)],
            tokens_involved=["WBNB", "BUSD"],
            detected_at=datetime.utcnow(),
        )
        await db_manager.save_transaction(tx)
    
    # Test from_address filter
    transactions = await db_manager.get_transactions(
        TransactionFilters(from_address=address1)
    )
    assert len(transactions) == 2
    assert all(t.from_address == address1 for t in transactions)
    
    # Test min_swaps filter
    transactions = await db_manager.get_transactions(
        TransactionFilters(chain_id=56, min_swaps=3)
    )
    assert len(transactions) >= 2
    assert all(t.swap_count >= 3 for t in transactions)
    
    # Test strategy filter
    transactions = await db_manager.get_transactions(
        TransactionFilters(chain_id=56, strategy="2-hop")
    )
    assert len(transactions) >= 1
    assert all(t.strategy == "2-hop" for t in transactions)


@pytest.mark.asyncio
async def test_concurrent_writes(db_manager):
    """Test connection pooling with concurrent writes"""
    
    async def save_opportunity(index: int):
        opp = Opportunity(
            chain_id=56,
            pool_name=f"Concurrent-Pool-{index}",
            pool_address=f"0xconcurrent{index:034d}",
            imbalance_pct=Decimal("5.0"),
            profit_usd=Decimal("10000.0"),
            profit_native=Decimal("30.0"),
            reserve0=Decimal("1000000.0"),
            reserve1=Decimal("300000000.0"),
            block_number=12345678 + index,
            detected_at=datetime.utcnow(),
        )
        return await db_manager.save_opportunity(opp)
    
    # Create 10 concurrent writes
    tasks = [save_opportunity(i) for i in range(10)]
    results = await asyncio.gather(*tasks)
    
    # All should succeed
    assert len(results) == 10
    assert all(r > 0 for r in results)
    
    # Verify all saved
    opportunities = await db_manager.get_opportunities(
        OpportunityFilters(chain_id=56, limit=100)
    )
    concurrent_opps = [o for o in opportunities if "Concurrent-Pool" in o.pool_name]
    assert len(concurrent_opps) == 10


@pytest.mark.asyncio
async def test_transaction_rollback_on_error(db_manager):
    """Test that invalid data doesn't get saved"""
    # Try to save transaction with invalid swap_count (< 2)
    invalid_tx = ArbitrageTransaction(
        chain_id=56,
        tx_hash="0xinvalid1234567890abcdef1234567890abcdef1234567890abcdef123456",
        from_address="0xabcdef1234567890abcdef1234567890abcdef12",
        block_number=12345678,
        block_timestamp=datetime.utcnow(),
        gas_price_gwei=Decimal("5.0"),
        gas_used=250000,
        gas_cost_native=Decimal("0.00125"),
        gas_cost_usd=Decimal("0.375"),
        swap_count=1,  # Invalid: must be >= 2
        strategy="1-hop",
        pools_involved=["0xpool1"],
        tokens_involved=["WBNB"],
        detected_at=datetime.utcnow(),
    )
    
    # Should raise error due to check constraint
    with pytest.raises(Exception):
        await db_manager.save_transaction(invalid_tx)
    
    # Verify nothing was saved
    transactions = await db_manager.get_transactions(
        TransactionFilters(chain_id=56, limit=100)
    )
    assert not any(t.tx_hash == invalid_tx.tx_hash for t in transactions)


@pytest.mark.asyncio
async def test_retry_logic(db_manager):
    """Test retry logic for transient failures"""
    # This test would require mocking to simulate transient failures
    # For now, we just verify the retry mechanism exists
    assert hasattr(db_manager, "_retry_operation")
    
    # Test that normal operations work through retry wrapper
    opportunity = Opportunity(
        chain_id=56,
        pool_name="Retry-Test-Pool",
        pool_address="0xretrytest000000000000000000000000000000",
        imbalance_pct=Decimal("5.0"),
        profit_usd=Decimal("10000.0"),
        profit_native=Decimal("30.0"),
        reserve0=Decimal("1000000.0"),
        reserve1=Decimal("300000000.0"),
        block_number=12345678,
        detected_at=datetime.utcnow(),
    )
    
    opportunity_id = await db_manager.save_opportunity(opportunity)
    assert opportunity_id > 0
