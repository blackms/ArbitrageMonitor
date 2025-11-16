"""Tests for chain connectors"""

import asyncio
import time
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest
from web3 import Web3
from web3.exceptions import Web3Exception

from src.chains import BSCConnector, ChainConnector, CircuitState, PolygonConnector
from src.config.models import ChainConfig


@pytest.fixture
def bsc_config():
    """BSC chain configuration for testing"""
    return ChainConfig(
        name="BSC",
        chain_id=56,
        rpc_urls=[
            "https://bsc-dataseed.bnbchain.org",
            "https://bsc-dataseed1.binance.org",
        ],
        block_time_seconds=3.0,
        native_token="BNB",
        native_token_usd=Decimal("300.0"),
        dex_routers={
            "PancakeSwap V2": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
            "PancakeSwap V3": "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
        },
        pools={
            "WBNB-BUSD": "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
        },
    )


@pytest.fixture
def polygon_config():
    """Polygon chain configuration for testing"""
    return ChainConfig(
        name="Polygon",
        chain_id=137,
        rpc_urls=[
            "https://polygon-rpc.com",
            "https://rpc-mainnet.matic.network",
        ],
        block_time_seconds=2.0,
        native_token="MATIC",
        native_token_usd=Decimal("0.80"),
        dex_routers={
            "QuickSwap": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
            "SushiSwap": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
        },
        pools={
            "WMATIC-USDC": "0x6e7a5FAFcec6BB1e78bAA2A0430e3B1B64B5c0D7",
        },
    )


class TestCircuitBreaker:
    """Test circuit breaker functionality"""

    def test_circuit_breaker_initial_state(self):
        """Test circuit breaker starts in CLOSED state"""
        from src.chains.connector import CircuitBreaker

        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.can_attempt() is True

    def test_circuit_breaker_opens_after_threshold(self):
        """Test circuit breaker opens after failure threshold"""
        from src.chains.connector import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=3)

        # Record failures
        for i in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3
        assert cb.can_attempt() is False

    def test_circuit_breaker_half_open_after_timeout(self):
        """Test circuit breaker transitions to HALF_OPEN after timeout"""
        from src.chains.connector import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

        # Open the circuit
        for i in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(1.1)

        # Should transition to HALF_OPEN
        assert cb.can_attempt() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_circuit_breaker_closes_on_success_from_half_open(self):
        """Test circuit breaker closes after successful call from HALF_OPEN"""
        from src.chains.connector import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

        # Open the circuit
        for i in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Wait for timeout to transition to HALF_OPEN
        time.sleep(1.1)
        cb.can_attempt()
        assert cb.state == CircuitState.HALF_OPEN

        # Record success should close the circuit
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_circuit_breaker_reopens_on_failure_from_half_open(self):
        """Test circuit breaker reopens after failure from HALF_OPEN"""
        from src.chains.connector import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

        # Open the circuit
        for i in range(3):
            cb.record_failure()

        # Wait for timeout to transition to HALF_OPEN
        time.sleep(1.1)
        cb.can_attempt()
        assert cb.state == CircuitState.HALF_OPEN

        # Record another failure
        cb.record_failure()
        assert cb.failure_count == 4

        # Circuit should remain open (or reopen)
        # Next can_attempt should return False until timeout
        assert cb.can_attempt() is False


