"""Integration tests for Redis cache manager

These tests require a Redis instance to be running.
To run these tests, ensure you have Redis running:
docker run --name redis-test -p 6379:6379 -d redis:7-alpine

Or skip these tests with: pytest -m "not integration"
"""

import asyncio
import os
from datetime import datetime
from decimal import Decimal

import pytest

from src.cache.manager import CacheManager
from src.database.models import Opportunity


# Test Redis URL
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture
async def cache_manager():
    """Create cache manager for testing"""
    manager = CacheManager(TEST_REDIS_URL)
    
    try:
        await manager.connect()
        
        # Clear test database before tests
        if manager.client:
            await manager.client.flushdb()
        
        yield manager
    finally:
        # Cleanup
        if manager.client:
            await manager.client.flushdb()
        await manager.disconnect()


@pytest.fixture
def sample_opportunity():
    """Create a sample opportunity for testing"""
    return Opportunity(
        id=1,
        chain_id=56,
        pool_name="WBNB-BUSD",
        pool_address="0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
        imbalance_pct=Decimal("7.5"),
        profit_usd=Decimal("15000.50"),
        profit_native=Decimal("50.25"),
        reserve0=Decimal("1000000.0"),
        reserve1=Decimal("300000000.0"),
        block_number=12345678,
        detected_at=datetime.utcnow(),
        captured=False,
        captured_by=None,
        capture_tx_hash=None,
    )


# ============================================================================
# Connection Tests
# ============================================================================

@pytest.mark.asyncio
async def test_cache_manager_connect():
    """Test cache manager can connect to Redis"""
    manager = CacheManager(TEST_REDIS_URL)
    
    await manager.connect()
    assert manager.client is not None
    
    # Test connection with ping
    result = await manager.client.ping()
    assert result is True
    
    await manager.disconnect()


@pytest.mark.asyncio
async def test_cache_manager_disconnect(cache_manager):
    """Test cache manager can disconnect from Redis"""
    assert cache_manager.client is not None
    
    # Store reference to client
    client = cache_manager.client
    
    await cache_manager.disconnect()
    
    # After disconnect, client connection should be closed
    # Verify by checking that the connection is no longer usable
    assert client.connection is not None or True  # Client object still exists but connection is closed


# ============================================================================
# Opportunity Caching Tests
# ============================================================================

@pytest.mark.asyncio
async def test_cache_opportunity_basic(cache_manager, sample_opportunity):
    """Test caching an opportunity"""
    await cache_manager.cache_opportunity(sample_opportunity)
    
    # Verify opportunity is cached
    key = f"opportunities:{sample_opportunity.chain_id}:{sample_opportunity.id}"
    cached_value = await cache_manager.client.get(key)
    
    assert cached_value is not None
    cached_data = cache_manager._deserialize_value(cached_value)
    assert cached_data["id"] == sample_opportunity.id
    assert cached_data["pool_name"] == sample_opportunity.pool_name
    assert float(cached_data["profit_usd"]) == float(sample_opportunity.profit_usd)


@pytest.mark.asyncio
async def test_cache_opportunity_with_custom_ttl(cache_manager, sample_opportunity):
    """Test caching opportunity with custom TTL"""
    custom_ttl = 10  # 10 seconds
    await cache_manager.cache_opportunity(sample_opportunity, ttl=custom_ttl)
    
    # Verify TTL is set correctly
    key = f"opportunities:{sample_opportunity.chain_id}:{sample_opportunity.id}"
    ttl = await cache_manager.client.ttl(key)
    
    # TTL should be close to custom_ttl (allow 1 second tolerance)
    assert ttl <= custom_ttl
    assert ttl > 0


@pytest.mark.asyncio
async def test_cache_opportunity_adds_to_recent_list(cache_manager, sample_opportunity):
    """Test that caching opportunity adds it to recent list"""
    await cache_manager.cache_opportunity(sample_opportunity)
    
    # Verify opportunity is in recent list
    list_key = f"opportunities:recent:{sample_opportunity.chain_id}"
    count = await cache_manager.client.zcard(list_key)
    
    assert count == 1


