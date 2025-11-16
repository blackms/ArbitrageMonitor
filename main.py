"""Main application entry point for Multi-Chain Arbitrage Monitor"""

import asyncio
import signal
import sys
from typing import Optional

import structlog
import uvicorn
from dotenv import load_dotenv

from src.analytics.stats_aggregator import StatsAggregator
from src.api.app import create_app
from src.api.websocket import ws_manager
from src.cache.manager import CacheManager
from src.chains.bsc_connector import BSCConnector
from src.chains.polygon_connector import PolygonConnector
from src.config.models import Settings
from src.database.manager import DatabaseManager
from src.detectors.pool_scanner import PoolScanner
from src.detectors.profit_calculator import ProfitCalculator
from src.detectors.transaction_analyzer import TransactionAnalyzer
from src.monitors.chain_monitor import ChainMonitor
from src.monitoring.metrics import start_metrics_server
from src.services.retention import DataRetentionService

# Load environment variables
load_dotenv()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class Application:
    """Main application orchestrator"""

    def __init__(self):
        """Initialize application components"""
        self.settings: Optional[Settings] = None
        self.db_manager: Optional[DatabaseManager] = None
        self.cache_manager: Optional[CacheManager] = None
        
        # Chain connectors
        self.bsc_connector: Optional[BSCConnector] = None
        self.polygon_connector: Optional[PolygonConnector] = None
        
        # Analyzers and calculators
        self.bsc_analyzer: Optional[TransactionAnalyzer] = None
        self.polygon_analyzer: Optional[TransactionAnalyzer] = None
        self.bsc_profit_calc: Optional[ProfitCalculator] = None
        self.polygon_profit_calc: Optional[ProfitCalculator] = None
        
        # Monitors and scanners
        self.bsc_monitor: Optional[ChainMonitor] = None
        self.polygon_monitor: Optional[ChainMonitor] = None
        self.bsc_scanner: Optional[PoolScanner] = None
        self.polygon_scanner: Optional[PoolScanner] = None
        
        # Services
        self.stats_aggregator: Optional[StatsAggregator] = None
        self.retention_service: Optional[DataRetentionService] = None
        
        # FastAPI app
        self.app = None
        
        # Shutdown flag
        self._shutdown_event = asyncio.Event()
        
        self._logger = logger.bind(component="application")

    async def initialize(self) -> None:
        """Initialize all application components"""
        self._logger.info("application_initializing")
        
        try:
            # Load settings from environment variables
            self._logger.info("loading_settings")
            self.settings = Settings()
            
            # Configure logging level
            log_level = self.settings.log_level.upper()
            structlog.configure(
                wrapper_class=structlog.make_filtering_bound_logger(
                    getattr(structlog.stdlib.logging, log_level, structlog.stdlib.logging.INFO)
                ),
            )
            
            self._logger.info(
                "settings_loaded",
                log_level=log_level,
                database_url=self.settings.database_url.split("@")[-1] if "@" in self.settings.database_url else "***",
            )
            
            # Initialize database manager
            self._logger.info("initializing_database")
            self.db_manager = DatabaseManager(self.settings.database_url)
            await self.db_manager.connect()
            await self.db_manager.initialize_schema()
            self._logger.info("database_initialized")
            
            # Initialize cache manager (optional)
            try:
                self._logger.info("initializing_cache")
                self.cache_manager = CacheManager(self.settings.redis_url)
                await self.cache_manager.connect()
                self._logger.info("cache_initialized")
            except Exception as e:
                self._logger.warning(
                    "cache_initialization_failed",
                    error=str(e),
                    message="Continuing without cache",
                )
                self.cache_manager = None
            
            # Get chain configurations
            bsc_config = self.settings.get_bsc_config()
            polygon_config = self.settings.get_polygon_config()
            
            # Initialize BSC components
            self._logger.info("initializing_bsc_components")
            self.bsc_connector = BSCConnector(bsc_config)
            self.bsc_analyzer = TransactionAnalyzer(
                chain_name="BSC",
                dex_routers=bsc_config.dex_routers,
            )
            self.bsc_profit_calc = ProfitCalculator(
                chain_name="BSC",
                native_token_usd_price=bsc_config.native_token_usd,
            )
            
            # Initialize Polygon components
            self._logger.info("initializing_polygon_components")
            self.polygon_connector = PolygonConnector(polygon_config)
            self.polygon_analyzer = TransactionAnalyzer(
                chain_name="Polygon",
                dex_routers=polygon_config.dex_routers,
            )
            self.polygon_profit_calc = ProfitCalculator(
                chain_name="Polygon",
                native_token_usd_price=polygon_config.native_token_usd,
            )
            
            # Initialize chain monitors
            self._logger.info("initializing_chain_monitors")
            self.bsc_monitor = ChainMonitor(
                chain_connector=self.bsc_connector,
                transaction_analyzer=self.bsc_analyzer,
                profit_calculator=self.bsc_profit_calc,
                database_manager=self.db_manager,
                broadcast_callback=ws_manager.broadcast_transaction,
            )
            
            self.polygon_monitor = ChainMonitor(
                chain_connector=self.polygon_connector,
                transaction_analyzer=self.polygon_analyzer,
                profit_calculator=self.polygon_profit_calc,
                database_manager=self.db_manager,
                broadcast_callback=ws_manager.broadcast_transaction,
            )
            
            # Initialize pool scanners
            self._logger.info("initializing_pool_scanners")
            self.bsc_scanner = PoolScanner(
                chain_connector=self.bsc_connector,
                config=bsc_config,
                database_manager=self.db_manager,
                cache_manager=self.cache_manager,
                scan_interval_seconds=3.0,  # BSC: 3 seconds
                broadcast_callback=ws_manager.broadcast_opportunity,
            )
            
            self.polygon_scanner = PoolScanner(
                chain_connector=self.polygon_connector,
                config=polygon_config,
                database_manager=self.db_manager,
                cache_manager=self.cache_manager,
                scan_interval_seconds=2.0,  # Polygon: 2 seconds
                broadcast_callback=ws_manager.broadcast_opportunity,
            )
            
            # Initialize statistics aggregator
            self._logger.info("initializing_stats_aggregator")
            self.stats_aggregator = StatsAggregator(
                database_manager=self.db_manager,
                aggregation_interval_hours=1,
            )
            
            # Initialize data retention service
            self._logger.info("initializing_retention_service")
            self.retention_service = DataRetentionService(
                database_manager=self.db_manager,
                opportunity_retention_days=30,
                transaction_archive_days=90,
            )
            
            # Create FastAPI application
            self._logger.info("creating_fastapi_app")
            self.app = create_app(
                settings=self.settings,
                db_manager=self.db_manager,
                cache_manager=self.cache_manager,
            )
            
            self._logger.info("application_initialized")
            
        except Exception as e:
            self._logger.error(
                "application_initialization_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def start(self) -> None:
        """Start all application components"""
        self._logger.info("application_starting")
        
        try:
            # Start WebSocket background tasks
            self._logger.info("starting_websocket_background_tasks")
            await ws_manager.start_background_tasks()
            
            # Start chain monitors
            self._logger.info("starting_chain_monitors")
            await self.bsc_monitor.start()
            await self.polygon_monitor.start()
            
            # Start pool scanners
            self._logger.info("starting_pool_scanners")
            await self.bsc_scanner.start()
            await self.polygon_scanner.start()
            
            # Start statistics aggregator
            self._logger.info("starting_stats_aggregator")
            await self.stats_aggregator.start()
            
            # Start data retention service
            self._logger.info("starting_retention_service")
            await self.retention_service.start()
            
            # Start Prometheus metrics server
            self._logger.info("starting_metrics_server", port=self.settings.prometheus_port)
            start_metrics_server(port=self.settings.prometheus_port)
            
            self._logger.info("application_started")
            
        except Exception as e:
            self._logger.error(
                "application_start_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def stop(self) -> None:
        """Stop all application components gracefully"""
        self._logger.info("application_stopping")
        
        try:
            # Stop data retention service
            if self.retention_service:
                self._logger.info("stopping_retention_service")
                await self.retention_service.stop()
            
            # Stop statistics aggregator
            if self.stats_aggregator:
                self._logger.info("stopping_stats_aggregator")
                await self.stats_aggregator.stop()
            
            # Stop pool scanners
            if self.bsc_scanner:
                self._logger.info("stopping_bsc_scanner")
                await self.bsc_scanner.stop()
            
            if self.polygon_scanner:
                self._logger.info("stopping_polygon_scanner")
                await self.polygon_scanner.stop()
            
            # Stop chain monitors
            if self.bsc_monitor:
                self._logger.info("stopping_bsc_monitor")
                await self.bsc_monitor.stop()
            
            if self.polygon_monitor:
                self._logger.info("stopping_polygon_monitor")
                await self.polygon_monitor.stop()
            
            # Stop WebSocket background tasks
            self._logger.info("stopping_websocket_background_tasks")
            await ws_manager.stop_background_tasks()
            
            # Close cache connection
            if self.cache_manager:
                self._logger.info("closing_cache_connection")
                await self.cache_manager.disconnect()
            
            # Close database connection
            if self.db_manager:
                self._logger.info("closing_database_connection")
                await self.db_manager.disconnect()
            
            self._logger.info("application_stopped")
            
        except Exception as e:
            self._logger.error(
                "application_stop_error",
                error=str(e),
                error_type=type(e).__name__,
            )

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            """Handle shutdown signals"""
            signal_name = signal.Signals(signum).name
            self._logger.info(
                "shutdown_signal_received",
                signal=signal_name,
            )
            self._shutdown_event.set()
        
        # Register signal handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        self._logger.info("signal_handlers_registered")

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal"""
        await self._shutdown_event.wait()


async def main() -> None:
    """Main application entry point"""
    app = Application()
    
    try:
        # Initialize application
        await app.initialize()
        
        # Setup signal handlers
        app.setup_signal_handlers()
        
        # Start application components
        await app.start()
        
        # Start uvicorn server in background
        config = uvicorn.Config(
            app.app,
            host="0.0.0.0",
            port=8000,
            log_level=app.settings.log_level.lower(),
            access_log=True,
        )
        server = uvicorn.Server(config)
        
        # Run server in background task
        server_task = asyncio.create_task(server.serve())
        
        logger.info(
            "uvicorn_server_started",
            host="0.0.0.0",
            port=8000,
        )
        
        # Wait for shutdown signal
        await app.wait_for_shutdown()
        
        # Shutdown server
        logger.info("shutting_down_uvicorn_server")
        server.should_exit = True
        await server_task
        
        # Stop application components
        await app.stop()
        
        logger.info("application_shutdown_complete")
        
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
        await app.stop()
    except Exception as e:
        logger.error(
            "application_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        await app.stop()
        sys.exit(1)


if __name__ == "__main__":
    """Run the application"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("application_terminated")
    except Exception as e:
        logger.error(
            "application_fatal_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        sys.exit(1)
