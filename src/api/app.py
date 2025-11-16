"""FastAPI application with authentication and CORS middleware"""

import time
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
import structlog

from src.cache.manager import CacheManager
from src.config.models import Settings
from src.database.manager import DatabaseManager
from src.monitoring import metrics

logger = structlog.get_logger()

# API key header security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class APIKeyAuth:
    """API key authentication dependency"""

    def __init__(self, api_keys: List[str]):
        self.api_keys = set(api_keys)
        self._logger = logger.bind(component="api_key_auth")

    async def __call__(self, api_key: str = Security(api_key_header)) -> str:
        """
        Validate API key from X-API-Key header.
        
        Args:
            api_key: API key from request header
            
        Returns:
            Validated API key
            
        Raises:
            HTTPException: If API key is missing or invalid
        """
        if api_key is None:
            self._logger.warning("api_auth_failed", reason="missing_api_key")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key. Provide X-API-Key header.",
            )

        if api_key not in self.api_keys:
            self._logger.warning("api_auth_failed", reason="invalid_api_key")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        return api_key


def create_app(
    settings: Settings, db_manager: DatabaseManager, cache_manager: Optional[CacheManager] = None
) -> FastAPI:
    """
    Create and configure FastAPI application.
    
    Args:
        settings: Application settings
        db_manager: Database manager instance
        cache_manager: Optional cache manager instance
        
    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Multi-Chain Arbitrage Monitor API",
        description="REST API for querying arbitrage opportunities and transactions across BSC and Polygon",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:8080",
            "https://arbitrage-monitor.example.com",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    
    # Add metrics middleware
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        """Middleware to track API request metrics"""
        # Skip metrics for the metrics endpoint itself
        if request.url.path == "/metrics":
            return await call_next(request)
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Record request metrics
            latency = time.time() - start_time
            metrics.api_request_latency.labels(
                endpoint=request.url.path,
                method=request.method
            ).observe(latency)
            
            metrics.api_requests_total.labels(
                endpoint=request.url.path,
                method=request.method,
                status=response.status_code
            ).inc()
            
            return response
        except Exception as e:
            # Record error
            error_type = type(e).__name__
            metrics.api_errors.labels(
                endpoint=request.url.path,
                error_type=error_type
            ).inc()
            raise

    # Create API key authentication dependency
    api_key_auth = APIKeyAuth(settings.get_api_keys_list())

    # Store dependencies in app state
    app.state.db_manager = db_manager
    app.state.settings = settings
    app.state.api_key_auth = api_key_auth
    app.state.cache_manager = cache_manager

    # Register routes
    from src.api.routes import arbitrageurs, chains, health, opportunities, stats, transactions

    app.include_router(chains.router)
    app.include_router(opportunities.router)
    app.include_router(transactions.router)
    app.include_router(arbitrageurs.router)
    app.include_router(stats.router)
    app.include_router(health.router)
    
    # Add metrics endpoint
    from fastapi import Response
    from src.monitoring.metrics import get_metrics, get_content_type
    
    @app.get("/metrics")
    async def metrics_endpoint():
        """Prometheus metrics endpoint"""
        return Response(content=get_metrics(), media_type=get_content_type())

    # Register WebSocket endpoint
    from src.api.websocket import websocket_endpoint, ws_manager

    @app.websocket("/ws/v1/stream")
    async def websocket_route(websocket):
        await websocket_endpoint(websocket)

    # Store WebSocket manager in app state
    app.state.ws_manager = ws_manager

    # Log application startup
    logger.info(
        "fastapi_app_created",
        title=app.title,
        version=app.version,
        docs_url=app.docs_url,
    )

    return app


def get_db_manager(app: FastAPI = Depends()) -> DatabaseManager:
    """Dependency to get database manager from app state"""
    return app.state.db_manager


def get_api_key_auth(app: FastAPI = Depends()) -> APIKeyAuth:
    """Dependency to get API key auth from app state"""
    return app.state.api_key_auth


def get_cache_manager(app: FastAPI = Depends()) -> Optional[CacheManager]:
    """Dependency to get cache manager from app state"""
    return app.state.cache_manager
