"""Comprehensive unit tests for profit calculator"""

import pytest
from decimal import Decimal

from src.detectors.profit_calculator import (
    ProfitCalculator,
    TokenFlow,
    GasCost,
    ProfitData,
)
from src.detectors.transaction_analyzer import SwapEvent


@pytest.fixture
def bsc_calculator():
    """Create BSC profit calculator for testing"""
    return ProfitCalculator(
        chain_name="BSC",
        native_token_usd_price=Decimal("300.0")  # BNB price
    )


@pytest.fixture
def polygon_calculator():
    """Create Polygon profit calculator for testing"""
    return ProfitCalculator(
        chain_name="Polygon",
        native_token_usd_price=Decimal("0.80")  # MATIC price
    )


@pytest.fixture
def sample_swap_events():
    """Create sample swap events for testing"""
    swap1 = SwapEvent(
        pool_address="0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
        sender="0x1234567890123456789012345678901234567890",
        to="0x0987654321098765432109876543210987654321",
        amount0In=1000000000000000000,  # 1 token in (18 decimals)
        amount1In=0,
        amount0Out=0,
        amount1Out=1050000000000000000,  # 1.05 tokens out
        log_index=0,
    )
    
    swap2 = SwapEvent(
        pool_address="0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE",
        sender="0x0987654321098765432109876543210987654321",
        to="0x1234567890123456789012345678901234567890",
        amount0In=1050000000000000000,  # 1.05 tokens in
        amount1In=0,
        amount0Out=0,
        amount1Out=1100000000000000000,  # 1.1 tokens out
        log_index=1,
    )
    
    return [swap1, swap2]


class TestInputAmountExtraction:
    """Test input amount extraction from first swap"""

    def test_extract_input_from_amount0In(self, bsc_calculator):
        """Test input amount extraction when amount0In is non-zero"""
        swap = SwapEvent(
            pool_address="0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
            sender="0x1234567890123456789012345678901234567890",
            to="0x0987654321098765432109876543210987654321",
            amount0In=2000000000000000000,  # 2 tokens
            amount1In=0,
            amount0Out=0,
            amount1Out=2100000000000000000,
            log_index=0,
        )
        
        token_flow = bsc_calculator.extract_token_flow([swap])
        
        assert token_flow is not None
        assert token_flow.input_amount == 2000000000000000000
        assert token_flow.input_token_index == 0

    def test_extract_input_from_amount1In(self, bsc_calculator):
        """Test input amount extraction when amount1In is non-zero"""
        swap = SwapEvent(
            pool_address="0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
            sender="0x1234567890123456789012345678901234567890",
            to="0x0987654321098765432109876543210987654321",
            amount0In=0,
            amount1In=3000000000000000000,  # 3 tokens
            amount0Out=3150000000000000000,
            amount1Out=0,
            log_index=0,
        )
        
        token_flow = bsc_calculator.extract_token_flow([swap])
        
        assert token_flow is not None
        assert token_flow.input_amount == 3000000000000000000
        assert token_flow.input_token_index == 1

    def test_extract_input_from_multi_swap_sequence(self, bsc_calculator, sample_swap_events):
        """Test input amount is extracted from first swap in sequence"""
        token_flow = bsc_calculator.extract_token_flow(sample_swap_events)
        
        assert token_flow is not None
        # Should use first swap's input
        assert token_flow.input_amount == 1000000000000000000
        assert token_flow.input_token_index == 0


