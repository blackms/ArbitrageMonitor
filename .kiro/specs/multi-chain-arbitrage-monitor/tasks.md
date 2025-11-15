# Implementation Plan

- [x] 1. Set up project structure and core configuration
  - Create Python project with Poetry for dependency management
  - Set up directory structure: chains/, detectors/, database/, api/, utils/
  - Create configuration models for chain settings and monitor config
  - Set up environment variable loading with python-dotenv
  - Configure structured logging with structlog
  - _Requirements: 1.1, 1.3_

- [-] 2. Implement database schema and connection management
  - [x] 2.1 Create PostgreSQL schema with all tables
    - Write SQL schema for chains, opportunities, transactions, arbitrageurs, chain_stats tables
    - Create indexes for high-frequency queries (chain_id, block_number, profit_usd, etc.)
    - Add foreign key constraints and check constraints
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [-] 2.2 Implement database manager with asyncpg
    - Create DatabaseManager class with connection pooling (min 5, max 20)
    - Implement save_opportunity, save_transaction, update_arbitrageur methods
    - Implement query methods with filtering support
    - Add retry logic for transient failures (3 attempts with exponential backoff)
    - _Requirements: 6.6, 6.7, 14.3, 14.4_

  - [ ] 2.3 Write database integration tests
    - Test connection pooling and concurrent writes
    - Test transaction rollback on errors
    - Test query performance with large datasets
    - _Requirements: 6.1-6.9_

- [ ] 3. Implement blockchain interaction layer
  - [ ] 3.1 Create base chain connector with web3.py
    - Implement ChainConnector base class with RPC connection management
    - Add automatic failover logic for backup RPC endpoints
    - Implement get_latest_block, get_block, get_transaction_receipt methods
    - Add circuit breaker pattern for RPC failures (open after 5 failures, 60s timeout)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 14.1, 14.2_

  - [ ] 3.2 Implement BSC chain connector
    - Create BSCConnector class extending ChainConnector
    - Configure BSC RPC endpoints (primary and fallback)
    - Define BSC DEX router addresses (PancakeSwap V2/V3, BiSwap, ApeSwap, THENA)
    - Define BSC pool addresses (WBNB pairs)
    - _Requirements: 1.1, 1.2, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ] 3.3 Implement Polygon chain connector
    - Create PolygonConnector class extending ChainConnector
    - Configure Polygon RPC endpoints (primary and fallback)
    - Define Polygon DEX router addresses (QuickSwap, SushiSwap, Uniswap V3, Balancer)
    - Define Polygon pool addresses (WMATIC pairs)
    - _Requirements: 1.3, 1.4, 3.6, 3.7, 3.8, 3.9_

  - [ ] 3.4 Write chain connector tests
    - Test RPC failover mechanism
    - Test circuit breaker behavior
    - Test connection recovery after failures
    - _Requirements: 1.1-1.7, 14.1-14.6_

- [ ] 4. Implement Swap event detection and arbitrage classification
  - [ ] 4.1 Create transaction analyzer with proper event signature detection
    - Calculate Swap event signature using web3.keccak(text="Swap(address,uint256,uint256,uint256,uint256,address)")
    - Implement count_swap_events method that filters by event signature (topics[0])
    - Implement parse_swap_events to extract token amounts from event data
    - Ensure only Swap events are counted, not Transfer, Sync, or Approval events
    - _Requirements: 2.1, 2.2_

  - [ ] 4.2 Implement arbitrage classification logic
    - Create is_arbitrage method that checks swap_count >= 2
    - Verify transaction targets known DEX router address
    - Verify transaction uses recognized swap method signature
    - Extract method signature from transaction input data (first 4 bytes)
    - _Requirements: 2.3, 2.4, 2.5, 2.7_

  - [ ] 4.3 Write comprehensive unit tests for swap detection
    - Test Swap event signature calculation matches expected value
    - Test count_swap_events with transaction containing multiple event types (should count only Swaps)
    - Test single swap transaction is NOT classified as arbitrage
    - Test multi-hop transaction (2+ swaps) IS classified as arbitrage
    - Test DEX router address validation
    - Test swap method signature recognition
    - _Requirements: 2.1, 2.2, 2.3, 2.6, 2.7_

