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
- **Profit Calculator**: Calculates gross profit, gas costs, net profit, and ROI from arbitrage transactions
- **Token Flow Analysis**: Extracts input/output amounts from multi-hop swap sequences
- **Pool Scanner**: Real-time monitoring of liquidity pools for arbitrage opportunities using CPMM imbalance detection

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

- **Swap Event Signature Filtering**: Uses cryptographic event signatures (`Web3.keccak`) to identify only genuine Swap events, filtering out Transfer, Sync, Approval, and other event types
- **Multi-Hop Detection**: Classifies transactions with 2+ swaps as arbitrage opportunities
- **DEX Router Validation**: Verifies transactions target known DEX router addresses (PancakeSwap, QuickSwap, etc.)
- **Method Signature Recognition**: Validates swap function calls including Uniswap V2/V3, Balancer, and fee-on-transfer token methods
- **Comprehensive Testing**: Full test coverage for event signature calculation, swap counting, and arbitrage classification

### Swap Event Detection

The analyzer calculates the Swap event signature using:
```python
SWAP_EVENT_SIGNATURE = Web3.keccak(
    text="Swap(address,uint256,uint256,uint256,uint256,address)"
).hex()
```

This ensures only actual Swap events are counted by comparing the first topic (`topics[0]`) of each log entry against the expected signature. The test suite verifies:
- Correct signature calculation (66 characters: `0x` + 64 hex chars)
- Accurate filtering of Swap events from mixed event logs
- Single swap transactions are NOT classified as arbitrage
- Multi-hop transactions (2+ swaps) ARE classified as arbitrage

### Chain Connector Features

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

## Profit Calculator

The profit calculator module provides comprehensive profit analysis for arbitrage transactions:

### Features

- **Token Flow Extraction**: Identifies input amount from first swap and output amount from last swap
- **Gross Profit Calculation**: Computes profit as `output_amount - input_amount` in native tokens
- **Gas Cost Analysis**: Calculates gas costs using `gasUsed * effectiveGasPrice` from transaction receipts
- **Net Profit Calculation**: Determines actual profit after deducting gas costs
- **ROI Calculation**: Computes return on investment as `(net_profit / input_amount) * 100`
- **USD Conversion**: Converts all amounts to USD using configurable native token prices
- **Detailed Gas Metrics**: Tracks gas used, gas price (wei and gwei), and costs in native token and USD

### Data Classes

The module provides structured data classes for profit analysis:

```python
@dataclass
class TokenFlow:
    """Token flow through swap sequence"""
    input_amount: int           # Input amount in wei
    output_amount: int          # Output amount in wei
    input_token_index: int      # 0 or 1 (which token in first pool)
    output_token_index: int     # 0 or 1 (which token in last pool)

@dataclass
class GasCost:
    """Gas cost information"""
    gas_used: int               # Total gas units consumed
    gas_price_wei: int          # Effective gas price in wei
    gas_price_gwei: Decimal     # Gas price in gwei (readable)
    gas_cost_native: Decimal    # Gas cost in native token (BNB/MATIC)
    gas_cost_usd: Decimal       # Gas cost in USD

@dataclass
class ProfitData:
    """Complete profit calculation"""
    gross_profit_native: Decimal    # Profit before gas costs
    gross_profit_usd: Decimal       # Gross profit in USD
    gas_cost: GasCost              # Detailed gas cost info
    net_profit_native: Decimal     # Profit after gas costs
    net_profit_usd: Decimal        # Net profit in USD
    roi_percentage: Decimal        # Return on investment %
    input_amount_native: Decimal   # Input amount in native token
    output_amount_native: Decimal  # Output amount in native token
```

### Usage Example

