"""Statistics endpoint"""

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
import structlog

from src.cache.manager import CacheManager
from src.database.manager import DatabaseManager

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["statistics"])


async def get_db_manager(request: Request) -> DatabaseManager:
    """Get database manager from app state"""
    return request.app.state.db_manager


async def get_cache_manager(request: Request) -> Optional[CacheManager]:
    """Get cache manager from app state"""
    return request.app.state.cache_manager


async def verify_api_key(request: Request) -> str:
    """Verify API key from request"""
    api_key_auth = request.app.state.api_key_auth
    api_key = request.headers.get("X-API-Key")
    return await api_key_auth(api_key)


class ProfitDistribution(BaseModel):
    """Profit distribution statistics"""

    min: Optional[float] = Field(None, description="Minimum profit")
    max: Optional[float] = Field(None, description="Maximum profit")
    avg: Optional[float] = Field(None, description="Average profit")
    median: Optional[float] = Field(None, description="Median profit")
    p95: Optional[float] = Field(None, description="95th percentile profit")


class GasStatistics(BaseModel):
    """Gas usage statistics"""

    total_gas_spent_usd: float = Field(description="Total gas spent in USD")
    avg_gas_price_gwei: Optional[float] = Field(None, description="Average gas price in Gwei")


class ChainStatistics(BaseModel):
    """Chain statistics response model"""

    chain_id: int
    hour_timestamp: datetime
    opportunities_detected: int
    opportunities_captured: int
    small_opportunities_count: int = Field(description="Opportunities with profit $10K-$100K")
    small_opps_captured: int = Field(description="Small opportunities captured")
    transactions_detected: int
    unique_arbitrageurs: int
    total_profit_usd: float
    capture_rate: Optional[float] = Field(None, description="Overall capture rate percentage")
    small_opp_capture_rate: Optional[float] = Field(
        None, description="Small opportunity capture rate percentage"
    )
    avg_competition_level: Optional[float] = Field(
        None, description="Average arbitrageurs per opportunity"
    )
    profit_distribution: ProfitDistribution
    gas_statistics: GasStatistics