- [ ] 5. Implement profit calculation engine
  - [ ] 5.1 Create profit calculator with token flow parsing
    - Implement parse_swap_event to extract amounts from event log data
    - Implement extract_token_flow to identify input from first swap and output from last swap
    - Handle both amount0In/amount1In and amount0Out/amount1Out fields
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ] 5.2 Implement profit and gas cost calculation
    - Calculate gross profit as output_amount - input_amount
    - Calculate gas cost as gasUsed * effectiveGasPrice
    - Calculate net profit as gross_profit - gas_cost
    - Calculate ROI as (net_profit / input_amount) * 100
    - Convert native token amounts to USD using price feeds
    - _Requirements: 5.4, 5.5, 5.6, 5.7_

  - [ ] 5.3 Write profit calculation tests
    - Test input amount extraction from first swap
    - Test output amount extraction from last swap
    - Test gross profit calculation
    - Test gas cost calculation with different gas prices
    - Test net profit calculation
    - Test ROI calculation
    - Test handling of zero input amounts
    - _Requirements: 5.1-5.7_

- [ ] 6. Implement pool scanner and opportunity detector
  - [ ] 6.1 Create pool scanner with multicall support
    - Implement PoolScanner class with get_pool_reserves method
    - Use multicall to batch reserve queries for efficiency
    - Query getReserves() function on pool contracts
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ] 6.2 Implement CPMM imbalance calculation
    - Calculate pool invariant k = reserve0 * reserve1
    - Calculate optimal reserves: optimal_x = optimal_y = sqrt(k)
    - Calculate imbalance percentage: max(|reserve0 - optimal_x| / optimal_x, |reserve1 - optimal_y| / optimal_y) * 100
    - Calculate profit potential accounting for 0.3% swap fee
    - Convert profit to USD assuming token1 is stablecoin
    - _Requirements: 4.5, 4.6_

  - [ ] 6.3 Implement opportunity detection and persistence
    - Scan pools every 3 seconds for BSC, 2 seconds for Polygon
    - Create Opportunity objects for imbalances > 5%
    - Save opportunities to database via DatabaseManager
    - Emit opportunities_detected metric
    - _Requirements: 4.7, 6.6_

  - [ ] 6.4 Write pool scanner tests
    - Test reserve retrieval from pool contracts
    - Test CPMM invariant calculation
    - Test imbalance percentage calculation
    - Test profit potential estimation
    - Test handling of zero reserves
    - _Requirements: 4.1-4.7_

- [ ] 7. Implement chain monitor orchestration
  - [ ] 7.1 Create chain monitor with block processing
    - Implement ChainMonitor class with start/stop methods
    - Poll for new blocks every 1 second
    - Process all transactions in each block
    - Filter transactions targeting DEX routers
    - Track last synced block number
    - _Requirements: 1.5, 1.6, 9.6_

  - [ ] 7.2 Implement transaction processing pipeline
    - Get transaction receipt for each filtered transaction
    - Pass receipt to TransactionAnalyzer for arbitrage detection
    - If arbitrage detected, calculate profit using ProfitCalculator
    - Save transaction to database
    - Update arbitrageur profile
    - Emit transactions_detected metric
    - _Requirements: 2.1-2.7, 5.1-5.7, 6.7, 10.1-10.8_

  - [ ] 7.3 Add monitoring metrics and error handling
    - Emit chain_blocks_behind metric
    - Emit chain_rpc_latency metric
    - Emit detection_latency metric
    - Handle RPC errors with automatic failover
    - Handle parsing errors gracefully (log and continue)
    - Implement graceful shutdown on stop signal
    - _Requirements: 1.7, 9.5, 12.1, 12.2, 12.3, 12.5, 14.5, 14.6_

  - [ ] 7.4 Write chain monitor integration tests
    - Test block detection and processing
    - Test transaction filtering by DEX router
    - Test RPC failover on connection errors
    - Test graceful error handling
    - _Requirements: 1.1-1.7, 9.1-9.6, 14.1-14.7_

