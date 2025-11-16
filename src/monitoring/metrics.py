"""Prometheus metrics for monitoring system health and performance"""

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST, start_http_server

# Chain Health Metrics
chain_blocks_behind = Gauge(
    'chain_blocks_behind',
    'Number of blocks behind the latest block',
    ['chain']
)

chain_rpc_latency = Histogram(
    'chain_rpc_latency_seconds',
    'RPC call latency in seconds',
    ['chain', 'endpoint', 'method'],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)
)

chain_rpc_errors = Counter(
    'chain_rpc_errors_total',
    'Total number of RPC errors',
    ['chain', 'error_type']
)

# Detection Performance Metrics
opportunities_detected = Counter(
    'opportunities_detected_total',
    'Total number of opportunities detected',
    ['chain']
)

transactions_detected = Counter(
    'transactions_detected_total',
    'Total number of arbitrage transactions detected',
    ['chain']
)

detection_latency = Histogram(
    'detection_latency_seconds',
    'Detection latency in seconds',
    ['chain', 'type'],
    buckets=(0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0)
)

# Database Performance Metrics
db_query_latency = Histogram(
    'db_query_latency_seconds',
    'Database query latency in seconds',
    ['operation'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0)
)

db_connection_pool_size = Gauge(
    'db_connection_pool_size',
    'Number of active database connections'
)

db_connection_pool_free = Gauge(
    'db_connection_pool_free',
    'Number of free database connections'
)

db_errors = Counter(
    'db_errors_total',
    'Total number of database errors',
    ['operation', 'error_type']
)

# API Performance Metrics
api_requests_total = Counter(
    'api_requests_total',
    'Total number of API requests',
    ['endpoint', 'method', 'status']
)

api_request_latency = Histogram(
    'api_request_latency_seconds',
    'API request latency in seconds',
    ['endpoint', 'method'],
    buckets=(0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0)
)

api_errors = Counter(
    'api_errors_total',
    'Total number of API errors',
    ['endpoint', 'error_type']
)

# WebSocket Metrics
websocket_connections_active = Gauge(
    'websocket_connections_active',
    'Number of active WebSocket connections'
)

websocket_messages_sent = Counter(
    'websocket_messages_sent_total',
    'Total number of WebSocket messages sent',
    ['message_type']
)

# Business Metrics
total_profit_detected_usd = Counter(
    'total_profit_detected_usd',
    'Cumulative profit detected in USD',
    ['chain']
)

active_arbitrageurs = Gauge(
    'active_arbitrageurs',
    'Number of unique arbitrageurs active in the last hour',
    ['chain']
)

small_opportunities_percentage = Gauge(
    'small_opportunities_percentage',
    'Percentage of opportunities classified as small ($10K-$100K)',
    ['chain']
)


def get_metrics() -> bytes:
    """
    Generate Prometheus metrics in text format.
    
    Returns:
        Metrics in Prometheus text format
    """
    return generate_latest()


def get_content_type() -> str:
    """
    Get the content type for Prometheus metrics.
    
    Returns:
        Content type string
    """
    return CONTENT_TYPE_LATEST


def start_metrics_server(port: int = 9090) -> None:
    """
    Start Prometheus metrics HTTP server.
    
    Args:
        port: Port to listen on (default 9090)
    """
    start_http_server(port)
