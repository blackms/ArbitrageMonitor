"""Cache manager with Redis connection and TTL support"""

import json
from decimal import Decimal
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
import structlog

from src.database.models import Opportunity

logger = structlog.get_logger()


class CacheManager:
    """
    Manages Redis cache operations with TTL support.
    
    Features:
    - Connection management for Redis
    - Opportunity caching with 5-minute TTL
    - Statistics caching with 60-second TTL
    - Arbitrageur leaderboard caching with 300-second TTL
    - Pattern-based cache invalidation
    """

    def __init__(self, redis_url: str):
        """
        Initialize cache manager.
        
        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379)
        """
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None
        self._logger = logger.bind(component="cache_manager")

    async def connect(self) -> None:
        """Establish connection to Redis"""
        try:
            self.client = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            # Test connection
            await self.client.ping()
            self._logger.info("redis_connected", url=self.redis_url)
        except Exception as e:
            self._logger.error("redis_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Close Redis connection"""
        if self.client:
            await self.client.close()
            self._logger.info("redis_disconnected")

    def _serialize_value(self, value: Any) -> str:
        """
        Serialize value to JSON string, handling Decimal types.
        
        Args:
            value: Value to serialize
            
        Returns:
            JSON string
        """

        def decimal_default(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        return json.dumps(value, default=decimal_default)

    def _deserialize_value(self, value: str) -> Any:
        """
        Deserialize JSON string to Python object.
        
        Args:
            value: JSON string
            
        Returns:
            Deserialized Python object
        """
        return json.loads(value)

    async def cache_opportunity(self, opportunity: Opportunity, ttl: int = 300) -> None:
        """
        Cache opportunity with 5-minute TTL (default).
        
        Args:
            opportunity: Opportunity object to cache
            ttl: Time-to-live in seconds (default: 300 = 5 minutes)
        """
        if not self.client:
            self._logger.warning("cache_opportunity_skipped", reason="redis_not_connected")
            return

        try:
            # Create cache key: opportunities:{chain_id}:{opportunity_id}
            key = f"opportunities:{opportunity.chain_id}:{opportunity.id}"

            # Serialize opportunity to dict
            opp_dict = {
                "id": opportunity.id,
                "chain_id": opportunity.chain_id,
                "pool_name": opportunity.pool_name,
                "pool_address": opportunity.pool_address,
                "imbalance_pct": opportunity.imbalance_pct,
                "profit_usd": opportunity.profit_usd,
                "profit_native": opportunity.profit_native,
                "reserve0": opportunity.reserve0,
                "reserve1": opportunity.reserve1,
                "block_number": opportunity.block_number,
                "detected_at": opportunity.detected_at.isoformat(),
                "captured": opportunity.captured,
                "captured_by": opportunity.captured_by,
                "capture_tx_hash": opportunity.capture_tx_hash,
            }

            # Cache with TTL
            await self.client.setex(key, ttl, self._serialize_value(opp_dict))

            # Add to sorted set for recent opportunities (score = timestamp)
            list_key = f"opportunities:recent:{opportunity.chain_id}"
            await self.client.zadd(
                list_key,
                {key: opportunity.detected_at.timestamp()},
            )

            # Keep only last 1000 opportunities per chain
            await self.client.zremrangebyrank(list_key, 0, -1001)

            self._logger.debug(
                "opportunity_cached",
                opportunity_id=opportunity.id,
                chain_id=opportunity.chain_id,
                ttl=ttl,
            )

        except Exception as e:
            self._logger.error(
                "cache_opportunity_failed",
                opportunity_id=opportunity.id,
                error=str(e),
            )

    async def get_cached_opportunities(
        self, chain_id: int, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get cached recent opportunities for a chain.
        
        Args:
            chain_id: Chain ID to query
            limit: Maximum number of opportunities to return
            
        Returns:
            List of opportunity dictionaries
        """
        if not self.client:
            return []

        try:
            # Get recent opportunity keys from sorted set (newest first)
            list_key = f"opportunities:recent:{chain_id}"
            keys = await self.client.zrevrange(list_key, 0, limit - 1)

            if not keys:
                return []

            # Get all opportunities in one pipeline
            pipeline = self.client.pipeline()
            for key in keys:
                pipeline.get(key)
            values = await pipeline.execute()

            # Deserialize and filter out expired entries
            opportunities = []
            for value in values:
                if value:
                    opportunities.append(self._deserialize_value(value))

            self._logger.debug(
                "opportunities_cache_hit",
                chain_id=chain_id,
                count=len(opportunities),
            )
            return opportunities

        except Exception as e:
            self._logger.error(
                "get_cached_opportunities_failed",
                chain_id=chain_id,
                error=str(e),
            )
            return []

    async def cache_stats(
        self, chain_id: int, period: str, stats: List[Dict[str, Any]], ttl: int = 60
    ) -> None:
        """
        Cache aggregated statistics with 60-second TTL (default).
        
        Args:
            chain_id: Chain ID (or None for all chains)
            period: Time period (1h, 24h, 7d, 30d)
            stats: Statistics data to cache
            ttl: Time-to-live in seconds (default: 60)
        """
        if not self.client:
            self._logger.warning("cache_stats_skipped", reason="redis_not_connected")
            return

        try:
            # Create cache key: stats:{chain_id}:{period}
            chain_key = chain_id if chain_id is not None else "all"
            key = f"stats:{chain_key}:{period}"

            # Cache with TTL
            await self.client.setex(key, ttl, self._serialize_value(stats))

            self._logger.debug(
                "stats_cached",
                chain_id=chain_id,
                period=period,
                ttl=ttl,
            )

        except Exception as e:
            self._logger.error(
                "cache_stats_failed",
                chain_id=chain_id,
                period=period,
                error=str(e),
            )

    async def get_cached_stats(
        self, chain_id: Optional[int], period: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached statistics.
        
        Args:
            chain_id: Chain ID (or None for all chains)
            period: Time period (1h, 24h, 7d, 30d)
            
        Returns:
            Cached statistics or None if not found
        """
        if not self.client:
            return None

        try:
            # Create cache key
            chain_key = chain_id if chain_id is not None else "all"
            key = f"stats:{chain_key}:{period}"

            # Get from cache
            value = await self.client.get(key)
            if value:
                self._logger.debug(
                    "stats_cache_hit",
                    chain_id=chain_id,
                    period=period,
                )
                return self._deserialize_value(value)

            self._logger.debug(
                "stats_cache_miss",
                chain_id=chain_id,
                period=period,
            )
            return None

        except Exception as e:
            self._logger.error(
                "get_cached_stats_failed",
                chain_id=chain_id,
                period=period,
                error=str(e),
            )
            return None

    async def cache_arbitrageur_leaderboard(
        self, chain_id: int, sort_by: str, leaderboard: List[Dict[str, Any]], ttl: int = 300
    ) -> None:
        """
        Cache arbitrageur leaderboard with 300-second TTL (default).
        
        Args:
            chain_id: Chain ID (or None for all chains)
            sort_by: Sort field (e.g., total_profit_usd)
            leaderboard: Leaderboard data to cache
            ttl: Time-to-live in seconds (default: 300 = 5 minutes)
        """
        if not self.client:
            self._logger.warning(
                "cache_leaderboard_skipped", reason="redis_not_connected"
            )
            return

        try:
            # Create cache key: leaderboard:{chain_id}:{sort_by}
            chain_key = chain_id if chain_id is not None else "all"
            key = f"leaderboard:{chain_key}:{sort_by}"

            # Cache with TTL
            await self.client.setex(key, ttl, self._serialize_value(leaderboard))

            self._logger.debug(
                "leaderboard_cached",
                chain_id=chain_id,
                sort_by=sort_by,
                ttl=ttl,
            )

        except Exception as e:
            self._logger.error(
                "cache_leaderboard_failed",
                chain_id=chain_id,
                sort_by=sort_by,
                error=str(e),
            )

    async def get_cached_arbitrageur_leaderboard(
        self, chain_id: Optional[int], sort_by: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached arbitrageur leaderboard.
        
        Args:
            chain_id: Chain ID (or None for all chains)
            sort_by: Sort field (e.g., total_profit_usd)
            
        Returns:
            Cached leaderboard or None if not found
        """
        if not self.client:
            return None

        try:
            # Create cache key
            chain_key = chain_id if chain_id is not None else "all"
            key = f"leaderboard:{chain_key}:{sort_by}"

            # Get from cache
            value = await self.client.get(key)
            if value:
                self._logger.debug(
                    "leaderboard_cache_hit",
                    chain_id=chain_id,
                    sort_by=sort_by,
                )
                return self._deserialize_value(value)

            self._logger.debug(
                "leaderboard_cache_miss",
                chain_id=chain_id,
                sort_by=sort_by,
            )
            return None

        except Exception as e:
            self._logger.error(
                "get_cached_leaderboard_failed",
                chain_id=chain_id,
                sort_by=sort_by,
                error=str(e),
            )
            return None

    async def invalidate_cache(self, pattern: str) -> int:
        """
        Invalidate cache entries matching pattern.
        
        Args:
            pattern: Redis key pattern (e.g., "opportunities:*", "stats:56:*")
            
        Returns:
            Number of keys deleted
        """
        if not self.client:
            self._logger.warning("invalidate_cache_skipped", reason="redis_not_connected")
            return 0

        try:
            # Find all keys matching pattern
            keys = []
            async for key in self.client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                # Delete all matching keys
                deleted = await self.client.delete(*keys)
                self._logger.info(
                    "cache_invalidated",
                    pattern=pattern,
                    deleted_count=deleted,
                )
                return deleted

            return 0

        except Exception as e:
            self._logger.error(
                "invalidate_cache_failed",
                pattern=pattern,
                error=str(e),
            )
            return 0