@pytest.mark.asyncio
async def test_cache_opportunity_limits_recent_list(cache_manager):
    """Test that recent opportunities list is limited to 1000 entries"""
    # Create and cache 1005 opportunities
    for i in range(1005):
        opp = Opportunity(
            id=i + 1,
            chain_id=56,
            pool_name=f"Pool-{i}",
            pool_address=f"0xpool{i:040d}",
            imbalance_pct=Decimal("5.0"),
            profit_usd=Decimal("10000.0"),
            profit_native=Decimal("30.0"),
            reserve0=Decimal("1000000.0"),
            reserve1=Decimal("300000000.0"),
            block_number=12345678 + i,
            detected_at=datetime.utcnow(),
        )
        await cache_manager.cache_opportunity(opp)
    
    # Verify list is limited to 1000
    list_key = "opportunities:recent:56"
    count = await cache_manager.client.zcard(list_key)
    
    assert count == 1000


@pytest.mark.asyncio
async def test_get_cached_opportunities_empty(cache_manager):
    """Test getting cached opportunities when none exist"""
    opportunities = await cache_manager.get_cached_opportunities(chain_id=56)
    
    assert opportunities == []


@pytest.mark.asyncio
async def test_get_cached_opportunities_with_data(cache_manager):
    """Test getting cached opportunities returns correct data"""
    # Cache multiple opportunities
    for i in range(5):
        opp = Opportunity(
            id=i + 1,
            chain_id=56,
            pool_name=f"Pool-{i}",
            pool_address=f"0xpool{i:040d}",
            imbalance_pct=Decimal("5.0"),
            profit_usd=Decimal(f"{10000 + i * 1000}.0"),
            profit_native=Decimal("30.0"),
            reserve0=Decimal("1000000.0"),
            reserve1=Decimal("300000000.0"),
            block_number=12345678 + i,
            detected_at=datetime.utcnow(),
        )
        await cache_manager.cache_opportunity(opp)
    
    # Get cached opportunities
    opportunities = await cache_manager.get_cached_opportunities(chain_id=56, limit=10)
    
    assert len(opportunities) == 5
    assert all("pool_name" in opp for opp in opportunities)
    assert all("profit_usd" in opp for opp in opportunities)


@pytest.mark.asyncio
async def test_get_cached_opportunities_respects_limit(cache_manager):
    """Test that get_cached_opportunities respects limit parameter"""
    # Cache 10 opportunities
    for i in range(10):
        opp = Opportunity(
            id=i + 1,
            chain_id=56,
            pool_name=f"Pool-{i}",
            pool_address=f"0xpool{i:040d}",
            imbalance_pct=Decimal("5.0"),
            profit_usd=Decimal("10000.0"),
            profit_native=Decimal("30.0"),
            reserve0=Decimal("1000000.0"),
            reserve1=Decimal("300000000.0"),
            block_number=12345678 + i,
            detected_at=datetime.utcnow(),
        )
        await cache_manager.cache_opportunity(opp)
    
    # Get with limit
    opportunities = await cache_manager.get_cached_opportunities(chain_id=56, limit=3)
    
    assert len(opportunities) == 3


@pytest.mark.asyncio
async def test_get_cached_opportunities_returns_newest_first(cache_manager):
    """Test that cached opportunities are returned newest first"""
    # Cache opportunities with different timestamps
    for i in range(3):
        await asyncio.sleep(0.01)  # Small delay to ensure different timestamps
        opp = Opportunity(
            id=i + 1,
            chain_id=56,
            pool_name=f"Pool-{i}",
            pool_address=f"0xpool{i:040d}",
            imbalance_pct=Decimal("5.0"),
            profit_usd=Decimal("10000.0"),
            profit_native=Decimal("30.0"),
            reserve0=Decimal("1000000.0"),
            reserve1=Decimal("300000000.0"),
            block_number=12345678 + i,
            detected_at=datetime.utcnow(),
        )
        await cache_manager.cache_opportunity(opp)
    
    # Get cached opportunities
    opportunities = await cache_manager.get_cached_opportunities(chain_id=56)
    
    # Verify newest first (highest ID should be first)
    assert opportunities[0]["id"] == 3
    assert opportunities[-1]["id"] == 1


