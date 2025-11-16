#!/usr/bin/env python3
"""Example usage of the cache manager"""

import asyncio
from datetime import datetime
from decimal import Decimal

from src.cache.manager import CacheManager
from src.database.models import Opportunity


async def main():
    """Demonstrate cache manager usage"""
    
    # Initialize cache manager
    cache_manager = CacheManager(redis_url="redis://localhost:6379")
    
    try:
        # Connect to Redis
        await cache_manager.connect()
        print("Connected to Redis")
        
        # Example 1: Cache an opportunity
        print("\n--- Example 1: Caching an Opportunity ---")
        opportunity = Opportunity(
            id=123,
            chain_id=56,
            pool_name="WBNB-BUSD",
            pool_address="0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
            imbalance_pct=Decimal("8.5"),
            profit_usd=Decimal("52000.00"),
            profit_native=Decimal("173.33"),
            reserve0=Decimal("1500000"),
            reserve1=Decimal("450000000"),
            block_number=12345678,
            detected_at=datetime.utcnow(),
            captured=False,
        )
        
        # Cache with 5-minute TTL
        await cache_manager.cache_opportunity(opportunity, ttl=300)
        print(f"Cached opportunity #{opportunity.id} for {opportunity.pool_name}")
        
        # Retrieve cached opportunities
        cached_opps = await cache_manager.get_cached_opportunities(chain_id=56, limit=10)
        print(f"Retrieved {len(cached_opps)} cached opportunities")
        
        # Example 2: Cache statistics
        print("\n--- Example 2: Caching Statistics ---")
        stats = [
            {
                "chain_id": 56,
                "hour_timestamp": datetime.utcnow().isoformat(),
                "opportunities_detected": 200,
                "opportunities_captured": 60,
                "small_opportunities_count": 45,
                "small_opps_captured": 12,
                "transactions_detected": 60,
                "unique_arbitrageurs": 15,
                "total_profit_usd": 1500000.0,
                "capture_rate": 30.0,
                "small_opp_capture_rate": 26.7,
                "avg_competition_level": 2.8,
                "profit_distribution": {
                    "min": 5000.0,
                    "max": 300000.0,
                    "avg": 25000.0,
                    "median": 18000.0,
                    "p95": 200000.0,
                },
                "gas_statistics": {
                    "total_gas_spent_usd": 15000.0,
                    "avg_gas_price_gwei": 5.5,
                },
            }
        ]
        
        # Cache with 60-second TTL
        await cache_manager.cache_stats(chain_id=56, period="24h", stats=stats, ttl=60)
        print("Cached statistics for BSC (24h period)")
        
        # Retrieve cached statistics
        cached_stats = await cache_manager.get_cached_stats(chain_id=56, period="24h")
        if cached_stats:
            print(f"Cache hit! Opportunities detected: {cached_stats[0]['opportunities_detected']}")
        
        # Example 3: Cache arbitrageur leaderboard
        print("\n--- Example 3: Caching Leaderboard ---")
        leaderboard = [
            {
                "id": 1,
                "address": "0xAbC1234567890123456789012345678901234567",
                "chain_id": 56,
                "first_seen": datetime.utcnow().isoformat(),
                "last_seen": datetime.utcnow().isoformat(),
                "total_transactions": 200,
                "successful_transactions": 195,
                "failed_transactions": 5,
                "success_rate": 97.5,
                "total_profit_usd": 1200000.0,
                "total_gas_spent_usd": 20000.0,
                "avg_gas_price_gwei": 5.8,
                "preferred_strategy": "3-hop",
                "is_bot": True,
                "contract_address": False,
            },
            {
                "id": 2,
                "address": "0xDeF9876543210987654321098765432109876543",
                "chain_id": 56,
                "first_seen": datetime.utcnow().isoformat(),
                "last_seen": datetime.utcnow().isoformat(),
                "total_transactions": 150,
                "successful_transactions": 142,
                "failed_transactions": 8,
                "success_rate": 94.7,
                "total_profit_usd": 850000.0,
                "total_gas_spent_usd": 18000.0,
                "avg_gas_price_gwei": 6.2,
                "preferred_strategy": "2-hop",
                "is_bot": True,
                "contract_address": False,
            },
        ]
        
        # Cache with 5-minute TTL
        await cache_manager.cache_arbitrageur_leaderboard(
            chain_id=56,
            sort_by="total_profit_usd",
            leaderboard=leaderboard,
            ttl=300
        )
        print("Cached arbitrageur leaderboard for BSC")
        
        # Retrieve cached leaderboard
        cached_leaderboard = await cache_manager.get_cached_arbitrageur_leaderboard(
            chain_id=56,
            sort_by="total_profit_usd"
        )
        if cached_leaderboard:
            print(f"Cache hit! Top arbitrageur: {cached_leaderboard[0]['address']}")
            print(f"Total profit: ${cached_leaderboard[0]['total_profit_usd']:,.2f}")
        
        # Example 4: Cache invalidation
        print("\n--- Example 4: Cache Invalidation ---")
        
        # Invalidate all opportunity caches
        deleted = await cache_manager.invalidate_cache("opportunities:*")
        print(f"Invalidated {deleted} opportunity cache entries")
        
        # Invalidate statistics for a specific chain
        deleted = await cache_manager.invalidate_cache("stats:56:*")
        print(f"Invalidated {deleted} statistics cache entries for BSC")
        
        # Verify invalidation
        cached_opps_after = await cache_manager.get_cached_opportunities(chain_id=56, limit=10)
        print(f"Opportunities after invalidation: {len(cached_opps_after)}")
        
        print("\n✓ All examples completed successfully!")
        
    except ConnectionError as e:
        print(f"Redis connection failed: {e}")
        print("\nTo run Redis locally:")
        print("  docker run -d -p 6379:6379 redis:7-alpine")
        
    finally:
        # Always disconnect
        await cache_manager.disconnect()
        print("\nDisconnected from Redis")


if __name__ == "__main__":
    asyncio.run(main())
