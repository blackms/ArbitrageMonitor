# Prometheus Metrics Implementation Summary

## Overview

Successfully implemented comprehensive Prometheus metrics for monitoring system health, performance, and business metrics across all components of the Multi-Chain Arbitrage Monitor.

## Implementation Details

### 1. Metrics Module (`src/monitoring/metrics.py`)

Created a centralized metrics module with the following metric categories:

#### Chain Health Metrics
- `chain_blocks_behind` (Gauge): Number of blocks behind the latest block
- `chain_rpc_latency_seconds` (Histogram): RPC call latency with buckets for different time ranges
- `chain_rpc_errors_total` (Counter): Total RPC errors by chain and error type

#### Detection Performance Metrics
- `opportunities_detected_total` (Counter): Total opportunities detected per chain
- `transactions_detected_total` (Counter): Total arbitrage transactions detected per chain
- `detection_latency_seconds` (Histogram): Detection latency for opportunities and transactions

#### Database Performance Metrics
- `db_query_latency_seconds` (Histogram): Database query latency by operation
- `db_connection_pool_size` (Gauge): Number of active database connections
- `db_connection_pool_free` (Gauge): Number of free database connections
- `db_errors_total` (Counter): Total database errors by operation and error type

#### API Performance Metrics
- `api_requests_total` (Counter): Total API requests by endpoint, method, and status
- `api_request_latency_seconds` (Histogram): API request latency by endpoint and method
- `api_errors_total` (Counter): Total API errors by endpoint and error type

#### WebSocket Metrics
- `websocket_connections_active` (Gauge): Number of active WebSocket connections
- `websocket_messages_sent_total` (Counter): Total WebSocket messages sent by message type

#### Business Metrics
- `total_profit_detected_usd` (Counter): Cumulative profit detected in USD per chain
- `active_arbitrageurs` (Gauge): Number of unique arbitrageurs active in the last hour
- `small_opportunities_percentage` (Gauge): Percentage of opportunities classified as small ($10K-$100K)

### 2. Component Integration

#### Chain Monitor (`src/monitors/chain_monitor.py`)
- Records `chain_blocks_behind` metric when processing new blocks
- Increments `transactions_detected` counter when arbitrage transactions are detected
- Increments `total_profit_detected_usd` counter with detected profit amounts

#### Pool Scanner (`src/detectors/pool_scanner.py`)
- Increments `opportunities_detected` counter when pool imbalances are detected

#### Database Manager (`src/database/manager.py`)
- Records `db_query_latency` for all database operations
- Updates `db_connection_pool_size` and `db_connection_pool_free` gauges
- Increments `db_errors` counter on database errors
- Tracks latency for save and query operations

#### Chain Connector (`src/chains/connector.py`)
- Records `chain_rpc_latency` for all RPC calls
- Increments `chain_rpc_errors` counter on RPC failures
- Tracks latency per endpoint and method

#### API Application (`src/api/app.py`)
- Added `/metrics` endpoint to expose Prometheus metrics
- Implemented middleware to track API request metrics:
  - Records request latency
  - Increments request counter with status codes
  - Tracks API errors

#### WebSocket Server (`src/api/websocket.py`)
- Updates `websocket_connections_active` gauge on connect/disconnect
- Increments `websocket_messages_sent` counter when broadcasting messages

### 3. Metrics Endpoint

The `/metrics` endpoint is available at the root level and returns metrics in Prometheus text format:

```
GET /metrics
Content-Type: text/plain; version=0.0.4; charset=utf-8
```

This endpoint does not require authentication and is designed to be scraped by Prometheus.

## Usage

### Prometheus Configuration

Add the following to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'arbitrage-monitor'
    scrape_interval: 15s
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

### Example Queries

#### Chain Health
```promql
# Blocks behind latest
chain_blocks_behind{chain="BSC"}

# RPC latency p95
histogram_quantile(0.95, rate(chain_rpc_latency_seconds_bucket[5m]))

# RPC error rate
rate(chain_rpc_errors_total[5m])
```

#### Detection Performance
```promql
# Opportunities detected per minute
rate(opportunities_detected_total[1m])

# Transactions detected per minute
rate(transactions_detected_total[1m])

# Detection latency p99
histogram_quantile(0.99, rate(detection_latency_seconds_bucket[5m]))
```

