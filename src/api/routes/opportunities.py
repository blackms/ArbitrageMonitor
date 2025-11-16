"""Opportunities endpoint"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
import structlog

from src.cache.manager import CacheManager
from src.database.manager import DatabaseManager
from src.database.models import OpportunityFilters

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["opportunities"])


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


class OpportunityResponse(BaseModel):
    """Opportunity response model"""

    id: int
    chain_id: int
    pool_name: str
    pool_address: str
    imbalance_pct: float = Field(description="Pool imbalance percentage")
    profit_usd: float = Field(description="Estimated profit in USD")
    profit_native: float = Field(description="Estimated profit in native token")
    reserve0: float = Field(description="Token0 reserve amount")
    reserve1: float = Field(description="Token1 reserve amount")
    block_number: int
    detected_at: datetime
    captured: bool = Field(description="Whether opportunity was captured")
    captured_by: Optional[str] = Field(None, description="Address that captured opportunity")
    capture_tx_hash: Optional[str] = Field(None, description="Transaction hash of capture")


@router.get("/opportunities", response_model=List[OpportunityResponse])
async def get_opportunities(
    chain_id: Optional[int] = Query(None, description="Filter by chain ID (56=BSC, 137=Polygon)"),
    min_profit: Optional[float] = Query(None, description="Minimum profit in USD"),
    max_profit: Optional[float] = Query(None, description="Maximum profit in USD"),
    captured: Optional[bool] = Query(None, description="Filter by capture status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db_manager: DatabaseManager = Depends(get_db_manager),
    cache_manager: Optional[CacheManager] = Depends(get_cache_manager),
    api_key: str = Depends(verify_api_key),
) -> List[OpportunityResponse]:
    """
    Get detected arbitrage opportunities with filtering and pagination.
    
    Supports filtering by:
    - chain_id: Blockchain (56 for BSC, 137 for Polygon)
    - min_profit: Minimum profit in USD
    - max_profit: Maximum profit in USD
    - captured: Whether opportunity was captured
    
    Results are ordered by detection time (newest first) and support pagination.
    
    Requires authentication via X-API-Key header.
    """
    try:
        # Try to get from cache if simple query (recent opportunities for a chain)
        cached_data = None
        if (
            cache_manager
            and chain_id is not None
            and min_profit is None
            and max_profit is None
            and captured is None
            and offset == 0
            and limit <= 1000
        ):
            cached_data = await cache_manager.get_cached_opportunities(chain_id, limit)

        if cached_data:
            # Use cached data
            response = [
                OpportunityResponse(
                    id=opp["id"],
                    chain_id=opp["chain_id"],
                    pool_name=opp["pool_name"],
                    pool_address=opp["pool_address"],
                    imbalance_pct=float(opp["imbalance_pct"]),
                    profit_usd=float(opp["profit_usd"]),
                    profit_native=float(opp["profit_native"]),
                    reserve0=float(opp["reserve0"]),
                    reserve1=float(opp["reserve1"]),
                    block_number=opp["block_number"],
                    detected_at=datetime.fromisoformat(opp["detected_at"]),
                    captured=opp["captured"],
                    captured_by=opp["captured_by"],
                    capture_tx_hash=opp["capture_tx_hash"],
                )
                for opp in cached_data
            ]
            logger.info(
                "opportunities_cache_hit",
                count=len(response),
                chain_id=chain_id,
            )
            return response

        # Create filters
        filters = OpportunityFilters(
            chain_id=chain_id,
            min_profit=Decimal(str(min_profit)) if min_profit is not None else None,
            max_profit=Decimal(str(max_profit)) if max_profit is not None else None,
            captured=captured,
            limit=limit,
            offset=offset,
        )

        # Query opportunities from database
        opportunities = await db_manager.get_opportunities(filters)

        # Convert to response models
        response = [
            OpportunityResponse(
                id=opp.id,
                chain_id=opp.chain_id,
                pool_name=opp.pool_name,
                pool_address=opp.pool_address,
                imbalance_pct=float(opp.imbalance_pct),
                profit_usd=float(opp.profit_usd),
                profit_native=float(opp.profit_native),
                reserve0=float(opp.reserve0),
                reserve1=float(opp.reserve1),
                block_number=opp.block_number,
                detected_at=opp.detected_at,
                captured=opp.captured,
                captured_by=opp.captured_by,
                capture_tx_hash=opp.capture_tx_hash,
            )
            for opp in opportunities
        ]

        logger.info(
            "opportunities_queried",
            count=len(response),
            chain_id=chain_id,
            captured=captured,
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("opportunities_query_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to query opportunities")
