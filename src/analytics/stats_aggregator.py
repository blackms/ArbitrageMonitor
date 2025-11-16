"""Statistics aggregation service for hourly chain statistics"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

import structlog

from src.database.manager import DatabaseManager

logger = structlog.get_logger()


class StatsAggregator:
    """
    Aggregates statistics for chain monitoring data.
    
    Runs hourly aggregation jobs to populate chain_stats table with:
    - Opportunity detection and capture rates
    - Small opportunity analysis ($10K-$100K)
    - Competition level tracking
    - Profit distribution statistics
    """

    def __init__(
        self,
        database_manager: DatabaseManager,
        aggregation_interval_seconds: float = 3600.0,  # 1 hour
        small_opp_min_usd: float = 10000.0,
        small_opp_max_usd: float = 100000.0,
    ):
        """
        Initialize statistics aggregator.
        
        Args:
            database_manager: Database manager for querying and persisting stats
            aggregation_interval_seconds: Seconds between aggregation runs (default 1 hour)
            small_opp_min_usd: Minimum profit for small opportunity classification
            small_opp_max_usd: Maximum profit for small opportunity classification
        """
        self.database_manager = database_manager
        self.aggregation_interval_seconds = aggregation_interval_seconds
        self.small_opp_min_usd = Decimal(str(small_opp_min_usd))
        self.small_opp_max_usd = Decimal(str(small_opp_max_usd))
        
        self._logger = logger.bind(component="stats_aggregator")
        self._running = False
        self._aggregation_task: Optional[asyncio.Task] = None

    async def aggregate_hourly_stats(self, chain_id: int, hour_timestamp: datetime) -> None:
        """
        Aggregate statistics for a specific hour and chain.
        
        Args:
            chain_id: Chain ID to aggregate stats for
            hour_timestamp: Hour timestamp (should be rounded to hour)
        """
        if not self.database_manager.pool:
            raise RuntimeError("Database pool not initialized")
        
        # Round timestamp to hour
        hour_start = hour_timestamp.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)
        
        self._logger.info(
            "aggregating_hourly_stats",
            chain_id=chain_id,
            hour_start=hour_start,
            hour_end=hour_end,
        )
        
        async with self.database_manager.pool.acquire() as conn:
            # Query opportunities for this hour
            opportunities = await conn.fetch(
                """
                SELECT 
                    COUNT(*) as total_opportunities,
                    COUNT(*) FILTER (WHERE captured = true) as captured_opportunities,
                    COUNT(*) FILTER (
                        WHERE profit_usd >= $1 AND profit_usd <= $2
                    ) as small_opportunities,
                    COUNT(*) FILTER (
                        WHERE captured = true 
                        AND profit_usd >= $1 
                        AND profit_usd <= $2
                    ) as small_opps_captured
                FROM opportunities
                WHERE chain_id = $3
                    AND detected_at >= $4
                    AND detected_at < $5
                """,
                self.small_opp_min_usd,
                self.small_opp_max_usd,
                chain_id,
                hour_start,
                hour_end,
            )
            
            opp_stats = opportunities[0]
            total_opportunities = opp_stats["total_opportunities"]
            captured_opportunities = opp_stats["captured_opportunities"]
            small_opportunities = opp_stats["small_opportunities"]
            small_opps_captured = opp_stats["small_opps_captured"]
            
            # Calculate capture rates
            capture_rate = None
            if total_opportunities > 0:
                capture_rate = (Decimal(captured_opportunities) / Decimal(total_opportunities)) * 100
            
            small_opp_capture_rate = None
            if small_opportunities > 0:
                small_opp_capture_rate = (Decimal(small_opps_captured) / Decimal(small_opportunities)) * 100
            
            # Query transactions for this hour
            transactions = await conn.fetch(
                """
                SELECT 
                    COUNT(*) as total_transactions,
                    COUNT(DISTINCT from_address) as unique_arbitrageurs,
                    SUM(profit_net_usd) as total_profit,
                    SUM(gas_cost_usd) as total_gas_spent,
                    AVG(profit_net_usd) as avg_profit,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY profit_net_usd) as median_profit,
                    MAX(profit_net_usd) as max_profit,
                    MIN(profit_net_usd) as min_profit,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY profit_net_usd) as p95_profit
                FROM transactions
                WHERE chain_id = $1
                    AND detected_at >= $2
                    AND detected_at < $3
                    AND profit_net_usd IS NOT NULL
                """,
                chain_id,
                hour_start,
                hour_end,
            )
            
            tx_stats = transactions[0]
            total_transactions = tx_stats["total_transactions"] or 0
            unique_arbitrageurs = tx_stats["unique_arbitrageurs"] or 0
            total_profit = tx_stats["total_profit"] or Decimal("0")
            total_gas_spent = tx_stats["total_gas_spent"] or Decimal("0")
            avg_profit = tx_stats["avg_profit"]
            median_profit = tx_stats["median_profit"]
            max_profit = tx_stats["max_profit"]
            min_profit = tx_stats["min_profit"]
            p95_profit = tx_stats["p95_profit"]
            
            # Query arbitrageurs who captured small opportunities
            small_opp_arbitrageurs = await conn.fetch(
                """
                SELECT DISTINCT captured_by
                FROM opportunities
                WHERE chain_id = $1
                    AND detected_at >= $2
                    AND detected_at < $3
                    AND captured = true
                    AND profit_usd >= $4
                    AND profit_usd <= $5
                    AND captured_by IS NOT NULL
                """,
                chain_id,
                hour_start,
                hour_end,
                self.small_opp_min_usd,
                self.small_opp_max_usd,
            )
            
            unique_small_opp_arbitrageurs = len(small_opp_arbitrageurs)
            
            # Calculate average competition level
            # Competition level = unique arbitrageurs per opportunity
            avg_competition_level = None
            if total_opportunities > 0 and unique_arbitrageurs > 0:
                avg_competition_level = Decimal(unique_arbitrageurs) / Decimal(total_opportunities)
            
            # Log small opportunity arbitrageur tracking
            if unique_small_opp_arbitrageurs > 0:
                self._logger.debug(
                    "small_opportunity_arbitrageurs_tracked",
                    chain_id=chain_id,
                    hour_timestamp=hour_start,
                    unique_small_opp_arbitrageurs=unique_small_opp_arbitrageurs,
                    small_opportunities=small_opportunities,
                    small_opps_captured=small_opps_captured,
                )
            
            # Insert or update chain_stats
            await conn.execute(
                """
                INSERT INTO chain_stats (
                    chain_id, hour_timestamp,
                    opportunities_detected, opportunities_captured,
                    small_opportunities_count, small_opps_captured,
                    transactions_detected, unique_arbitrageurs,
                    total_profit_usd, total_gas_spent_usd,
                    avg_profit_usd, median_profit_usd,
                    max_profit_usd, min_profit_usd, p95_profit_usd,
                    capture_rate, small_opp_capture_rate,
                    avg_competition_level
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18
                )
                ON CONFLICT (chain_id, hour_timestamp) DO UPDATE SET
                    opportunities_detected = EXCLUDED.opportunities_detected,
                    opportunities_captured = EXCLUDED.opportunities_captured,
                    small_opportunities_count = EXCLUDED.small_opportunities_count,
                    small_opps_captured = EXCLUDED.small_opps_captured,
                    transactions_detected = EXCLUDED.transactions_detected,
                    unique_arbitrageurs = EXCLUDED.unique_arbitrageurs,
                    total_profit_usd = EXCLUDED.total_profit_usd,
                    total_gas_spent_usd = EXCLUDED.total_gas_spent_usd,
                    avg_profit_usd = EXCLUDED.avg_profit_usd,
                    median_profit_usd = EXCLUDED.median_profit_usd,
                    max_profit_usd = EXCLUDED.max_profit_usd,
                    min_profit_usd = EXCLUDED.min_profit_usd,
                    p95_profit_usd = EXCLUDED.p95_profit_usd,
                    capture_rate = EXCLUDED.capture_rate,
                    small_opp_capture_rate = EXCLUDED.small_opp_capture_rate,
                    avg_competition_level = EXCLUDED.avg_competition_level
                """,
                chain_id,
                hour_start,
                total_opportunities,
                captured_opportunities,
                small_opportunities,
                small_opps_captured,
                total_transactions,
                unique_arbitrageurs,
                total_profit,
                total_gas_spent,
                avg_profit,
                median_profit,
                max_profit,
                min_profit,
                p95_profit,
                capture_rate,
                small_opp_capture_rate,
                avg_competition_level,
            )
        
        self._logger.info(
            "hourly_stats_aggregated",
            chain_id=chain_id,
            hour_timestamp=hour_start,
            total_opportunities=total_opportunities,
            captured_opportunities=captured_opportunities,
            small_opportunities=small_opportunities,
            capture_rate=float(capture_rate) if capture_rate else None,
            small_opp_capture_rate=float(small_opp_capture_rate) if small_opp_capture_rate else None,
            unique_arbitrageurs=unique_arbitrageurs,
        )

    async def aggregate_all_chains(self, hour_timestamp: Optional[datetime] = None) -> None:
        """
        Aggregate statistics for all chains for a specific hour.
        
        Args:
            hour_timestamp: Hour to aggregate (defaults to previous hour)
        """
        if hour_timestamp is None:
            # Default to previous hour
            now = datetime.utcnow()
            hour_timestamp = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        
        if not self.database_manager.pool:
            raise RuntimeError("Database pool not initialized")
        
        # Get all chain IDs
        async with self.database_manager.pool.acquire() as conn:
            chains = await conn.fetch("SELECT chain_id FROM chains")
        
        # Aggregate stats for each chain
        for chain in chains:
            chain_id = chain["chain_id"]
            try:
                await self.aggregate_hourly_stats(chain_id, hour_timestamp)
            except Exception as e:
                self._logger.error(
                    "failed_to_aggregate_chain_stats",
                    chain_id=chain_id,
                    hour_timestamp=hour_timestamp,
                    error=str(e),
                )

    async def start(self) -> None:
        """Start hourly aggregation loop"""
        if self._running:
            self._logger.warning("stats_aggregator_already_running")
            return
        
        self._running = True
        self._aggregation_task = asyncio.create_task(self._aggregation_loop())
        
        self._logger.info(
            "stats_aggregator_started",
            aggregation_interval_seconds=self.aggregation_interval_seconds,
        )

    async def stop(self) -> None:
        """Stop aggregation loop"""
        if not self._running:
            return
        
        self._running = False
        
        if self._aggregation_task:
            self._aggregation_task.cancel()
            try:
                await self._aggregation_task
            except asyncio.CancelledError:
                pass
        
        self._logger.info("stats_aggregator_stopped")

    async def _aggregation_loop(self) -> None:
        """Internal aggregation loop"""
        while self._running:
            try:
                await self.aggregate_all_chains()
            except Exception as e:
                self._logger.error(
                    "aggregation_loop_error",
                    error=str(e),
                )
            
            # Wait for next aggregation interval
            await asyncio.sleep(self.aggregation_interval_seconds)