#### Database Performance
```promql
# Query latency p95
histogram_quantile(0.95, rate(db_query_latency_seconds_bucket[5m]))

# Connection pool utilization
(db_connection_pool_size - db_connection_pool_free) / db_connection_pool_size

# Database error rate
rate(db_errors_total[5m])
```

#### API Performance
```promql
# Request rate by endpoint
rate(api_requests_total[1m])

# Request latency p95
histogram_quantile(0.95, rate(api_request_latency_seconds_bucket[5m]))

# Error rate
rate(api_errors_total[5m])
```

#### Business Metrics
```promql
# Total profit detected
total_profit_detected_usd

# Active arbitrageurs
active_arbitrageurs{chain="BSC"}

# Small opportunity percentage
small_opportunities_percentage{chain="Polygon"}
```

### Alerting Rules

Example Prometheus alerting rules:

```yaml
groups:
  - name: arbitrage_monitor
    rules:
      # Critical: Chain is falling behind
      - alert: ChainBlocksBehind
        expr: chain_blocks_behind > 100
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Chain {{ $labels.chain }} is {{ $value }} blocks behind"
          
      # Warning: High RPC latency
      - alert: HighRPCLatency
        expr: histogram_quantile(0.95, rate(chain_rpc_latency_seconds_bucket[5m])) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High RPC latency for {{ $labels.chain }}: {{ $value }}s"
          
      # Warning: No opportunities detected
      - alert: NoOpportunitiesDetected
        expr: rate(opportunities_detected_total[5m]) == 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "No opportunities detected for {{ $labels.chain }} in 5 minutes"
          
      # Warning: High database error rate
      - alert: HighDatabaseErrorRate
        expr: rate(db_errors_total[5m]) > 0.1
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "High database error rate: {{ $value }} errors/sec"
          
      # Warning: High API error rate
      - alert: HighAPIErrorRate
        expr: rate(api_errors_total[5m]) / rate(api_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API error rate: {{ $value }}%"
```

## Grafana Dashboard

### Recommended Panels

1. **Chain Health**
   - Blocks behind (gauge)
   - RPC latency (graph)
   - RPC error rate (graph)

2. **Detection Performance**
   - Opportunities detected rate (graph)
   - Transactions detected rate (graph)
   - Detection latency (heatmap)

3. **Database Performance**
   - Query latency by operation (graph)
   - Connection pool utilization (gauge)
   - Database error rate (graph)

4. **API Performance**
   - Request rate by endpoint (graph)
   - Request latency percentiles (graph)
   - Error rate (graph)

5. **Business Metrics**
   - Total profit detected (counter)
   - Active arbitrageurs (gauge)
   - Small opportunity percentage (gauge)

## Testing

Run the verification script to test metrics:

```bash
python3 verify_metrics.py
```

The script tests:
- Metrics initialization
- Metrics recording
- Metrics export in Prometheus format

## Requirements Met

✅ **12.1**: Chain health metrics (blocks_behind, rpc_latency, rpc_errors)
✅ **12.2**: Detection performance metrics (opportunities_detected, transactions_detected)
✅ **12.3**: Database performance metrics (query_latency, connection_pool_size)
✅ **12.4**: API performance metrics (requests_total, latency, errors)
✅ **12.5**: WebSocket metrics (connections_active, messages_sent)
✅ **12.6**: Metrics endpoint exposed at `/metrics`

## Files Modified

1. `src/monitoring/__init__.py` - Created monitoring module
2. `src/monitoring/metrics.py` - Created metrics definitions
3. `src/monitors/chain_monitor.py` - Added chain and transaction metrics
4. `src/detectors/pool_scanner.py` - Added opportunity detection metrics
5. `src/database/manager.py` - Added database performance metrics
6. `src/chains/connector.py` - Added RPC latency and error metrics
7. `src/api/app.py` - Added metrics endpoint and middleware
8. `src/api/websocket.py` - Added WebSocket metrics
9. `verify_metrics.py` - Created verification script

## Next Steps

To complete the monitoring implementation:

1. Set up Prometheus server to scrape the `/metrics` endpoint
2. Configure alerting rules in Prometheus
3. Create Grafana dashboards for visualization
4. Set up alert notifications (PagerDuty, Slack, etc.)
5. Document operational runbooks for common alerts

## Notes

- All metrics are automatically collected without requiring manual instrumentation in most cases
- The metrics middleware automatically tracks all API requests
- Database operations are automatically timed and tracked
- RPC calls are automatically monitored for latency and errors
- The implementation follows Prometheus best practices for metric naming and labeling
