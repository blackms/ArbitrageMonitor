# Docker Deployment Guide

This guide explains how to deploy the Multi-Chain Arbitrage Monitor using Docker and Docker Compose.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- At least 4GB RAM available
- 20GB disk space

## Quick Start

1. **Clone the repository and navigate to the project directory**

2. **Create environment file**
   ```bash
   cp .env.example .env
   ```

3. **Edit `.env` file with your configuration**
   ```bash
   # Required: Set a secure database password
   DB_PASSWORD=your_secure_password_here
   
   # Optional: Configure RPC endpoints (defaults provided)
   BSC_RPC_PRIMARY=https://bsc-dataseed.bnbchain.org
   POLYGON_RPC_PRIMARY=https://polygon-rpc.com
   
   # Optional: Set API keys for authentication
   API_KEYS=your_api_key_1,your_api_key_2
   ```

4. **Start the services**
   ```bash
   docker-compose up -d
   ```

5. **Check service health**
   ```bash
   docker-compose ps
   docker-compose logs -f monitor
   ```

6. **Access the API**
   - API Documentation: http://localhost:8000/docs
   - Health Check: http://localhost:8000/api/v1/health
   - Metrics: http://localhost:9090/metrics

## Service Architecture

The deployment consists of three services:

### 1. PostgreSQL Database (`postgres`)
- **Image**: postgres:15-alpine
- **Port**: 5432
- **Volume**: `postgres_data` for data persistence
- **Health Check**: Automatic readiness check

### 2. Redis Cache (`redis`)
- **Image**: redis:7-alpine
- **Port**: 6379
- **Volume**: `redis_data` for persistence
- **Configuration**: AOF persistence enabled

### 3. Monitor Application (`monitor`)
- **Build**: Custom Dockerfile
- **Ports**: 
  - 8000 (API)
  - 9090 (Prometheus metrics)
- **Dependencies**: Waits for postgres and redis to be healthy
- **Restart Policy**: Automatic restart on failure

## Configuration

### Environment Variables

All configuration is done via environment variables in the `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_PASSWORD` | PostgreSQL password | `changeme` |
| `BSC_RPC_PRIMARY` | Primary BSC RPC endpoint | `https://bsc-dataseed.bnbchain.org` |
| `BSC_RPC_FALLBACK` | Fallback BSC RPC endpoint | `https://bsc-dataseed1.binance.org` |
| `POLYGON_RPC_PRIMARY` | Primary Polygon RPC endpoint | `https://polygon-rpc.com` |
| `POLYGON_RPC_FALLBACK` | Fallback Polygon RPC endpoint | `https://rpc-mainnet.matic.network` |
| `API_KEYS` | Comma-separated API keys | `dev_key_1,dev_key_2` |
| `RATE_LIMIT_PER_MINUTE` | API rate limit | `100` |
| `MAX_WEBSOCKET_CONNECTIONS` | Max WebSocket connections | `100` |
| `LOG_LEVEL` | Logging level | `INFO` |

### Using Custom RPC Endpoints

For production use, it's recommended to use dedicated RPC endpoints:

```bash
# Alchemy
BSC_RPC_PRIMARY=https://bnb-mainnet.g.alchemy.com/v2/YOUR_API_KEY

# Infura
POLYGON_RPC_PRIMARY=https://polygon-mainnet.infura.io/v3/YOUR_PROJECT_ID

# QuickNode
BSC_RPC_PRIMARY=https://YOUR_ENDPOINT.bsc.quiknode.pro/YOUR_TOKEN/
```

## Management Commands

### Start Services
```bash
docker-compose up -d
```

### Stop Services
```bash
docker-compose down
```

### Stop and Remove Volumes (⚠️ Deletes all data)
```bash
docker-compose down -v
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f monitor
docker-compose logs -f postgres
docker-compose logs -f redis
```

### Restart a Service
```bash
docker-compose restart monitor
```

### Rebuild After Code Changes
```bash
docker-compose up -d --build monitor
```

### Execute Commands in Container
```bash
# Access monitor container shell
docker-compose exec monitor bash

# Run Python commands
docker-compose exec monitor python -c "import sys; print(sys.version)"
```

## Database Management

### Access PostgreSQL
```bash
docker-compose exec postgres psql -U monitor -d arbitrage_monitor
```

### Backup Database
```bash
docker-compose exec postgres pg_dump -U monitor arbitrage_monitor > backup.sql
```

### Restore Database
```bash
cat backup.sql | docker-compose exec -T postgres psql -U monitor -d arbitrage_monitor
```

### View Database Size
```bash
docker-compose exec postgres psql -U monitor -d arbitrage_monitor -c "\l+"
```

## Monitoring

### Health Checks

All services have health checks configured:

```bash
# Check service health
docker-compose ps

# Expected output:
# NAME                  STATUS
# arbitrage-monitor     Up (healthy)
# arbitrage-postgres    Up (healthy)
# arbitrage-redis       Up (healthy)
```

### Application Health
```bash
curl http://localhost:8000/api/v1/health
```

