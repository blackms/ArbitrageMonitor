# Implementation Plan

- [x] 1. Set up project structure and core configuration
  - Create Python project with Poetry for dependency management
  - Set up directory structure: chains/, detectors/, database/, api/, utils/
  - Create configuration models for chain settings and monitor config
  - Set up environment variable loading with python-dotenv
  - Configure structured logging with structlog
  - _Requirements: 1.1, 1.3_

- [x] 2. Implement database schema and connection management
  - [x] 2.1 Create PostgreSQL schema with all tables
    - Write SQL schema for chains, opportunities, transactions, arbitrageurs, chain_stats tables
    - Create indexes for high-frequency queries (chain_id, block_number, profit_usd, etc.)
    - Add foreign key constraints and check constraints
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 2.2 Implement database manager with asyncpg
    - Create DatabaseManager class with connection pooling (min 5, max 20)
    - Implement save_opportunity, save_transaction, update_arbitrageur methods
    - Implement query methods with filtering support
    - Add retry logic for transient failures (3 attempts with exponential backoff)
    - _Requirements: 6.6, 6.7, 14.3, 14.4_

  - [x] 2.3 Write database integration tests
    - Test connection pooling and concurrent writes
    - Test transaction rollback on errors
    - Test query performance with large datasets
    - _Requirements: 6.1-6.9_

- [x] 3. Implement blockchain interaction layer
  - [x] 3.1 Create base chain connector with web3.py
    - Implement ChainConnector base class with RPC connection management
    - Add automatic failover logic for backup RPC endpoints
    - Implement get_latest_block, get_block, get_transaction_receipt methods
    - Add circuit breaker pattern for RPC failures (open after 5 failures, 60s timeout)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 14.1, 14.2_

  - [x] 3.2 Implement BSC chain connector
    - Create BSCConnector class extending ChainConnector
    - Configure BSC RPC endpoints (primary and fallback)
    - Define BSC DEX router addresses (PancakeSwap V2/V3, BiSwap, ApeSwap, THENA)
    - Define BSC pool addresses (WBNB pairs)
    - _Requirements: 1.1, 1.2, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.3 Implement Polygon chain connector
    - Create PolygonConnector class extending ChainConnector
    - Configure Polygon RPC endpoints (primary and fallback)
    - Define Polygon DEX router addresses (QuickSwap, SushiSwap, Uniswap V3, Balancer)
    - Define Polygon pool addresses (WMATIC pairs)
    - _Requirements: 1.3, 1.4, 3.6, 3.7, 3.8, 3.9_

  - [x] 3.4 Write chain connector tests
    - Test RPC failover mechanism
    - Test circuit breaker behavior
    - Test connection recovery after failures
    - _Requirements: 1.1-1.7, 14.1-14.6_

- [x] 4. Implement Swap event detection and arbitrage classification
  - [x] 4.1 Create transaction analyzer with proper event signature detection
    - Calculate Swap event signature using web3.keccak(text="Swap(address,uint256,uint256,uint256,uint256,address)")
    - Implement count_swap_events method that filters by event signature (topics[0])
    - Implement parse_swap_events to extract token amounts from event data
    - Ensure only Swap events are counted, not Transfer, Sync, or Approval events
    - _Requirements: 2.1, 2.2_

  - [x] 4.2 Implement arbitrage classification logic
    - Create is_arbitrage method that checks swap_count >= 2
    - Verify transaction targets known DEX router address
    - Verify transaction uses recognized swap method signature
    - Extract method signature from transaction input data (first 4 bytes)
    - _Requirements: 2.3, 2.4, 2.5, 2.7_

  - [x] 4.3 Write comprehensive unit tests for swap detection
    - Test Swap event signature calculation matches expected value
    - Test count_swap_events with transaction containing multiple event types (should count only Swaps)
    - Test single swap transaction is NOT classified as arbitrage
    - Test multi-hop transaction (2+ swaps) IS classified as arbitrage
    - Test DEX router address validation
    - Test swap method signature recognition
    - _Requirements: 2.1, 2.2, 2.3, 2.6, 2.7_

- [x] 5. Implement profit calculation engine
  - [x] 5.1 Create profit calculator with token flow parsing
    - Implement ProfitCalculator class in src/detectors/profit_calculator.py
    - Implement extract_token_flow to identify input from first swap and output from last swap
    - Handle both amount0In/amount1In and amount0Out/amount1Out fields from SwapEvent objects
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 5.2 Implement profit and gas cost calculation
    - Calculate gross profit as output_amount - input_amount
    - Calculate gas cost as gasUsed * effectiveGasPrice from transaction receipt
    - Calculate net profit as gross_profit - gas_cost
    - Calculate ROI as (net_profit / input_amount) * 100
    - Convert native token amounts to USD using chain config native_token_usd price
    - _Requirements: 5.4, 5.5, 5.6, 5.7_

  - [x] 5.3 Write profit calculation tests
    - Test input amount extraction from first swap
    - Test output amount extraction from last swap
    - Test gross profit calculation
    - Test gas cost calculation with different gas prices
    - Test net profit calculation
    - Test ROI calculation
    - Test handling of zero input amounts
    - _Requirements: 5.1-5.7_

