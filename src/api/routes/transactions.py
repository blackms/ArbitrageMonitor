"""Transactions endpoint"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
import structlog

from src.database.manager import DatabaseManager
from src.database.models import TransactionFilters

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["transactions"])


async def get_db_manager(request: Request) -> DatabaseManager:
    """Get database manager from app state"""
    return request.app.state.db_manager


async def verify_api_key(request: Request) -> str:
    """Verify API key from request"""
    api_key_auth = request.app.state.api_key_auth
    api_key = request.headers.get("X-API-Key")
    return await api_key_auth(api_key)


class TransactionResponse(BaseModel):
    """Transaction response model"""

    id: int
    chain_id: int
    tx_hash: str
    from_address: str = Field(description="Arbitrageur address")
    block_number: int
    block_timestamp: datetime
    gas_price_gwei: float = Field(description="Gas price in Gwei")
    gas_used: int
    gas_cost_native: float = Field(description="Gas cost in native token")
    gas_cost_usd: float = Field(description="Gas cost in USD")
    swap_count: int = Field(description="Number of swaps in transaction")
    strategy: str = Field(description="Arbitrage strategy (2-hop, 3-hop, etc.)")
    profit_gross_usd: Optional[float] = Field(None, description="Gross profit in USD")
    profit_net_usd: Optional[float] = Field(None, description="Net profit in USD (after gas)")
    pools_involved: List[str] = Field(description="Pool addresses involved")
    tokens_involved: List[str] = Field(description="Token addresses involved")
    detected_at: datetime


@router.get("/transactions", response_model=List[TransactionResponse])
async def get_transactions(
    chain_id: Optional[int] = Query(None, description="Filter by chain ID (56=BSC, 137=Polygon)"),
    from_address: Optional[str] = Query(None, description="Filter by arbitrageur address"),
    min_profit: Optional[float] = Query(None, description="Minimum net profit in USD"),
    min_swaps: Optional[int] = Query(None, ge=2, description="Minimum number of swaps"),
    strategy: Optional[str] = Query(
        None, description="Filter by strategy (2-hop, 3-hop, 4-hop, etc.)"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db_manager: DatabaseManager = Depends(get_db_manager),
    api_key: str = Depends(verify_api_key),
) -> List[TransactionResponse]:
    """
    Get arbitrage transactions with filtering and pagination.
    
    Supports filtering by:
    - chain_id: Blockchain (56 for BSC, 137 for Polygon)
    - from_address: Arbitrageur wallet address
    - min_profit: Minimum net profit in USD
    - min_swaps: Minimum number of swaps (2+)
    - strategy: Arbitrage strategy type
    
    Results are ordered by detection time (newest first) and support pagination.
    
    Requires authentication via X-API-Key header.
    """
    try:
        # Create filters
        filters = TransactionFilters(
            chain_id=chain_id,
            from_address=from_address,
            min_profit=Decimal(str(min_profit)) if min_profit is not None else None,
            min_swaps=min_swaps,
            strategy=strategy,
            limit=limit,
            offset=offset,
        )

        # Query transactions
        transactions = await db_manager.get_transactions(filters)

        # Convert to response models
        response = [
            TransactionResponse(
                id=tx.id,
                chain_id=tx.chain_id,
                tx_hash=tx.tx_hash,
                from_address=tx.from_address,
                block_number=tx.block_number,
                block_timestamp=tx.block_timestamp,
                gas_price_gwei=float(tx.gas_price_gwei),
                gas_used=tx.gas_used,
                gas_cost_native=float(tx.gas_cost_native),
                gas_cost_usd=float(tx.gas_cost_usd),
                swap_count=tx.swap_count,
                strategy=tx.strategy,
                profit_gross_usd=float(tx.profit_gross_usd) if tx.profit_gross_usd else None,
                profit_net_usd=float(tx.profit_net_usd) if tx.profit_net_usd else None,
                pools_involved=tx.pools_involved,
                tokens_involved=tx.tokens_involved,
                detected_at=tx.detected_at,
            )
            for tx in transactions
        ]

        logger.info(
            "transactions_queried",
            count=len(response),
            chain_id=chain_id,
            from_address=from_address,
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("transactions_query_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to query transactions")