### Prometheus Metrics
```bash
curl http://localhost:9090/metrics
```

### View Resource Usage
```bash
docker stats
```

## Troubleshooting

### Monitor Service Won't Start

1. **Check logs**
   ```bash
   docker-compose logs monitor
   ```

2. **Verify database connection**
   ```bash
   docker-compose exec postgres psql -U monitor -d arbitrage_monitor -c "SELECT 1;"
   ```

3. **Check environment variables**
   ```bash
   docker-compose exec monitor env | grep -E "(DATABASE|REDIS|RPC)"
   ```

### Database Connection Issues

1. **Ensure postgres is healthy**
   ```bash
   docker-compose ps postgres
   ```

2. **Check postgres logs**
   ```bash
   docker-compose logs postgres
   ```

3. **Verify network connectivity**
   ```bash
   docker-compose exec monitor ping postgres
   ```

### RPC Connection Issues

1. **Test RPC endpoints manually**
   ```bash
   curl -X POST -H "Content-Type: application/json" \
     --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
     https://bsc-dataseed.bnbchain.org
   ```

2. **Check monitor logs for RPC errors**
   ```bash
   docker-compose logs monitor | grep -i rpc
   ```

### High Memory Usage

1. **Check container stats**
   ```bash
   docker stats --no-stream
   ```

2. **Adjust PostgreSQL memory settings** (add to docker-compose.yml)
   ```yaml
   postgres:
     command: postgres -c shared_buffers=256MB -c max_connections=100
   ```

### Disk Space Issues

1. **Check volume sizes**
   ```bash
   docker system df -v
   ```

2. **Clean up old data**
   ```bash
   # Remove unused images
   docker image prune -a
   
   # Remove unused volumes (⚠️ careful!)
   docker volume prune
   ```

## Production Deployment

### Security Hardening

1. **Use strong passwords**
   ```bash
   # Generate secure password
   openssl rand -base64 32
   ```

2. **Restrict network access**
   ```yaml
   # In docker-compose.yml, remove port mappings for internal services
   postgres:
     # ports:
     #   - "5432:5432"  # Remove this line
   ```

3. **Use secrets management**
   ```bash
   # Use Docker secrets instead of environment variables
   echo "my_secure_password" | docker secret create db_password -
   ```

4. **Enable TLS for API**
   - Use a reverse proxy (nginx/traefik) with SSL certificates
   - Configure HTTPS in production

### Performance Tuning

1. **Increase database connections**
   ```yaml
   monitor:
     environment:
       DB_POOL_MIN_SIZE: 10
       DB_POOL_MAX_SIZE: 50
   ```

2. **Optimize PostgreSQL**
   ```yaml
   postgres:
     command: |
       postgres
       -c shared_buffers=512MB
       -c effective_cache_size=2GB
       -c maintenance_work_mem=128MB
       -c max_connections=200
   ```

3. **Add resource limits**
   ```yaml
   monitor:
     deploy:
       resources:
         limits:
           cpus: '2'
           memory: 4G
         reservations:
           cpus: '1'
           memory: 2G
   ```

### Scaling

For high-throughput scenarios:

1. **Run multiple monitor instances**
   ```bash
   docker-compose up -d --scale monitor=3
   ```

2. **Add load balancer** (nginx example)
   ```yaml
   nginx:
     image: nginx:alpine
     ports:
       - "80:80"
     volumes:
       - ./nginx.conf:/etc/nginx/nginx.conf:ro
     depends_on:
       - monitor
   ```

### Backup Strategy

1. **Automated backups**
   ```bash
   # Add to crontab
   0 2 * * * docker-compose exec -T postgres pg_dump -U monitor arbitrage_monitor | gzip > /backups/arbitrage_$(date +\%Y\%m\%d).sql.gz
   ```

2. **Volume backups**
   ```bash
   # Backup volumes
   docker run --rm -v arbitrage_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_data.tar.gz /data
   ```

## API Usage Examples

### Authentication
```bash
# All API requests require X-API-Key header
curl -H "X-API-Key: your_api_key" http://localhost:8000/api/v1/chains
```

### Query Opportunities
```bash
curl -H "X-API-Key: your_api_key" \
  "http://localhost:8000/api/v1/opportunities?chain_id=56&min_profit=1000&limit=10"
```

### Query Transactions
```bash
curl -H "X-API-Key: your_api_key" \
  "http://localhost:8000/api/v1/transactions?chain_id=137&min_swaps=2&limit=20"
```

### WebSocket Connection
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/v1/stream');

ws.onopen = () => {
  // Subscribe to opportunities
  ws.send(JSON.stringify({
    action: 'subscribe',
    channel: 'opportunities',
    filters: { chain_id: 56, min_profit: 5000 }
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('New opportunity:', data);
};
```

## Support

For issues and questions:
- Check logs: `docker-compose logs -f`
- Review health status: `docker-compose ps`
- Verify configuration: Check `.env` file
- Test RPC endpoints: Ensure they're accessible

## License

See LICENSE file for details.