@router.get("/stats", response_model=List[ChainStatistics])
async def get_statistics(
    chain_id: Optional[int] = Query(None, description="Filter by chain ID (56=BSC, 137=Polygon)"),
    period: str = Query(
        "24h", description="Time period (1h, 24h, 7d, 30d)", regex="^(1h|24h|7d|30d)$"
    ),
    db_manager: DatabaseManager = Depends(get_db_manager),
    cache_manager: Optional[CacheManager] = Depends(get_cache_manager),
    api_key: str = Depends(verify_api_key),
) -> List[ChainStatistics]:
    """
    Get aggregated statistics for chains with time period filtering.
    
    Supports filtering by:
    - chain_id: Blockchain (56 for BSC, 137 for Polygon)
    - period: Time period (1h, 24h, 7d, 30d)
    
    Returns aggregated statistics including:
    - Opportunity detection and capture rates
    - Small opportunity analysis ($10K-$100K)
    - Transaction counts and unique arbitrageurs
    - Profit distribution (min, max, avg, median, p95)
    - Gas statistics
    - Competition level metrics
    
    Requires authentication via X-API-Key header.
    """
    try:
        if not db_manager.pool:
            raise HTTPException(status_code=503, detail="Database not connected")

        # Try to get from cache
        if cache_manager:
            cached_stats = await cache_manager.get_cached_stats(chain_id, period)
            if cached_stats:
                # Convert cached data to response models
                response = [
                    ChainStatistics(
                        chain_id=stat["chain_id"],
                        hour_timestamp=datetime.fromisoformat(stat["hour_timestamp"]),
                        opportunities_detected=stat["opportunities_detected"],
                        opportunities_captured=stat["opportunities_captured"],
                        small_opportunities_count=stat["small_opportunities_count"],
                        small_opps_captured=stat["small_opps_captured"],
                        transactions_detected=stat["transactions_detected"],
                        unique_arbitrageurs=stat["unique_arbitrageurs"],
                        total_profit_usd=stat["total_profit_usd"],
                        capture_rate=stat.get("capture_rate"),
                        small_opp_capture_rate=stat.get("small_opp_capture_rate"),
                        avg_competition_level=stat.get("avg_competition_level"),
                        profit_distribution=ProfitDistribution(**stat["profit_distribution"]),
                        gas_statistics=GasStatistics(**stat["gas_statistics"]),
                    )
                    for stat in cached_stats
                ]
                logger.info(
                    "statistics_cache_hit",
                    count=len(response),
                    chain_id=chain_id,
                    period=period,
                )
                return response

        # Calculate time range based on period
        period_hours = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}
        hours = period_hours.get(period, 24)
        start_time = datetime.utcnow() - timedelta(hours=hours)

        # Build query
        query = """
            SELECT 
                chain_id,
                hour_timestamp,
                opportunities_detected,
                opportunities_captured,
                small_opportunities_count,
                small_opps_captured,
                transactions_detected,
                unique_arbitrageurs,
                total_profit_usd,
                total_gas_spent_usd,
                avg_profit_usd,
                median_profit_usd,
                max_profit_usd,
                min_profit_usd,
                p95_profit_usd,
                capture_rate,
                small_opp_capture_rate,
                avg_competition_level
            FROM chain_stats
            WHERE hour_timestamp >= $1
        """
        params = [start_time]

        if chain_id is not None:
            query += " AND chain_id = $2"
            params.append(chain_id)

        query += " ORDER BY hour_timestamp DESC"

        async with db_manager.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        # Convert to response models
        response = [
            ChainStatistics(
                chain_id=row["chain_id"],
                hour_timestamp=row["hour_timestamp"],
                opportunities_detected=row["opportunities_detected"],
                opportunities_captured=row["opportunities_captured"],
                small_opportunities_count=row["small_opportunities_count"],
                small_opps_captured=row["small_opps_captured"],
                transactions_detected=row["transactions_detected"],
                unique_arbitrageurs=row["unique_arbitrageurs"],
                total_profit_usd=float(row["total_profit_usd"]),
                capture_rate=float(row["capture_rate"]) if row["capture_rate"] else None,
                small_opp_capture_rate=(
                    float(row["small_opp_capture_rate"])
                    if row["small_opp_capture_rate"]
                    else None
                ),
                avg_competition_level=(
                    float(row["avg_competition_level"])
                    if row["avg_competition_level"]
                    else None
                ),
                profit_distribution=ProfitDistribution(
                    min=float(row["min_profit_usd"]) if row["min_profit_usd"] else None,
                    max=float(row["max_profit_usd"]) if row["max_profit_usd"] else None,
                    avg=float(row["avg_profit_usd"]) if row["avg_profit_usd"] else None,
                    median=(
                        float(row["median_profit_usd"]) if row["median_profit_usd"] else None
                    ),
                    p95=float(row["p95_profit_usd"]) if row["p95_profit_usd"] else None,
                ),
                gas_statistics=GasStatistics(
                    total_gas_spent_usd=float(row["total_gas_spent_usd"]),
                    avg_gas_price_gwei=None,  # Not stored in chain_stats, would need to calculate
                ),
            )
            for row in rows
        ]

        logger.info(
            "statistics_queried", count=len(response), chain_id=chain_id, period=period
        )

        # Cache the results
        if cache_manager and response:
            # Convert response to cacheable format
            cache_data = [
                {
                    "chain_id": stat.chain_id,
                    "hour_timestamp": stat.hour_timestamp.isoformat(),
                    "opportunities_detected": stat.opportunities_detected,
                    "opportunities_captured": stat.opportunities_captured,
                    "small_opportunities_count": stat.small_opportunities_count,
                    "small_opps_captured": stat.small_opps_captured,
                    "transactions_detected": stat.transactions_detected,
                    "unique_arbitrageurs": stat.unique_arbitrageurs,
                    "total_profit_usd": stat.total_profit_usd,
                    "capture_rate": stat.capture_rate,
                    "small_opp_capture_rate": stat.small_opp_capture_rate,
                    "avg_competition_level": stat.avg_competition_level,
                    "profit_distribution": {
                        "min": stat.profit_distribution.min,
                        "max": stat.profit_distribution.max,
                        "avg": stat.profit_distribution.avg,
                        "median": stat.profit_distribution.median,
                        "p95": stat.profit_distribution.p95,
                    },
                    "gas_statistics": {
                        "total_gas_spent_usd": stat.gas_statistics.total_gas_spent_usd,
                        "avg_gas_price_gwei": stat.gas_statistics.avg_gas_price_gwei,
                    },
                }
                for stat in response
            ]
            await cache_manager.cache_stats(chain_id, period, cache_data, ttl=60)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("statistics_query_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to query statistics")