- [x] 6. Implement pool scanner and opportunity detector
  - [x] 6.1 Create pool scanner with reserve querying
    - Implement PoolScanner class in src/detectors/pool_scanner.py
    - Implement get_pool_reserves method to query getReserves() function on pool contracts
    - Use web3.py contract calls to fetch reserve data
    - Handle pool contract ABI for Uniswap V2-style pools
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 6.2 Implement CPMM imbalance calculation
    - Calculate pool invariant k = reserve0 * reserve1
    - Calculate optimal reserves: optimal_x = optimal_y = sqrt(k)
    - Calculate imbalance percentage: max(|reserve0 - optimal_x| / optimal_x, |reserve1 - optimal_y| / optimal_y) * 100
    - Calculate profit potential accounting for 0.3% swap fee
    - Convert profit to USD assuming token1 is stablecoin
    - _Requirements: 4.5, 4.6_

  - [x] 6.3 Implement opportunity detection and persistence
    - Scan pools every 3 seconds for BSC, 2 seconds for Polygon
    - Create Opportunity objects for imbalances > 5%
    - Save opportunities to database via DatabaseManager
    - Log opportunity detection events
    - _Requirements: 4.7, 6.6_

  - [ ]* 6.4 Write pool scanner tests
    - Test reserve retrieval from pool contracts
    - Test CPMM invariant calculation
    - Test imbalance percentage calculation
    - Test profit potential estimation
    - Test handling of zero reserves
    - _Requirements: 4.1-4.7_

- [ ] 7. Implement chain monitor orchestration
  - [ ] 7.1 Create chain monitor with block processing
    - Implement ChainMonitor class in src/monitors/chain_monitor.py
    - Implement start/stop methods with asyncio task management
    - Poll for new blocks every 1 second using ChainConnector.get_latest_block()
    - Process all transactions in each block using ChainConnector.get_block()
    - Filter transactions targeting DEX routers using ChainConnector.is_dex_router()
    - Track last synced block number in memory
    - _Requirements: 1.5, 1.6, 9.6_

  - [ ] 7.2 Implement transaction processing pipeline
    - Get transaction receipt for each filtered transaction using ChainConnector.get_transaction_receipt()
    - Pass receipt and transaction to TransactionAnalyzer.is_arbitrage() for detection
    - If arbitrage detected, parse swap events using TransactionAnalyzer.parse_swap_events()
    - Calculate profit using ProfitCalculator
    - Create ArbitrageTransaction object and save to database
    - Update arbitrageur profile using DatabaseManager.update_arbitrageur()
    - Log transaction detection events
    - _Requirements: 2.1-2.7, 5.1-5.7, 6.7, 10.1-10.8_

  - [ ] 7.3 Add error handling and graceful shutdown
    - Handle RPC errors with automatic failover (already in ChainConnector)
    - Handle parsing errors gracefully (log and continue processing)
    - Implement graceful shutdown on stop() call
    - Cancel asyncio tasks cleanly
    - Log chain monitor lifecycle events
    - _Requirements: 1.7, 9.5, 14.5, 14.6_

  - [ ]* 7.4 Write chain monitor integration tests
    - Test block detection and processing
    - Test transaction filtering by DEX router
    - Test RPC failover on connection errors
    - Test graceful error handling
    - _Requirements: 1.1-1.7, 9.1-9.6, 14.1-14.7_

- [x] 8. Implement arbitrageur tracking
  - [x] 8.1 Create arbitrageur tracker
    - Implement update_arbitrageur method in DatabaseManager (already completed)
    - On new transaction, check if arbitrageur exists (by address and chain_id)
    - If new, create arbitrageur record with first_seen timestamp
    - Update last_seen, total_transactions, successful/failed counts
    - Accumulate total_profit_usd and total_gas_spent_usd
    - Calculate avg_gas_price_gwei as running average
    - Determine preferred_strategy from transaction history (most common hop count)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

  - [x] 8.2 Write arbitrageur tracking tests
    - Test new arbitrageur creation (completed in test_database.py)
    - Test existing arbitrageur updates (completed in test_database.py)
    - Test profit accumulation (completed in test_database.py)
    - Test gas cost accumulation (completed in test_database.py)
    - Test preferred strategy calculation (completed in test_database.py)
    - _Requirements: 10.1-10.8_