```python
from src.detectors.profit_calculator import ProfitCalculator
from src.detectors.transaction_analyzer import TransactionAnalyzer
from decimal import Decimal

# Initialize calculator with chain info and native token price
calculator = ProfitCalculator(
    chain_name="BSC",
    native_token_usd_price=Decimal("300.0")  # BNB price
)

# Parse swap events from transaction receipt
analyzer = TransactionAnalyzer("BSC", dex_routers)
swaps = analyzer.parse_swap_events(receipt)

# Calculate profit
profit_data = calculator.calculate_profit(swaps, receipt)

if profit_data:
    print(f"Gross Profit: ${profit_data.gross_profit_usd:.2f}")
    print(f"Gas Cost: ${profit_data.gas_cost.gas_cost_usd:.2f}")
    print(f"Net Profit: ${profit_data.net_profit_usd:.2f}")
    print(f"ROI: {profit_data.roi_percentage:.2f}%")
    print(f"Gas Price: {profit_data.gas_cost.gas_price_gwei:.2f} gwei")
```

### Token Flow Extraction

The calculator analyzes swap sequences to determine token flow:

1. **First Swap**: Identifies input by finding non-zero `amount0In` or `amount1In`
2. **Last Swap**: Identifies output by finding non-zero `amount0Out` or `amount1Out`
3. **Validation**: Returns `None` if no valid input/output amounts found

This handles complex multi-hop arbitrage paths like:
- 2-hop: Token A → Token B → Token A
- 3-hop: Token A → Token B → Token C → Token A
- 4-hop: Token A → Token B → Token C → Token D → Token A

### Profit Calculation Formula

```
gross_profit = output_amount - input_amount
gas_cost = gas_used × effective_gas_price
net_profit = gross_profit - gas_cost
roi = (net_profit / input_amount) × 100
```

All amounts are converted from wei (10^18) to native token units and then to USD using the configured native token price.

### Logging

The calculator provides structured logging for debugging and monitoring:

- `token_flow_extracted`: Logs input/output amounts and swap count
- `gas_cost_calculated`: Logs gas metrics (used, price, costs)
- `profit_calculated`: Logs complete profit analysis with ROI
- `extract_token_flow_empty_swaps`: Warning for empty swap lists
- `extract_token_flow_no_input`: Warning when no input amount found
- `extract_token_flow_no_output`: Warning when no output amount found

## Pool Scanner

The pool scanner module monitors liquidity pools in real-time to detect arbitrage opportunities through pool imbalances:

### Features

- **CPMM Imbalance Detection**: Uses Constant Product Market Maker formula (k = x × y) to identify pool imbalances
- **Real-time Reserve Monitoring**: Queries pool reserves using `getReserves()` function on Uniswap V2-style pools
- **Profit Potential Calculation**: Estimates profit after accounting for swap fees (default 0.3%)
- **Configurable Thresholds**: Customizable imbalance threshold (default 5%) and scan intervals
- **Small Opportunity Classification**: Tracks opportunities in the $10K-$100K range for small trader viability analysis
- **Automatic Persistence**: Saves detected opportunities to database with full context
- **Async Scanning Loop**: Non-blocking continuous monitoring with configurable intervals
- **Multi-Pool Support**: Scans multiple pools per chain simultaneously

### CPMM Imbalance Formula

The scanner uses the Constant Product Market Maker invariant to detect imbalances:

```
k = reserve0 × reserve1 (constant product)
optimal_reserve0 = optimal_reserve1 = √k
imbalance_pct = max(|reserve0 - optimal| / optimal, |reserve1 - optimal| / optimal) × 100
profit_potential = (imbalance_pct - swap_fee_pct) × reserve_size
```

When a pool's reserves deviate from the optimal balanced state, it creates an arbitrage opportunity. The scanner calculates:

1. **Pool Invariant (k)**: Product of both reserves
2. **Optimal Reserves**: Square root of k (balanced state)
3. **Imbalance Percentage**: Maximum deviation from optimal state
4. **Profit Potential**: Excess imbalance after deducting swap fees

### Data Classes

```python
@dataclass
class PoolReserves:
    """Pool reserve data from getReserves() call"""
    pool_address: str
    pool_name: str
    reserve0: int              # Reserve amount for token0
    reserve1: int              # Reserve amount for token1
    block_timestamp: int       # Last update timestamp

@dataclass
class ImbalanceData:
    """Pool imbalance calculation results"""
    imbalance_pct: Decimal           # Imbalance percentage
    profit_potential_usd: Decimal    # Estimated profit in USD
    profit_potential_native: Decimal # Estimated profit in native token
    optimal_reserve0: Decimal        # Optimal reserve for token0
    optimal_reserve1: Decimal        # Optimal reserve for token1
```

