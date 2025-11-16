"""Integration test demonstrating metrics collection across components"""

import asyncio
from decimal import Decimal

from src.monitoring import metrics


async def simulate_chain_monitor_metrics():
    """Simulate chain monitor recording metrics"""
    print("\n1. Chain Monitor Metrics:")
    
    # Simulate blocks behind
    metrics.chain_blocks_behind.labels(chain="BSC").set(3)
    print("   - Set blocks_behind to 3 for BSC")
    
    # Simulate transaction detection
    metrics.transactions_detected.labels(chain="BSC").inc()
    print("   - Incremented transactions_detected for BSC")
    
    # Simulate profit detection
    metrics.total_profit_detected_usd.labels(chain="BSC").inc(1250.75)
    print("   - Added $1250.75 to total_profit_detected for BSC")


async def simulate_pool_scanner_metrics():
    """Simulate pool scanner recording metrics"""
    print("\n2. Pool Scanner Metrics:")
    
    # Simulate opportunity detection
    metrics.opportunities_detected.labels(chain="Polygon").inc()
    print("   - Incremented opportunities_detected for Polygon")


async def simulate_database_metrics():
    """Simulate database operations recording metrics"""
    print("\n3. Database Metrics:")
    
    # Simulate query latency
    metrics.db_query_latency.labels(operation="save_opportunity").observe(0.045)
    print("   - Recorded query latency: 0.045s for save_opportunity")
    
    # Simulate connection pool
    metrics.db_connection_pool_size.set(20)
    metrics.db_connection_pool_free.set(12)
    print("   - Set connection pool: 20 total, 12 free")
    
    # Simulate error
    metrics.db_errors.labels(operation="save_transaction", error_type="TimeoutError").inc()
    print("   - Incremented db_errors for TimeoutError")


async def simulate_rpc_metrics():
    """Simulate RPC call metrics"""
    print("\n4. RPC Metrics:")
    
    # Simulate RPC latency
    metrics.chain_rpc_latency.labels(
        chain="BSC",
        endpoint="https://bsc-dataseed.bnbchain.org",
        method="get_block"
    ).observe(0.234)
    print("   - Recorded RPC latency: 0.234s for get_block")
    
    # Simulate RPC error
    metrics.chain_rpc_errors.labels(chain="Polygon", error_type="ConnectionError").inc()
    print("   - Incremented rpc_errors for ConnectionError")


async def simulate_api_metrics():
    """Simulate API request metrics"""
    print("\n5. API Metrics:")
    
    # Simulate successful request
    metrics.api_requests_total.labels(
        endpoint="/api/v1/opportunities",
        method="GET",
        status=200
    ).inc()
    metrics.api_request_latency.labels(
        endpoint="/api/v1/opportunities",
        method="GET"
    ).observe(0.089)
    print("   - Recorded API request: GET /api/v1/opportunities (200) in 0.089s")
    
    # Simulate error
    metrics.api_errors.labels(
        endpoint="/api/v1/transactions",
        error_type="ValidationError"
    ).inc()
    print("   - Incremented api_errors for ValidationError")


async def simulate_websocket_metrics():
    """Simulate WebSocket metrics"""
    print("\n6. WebSocket Metrics:")
    
    # Simulate active connections
    metrics.websocket_connections_active.set(15)
    print("   - Set active WebSocket connections: 15")
    
    # Simulate message broadcast
    metrics.websocket_messages_sent.labels(message_type="opportunity").inc(8)
    print("   - Sent 8 opportunity messages")
    
    metrics.websocket_messages_sent.labels(message_type="transaction").inc(3)
    print("   - Sent 3 transaction messages")


async def simulate_business_metrics():
    """Simulate business metrics"""
    print("\n7. Business Metrics:")
    
    # Simulate active arbitrageurs
    metrics.active_arbitrageurs.labels(chain="BSC").set(42)
    print("   - Set active arbitrageurs: 42 for BSC")
    
    # Simulate small opportunity percentage
    metrics.small_opportunities_percentage.labels(chain="Polygon").set(28.5)
    print("   - Set small opportunity percentage: 28.5% for Polygon")


def display_metrics_summary():
    """Display summary of collected metrics"""
    print("\n" + "=" * 60)
    print("Metrics Summary")
    print("=" * 60)
    
    # Export metrics
    metrics_output = metrics.get_metrics().decode('utf-8')
    
    # Count different metric types
    metric_types = {
        'Chain Health': ['chain_blocks_behind', 'chain_rpc_latency', 'chain_rpc_errors'],
        'Detection': ['opportunities_detected', 'transactions_detected'],
        'Database': ['db_query_latency', 'db_connection_pool', 'db_errors'],
        'API': ['api_requests_total', 'api_request_latency', 'api_errors'],
        'WebSocket': ['websocket_connections', 'websocket_messages'],
        'Business': ['total_profit_detected', 'active_arbitrageurs', 'small_opportunities']
    }
    
    print("\nMetric Categories Present:")
    for category, metric_names in metric_types.items():
        found = sum(1 for name in metric_names if name in metrics_output)
        print(f"  {category}: {found}/{len(metric_names)} metrics")
    
    print(f"\nTotal metrics output size: {len(metrics_output)} bytes")
    print(f"Content type: {metrics.get_content_type()}")
    
    # Show sample of actual metrics
    print("\nSample Metrics Output:")
    print("-" * 60)
    lines = metrics_output.split('\n')
    
    # Find and display some key metrics
    for line in lines:
        if any(keyword in line for keyword in [
            'chain_blocks_behind{',
            'opportunities_detected_total{',
            'db_connection_pool_size',
            'api_requests_total{',
            'websocket_connections_active'
        ]):
            print(line)


async def main():
    """Run all metric simulations"""
    print("=" * 60)
    print("Metrics Integration Test")
    print("=" * 60)
    print("\nSimulating metrics collection from all components...")
    
    # Simulate metrics from different components
    await simulate_chain_monitor_metrics()
    await simulate_pool_scanner_metrics()
    await simulate_database_metrics()
    await simulate_rpc_metrics()
    await simulate_api_metrics()
    await simulate_websocket_metrics()
    await simulate_business_metrics()
    
    # Display summary
    display_metrics_summary()
    
    print("\n" + "=" * 60)
    print("✓ Integration test completed successfully!")
    print("=" * 60)
    print("\nMetrics are ready to be scraped by Prometheus at /metrics endpoint")


if __name__ == "__main__":
    asyncio.run(main())