- [ ] 9. Implement small trader viability analysis
  - [ ] 9.1 Add small opportunity classification
    - In PoolScanner, classify opportunities with profit $10K-$100K as "small"
    - Add is_small_opportunity helper method to check profit range
    - Track small opportunity count when saving to database
    - _Requirements: 11.1, 11.2, 11.3_

  - [ ] 9.2 Implement statistics aggregation service
    - Create StatsAggregator class in src/analytics/stats_aggregator.py
    - Implement hourly aggregation job to populate chain_stats table
    - Calculate capture_rate as (total_captured / total_opportunities) * 100
    - Calculate small opportunity capture rate separately
    - Query opportunities and transactions from database for aggregation
    - _Requirements: 11.4_

  - [ ] 9.3 Add competition level tracking
    - Track unique arbitrageurs per hour in chain_stats
    - For small opportunities, track which arbitrageurs captured them
    - Calculate average competition level as arbitrageurs per opportunity
    - Store aggregated data in chain_stats table
    - _Requirements: 11.5, 11.6_

  - [ ]* 9.4 Write viability analysis tests
    - Test small opportunity classification
    - Test capture rate calculation
    - Test competition level tracking
    - _Requirements: 11.1-11.7_

- [ ] 10. Implement REST API with FastAPI
  - [ ] 10.1 Create FastAPI application with authentication
    - Create FastAPI app in src/api/app.py
    - Set up CORS middleware with allowed origins
    - Implement API key authentication dependency via X-API-Key header
    - Create authentication middleware to validate API keys from Settings
    - Configure OpenAPI documentation at /docs
    - _Requirements: 7.8, 13.1, 13.2_

  - [ ] 10.2 Implement chain status endpoint
    - Create GET /api/v1/chains endpoint in src/api/routes/chains.py
    - Query chains table for status information
    - Return list of chains with status, last_synced_block, blocks_behind, uptime_pct
    - Use Pydantic models for response validation
    - _Requirements: 7.1_

  - [ ] 10.3 Implement opportunities endpoint
    - Create GET /api/v1/opportunities endpoint in src/api/routes/opportunities.py
    - Use DatabaseManager.get_opportunities() with OpportunityFilters
    - Support filtering by chain_id, min_profit, max_profit, captured
    - Support pagination with limit and offset query parameters
    - Return opportunities with all fields including capture status
    - _Requirements: 7.2, 7.6_

  - [ ] 10.4 Implement transactions endpoint
    - Create GET /api/v1/transactions endpoint in src/api/routes/transactions.py
    - Use DatabaseManager.get_transactions() with TransactionFilters
    - Support filtering by chain_id, from_address, min_profit, min_swaps, strategy
    - Support pagination with limit and offset
    - Return transactions with profit, gas cost, pools involved, tokens involved
    - _Requirements: 7.2, 7.6_

  - [ ] 10.5 Implement arbitrageurs endpoint
    - Create GET /api/v1/arbitrageurs endpoint in src/api/routes/arbitrageurs.py
    - Use DatabaseManager.get_arbitrageurs() with ArbitrageurFilters
    - Support filtering by chain_id, min_transactions, sort_by, sort_order
    - Support pagination with limit and offset
    - Return arbitrageur profiles with success rate, total profit, preferred strategy
    - _Requirements: 7.2, 7.6_

  - [ ] 10.6 Implement statistics endpoint
    - Create GET /api/v1/stats endpoint in src/api/routes/stats.py
    - Query chain_stats table for aggregated statistics
    - Support filtering by chain_id and time period (1h, 24h, 7d, 30d)
    - Return aggregated statistics including small opportunity analysis
    - Include profit distribution (min, max, avg, median, p95)
    - Include gas statistics
    - _Requirements: 7.2, 7.6, 7.7_

  - [ ] 10.7 Add health check endpoint
    - Create GET /api/v1/health endpoint in src/api/routes/health.py
    - Check database connectivity using DatabaseManager.pool
    - Return 200 if healthy with status details, 503 if unhealthy
    - Include database pool size and free connections in response
    - _Requirements: 1.7, 12.1-12.5_

  - [ ]* 10.8 Write API integration tests
    - Test authentication with valid and invalid API keys
    - Test all endpoints with various filters
    - Test pagination behavior
    - Test error responses
    - _Requirements: 7.1-7.8, 13.1-13.7_

