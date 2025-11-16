"""Integration tests for data retention service

These tests require a PostgreSQL test database to be running.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.database import (
    ArbitrageTransaction,
    DatabaseManager,
    Opportunity,
    OpportunityFilters,
    TransactionFilters,
)
from src.services.retention import DataRetentionService


# Test database URL
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
                # Also clean up archive table if it exists
                await conn.execute("DROP TABLE IF EXISTS transactions_archive")
        await manager.disconnect()


@pytest.fixture
async def retention_service(db_manager):
    """Create data retention service for testing"""
    service = DataRetentionService(
        database_manager=db_manager,
        opportunity_retention_days=30,
        transaction_archive_days=90,
        run_hour_utc=2,
    )
    yield service
    # Stop service if it was started
    if service._running:
        await service.stop()


@pytest.mark.asyncio
async def test_delete_old_opportunities(db_manager, retention_service):
    """Test deletion of opportunities older than 30 days"""
    now = datetime.now(timezone.utc)
    
    # Create opportunities at different ages
    opportunities_data = [
        (now - timedelta(days=10), "Recent-1"),  # Should NOT be deleted
        (now - timedelta(days=25), "Recent-2"),  # Should NOT be deleted
        (now - timedelta(days=35), "Old-1"),     # Should be deleted
        (now - timedelta(days=60), "Old-2"),     # Should be deleted
        (now - timedelta(days=90), "Old-3"),     # Should be deleted
    ]
    
    for detected_at, pool_name in opportunities_data:
        opp = Opportunity(
            chain_id=56,
            pool_name=pool_name,
            pool_address=f"0x{pool_name.lower():040s}",
            imbalance_pct=Decimal("5.0"),
            profit_usd=Decimal("10000.0"),
            profit_native=Decimal("30.0"),
            reserve0=Decimal("1000000.0"),
            reserve1=Decimal("300000000.0"),
            block_number=12345678,
            detected_at=detected_at,
        )
        await db_manager.save_opportunity(opp)
    
    # Verify all opportunities were created
    all_opps = await db_manager.get_opportunities(OpportunityFilters(limit=100))
    assert len(all_opps) == 5
    
    # Run deletion
    deleted_count = await retention_service.delete_old_opportunities()
    
    # Should delete 3 old opportunities
    assert deleted_count == 3
    
    # Verify only recent opportunities remain
    remaining_opps = await db_manager.get_opportunities(OpportunityFilters(limit=100))
    assert len(remaining_opps) == 2
    assert all("Recent" in opp.pool_name for opp in remaining_opps)


@pytest.mark.asyncio
async def test_archive_old_transactions(db_manager, retention_service):
    """Test archival of transactions older than 90 days"""
    now = datetime.now(timezone.utc)
    
    # Create transactions at different ages
    transactions_data = [
        (now - timedelta(days=30), "0xtx1recent"),   # Should NOT be archived
        (now - timedelta(days=60), "0xtx2recent"),   # Should NOT be archived
        (now - timedelta(days=95), "0xtx3old"),      # Should be archived
        (now - timedelta(days=120), "0xtx4old"),     # Should be archived
        (now - timedelta(days=180), "0xtx5old"),     # Should be archived
    ]
    
    for block_timestamp, tx_hash in transactions_data:
        tx = ArbitrageTransaction(
            chain_id=56,
            tx_hash=tx_hash.ljust(66, '0'),
            from_address="0xabcdef1234567890abcdef1234567890abcdef12",
            block_number=12345678,
            block_timestamp=block_timestamp,
            gas_price_gwei=Decimal("5.0"),
            gas_used=250000,
            gas_cost_native=Decimal("0.00125"),
            gas_cost_usd=Decimal("0.375"),
            swap_count=2,
            strategy="2-hop",
            profit_gross_usd=Decimal("1000.0"),
            profit_net_usd=Decimal("999.625"),
            pools_involved=["0xpool1", "0xpool2"],
            tokens_involved=["WBNB", "BUSD"],
            detected_at=block_timestamp,
        )
        await db_manager.save_transaction(tx)
    
    # Verify all transactions were created
    all_txs = await db_manager.get_transactions(TransactionFilters(limit=100))
    assert len(all_txs) == 5
    
    # Run archival
    archived_count = await retention_service.archive_old_transactions()
    
    # Should archive 3 old transactions
    assert archived_count == 3
    
    # Verify only recent transactions remain in main table
    remaining_txs = await db_manager.get_transactions(TransactionFilters(limit=100))
    assert len(remaining_txs) == 2
    assert all("recent" in tx.tx_hash for tx in remaining_txs)
    
    # Verify archived transactions are in archive table
    async with db_manager.pool.acquire() as conn:
        archived_rows = await conn.fetch("SELECT * FROM transactions_archive")
        assert len(archived_rows) == 3
        assert all("old" in row["tx_hash"] for row in archived_rows)


@pytest.mark.asyncio
async def test_referential_integrity_maintained(db_manager, retention_service):
    """Test that archival maintains referential integrity with arbitrageurs"""
    now = datetime.now(timezone.utc)
    address = "0x1234567890123456789012345678901234567890"
    
    # Create arbitrageur with transaction
    tx_data = {
        "success": True,
        "profit_usd": Decimal("500.0"),
        "gas_spent_usd": Decimal("10.0"),
        "gas_price_gwei": Decimal("5.0"),
        "strategy": "2-hop",
    }
    await db_manager.update_arbitrageur(address, 56, tx_data)
    
    # Create old transaction from this arbitrageur
    old_tx = ArbitrageTransaction(
        chain_id=56,
        tx_hash="0xtxold1234567890abcdef1234567890abcdef1234567890abcdef123456",
        from_address=address,
        block_number=12345678,
        block_timestamp=now - timedelta(days=100),
        gas_price_gwei=Decimal("5.0"),
        gas_used=250000,
        gas_cost_native=Decimal("0.00125"),
        gas_cost_usd=Decimal("0.375"),
        swap_count=2,
        strategy="2-hop",
        pools_involved=["0xpool1", "0xpool2"],
        tokens_involved=["WBNB", "BUSD"],
        detected_at=now - timedelta(days=100),
    )
    await db_manager.save_transaction(old_tx)
    
    # Archive old transactions
    archived_count = await retention_service.archive_old_transactions()
    assert archived_count == 1
    
    # Verify arbitrageur still exists (referential integrity maintained)
    from src.database.models import ArbitrageurFilters
    arbitrageurs = await db_manager.get_arbitrageurs(ArbitrageurFilters(chain_id=56))
    assert len(arbitrageurs) >= 1
    assert any(arb.address == address for arb in arbitrageurs)


@pytest.mark.asyncio
async def test_run_once_executes_all_jobs(db_manager, retention_service):
    """Test that run_once executes both deletion and archival jobs"""
    now = datetime.now(timezone.utc)
    
    # Create old opportunity
    old_opp = Opportunity(
        chain_id=56,
        pool_name="Old-Opportunity",
        pool_address="0xoldopp000000000000000000000000000000000",
        imbalance_pct=Decimal("5.0"),
        profit_usd=Decimal("10000.0"),
        profit_native=Decimal("30.0"),
        reserve0=Decimal("1000000.0"),
        reserve1=Decimal("300000000.0"),
        block_number=12345678,
        detected_at=now - timedelta(days=40),
    )
    await db_manager.save_opportunity(old_opp)
    
    # Create old transaction
    old_tx = ArbitrageTransaction(
        chain_id=56,
        tx_hash="0xtxold9876543210abcdef1234567890abcdef1234567890abcdef123456",
        from_address="0xabcdef1234567890abcdef1234567890abcdef12",
        block_number=12345678,
        block_timestamp=now - timedelta(days=100),
        gas_price_gwei=Decimal("5.0"),
        gas_used=250000,
        gas_cost_native=Decimal("0.00125"),
        gas_cost_usd=Decimal("0.375"),
        swap_count=2,
        strategy="2-hop",
        pools_involved=["0xpool1", "0xpool2"],
        tokens_involved=["WBNB", "BUSD"],
        detected_at=now - timedelta(days=100),
    )
    await db_manager.save_transaction(old_tx)
    
    # Run all retention jobs
    await retention_service.run_once()
    
    # Verify opportunity was deleted
    opps = await db_manager.get_opportunities(OpportunityFilters(limit=100))
    assert len(opps) == 0
    
    # Verify transaction was archived
    txs = await db_manager.get_transactions(TransactionFilters(limit=100))
    assert len(txs) == 0
    
    # Verify transaction is in archive
    async with db_manager.pool.acquire() as conn:
        archived_rows = await conn.fetch("SELECT * FROM transactions_archive")
        assert len(archived_rows) == 1


@pytest.mark.asyncio
async def test_calculate_next_run_time(retention_service):
    """Test calculation of next run time"""
    # Test when current time is before run hour
    now = datetime(2024, 1, 15, 1, 30, 0, tzinfo=timezone.utc)  # 1:30 AM UTC
    next_run = retention_service._calculate_next_run_time(now)
    expected = datetime(2024, 1, 15, 2, 0, 0, tzinfo=timezone.utc)  # 2:00 AM today
    assert next_run == expected
    
    # Test when current time is after run hour
    now = datetime(2024, 1, 15, 3, 30, 0, tzinfo=timezone.utc)  # 3:30 AM UTC
    next_run = retention_service._calculate_next_run_time(now)
    expected = datetime(2024, 1, 16, 2, 0, 0, tzinfo=timezone.utc)  # 2:00 AM tomorrow
    assert next_run == expected
    
    # Test when current time is exactly at run hour
    now = datetime(2024, 1, 15, 2, 0, 0, tzinfo=timezone.utc)  # 2:00 AM UTC
    next_run = retention_service._calculate_next_run_time(now)
    expected = datetime(2024, 1, 16, 2, 0, 0, tzinfo=timezone.utc)  # 2:00 AM tomorrow
    assert next_run == expected


@pytest.mark.asyncio
async def test_service_start_stop(retention_service):
    """Test starting and stopping the retention service"""
    assert not retention_service._running
    
    # Start service
    await retention_service.start()
    assert retention_service._running
    assert retention_service._task is not None
    
    # Stop service
    await retention_service.stop()
    assert not retention_service._running
    
    # Starting again should work
    await retention_service.start()
    assert retention_service._running
    await retention_service.stop()


@pytest.mark.asyncio
async def test_no_deletion_when_no_old_data(db_manager, retention_service):
    """Test that retention jobs handle empty results gracefully"""
    now = datetime.now(timezone.utc)
    
    # Create only recent data
    recent_opp = Opportunity(
        chain_id=56,
        pool_name="Recent-Opportunity",
        pool_address="0xrecentopp00000000000000000000000000000",
        imbalance_pct=Decimal("5.0"),
        profit_usd=Decimal("10000.0"),
        profit_native=Decimal("30.0"),
        reserve0=Decimal("1000000.0"),
        reserve1=Decimal("300000000.0"),
        block_number=12345678,
        detected_at=now - timedelta(days=5),
    )
    await db_manager.save_opportunity(recent_opp)
    
    recent_tx = ArbitrageTransaction(
        chain_id=56,
        tx_hash="0xtxrecent1234567890abcdef1234567890abcdef1234567890abcdef1234",
        from_address="0xabcdef1234567890abcdef1234567890abcdef12",
        block_number=12345678,
        block_timestamp=now - timedelta(days=10),
        gas_price_gwei=Decimal("5.0"),
        gas_used=250000,
        gas_cost_native=Decimal("0.00125"),
        gas_cost_usd=Decimal("0.375"),
        swap_count=2,
        strategy="2-hop",
        pools_involved=["0xpool1", "0xpool2"],
        tokens_involved=["WBNB", "BUSD"],
        detected_at=now - timedelta(days=10),
    )
    await db_manager.save_transaction(recent_tx)
    
    # Run retention jobs
    deleted_count = await retention_service.delete_old_opportunities()
    archived_count = await retention_service.archive_old_transactions()
    
    # Nothing should be deleted or archived
    assert deleted_count == 0
    assert archived_count == 0
    
    # Verify data still exists
    opps = await db_manager.get_opportunities(OpportunityFilters(limit=100))
    assert len(opps) == 1
    
    txs = await db_manager.get_transactions(TransactionFilters(limit=100))
    assert len(txs) == 1