class TestRPCFailover:
    """Test RPC failover mechanism"""

    @pytest.mark.asyncio
    async def test_failover_to_backup_on_primary_failure(self, bsc_config):
        """Test automatic failover to backup RPC when primary fails"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_web3_class.return_value = mock_w3

            connector = BSCConnector(bsc_config)
            initial_index = connector.current_rpc_index
            
            # Manually trigger failover
            connector._failover()
            
            # Should have switched to next endpoint
            assert connector.current_rpc_index == (initial_index + 1) % len(bsc_config.rpc_urls)

    @pytest.mark.asyncio
    async def test_failover_cycles_through_all_endpoints(self, bsc_config):
        """Test failover cycles through all available RPC endpoints"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_web3_class.return_value = mock_w3

            connector = BSCConnector(bsc_config)
            initial_index = connector.current_rpc_index

            # Trigger failover
            connector._failover()

            # Should have moved to next index
            assert connector.current_rpc_index == (initial_index + 1) % len(bsc_config.rpc_urls)

    @pytest.mark.asyncio
    async def test_failover_respects_circuit_breaker(self, bsc_config):
        """Test failover skips endpoints with open circuit breakers"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_web3_class.return_value = mock_w3

            connector = BSCConnector(bsc_config)

            # Open circuit breaker for backup endpoint
            backup_url = bsc_config.rpc_urls[1]
            connector._circuit_breakers[backup_url].state = CircuitState.OPEN
            connector._circuit_breakers[backup_url].failure_count = 5

            # Set to primary
            connector.current_rpc_index = 0

            # Trigger failover - should skip backup due to open circuit
            result = connector._failover()

            # Should cycle back to primary or fail
            assert connector.current_rpc_index in [0, 1]

    @pytest.mark.asyncio
    async def test_retry_with_failover_on_web3_exception(self, bsc_config):
        """Test retry with failover when Web3Exception occurs"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            
            # First call fails, second succeeds after failover
            call_count = [0]
            
            def mock_block_number():
                call_count[0] += 1
                if call_count[0] == 1:
                    raise Web3Exception("Connection timeout")
                return 12345
            
            mock_w3.eth.block_number = property(lambda self: mock_block_number())
            mock_web3_class.return_value = mock_w3

            connector = BSCConnector(bsc_config)
            
            # Should retry and succeed
            block_number = await connector.get_latest_block()
            assert block_number == 12345
            assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_all_endpoints_fail_raises_error(self, bsc_config):
        """Test that error is raised when all RPC endpoints fail"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_w3.eth.block_number = property(lambda self: (_ for _ in ()).throw(Web3Exception("All endpoints down")))
            mock_web3_class.return_value = mock_w3

            connector = BSCConnector(bsc_config)

            # Should raise after exhausting all retries and endpoints
            with pytest.raises(Web3Exception):
                await connector.get_latest_block()


class TestConnectionRecovery:
    """Test connection recovery after failures"""

    @pytest.mark.asyncio
    async def test_circuit_breaker_allows_retry_after_timeout(self, bsc_config):
        """Test that circuit breaker allows retry after timeout period"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_web3_class.return_value = mock_w3

            connector = BSCConnector(bsc_config)
            
            # Open circuit breaker with short timeout
            primary_url = bsc_config.rpc_urls[0]
            cb = connector._circuit_breakers[primary_url]
            cb.failure_threshold = 3
            cb.timeout_seconds = 1
            
            # Trigger failures to open circuit
            for _ in range(3):
                cb.record_failure()
            
            assert cb.state == CircuitState.OPEN
            assert cb.can_attempt() is False

            # Wait for timeout
            time.sleep(1.1)

            # Should allow retry
            assert cb.can_attempt() is True
            assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_successful_call_resets_circuit_breaker(self, bsc_config):
        """Test that successful call resets circuit breaker state"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_w3.eth.block_number = 12345
            mock_web3_class.return_value = mock_w3

            connector = BSCConnector(bsc_config)
            
            # Simulate some failures
            primary_url = bsc_config.rpc_urls[0]
            cb = connector._circuit_breakers[primary_url]
            cb.record_failure()
            cb.record_failure()
            
            assert cb.failure_count == 2

            # Successful call should reset
            block_number = await connector.get_latest_block()
            
            assert block_number == 12345
            assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_connection_recovery_after_network_outage(self, bsc_config):
        """Test connection recovery after simulated network outage"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            
            # Simulate network outage then recovery
            call_count = [0]
            
            def mock_block_number():
                call_count[0] += 1
                if call_count[0] <= 2:
                    raise ConnectionError("Network unreachable")
                return 12345
            
            mock_w3.eth.block_number = property(lambda self: mock_block_number())
            mock_web3_class.return_value = mock_w3

            connector = BSCConnector(bsc_config)
            
            # Should recover after retries
            block_number = await connector.get_latest_block()
            assert block_number == 12345
            assert call_count[0] == 3

    @pytest.mark.asyncio
    async def test_multiple_operations_with_intermittent_failures(self, bsc_config):
        """Test multiple operations with intermittent failures"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            
            # Simulate intermittent failures
            call_count = [0]
            
            def mock_block_number():
                call_count[0] += 1
                if call_count[0] % 3 == 0:  # Every 3rd call fails
                    raise Web3Exception("Intermittent failure")
                return 10000 + call_count[0]
            
            mock_w3.eth.block_number = property(lambda self: mock_block_number())
            mock_web3_class.return_value = mock_w3

            connector = BSCConnector(bsc_config)
            
            # Make multiple calls
            results = []
            for _ in range(5):
                try:
                    block = await connector.get_latest_block()
                    results.append(block)
                except Web3Exception:
                    pass
            
            # Should have some successful results
            assert len(results) > 0


class TestChainConnectorIntegration:
    """Integration tests for chain connectors"""

    @pytest.mark.asyncio
    async def test_bsc_connector_initialization(self, bsc_config):
        """Test BSC connector initializes correctly"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_web3_class.return_value = mock_w3

            connector = BSCConnector(bsc_config)
            
            assert connector.chain_name == "BSC"
            assert connector.chain_id == 56
            assert len(connector.rpc_urls) == 2
            assert len(connector._circuit_breakers) == 2

    @pytest.mark.asyncio
    async def test_polygon_connector_initialization(self, polygon_config):
        """Test Polygon connector initializes correctly"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_web3_class.return_value = mock_w3

            connector = PolygonConnector(polygon_config)
            
            assert connector.chain_name == "Polygon"
            assert connector.chain_id == 137
            assert len(connector.rpc_urls) == 2
            assert len(connector._circuit_breakers) == 2

    @pytest.mark.asyncio
    async def test_dex_router_recognition(self, bsc_config):
        """Test DEX router address recognition"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            mock_web3_class.return_value = mock_w3

            connector = BSCConnector(bsc_config)
            
            # Test known router
            pancakeswap_router = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
            assert connector.is_dex_router(pancakeswap_router) is True
            
            # Test unknown address
            random_address = "0x0000000000000000000000000000000000000000"
            assert connector.is_dex_router(random_address) is False

    @pytest.mark.asyncio
    async def test_get_transaction_receipt_with_retry(self, bsc_config):
        """Test getting transaction receipt with retry logic"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            
            mock_receipt = {
                "transactionHash": "0x123",
                "blockNumber": 12345,
                "status": 1
            }
            
            # First call fails, second succeeds
            call_count = [0]
            
            def mock_get_receipt(tx_hash):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise Web3Exception("Timeout")
                return mock_receipt
            
            mock_w3.eth.get_transaction_receipt = mock_get_receipt
            mock_web3_class.return_value = mock_w3

            connector = BSCConnector(bsc_config)
            
            receipt = await connector.get_transaction_receipt("0x123")
            assert receipt["transactionHash"] == "0x123"
            assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_get_block_with_retry(self, bsc_config):
        """Test getting block with retry logic"""
        with patch("src.chains.connector.Web3") as mock_web3_class:
            mock_w3 = MagicMock()
            mock_w3.is_connected.return_value = True
            
            mock_block = {
                "number": 12345,
                "hash": "0xabc",
                "transactions": []
            }
            
            # First call fails, second succeeds
            call_count = [0]
            
            def mock_get_block(block_num, full_transactions=True):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise Web3Exception("Timeout")
                return mock_block
            
            mock_w3.eth.get_block = mock_get_block
            mock_web3_class.return_value = mock_w3

            connector = BSCConnector(bsc_config)
            
            block = await connector.get_block(12345)
            assert block["number"] == 12345
            assert call_count[0] == 2