- [ ] 8. Implement arbitrageur tracking
  - [ ] 8.1 Create arbitrageur tracker
    - Implement update_arbitrageur method in DatabaseManager
    - On new transaction, check if arbitrageur exists (by address and chain_id)
    - If new, create arbitrageur record with first_seen timestamp
    - Update last_seen, total_transactions, successful/failed counts
    - Accumulate total_profit_usd and total_gas_spent_usd
    - Calculate avg_gas_price_gwei as running average
    - Determine preferred_strategy from transaction history (most common hop count)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

  - [ ] 8.2 Write arbitrageur tracking tests
    - Test new arbitrageur creation
    - Test existing arbitrageur updates
    - Test profit accumulation
    - Test gas cost accumulation
    - Test preferred strategy calculation
    - _Requirements: 10.1-10.8_

- [ ] 9. Implement small trader viability analysis
  - [ ] 9.1 Add small opportunity classification
    - In opportunity detection, classify opportunities with profit $10K-$100K as "small"
    - Track small_opportunities_count in chain_stats table
    - When opportunity is captured, check if it was small and increment small_opps_captured
    - _Requirements: 11.1, 11.2, 11.3_

  - [ ] 9.2 Implement capture rate calculation
    - Calculate capture_rate as (total_captured / total_opportunities) * 100
    - Calculate small opportunity capture rate separately
    - Store in chain_stats table hourly
    - _Requirements: 11.4_

  - [ ] 9.3 Add competition level tracking
    - Track unique arbitrageurs per hour in chain_stats
    - For small opportunities, track which arbitrageurs captured them
    - Calculate average competition level as arbitrageurs per opportunity
    - _Requirements: 11.5, 11.6_

  - [ ] 9.4 Write viability analysis tests
    - Test small opportunity classification
    - Test capture rate calculation
    - Test competition level tracking
    - _Requirements: 11.1-11.7_

- [ ] 10. Implement REST API with FastAPI
  - [ ] 10.1 Create FastAPI application with authentication
    - Set up FastAPI app with CORS middleware
    - Implement API key authentication via X-API-Key header
    - Add rate limiting middleware (100 req/min per key)
    - Configure OpenAPI documentation
    - _Requirements: 7.8, 13.1, 13.2_

  - [ ] 10.2 Implement chain status endpoint
    - Create GET /api/v1/chains endpoint
    - Return list of chains with status, last_synced_block, blocks_behind, uptime_pct
    - Cache response for 30 seconds
    - _Requirements: 7.1_

  - [ ] 10.3 Implement opportunities endpoint
    - Create GET /api/v1/opportunities endpoint
    - Support filtering by chain, min_profit, max_profit, limit
    - Support pagination with page and per_page parameters
    - Return opportunities with all fields including capture status
    - Cache expensive queries for 60 seconds
    - _Requirements: 7.2, 7.6_

  - [ ] 10.4 Implement transactions endpoint
    - Create GET /api/v1/transactions endpoint
    - Support filtering by chain, min_profit, min_swaps, limit
    - Support pagination
    - Return transactions with profit, gas cost, pools involved, tokens involved
    - _Requirements: 7.2, 7.6_

  - [ ] 10.5 Implement arbitrageurs endpoint
    - Create GET /api/v1/arbitrageurs endpoint
    - Support filtering by chain, min_transactions, sort order
    - Support pagination
    - Return arbitrageur profiles with success rate, total profit, preferred strategy
    - _Requirements: 7.2, 7.6_

  - [ ] 10.6 Implement statistics endpoint
    - Create GET /api/v1/stats endpoint
    - Support filtering by chain and time period (1h, 24h, 7d, 30d)
    - Return aggregated statistics including small opportunity analysis
    - Include profit distribution (min, max, avg, median, p95)
    - Include gas statistics
    - Cache for 60 seconds
    - _Requirements: 7.2, 7.6, 7.7_

  - [ ] 10.7 Add health check endpoint
    - Create GET /api/v1/health endpoint
    - Check database connectivity
    - Check Redis connectivity
    - Check chain monitor status
    - Return 200 if healthy, 503 if unhealthy
    - _Requirements: 1.7, 12.1-12.5_

  - [ ] 10.8 Write API integration tests
    - Test authentication with valid and invalid API keys
    - Test rate limiting enforcement
    - Test all endpoints with various filters
    - Test pagination behavior
    - Test response caching
    - Test error responses
    - _Requirements: 7.1-7.8, 13.1-13.7_

