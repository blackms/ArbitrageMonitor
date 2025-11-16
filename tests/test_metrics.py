"""Unit tests for monitoring metrics"""

import pytest
from prometheus_client import REGISTRY
from src.monitoring import metrics


class TestMetricsEmission:
    """Test that metrics are properly emitted"""
    
    def test_chain_blocks_behind_emission(self):
        """Test chain_blocks_behind metric emission"""
        # Set metric value
        metrics.chain_blocks_behind.labels(chain="BSC").set(5)
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'chain_blocks_behind{chain="BSC"} 5.0' in metric_output
    
    def test_chain_rpc_latency_emission(self):
        """Test chain_rpc_latency histogram emission"""
        # Record latency observation
        metrics.chain_rpc_latency.labels(
            chain="Polygon",
            endpoint="https://polygon-rpc.com",
            method="get_block"
        ).observe(0.5)
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'chain_rpc_latency_seconds_count{chain="Polygon"' in metric_output
        assert 'endpoint="https://polygon-rpc.com"' in metric_output
        assert 'method="get_block"' in metric_output
    
    def test_chain_rpc_errors_emission(self):
        """Test chain_rpc_errors counter emission"""
        # Get initial value
        initial_output = metrics.get_metrics().decode('utf-8')
        
        # Increment counter
        metrics.chain_rpc_errors.labels(chain="BSC", error_type="ConnectionError").inc()
        
        # Verify counter incremented
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'chain_rpc_errors_total{chain="BSC",error_type="ConnectionError"}' in metric_output
    
    def test_opportunities_detected_emission(self):
        """Test opportunities_detected counter emission"""
        # Increment counter
        metrics.opportunities_detected.labels(chain="BSC").inc()
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'opportunities_detected_total{chain="BSC"}' in metric_output
    
    def test_transactions_detected_emission(self):
        """Test transactions_detected counter emission"""
        # Increment counter
        metrics.transactions_detected.labels(chain="Polygon").inc()
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'transactions_detected_total{chain="Polygon"}' in metric_output
    
    def test_detection_latency_emission(self):
        """Test detection_latency histogram emission"""
        # Record latency
        metrics.detection_latency.labels(chain="BSC", type="opportunity").observe(1.5)
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'detection_latency_seconds_count{chain="BSC",type="opportunity"}' in metric_output
    
    def test_db_query_latency_emission(self):
        """Test db_query_latency histogram emission"""
        # Record query latency
        metrics.db_query_latency.labels(operation="save_opportunity").observe(0.05)
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'db_query_latency_seconds_count{operation="save_opportunity"}' in metric_output
    
    def test_db_connection_pool_emission(self):
        """Test database connection pool metrics emission"""
        # Set pool metrics
        metrics.db_connection_pool_size.set(20)
        metrics.db_connection_pool_free.set(15)
        
        # Verify metrics are in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'db_connection_pool_size 20.0' in metric_output
        assert 'db_connection_pool_free 15.0' in metric_output
    
    def test_db_errors_emission(self):
        """Test db_errors counter emission"""
        # Increment error counter
        metrics.db_errors.labels(operation="save_transaction", error_type="TimeoutError").inc()
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'db_errors_total{error_type="TimeoutError",operation="save_transaction"}' in metric_output
    
    def test_api_requests_emission(self):
        """Test api_requests_total counter emission"""
        # Increment request counter
        metrics.api_requests_total.labels(
            endpoint="/api/v1/opportunities",
            method="GET",
            status=200
        ).inc()
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'api_requests_total{endpoint="/api/v1/opportunities",method="GET",status="200"}' in metric_output
    
    def test_api_request_latency_emission(self):
        """Test api_request_latency histogram emission"""
        # Record API latency
        metrics.api_request_latency.labels(
            endpoint="/api/v1/transactions",
            method="GET"
        ).observe(0.12)
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'api_request_latency_seconds_count{endpoint="/api/v1/transactions",method="GET"}' in metric_output
    
    def test_api_errors_emission(self):
        """Test api_errors counter emission"""
        # Increment error counter
        metrics.api_errors.labels(endpoint="/api/v1/stats", error_type="ValidationError").inc()
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'api_errors_total{endpoint="/api/v1/stats",error_type="ValidationError"}' in metric_output
    
    def test_websocket_connections_emission(self):
        """Test websocket_connections_active gauge emission"""
        # Set active connections
        metrics.websocket_connections_active.set(25)
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'websocket_connections_active 25.0' in metric_output
    
    def test_websocket_messages_emission(self):
        """Test websocket_messages_sent counter emission"""
        # Increment message counter
        metrics.websocket_messages_sent.labels(message_type="opportunity").inc(5)
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'websocket_messages_sent_total{message_type="opportunity"}' in metric_output
    
    def test_total_profit_detected_emission(self):
        """Test total_profit_detected_usd counter emission"""
        # Add profit
        metrics.total_profit_detected_usd.labels(chain="BSC").inc(1500.50)
        
        # Verify metric is in registry (counters get _total suffix)
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'total_profit_detected_usd_total{chain="BSC"}' in metric_output
    
    def test_active_arbitrageurs_emission(self):
        """Test active_arbitrageurs gauge emission"""
        # Set active arbitrageurs
        metrics.active_arbitrageurs.labels(chain="Polygon").set(42)
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'active_arbitrageurs{chain="Polygon"} 42.0' in metric_output
    
    def test_small_opportunities_percentage_emission(self):
        """Test small_opportunities_percentage gauge emission"""
        # Set percentage
        metrics.small_opportunities_percentage.labels(chain="BSC").set(28.5)
        
        # Verify metric is in registry
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'small_opportunities_percentage{chain="BSC"} 28.5' in metric_output


