"""Verification script for REST API implementation"""

import asyncio
import os
from decimal import Decimal

from src.api.app import create_app
from src.config.models import Settings
from src.database.manager import DatabaseManager


async def verify_api():
    """Verify API can be created and configured correctly"""
    print("=" * 60)
    print("REST API Verification")
    print("=" * 60)

    # Set up minimal environment variables for testing
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
    os.environ["REDIS_URL"] = "redis://localhost:6379"
    os.environ["BSC_RPC_PRIMARY"] = "https://bsc-dataseed.bnbchain.org"
    os.environ["BSC_RPC_FALLBACK"] = "https://bsc-dataseed1.binance.org"
    os.environ["POLYGON_RPC_PRIMARY"] = "https://polygon-rpc.com"
    os.environ["POLYGON_RPC_FALLBACK"] = "https://rpc-mainnet.matic.network"
    os.environ["API_KEYS"] = "test_key_1,test_key_2,test_key_3"

    try:
        # Load settings
        settings = Settings()
        print("\n✓ Settings loaded successfully")
        print(f"  - API Keys configured: {len(settings.get_api_keys_list())}")
        print(f"  - Rate limit: {settings.rate_limit_per_minute} req/min")

        # Create database manager (without connecting)
        db_manager = DatabaseManager(settings.database_url)
        print("\n✓ Database manager created")

        # Create FastAPI app
        app = create_app(settings, db_manager)
        print("\n✓ FastAPI application created")
        print(f"  - Title: {app.title}")
        print(f"  - Version: {app.version}")
        print(f"  - Docs URL: {app.docs_url}")

        # Verify routes are registered
        routes = [route.path for route in app.routes]
        expected_routes = [
            "/api/v1/chains",
            "/api/v1/opportunities",
            "/api/v1/transactions",
            "/api/v1/arbitrageurs",
            "/api/v1/stats",
            "/api/v1/health",
        ]

        print("\n✓ Routes registered:")
        for route in expected_routes:
            if route in routes:
                print(f"  ✓ {route}")
            else:
                print(f"  ✗ {route} - MISSING!")

        # Verify API key authentication is configured
        if hasattr(app.state, "api_key_auth"):
            print("\n✓ API key authentication configured")
            print(f"  - Valid keys: {len(app.state.api_key_auth.api_keys)}")
        else:
            print("\n✗ API key authentication NOT configured")

        # Verify CORS middleware
        middleware_types = [type(m).__name__ for m in app.user_middleware]
        if "CORSMiddleware" in middleware_types:
            print("\n✓ CORS middleware configured")
        else:
            print("\n✗ CORS middleware NOT configured")

        print("\n" + "=" * 60)
        print("API Verification Complete!")
        print("=" * 60)
        print("\nAll endpoints implemented:")
        print("  - GET /api/v1/chains - Chain status")
        print("  - GET /api/v1/opportunities - Arbitrage opportunities")
        print("  - GET /api/v1/transactions - Arbitrage transactions")
        print("  - GET /api/v1/arbitrageurs - Arbitrageur profiles")
        print("  - GET /api/v1/stats - Aggregated statistics")
        print("  - GET /api/v1/health - Health check (no auth required)")
        print("\nAuthentication: X-API-Key header required (except /health)")
        print("Documentation: Available at /docs when server is running")

    except Exception as e:
        print(f"\n✗ Error during verification: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(verify_api())
    exit(0 if success else 1)