### Usage Example

```python
from src.detectors.pool_scanner import PoolScanner
from src.chains import BSCConnector
from src.database import DatabaseManager
from src.config.models import ChainConfig
from decimal import Decimal

# Configure BSC with pools to monitor
config = ChainConfig(
    name="BSC",
    chain_id=56,
    rpc_urls=["https://bsc-dataseed.bnbchain.org"],
    block_time_seconds=3.0,
    native_token="BNB",
    native_token_usd=Decimal("300.0"),
    dex_routers={...},
    pools={
        "WBNB-BUSD": "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
        "WBNB-USDT": "0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE",
    },
)

# Initialize components
connector = BSCConnector(config)
db_manager = DatabaseManager("postgresql://...")
await db_manager.connect()

# Create pool scanner
scanner = PoolScanner(
    chain_connector=connector,
    config=config,
    database_manager=db_manager,
    scan_interval_seconds=3.0,      # Scan every 3 seconds (BSC block time)
    imbalance_threshold_pct=5.0,    # Detect imbalances >= 5%
    swap_fee_pct=0.3,               # Account for 0.3% swap fee
    small_opp_min_usd=10000.0,      # Min profit for small opportunity ($10K)
    small_opp_max_usd=100000.0,     # Max profit for small opportunity ($100K)
)

# Start continuous scanning
await scanner.start()

# Scanner runs in background, detecting opportunities...
# Opportunities are automatically saved to database

# Stop scanning when done
await scanner.stop()
```

### Manual Pool Scanning

For one-time scans without the background loop:

```python
# Scan all pools once
opportunities = await scanner.scan_pools()

for opp in opportunities:
    print(f"Pool: {opp.pool_name}")
    print(f"Imbalance: {opp.imbalance_pct:.2f}%")
    print(f"Profit Potential: ${opp.profit_usd:.2f}")
    print(f"Block: {opp.block_number}")
```

### Reserve Querying

Query individual pool reserves:

```python
reserves = await scanner.get_pool_reserves(
    pool_address="0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
    pool_name="WBNB-BUSD"
)

if reserves:
    print(f"Reserve0: {reserves.reserve0}")
    print(f"Reserve1: {reserves.reserve1}")
    print(f"Timestamp: {reserves.block_timestamp}")
```

### Imbalance Calculation

Calculate imbalance for specific reserves:

```python
imbalance_data = scanner.calculate_imbalance(
    reserve0=1000000000000000000000,  # 1000 tokens
    reserve1=300000000000000000000000, # 300000 tokens
)

if imbalance_data:
    print(f"Imbalance: {imbalance_data.imbalance_pct:.2f}%")
    print(f"Profit (USD): ${imbalance_data.profit_potential_usd:.2f}")
    print(f"Optimal Reserve0: {imbalance_data.optimal_reserve0}")
    print(f"Optimal Reserve1: {imbalance_data.optimal_reserve1}")
```

### Configuration Options

The pool scanner supports flexible configuration:

- **scan_interval_seconds**: Time between scans (default 3.0 for BSC, 2.0 for Polygon)
- **imbalance_threshold_pct**: Minimum imbalance to detect (default 5.0%)
- **swap_fee_pct**: DEX swap fee to account for (default 0.3%)
- **small_opp_min_usd**: Minimum profit for small opportunity classification (default $10,000)
- **small_opp_max_usd**: Maximum profit for small opportunity classification (default $100,000)
- **database_manager**: Optional database for persisting opportunities

### Scan Intervals by Chain

Recommended scan intervals based on block times:

- **BSC**: 3 seconds (matches ~3s block time)
- **Polygon**: 2 seconds (matches ~2s block time)
- **Ethereum**: 12 seconds (matches ~12s block time)

### Small Opportunity Tracking

The scanner tracks opportunities in the $10K-$100K profit range to analyze viability for small traders:

```python
# Check if an opportunity qualifies as "small"
is_small = scanner.is_small_opportunity(Decimal("50000"))  # Returns True

# Get count of small opportunities detected
small_count = scanner.get_small_opportunity_count()
print(f"Small opportunities detected: {small_count}")
```

