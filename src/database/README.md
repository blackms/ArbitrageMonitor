# Database Module

This module provides PostgreSQL database management for the Multi-Chain Arbitrage Monitor.

## Features

- **Connection Pooling**: Efficient connection management (min 5, max 20 connections)
- **Retry Logic**: Automatic retry for transient failures (3 attempts with exponential backoff)
- **Parameterized Queries**: SQL injection prevention
- **Transaction Support**: Multi-table updates with rollback
- **Comprehensive Schema**: Tables for chains, opportunities, transactions, arbitrageurs, and statistics

## Components

### Schema (`schema.py`)

Defines the complete PostgreSQL schema including:
- **chains**: Blockchain configuration and status
- **opportunities**: Detected pool imbalances
- **transactions**: Arbitrage transactions with 2+ swaps
- **arbitrageurs**: Trader profiles and statistics
- **chain_stats**: Hourly aggregated statistics

Key features:
- Foreign key constraints for referential integrity
- Check constraints for data validation
- Indexes for high-frequency queries
- Automatic timestamp updates via triggers

### Models (`models.py`)

Data classes for database entities:
- `Opportunity`: Pool imbalance opportunity
- `ArbitrageTransaction`: Multi-hop arbitrage transaction
- `Arbitrageur`: Trader profile with statistics
- Filter classes for querying: `OpportunityFilters`, `TransactionFilters`, `ArbitrageurFilters`

### Manager (`manager.py`)

`DatabaseManager` class provides:
- Connection pool management
- CRUD operations for all entities
- Query methods with filtering
- Automatic retry logic
- Structured logging

## Usage

### Basic Setup

```python
from src.database import DatabaseManager

# Initialize manager
db_manager = DatabaseManager(
    database_url="postgresql://user:pass@localhost/db",
    min_pool_size=5,
    max_pool_size=20
)

# Connect and initialize schema
await db_manager.connect()
await db_manager.initialize_schema()
```

### Saving Data

```python
from datetime import datetime
from decimal import Decimal
from src.database import Opportunity, ArbitrageTransaction

# Save opportunity
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
opportunity_id = await db_manager.save_opportunity(opportunity)

# Save transaction
transaction = ArbitrageTransaction(
    chain_id=56,
    tx_hash="0x1234...",
    from_address="0xabcd...",
    block_number=12345678,
    block_timestamp=datetime.utcnow(),
    gas_price_gwei=Decimal("5.0"),
    gas_used=250000,
    gas_cost_native=Decimal("0.00125"),
    gas_cost_usd=Decimal("0.375"),
    swap_count=3,
    strategy="3-hop",
    pools_involved=["0xpool1", "0xpool2", "0xpool3"],
    tokens_involved=["WBNB", "BUSD", "USDT"],
    detected_at=datetime.utcnow(),
)
tx_id = await db_manager.save_transaction(transaction)

# Update arbitrageur
await db_manager.update_arbitrageur(
    address="0xabcd...",
    chain_id=56,
    tx_data={
        "success": True,
        "profit_usd": Decimal("1500.0"),
        "gas_spent_usd": Decimal("10.0"),
        "gas_price_gwei": Decimal("5.0"),
        "strategy": "3-hop",
    }
)
```

### Querying Data

```python
from src.database import OpportunityFilters, TransactionFilters, ArbitrageurFilters

# Query opportunities
opportunities = await db_manager.get_opportunities(
    OpportunityFilters(
        chain_id=56,
        min_profit=Decimal("10000.0"),
        limit=100
    )
)

# Query transactions
transactions = await db_manager.get_transactions(
    TransactionFilters(
        chain_id=56,
        min_swaps=3,
        strategy="3-hop",
        limit=50
    )
)

# Query arbitrageurs
arbitrageurs = await db_manager.get_arbitrageurs(
    ArbitrageurFilters(
        chain_id=56,
        min_transactions=10,
        sort_by="total_profit_usd",
        sort_order="DESC",
        limit=20
    )
)
```

### Cleanup

```python
await db_manager.disconnect()
```

## Testing

### Unit Tests

Run unit tests (no database required):

```bash
poetry run pytest tests/test_database_models.py -v
```

### Integration Tests

Integration tests require a PostgreSQL test database.

#### Setup Test Database with Docker

```bash
docker run --name postgres-test \
    -e POSTGRES_DB=arbitrage_monitor_test \
    -e POSTGRES_USER=monitor \
    -e POSTGRES_PASSWORD=password \
    -p 5432:5432 \
    -d postgres:15
```

#### Run Integration Tests

```bash
# Run all integration tests
poetry run pytest tests/test_database.py -v -m integration

# Or set custom database URL
TEST_DATABASE_URL="postgresql://user:pass@host/db" \
    poetry run pytest tests/test_database.py -v -m integration
```

#### Skip Integration Tests

```bash
# Run all tests except integration tests
poetry run pytest -v -m "not integration"
```

## Schema Management

### Initialize Schema

```python
await db_manager.initialize_schema()
```

### Manual Schema Creation

```sql
-- Get schema SQL
from src.database import get_schema_sql
schema_sql = get_schema_sql()

-- Execute in PostgreSQL
psql -U monitor -d arbitrage_monitor -f schema.sql
```

## Performance Considerations

### Connection Pooling

- Default: min 5, max 20 connections
- Adjust based on workload and database capacity
- Monitor pool usage with `get_pool_size()` and `get_pool_free_size()`

### Indexes

All high-frequency queries are indexed:
- Chain ID + Block Number (DESC)
- Profit amounts (DESC)
- Timestamps (DESC)
- Address lookups

### Query Optimization

- Use filters to limit result sets
- Leverage pagination (limit/offset)
- Results are ordered by `detected_at DESC` by default

## Error Handling

### Automatic Retry

Transient failures are automatically retried:
- 3 attempts with exponential backoff (0.5s, 1s, 2s)
- Applies to all database operations
- Logs retry attempts with context

### Constraint Violations

Check constraints prevent invalid data:
- `swap_count >= 2` for transactions
- `imbalance_pct >= 0` for opportunities
- `total_transactions = successful + failed` for arbitrageurs

### Connection Failures

- Logs connection errors with context
- Raises exception after retry exhaustion
- Supports graceful shutdown with `disconnect()`

## Monitoring

### Structured Logging

All operations are logged with structured context:

```python
logger.info("opportunity_saved",
    opportunity_id=123,
    chain_id=56,
    profit_usd=15000.50
)
```

### Pool Metrics

Monitor connection pool health:

```python
pool_size = await db_manager.get_pool_size()
free_connections = await db_manager.get_pool_free_size()
```

## Security

- **Parameterized Queries**: All queries use parameters to prevent SQL injection
- **Input Validation**: Pydantic models validate all data
- **Least Privilege**: Application should use read/write user, not superuser
- **TLS Encryption**: Configure PostgreSQL to require TLS connections