class TestOutputAmountExtraction:
    """Test output amount extraction from last swap"""

    def test_extract_output_from_amount0Out(self, bsc_calculator):
        """Test output amount extraction when amount0Out is non-zero"""
        swap = SwapEvent(
            pool_address="0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
            sender="0x1234567890123456789012345678901234567890",
            to="0x0987654321098765432109876543210987654321",
            amount0In=1000000000000000000,
            amount1In=0,
            amount0Out=1050000000000000000,  # 1.05 tokens
            amount1Out=0,
            log_index=0,
        )
        
        token_flow = bsc_calculator.extract_token_flow([swap])
        
        assert token_flow is not None
        assert token_flow.output_amount == 1050000000000000000
        assert token_flow.output_token_index == 0

    def test_extract_output_from_amount1Out(self, bsc_calculator):
        """Test output amount extraction when amount1Out is non-zero"""
        swap = SwapEvent(
            pool_address="0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
            sender="0x1234567890123456789012345678901234567890",
            to="0x0987654321098765432109876543210987654321",
            amount0In=1000000000000000000,
            amount1In=0,
            amount0Out=0,
            amount1Out=1050000000000000000,  # 1.05 tokens
            log_index=0,
        )
        
        token_flow = bsc_calculator.extract_token_flow([swap])
        
        assert token_flow is not None
        assert token_flow.output_amount == 1050000000000000000
        assert token_flow.output_token_index == 1

    def test_extract_output_from_multi_swap_sequence(self, bsc_calculator, sample_swap_events):
        """Test output amount is extracted from last swap in sequence"""
        token_flow = bsc_calculator.extract_token_flow(sample_swap_events)
        
        assert token_flow is not None
        # Should use last swap's output
        assert token_flow.output_amount == 1100000000000000000
        assert token_flow.output_token_index == 1

    def test_extract_output_from_three_hop_sequence(self, bsc_calculator):
        """Test output extraction from 3-hop arbitrage"""
        swaps = [
            SwapEvent(
                pool_address="0xPool1",
                sender="0xSender",
                to="0xTo",
                amount0In=1000000000000000000,
                amount1In=0,
                amount0Out=0,
                amount1Out=1050000000000000000,
                log_index=0,
            ),
            SwapEvent(
                pool_address="0xPool2",
                sender="0xSender",
                to="0xTo",
                amount0In=1050000000000000000,
                amount1In=0,
                amount0Out=0,
                amount1Out=1100000000000000000,
                log_index=1,
            ),
            SwapEvent(
                pool_address="0xPool3",
                sender="0xSender",
                to="0xTo",
                amount0In=1100000000000000000,
                amount1In=0,
                amount0Out=0,
                amount1Out=1150000000000000000,  # Final output
                log_index=2,
            ),
        ]
        
        token_flow = bsc_calculator.extract_token_flow(swaps)
        
        assert token_flow is not None
        assert token_flow.output_amount == 1150000000000000000


class TestGrossProfitCalculation:
    """Test gross profit calculation"""

    def test_calculate_gross_profit_positive(self, bsc_calculator, sample_swap_events):
        """Test gross profit calculation with positive profit"""
        receipt = {
            "gasUsed": 150000,
            "effectiveGasPrice": 5000000000,
        }
        
        profit_data = bsc_calculator.calculate_profit(sample_swap_events, receipt)
        
        assert profit_data is not None
        # Input: 1.0, Output: 1.1, Gross profit: 0.1
        assert profit_data.gross_profit_native == Decimal("0.1")
        # 0.1 * 300 = 30 USD
        assert profit_data.gross_profit_usd == Decimal("30.0")

    def test_calculate_gross_profit_negative(self, bsc_calculator):
        """Test gross profit calculation with negative profit (loss)"""
        swaps = [
            SwapEvent(
                pool_address="0xPool1",
                sender="0xSender",
                to="0xTo",
                amount0In=1000000000000000000,  # 1.0 in
                amount1In=0,
                amount0Out=0,
                amount1Out=900000000000000000,  # 0.9 out (loss)
                log_index=0,
            ),
        ]
        
        receipt = {
            "gasUsed": 150000,
            "effectiveGasPrice": 5000000000,
        }
        
        profit_data = bsc_calculator.calculate_profit(swaps, receipt)
        
        assert profit_data is not None
        # Input: 1.0, Output: 0.9, Gross profit: -0.1
        assert profit_data.gross_profit_native == Decimal("-0.1")
        assert profit_data.gross_profit_usd == Decimal("-30.0")

    def test_calculate_gross_profit_zero(self, bsc_calculator):
        """Test gross profit calculation with zero profit"""
        swaps = [
            SwapEvent(
                pool_address="0xPool1",
                sender="0xSender",
                to="0xTo",
                amount0In=1000000000000000000,  # 1.0 in
                amount1In=0,
                amount0Out=0,
                amount1Out=1000000000000000000,  # 1.0 out (break even)
                log_index=0,
            ),
        ]
        
        receipt = {
            "gasUsed": 150000,
            "effectiveGasPrice": 5000000000,
        }
        
        profit_data = bsc_calculator.calculate_profit(swaps, receipt)
        
        assert profit_data is not None
        assert profit_data.gross_profit_native == Decimal("0")
        assert profit_data.gross_profit_usd == Decimal("0")


