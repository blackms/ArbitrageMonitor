"""Arbitrageurs endpoint"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
import structlog

from src.cache.manager import CacheManager
from src.database.manager import DatabaseManager
from src.database.models import ArbitrageurFilters

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["arbitrageurs"])


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


class ArbitrageurResponse(BaseModel):
    """Arbitrageur response model"""

    id: int
    address: str = Field(description="Arbitrageur wallet address")
    chain_id: int
    first_seen: datetime
    last_seen: datetime
    total_transactions: int
    successful_transactions: int
    failed_transactions: int
    success_rate: float = Field(description="Success rate percentage")
    total_profit_usd: float = Field(description="Total profit in USD")
    total_gas_spent_usd: float = Field(description="Total gas spent in USD")
    avg_gas_price_gwei: Optional[float] = Field(None, description="Average gas price in Gwei")
    preferred_strategy: Optional[str] = Field(None, description="Most used strategy")
    is_bot: bool = Field(description="Whether address appears to be a bot")
    contract_address: bool = Field(description="Whether address is a smart contract")


@router.get("/arbitrageurs", response_model=List[ArbitrageurResponse])
async def get_arbitrageurs(
    chain_id: Optional[int] = Query(None, description="Filter by chain ID (56=BSC, 137=Polygon)"),
    min_transactions: Optional[int] = Query(
        None, ge=1, description="Minimum number of transactions"
    ),
    sort_by: str = Query(
        "total_profit_usd",
        description="Sort field (total_profit_usd, total_transactions, last_seen, total_gas_spent_usd)",
    ),
    sort_order: str = Query("DESC", description="Sort order (ASC or DESC)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db_manager: DatabaseManager = Depends(get_db_manager),
    cache_manager: Optional[CacheManager] = Depends(get_cache_manager),
    api_key: str = Depends(verify_api_key),
) -> List[ArbitrageurResponse]:
    """
    Get arbitrageur profiles with filtering, sorting, and pagination.
    
    Supports filtering by:
    - chain_id: Blockchain (56 for BSC, 137 for Polygon)
    - min_transactions: Minimum number of transactions executed
    
    Supports sorting by:
    - total_profit_usd: Total profit earned (default)
    - total_transactions: Number of transactions
    - last_seen: Most recent activity
    - total_gas_spent_usd: Total gas costs
    
    Results support pagination and include success rate calculation.
    
    Requires authentication via X-API-Key header.
    """
    try:
        # Validate sort_by field
        allowed_sort_fields = [
            "total_profit_usd",
            "total_transactions",
            "last_seen",
            "total_gas_spent_usd",
        ]
        if sort_by not in allowed_sort_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sort_by field. Allowed: {', '.join(allowed_sort_fields)}",
            )

        # Validate sort_order
        if sort_order.upper() not in ["ASC", "DESC"]:
            raise HTTPException(
                status_code=400, detail="Invalid sort_order. Must be ASC or DESC"
            )

        # Try to get from cache if it's a leaderboard query (no filters, offset=0)
        cached_data = None
        if (
            cache_manager
            and min_transactions is None
            and offset == 0
            and limit <= 100
            and sort_order.upper() == "DESC"
        ):
            cached_data = await cache_manager.get_cached_arbitrageur_leaderboard(
                chain_id, sort_by
            )

        if cached_data:
            # Use cached data
            response = [
                ArbitrageurResponse(
                    id=arb["id"],
                    address=arb["address"],
                    chain_id=arb["chain_id"],
                    first_seen=datetime.fromisoformat(arb["first_seen"]),
                    last_seen=datetime.fromisoformat(arb["last_seen"]),
                    total_transactions=arb["total_transactions"],
                    successful_transactions=arb["successful_transactions"],
                    failed_transactions=arb["failed_transactions"],
                    success_rate=arb["success_rate"],
                    total_profit_usd=arb["total_profit_usd"],
                    total_gas_spent_usd=arb["total_gas_spent_usd"],
                    avg_gas_price_gwei=arb["avg_gas_price_gwei"],
                    preferred_strategy=arb["preferred_strategy"],
                    is_bot=arb["is_bot"],
                    contract_address=arb["contract_address"],
                )
                for arb in cached_data
            ]
            logger.info(
                "arbitrageurs_cache_hit",
                count=len(response),
                chain_id=chain_id,
                sort_by=sort_by,
            )
            return response

        # Create filters
        filters = ArbitrageurFilters(
            chain_id=chain_id,
            min_transactions=min_transactions,
            sort_by=sort_by,
            sort_order=sort_order.upper(),
            limit=limit,
            offset=offset,
        )

        # Query arbitrageurs from database
        arbitrageurs = await db_manager.get_arbitrageurs(filters)

        # Convert to response models
        response = [
            ArbitrageurResponse(
                id=arb.id,
                address=arb.address,
                chain_id=arb.chain_id,
                first_seen=arb.first_seen,
                last_seen=arb.last_seen,
                total_transactions=arb.total_transactions,
                successful_transactions=arb.successful_transactions,
                failed_transactions=arb.failed_transactions,
                success_rate=(
                    (arb.successful_transactions / arb.total_transactions * 100)
                    if arb.total_transactions > 0
                    else 0.0
                ),
                total_profit_usd=float(arb.total_profit_usd),
                total_gas_spent_usd=float(arb.total_gas_spent_usd),
                avg_gas_price_gwei=(
                    float(arb.avg_gas_price_gwei) if arb.avg_gas_price_gwei else None
                ),
                preferred_strategy=arb.preferred_strategy,
                is_bot=arb.is_bot,
                contract_address=arb.contract_address,
            )
            for arb in arbitrageurs
        ]

        logger.info(
            "arbitrageurs_queried",
            count=len(response),
            chain_id=chain_id,
            sort_by=sort_by,
        )

        # Cache leaderboard results (no filters, offset=0, DESC order)
        if (
            cache_manager
            and min_transactions is None
            and offset == 0
            and limit <= 100
            and sort_order.upper() == "DESC"
            and response
        ):
            # Convert response to cacheable format
            cache_data = [
                {
                    "id": arb.id,
                    "address": arb.address,
                    "chain_id": arb.chain_id,
                    "first_seen": arb.first_seen.isoformat(),
                    "last_seen": arb.last_seen.isoformat(),
                    "total_transactions": arb.total_transactions,
                    "successful_transactions": arb.successful_transactions,
                    "failed_transactions": arb.failed_transactions,
                    "success_rate": arb.success_rate,
                    "total_profit_usd": arb.total_profit_usd,
                    "total_gas_spent_usd": arb.total_gas_spent_usd,
                    "avg_gas_price_gwei": arb.avg_gas_price_gwei,
                    "preferred_strategy": arb.preferred_strategy,
                    "is_bot": arb.is_bot,
                    "contract_address": arb.contract_address,
                }
                for arb in response
            ]
            await cache_manager.cache_arbitrageur_leaderboard(
                chain_id, sort_by, cache_data, ttl=300
            )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("arbitrageurs_query_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to query arbitrageurs")