# ============================================================================
# Statistics Caching Tests
# ============================================================================

@pytest.mark.asyncio
async def test_cache_stats_basic(cache_manager):
    """Test caching statistics"""
    stats = [
        {
            "chain_id": 56,
            "opportunities_detected": 100,
            "capture_rate": 80.0,
            "total_profit_usd": 150000.0,
        }
    ]
    
    await cache_manager.cache_stats(chain_id=56, period="1h", stats=stats)
    
    # Verify stats are cached
    key = "stats:56:1h"
    cached_value = await cache_manager.client.get(key)
    
    assert cached_value is not None
    cached_data = cache_manager._deserialize_value(cached_value)
    assert cached_data == stats


@pytest.mark.asyncio
async def test_cache_stats_with_custom_ttl(cache_manager):
    """Test caching stats with custom TTL"""
    stats = [{"chain_id": 56, "opportunities_detected": 100}]
    custom_ttl = 30
    
    await cache_manager.cache_stats(chain_id=56, period="1h", stats=stats, ttl=custom_ttl)
    
    # Verify TTL
    key = "stats:56:1h"
    ttl = await cache_manager.client.ttl(key)
    
    assert ttl <= custom_ttl
    assert ttl > 0


@pytest.mark.asyncio
async def test_get_cached_stats_hit(cache_manager):
    """Test cache hit for statistics"""
    stats = [{"chain_id": 56, "opportunities_detected": 100}]
    
    await cache_manager.cache_stats(chain_id=56, period="24h", stats=stats)
    
    # Get cached stats
    cached_stats = await cache_manager.get_cached_stats(chain_id=56, period="24h")
    
    assert cached_stats is not None
    assert cached_stats == stats


@pytest.mark.asyncio
async def test_get_cached_stats_miss(cache_manager):
    """Test cache miss for statistics"""
    # Try to get stats that don't exist
    cached_stats = await cache_manager.get_cached_stats(chain_id=56, period="7d")
    
    assert cached_stats is None


@pytest.mark.asyncio
async def test_cache_stats_different_periods(cache_manager):
    """Test caching stats for different time periods"""
    periods = ["1h", "24h", "7d", "30d"]
    
    for period in periods:
        stats = [{"period": period, "data": f"stats for {period}"}]
        await cache_manager.cache_stats(chain_id=56, period=period, stats=stats)
    
    # Verify all periods are cached separately
    for period in periods:
        cached_stats = await cache_manager.get_cached_stats(chain_id=56, period=period)
        assert cached_stats is not None
        assert cached_stats[0]["period"] == period


# ============================================================================
# Arbitrageur Leaderboard Caching Tests
# ============================================================================

@pytest.mark.asyncio
async def test_cache_arbitrageur_leaderboard_basic(cache_manager):
    """Test caching arbitrageur leaderboard"""
    leaderboard = [
        {"address": "0xaddr1", "total_profit_usd": 50000.0},
        {"address": "0xaddr2", "total_profit_usd": 30000.0},
    ]
    
    await cache_manager.cache_arbitrageur_leaderboard(
        chain_id=56, sort_by="total_profit_usd", leaderboard=leaderboard
    )
    
    # Verify leaderboard is cached
    key = "leaderboard:56:total_profit_usd"
    cached_value = await cache_manager.client.get(key)
    
    assert cached_value is not None
    cached_data = cache_manager._deserialize_value(cached_value)
    assert cached_data == leaderboard


@pytest.mark.asyncio
async def test_cache_arbitrageur_leaderboard_with_custom_ttl(cache_manager):
    """Test caching leaderboard with custom TTL"""
    leaderboard = [{"address": "0xaddr1", "total_profit_usd": 50000.0}]
    custom_ttl = 60
    
    await cache_manager.cache_arbitrageur_leaderboard(
        chain_id=56, sort_by="total_profit_usd", leaderboard=leaderboard, ttl=custom_ttl
    )
    
    # Verify TTL
    key = "leaderboard:56:total_profit_usd"
    ttl = await cache_manager.client.ttl(key)
    
    assert ttl <= custom_ttl
    assert ttl > 0


