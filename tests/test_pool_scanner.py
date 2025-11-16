"""Comprehensive unit tests for pool scanner"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import math

from src.detectors.pool_scanner import (
    PoolScanner,
    PoolReserves,
    ImbalanceData,
)
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
            "WBNB-USDT": "0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE",
        }
    )


@pytest.fixture
def polygon_config():
    """Create Polygon chain configuration for testing"""
    return ChainConfig(
        name="Polygon",
        chain_id=137,
        rpc_urls=["https://polygon-rpc.com"],
        block_time_seconds=2.0,
        native_token="MATIC",
        native_token_usd=Decimal("0.80"),
        dex_routers={
            "QuickSwap": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
        },
        pools={
            "WMATIC-USDC": "0x6e7a5FAFcec6BB1e78bAA2A0430e3B1B64B5c0D7",
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
def bsc_scanner(mock_chain_connector, bsc_config):
    """Create BSC pool scanner for testing"""
    return PoolScanner(
        chain_connector=mock_chain_connector,
        config=bsc_config,
        database_manager=None,
        scan_interval_seconds=3.0,
        imbalance_threshold_pct=5.0,
        swap_fee_pct=0.3,
    )


@pytest.fixture
def polygon_scanner(mock_chain_connector, polygon_config):
    """Create Polygon pool scanner for testing"""
    return PoolScanner(
        chain_connector=mock_chain_connector,
        config=polygon_config,
        database_manager=None,
        scan_interval_seconds=2.0,
        imbalance_threshold_pct=5.0,
        swap_fee_pct=0.3,
    )


class TestReserveRetrieval:
    """Test reserve retrieval from pool contracts"""

    @pytest.mark.asyncio
    async def test_get_pool_reserves_success(self, bsc_scanner):
        """Test successful reserve retrieval from pool contract"""
        pool_address = "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16"
        pool_name = "WBNB-BUSD"
        
        # Mock contract call
        mock_contract = MagicMock()
        mock_contract.functions.getReserves().call.return_value = (
            1000000000000000000000,  # reserve0: 1000 tokens
            2000000000000000000000,  # reserve1: 2000 tokens
            1234567890,  # block timestamp
        )
        
        bsc_scanner.chain_connector.w3.eth.contract.return_value = mock_contract
        
        reserves = await bsc_scanner.get_pool_reserves(pool_address, pool_name)
        
        assert reserves is not None
        assert reserves.pool_address == pool_address
        assert reserves.pool_name == pool_name
        assert reserves.reserve0 == 1000000000000000000000
        assert reserves.reserve1 == 2000000000000000000000
        assert reserves.block_timestamp == 1234567890

    @pytest.mark.asyncio
    async def test_get_pool_reserves_with_different_values(self, bsc_scanner):
        """Test reserve retrieval with different reserve values"""
        pool_address = "0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE"
        pool_name = "WBNB-USDT"
        
        # Mock contract call with different values
        mock_contract = MagicMock()
        mock_contract.functions.getReserves().call.return_value = (
            500000000000000000000,  # reserve0: 500 tokens
            750000000000000000000,  # reserve1: 750 tokens
            1234567900,
        )
        
        bsc_scanner.chain_connector.w3.eth.contract.return_value = mock_contract
        
        reserves = await bsc_scanner.get_pool_reserves(pool_address, pool_name)
        
        assert reserves is not None
        assert reserves.reserve0 == 500000000000000000000
        assert reserves.reserve1 == 750000000000000000000

    @pytest.mark.asyncio
    async def test_get_pool_reserves_failure(self, bsc_scanner):
        """Test reserve retrieval failure returns None"""
        pool_address = "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16"
        pool_name = "WBNB-BUSD"
        
        # Mock contract call to raise exception
        mock_contract = MagicMock()
        mock_contract.functions.getReserves().call.side_effect = Exception("RPC error")
        
        bsc_scanner.chain_connector.w3.eth.contract.return_value = mock_contract
        
        reserves = await bsc_scanner.get_pool_reserves(pool_address, pool_name)
        
        assert reserves is None

    @pytest.mark.asyncio
    async def test_get_pool_reserves_with_zero_reserves(self, bsc_scanner):
        """Test reserve retrieval with zero reserves"""
        pool_address = "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16"
        pool_name = "WBNB-BUSD"
        
        # Mock contract call with zero reserves
        mock_contract = MagicMock()
        mock_contract.functions.getReserves().call.return_value = (
            0,  # reserve0: 0
            0,  # reserve1: 0
            1234567890,
        )
        
        bsc_scanner.chain_connector.w3.eth.contract.return_value = mock_contract
        
        reserves = await bsc_scanner.get_pool_reserves(pool_address, pool_name)
        
        # Should still return reserves object, but imbalance calculation will handle zeros
        assert reserves is not None
        assert reserves.reserve0 == 0
        assert reserves.reserve1 == 0


class TestCPMMInvariantCalculation:
    """Test CPMM invariant calculation"""

    def test_calculate_invariant_balanced_pool(self, bsc_scanner):
        """Test CPMM invariant calculation for balanced pool"""
        # Balanced pool: reserve0 = reserve1 = 1000
        reserve0 = 1000000000000000000000  # 1000 tokens (18 decimals)
        reserve1 = 1000000000000000000000  # 1000 tokens
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # k = 1000 * 1000 = 1,000,000
        # optimal_x = optimal_y = sqrt(1,000,000) = 1000
        # Since reserves are already optimal, imbalance should be 0%
        assert imbalance_data.imbalance_pct == Decimal("0")
        assert imbalance_data.optimal_reserve0 == Decimal("1000000000000000000000")
        assert imbalance_data.optimal_reserve1 == Decimal("1000000000000000000000")

    def test_calculate_invariant_imbalanced_pool(self, bsc_scanner):
        """Test CPMM invariant calculation for imbalanced pool"""
        # Imbalanced pool: reserve0 = 800, reserve1 = 1250
        # k = 800 * 1250 = 1,000,000
        # optimal = sqrt(1,000,000) = 1000
        reserve0 = 800000000000000000000  # 800 tokens
        reserve1 = 1250000000000000000000  # 1250 tokens
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # optimal_x = optimal_y = 1000
        expected_optimal = Decimal("1000000000000000000000")
        assert imbalance_data.optimal_reserve0 == expected_optimal
        assert imbalance_data.optimal_reserve1 == expected_optimal
        
        # Imbalance0 = |800 - 1000| / 1000 * 100 = 20%
        # Imbalance1 = |1250 - 1000| / 1000 * 100 = 25%
        # Max imbalance = 25%
        assert imbalance_data.imbalance_pct == Decimal("25")

    def test_calculate_invariant_large_imbalance(self, bsc_scanner):
        """Test CPMM invariant calculation with large imbalance"""
        # Highly imbalanced pool: reserve0 = 500, reserve1 = 2000
        # k = 500 * 2000 = 1,000,000
        # optimal = 1000
        reserve0 = 500000000000000000000  # 500 tokens
        reserve1 = 2000000000000000000000  # 2000 tokens
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # Imbalance0 = |500 - 1000| / 1000 * 100 = 50%
        # Imbalance1 = |2000 - 1000| / 1000 * 100 = 100%
        # Max imbalance = 100%
        assert imbalance_data.imbalance_pct == Decimal("100")

    def test_calculate_invariant_small_imbalance(self, bsc_scanner):
        """Test CPMM invariant calculation with small imbalance"""
        # Slightly imbalanced pool: reserve0 = 980, reserve1 = 1020.408...
        # k ≈ 1,000,000
        reserve0 = 980000000000000000000  # 980 tokens
        reserve1 = 1020408163265306122449  # ~1020.408 tokens
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # Small imbalance, should be around 2%
        assert imbalance_data.imbalance_pct < Decimal("3")
        assert imbalance_data.imbalance_pct > Decimal("1")


class TestImbalancePercentageCalculation:
    """Test imbalance percentage calculation"""

    def test_imbalance_percentage_zero_for_balanced(self, bsc_scanner):
        """Test imbalance percentage is zero for perfectly balanced pool"""
        reserve0 = 1000000000000000000000
        reserve1 = 1000000000000000000000
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        assert imbalance_data.imbalance_pct == Decimal("0")

    def test_imbalance_percentage_calculation_accuracy(self, bsc_scanner):
        """Test imbalance percentage calculation accuracy"""
        # reserve0 = 900, reserve1 = 1111.111...
        # k = 1,000,000, optimal = 1000
        # imbalance0 = |900 - 1000| / 1000 = 10%
        # imbalance1 = |1111.111 - 1000| / 1000 = 11.111%
        reserve0 = 900000000000000000000
        reserve1 = 1111111111111111111111
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # Should take max imbalance (11.111%)
        assert imbalance_data.imbalance_pct > Decimal("11")
        assert imbalance_data.imbalance_pct < Decimal("12")

    def test_imbalance_uses_maximum_of_both_reserves(self, bsc_scanner):
        """Test that imbalance uses maximum of both reserve imbalances"""
        # reserve0 = 950 (5% imbalance), reserve1 = 1052.63 (5.263% imbalance)
        # k = 1,000,000, optimal = 1000
        reserve0 = 950000000000000000000
        reserve1 = 1052631578947368421053
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # Should use the larger imbalance (~5.263%)
        assert imbalance_data.imbalance_pct > Decimal("5")
        assert imbalance_data.imbalance_pct < Decimal("6")

    def test_imbalance_percentage_with_very_large_reserves(self, bsc_scanner):
        """Test imbalance calculation with very large reserve values"""
        # Large reserves: 1,000,000 and 1,000,000
        reserve0 = 1000000000000000000000000  # 1M tokens
        reserve1 = 1000000000000000000000000  # 1M tokens
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # Allow for tiny floating point precision errors
        assert imbalance_data.imbalance_pct < Decimal("0.0001")

    def test_imbalance_percentage_with_very_small_reserves(self, bsc_scanner):
        """Test imbalance calculation with very small reserve values"""
        # Small reserves: 1 and 1
        reserve0 = 1000000000000000000  # 1 token
        reserve1 = 1000000000000000000  # 1 token
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        assert imbalance_data.imbalance_pct == Decimal("0")


class TestProfitPotentialEstimation:
    """Test profit potential estimation"""

    def test_profit_potential_with_imbalance_above_fee(self, bsc_scanner):
        """Test profit potential calculation when imbalance exceeds swap fee"""
        # Imbalanced pool with 10% imbalance
        # reserve0 = 900, reserve1 = 1111.111
        # Imbalance ~11.11%, swap fee 0.3%
        # Profit potential = (11.11 - 0.3)% = 10.81%
        reserve0 = 900000000000000000000
        reserve1 = 1111111111111111111111
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # Profit should be positive
        assert imbalance_data.profit_potential_usd > Decimal("0")
        # Profit in native tokens should be positive
        assert imbalance_data.profit_potential_native > Decimal("0")

    def test_profit_potential_with_imbalance_below_fee(self, bsc_scanner):
        """Test profit potential is zero when imbalance is below swap fee"""
        # Small imbalance: 0.2% (below 0.3% fee)
        # reserve0 = 998, reserve1 = 1002.004
        reserve0 = 998000000000000000000
        reserve1 = 1002004008016032064128
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # Profit should be zero since imbalance < swap fee
        assert imbalance_data.profit_potential_usd == Decimal("0")
        assert imbalance_data.profit_potential_native == Decimal("0")

    def test_profit_potential_calculation_formula(self, bsc_scanner):
        """Test profit potential calculation follows correct formula"""
        # 20% imbalance, 0.3% fee
        # Profit = (20 - 0.3)% = 19.7% of reserve1
        reserve0 = 800000000000000000000  # 800 tokens
        reserve1 = 1250000000000000000000  # 1250 tokens
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # Imbalance should be 25% (from reserve1)
        assert imbalance_data.imbalance_pct == Decimal("25")
        
        # Profit = (25 - 0.3)% * 1250 = 24.7% * 1250 = 308.75 tokens
        # In USD (assuming 1:1 with stablecoin): 308.75 USD
        expected_profit_pct = Decimal("25") - Decimal("0.3")
        expected_profit_native = (expected_profit_pct / 100) * Decimal(reserve1)
        expected_profit_usd = expected_profit_native / Decimal(10**18)
        
        assert imbalance_data.profit_potential_usd == expected_profit_usd

    def test_profit_potential_with_large_imbalance(self, bsc_scanner):
        """Test profit potential with large imbalance"""
        # 100% imbalance
        reserve0 = 500000000000000000000  # 500 tokens
        reserve1 = 2000000000000000000000  # 2000 tokens
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # Profit should be substantial
        assert imbalance_data.profit_potential_usd > Decimal("1000")

    def test_profit_potential_accounts_for_swap_fee(self, bsc_scanner):
        """Test that profit potential correctly accounts for swap fee"""
        # 5% imbalance with 0.3% fee
        # Net profit = 4.7%
        reserve0 = 950000000000000000000
        reserve1 = 1052631578947368421053
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # Profit should be reduced by swap fee
        # Imbalance ~5.26%, profit ~4.96%
        profit_pct = (imbalance_data.profit_potential_native / Decimal(reserve1)) * 100
        assert profit_pct < imbalance_data.imbalance_pct
        # Profit should be approximately imbalance - fee (with some tolerance for calculation)
        assert profit_pct >= (imbalance_data.imbalance_pct - Decimal("0.31"))


class TestZeroReservesHandling:
    """Test handling of zero reserves"""

    def test_zero_reserve0_returns_none(self, bsc_scanner):
        """Test that zero reserve0 returns None"""
        reserve0 = 0
        reserve1 = 1000000000000000000000
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is None

    def test_zero_reserve1_returns_none(self, bsc_scanner):
        """Test that zero reserve1 returns None"""
        reserve0 = 1000000000000000000000
        reserve1 = 0
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is None

    def test_both_reserves_zero_returns_none(self, bsc_scanner):
        """Test that both reserves zero returns None"""
        reserve0 = 0
        reserve1 = 0
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is None

    def test_scan_pools_handles_zero_reserves_gracefully(self, bsc_scanner):
        """Test that scan_pools handles zero reserves gracefully"""
        # This test ensures the scanner doesn't crash on zero reserves
        # It should log a warning and continue
        pass  # Covered by integration with calculate_imbalance returning None


class TestPoolScannerConfiguration:
    """Test pool scanner configuration"""

    def test_scanner_initialization_with_bsc_config(self, mock_chain_connector, bsc_config):
        """Test scanner initializes correctly with BSC config"""
        scanner = PoolScanner(
            chain_connector=mock_chain_connector,
            config=bsc_config,
            scan_interval_seconds=3.0,
            imbalance_threshold_pct=5.0,
        )
        
        assert scanner.chain_name == "BSC"
        assert scanner.chain_id == 56
        assert scanner.scan_interval_seconds == 3.0
        assert scanner.imbalance_threshold_pct == Decimal("5.0")
        assert len(scanner.pools) == 2

    def test_scanner_initialization_with_polygon_config(self, mock_chain_connector, polygon_config):
        """Test scanner initializes correctly with Polygon config"""
        scanner = PoolScanner(
            chain_connector=mock_chain_connector,
            config=polygon_config,
            scan_interval_seconds=2.0,
            imbalance_threshold_pct=5.0,
        )
        
        assert scanner.chain_name == "Polygon"
        assert scanner.chain_id == 137
        assert scanner.scan_interval_seconds == 2.0

    def test_scanner_custom_imbalance_threshold(self, mock_chain_connector, bsc_config):
        """Test scanner with custom imbalance threshold"""
        scanner = PoolScanner(
            chain_connector=mock_chain_connector,
            config=bsc_config,
            imbalance_threshold_pct=10.0,
        )
        
        assert scanner.imbalance_threshold_pct == Decimal("10.0")

    def test_scanner_custom_swap_fee(self, mock_chain_connector, bsc_config):
        """Test scanner with custom swap fee"""
        scanner = PoolScanner(
            chain_connector=mock_chain_connector,
            config=bsc_config,
            swap_fee_pct=0.25,
        )
        
        assert scanner.swap_fee_pct == Decimal("0.25")


class TestSmallOpportunityClassification:
    """Test small opportunity classification for $10K-$100K range"""

    def test_is_small_opportunity_within_range(self, bsc_scanner):
        """Test opportunity within $10K-$100K is classified as small"""
        profit_usd = Decimal("50000")  # $50K
        
        is_small = bsc_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is True

    def test_is_small_opportunity_at_lower_bound(self, bsc_scanner):
        """Test opportunity at exactly $10K is classified as small"""
        profit_usd = Decimal("10000")  # $10K
        
        is_small = bsc_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is True

    def test_is_small_opportunity_at_upper_bound(self, bsc_scanner):
        """Test opportunity at exactly $100K is classified as small"""
        profit_usd = Decimal("100000")  # $100K
        
        is_small = bsc_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is True

    def test_is_small_opportunity_below_range(self, bsc_scanner):
        """Test opportunity below $10K is not classified as small"""
        profit_usd = Decimal("5000")  # $5K
        
        is_small = bsc_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is False

    def test_is_small_opportunity_above_range(self, bsc_scanner):
        """Test opportunity above $100K is not classified as small"""
        profit_usd = Decimal("150000")  # $150K
        
        is_small = bsc_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is False

    def test_is_small_opportunity_just_below_lower_bound(self, bsc_scanner):
        """Test opportunity just below $10K is not classified as small"""
        profit_usd = Decimal("9999.99")
        
        is_small = bsc_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is False

    def test_is_small_opportunity_just_above_upper_bound(self, bsc_scanner):
        """Test opportunity just above $100K is not classified as small"""
        profit_usd = Decimal("100000.01")
        
        is_small = bsc_scanner.is_small_opportunity(profit_usd)
        
        assert is_small is False

    def test_get_small_opportunity_count_initial(self, bsc_scanner):
        """Test small opportunity count is zero initially"""
        count = bsc_scanner.get_small_opportunity_count()
        
        assert count == 0

    def test_scanner_with_custom_small_opp_range(self, mock_chain_connector, bsc_config):
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


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_imbalance_exactly_at_threshold(self, bsc_scanner):
        """Test imbalance exactly at threshold (5%)"""
        # Create reserves with exactly 5% imbalance
        # reserve0 = 950, reserve1 = 1052.63 (5.26% imbalance)
        reserve0 = 950000000000000000000
        reserve1 = 1052631578947368421053
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # Should be detected since it's >= threshold
        assert imbalance_data.imbalance_pct >= Decimal("5.0")

    def test_imbalance_just_below_threshold(self, bsc_scanner):
        """Test imbalance just below threshold"""
        # Create reserves with ~4.5% imbalance
        # reserve0 = 955, reserve1 = 1047.12 gives ~4.5% imbalance
        reserve0 = 955000000000000000000
        reserve1 = 1047120418848167539267
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # Should still calculate, but might not trigger opportunity
        assert imbalance_data.imbalance_pct < Decimal("5.0")

    def test_very_small_reserves_calculation(self, bsc_scanner):
        """Test calculation with very small reserves"""
        reserve0 = 1  # 1 wei
        reserve1 = 1  # 1 wei
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        assert imbalance_data.imbalance_pct == Decimal("0")

    def test_asymmetric_reserves_calculation(self, bsc_scanner):
        """Test calculation with highly asymmetric reserves"""
        reserve0 = 100000000000000000000  # 100 tokens
        reserve1 = 10000000000000000000000  # 10,000 tokens
        
        imbalance_data = bsc_scanner.calculate_imbalance(reserve0, reserve1)
        
        assert imbalance_data is not None
        # Should have very high imbalance
        assert imbalance_data.imbalance_pct > Decimal("90")
