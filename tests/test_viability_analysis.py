"""Comprehensive unit tests for small trader viability analysis"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.analytics.stats_aggregator import StatsAggregator
from src.detectors.pool_scanner import PoolScanner
from src.config.models import ChainConfig


@pytest.fixture
def bsc_config():
    """Create BSC chain configuration for testing"""
    return ChainConfig(
        name="BSC",
        chain_id=56,
        rpc_urls=["https://bsc-dataseed.bnbchain.org"],
        block_time_seconds=3.0,
        native_token="BNB",
        native_token_usd=Decimal("300.0"),
        dex_routers={
            "PancakeSwap V2": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
        },
        pools={
            "WBNB-BUSD": "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
        }
    )


@pytest.fixture
def mock_chain_connector():
    """Create mock chain connector"""
    connector = MagicMock()
    connector.w3 = MagicMock()
    connector.get_latest_block = AsyncMock(return_value=12345678)
    return connector


@pytest.fixture
def mock_database_manager():
    """Create mock database manager"""
    db_manager = MagicMock()
    db_manager.pool = MagicMock()
    db_manager.save_opportunity = AsyncMock()
    return db_manager


@pytest.fixture
def pool_scanner(mock_chain_connector, bsc_config):
    """Create pool scanner for testing"""
    return PoolScanner(
        chain_connector=mock_chain_connector,
        config=bsc_config,
        database_manager=None,
        scan_interval_seconds=3.0,
        imbalance_threshold_pct=5.0,
        swap_fee_pct=0.3,
        small_opp_min_usd=10000.0,
        small_opp_max_usd=100000.0,
    )


@pytest.fixture
def stats_aggregator(mock_database_manager):
    """Create stats aggregator for testing"""
    return StatsAggregator(
        database_manager=mock_database_manager,
        aggregation_interval_seconds=3600.0,
        small_opp_min_usd=10000.0,
        small_opp_max_usd=100000.0,
    )


class TestSmallOpportunityClassification:
    """Test small opportunity classification for $10K-$100K range (Requirement 11.1)"""

    def test_classify_small_opportunity_within_range(self, pool_scanner):
        """Test opportunity within $10K-$100K is classified as small"""
        profit_usd = Decimal("50000")  # $50K
        
        is_small = pool_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is True

    def test_classify_small_opportunity_at_lower_bound(self, pool_scanner):
        """Test opportunity at exactly $10K is classified as small"""
        profit_usd = Decimal("10000")  # $10K
        
        is_small = pool_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is True

    def test_classify_small_opportunity_at_upper_bound(self, pool_scanner):
        """Test opportunity at exactly $100K is classified as small"""
        profit_usd = Decimal("100000")  # $100K
        
        is_small = pool_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is True

    def test_classify_small_opportunity_below_range(self, pool_scanner):
        """Test opportunity below $10K is not classified as small"""
        profit_usd = Decimal("5000")  # $5K
        
        is_small = pool_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is False

    def test_classify_small_opportunity_above_range(self, pool_scanner):
        """Test opportunity above $100K is not classified as small"""
        profit_usd = Decimal("150000")  # $150K
        
        is_small = pool_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is False

    def test_classify_small_opportunity_just_below_lower_bound(self, pool_scanner):
        """Test opportunity just below $10K is not classified as small"""
        profit_usd = Decimal("9999.99")
        
        is_small = pool_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is False

    def test_classify_small_opportunity_just_above_upper_bound(self, pool_scanner):
        """Test opportunity just above $100K is not classified as small"""
        profit_usd = Decimal("100000.01")
        
        is_small = pool_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is False

    def test_small_opportunity_count_tracking(self, pool_scanner):
        """Test small opportunity count is tracked correctly (Requirement 11.2)"""
        # Initial count should be zero
        assert pool_scanner.get_small_opportunity_count() == 0

    def test_custom_small_opportunity_range(self, mock_chain_connector, bsc_config):
        """Test scanner with custom small opportunity range"""
        scanner = PoolScanner(
            chain_connector=mock_chain_connector,
            config=bsc_config,
            small_opp_min_usd=20000.0,
            small_opp_max_usd=80000.0,
        )
        
        assert scanner.small_opp_min_usd == Decimal("20000")
        assert scanner.small_opp_max_usd == Decimal("80000")
        
        # Test classification with custom range
        assert scanner.is_small_opportunity(Decimal("30000")) is True
        assert scanner.is_small_opportunity(Decimal("15000")) is False
        assert scanner.is_small_opportunity(Decimal("90000")) is False


class TestCaptureRateCalculation:
    """Test capture rate calculation for opportunities (Requirement 11.4)"""

    @pytest.mark.asyncio
    async def test_capture_rate_calculation_all_captured(self, stats_aggregator):
        """Test capture rate when all opportunities are captured"""
        # Mock database query results - all opportunities captured
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            # Opportunities query result
            [{
                "total_opportunities": 100,
                "captured_opportunities": 100,
                "small_opportunities": 30,
                "small_opps_captured": 30,
            }],
            # Transactions query result
            [{
                "total_transactions": 100,
                "unique_arbitrageurs": 20,
                "total_profit": Decimal("500000"),
                "total_gas_spent": Decimal("50000"),
                "avg_profit": Decimal("5000"),
                "median_profit": Decimal("4500"),
                "max_profit": Decimal("50000"),
                "min_profit": Decimal("1000"),
                "p95_profit": Decimal("20000"),
            }],
            # Small opportunity arbitrageurs query
            [{"captured_by": f"0xAddress{i}"} for i in range(15)],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        # Verify capture rate calculation: (100 / 100) * 100 = 100%
        call_args = mock_conn.execute.call_args[0]
        capture_rate = call_args[16]  # capture_rate parameter
        assert capture_rate == Decimal("100")

    @pytest.mark.asyncio
    async def test_capture_rate_calculation_partial_captured(self, stats_aggregator):
        """Test capture rate when some opportunities are captured"""
        # Mock database query results - 60% captured
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 100,
                "captured_opportunities": 60,
                "small_opportunities": 30,
                "small_opps_captured": 18,
            }],
            [{
                "total_transactions": 60,
                "unique_arbitrageurs": 15,
                "total_profit": Decimal("300000"),
                "total_gas_spent": Decimal("30000"),
                "avg_profit": Decimal("5000"),
                "median_profit": Decimal("4500"),
                "max_profit": Decimal("50000"),
                "min_profit": Decimal("1000"),
                "p95_profit": Decimal("20000"),
            }],
            [{"captured_by": f"0xAddress{i}"} for i in range(10)],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        # Verify capture rate calculation: (60 / 100) * 100 = 60%
        call_args = mock_conn.execute.call_args[0]
        capture_rate = call_args[16]
        assert capture_rate == Decimal("60")

    @pytest.mark.asyncio
    async def test_capture_rate_calculation_none_captured(self, stats_aggregator):
        """Test capture rate when no opportunities are captured"""
        # Mock database query results - 0% captured
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 100,
                "captured_opportunities": 0,
                "small_opportunities": 30,
                "small_opps_captured": 0,
            }],
            [{
                "total_transactions": 0,
                "unique_arbitrageurs": 0,
                "total_profit": Decimal("0"),
                "total_gas_spent": Decimal("0"),
                "avg_profit": None,
                "median_profit": None,
                "max_profit": None,
                "min_profit": None,
                "p95_profit": None,
            }],
            [],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        # Verify capture rate calculation: (0 / 100) * 100 = 0%
        call_args = mock_conn.execute.call_args[0]
        capture_rate = call_args[16]
        assert capture_rate == Decimal("0")

    @pytest.mark.asyncio
    async def test_capture_rate_calculation_no_opportunities(self, stats_aggregator):
        """Test capture rate when no opportunities detected"""
        # Mock database query results - no opportunities
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 0,
                "captured_opportunities": 0,
                "small_opportunities": 0,
                "small_opps_captured": 0,
            }],
            [{
                "total_transactions": 0,
                "unique_arbitrageurs": 0,
                "total_profit": Decimal("0"),
                "total_gas_spent": Decimal("0"),
                "avg_profit": None,
                "median_profit": None,
                "max_profit": None,
                "min_profit": None,
                "p95_profit": None,
            }],
            [],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        # Verify capture rate is None when no opportunities
        call_args = mock_conn.execute.call_args[0]
        capture_rate = call_args[16]
        assert capture_rate is None

    @pytest.mark.asyncio
    async def test_small_opportunity_capture_rate_calculation(self, stats_aggregator):
        """Test small opportunity capture rate calculation (Requirement 11.3, 11.4)"""
        # Mock database query results - 60% of small opportunities captured
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 100,
                "captured_opportunities": 70,
                "small_opportunities": 50,
                "small_opps_captured": 30,
            }],
            [{
                "total_transactions": 70,
                "unique_arbitrageurs": 20,
                "total_profit": Decimal("400000"),
                "total_gas_spent": Decimal("40000"),
                "avg_profit": Decimal("5714"),
                "median_profit": Decimal("5000"),
                "max_profit": Decimal("50000"),
                "min_profit": Decimal("1000"),
                "p95_profit": Decimal("20000"),
            }],
            [{"captured_by": f"0xAddress{i}"} for i in range(12)],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        # Verify small opportunity capture rate: (30 / 50) * 100 = 60%
        call_args = mock_conn.execute.call_args[0]
        small_opp_capture_rate = call_args[17]  # small_opp_capture_rate parameter
        assert small_opp_capture_rate == Decimal("60")

    @pytest.mark.asyncio
    async def test_small_opportunity_capture_rate_no_small_opps(self, stats_aggregator):
        """Test small opportunity capture rate when no small opportunities"""
        # Mock database query results - no small opportunities
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 100,
                "captured_opportunities": 80,
                "small_opportunities": 0,
                "small_opps_captured": 0,
            }],
            [{
                "total_transactions": 80,
                "unique_arbitrageurs": 25,
                "total_profit": Decimal("800000"),
                "total_gas_spent": Decimal("60000"),
                "avg_profit": Decimal("10000"),
                "median_profit": Decimal("9000"),
                "max_profit": Decimal("150000"),
                "min_profit": Decimal("5000"),
                "p95_profit": Decimal("50000"),
            }],
            [],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        # Verify small opportunity capture rate is None when no small opportunities
        call_args = mock_conn.execute.call_args[0]
        small_opp_capture_rate = call_args[17]
        assert small_opp_capture_rate is None


class TestCompetitionLevelTracking:
    """Test competition level tracking for arbitrage opportunities (Requirement 11.5, 11.6)"""

    @pytest.mark.asyncio
    async def test_competition_level_calculation_basic(self, stats_aggregator):
        """Test basic competition level calculation"""
        # Mock database query results - 20 arbitrageurs for 100 opportunities
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 100,
                "captured_opportunities": 80,
                "small_opportunities": 30,
                "small_opps_captured": 25,
            }],
            [{
                "total_transactions": 80,
                "unique_arbitrageurs": 20,
                "total_profit": Decimal("500000"),
                "total_gas_spent": Decimal("50000"),
                "avg_profit": Decimal("6250"),
                "median_profit": Decimal("5500"),
                "max_profit": Decimal("50000"),
                "min_profit": Decimal("1000"),
                "p95_profit": Decimal("20000"),
            }],
            [{"captured_by": f"0xAddress{i}"} for i in range(15)],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        # Verify competition level: 20 arbitrageurs / 100 opportunities = 0.2
        call_args = mock_conn.execute.call_args[0]
        avg_competition_level = call_args[18]  # avg_competition_level parameter
        assert avg_competition_level == Decimal("0.2")

    @pytest.mark.asyncio
    async def test_competition_level_high_competition(self, stats_aggregator):
        """Test competition level with high competition (many arbitrageurs per opportunity)"""
        # Mock database query results - 50 arbitrageurs for 100 opportunities
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 100,
                "captured_opportunities": 95,
                "small_opportunities": 40,
                "small_opps_captured": 38,
            }],
            [{
                "total_transactions": 95,
                "unique_arbitrageurs": 50,
                "total_profit": Decimal("600000"),
                "total_gas_spent": Decimal("70000"),
                "avg_profit": Decimal("6316"),
                "median_profit": Decimal("5800"),
                "max_profit": Decimal("60000"),
                "min_profit": Decimal("1500"),
                "p95_profit": Decimal("25000"),
            }],
            [{"captured_by": f"0xAddress{i}"} for i in range(30)],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        # Verify competition level: 50 arbitrageurs / 100 opportunities = 0.5
        call_args = mock_conn.execute.call_args[0]
        avg_competition_level = call_args[18]
        assert avg_competition_level == Decimal("0.5")

    @pytest.mark.asyncio
    async def test_competition_level_low_competition(self, stats_aggregator):
        """Test competition level with low competition (few arbitrageurs per opportunity)"""
        # Mock database query results - 5 arbitrageurs for 100 opportunities
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 100,
                "captured_opportunities": 50,
                "small_opportunities": 25,
                "small_opps_captured": 12,
            }],
            [{
                "total_transactions": 50,
                "unique_arbitrageurs": 5,
                "total_profit": Decimal("300000"),
                "total_gas_spent": Decimal("30000"),
                "avg_profit": Decimal("6000"),
                "median_profit": Decimal("5500"),
                "max_profit": Decimal("40000"),
                "min_profit": Decimal("2000"),
                "p95_profit": Decimal("18000"),
            }],
            [{"captured_by": f"0xAddress{i}"} for i in range(3)],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        # Verify competition level: 5 arbitrageurs / 100 opportunities = 0.05
        call_args = mock_conn.execute.call_args[0]
        avg_competition_level = call_args[18]
        assert avg_competition_level == Decimal("0.05")

    @pytest.mark.asyncio
    async def test_competition_level_no_opportunities(self, stats_aggregator):
        """Test competition level when no opportunities detected"""
        # Mock database query results - no opportunities
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 0,
                "captured_opportunities": 0,
                "small_opportunities": 0,
                "small_opps_captured": 0,
            }],
            [{
                "total_transactions": 0,
                "unique_arbitrageurs": 0,
                "total_profit": Decimal("0"),
                "total_gas_spent": Decimal("0"),
                "avg_profit": None,
                "median_profit": None,
                "max_profit": None,
                "min_profit": None,
                "p95_profit": None,
            }],
            [],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        # Verify competition level is None when no opportunities
        call_args = mock_conn.execute.call_args[0]
        avg_competition_level = call_args[18]
        assert avg_competition_level is None

    @pytest.mark.asyncio
    async def test_competition_level_no_arbitrageurs(self, stats_aggregator):
        """Test competition level when opportunities exist but no arbitrageurs captured them"""
        # Mock database query results - opportunities but no captures
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 100,
                "captured_opportunities": 0,
                "small_opportunities": 30,
                "small_opps_captured": 0,
            }],
            [{
                "total_transactions": 0,
                "unique_arbitrageurs": 0,
                "total_profit": Decimal("0"),
                "total_gas_spent": Decimal("0"),
                "avg_profit": None,
                "median_profit": None,
                "max_profit": None,
                "min_profit": None,
                "p95_profit": None,
            }],
            [],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        # Verify competition level is None when no arbitrageurs
        call_args = mock_conn.execute.call_args[0]
        avg_competition_level = call_args[18]
        assert avg_competition_level is None

    @pytest.mark.asyncio
    async def test_unique_small_opportunity_arbitrageurs_tracking(self, stats_aggregator):
        """Test tracking of unique arbitrageurs for small opportunities (Requirement 11.5)"""
        # Mock database query results - 15 unique arbitrageurs captured small opportunities
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 100,
                "captured_opportunities": 80,
                "small_opportunities": 40,
                "small_opps_captured": 35,
            }],
            [{
                "total_transactions": 80,
                "unique_arbitrageurs": 25,
                "total_profit": Decimal("500000"),
                "total_gas_spent": Decimal("50000"),
                "avg_profit": Decimal("6250"),
                "median_profit": Decimal("5500"),
                "max_profit": Decimal("50000"),
                "min_profit": Decimal("1000"),
                "p95_profit": Decimal("20000"),
            }],
            # 15 unique arbitrageurs captured small opportunities
            [{"captured_by": f"0xSmallTrader{i}"} for i in range(15)],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        # Verify the query for small opportunity arbitrageurs was called
        # Third fetch call should query for unique arbitrageurs who captured small opportunities
        assert mock_conn.fetch.call_count == 3
        small_opp_query_call = mock_conn.fetch.call_args_list[2]
        
        # Verify query filters for small opportunities
        query_sql = small_opp_query_call[0][0]
        assert "captured = true" in query_sql
        assert "profit_usd >=" in query_sql
        assert "profit_usd <=" in query_sql
        assert "captured_by IS NOT NULL" in query_sql


class TestViabilityAnalysisIntegration:
    """Integration tests for small trader viability analysis (Requirement 11.7)"""

    @pytest.mark.asyncio
    async def test_complete_viability_analysis_workflow(self, stats_aggregator):
        """Test complete viability analysis workflow with all metrics"""
        # Mock database query results - realistic scenario
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 200,
                "captured_opportunities": 150,
                "small_opportunities": 80,
                "small_opps_captured": 45,
            }],
            [{
                "total_transactions": 150,
                "unique_arbitrageurs": 35,
                "total_profit": Decimal("1200000"),
                "total_gas_spent": Decimal("120000"),
                "avg_profit": Decimal("8000"),
                "median_profit": Decimal("7000"),
                "max_profit": Decimal("150000"),
                "min_profit": Decimal("2000"),
                "p95_profit": Decimal("50000"),
            }],
            [{"captured_by": f"0xAddress{i}"} for i in range(20)],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        # Verify all viability metrics are calculated
        call_args = mock_conn.execute.call_args[0]
        
        # Overall capture rate: (150 / 200) * 100 = 75%
        capture_rate = call_args[16]
        assert capture_rate == Decimal("75")
        
        # Small opportunity capture rate: (45 / 80) * 100 = 56.25%
        small_opp_capture_rate = call_args[17]
        assert small_opp_capture_rate == Decimal("56.25")
        
        # Competition level: 35 arbitrageurs / 200 opportunities = 0.175
        avg_competition_level = call_args[18]
        assert avg_competition_level == Decimal("0.175")
        
        # Verify small opportunity counts
        small_opportunities_count = call_args[5]
        small_opps_captured = call_args[6]
        assert small_opportunities_count == 80
        assert small_opps_captured == 45

    @pytest.mark.asyncio
    async def test_viability_analysis_favorable_for_small_traders(self, stats_aggregator):
        """Test viability analysis showing favorable conditions for small traders"""
        # Mock database query results - low competition, high capture rate for small opportunities
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 150,
                "captured_opportunities": 100,
                "small_opportunities": 60,
                "small_opps_captured": 50,
            }],
            [{
                "total_transactions": 100,
                "unique_arbitrageurs": 10,
                "total_profit": Decimal("800000"),
                "total_gas_spent": Decimal("80000"),
                "avg_profit": Decimal("8000"),
                "median_profit": Decimal("7500"),
                "max_profit": Decimal("120000"),
                "min_profit": Decimal("3000"),
                "p95_profit": Decimal("40000"),
            }],
            [{"captured_by": f"0xAddress{i}"} for i in range(8)],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        call_args = mock_conn.execute.call_args[0]
        
        # High small opportunity capture rate: (50 / 60) * 100 = 83.33%
        small_opp_capture_rate = call_args[17]
        assert small_opp_capture_rate > Decimal("80")
        
        # Low competition level: 10 arbitrageurs / 150 opportunities = 0.067
        avg_competition_level = call_args[18]
        assert avg_competition_level < Decimal("0.1")

    @pytest.mark.asyncio
    async def test_viability_analysis_unfavorable_for_small_traders(self, stats_aggregator):
        """Test viability analysis showing unfavorable conditions for small traders"""
        # Mock database query results - high competition, low capture rate for small opportunities
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            [{
                "total_opportunities": 150,
                "captured_opportunities": 140,
                "small_opportunities": 60,
                "small_opps_captured": 20,
            }],
            [{
                "total_transactions": 140,
                "unique_arbitrageurs": 80,
                "total_profit": Decimal("1500000"),
                "total_gas_spent": Decimal("200000"),
                "avg_profit": Decimal("10714"),
                "median_profit": Decimal("9500"),
                "max_profit": Decimal("200000"),
                "min_profit": Decimal("5000"),
                "p95_profit": Decimal("80000"),
            }],
            [{"captured_by": f"0xAddress{i}"} for i in range(15)],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_hourly_stats(56, hour_timestamp)
        
        call_args = mock_conn.execute.call_args[0]
        
        # Low small opportunity capture rate: (20 / 60) * 100 = 33.33%
        small_opp_capture_rate = call_args[17]
        assert small_opp_capture_rate < Decimal("40")
        
        # High competition level: 80 arbitrageurs / 150 opportunities = 0.533
        avg_competition_level = call_args[18]
        assert avg_competition_level > Decimal("0.5")

    @pytest.mark.asyncio
    async def test_aggregation_with_multiple_chains(self, stats_aggregator):
        """Test aggregation across multiple chains"""
        # Mock database to return two chains
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(side_effect=[
            # First call: get chains
            [{"chain_id": 56}, {"chain_id": 137}],
            # BSC chain stats
            [{
                "total_opportunities": 100,
                "captured_opportunities": 80,
                "small_opportunities": 40,
                "small_opps_captured": 30,
            }],
            [{
                "total_transactions": 80,
                "unique_arbitrageurs": 20,
                "total_profit": Decimal("500000"),
                "total_gas_spent": Decimal("50000"),
                "avg_profit": Decimal("6250"),
                "median_profit": Decimal("5500"),
                "max_profit": Decimal("50000"),
                "min_profit": Decimal("1000"),
                "p95_profit": Decimal("20000"),
            }],
            [{"captured_by": f"0xAddress{i}"} for i in range(15)],
            # Polygon chain stats
            [{
                "total_opportunities": 150,
                "captured_opportunities": 120,
                "small_opportunities": 60,
                "small_opps_captured": 50,
            }],
            [{
                "total_transactions": 120,
                "unique_arbitrageurs": 30,
                "total_profit": Decimal("700000"),
                "total_gas_spent": Decimal("60000"),
                "avg_profit": Decimal("5833"),
                "median_profit": Decimal("5200"),
                "max_profit": Decimal("60000"),
                "min_profit": Decimal("1500"),
                "p95_profit": Decimal("25000"),
            }],
            [{"captured_by": f"0xAddress{i}"} for i in range(20)],
        ])
        mock_conn.execute = AsyncMock()
        
        stats_aggregator.database_manager.pool.acquire.return_value.__aenter__.return_value = mock_conn
        
        hour_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        await stats_aggregator.aggregate_all_chains(hour_timestamp)
        
        # Verify execute was called twice (once per chain)
        assert mock_conn.execute.call_count == 2
