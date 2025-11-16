# Running the Multi-Chain Arbitrage Monitor

This guide explains how to run the complete Multi-Chain Arbitrage Monitor application.

## Prerequisites

1. **Python 3.11+** installed
2. **PostgreSQL 15+** running and accessible
3. **Redis 7+** running (optional, for caching)
4. **Environment variables** configured (see `.env.example`)

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
# or with poetry
poetry install
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/arbitrage_monitor

# Redis (optional)
REDIS_URL=redis://localhost:6379

# BSC RPC Endpoints
BSC_RPC_PRIMARY=https://bsc-dataseed.bnbchain.org
BSC_RPC_FALLBACK=https://bsc-dataseed1.binance.org

# Polygon RPC Endpoints
POLYGON_RPC_PRIMARY=https://polygon-rpc.com
POLYGON_RPC_FALLBACK=https://rpc-mainnet.matic.network

# API Configuration
API_KEYS=your-api-key-1,your-api-key-2
RATE_LIMIT_PER_MINUTE=100
MAX_WEBSOCKET_CONNECTIONS=100

# Monitoring
PROMETHEUS_PORT=9090
LOG_LEVEL=INFO
```

### 3. Initialize Database

The application will automatically initialize the database schema on first run.

Alternatively, you can manually initialize:

```bash
python3 -c "
import asyncio
from src.database.manager import DatabaseManager
from src.config.models import Settings

async def init():
    settings = Settings()
    db = DatabaseManager(settings.database_url)
    await db.connect()
    await db.initialize_schema()
    await db.disconnect()

asyncio.run(init())
"
```

### 4. Run the Application

```bash
python3 main.py
```

The application will:
- Initialize all components (database, cache, chain connectors)
- Start chain monitors for BSC and Polygon
- Start pool scanners for both chains
- Start the FastAPI REST API server on port 8000
- Start the WebSocket server at `/ws/v1/stream`
- Start the Prometheus metrics server on port 9090
- Start background services (stats aggregator, data retention)

## Application Components

### REST API Endpoints

Once running, the API is available at `http://localhost:8000`:

- **Documentation**: http://localhost:8000/docs
- **Health Check**: `GET /api/v1/health`
- **Chains**: `GET /api/v1/chains`
- **Opportunities**: `GET /api/v1/opportunities`
- **Transactions**: `GET /api/v1/transactions`
- **Arbitrageurs**: `GET /api/v1/arbitrageurs`
- **Statistics**: `GET /api/v1/stats`

All endpoints require `X-API-Key` header with a valid API key.

### WebSocket Streaming

Connect to `ws://localhost:8000/ws/v1/stream` for real-time updates:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/v1/stream');

// Subscribe to opportunities
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'opportunities',
  filters: {
    chain_id: 56,  // BSC
    min_profit: 10000
  }
}));

// Subscribe to transactions
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'transactions',
  filters: {
    chain_id: 137,  // Polygon
    min_swaps: 2
  }
}));
```

### Prometheus Metrics

Metrics are available at `http://localhost:9090/metrics`

Key metrics:
- `chain_blocks_behind` - Blocks behind latest
- `opportunities_detected_total` - Total opportunities detected
- `transactions_detected_total` - Total arbitrage transactions
- `api_requests_total` - API request count
- `websocket_connections_active` - Active WebSocket connections

## Graceful Shutdown

The application handles graceful shutdown on `SIGTERM` or `SIGINT` (Ctrl+C):

```bash
# Send SIGTERM
kill -TERM <pid>

# Or press Ctrl+C
```

Shutdown sequence:
1. Stop data retention service
2. Stop statistics aggregator
3. Stop pool scanners
4. Stop chain monitors
5. Stop WebSocket background tasks
6. Close cache connection
7. Close database connection

## Docker Deployment

For production deployment with Docker:

```bash
# Build and run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f monitor

# Stop
docker-compose down
```

See `DOCKER_DEPLOYMENT.md` for detailed Docker instructions.

## Monitoring

### Logs

The application uses structured JSON logging. All logs are written to stdout:

```bash
# View logs
python3 main.py | jq .

# Filter by level
python3 main.py | jq 'select(.level == "error")'

# Filter by component
python3 main.py | jq 'select(.component == "chain_monitor")'
```

### Health Checks

Check application health:

```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/api/v1/health
```

Response:
```json
{
  "status": "healthy",
  "database": {
    "connected": true,
    "pool_size": 10,
    "free_connections": 8
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Test connection
psql -h localhost -U user -d arbitrage_monitor
```

### RPC Connection Issues

```bash
# Test BSC RPC
curl -X POST https://bsc-dataseed.bnbchain.org \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'

# Test Polygon RPC
curl -X POST https://polygon-rpc.com \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'
```

### High Memory Usage

If memory usage is high:
1. Reduce database connection pool size in `DatabaseManager`
2. Reduce WebSocket max connections
3. Increase data retention cleanup frequency

### Slow Performance

If detection is slow:
1. Check `chain_blocks_behind` metric
2. Verify RPC endpoint latency
3. Check database query performance
4. Consider adding Redis cache

## Development Mode

For development with auto-reload:

```bash
# Install uvicorn with reload
pip install uvicorn[standard]

# Run with auto-reload (API only)
uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

# For full application, use main.py
python3 main.py
```

## Testing

Run verification tests:

```bash
# Verify main application
python3 verify_main.py

# Run all tests
pytest tests/

# Run specific test
pytest tests/test_chain_monitor.py -v
```

## Support

For issues or questions:
1. Check logs for error messages
2. Verify environment configuration
3. Check database and RPC connectivity
4. Review metrics for anomalies
5. Consult the design document in `.kiro/specs/multi-chain-arbitrage-monitor/design.md`