- [ ] 11. Implement WebSocket streaming (OPTIONAL - can be deferred)
  - [ ] 11.1 Create WebSocket server with subscription management
    - Implement WebSocket endpoint at /ws/v1/stream in src/api/websocket.py
    - Handle connection, disconnection, and heartbeat using FastAPI WebSocket
    - Support subscribe/unsubscribe messages with filters
    - Track active subscriptions per connection
    - Limit to 100 concurrent connections
    - _Requirements: 8.1, 8.7_

  - [ ] 11.2 Implement opportunity broadcasting
    - When opportunity detected in PoolScanner, broadcast to subscribed clients
    - Filter broadcasts based on client subscription filters (chain, profit range)
    - Use asyncio queues for message passing
    - _Requirements: 8.2, 8.4_

  - [ ] 11.3 Implement transaction broadcasting
    - When arbitrage transaction detected in ChainMonitor, broadcast to subscribed clients
    - Filter broadcasts based on client subscription filters (chain, min_swaps)
    - Use asyncio queues for message passing
    - _Requirements: 8.3, 8.5, 8.6_

  - [ ]* 11.4 Write WebSocket integration tests
    - Test connection handling and heartbeat
    - Test subscription filtering
    - Test broadcast delivery
    - Test connection limit enforcement
    - _Requirements: 8.1-8.7_

- [ ] 12. Implement caching layer with Redis (OPTIONAL - can be deferred)
  - [ ] 12.1 Create cache manager
    - Implement CacheManager class in src/cache/manager.py with Redis connection
    - Add cache_opportunity method with 5-minute TTL
    - Add get_cached_stats method
    - Add invalidate_cache method for pattern-based invalidation
    - _Requirements: 7.7_

  - [ ] 12.2 Integrate caching with API endpoints
    - Cache recent opportunities (last 1000 per chain)
    - Cache aggregated statistics (60 second TTL)
    - Cache arbitrageur leaderboards (300 second TTL)
    - _Requirements: 7.6, 7.7_

  - [ ]* 12.3 Write cache integration tests
    - Test cache hit/miss behavior
    - Test TTL expiration
    - Test cache invalidation
    - _Requirements: 7.6, 7.7_

- [ ] 13. Implement monitoring and alerting (OPTIONAL - can be deferred)
  - [ ] 13.1 Set up Prometheus metrics
    - Create metrics module in src/monitoring/metrics.py
    - Create metrics for chain health (blocks_behind, rpc_latency, rpc_errors)
    - Create metrics for detection performance (opportunities_detected, transactions_detected)
    - Create metrics for database performance (query_latency, connection_pool_size)
    - Create metrics for API performance (requests_total, latency, errors)
    - Expose metrics endpoint at /metrics in FastAPI app
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [ ]* 13.2 Write monitoring tests
    - Test metric emission
    - Test metric accuracy
    - _Requirements: 12.1-12.9_

- [ ] 14. Implement data retention and archival (OPTIONAL - can be deferred)
  - [ ] 14.1 Create data retention service
    - Implement DataRetentionService class in src/services/retention.py
    - Implement scheduled job to delete opportunities older than 30 days
    - Implement scheduled job to archive transactions older than 90 days
    - Run retention jobs during low-activity hours (2 AM - 4 AM UTC)
    - Maintain referential integrity during deletion/archival
    - _Requirements: 15.1, 15.2, 15.5, 15.6_

  - [ ]* 14.2 Write data retention tests
    - Test opportunity deletion after 30 days
    - Test transaction archival after 90 days
    - _Requirements: 15.1-15.6_

- [ ] 15. Create Docker deployment configuration
  - [ ] 15.1 Create Dockerfile for backend service
    - Use Python 3.11 slim base image
    - Install dependencies via Poetry
    - Copy application code
    - Set up non-root user for security
    - Expose port 8000
    - Set CMD to run main application
    - _Requirements: 1.1-1.7_

  - [ ] 15.2 Create docker-compose.yml
    - Define postgres service with volume for data persistence
    - Define monitor service with environment variables
    - Set up service dependencies (monitor depends on postgres)
    - Configure restart policies
    - Map ports for API access
    - _Requirements: 1.1-1.7_

  - [x] 15.3 Create environment configuration
    - .env.example already exists with all required variables
    - Documents RPC endpoint configuration
    - Documents database credentials
    - Documents API keys
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 13.1_

- [ ] 16. Create main application entry point
  - [ ] 16.1 Implement application startup
    - Create main.py in project root
    - Initialize Settings from environment variables
    - Create DatabaseManager and connect
    - Initialize database schema
    - Create BSC and Polygon ChainConnectors
    - Create TransactionAnalyzer for each chain
    - Create ProfitCalculator
    - Create PoolScanner for each chain
    - Create ChainMonitor for BSC and Polygon
    - Start FastAPI app with uvicorn
    - Start chain monitors as background tasks
    - Start pool scanners as background tasks
    - Set up signal handlers for graceful shutdown
    - _Requirements: 1.1-1.7, 9.1-9.6_

  - [ ] 16.2 Implement graceful shutdown
    - Stop chain monitors on SIGTERM/SIGINT
    - Stop pool scanners
    - Close database connections
    - Wait for in-flight requests to complete
    - Log shutdown events
    - _Requirements: 14.6, 14.7_