This data is used by the StatsAggregator to calculate capture rates and competition levels specifically for small traders.

### Logging

The scanner provides structured logging for monitoring:

- `pool_scanner_started`: Scanner initialization with configuration (includes small opportunity range)
- `pool_reserves_fetched`: Successful reserve query with amounts
- `opportunity_detected`: Opportunity found with imbalance and profit details (includes `is_small_opportunity` flag)
- `pool_scanner_stopped`: Scanner shutdown
- `pool_reserves_fetch_failed`: Warning when reserve query fails
- `pool_reserves_zero`: Warning when reserves are zero
- `failed_to_get_block_number`: Error getting current block
- `failed_to_save_opportunity`: Error persisting to database
- `pool_scan_error`: General scanning error

### Error Handling

The scanner handles errors gracefully:

- **RPC Failures**: Logs warning and continues to next pool
- **Zero Reserves**: Skips calculation and logs warning
- **Database Errors**: Logs error but continues scanning
- **Block Number Errors**: Returns empty opportunities list

The background scanning loop continues running even if individual scans fail, ensuring continuous monitoring.

### Integration with Database

When a database manager is provided, opportunities are automatically persisted:

```python
# Opportunity saved to database includes:
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
    captured=False,  # Not yet captured by arbitrageur
)
```

### Performance Considerations

- **Async Operations**: All RPC calls are async for non-blocking execution
- **Batch Scanning**: Scans all pools in parallel within each interval
- **Configurable Intervals**: Adjust scan frequency based on chain block time
- **Selective Persistence**: Only saves opportunities exceeding threshold
- **Connection Pooling**: Leverages chain connector's RPC connection management

## Chain Monitor

The chain monitor module orchestrates the complete blockchain monitoring pipeline, from block detection to transaction analysis and data persistence:

### Features

- **Real-time Block Monitoring**: Polls for new blocks every 1 second
- **Transaction Filtering**: Filters transactions targeting known DEX routers
- **Arbitrage Detection**: Analyzes transactions using TransactionAnalyzer
- **Profit Calculation**: Calculates profit metrics using ProfitCalculator
- **Data Persistence**: Saves arbitrage transactions to database
- **Arbitrageur Tracking**: Updates arbitrageur profiles with transaction data
- **Graceful Error Handling**: Continues monitoring despite RPC or parsing errors
- **Async Task Management**: Non-blocking operation with proper shutdown handling

### Architecture

The ChainMonitor orchestrates multiple components:

1. **ChainConnector**: Blockchain RPC interaction with failover
2. **TransactionAnalyzer**: Swap event detection and arbitrage classification
3. **ProfitCalculator**: Profit and gas cost calculations
4. **DatabaseManager**: Data persistence and querying

### Usage Example

```python
from src.monitors.chain_monitor import ChainMonitor
from src.chains import BSCConnector
from src.detectors import TransactionAnalyzer, ProfitCalculator
from src.database import DatabaseManager
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
        "PancakeSwap V3": "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
    },
    pools={
        "WBNB-BUSD": "0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16",
    },
)

# Initialize components
connector = BSCConnector(config)
analyzer = TransactionAnalyzer("BSC", config.dex_routers)
calculator = ProfitCalculator("BSC", config.native_token_usd)
db_manager = DatabaseManager("postgresql://...")
await db_manager.connect()

# Create chain monitor
monitor = ChainMonitor(
    chain_connector=connector,
    transaction_analyzer=analyzer,
    profit_calculator=calculator,
    database_manager=db_manager,
)

# Start monitoring
await monitor.start()

# Monitor runs in background, detecting and persisting arbitrage transactions...

# Stop monitoring when done
await monitor.stop()
```

### Processing Pipeline

For each new block, the monitor:

1. **Fetches Block Data**: Gets full block with all transactions
2. **Filters Transactions**: Keeps only transactions to DEX routers
3. **Gets Receipt**: Fetches transaction receipt for event logs
4. **Detects Arbitrage**: Uses TransactionAnalyzer to check if transaction is arbitrage
5. **Parses Swaps**: Extracts swap events from transaction logs
6. **Calculates Profit**: Computes gross/net profit, gas costs, and ROI
7. **Persists Data**: Saves ArbitrageTransaction to database
8. **Updates Profile**: Updates arbitrageur statistics

### Transaction Data

Detected arbitrage transactions include:

```python
ArbitrageTransaction(
    chain_id=56,
    tx_hash="0x123...",
    from_address="0xabc...",
    block_number=12345678,
    block_timestamp=datetime(...),
    gas_price_gwei=Decimal("5.0"),
    gas_used=150000,
    gas_cost_native=Decimal("0.00075"),
    gas_cost_usd=Decimal("0.225"),
    swap_count=3,
    strategy="3-hop",
    profit_gross_usd=Decimal("30.0"),
    profit_net_usd=Decimal("29.775"),
    pools_involved=["0x58F...", "0x16b..."],
    tokens_involved=[],
    detected_at=datetime.utcnow(),
)
```

### Strategy Classification

Transactions are classified by hop count:

- **2-hop**: Token A → Token B → Token A
- **3-hop**: Token A → Token B → Token C → Token A
- **4-hop**: Token A → Token B → Token C → Token D → Token A
- **N-hop**: For transactions with more than 4 swaps

### Logging

The monitor provides comprehensive structured logging:

- `chain_monitor_started`: Monitor initialization
- `chain_monitor_loop_started`: Monitoring loop begins
- `chain_monitor_initialized`: First block sync point set
- `new_blocks_detected`: New blocks available for processing
- `processing_block`: Block processing started
- `block_processed`: Block processing completed
- `arbitrage_transaction_processed`: Arbitrage transaction detected and saved
- `arbitrage_insufficient_swap_events`: Warning when swap count is invalid
- `transaction_processing_error`: Error processing specific transaction
- `block_processing_error`: Error processing entire block
- `chain_monitor_loop_error`: Error in main monitoring loop
- `chain_monitor_stopped`: Monitor shutdown
- `chain_monitor_loop_cancelled`: Monitoring loop cancelled
- `chain_monitor_loop_exited`: Monitoring loop exited

### Error Handling

The monitor handles errors at multiple levels:

- **RPC Errors**: Automatic failover via ChainConnector
- **Transaction Errors**: Logs error and continues to next transaction
- **Block Errors**: Logs error and continues to next block
- **Loop Errors**: Logs error and continues monitoring after 1 second delay

This ensures continuous monitoring even when individual operations fail.

### Graceful Shutdown

The monitor supports graceful shutdown:

```python
# Stop monitoring
await monitor.stop()

# This will:
# 1. Set _running flag to False
# 2. Cancel the monitoring task
# 3. Wait for task cancellation
# 4. Log shutdown events
```

### Performance Characteristics

- **Poll Interval**: 1 second (configurable via sleep duration)
- **Block Processing**: Sequential to maintain order
- **Transaction Processing**: Sequential within each block
- **Non-blocking**: All I/O operations are async
- **Memory Efficient**: Processes one block at a time
- **Fault Tolerant**: Continues despite individual failures

### Integration with Other Components

The ChainMonitor integrates seamlessly with:

- **ChainConnector**: RPC interaction with automatic failover
- **TransactionAnalyzer**: Accurate arbitrage detection with zero false positives
- **ProfitCalculator**: Complete profit analysis with gas costs
- **DatabaseManager**: Persistent storage with connection pooling
- **PoolScanner**: Can run in parallel for opportunity detection

## Development

Run all tests:
```bash
poetry run pytest
```

Run specific test modules:
```bash
# Test chain connectors (RPC failover, circuit breaker)
poetry run pytest tests/test_chain_connector.py -v

# Test transaction analyzer (swap detection, arbitrage classification)
poetry run pytest tests/test_transaction_analyzer.py -v

# Test profit calculator (token flow, gas costs, profit calculation)
poetry run pytest tests/test_profit_calculator.py -v

# Test pool scanner (reserve querying, CPMM imbalance detection, profit estimation)
poetry run pytest tests/test_pool_scanner.py -v

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