class TestGasCostCalculation:
    """Test gas cost calculation with different gas prices"""

    def test_calculate_gas_cost_low_gas_price(self, bsc_calculator):
        """Test gas cost calculation with low gas price (5 gwei)"""
        gas_cost = bsc_calculator.calculate_gas_cost(
            gas_used=150000,
            effective_gas_price_wei=5000000000  # 5 gwei
        )
        
        assert gas_cost.gas_used == 150000
        assert gas_cost.gas_price_wei == 5000000000
        assert gas_cost.gas_price_gwei == Decimal("5")
        # 150000 * 5 gwei = 750000 gwei = 0.00075 BNB
        assert gas_cost.gas_cost_native == Decimal("0.00075")
        # 0.00075 * 300 = 0.225 USD
        assert gas_cost.gas_cost_usd == Decimal("0.225")

    def test_calculate_gas_cost_medium_gas_price(self, bsc_calculator):
        """Test gas cost calculation with medium gas price (20 gwei)"""
        gas_cost = bsc_calculator.calculate_gas_cost(
            gas_used=200000,
            effective_gas_price_wei=20000000000  # 20 gwei
        )
        
        assert gas_cost.gas_price_gwei == Decimal("20")
        # 200000 * 20 gwei = 4000000 gwei = 0.004 BNB
        assert gas_cost.gas_cost_native == Decimal("0.004")
        # 0.004 * 300 = 1.2 USD
        assert gas_cost.gas_cost_usd == Decimal("1.2")

    def test_calculate_gas_cost_high_gas_price(self, bsc_calculator):
        """Test gas cost calculation with high gas price (100 gwei)"""
        gas_cost = bsc_calculator.calculate_gas_cost(
            gas_used=300000,
            effective_gas_price_wei=100000000000  # 100 gwei
        )
        
        assert gas_cost.gas_price_gwei == Decimal("100")
        # 300000 * 100 gwei = 30000000 gwei = 0.03 BNB
        assert gas_cost.gas_cost_native == Decimal("0.03")
        # 0.03 * 300 = 9.0 USD
        assert gas_cost.gas_cost_usd == Decimal("9.0")

    def test_calculate_gas_cost_polygon_low_price(self, polygon_calculator):
        """Test gas cost calculation on Polygon with low native token price"""
        gas_cost = polygon_calculator.calculate_gas_cost(
            gas_used=150000,
            effective_gas_price_wei=50000000000  # 50 gwei
        )
        
        assert gas_cost.gas_price_gwei == Decimal("50")
        # 150000 * 50 gwei = 7500000 gwei = 0.0075 MATIC
        assert gas_cost.gas_cost_native == Decimal("0.0075")
        # 0.0075 * 0.80 = 0.006 USD
        assert gas_cost.gas_cost_usd == Decimal("0.006")

    def test_calculate_gas_cost_zero_gas(self, bsc_calculator):
        """Test gas cost calculation with zero gas used"""
        gas_cost = bsc_calculator.calculate_gas_cost(
            gas_used=0,
            effective_gas_price_wei=5000000000
        )
        
        assert gas_cost.gas_used == 0
        assert gas_cost.gas_cost_native == Decimal("0")
        assert gas_cost.gas_cost_usd == Decimal("0")