class TestMetricsAccuracy:
    """Test that metrics accurately reflect operations"""
    
    def test_counter_increments_accurately(self):
        """Test that counters increment by correct amounts"""
        # Get baseline
        initial_output = metrics.get_metrics().decode('utf-8')
        
        # Increment by specific amount
        metrics.opportunities_detected.labels(chain="TestChain").inc(3)
        
        # Verify increment
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'opportunities_detected_total{chain="TestChain"}' in metric_output
    
    def test_gauge_sets_accurate_value(self):
        """Test that gauges set exact values"""
        # Set specific value
        test_value = 123.45
        metrics.chain_blocks_behind.labels(chain="TestChain").set(test_value)
        
        # Verify exact value
        metric_output = metrics.get_metrics().decode('utf-8')
        assert f'chain_blocks_behind{{chain="TestChain"}} {test_value}' in metric_output
    
    def test_histogram_records_observations(self):
        """Test that histograms record observations in correct buckets"""
        # Record multiple observations
        test_chain = "TestChainHisto"
        metrics.detection_latency.labels(chain=test_chain, type="test").observe(0.5)
        metrics.detection_latency.labels(chain=test_chain, type="test").observe(1.5)
        metrics.detection_latency.labels(chain=test_chain, type="test").observe(2.5)
        
        # Verify observations are recorded
        metric_output = metrics.get_metrics().decode('utf-8')
        assert f'detection_latency_seconds_count{{chain="{test_chain}",type="test"}} 3.0' in metric_output
        
        # Verify sum is accurate (0.5 + 1.5 + 2.5 = 4.5)
        assert f'detection_latency_seconds_sum{{chain="{test_chain}",type="test"}} 4.5' in metric_output
    
    def test_multiple_labels_tracked_separately(self):
        """Test that metrics with different labels are tracked independently"""
        # Set different values for different chains
        metrics.chain_blocks_behind.labels(chain="BSC").set(5)
        metrics.chain_blocks_behind.labels(chain="Polygon").set(10)
        
        # Verify both are tracked correctly
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'chain_blocks_behind{chain="BSC"} 5.0' in metric_output
        assert 'chain_blocks_behind{chain="Polygon"} 10.0' in metric_output
    
    def test_counter_only_increases(self):
        """Test that counters only increase, never decrease"""
        # Increment counter
        test_chain = "TestCounterChain"
        metrics.transactions_detected.labels(chain=test_chain).inc(5)
        
        # Get current value
        metric_output = metrics.get_metrics().decode('utf-8')
        assert f'transactions_detected_total{{chain="{test_chain}"}} 5.0' in metric_output
        
        # Increment again
        metrics.transactions_detected.labels(chain=test_chain).inc(3)
        
        # Verify total is cumulative (5 + 3 = 8)
        metric_output = metrics.get_metrics().decode('utf-8')
        assert f'transactions_detected_total{{chain="{test_chain}"}} 8.0' in metric_output
    
    def test_histogram_bucket_distribution(self):
        """Test that histogram observations are distributed into correct buckets"""
        test_op = "test_bucket_op"
        
        # Record observations in different ranges
        metrics.db_query_latency.labels(operation=test_op).observe(0.005)  # < 0.01
        metrics.db_query_latency.labels(operation=test_op).observe(0.03)   # 0.01-0.05
        metrics.db_query_latency.labels(operation=test_op).observe(0.15)   # 0.1-0.25
        metrics.db_query_latency.labels(operation=test_op).observe(0.8)    # 0.5-1.0
        
        # Verify count
        metric_output = metrics.get_metrics().decode('utf-8')
        assert f'db_query_latency_seconds_count{{operation="{test_op}"}} 4.0' in metric_output
        
        # Verify buckets exist
        assert f'db_query_latency_seconds_bucket{{le="0.01",operation="{test_op}"}}' in metric_output
        assert f'db_query_latency_seconds_bucket{{le="0.05",operation="{test_op}"}}' in metric_output
        assert f'db_query_latency_seconds_bucket{{le="1.0",operation="{test_op}"}}' in metric_output
    
    def test_profit_accumulation_accuracy(self):
        """Test that profit counter accumulates correctly"""
        test_chain = "TestProfitChain"
        
        # Add multiple profit amounts
        metrics.total_profit_detected_usd.labels(chain=test_chain).inc(1000.50)
        metrics.total_profit_detected_usd.labels(chain=test_chain).inc(2500.75)
        metrics.total_profit_detected_usd.labels(chain=test_chain).inc(500.25)
        
        # Verify total (1000.50 + 2500.75 + 500.25 = 4001.50)
        metric_output = metrics.get_metrics().decode('utf-8')
        assert f'total_profit_detected_usd_total{{chain="{test_chain}"}} 4001.5' in metric_output
    
    def test_websocket_connection_tracking(self):
        """Test that WebSocket connection gauge tracks current state"""
        # Set initial connections
        metrics.websocket_connections_active.set(10)
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'websocket_connections_active 10.0' in metric_output
        
        # Update to new value (not cumulative)
        metrics.websocket_connections_active.set(15)
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'websocket_connections_active 15.0' in metric_output
        
        # Decrease connections
        metrics.websocket_connections_active.set(8)
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'websocket_connections_active 8.0' in metric_output


