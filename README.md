# Multi-Chain Arbitrage Monitor

Production-ready system to detect, track, and analyze real multi-hop arbitrage opportunities and transactions across BSC and Polygon blockchains.

## Features

### Blockchain Integration
- Real-time monitoring of BSC and Polygon blockchains
- Automatic RPC failover with circuit breaker pattern (5 failure threshold, 60s timeout)
- Connection recovery with exponential backoff
- Support for multiple RPC endpoints per chain
- DEX router recognition for PancakeSwap, QuickSwap, SushiSwap, Uniswap V3, and more

### Detection & Analysis
- **Accurate Swap Event Detection**: Filters events by signature to count only Swap events, excluding Transfer, Sync, and Approval events
- **Arbitrage Classification**: Identifies multi-hop arbitrage transactions (2+ swaps) targeting known DEX routers
- **Swap Event Parsing**: Extracts token amounts (amount0In, amount1In, amount0Out, amount1Out) from event logs
- **DEX Router Validation**: Verifies transactions target recognized DEX router addresses
- **Method Signature Recognition**: Validates swap function calls (supports Uniswap V2/V3, Balancer, and more)
- Pool imbalance detection using CPMM formulas
- Real profit calculation including gas costs

### Data Management
- PostgreSQL database with connection pooling (5-20 connections)
- Automatic retry logic for transient failures (3 attempts with exponential backoff)
- Comprehensive data models for opportunities, transactions, and arbitrageurs
- Efficient querying with indexes and filtering

### API & Monitoring
- REST API and WebSocket streaming
- Comprehensive monitoring and alerting
- Structured logging with contextual information

## Project Structure

```
multi-chain-arbitrage-monitor/
├── src/
│   ├── chains/          # Blockchain interaction layer
│   ├── detectors/       # Arbitrage detection and analysis
│   ├── database/        # Database management
│   ├── api/             # REST API and WebSocket server
│   ├── config/          # Configuration models
│   └── utils/           # Utility functions
├── tests/               # Test suite
├── pyproject.toml       # Poetry dependencies
└── .env.example         # Environment variables template
```

## Setup

1. Install dependencies with Poetry:
```bash
poetry install
```

2. Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Set up PostgreSQL and Redis (using Docker):
```bash
docker-compose up -d postgres redis
```

4. Initialize the database schema:
```python
from src.database import DatabaseManager
from src.config import Settings

settings = Settings()
db_manager = DatabaseManager(settings.database_url)
await db_manager.connect()
await db_manager.initialize_schema()
```

## Transaction Analyzer

The transaction analyzer module provides accurate arbitrage detection with zero false positives:

### Features

- **Swap Event Signature Filtering**: Uses 

- **RPC Failover**: Automatic failover to backup RPC endpoints on connection failures
- **Circuit Breaker**: Prevents cascading failures with configurable thresholds (default: 5 failures, 60s timeout)
- **Connection Recovery**: Automatic retry with exponential backoff for transient errors
- **Multi-Chain Support**: BSC and Polygon connectors with chain-specific DEX configurations
- **DEX Router Recognition**: Built-in validation for known DEX router addresses

### Supported DEXs

**BSC:**
- PancakeSwap V2/V3
- BiSwap
- ApeSwap
- THENA

**Polygon:**
- QuickSwap
- SushiSwap
- Uniswap V3
- Balancer

### Quick Example

```python
from src.chains import BSCConnector
from src.config.models import ChainConfig
from decimal import Decimal

# Configure BSC
config = ChainConfig(
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
    },
    pools={
        "WBNB-BUSD": "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
    },
)

# Initialize connector
connector = BSCConnector(config)

# Get latest block (with automatic retry and failover)
block_number = await connector.get_latest_block()

# Get block details
block = await connector.get_block(block_number)

# Get transaction receipt
receipt = await connector.get_transaction_receipt("0x123...")

# Check if address is a known DEX router
is_dex = connector.is_dex_router("0x10ED43C718714eb63d5aA57B78B54704E256024E")
```

## Database Module

The database module provides comprehensive PostgreSQL integration with:

- **Connection Pooling**: Efficient management with 5-20 connections
- **Automatic Retry**: 3 attempts with exponential backoff for transient failures
- **Data Models**: `Opportunity`, `ArbitrageTransaction`, `Arbitrageur` with filter classes
- **Query Methods**: Flexible filtering, pagination, and sorting
- **Schema Management**: Automated schema initialization with indexes and constraints

See [src/database/README.md](src/database/README.md) for detailed documentation.

### Quick Example

```python
from src.database import DatabaseManager, Opportunity, OpportunityFilters
from decimal import Decimal
from datetime import datetime

# Initialize and connect
db = DatabaseManager("postgresql://user:pass@localhost/db")
await db.connect()

# Save an opportunity
opportunity = Opportunity(
    chain_id=56,
    pool_name="WBNB-BUSD",
    pool_address="0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
    imbalance_pct=Decimal("7.5"),
    profit_usd=Decimal("15000.50"),
    profit_native=Decimal("50.0"),
    reserve0=Decimal("1000000.0"),
    reserve1=Decimal("300000000.0"),
    block_number=12345678,
    detected_at=datetime.utcnow(),
)
opportunity_id = await db.save_opportunity(opportunity)

# Query opportunities
opportunities = await db.get_opportunities(
    OpportunityFilters(chain_id=56, min_profit=Decimal("10000.0"))
)
```

## Development

Run all tests:
```bash
poetry run pytest
```

Run specific test modules:
```bash
# Test chain connectors (RPC failover, circuit breaker)
poetry run pytest tests/test_chain_connector.py -v

# Test database integration
poetry run pytest tests/test_database.py -v

# Test configuration
poetry run pytest tests/test_config.py -v
```

Run tests excluding integration tests (no database required):
```bash
poetry run pytest -m "not integration"
```

Run integration tests (requires PostgreSQL):
```bash
# Start test database
docker run --name postgres-test \
    -e POSTGRES_DB=arbitrage_monitor_test \
    -e POSTGRES_USER=monitor \
    -e POSTGRES_PASSWORD=password \
    -p 5432:5432 \
    -d postgres:15

# Run integration tests
poetry run pytest tests/test_database.py -v -m integration
```

Format code:
```bash
poetry run black src tests
```

Lint code:
```bash
poetry run ruff check src tests
```

## Requirements

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- BSC and Polygon RPC endpoints

## License

MIT