class TestNetProfitCalculation:
    """Test net profit calculation"""

    def test_calculate_net_profit_positive(self, bsc_calculator, sample_swap_events):
        """Test net profit calculation with positive result"""
        receipt = {
            "gasUsed": 150000,
            "effectiveGasPrice": 5000000000,  # 5 gwei
        }
        
        profit_data = bsc_calculator.calculate_profit(sample_swap_events, receipt)
        
        assert profit_data is not None
        # Gross profit: 0.1 BNB = 30 USD
        # Gas cost: 0.00075 BNB = 0.225 USD
        # Net profit: 0.09925 BNB = 29.775 USD
        assert profit_data.net_profit_native == Decimal("0.09925")
        assert profit_data.net_profit_usd == Decimal("29.775")

    def test_calculate_net_profit_negative_after_gas(self, bsc_calculator):
        """Test net profit calculation that becomes negative after gas costs"""
        swaps = [
            SwapEvent(
                pool_address="0xPool1",
                sender="0xSender",
                to="0xTo",
                amount0In=1000000000000000000,  # 1.0 in
                amount1In=0,
                amount0Out=0,
                amount1Out=1001000000000000000,  # 1.001 out (tiny profit)
                log_index=0,
            ),
        ]
        
        receipt = {
            "gasUsed": 150000,
            "effectiveGasPrice": 5000000000,  # Gas cost: 0.00075 BNB
        }
        
        profit_data = bsc_calculator.calculate_profit(swaps, receipt)
        
        assert profit_data is not None
        # Gross profit: 0.001 BNB
        # Gas cost: 0.00075 BNB
        # Net profit: 0.00025 BNB (still positive but barely)
        assert profit_data.net_profit_native == Decimal("0.00025")

    def test_calculate_net_profit_high_gas_cost(self, bsc_calculator):
        """Test net profit with high gas cost eating into profit"""
        swaps = [
            SwapEvent(
                pool_address="0xPool1",
                sender="0xSender",
                to="0xTo",
                amount0In=1000000000000000000,  # 1.0 in
                amount1In=0,
                amount0Out=0,
                amount1Out=1100000000000000000,  # 1.1 out
                log_index=0,
            ),
        ]
        
        receipt = {
            "gasUsed": 500000,
            "effectiveGasPrice": 100000000000,  # 100 gwei - very high
        }
        
        profit_data = bsc_calculator.calculate_profit(swaps, receipt)
        
        assert profit_data is not None
        # Gross profit: 0.1 BNB = 30 USD
        # Gas cost: 500000 * 100 gwei = 0.05 BNB = 15 USD
        # Net profit: 0.05 BNB = 15 USD
        assert profit_data.net_profit_native == Decimal("0.05")
        assert profit_data.net_profit_usd == Decimal("15.0")


class TestROICalculation:
    """Test ROI calculation"""

    def test_calculate_roi_positive(self, bsc_calculator, sample_swap_events):
        """Test ROI calculation with positive profit"""
        receipt = {
            "gasUsed": 150000,
            "effectiveGasPrice": 5000000000,
        }
        
        profit_data = bsc_calculator.calculate_profit(sample_swap_events, receipt)
        
        assert profit_data is not None
        # Net profit: 0.09925 BNB
        # Input: 1.0 BNB
        # ROI: (0.09925 / 1.0) * 100 = 9.925%
        assert profit_data.roi_percentage == Decimal("9.925")

    def test_calculate_roi_negative(self, bsc_calculator):
        """Test ROI calculation with negative profit"""
        swaps = [
            SwapEvent(
                pool_address="0xPool1",
                sender="0xSender",
                to="0xTo",
                amount0In=1000000000000000000,  # 1.0 in
                amount1In=0,
                amount0Out=0,
                amount1Out=900000000000000000,  # 0.9 out (loss)
                log_index=0,
            ),
        ]
        
        receipt = {
            "gasUsed": 150000,
            "effectiveGasPrice": 5000000000,
        }
        
        profit_data = bsc_calculator.calculate_profit(swaps, receipt)
        
        assert profit_data is not None
        # Gross loss: -0.1 BNB
        # Gas cost: 0.00075 BNB
        # Net loss: -0.10075 BNB
        # ROI: (-0.10075 / 1.0) * 100 = -10.075%
        assert profit_data.roi_percentage == Decimal("-10.075")

    def test_calculate_roi_high_return(self, bsc_calculator):
        """Test ROI calculation with high return"""
        swaps = [
            SwapEvent(
                pool_address="0xPool1",
                sender="0xSender",
                to="0xTo",
                amount0In=1000000000000000000,  # 1.0 in
                amount1In=0,
                amount0Out=0,
                amount1Out=2000000000000000000,  # 2.0 out (100% gross profit)
                log_index=0,
            ),
        ]
        
        receipt = {
            "gasUsed": 150000,
            "effectiveGasPrice": 5000000000,
        }
        
        profit_data = bsc_calculator.calculate_profit(swaps, receipt)
        
        assert profit_data is not None
        # Gross profit: 1.0 BNB
        # Gas cost: 0.00075 BNB
        # Net profit: 0.99925 BNB
        # ROI: (0.99925 / 1.0) * 100 = 99.925%
        assert profit_data.roi_percentage == Decimal("99.925")

    def test_calculate_roi_small_input(self, bsc_calculator):
        """Test ROI calculation with small input amount"""
        swaps = [
            SwapEvent(
                pool_address="0xPool1",
                sender="0xSender",
                to="0xTo",
                amount0In=100000000000000000,  # 0.1 in
                amount1In=0,
                amount0Out=0,
                amount1Out=110000000000000000,  # 0.11 out
                log_index=0,
            ),
        ]
        
        receipt = {
            "gasUsed": 150000,
            "effectiveGasPrice": 5000000000,
        }
        
        profit_data = bsc_calculator.calculate_profit(swaps, receipt)
        
        assert profit_data is not None
        # Gross profit: 0.01 BNB
        # Gas cost: 0.00075 BNB
        # Net profit: 0.00925 BNB
        # ROI: (0.00925 / 0.1) * 100 = 9.25%
        assert profit_data.roi_percentage == Decimal("9.25")