class TestMetricsFormat:
    """Test metrics output format"""
    
    def test_get_metrics_returns_bytes(self):
        """Test that get_metrics returns bytes"""
        result = metrics.get_metrics()
        assert isinstance(result, bytes)
    
    def test_get_metrics_is_valid_prometheus_format(self):
        """Test that metrics output is valid Prometheus format"""
        metric_output = metrics.get_metrics().decode('utf-8')
        
        # Should contain HELP and TYPE declarations
        assert '# HELP' in metric_output
        assert '# TYPE' in metric_output
    
    def test_get_content_type_returns_correct_type(self):
        """Test that content type is correct for Prometheus"""
        content_type = metrics.get_content_type()
        # Prometheus client library uses version 1.0.0
        assert 'text/plain' in content_type
        assert 'charset=utf-8' in content_type
    
    def test_all_metrics_have_help_text(self):
        """Test that all metrics have HELP documentation"""
        metric_output = metrics.get_metrics().decode('utf-8')
        
        # Check for key metrics
        metric_names = [
            'chain_blocks_behind',
            'opportunities_detected_total',
            'db_query_latency_seconds',
            'api_requests_total',
            'websocket_connections_active'
        ]
        
        for metric_name in metric_names:
            assert f'# HELP {metric_name}' in metric_output
    
    def test_all_metrics_have_type_declaration(self):
        """Test that all metrics have TYPE declaration"""
        metric_output = metrics.get_metrics().decode('utf-8')
        
        # Check for different metric types
        assert '# TYPE chain_blocks_behind gauge' in metric_output
        assert '# TYPE opportunities_detected_total counter' in metric_output
        assert '# TYPE db_query_latency_seconds histogram' in metric_output


