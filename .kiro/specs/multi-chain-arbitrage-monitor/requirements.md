# Requirements Document

## Introduction

The Multi-Chain Arbitrage Monitor is a production-ready system designed to detect, track, and analyze real multi-hop arbitrage opportunities and transactions across multiple EVM-compatible blockchains (BSC and Polygon). The system targets small traders with $10K-$100K capital to assess market viability by providing accurate detection of arbitrage opportunities, competition analysis, and real-time monitoring with sub-second latency.

## Glossary

- **System**: The Multi-Chain Arbitrage Monitor application
- **Chain Monitor**: Component responsible for monitoring a specific blockchain (BSC or Polygon)
- **Arbitrage Transaction**: A blockchain transaction containing 2 or more token swaps in a single transaction
- **Swap Event**: A blockchain event with signature `Swap(address,uint256,uint256,uint256,uint256,address)`
- **DEX Router**: Decentralized exchange router smart contract that facilitates token swaps
- **Pool**: A liquidity pool smart contract containing token reserves for trading
- **Opportunity**: A detected pool imbalance that could be exploited for profit
- **Arbitrageur**: A blockchain address that executes arbitrage transactions
- **Multi-Hop**: A transaction path involving 2 or more sequential token swaps
- **CPMM**: Constant Product Market Maker (x * y = k formula)
- **RPC Endpoint**: Remote Procedure Call endpoint for blockchain interaction
- **Block Latency**: Time difference between block creation and system detection
- **False Positive**: A transaction incorrectly identified as arbitrage

## Requirements

### Requirement 1: Multi-Chain Blockchain Monitoring

**User Story:** As a market analyst, I want the system to monitor both BSC and Polygon blockchains simultaneously, so that I can compare arbitrage opportunities across multiple chains.

#### Acceptance Criteria

1. THE System SHALL establish connection to BSC mainnet using primary RPC endpoint `https://bsc-dataseed.bnbchain.org`
2. WHEN the primary BSC RPC endpoint fails, THE System SHALL automatically failover to backup RPC endpoint `https://bsc-dataseed1.binance.org`
3. THE System SHALL establish connection to Polygon mainnet using primary RPC endpoint `https://polygon-rpc.com`
4. WHEN the primary Polygon RPC endpoint fails, THE System SHALL automatically failover to backup RPC endpoint `https://rpc-mainnet.matic.network`
5. THE System SHALL detect new blocks on BSC within 1 second of block creation
6. THE System SHALL detect new blocks on Polygon within 1 second of block creation
7. THE System SHALL maintain 99.9% uptime for each Chain Monitor independently

### Requirement 2: Accurate Arbitrage Detection

**User Story:** As a trader, I want the system to detect only real multi-hop arbitrage transactions with zero false positives, so that I can trust the data for investment decisions.

#### Acceptance Criteria

1. THE System SHALL identify Swap Events by matching event signature `0xd78ad95fa28c6997e71598397e6f1902e52d1b5a7e5e0c75c1b1b1b1b1b1b1b1` (keccak256 hash of Swap signature)
2. WHEN analyzing a transaction receipt, THE System SHALL count only events matching the Swap Event signature
3. THE System SHALL classify a transaction as Arbitrage Transaction IF AND ONLY IF the transaction contains 2 or more Swap Events
4. THE System SHALL verify that Arbitrage Transactions target known DEX Router addresses
5. THE System SHALL verify that Arbitrage Transactions use recognized swap method signatures
6. THE System SHALL achieve 0% false positive rate for arbitrage detection
7. THE System SHALL exclude transactions with single Swap Events from arbitrage classification

### Requirement 3: DEX Router Recognition

**User Story:** As a system administrator, I want the system to recognize all major DEX routers on BSC and Polygon, so that arbitrage transactions are accurately identified.

#### Acceptance Criteria

1. THE System SHALL recognize PancakeSwap V2 router at address `0x10ED43C718714eb63d5aA57B78B54704E256024E` on BSC
2. THE System SHALL recognize PancakeSwap V3 router at address `0x13f4EA83D0bd40E75C8222255bc855a974568Dd4` on BSC
3. THE System SHALL recognize BiSwap router at address `0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8` on BSC
4. THE System SHALL recognize ApeSwap router at address `0xcF0feBd3f17CEf5b47b0cD257aCf6025c5BFf3b7` on BSC
5. THE System SHALL recognize THENA router at address `0xd4ae6eCA985340Dd434D38F470aCCce4DC78D109` on BSC
6. THE System SHALL recognize QuickSwap router at address `0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff` on Polygon
7. THE System SHALL recognize SushiSwap router at address `0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506` on Polygon
8. THE System SHALL recognize Uniswap V3 router at address `0xE592427A0AEce92De3Edee1F18E0157C05861564` on Polygon
9. THE System SHALL recognize Balancer router at address `0xBA12222222228d8Ba445958a75a0704d566BF2C8` on Polygon

### Requirement 4: Pool Imbalance Detection

**User Story:** As a trader, I want the system to detect pool imbalances using CPMM formulas, so that I can identify arbitrage opportunities before they are executed.

