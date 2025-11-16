"""Health check endpoint"""

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
import structlog

from src.database.manager import DatabaseManager

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["health"])


async def get_db_manager(request: Request) -> DatabaseManager:
    """Get database manager from app state"""
    return request.app.state.db_manager


class HealthResponse(BaseModel):
    """Health check response model"""

    status: str = Field(description="Overall health status (healthy or unhealthy)")
    database: str = Field(description="Database connection status")
    database_pool_size: int = Field(description="Current database connection pool size")
    database_pool_free: int = Field(description="Number of free connections in pool")


@router.get("/health", response_model=HealthResponse)
async def health_check(
    response: Response,
    db_manager: DatabaseManager = Depends(get_db_manager),
) -> HealthResponse:
    """
    Health check endpoint to verify system status.
    
    Checks:
    - Database connectivity
    - Connection pool status
    
    Returns:
    - 200 OK if all systems are healthy
    - 503 Service Unavailable if any system is unhealthy
    
    Does not require authentication (public endpoint).
    """
    try:
        # Check database connectivity
        if not db_manager.pool:
            logger.error("health_check_failed", reason="database_pool_not_initialized")
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthResponse(
                status="unhealthy",
                database="disconnected",
                database_pool_size=0,
                database_pool_free=0,
            )

        # Get pool statistics
        pool_size = await db_manager.get_pool_size()
        pool_free = await db_manager.get_pool_free_size()

        # Test database connectivity with a simple query
        async with db_manager.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

        logger.info(
            "health_check_success",
            pool_size=pool_size,
            pool_free=pool_free,
        )

        return HealthResponse(
            status="healthy",
            database="connected",
            database_pool_size=pool_size,
            database_pool_free=pool_free,
        )

    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="unhealthy",
            database="error",
            database_pool_size=0,
            database_pool_free=0,
        )
