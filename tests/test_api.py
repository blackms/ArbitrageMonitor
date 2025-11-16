"""Integration tests for FastAPI REST API

These tests require a PostgreSQL test database to be running.
To run these tests, ensure you have a PostgreSQL instance with:
- Database: arbitrage_monitor_test
- User: monitor
- Password: password
- Host: localhost
- Port: 5432

You can set up a test database with Docker:
docker run --name postgres-test -e POSTGRES_DB=arbitrage_monitor_test \
    -e POSTGRES_USER=monitor -e POSTGRES_PASSWORD=password \
    -p 5432:5432 -d postgres:15

Or skip these tests with: pytest -m "not integration"
"""

import os
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config.models import Settings
from src.database import (
    Arbitrageur,
    ArbitrageTransaction,
    DatabaseManager,
    Opportunity,
)


# Test database URL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://monitor:password@localhost:5432/arbitrage_monitor_test"
)

# Test API keys
TEST_API_KEY_VALID = "test-api-key-12345"
TEST_API_KEY_INVALID = "invalid-key-99999"

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture
async def db_manager():
    """Create database manager for testing"""
    manager = DatabaseManager(TEST_DATABASE_URL, min_pool_size=2, max_pool_size=5)
    
    try:
        await manager.connect()
        await manager.initialize_schema()
        
        # Insert test chain data
        async with manager.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chains (name, chain_id, rpc_primary, block_time_seconds, 
                                   native_token, native_token_usd, status, last_synced_block,
                                   blocks_behind, uptime_pct)
                VALUES ('BSC', 56, 'https://bsc-dataseed.bnbchain.org', 3.0, 'BNB', 300.0,
                        'active', 12345678, 5, 99.9),
                       ('Polygon', 137, 'https://polygon-rpc.com', 2.0, 'MATIC', 0.8,
                        'active', 23456789, 3, 99.8)
                ON CONFLICT (chain_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    last_synced_block = EXCLUDED.last_synced_block,
                    blocks_behind = EXCLUDED.blocks_behind,
                    uptime_pct = EXCLUDED.uptime_pct
                """
            )
        
        yield manager
    finally:
        # Cleanup
        if manager.pool:
            async with manager.pool.acquire() as conn:
                await conn.execute(
                    "TRUNCATE opportunities, transactions, arbitrageurs, chain_stats CASCADE"
                )
        await manager.disconnect()


@pytest.fixture
def test_settings():
    """Create test settings"""
    return Settings(
        database_url=TEST_DATABASE_URL,
        bsc_rpc_primary="https://bsc-dataseed.bnbchain.org",
        bsc_rpc_fallback="https://bsc-dataseed1.binance.org",
        polygon_rpc_primary="https://polygon-rpc.com",
        polygon_rpc_fallback="https://rpc-mainnet.matic.network",
        api_keys=TEST_API_KEY_VALID,
        log_level="INFO",
    )


@pytest.fixture
async def client(db_manager, test_settings):
    """Create test client with FastAPI app"""
    app = create_app(test_settings, db_manager)
    with TestClient(app) as test_client:
        yield test_client



# ============================================================================
# Authentication Tests
# ============================================================================

def test_api_authentication_missing_key(client):
    """Test API request without API key returns 401"""
    response = client.get("/api/v1/chains")
    assert response.status_code == 401
    assert "Missing API key" in response.json()["detail"]


def test_api_authentication_invalid_key(client):
    """Test API request with invalid API key returns 401"""
    response = client.get(
        "/api/v1/chains",
        headers={"X-API-Key": TEST_API_KEY_INVALID}
    )
    assert response.status_code == 401
    assert "Invalid API key" in response.json()["detail"]


def test_api_authentication_valid_key(client):
    """Test API request with valid API key succeeds"""
    response = client.get(
        "/api/v1/chains",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    assert response.status_code == 200


def test_health_endpoint_no_auth_required(client):
    """Test health endpoint does not require authentication"""
    response = client.get("/api/v1/health")
    assert response.status_code in [200, 503]  # May be unhealthy but accessible


# ============================================================================
# Chains Endpoint Tests
# ============================================================================

def test_get_chains_success(client):
    """Test GET /api/v1/chains returns chain status"""
    response = client.get(
        "/api/v1/chains",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    
    # Verify BSC chain
    bsc = next((c for c in data if c["chain_id"] == 56), None)
    assert bsc is not None
    assert bsc["name"] == "BSC"
    assert bsc["status"] == "active"
    assert bsc["native_token"] == "BNB"
    assert "last_synced_block" in bsc
    assert "blocks_behind" in bsc
    assert "uptime_pct" in bsc



# ============================================================================
# Opportunities Endpoint Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_opportunities_empty(client, db_manager):
    """Test GET /api/v1/opportunities with no data"""
    response = client.get(
        "/api/v1/opportunities",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_opportunities_with_data(client, db_manager):
    """Test GET /api/v1/opportunities returns opportunities"""
    # Create test opportunities
    for i in range(5):
        opp = Opportunity(
            chain_id=56,
            pool_name=f"WBNB-BUSD-{i}",
            pool_address=f"0xpool{i:040d}",
            imbalance_pct=Decimal(f"{5 + i}.0"),
            profit_usd=Decimal(f"{10000 + i * 5000}.0"),
            profit_native=Decimal(f"{30 + i * 10}.0"),
            reserve0=Decimal("1000000.0"),
            reserve1=Decimal("300000000.0"),
            block_number=12345678 + i,
            detected_at=datetime.utcnow(),
        )
        await db_manager.save_opportunity(opp)
    
    response = client.get(
        "/api/v1/opportunities",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 5
    assert all("pool_name" in opp for opp in data)
    assert all("profit_usd" in opp for opp in data)


@pytest.mark.asyncio
async def test_get_opportunities_filter_by_chain(client, db_manager):
    """Test filtering opportunities by chain_id"""
    # Create opportunities on different chains
    for chain_id in [56, 137]:
        opp = Opportunity(
            chain_id=chain_id,
            pool_name=f"Pool-Chain-{chain_id}",
            pool_address=f"0xchain{chain_id:038d}",
            imbalance_pct=Decimal("5.0"),
            profit_usd=Decimal("10000.0"),
            profit_native=Decimal("30.0"),
            reserve0=Decimal("1000000.0"),
            reserve1=Decimal("300000000.0"),
            block_number=12345678,
            detected_at=datetime.utcnow(),
        )
        await db_manager.save_opportunity(opp)
    
    response = client.get(
        "/api/v1/opportunities?chain_id=56",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert all(opp["chain_id"] == 56 for opp in data)



@pytest.mark.asyncio
async def test_get_opportunities_filter_by_profit(client, db_manager):
    """Test filtering opportunities by profit range"""
    # Create opportunities with different profits
    profits = [5000, 15000, 25000, 35000, 45000]
    for i, profit in enumerate(profits):
        opp = Opportunity(
            chain_id=56,
            pool_name=f"Pool-Profit-{profit}",
            pool_address=f"0xprofit{i:038d}",
            imbalance_pct=Decimal("5.0"),
            profit_usd=Decimal(str(profit)),
            profit_native=Decimal("30.0"),
            reserve0=Decimal("1000000.0"),
            reserve1=Decimal("300000000.0"),
            block_number=12345678 + i,
            detected_at=datetime.utcnow(),
        )
        await db_manager.save_opportunity(opp)
    
    # Test min_profit filter
    response = client.get(
        "/api/v1/opportunities?min_profit=20000",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert all(float(opp["profit_usd"]) >= 20000 for opp in data)
    
    # Test max_profit filter
    response = client.get(
        "/api/v1/opportunities?max_profit=20000",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert all(float(opp["profit_usd"]) <= 20000 for opp in data)


@pytest.mark.asyncio
async def test_get_opportunities_pagination(client, db_manager):
    """Test pagination with limit and offset"""
    # Create 10 opportunities
    for i in range(10):
        opp = Opportunity(
            chain_id=56,
            pool_name=f"Pool-Page-{i}",
            pool_address=f"0xpage{i:041d}",
            imbalance_pct=Decimal("5.0"),
            profit_usd=Decimal("10000.0"),
            profit_native=Decimal("30.0"),
            reserve0=Decimal("1000000.0"),
            reserve1=Decimal("300000000.0"),
            block_number=12345678 + i,
            detected_at=datetime.utcnow(),
        )
        await db_manager.save_opportunity(opp)
    
    # Test limit
    response = client.get(
        "/api/v1/opportunities?limit=5",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5
    
    # Test offset
    response = client.get(
        "/api/v1/opportunities?limit=5&offset=5",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 5



# ============================================================================
# Transactions Endpoint Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_transactions_empty(client, db_manager):
    """Test GET /api/v1/transactions with no data"""
    response = client.get(
        "/api/v1/transactions",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_transactions_with_data(client, db_manager):
    """Test GET /api/v1/transactions returns transactions"""
    # Create test transactions
    for i in range(3):
        tx = ArbitrageTransaction(
            chain_id=56,
            tx_hash=f"0xtx{i:062d}",
            from_address=f"0xaddr{i:038d}",
            block_number=12345678 + i,
            block_timestamp=datetime.utcnow(),
            gas_price_gwei=Decimal("5.0"),
            gas_used=250000,
            gas_cost_native=Decimal("0.00125"),
            gas_cost_usd=Decimal("0.375"),
            swap_count=2 + i,
            strategy=f"{2 + i}-hop",
            profit_gross_usd=Decimal(f"{1000 + i * 500}.0"),
            profit_net_usd=Decimal(f"{999 + i * 500}.0"),
            pools_involved=[f"0xpool{j}" for j in range(2 + i)],
            tokens_involved=["WBNB", "BUSD", "USDT"],
            detected_at=datetime.utcnow(),
        )
        await db_manager.save_transaction(tx)
    
    response = client.get(
        "/api/v1/transactions",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 3
    assert all("tx_hash" in tx for tx in data)
    assert all("swap_count" in tx for tx in data)
    assert all("strategy" in tx for tx in data)


@pytest.mark.asyncio
async def test_get_transactions_filter_by_chain(client, db_manager):
    """Test filtering transactions by chain_id"""
    # Create transactions on different chains
    for chain_id in [56, 137]:
        tx = ArbitrageTransaction(
            chain_id=chain_id,
            tx_hash=f"0xchain{chain_id:058d}",
            from_address=f"0xaddr{chain_id:038d}",
            block_number=12345678,
            block_timestamp=datetime.utcnow(),
            gas_price_gwei=Decimal("5.0"),
            gas_used=250000,
            gas_cost_native=Decimal("0.00125"),
            gas_cost_usd=Decimal("0.375"),
            swap_count=2,
            strategy="2-hop",
            pools_involved=["0xpool1", "0xpool2"],
            tokens_involved=["WBNB", "BUSD"],
            detected_at=datetime.utcnow(),
        )
        await db_manager.save_transaction(tx)
    
    response = client.get(
        "/api/v1/transactions?chain_id=137",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert all(tx["chain_id"] == 137 for tx in data)



@pytest.mark.asyncio
async def test_get_transactions_filter_by_address(client, db_manager):
    """Test filtering transactions by from_address"""
    address1 = "0xaddr1000000000000000000000000000000000001"
    address2 = "0xaddr2000000000000000000000000000000000002"
    
    # Create transactions from different addresses
    for i, address in enumerate([address1, address1, address2]):
        tx = ArbitrageTransaction(
            chain_id=56,
            tx_hash=f"0xaddr{i:061d}",
            from_address=address,
            block_number=12345678 + i,
            block_timestamp=datetime.utcnow(),
            gas_price_gwei=Decimal("5.0"),
            gas_used=250000,
            gas_cost_native=Decimal("0.00125"),
            gas_cost_usd=Decimal("0.375"),
            swap_count=2,
            strategy="2-hop",
            pools_involved=["0xpool1", "0xpool2"],
            tokens_involved=["WBNB", "BUSD"],
            detected_at=datetime.utcnow(),
        )
        await db_manager.save_transaction(tx)
    
    response = client.get(
        f"/api/v1/transactions?from_address={address1}",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert all(tx["from_address"] == address1 for tx in data)


@pytest.mark.asyncio
async def test_get_transactions_filter_by_swaps(client, db_manager):
    """Test filtering transactions by minimum swap count"""
    # Create transactions with different swap counts
    for swap_count in [2, 3, 4]:
        tx = ArbitrageTransaction(
            chain_id=56,
            tx_hash=f"0xswap{swap_count:061d}",
            from_address=f"0xaddr{swap_count:038d}",
            block_number=12345678,
            block_timestamp=datetime.utcnow(),
            gas_price_gwei=Decimal("5.0"),
            gas_used=250000,
            gas_cost_native=Decimal("0.00125"),
            gas_cost_usd=Decimal("0.375"),
            swap_count=swap_count,
            strategy=f"{swap_count}-hop",
            pools_involved=[f"0xpool{i}" for i in range(swap_count)],
            tokens_involved=["WBNB", "BUSD"],
            detected_at=datetime.utcnow(),
        )
        await db_manager.save_transaction(tx)
    
    response = client.get(
        "/api/v1/transactions?min_swaps=3",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert all(tx["swap_count"] >= 3 for tx in data)


@pytest.mark.asyncio
async def test_get_transactions_filter_by_strategy(client, db_manager):
    """Test filtering transactions by strategy"""
    # Create transactions with different strategies
    for strategy in ["2-hop", "3-hop", "4-hop"]:
        swap_count = int(strategy[0])
        tx = ArbitrageTransaction(
            chain_id=56,
            tx_hash=f"0xstrat{swap_count:060d}",
            from_address=f"0xaddr{swap_count:038d}",
            block_number=12345678,
            block_timestamp=datetime.utcnow(),
            gas_price_gwei=Decimal("5.0"),
            gas_used=250000,
            gas_cost_native=Decimal("0.00125"),
            gas_cost_usd=Decimal("0.375"),
            swap_count=swap_count,
            strategy=strategy,
            pools_involved=[f"0xpool{i}" for i in range(swap_count)],
            tokens_involved=["WBNB", "BUSD"],
            detected_at=datetime.utcnow(),
        )
        await db_manager.save_transaction(tx)
    
    response = client.get(
        "/api/v1/transactions?strategy=3-hop",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert all(tx["strategy"] == "3-hop" for tx in data)



@pytest.mark.asyncio
async def test_get_transactions_pagination(client, db_manager):
    """Test transaction pagination"""
    # Create 10 transactions
    for i in range(10):
        tx = ArbitrageTransaction(
            chain_id=56,
            tx_hash=f"0xpage{i:061d}",
            from_address=f"0xaddr{i:038d}",
            block_number=12345678 + i,
            block_timestamp=datetime.utcnow(),
            gas_price_gwei=Decimal("5.0"),
            gas_used=250000,
            gas_cost_native=Decimal("0.00125"),
            gas_cost_usd=Decimal("0.375"),
            swap_count=2,
            strategy="2-hop",
            pools_involved=["0xpool1", "0xpool2"],
            tokens_involved=["WBNB", "BUSD"],
            detected_at=datetime.utcnow(),
        )
        await db_manager.save_transaction(tx)
    
    # Test limit
    response = client.get(
        "/api/v1/transactions?limit=3",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    
    # Test offset
    response = client.get(
        "/api/v1/transactions?limit=3&offset=3",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 3


# ============================================================================
# Arbitrageurs Endpoint Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_arbitrageurs_empty(client, db_manager):
    """Test GET /api/v1/arbitrageurs with no data"""
    response = client.get(
        "/api/v1/arbitrageurs",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_arbitrageurs_with_data(client, db_manager):
    """Test GET /api/v1/arbitrageurs returns arbitrageur profiles"""
    # Create test arbitrageurs via transactions
    for i in range(3):
        address = f"0xarb{i:041d}"
        tx_data = {
            "success": True,
            "profit_usd": Decimal(f"{500 + i * 100}.0"),
            "gas_spent_usd": Decimal("10.0"),
            "gas_price_gwei": Decimal("5.0"),
            "strategy": "2-hop",
        }
        await db_manager.update_arbitrageur(address, 56, tx_data)
    
    response = client.get(
        "/api/v1/arbitrageurs",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 3
    assert all("address" in arb for arb in data)
    assert all("total_transactions" in arb for arb in data)
    assert all("total_profit_usd" in arb for arb in data)



@pytest.mark.asyncio
async def test_get_arbitrageurs_filter_by_chain(client, db_manager):
    """Test filtering arbitrageurs by chain_id"""
    # Create arbitrageurs on different chains
    for chain_id in [56, 137]:
        address = f"0xchain{chain_id:037d}"
        tx_data = {
            "success": True,
            "profit_usd": Decimal("500.0"),
            "gas_spent_usd": Decimal("10.0"),
            "gas_price_gwei": Decimal("5.0"),
            "strategy": "2-hop",
        }
        await db_manager.update_arbitrageur(address, chain_id, tx_data)
    
    response = client.get(
        "/api/v1/arbitrageurs?chain_id=56",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert all(arb["chain_id"] == 56 for arb in data)


@pytest.mark.asyncio
async def test_get_arbitrageurs_filter_by_min_transactions(client, db_manager):
    """Test filtering arbitrageurs by minimum transaction count"""
    # Create arbitrageurs with different transaction counts
    for i in range(1, 4):
        address = f"0xtxcount{i:037d}"
        for _ in range(i):
            tx_data = {
                "success": True,
                "profit_usd": Decimal("500.0"),
                "gas_spent_usd": Decimal("10.0"),
                "gas_price_gwei": Decimal("5.0"),
                "strategy": "2-hop",
            }
            await db_manager.update_arbitrageur(address, 56, tx_data)
    
    response = client.get(
        "/api/v1/arbitrageurs?min_transactions=2",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert all(arb["total_transactions"] >= 2 for arb in data)


@pytest.mark.asyncio
async def test_get_arbitrageurs_sorting(client, db_manager):
    """Test sorting arbitrageurs by different fields"""
    # Create arbitrageurs with different profits
    profits = [1000, 500, 1500]
    for i, profit in enumerate(profits):
        address = f"0xsort{i:041d}"
        tx_data = {
            "success": True,
            "profit_usd": Decimal(str(profit)),
            "gas_spent_usd": Decimal("10.0"),
            "gas_price_gwei": Decimal("5.0"),
            "strategy": "2-hop",
        }
        await db_manager.update_arbitrageur(address, 56, tx_data)
    
    # Test sort by profit descending
    response = client.get(
        "/api/v1/arbitrageurs?sort_by=total_profit&sort_order=desc",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    if len(data) >= 2:
        # Verify descending order
        profits = [float(arb["total_profit_usd"]) for arb in data]
        assert profits == sorted(profits, reverse=True)


@pytest.mark.asyncio
async def test_get_arbitrageurs_pagination(client, db_manager):
    """Test arbitrageur pagination"""
    # Create 10 arbitrageurs
    for i in range(10):
        address = f"0xpagearb{i:037d}"
        tx_data = {
            "success": True,
            "profit_usd": Decimal("500.0"),
            "gas_spent_usd": Decimal("10.0"),
            "gas_price_gwei": Decimal("5.0"),
            "strategy": "2-hop",
        }
        await db_manager.update_arbitrageur(address, 56, tx_data)
    
    # Test limit
    response = client.get(
        "/api/v1/arbitrageurs?limit=5",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5



# ============================================================================
# Statistics Endpoint Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_stats_empty(client, db_manager):
    """Test GET /api/v1/stats with no data"""
    response = client.get(
        "/api/v1/stats",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_stats_with_data(client, db_manager):
    """Test GET /api/v1/stats returns statistics"""
    # Insert test statistics
    async with db_manager.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chain_stats (
                chain_id, hour_timestamp, opportunities_detected, opportunities_captured,
                small_opportunities_count, small_opps_captured, transactions_detected,
                unique_arbitrageurs, total_profit_usd, total_gas_spent_usd,
                avg_profit_usd, median_profit_usd, max_profit_usd, min_profit_usd,
                p95_profit_usd, capture_rate, small_opp_capture_rate, avg_competition_level
            )
            VALUES (
                56, $1, 100, 80, 30, 20, 80, 15, 150000.0, 5000.0,
                1875.0, 1500.0, 5000.0, 500.0, 3500.0, 80.0, 66.67, 2.5
            )
            """,
            datetime.utcnow() - timedelta(hours=1)
        )
    
    response = client.get(
        "/api/v1/stats",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    
    stat = data[0]
    assert "chain_id" in stat
    assert "opportunities_detected" in stat
    assert "capture_rate" in stat
    assert "profit_distribution" in stat
    assert "gas_statistics" in stat


@pytest.mark.asyncio
async def test_get_stats_filter_by_chain(client, db_manager):
    """Test filtering statistics by chain_id"""
    # Insert statistics for different chains
    for chain_id in [56, 137]:
        async with db_manager.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chain_stats (
                    chain_id, hour_timestamp, opportunities_detected, opportunities_captured,
                    small_opportunities_count, small_opps_captured, transactions_detected,
                    unique_arbitrageurs, total_profit_usd, total_gas_spent_usd
                )
                VALUES ($1, $2, 100, 80, 30, 20, 80, 15, 150000.0, 5000.0)
                """,
                chain_id,
                datetime.utcnow() - timedelta(hours=1)
            )
    
    response = client.get(
        "/api/v1/stats?chain_id=137",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert all(stat["chain_id"] == 137 for stat in data)


@pytest.mark.asyncio
async def test_get_stats_filter_by_period(client, db_manager):
    """Test filtering statistics by time period"""
    # Insert statistics at different times
    now = datetime.utcnow()
    timestamps = [
        now - timedelta(hours=0.5),  # Within 1h
        now - timedelta(hours=12),   # Within 24h
        now - timedelta(days=3),     # Within 7d
        now - timedelta(days=15),    # Within 30d
    ]
    
    for i, timestamp in enumerate(timestamps):
        async with db_manager.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chain_stats (
                    chain_id, hour_timestamp, opportunities_detected, opportunities_captured,
                    small_opportunities_count, small_opps_captured, transactions_detected,
                    unique_arbitrageurs, total_profit_usd, total_gas_spent_usd
                )
                VALUES (56, $1, $2, 80, 30, 20, 80, 15, 150000.0, 5000.0)
                """,
                timestamp,
                100 + i
            )
    
    # Test 1h period
    response = client.get(
        "/api/v1/stats?period=1h",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 200
    data = response.json()
    # Should only include stats from last hour
    assert all(
        (now - stat_time).total_seconds() <= 3600
        for stat in data
        for stat_time in [datetime.fromisoformat(stat["hour_timestamp"].replace("Z", "+00:00"))]
    )



@pytest.mark.asyncio
async def test_get_stats_invalid_period(client, db_manager):
    """Test statistics endpoint with invalid period parameter"""
    response = client.get(
        "/api/v1/stats?period=invalid",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    # Should return 422 for validation error
    assert response.status_code == 422


# ============================================================================
# Health Endpoint Tests
# ============================================================================

def test_health_check_healthy(client):
    """Test health check returns healthy status"""
    response = client.get("/api/v1/health")
    
    assert response.status_code in [200, 503]
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "database_pool_size" in data
    assert "database_pool_free" in data


# ============================================================================
# Error Response Tests
# ============================================================================

def test_invalid_endpoint_returns_404(client):
    """Test requesting non-existent endpoint returns 404"""
    response = client.get(
        "/api/v1/nonexistent",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalid_chain_id_parameter(client, db_manager):
    """Test invalid chain_id parameter returns validation error"""
    response = client.get(
        "/api/v1/opportunities?chain_id=invalid",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    # Should return 422 for validation error
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_limit_parameter(client, db_manager):
    """Test invalid limit parameter returns validation error"""
    response = client.get(
        "/api/v1/opportunities?limit=-1",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    # Should return 422 for validation error
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_offset_parameter(client, db_manager):
    """Test invalid offset parameter returns validation error"""
    response = client.get(
        "/api/v1/opportunities?offset=-1",
        headers={"X-API-Key": TEST_API_KEY_VALID}
    )
    
    # Should return 422 for validation error
    assert response.status_code == 422


# ============================================================================
# CORS Tests
# ============================================================================

def test_cors_headers_present(client):
    """Test CORS headers are present in responses"""
    response = client.options(
        "/api/v1/chains",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        }
    )
    
    # CORS preflight should succeed
    assert response.status_code in [200, 204]