#### Acceptance Criteria

1. THE System SHALL monitor WBNB-BUSD pool at address `0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16` on BSC
2. THE System SHALL monitor WBNB-USDT pool at address `0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE` on BSC
3. THE System SHALL monitor WMATIC-USDC pool at address `0x6e7a5FAFcec6BB1e78bAA2A0430e3B1B64B5c0D7` on Polygon
4. THE System SHALL monitor WMATIC-USDT pool at address `0x604229c960e5CACF2aaEAc8Be68Ac07BA9dF81c3` on Polygon
5. WHEN pool reserves are retrieved, THE System SHALL calculate imbalance percentage using CPMM invariant formula (k = x * y)
6. WHEN pool reserves are retrieved, THE System SHALL calculate profit potential in USD accounting for 0.3% swap fee
7. THE System SHALL detect pool imbalances within 2 seconds of reserve state change

### Requirement 5: Real Profit Calculation

**User Story:** As a trader, I want the system to calculate actual profit from arbitrage transactions by parsing token flows, so that I can understand real profitability after gas costs.

#### Acceptance Criteria

1. WHEN analyzing an Arbitrage Transaction, THE System SHALL parse all Swap Events to extract token amounts (amount0In, amount1In, amount0Out, amount1Out)
2. WHEN calculating profit, THE System SHALL determine input amount from the first Swap Event in the transaction
3. WHEN calculating profit, THE System SHALL determine output amount from the last Swap Event in the transaction
4. THE System SHALL calculate gross profit as the difference between output amount and input amount
5. THE System SHALL calculate gas cost by multiplying gas used by effective gas price
6. THE System SHALL calculate net profit by subtracting gas cost from gross profit
7. THE System SHALL calculate ROI percentage as (net profit / input amount) * 100

### Requirement 6: Data Persistence

**User Story:** As a data analyst, I want all detected opportunities and transactions stored in a relational database, so that I can perform historical analysis and generate reports.

#### Acceptance Criteria

1. THE System SHALL store chain configuration data in a PostgreSQL table named `chains`
2. THE System SHALL store detected opportunities in a PostgreSQL table named `opportunities`
3. THE System SHALL store arbitrage transactions in a PostgreSQL table named `transactions`
4. THE System SHALL store arbitrageur profiles in a PostgreSQL table named `arbitrageurs`
5. THE System SHALL store hourly aggregated statistics in a PostgreSQL table named `chain_stats`
6. WHEN an Opportunity is detected, THE System SHALL persist the record within 1 second
7. WHEN an Arbitrage Transaction is detected, THE System SHALL persist the record within 3 seconds
8. THE System SHALL maintain opportunities data for 30 days rolling window
9. THE System SHALL maintain transactions data permanently with archival after 90 days

### Requirement 7: REST API

**User Story:** As a frontend developer, I want a REST API to query opportunities, transactions, and arbitrageurs, so that I can build user interfaces and integrations.

#### Acceptance Criteria

1. THE System SHALL provide a GET endpoint `/api/v1/chains` that returns status of all monitored chains
2. THE System SHALL provide a GET endpoint `/api/v1/opportunities` that returns detected opportunities with filtering by chain, profit range, and limit
3. THE System SHALL provide a GET endpoint `/api/v1/transactions` that returns arbitrage transactions with filtering by chain, profit range, and limit
4. THE System SHALL provide a GET endpoint `/api/v1/arbitrageurs` that returns arbitrageur profiles with filtering by chain, transaction count, and sorting
5. THE System SHALL provide a GET endpoint `/api/v1/stats` that returns aggregated statistics for a specified chain and time period
6. THE System SHALL respond to API queries within 200 milliseconds for non-cached data
7. THE System SHALL respond to API queries within 50 milliseconds for cached data
8. THE System SHALL implement rate limiting of 100 requests per minute per API key

### Requirement 8: Real-Time WebSocket Streaming

**User Story:** As a trader, I want real-time notifications of opportunities and transactions via WebSocket, so that I can react quickly to market conditions.

#### Acceptance Criteria

1. THE System SHALL provide a WebSocket endpoint at `/ws/v1/stream` for real-time data streaming
2. WHEN a client subscribes to the `opportunities` channel, THE System SHALL stream newly detected opportunities matching client filters
3. WHEN a client subscribes to the `transactions` channel, THE System SHALL stream newly detected arbitrage transactions matching client filters
4. THE System SHALL broadcast opportunity notifications within 100 milliseconds of detection
5. THE System SHALL broadcast transaction notifications within 100 milliseconds of detection
6. THE System SHALL support filtering by chain, profit range, and swap count in WebSocket subscriptions
7. THE System SHALL support at least 100 concurrent WebSocket connections

### Requirement 9: Performance and Throughput

**User Story:** As a system operator, I want the system to handle high transaction volumes with low latency, so that no opportunities are missed during peak activity.

#### Acceptance Criteria

