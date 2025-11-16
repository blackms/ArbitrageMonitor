"""Comprehensive unit tests for transaction analyzer swap detection"""

import pytest
from web3 import Web3

from src.detectors.transaction_analyzer import SwapEvent, TransactionAnalyzer


@pytest.fixture
def bsc_analyzer():
    """Create BSC transaction analyzer for testing"""
    dex_routers = {
        "PancakeSwap V2": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
        "PancakeSwap V3": "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
        "BiSwap": "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8",
        "ApeSwap": "0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7",
        "THENA": "0xd4ae6eCA985340Dd434D38F470aCCce4DC78D109",
    }
    return TransactionAnalyzer("BSC", dex_routers)


@pytest.fixture
def polygon_analyzer():
    """Create Polygon transaction analyzer for testing"""
    dex_routers = {
        "QuickSwap": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
        "SushiSwap": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
        "Uniswap V3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        "Balancer": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    }
    return TransactionAnalyzer("Polygon", dex_routers)


class TestSwapEventSignature:
    """Test Swap event signature calculation"""

    def test_swap_event_signature_matches_expected(self, bsc_analyzer):
        """Test that Swap event signature calculation matches expected value"""
        # Expected signature for Swap(address,uint256,uint256,uint256,uint256,address)
        expected_signature = Web3.keccak(
            text="Swap(address,uint256,uint256,uint256,uint256,address)"
        ).hex()
        
        assert bsc_analyzer.SWAP_EVENT_SIGNATURE == expected_signature
        assert bsc_analyzer.SWAP_EVENT_SIGNATURE.startswith("0x")
        assert len(bsc_analyzer.SWAP_EVENT_SIGNATURE) == 66  # 0x + 64 hex chars


    def test_swap_signature_consistent_across_analyzers(self, bsc_analyzer, polygon_analyzer):
        """Test that Swap signature is consistent across different chain analyzers"""
        assert bsc_analyzer.SWAP_EVENT_SIGNATURE == polygon_analyzer.SWAP_EVENT_SIGNATURE


class TestCountSwapEvents:
    """Test counting Swap events with proper signature filtering"""

    def test_count_swap_events_with_multiple_event_types(self, bsc_analyzer):
        """Test count_swap_events with transaction containing multiple event types (should count only Swaps)"""
        # Create mock receipt with multiple event types
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        transfer_signature = Web3.keccak(text="Transfer(address,address,uint256)").hex()
        sync_signature = Web3.keccak(text="Sync(uint112,uint112)").hex()
        approval_signature = Web3.keccak(text="Approval(address,address,uint256)").hex()
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [transfer_signature], "data": "0x"},  # Transfer event
                {"topics": [swap_signature], "data": "0x"},      # Swap event #1
                {"topics": [sync_signature], "data": "0x"},      # Sync event
                {"topics": [swap_signature], "data": "0x"},      # Swap event #2
                {"topics": [approval_signature], "data": "0x"},  # Approval event
                {"topics": [swap_signature], "data": "0x"},      # Swap event #3
                {"topics": [transfer_signature], "data": "0x"},  # Transfer event
            ]
        }
        
        swap_count = bsc_analyzer.count_swap_events(receipt)
        
        # Should count only the 3 Swap events, not Transfer, Sync, or Approval
        assert swap_count == 3

    def test_count_swap_events_with_no_swaps(self, bsc_analyzer):
        """Test count_swap_events returns 0 when no Swap events present"""
        transfer_signature = Web3.keccak(text="Transfer(address,address,uint256)").hex()
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [transfer_signature], "data": "0x"},
                {"topics": [transfer_signature], "data": "0x"},
            ]
        }
        
        swap_count = bsc_analyzer.count_swap_events(receipt)
        assert swap_count == 0

    def test_count_swap_events_with_only_swaps(self, bsc_analyzer):
        """Test count_swap_events with transaction containing only Swap events"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        swap_count = bsc_analyzer.count_swap_events(receipt)
        assert swap_count == 4

    def test_count_swap_events_with_empty_logs(self, bsc_analyzer):
        """Test count_swap_events with empty logs array"""
        receipt = {
            "transactionHash": "0x123",
            "logs": []
        }
        
        swap_count = bsc_analyzer.count_swap_events(receipt)
        assert swap_count == 0

    def test_count_swap_events_with_bytes_topics(self, bsc_analyzer):
        """Test count_swap_events handles topics as bytes"""
        swap_signature_bytes = Web3.keccak(text="Swap(address,uint256,uint256,uint256,uint256,address)")
        
        receipt = {
            "transactionHash": b"\x12\x34",
            "logs": [
                {"topics": [swap_signature_bytes], "data": "0x"},
                {"topics": [swap_signature_bytes], "data": "0x"},
            ]
        }
        
        swap_count = bsc_analyzer.count_swap_events(receipt)
        assert swap_count == 2


class TestArbitrageClassification:
    """Test arbitrage classification logic"""

    def test_single_swap_not_arbitrage(self, bsc_analyzer):
        """Test single swap transaction is NOT classified as arbitrage"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap_router = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},  # Only 1 swap
            ]
        }
        
        transaction = {
            "to": pancakeswap_router,
            "input": "0x38ed1739" + "0" * 200,  # swapExactTokensForTokens method
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        
        # Single swap should NOT be classified as arbitrage
        assert is_arb is False


    def test_multi_hop_is_arbitrage(self, bsc_analyzer):
        """Test multi-hop transaction (2+ swaps) IS classified as arbitrage"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap_router = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},  # Swap 1
                {"topics": [swap_signature], "data": "0x"},  # Swap 2
            ]
        }
        
        transaction = {
            "to": pancakeswap_router,
            "input": "0x38ed1739" + "0" * 200,  # swapExactTokensForTokens method
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        
        # 2 swaps should be classified as arbitrage
        assert is_arb is True

    def test_three_hop_is_arbitrage(self, bsc_analyzer):
        """Test 3-hop transaction IS classified as arbitrage"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap_router = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},  # Swap 1
                {"topics": [swap_signature], "data": "0x"},  # Swap 2
                {"topics": [swap_signature], "data": "0x"},  # Swap 3
            ]
        }
        
        transaction = {
            "to": pancakeswap_router,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_four_hop_is_arbitrage(self, bsc_analyzer):
        """Test 4-hop transaction IS classified as arbitrage"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap_router = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap_router,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_zero_swaps_not_arbitrage(self, bsc_analyzer):
        """Test transaction with zero swaps is NOT arbitrage"""
        pancakeswap_router = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": []
        }
        
        transaction = {
            "to": pancakeswap_router,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is False


class TestDEXRouterValidation:
    """Test DEX router address validation"""

    def test_known_pancakeswap_v2_router(self, bsc_analyzer):
        """Test PancakeSwap V2 router is recognized"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap_v2 = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap_v2,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_known_pancakeswap_v3_router(self, bsc_analyzer):
        """Test PancakeSwap V3 router is recognized"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap_v3 = "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap_v3,
            "input": "0xc04b8d59" + "0" * 200,  # exactInput for V3
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True


    def test_known_biswap_router(self, bsc_analyzer):
        """Test BiSwap router is recognized"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        biswap = "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": biswap,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_known_apeswap_router(self, bsc_analyzer):
        """Test ApeSwap router is recognized"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        apeswap = "0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": apeswap,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_known_thena_router(self, bsc_analyzer):
        """Test THENA router is recognized"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        thena = "0xd4ae6eCA985340Dd434D38F470aCCce4DC78D109"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": thena,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_unknown_router_not_arbitrage(self, bsc_analyzer):
        """Test transaction to unknown router is NOT classified as arbitrage"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        unknown_router = "0x0000000000000000000000000000000000000000"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": unknown_router,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is False

    def test_polygon_quickswap_router(self, polygon_analyzer):
        """Test QuickSwap router is recognized on Polygon"""
        swap_signature = polygon_analyzer.SWAP_EVENT_SIGNATURE
        quickswap = "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": quickswap,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = polygon_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_polygon_sushiswap_router(self, polygon_analyzer):
        """Test SushiSwap router is recognized on Polygon"""
        swap_signature = polygon_analyzer.SWAP_EVENT_SIGNATURE
        sushiswap = "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": sushiswap,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = polygon_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True


    def test_polygon_uniswap_v3_router(self, polygon_analyzer):
        """Test Uniswap V3 router is recognized on Polygon"""
        swap_signature = polygon_analyzer.SWAP_EVENT_SIGNATURE
        uniswap_v3 = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": uniswap_v3,
            "input": "0xc04b8d59" + "0" * 200,  # exactInput
        }
        
        is_arb = polygon_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_polygon_balancer_router(self, polygon_analyzer):
        """Test Balancer router is recognized on Polygon"""
        swap_signature = polygon_analyzer.SWAP_EVENT_SIGNATURE
        balancer = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": balancer,
            "input": "0x472b43f3" + "0" * 200,  # swapExactAmountIn
        }
        
        is_arb = polygon_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_router_address_case_insensitive(self, bsc_analyzer):
        """Test router validation is case-insensitive"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        # Use lowercase version of PancakeSwap router
        pancakeswap_lower = "0x10ed43c718714eb63d5aa57b78b54704e256024e"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap_lower,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True


class TestSwapMethodSignatureRecognition:
    """Test swap method signature recognition"""

    def test_swap_exact_tokens_for_tokens(self, bsc_analyzer):
        """Test swapExactTokensForTokens method is recognized"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap,
            "input": "0x38ed1739" + "0" * 200,  # swapExactTokensForTokens
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_swap_tokens_for_exact_tokens(self, bsc_analyzer):
        """Test swapTokensForExactTokens method is recognized"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap,
            "input": "0x8803dbee" + "0" * 200,  # swapTokensForExactTokens
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_swap_exact_eth_for_tokens(self, bsc_analyzer):
        """Test swapExactETHForTokens method is recognized"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap,
            "input": "0x7ff36ab5" + "0" * 200,  # swapExactETHForTokens
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True


    def test_swap_exact_tokens_for_eth(self, bsc_analyzer):
        """Test swapExactTokensForETH method is recognized"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap,
            "input": "0x18cbafe5" + "0" * 200,  # swapExactTokensForETH
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_swap_supporting_fee_on_transfer(self, bsc_analyzer):
        """Test swapExactTokensForTokensSupportingFeeOnTransferTokens is recognized"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap,
            "input": "0x5c11d795" + "0" * 200,  # swapExactTokensForTokensSupportingFeeOnTransferTokens
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_uniswap_v3_exact_input(self, bsc_analyzer):
        """Test Uniswap V3 exactInput method is recognized"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap_v3 = "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap_v3,
            "input": "0xc04b8d59" + "0" * 200,  # exactInput
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_uniswap_v3_exact_input_single(self, bsc_analyzer):
        """Test Uniswap V3 exactInputSingle method is recognized"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap_v3 = "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap_v3,
            "input": "0x09b81346" + "0" * 200,  # exactInputSingle
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_balancer_swap_exact_amount_in(self, polygon_analyzer):
        """Test Balancer swapExactAmountIn method is recognized"""
        swap_signature = polygon_analyzer.SWAP_EVENT_SIGNATURE
        balancer = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": balancer,
            "input": "0x472b43f3" + "0" * 200,  # swapExactAmountIn
        }
        
        is_arb = polygon_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_unknown_method_signature_not_arbitrage(self, bsc_analyzer):
        """Test transaction with unknown method signature is NOT arbitrage"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap,
            "input": "0x12345678" + "0" * 200,  # Unknown method
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is False

    def test_no_method_signature_not_arbitrage(self, bsc_analyzer):
        """Test transaction with no method signature is NOT arbitrage"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap,
            "input": "0x123",  # Too short for method signature
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is False

    def test_empty_input_not_arbitrage(self, bsc_analyzer):
        """Test transaction with empty input is NOT arbitrage"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap,
            "input": "",
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is False


class TestCompleteArbitrageDetection:
    """Test complete arbitrage detection with all criteria"""

    def test_valid_arbitrage_all_criteria_met(self, bsc_analyzer):
        """Test valid arbitrage with all criteria met"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is True

    def test_fails_on_insufficient_swaps(self, bsc_analyzer):
        """Test fails when swap count < 2"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},  # Only 1 swap
            ]
        }
        
        transaction = {
            "to": pancakeswap,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is False

    def test_fails_on_unknown_router(self, bsc_analyzer):
        """Test fails when router is unknown"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        unknown_router = "0x9999999999999999999999999999999999999999"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": unknown_router,
            "input": "0x38ed1739" + "0" * 200,
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is False

    def test_fails_on_unknown_method(self, bsc_analyzer):
        """Test fails when method signature is unknown"""
        swap_signature = bsc_analyzer.SWAP_EVENT_SIGNATURE
        pancakeswap = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
        
        receipt = {
            "transactionHash": "0x123",
            "logs": [
                {"topics": [swap_signature], "data": "0x"},
                {"topics": [swap_signature], "data": "0x"},
            ]
        }
        
        transaction = {
            "to": pancakeswap,
            "input": "0xabcdef12" + "0" * 200,  # Unknown method
        }
        
        is_arb = bsc_analyzer.is_arbitrage(receipt, transaction)
        assert is_arb is False