- [ ] 11. Implement WebSocket streaming
  - [ ] 11.1 Create WebSocket server with subscription management
    - Implement WebSocket endpoint at /ws/v1/stream
    - Handle connection, disconnection, and heartbeat
    - Support subscribe/unsubscribe messages with filters
    - Track active subscriptions per connection
    - Limit to 100 concurrent connections
    - _Requirements: 8.1, 8.7_

  - [ ] 11.2 Implement opportunity broadcasting
    - When opportunity detected, broadcast to subscribed clients
    - Filter broadcasts based on client subscription filters (chain, profit range)
    - Broadcast within 100ms of detection
    - _Requirements: 8.2, 8.4_

  - [ ] 11.3 Implement transaction broadcasting
    - When arbitrage transaction detected, broadcast to subscribed clients
    - Filter broadcasts based on client subscription filters (chain, min_swaps)
    - Broadcast within 100ms of detection
    - _Requirements: 8.3, 8.5, 8.6_

  - [ ] 11.4 Write WebSocket integration tests
    - Test connection handling and heartbeat
    - Test subscription filtering
    - Test broadcast delivery
    - Test connection limit enforcement
    - Test reconnection behavior
    - _Requirements: 8.1-8.7_

- [ ] 12. Implement caching layer with Redis
  - [ ] 12.1 Create cache manager
    - Implement CacheManager class with Redis connection
    - Add cache_opportunity method with 5-minute TTL
    - Add get_cached_stats method
    - Add invalidate_cache method for pattern-based invalidation
    - _Requirements: 7.7_

  - [ ] 12.2 Integrate caching with API endpoints
    - Cache recent opportunities (last 1000 per chain)
    - Cache aggregated statistics (60 second TTL)
    - Cache arbitrageur leaderboards (300 second TTL)
    - Implement cache warming on startup
    - _Requirements: 7.6, 7.7_

  - [ ] 12.3 Write cache integration tests
    - Test cache hit/miss behavior
    - Test TTL expiration
    - Test cache invalidation
    - Test cache warming
    - _Requirements: 7.6, 7.7_

- [ ] 13. Implement monitoring and alerting
  - [ ] 13.1 Set up Prometheus metrics
    - Create metrics for chain health (blocks_behind, rpc_latency, rpc_errors)
    - Create metrics for detection performance (opportunities_detected, transactions_detected, detection_latency)
    - Create metrics for database performance (query_latency, connection_pool_size, errors)
    - Create metrics for API performance (requests_total, latency, errors)
    - Create metrics for business KPIs (total_profit, active_arbitrageurs, small_opportunities_pct)
    - Expose metrics endpoint at /metrics
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [ ] 13.2 Implement alert conditions
    - Add alert for blocks_behind > 100 (critical)
    - Add alert for rpc_latency p95 > 2000ms (warning)
    - Add alert for database connection pool > 80% (critical)
    - Add alert for no opportunities detected in 5 minutes (warning)
    - _Requirements: 12.7, 12.8, 12.9_

  - [ ] 13.3 Write monitoring tests
    - Test metric emission
    - Test metric accuracy
    - Test alert condition evaluation
    - _Requirements: 12.1-12.9_