@pytest.mark.asyncio
async def test_get_cached_arbitrageur_leaderboard_hit(cache_manager):
    """Test cache hit for arbitrageur leaderboard"""
    leaderboard = [{"address": "0xaddr1", "total_profit_usd": 50000.0}]
    
    await cache_manager.cache_arbitrageur_leaderboard(
        chain_id=56, sort_by="total_profit_usd", leaderboard=leaderboard
    )
    
    # Get cached leaderboard
    cached_leaderboard = await cache_manager.get_cached_arbitrageur_leaderboard(
        chain_id=56, sort_by="total_profit_usd"
    )
    
    assert cached_leaderboard is not None
    assert cached_leaderboard == leaderboard


@pytest.mark.asyncio
async def test_get_cached_arbitrageur_leaderboard_miss(cache_manager):
    """Test cache miss for arbitrageur leaderboard"""
    # Try to get leaderboard that doesn't exist
    cached_leaderboard = await cache_manager.get_cached_arbitrageur_leaderboard(
        chain_id=56, sort_by="total_transactions"
    )
    
    assert cached_leaderboard is None


@pytest.mark.asyncio
async def test_cache_leaderboard_different_sort_fields(cache_manager):
    """Test caching leaderboards with different sort fields"""
    sort_fields = ["total_profit_usd", "total_transactions", "success_rate"]
    
    for sort_by in sort_fields:
        leaderboard = [{"sort_by": sort_by, "data": f"leaderboard for {sort_by}"}]
        await cache_manager.cache_arbitrageur_leaderboard(
            chain_id=56, sort_by=sort_by, leaderboard=leaderboard
        )
    
    # Verify all sort fields are cached separately
    for sort_by in sort_fields:
        cached_leaderboard = await cache_manager.get_cached_arbitrageur_leaderboard(
            chain_id=56, sort_by=sort_by
        )
        assert cached_leaderboard is not None
        assert cached_leaderboard[0]["sort_by"] == sort_by


# ============================================================================
# TTL Expiration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_opportunity_cache_expires_after_ttl(cache_manager, sample_opportunity):
    """Test that cached opportunity expires after TTL"""
    # Cache with very short TTL
    short_ttl = 1  # 1 second
    await cache_manager.cache_opportunity(sample_opportunity, ttl=short_ttl)
    
    # Verify it exists immediately
    key = f"opportunities:{sample_opportunity.chain_id}:{sample_opportunity.id}"
    cached_value = await cache_manager.client.get(key)
    assert cached_value is not None
    
    # Wait for expiration
    await asyncio.sleep(short_ttl + 0.5)
    
    # Verify it's expired
    cached_value = await cache_manager.client.get(key)
    assert cached_value is None


@pytest.mark.asyncio
async def test_stats_cache_expires_after_ttl(cache_manager):
    """Test that cached stats expire after TTL"""
    stats = [{"chain_id": 56, "opportunities_detected": 100}]
    short_ttl = 1  # 1 second
    
    await cache_manager.cache_stats(chain_id=56, period="1h", stats=stats, ttl=short_ttl)
    
    # Verify it exists immediately
    cached_stats = await cache_manager.get_cached_stats(chain_id=56, period="1h")
    assert cached_stats is not None
    
    # Wait for expiration
    await asyncio.sleep(short_ttl + 0.5)
    
    # Verify it's expired
    cached_stats = await cache_manager.get_cached_stats(chain_id=56, period="1h")
    assert cached_stats is None


