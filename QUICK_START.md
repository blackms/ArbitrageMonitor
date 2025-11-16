# Quick Start Guide

Get the Multi-Chain Arbitrage Monitor running in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- 4GB RAM available
- Internet connection for RPC endpoints

## Steps

### 1. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit with your settings (optional - defaults work for testing)
nano .env
```

**Minimum required change:**
```bash
DB_PASSWORD=your_secure_password
```

### 2. Start Services

```bash
# Start all services in background
docker-compose up -d

# Watch logs
docker-compose logs -f monitor
```

### 3. Verify Deployment

```bash
# Check service health
docker-compose ps

# Test API
curl http://localhost:8000/api/v1/health

# View API documentation
open http://localhost:8000/docs
```

### 4. Access the System

- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/api/v1/health
- **Metrics**: http://localhost:9090/metrics
- **WebSocket**: ws://localhost:8000/ws/v1/stream

### 5. Query Data

```bash
# Get chain status (requires API key from .env)
curl -H "X-API-Key: dev_key_1" http://localhost:8000/api/v1/chains

# Get opportunities
curl -H "X-API-Key: dev_key_1" \
  "http://localhost:8000/api/v1/opportunities?chain_id=56&limit=10"

# Get transactions
curl -H "X-API-Key: dev_key_1" \
  "http://localhost:8000/api/v1/transactions?chain_id=137&limit=10"
```

## Common Commands

```bash
# Stop services
docker-compose down

# Restart monitor
docker-compose restart monitor

# View logs
docker-compose logs -f

# Rebuild after code changes
docker-compose up -d --build

# Clean everything (⚠️ deletes data)
docker-compose down -v
```

## Troubleshooting

**Services won't start?**
```bash
docker-compose logs
```

**Database connection issues?**
```bash
docker-compose exec postgres psql -U monitor -d arbitrage_monitor -c "SELECT 1;"
```

**Need to reset everything?**
```bash
docker-compose down -v
docker-compose up -d
```

## Next Steps

- Review [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) for detailed documentation
- Configure production RPC endpoints in `.env`
- Set up monitoring and alerting
- Review security hardening steps

## Support

Check logs for errors:
```bash
docker-compose logs -f monitor
```

Verify configuration:
```bash
docker-compose config
```