- [ ] 14. Implement data retention and archival
  - [ ] 14.1 Create data retention service
    - Implement scheduled job to delete opportunities older than 30 days
    - Implement scheduled job to archive transactions older than 90 days
    - Run retention jobs during low-activity hours (2 AM - 4 AM UTC)
    - Maintain referential integrity during deletion/archival
    - _Requirements: 15.1, 15.2, 15.5, 15.6_

  - [ ] 14.2 Write data retention tests
    - Test opportunity deletion after 30 days
    - Test transaction archival after 90 days
    - Test referential integrity maintenance
    - _Requirements: 15.1-15.6_

- [ ] 15. Create Docker deployment configuration
  - [ ] 15.1 Create Dockerfile for backend service
    - Use Python 3.11 slim base image
    - Install dependencies via Poetry
    - Copy application code
    - Set up non-root user for security
    - Expose port 8000
    - _Requirements: 1.1-1.7_

  - [ ] 15.2 Create docker-compose.yml
    - Define postgres service with volume for data persistence
    - Define redis service with volume for data persistence
    - Define monitor service with environment variables
    - Set up service dependencies
    - Configure restart policies
    - _Requirements: 1.1-1.7_

  - [ ] 15.3 Create environment configuration
    - Create .env.example with all required variables
    - Document RPC endpoint configuration
    - Document database credentials
    - Document API keys
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 13.1_

- [ ] 16. Create main application entry point
  - [ ] 16.1 Implement application startup
    - Create main.py with FastAPI app initialization
    - Start BSC chain monitor in background task
    - Start Polygon chain monitor in background task
    - Start pool scanner for both chains
    - Initialize database connection pool
    - Initialize Redis connection
    - Set up signal handlers for graceful shutdown
    - _Requirements: 1.1-1.7, 9.1-9.6_

  - [ ] 16.2 Implement graceful shutdown
    - Stop chain monitors on SIGTERM/SIGINT
    - Close database connections
    - Close Redis connections
    - Wait for in-flight requests to complete
    - _Requirements: 14.6, 14.7_

- [ ] 17. End-to-end validation
  - [ ] 17.1 Deploy to test environment
    - Build Docker images
    - Start all services with docker-compose
    - Verify database schema creation
    - Verify chain monitors start successfully
    - _Requirements: 1.1-1.7_

  - [ ] 17.2 Validate opportunity detection
    - Monitor logs for opportunity detection
    - Verify opportunities are saved to database
    - Query opportunities via API
    - Verify WebSocket broadcasts
    - _Requirements: 4.1-4.7, 6.1-6.7, 7.1-7.2, 8.1-8.7_

  - [ ] 17.3 Validate transaction analysis
    - Wait for arbitrage transactions to be detected
    - Verify Swap event counting is accurate (no false positives)
    - Verify profit calculations are correct
    - Verify arbitrageur profiles are updated
    - Query transactions via API
    - _Requirements: 2.1-2.7, 5.1-5.7, 10.1-10.8_

  - [ ] 17.4 Validate performance requirements
    - Monitor detection latency (should be <2 seconds)
    - Monitor API response times (should be <200ms)
    - Monitor blocks_behind metric (should be <5)
    - Verify system handles expected TPS (200 for BSC, 300 for Polygon)
    - _Requirements: 9.1-9.6_

  - [ ] 17.5 Run 24-hour burn-in test
    - Let system run for 24 hours
    - Monitor for memory leaks
    - Monitor for connection pool exhaustion
    - Verify no crashes or restarts
    - Verify data consistency
    - _Requirements: 1.7, 9.1-9.6_