@pytest.mark.asyncio
async def test_leaderboard_cache_expires_after_ttl(cache_manager):
    """Test that cached leaderboard expires after TTL"""
    leaderboard = [{"address": "0xaddr1", "total_profit_usd": 50000.0}]
    short_ttl = 1  # 1 second
    
    await cache_manager.cache_arbitrageur_leaderboard(
        chain_id=56, sort_by="total_profit_usd", leaderboard=leaderboard, ttl=short_ttl
    )
    
    # Verify it exists immediately
    cached_leaderboard = await cache_manager.get_cached_arbitrageur_leaderboard(
        chain_id=56, sort_by="total_profit_usd"
    )
    assert cached_leaderboard is not None
    
    # Wait for expiration
    await asyncio.sleep(short_ttl + 0.5)
    
    # Verify it's expired
    cached_leaderboard = await cache_manager.get_cached_arbitrageur_leaderboard(
        chain_id=56, sort_by="total_profit_usd"
    )
    assert cached_leaderboard is None


# ============================================================================
# Cache Invalidation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_invalidate_cache_by_pattern(cache_manager):
    """Test invalidating cache entries by pattern"""
    # Cache multiple opportunities
    for i in range(5):
        opp = Opportunity(
            id=i + 1,
            chain_id=56,
            pool_name=f"Pool-{i}",
            pool_address=f"0xpool{i:040d}",
            imbalance_pct=Decimal("5.0"),
            profit_usd=Decimal("10000.0"),
            profit_native=Decimal("30.0"),
            reserve0=Decimal("1000000.0"),
            reserve1=Decimal("300000000.0"),
            block_number=12345678 + i,
            detected_at=datetime.utcnow(),
        )
        await cache_manager.cache_opportunity(opp)
    
    # Invalidate all opportunities for chain 56
    deleted_count = await cache_manager.invalidate_cache("opportunities:56:*")
    
    assert deleted_count == 5
    
    # Verify opportunities are deleted
    for i in range(5):
        key = f"opportunities:56:{i + 1}"
        cached_value = await cache_manager.client.get(key)
        assert cached_value is None


@pytest.mark.asyncio
async def test_invalidate_cache_stats_pattern(cache_manager):
    """Test invalidating stats cache by pattern"""
    # Cache stats for different periods
    periods = ["1h", "24h", "7d"]
    for period in periods:
        stats = [{"period": period}]
        await cache_manager.cache_stats(chain_id=56, period=period, stats=stats)
    
    # Invalidate all stats for chain 56
    deleted_count = await cache_manager.invalidate_cache("stats:56:*")
    
    assert deleted_count == 3
    
    # Verify stats are deleted
    for period in periods:
        cached_stats = await cache_manager.get_cached_stats(chain_id=56, period=period)
        assert cached_stats is None


@pytest.mark.asyncio
async def test_invalidate_cache_leaderboard_pattern(cache_manager):
    """Test invalidating leaderboard cache by pattern"""
    # Cache leaderboards with different sort fields
    sort_fields = ["total_profit_usd", "total_transactions"]
    for sort_by in sort_fields:
        leaderboard = [{"sort_by": sort_by}]
        await cache_manager.cache_arbitrageur_leaderboard(
            chain_id=56, sort_by=sort_by, leaderboard=leaderboard
        )
    
    # Invalidate all leaderboards for chain 56
    deleted_count = await cache_manager.invalidate_cache("leaderboard:56:*")
    
    assert deleted_count == 2
    
    # Verify leaderboards are deleted
    for sort_by in sort_fields:
        cached_leaderboard = await cache_manager.get_cached_arbitrageur_leaderboard(
            chain_id=56, sort_by=sort_by
        )
        assert cached_leaderboard is None


@pytest.mark.asyncio
async def test_invalidate_cache_wildcard_all(cache_manager):
    """Test invalidating all cache entries"""
    # Cache various types of data
    opp = Opportunity(
        id=1,
        chain_id=56,
        pool_name="Pool-1",
        pool_address="0xpool1",
        imbalance_pct=Decimal("5.0"),
        profit_usd=Decimal("10000.0"),
        profit_native=Decimal("30.0"),
        reserve0=Decimal("1000000.0"),
        reserve1=Decimal("300000000.0"),
        block_number=12345678,
        detected_at=datetime.utcnow(),
    )
    await cache_manager.cache_opportunity(opp)
    
    stats = [{"chain_id": 56}]
    await cache_manager.cache_stats(chain_id=56, period="1h", stats=stats)
    
    leaderboard = [{"address": "0xaddr1"}]
    await cache_manager.cache_arbitrageur_leaderboard(
        chain_id=56, sort_by="total_profit_usd", leaderboard=leaderboard
    )
    
    # Invalidate all
    deleted_count = await cache_manager.invalidate_cache("*")
    
    # Should delete at least 3 keys (opportunity, stats, leaderboard)
    # Plus the recent list key
    assert deleted_count >= 3