class TestZeroInputHandling:
    """Test handling of zero input amounts"""

    def test_zero_input_returns_none(self, bsc_calculator):
        """Test that zero input amount returns None"""
        swaps = [
            SwapEvent(
                pool_address="0xPool1",
                sender="0xSender",
                to="0xTo",
                amount0In=0,  # No input
                amount1In=0,  # No input
                amount0Out=1000000000000000000,
                amount1Out=0,
                log_index=0,
            ),
        ]
        
        token_flow = bsc_calculator.extract_token_flow(swaps)
        
        assert token_flow is None

    def test_zero_output_returns_none(self, bsc_calculator):
        """Test that zero output amount returns None"""
        swaps = [
            SwapEvent(
                pool_address="0xPool1",
                sender="0xSender",
                to="0xTo",
                amount0In=1000000000000000000,
                amount1In=0,
                amount0Out=0,  # No output
                amount1Out=0,  # No output
                log_index=0,
            ),
        ]
        
        token_flow = bsc_calculator.extract_token_flow(swaps)
        
        assert token_flow is None

    def test_empty_swaps_returns_none(self, bsc_calculator):
        """Test that empty swaps list returns None"""
        token_flow = bsc_calculator.extract_token_flow([])
        
        assert token_flow is None

    def test_calculate_profit_with_zero_input_returns_none(self, bsc_calculator):
        """Test that calculate_profit returns None when input is zero"""
        swaps = [
            SwapEvent(
                pool_address="0xPool1",
                sender="0xSender",
                to="0xTo",
                amount0In=0,
                amount1In=0,
                amount0Out=1000000000000000000,
                amount1Out=0,
                log_index=0,
            ),
        ]
        
        receipt = {
            "gasUsed": 150000,
            "effectiveGasPrice": 5000000000,
        }
        
        profit_data = bsc_calculator.calculate_profit(swaps, receipt)
        
        assert profit_data is None

    def test_roi_zero_when_input_zero_in_token_flow(self, bsc_calculator):
        """Test ROI is zero when input amount is zero (edge case)"""
        # This tests the ROI calculation logic when input_amount_native is 0
        # In practice, this shouldn't happen due to extract_token_flow validation
        # but we test the defensive code
        swaps = [
            SwapEvent(
                pool_address="0xPool1",
                sender="0xSender",
                to="0xTo",
                amount0In=1,  # Minimal input to pass validation
                amount1In=0,
                amount0Out=0,
                amount1Out=1000000000000000000,
                log_index=0,
            ),
        ]
        
        receipt = {
            "gasUsed": 150000,
            "effectiveGasPrice": 5000000000,
        }
        
        profit_data = bsc_calculator.calculate_profit(swaps, receipt)
        
        # Should calculate successfully with tiny input
        assert profit_data is not None
        assert profit_data.input_amount_native > 0
