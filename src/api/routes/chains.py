"""Chain status endpoint"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
import structlog

from src.database.manager import DatabaseManager

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["chains"])


class ChainStatusResponse(BaseModel):
    """Chain status response model"""

    id: int
    name: str
    chain_id: int
    status: str
    last_synced_block: int
    blocks_behind: int
    uptime_pct: float = Field(description="Uptime percentage")
    native_token: str
    native_token_usd: float
    block_time_seconds: float


async def get_db_manager(request: Request) -> DatabaseManager:
    """Get database manager from app state"""
    return request.app.state.db_manager


async def verify_api_key(request: Request) -> str:
    """Verify API key from request"""
    api_key_auth = request.app.state.api_key_auth
    api_key = request.headers.get("X-API-Key")
    return await api_key_auth(api_key)


@router.get("/chains", response_model=List[ChainStatusResponse])
async def get_chains(
    db_manager: DatabaseManager = Depends(get_db_manager),
    api_key: str = Depends(verify_api_key),
) -> List[ChainStatusResponse]:
    """
    Get status of all monitored chains.
    
    Returns list of chains with:
    - Current status (active, inactive, error)
    - Last synced block number
    - Blocks behind latest
    - Uptime percentage
    - Chain configuration
    
    Requires authentication via X-API-Key header.
    """
    try:
        if not db_manager.pool:
            raise HTTPException(status_code=503, detail="Database not connected")

        async with db_manager.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, chain_id, status, last_synced_block,
                       blocks_behind, uptime_pct, native_token, native_token_usd,
                       block_time_seconds
                FROM chains
                ORDER BY chain_id
                """
            )

        chains = [
            ChainStatusResponse(
                id=row["id"],
                name=row["name"],
                chain_id=row["chain_id"],
                status=row["status"],
                last_synced_block=row["last_synced_block"],
                blocks_behind=row["blocks_behind"],
                uptime_pct=float(row["uptime_pct"]),
                native_token=row["native_token"],
                native_token_usd=float(row["native_token_usd"]),
                block_time_seconds=float(row["block_time_seconds"]),
            )
            for row in rows
        ]

        logger.info("chains_queried", count=len(chains))
        return chains

    except HTTPException:
        raise
    except Exception as e:
        logger.error("chains_query_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to query chains")