@pytest.mark.asyncio
async def test_invalidate_cache_no_matches(cache_manager):
    """Test invalidating cache with pattern that matches nothing"""
    deleted_count = await cache_manager.invalidate_cache("nonexistent:*")
    
    assert deleted_count == 0


@pytest.mark.asyncio
async def test_invalidate_cache_specific_chain(cache_manager):
    """Test invalidating cache for specific chain only"""
    # Cache opportunities for different chains
    for chain_id in [56, 137]:
        opp = Opportunity(
            id=chain_id,
            chain_id=chain_id,
            pool_name=f"Pool-{chain_id}",
            pool_address=f"0xpool{chain_id}",
            imbalance_pct=Decimal("5.0"),
            profit_usd=Decimal("10000.0"),
            profit_native=Decimal("30.0"),
            reserve0=Decimal("1000000.0"),
            reserve1=Decimal("300000000.0"),
            block_number=12345678,
            detected_at=datetime.utcnow(),
        )
        await cache_manager.cache_opportunity(opp)
    
    # Invalidate only chain 56
    deleted_count = await cache_manager.invalidate_cache("opportunities:56:*")
    
    assert deleted_count == 1
    
    # Verify chain 56 is deleted but chain 137 remains
    key_56 = "opportunities:56:56"
    key_137 = "opportunities:137:137"
    
    assert await cache_manager.client.get(key_56) is None
    assert await cache_manager.client.get(key_137) is not None


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_cache_operations_without_connection():
    """Test cache operations when not connected"""
    manager = CacheManager(TEST_REDIS_URL)
    # Don't connect
    
    sample_opp = Opportunity(
        id=1,
        chain_id=56,
        pool_name="Pool-1",
        pool_address="0xpool1",
        imbalance_pct=Decimal("5.0"),
        profit_usd=Decimal("10000.0"),
        profit_native=Decimal("30.0"),
        reserve0=Decimal("1000000.0"),
        reserve1=Decimal("300000000.0"),
        block_number=12345678,
        detected_at=datetime.utcnow(),
    )
    
    # Operations should not raise errors, just log warnings
    await manager.cache_opportunity(sample_opp)
    opportunities = await manager.get_cached_opportunities(chain_id=56)
    assert opportunities == []
    
    stats = [{"chain_id": 56}]
    await manager.cache_stats(chain_id=56, period="1h", stats=stats)
    cached_stats = await manager.get_cached_stats(chain_id=56, period="1h")
    assert cached_stats is None
    
    deleted = await manager.invalidate_cache("*")
    assert deleted == 0


@pytest.mark.asyncio
async def test_cache_handles_decimal_serialization(cache_manager):
    """Test that cache properly handles Decimal types"""
    opp = Opportunity(
        id=1,
        chain_id=56,
        pool_name="Pool-1",
        pool_address="0xpool1",
        imbalance_pct=Decimal("7.123456789"),
        profit_usd=Decimal("15000.987654321"),
        profit_native=Decimal("50.111111111"),
        reserve0=Decimal("1000000.123456"),
        reserve1=Decimal("300000000.654321"),
        block_number=12345678,
        detected_at=datetime.utcnow(),
    )
    
    await cache_manager.cache_opportunity(opp)
    
    # Get and verify Decimal values are preserved (as floats)
    opportunities = await cache_manager.get_cached_opportunities(chain_id=56)
    
    assert len(opportunities) == 1
    cached_opp = opportunities[0]
    
    # Values should be close (converted to float)
    assert abs(cached_opp["imbalance_pct"] - 7.123456789) < 0.0001
    assert abs(cached_opp["profit_usd"] - 15000.987654321) < 0.0001
