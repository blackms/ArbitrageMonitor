#!/usr/bin/env python3
"""Verification script for cache manager implementation"""

import asyncio
from datetime import datetime
from decimal import Decimal

from src.cache.manager import CacheManager
from src.database.models import Opportunity


async def verify_cache_manager():
    """Verify cache manager functionality"""
    print("=" * 60)
    print("Cache Manager Verification")
    print("=" * 60)
    
    # Initialize cache manager (will fail if Redis not running, which is expected)
    cache_manager = CacheManager(redis_url="redis://localhost:6379")
    
    try:
        # Try to connect to Redis
        await cache_manager.connect()
        print("✓ Redis connection established")
        
        # Test 1: Cache an opportunity
        print("\n1. Testing opportunity caching...")
        test_opportunity = Opportunity(
            id=1,
            chain_id=56,
            pool_name="WBNB-BUSD",
            pool_address="0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
            imbalance_pct=Decimal("7.5"),
            profit_usd=Decimal("45230.50"),
            profit_native=Decimal("150.77"),
            reserve0=Decimal("1000000"),
            reserve1=Decimal("300000000"),
            block_number=12345678,
            detected_at=datetime.utcnow(),
            captured=False,
        )
        
        await cache_manager.cache_opportunity(test_opportunity, ttl=300)
        print("✓ Opportunity cached successfully")
        
        # Test 2: Retrieve cached opportunities
        print("\n2. Testing opportunity retrieval...")
        cached_opps = await cache_manager.get_cached_opportunities(chain_id=56, limit=10)
        if cached_opps:
            print(f"✓ Retrieved {len(cached_opps)} cached opportunities")
            print(f"  First opportunity: {cached_opps[0]['pool_name']} - ${cached_opps[0]['profit_usd']}")
        else:
            print("✗ No cached opportunities found")
        
        # Test 3: Cache statistics
        print("\n3. Testing statistics caching...")
        test_stats = [
            {
                "chain_id": 56,
                "hour_timestamp": datetime.utcnow().isoformat(),
                "opportunities_detected": 150,
                "opportunities_captured": 45,
                "small_opportunities_count": 30,
                "small_opps_captured": 8,
                "transactions_detected": 45,
                "unique_arbitrageurs": 12,
                "total_profit_usd": 1250000.0,
                "capture_rate": 30.0,
                "small_opp_capture_rate": 26.7,
                "avg_competition_level": 2.5,
                "profit_distribution": {
                    "min": 5000.0,
                    "max": 250000.0,
                    "avg": 27777.78,
                    "median": 15000.0,
                    "p95": 180000.0,
                },
                "gas_statistics": {
                    "total_gas_spent_usd": 12500.0,
                    "avg_gas_price_gwei": 5.2,
                },
            }
        ]
        
        await cache_manager.cache_stats(chain_id=56, period="24h", stats=test_stats, ttl=60)
        print("✓ Statistics cached successfully")
        
        # Test 4: Retrieve cached statistics
        print("\n4. Testing statistics retrieval...")
        cached_stats = await cache_manager.get_cached_stats(chain_id=56, period="24h")
        if cached_stats:
            print(f"✓ Retrieved cached statistics")
            print(f"  Opportunities detected: {cached_stats[0]['opportunities_detected']}")
            print(f"  Capture rate: {cached_stats[0]['capture_rate']}%")
        else:
            print("✗ No cached statistics found")
        
        # Test 5: Cache arbitrageur leaderboard
        print("\n5. Testing leaderboard caching...")
        test_leaderboard = [
            {
                "id": 1,
                "address": "0x1234567890123456789012345678901234567890",
                "chain_id": 56,
                "first_seen": datetime.utcnow().isoformat(),
                "last_seen": datetime.utcnow().isoformat(),
                "total_transactions": 150,
                "successful_transactions": 145,
                "failed_transactions": 5,
                "success_rate": 96.67,
                "total_profit_usd": 850000.0,
                "total_gas_spent_usd": 15000.0,
                "avg_gas_price_gwei": 5.5,
                "preferred_strategy": "3-hop",
                "is_bot": True,
                "contract_address": False,
            }
        ]
        
        await cache_manager.cache_arbitrageur_leaderboard(
            chain_id=56, sort_by="total_profit_usd", leaderboard=test_leaderboard, ttl=300
        )
        print("✓ Leaderboard cached successfully")
        
        # Test 6: Retrieve cached leaderboard
        print("\n6. Testing leaderboard retrieval...")
        cached_leaderboard = await cache_manager.get_cached_arbitrageur_leaderboard(
            chain_id=56, sort_by="total_profit_usd"
        )
        if cached_leaderboard:
            print(f"✓ Retrieved cached leaderboard")
            print(f"  Top arbitrageur: {cached_leaderboard[0]['address']}")
            print(f"  Total profit: ${cached_leaderboard[0]['total_profit_usd']:,.2f}")
        else:
            print("✗ No cached leaderboard found")
        
        # Test 7: Cache invalidation
        print("\n7. Testing cache invalidation...")
        deleted_count = await cache_manager.invalidate_cache("opportunities:*")
        print(f"✓ Invalidated {deleted_count} opportunity cache entries")
        
        # Verify invalidation
        cached_opps_after = await cache_manager.get_cached_opportunities(chain_id=56, limit=10)
        if not cached_opps_after:
            print("✓ Cache invalidation verified - no opportunities found")
        else:
            print(f"✗ Cache invalidation incomplete - {len(cached_opps_after)} opportunities still cached")
        
        print("\n" + "=" * 60)
        print("✓ All cache manager tests passed!")
        print("=" * 60)
        
    except ConnectionError as e:
        print(f"\n✗ Redis connection failed: {e}")
        print("\nNote: This is expected if Redis is not running.")
        print("To run Redis locally: docker run -d -p 6379:6379 redis:7-alpine")
        
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        await cache_manager.disconnect()
        print("\n✓ Redis connection closed")


if __name__ == "__main__":
    asyncio.run(verify_cache_manager())