1. THE System SHALL process at least 200 transactions per second on BSC
2. THE System SHALL process at least 300 transactions per second on Polygon
3. THE System SHALL scan at least 20 pools per chain per minute
4. THE System SHALL sustain at least 1000 database inserts per minute
5. THE System SHALL analyze transactions within 3 seconds of block inclusion
6. THE System SHALL maintain block synchronization with less than 5 blocks behind latest block under normal conditions

### Requirement 10: Arbitrageur Analysis

**User Story:** As a market researcher, I want to track arbitrageur behavior and success patterns, so that I can understand competition dynamics.

#### Acceptance Criteria

1. WHEN an Arbitrage Transaction is detected, THE System SHALL identify or create an Arbitrageur record for the sender address
2. THE System SHALL increment total transaction count for the Arbitrageur
3. WHEN a transaction succeeds, THE System SHALL increment successful transaction count for the Arbitrageur
4. WHEN a transaction fails, THE System SHALL increment failed transaction count for the Arbitrageur
5. THE System SHALL accumulate total profit in USD for each Arbitrageur
6. THE System SHALL accumulate total gas spent in USD for each Arbitrageur
7. THE System SHALL calculate average gas price used by each Arbitrageur
8. THE System SHALL identify the preferred strategy (2-hop, 3-hop, 4-hop) for each Arbitrageur based on transaction history

### Requirement 11: Small Trader Viability Assessment

**User Story:** As a small trader with $10K-$100K capital, I want to understand if I can compete in the arbitrage market, so that I can make informed investment decisions.

#### Acceptance Criteria

1. THE System SHALL classify opportunities with profit between $10,000 and $100,000 as small opportunities
2. THE System SHALL track the count of small opportunities detected per hour
3. THE System SHALL track the count of small opportunities captured per hour
4. THE System SHALL calculate capture rate for small opportunities as (captured / detected) * 100
5. THE System SHALL identify unique arbitrageurs competing for small opportunities
6. THE System SHALL calculate average competition level as arbitrageurs per small opportunity
7. THE System SHALL provide statistical analysis comparing small opportunity capture rates to larger opportunities

### Requirement 12: Monitoring and Health Metrics

**User Story:** As a system operator, I want comprehensive health metrics and alerting, so that I can maintain system reliability and quickly respond to issues.

#### Acceptance Criteria

1. THE System SHALL expose a metric `chain.blocks_behind` indicating blocks behind latest for each chain
2. THE System SHALL expose a metric `chain.rpc_latency_ms` measuring RPC call latency
3. THE System SHALL expose a metric `detector.opportunities_detected_total` counting total opportunities detected
4. THE System SHALL expose a metric `detector.transactions_detected_total` counting total arbitrage transactions detected
5. THE System SHALL expose a metric `detector.latency_ms` measuring detection latency
6. THE System SHALL expose a metric `api.response_latency_ms` measuring API response time
7. WHEN blocks behind exceeds 100, THE System SHALL trigger a critical alert
8. WHEN RPC latency p95 exceeds 2000 milliseconds, THE System SHALL trigger a warning alert
9. WHEN no opportunities are detected for 5 minutes, THE System SHALL trigger a warning alert

### Requirement 13: Security and Authentication

**User Story:** As a security administrator, I want the system to implement proper authentication and security controls, so that data access is controlled and the system is protected.

#### Acceptance Criteria

1. THE System SHALL require API key authentication for all REST API endpoints
2. THE System SHALL validate and sanitize all API input parameters to prevent injection attacks
3. THE System SHALL use parameterized queries for all database operations to prevent SQL injection
4. THE System SHALL enforce HTTPS for all RPC endpoint connections
5. THE System SHALL implement CORS configuration to restrict API access to authorized domains
6. THE System SHALL encrypt database connections using TLS
7. THE System SHALL log all API requests with timestamp, API key, endpoint, and response status

### Requirement 14: Error Handling and Resilience

**User Story:** As a system operator, I want robust error handling and automatic recovery, so that the system remains operational during transient failures.

#### Acceptance Criteria

1. WHEN an RPC endpoint returns an error, THE System SHALL retry the request up to 3 times with exponential backoff
2. WHEN all RPC endpoints for a chain fail, THE System SHALL log a critical error and continue monitoring other chains
3. WHEN a database write fails, THE System SHALL retry the operation up to 3 times
4. WHEN a database connection is lost, THE System SHALL attempt to reconnect every 5 seconds
5. WHEN a transaction analysis fails, THE System SHALL log the error with transaction hash and continue processing other transactions
6. THE System SHALL continue operating other Chain Monitors when one Chain Monitor encounters errors
7. THE System SHALL recover automatically from transient failures without manual intervention

### Requirement 15: Data Retention and Archival

**User Story:** As a database administrator, I want automated data retention policies, so that database size is managed and historical data is preserved appropriately.

#### Acceptance Criteria

1. THE System SHALL delete opportunity records older than 30 days automatically
2. THE System SHALL archive transaction records older than 90 days to separate storage
3. THE System SHALL retain arbitrageur records permanently
4. THE System SHALL retain chain statistics records permanently
5. THE System SHALL execute data retention operations during low-activity hours (2 AM - 4 AM UTC)
6. WHEN archiving transactions, THE System SHALL maintain referential integrity with arbitrageur records
