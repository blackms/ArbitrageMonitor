"""Verification script for Prometheus metrics implementation"""

import asyncio
from decimal import Decimal

from src.monitoring import metrics


def test_metrics_initialization():
    """Test that all metrics are properly initialized"""
    print("Testing metrics initialization...")
    
    # Chain health metrics
    assert metrics.chain_blocks_behind is not None
    assert metrics.chain_rpc_latency is not None
    assert metrics.chain_rpc_errors is not None
    print("✓ Chain health metrics initialized")
    
    # Detection performance metrics
    assert metrics.opportunities_detected is not None
    assert metrics.transactions_detected is not None
    assert metrics.detection_latency is not None
    print("✓ Detection performance metrics initialized")
    
    # Database performance metrics
    assert metrics.db_query_latency is not None
    assert metrics.db_connection_pool_size is not None
    assert metrics.db_connection_pool_free is not None
    assert metrics.db_errors is not None
    print("✓ Database performance metrics initialized")
    
    # API performance metrics
    assert metrics.api_requests_total is not None
    assert metrics.api_request_latency is not None
    assert metrics.api_errors is not None
    print("✓ API performance metrics initialized")
    
    # WebSocket metrics
    assert metrics.websocket_connections_active is not None
    assert metrics.websocket_messages_sent is not None
    print("✓ WebSocket metrics initialized")
    
    # Business metrics
    assert metrics.total_profit_detected_usd is not None
    assert metrics.active_arbitrageurs is not None
    assert metrics.small_opportunities_percentage is not None
    print("✓ Business metrics initialized")


def test_metrics_recording():
    """Test that metrics can be recorded"""
    print("\nTesting metrics recording...")
    
    # Test chain metrics
    metrics.chain_blocks_behind.labels(chain="BSC").set(5)
    metrics.chain_rpc_latency.labels(chain="BSC", endpoint="https://bsc-rpc.com", method="get_block").observe(0.5)
    metrics.chain_rpc_errors.labels(chain="BSC", error_type="TimeoutError").inc()
    print("✓ Chain metrics recorded")
    
    # Test detection metrics
    metrics.opportunities_detected.labels(chain="BSC").inc()
    metrics.transactions_detected.labels(chain="Polygon").inc()
    metrics.detection_latency.labels(chain="BSC", type="opportunity").observe(1.2)
    print("✓ Detection metrics recorded")
    
    # Test database metrics
    metrics.db_query_latency.labels(operation="save_opportunity").observe(0.05)
    metrics.db_connection_pool_size.set(10)
    metrics.db_connection_pool_free.set(5)
    metrics.db_errors.labels(operation="save_transaction", error_type="ConnectionError").inc()
    print("✓ Database metrics recorded")
    
    # Test API metrics
    metrics.api_requests_total.labels(endpoint="/api/v1/opportunities", method="GET", status=200).inc()
    metrics.api_request_latency.labels(endpoint="/api/v1/opportunities", method="GET").observe(0.1)
    metrics.api_errors.labels(endpoint="/api/v1/transactions", error_type="ValidationError").inc()
    print("✓ API metrics recorded")
    
    # Test WebSocket metrics
    metrics.websocket_connections_active.set(25)
    metrics.websocket_messages_sent.labels(message_type="opportunity").inc(10)
    print("✓ WebSocket metrics recorded")
    
    # Test business metrics
    metrics.total_profit_detected_usd.labels(chain="BSC").inc(1500.50)
    metrics.active_arbitrageurs.labels(chain="Polygon").set(42)
    metrics.small_opportunities_percentage.labels(chain="BSC").set(35.5)
    print("✓ Business metrics recorded")


def test_metrics_export():
    """Test that metrics can be exported"""
    print("\nTesting metrics export...")
    
    # Get metrics in Prometheus format
    metrics_output = metrics.get_metrics()
    assert metrics_output is not None
    assert isinstance(metrics_output, bytes)
    assert len(metrics_output) > 0
    print("✓ Metrics exported successfully")
    
    # Check content type
    content_type = metrics.get_content_type()
    assert content_type is not None
    assert "text/plain" in content_type
    print("✓ Content type correct")
    
    # Verify some metrics are in the output
    metrics_text = metrics_output.decode('utf-8')
    assert "chain_blocks_behind" in metrics_text
    assert "opportunities_detected_total" in metrics_text
    assert "db_query_latency" in metrics_text
    assert "api_requests_total" in metrics_text
    print("✓ Metrics content verified")
    
    print(f"\nSample metrics output (first 500 chars):")
    print(metrics_text[:500])


def main():
    """Run all verification tests"""
    print("=" * 60)
    print("Prometheus Metrics Verification")
    print("=" * 60)
    
    try:
        test_metrics_initialization()
        test_metrics_recording()
        test_metrics_export()
        
        print("\n" + "=" * 60)
        print("✓ All metrics tests passed!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