class TestMetricsLabels:
    """Test metric label handling"""
    
    def test_chain_label_variations(self):
        """Test that chain label works with different chain names"""
        chains = ["BSC", "Polygon", "Ethereum", "Arbitrum"]
        
        for chain in chains:
            metrics.opportunities_detected.labels(chain=chain).inc()
        
        metric_output = metrics.get_metrics().decode('utf-8')
        for chain in chains:
            assert f'opportunities_detected_total{{chain="{chain}"}}' in metric_output
    
    def test_multiple_label_combinations(self):
        """Test metrics with multiple labels"""
        # Test RPC latency with multiple label combinations
        combinations = [
            ("BSC", "https://bsc-dataseed.bnbchain.org", "get_block"),
            ("BSC", "https://bsc-dataseed1.binance.org", "get_transaction"),
            ("Polygon", "https://polygon-rpc.com", "get_block"),
        ]
        
        for chain, endpoint, method in combinations:
            metrics.chain_rpc_latency.labels(
                chain=chain,
                endpoint=endpoint,
                method=method
            ).observe(0.1)
        
        metric_output = metrics.get_metrics().decode('utf-8')
        for chain, endpoint, method in combinations:
            assert f'chain="{chain}"' in metric_output
            assert f'endpoint="{endpoint}"' in metric_output
            assert f'method="{method}"' in metric_output
    
    def test_api_status_code_labels(self):
        """Test API metrics with different status codes"""
        status_codes = [200, 400, 404, 500]
        
        for status in status_codes:
            metrics.api_requests_total.labels(
                endpoint="/api/v1/test",
                method="GET",
                status=status
            ).inc()
        
        metric_output = metrics.get_metrics().decode('utf-8')
        for status in status_codes:
            assert f'status="{status}"' in metric_output


class TestMetricsIntegration:
    """Test metrics integration scenarios"""
    
    def test_complete_chain_monitor_workflow(self):
        """Test metrics for complete chain monitor workflow"""
        chain = "WorkflowTestChain"
        
        # Simulate chain monitor operations
        metrics.chain_blocks_behind.labels(chain=chain).set(2)
        metrics.chain_rpc_latency.labels(
            chain=chain,
            endpoint="https://test-rpc.com",
            method="get_block"
        ).observe(0.3)
        metrics.transactions_detected.labels(chain=chain).inc(5)
        metrics.total_profit_detected_usd.labels(chain=chain).inc(15000.0)
        
        # Verify all metrics are present
        metric_output = metrics.get_metrics().decode('utf-8')
        assert f'chain_blocks_behind{{chain="{chain}"}} 2.0' in metric_output
        assert f'transactions_detected_total{{chain="{chain}"}} 5.0' in metric_output
        assert f'total_profit_detected_usd_total{{chain="{chain}"}} 15000.0' in metric_output
    
    def test_complete_api_request_workflow(self):
        """Test metrics for complete API request workflow"""
        endpoint = "/api/v1/workflow_test"
        
        # Simulate API request
        metrics.api_requests_total.labels(
            endpoint=endpoint,
            method="GET",
            status=200
        ).inc()
        metrics.api_request_latency.labels(
            endpoint=endpoint,
            method="GET"
        ).observe(0.15)
        
        # Verify metrics
        metric_output = metrics.get_metrics().decode('utf-8')
        assert f'api_requests_total{{endpoint="{endpoint}",method="GET",status="200"}}' in metric_output
        assert f'api_request_latency_seconds_count{{endpoint="{endpoint}",method="GET"}}' in metric_output
    
    def test_error_tracking_workflow(self):
        """Test error tracking across different components"""
        # Simulate errors from different sources
        metrics.chain_rpc_errors.labels(chain="BSC", error_type="TimeoutError").inc()
        metrics.db_errors.labels(operation="save_opportunity", error_type="ConnectionError").inc()
        metrics.api_errors.labels(endpoint="/api/v1/test", error_type="ValidationError").inc()
        
        # Verify all errors are tracked
        metric_output = metrics.get_metrics().decode('utf-8')
        assert 'chain_rpc_errors_total{chain="BSC",error_type="TimeoutError"}' in metric_output
        assert 'db_errors_total{error_type="ConnectionError",operation="save_opportunity"}' in metric_output
        assert 'api_errors_total{endpoint="/api/v1/test",error_type="ValidationError"}' in metric_output
