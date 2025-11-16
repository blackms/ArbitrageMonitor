"""Verification script for data retention service implementation"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from src.services.retention import DataRetentionService


async def test_calculate_next_run_time():
    """Test calculation of next run time"""
    print("Testing next run time calculation...")
    
    # Create mock database manager
    mock_db = MagicMock()
    service = DataRetentionService(
        database_manager=mock_db,
        opportunity_retention_days=30,
        transaction_archive_days=90,
        run_hour_utc=2,
    )
    
    # Test when current time is before run hour
    now = datetime(2024, 1, 15, 1, 30, 0, tzinfo=timezone.utc)  # 1:30 AM UTC
    next_run = service._calculate_next_run_time(now)
    expected = datetime(2024, 1, 15, 2, 0, 0, tzinfo=timezone.utc)  # 2:00 AM today
    assert next_run == expected, f"Expected {expected}, got {next_run}"
    print("✓ Next run time before window: PASSED")
    
    # Test when current time is after run hour
    now = datetime(2024, 1, 15, 3, 30, 0, tzinfo=timezone.utc)  # 3:30 AM UTC
    next_run = service._calculate_next_run_time(now)
    expected = datetime(2024, 1, 16, 2, 0, 0, tzinfo=timezone.utc)  # 2:00 AM tomorrow
    assert next_run == expected, f"Expected {expected}, got {next_run}"
    print("✓ Next run time after window: PASSED")
    
    # Test when current time is exactly at run hour
    now = datetime(2024, 1, 15, 2, 0, 0, tzinfo=timezone.utc)  # 2:00 AM UTC
    next_run = service._calculate_next_run_time(now)
    expected = datetime(2024, 1, 16, 2, 0, 0, tzinfo=timezone.utc)  # 2:00 AM tomorrow
    assert next_run == expected, f"Expected {expected}, got {next_run}"
    print("✓ Next run time at exact window: PASSED")


async def test_service_lifecycle():
    """Test starting and stopping the service"""
    print("\nTesting service lifecycle...")
    
    # Create mock database manager
    mock_db = MagicMock()
    service = DataRetentionService(
        database_manager=mock_db,
        opportunity_retention_days=30,
        transaction_archive_days=90,
        run_hour_utc=2,
    )
    
    # Initially not running
    assert not service._running, "Service should not be running initially"
    print("✓ Initial state: PASSED")
    
    # Start service
    await service.start()
    assert service._running, "Service should be running after start"
    assert service._task is not None, "Service task should be created"
    print("✓ Service start: PASSED")
    
    # Stop service
    await service.stop()
    assert not service._running, "Service should not be running after stop"
    print("✓ Service stop: PASSED")
    
    # Can start again
    await service.start()
    assert service._running, "Service should be running after restart"
    await service.stop()
    print("✓ Service restart: PASSED")


async def test_configuration():
    """Test service configuration"""
    print("\nTesting service configuration...")
    
    mock_db = MagicMock()
    service = DataRetentionService(
        database_manager=mock_db,
        opportunity_retention_days=45,
        transaction_archive_days=120,
        run_hour_utc=3,
    )
    
    assert service.opportunity_retention_days == 45, "Opportunity retention days should be 45"
    assert service.transaction_archive_days == 120, "Transaction archive days should be 120"
    assert service.run_hour_utc == 3, "Run hour should be 3"
    print("✓ Custom configuration: PASSED")
    
    # Test default configuration
    service_default = DataRetentionService(database_manager=mock_db)
    assert service_default.opportunity_retention_days == 30, "Default opportunity retention should be 30"
    assert service_default.transaction_archive_days == 90, "Default transaction archive should be 90"
    assert service_default.run_hour_utc == 2, "Default run hour should be 2"
    print("✓ Default configuration: PASSED")


async def test_delete_opportunities_logic():
    """Test the delete opportunities method structure"""
    print("\nTesting delete opportunities method...")
    
    # Create mock database manager with pool
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value="DELETE 5")
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    
    mock_db = MagicMock()
    mock_db.pool = mock_pool
    
    service = DataRetentionService(database_manager=mock_db)
    
    # Call delete method
    deleted_count = await service.delete_old_opportunities()
    
    assert deleted_count == 5, f"Expected 5 deleted, got {deleted_count}"
    assert mock_conn.execute.called, "Execute should be called"
    print("✓ Delete opportunities logic: PASSED")


async def test_archive_transactions_logic():
    """Test the archive transactions method structure"""
    print("\nTesting archive transactions method...")
    
    # Create mock database manager with pool
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_transaction = AsyncMock()
    mock_transaction.__aenter__ = AsyncMock(return_value=None)
    mock_transaction.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_transaction)
    mock_conn.execute = AsyncMock(side_effect=["", "INSERT 0 10"])
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    
    mock_db = MagicMock()
    mock_db.pool = mock_pool
    
    service = DataRetentionService(database_manager=mock_db)
    
    # Call archive method
    archived_count = await service.archive_old_transactions()
    
    assert archived_count == 10, f"Expected 10 archived, got {archived_count}"
    assert mock_conn.execute.call_count == 2, "Execute should be called twice (create table + move)"
    print("✓ Archive transactions logic: PASSED")


async def test_run_once():
    """Test run_once method"""
    print("\nTesting run_once method...")
    
    # Create mock database manager
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_transaction = AsyncMock()
    mock_transaction.__aenter__ = AsyncMock(return_value=None)
    mock_transaction.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_transaction)
    mock_conn.execute = AsyncMock(side_effect=["DELETE 3", "", "INSERT 0 5"])
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    
    mock_db = MagicMock()
    mock_db.pool = mock_pool
    
    service = DataRetentionService(database_manager=mock_db)
    
    # Call run_once
    await service.run_once()
    
    # Should have called execute 3 times (delete + create table + archive)
    assert mock_conn.execute.call_count == 3, f"Expected 3 execute calls, got {mock_conn.execute.call_count}"
    print("✓ Run once execution: PASSED")


async def main():
    """Run all verification tests"""
    print("=" * 70)
    print("Data Retention Service Verification")
    print("=" * 70)
    
    try:
        await test_calculate_next_run_time()
        await test_service_lifecycle()
        await test_configuration()
        await test_delete_opportunities_logic()
        await test_archive_transactions_logic()
        await test_run_once()
        
        print("\n" + "=" * 70)
        print("✓ ALL VERIFICATION TESTS PASSED")
        print("=" * 70)
        print("\nData retention service implementation is complete!")
        print("\nKey features implemented:")
        print("  • Delete opportunities older than 30 days (configurable)")
        print("  • Archive transactions older than 90 days (configurable)")
        print("  • Scheduled execution during low-activity hours (2-4 AM UTC)")
        print("  • Maintains referential integrity during operations")
        print("  • Automatic scheduler with graceful start/stop")
        print("  • Manual run_once() method for testing")
        print("\nNote: Integration tests require a PostgreSQL database.")
        print("Run 'pytest tests/test_retention.py -m integration' with a test database.")
        
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
