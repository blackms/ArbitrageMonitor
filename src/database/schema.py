"""PostgreSQL schema definition for arbitrage monitoring system"""


def get_schema_sql() -> str:
    """
    Returns the complete SQL schema for the arbitrage monitoring database.
    
    Tables:
    - chains: Blockchain configuration and status
    - opportunities: Detected pool imbalances
    - transactions: Arbitrage transactions
    - arbitrageurs: Trader profiles and statistics
    - chain_stats: Hourly aggregated statistics
    """
    return """
-- Chains table: Store blockchain configuration and status
CREATE TABLE IF NOT EXISTS chains (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    chain_id INTEGER NOT NULL UNIQUE,
    rpc_primary VARCHAR(255) NOT NULL,
    rpc_fallback VARCHAR(255),
    block_time_seconds DECIMAL(5, 2) NOT NULL,
    native_token VARCHAR(10) NOT NULL,
    native_token_usd DECIMAL(18, 8) NOT NULL,
    last_synced_block BIGINT DEFAULT 0,
    blocks_behind INTEGER DEFAULT 0,
    uptime_pct DECIMAL(5, 2) DEFAULT 100.00,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chains_status_check CHECK (status IN ('active', 'inactive', 'error'))
);

-- Opportunities table: Store detected pool imbalances
CREATE TABLE IF NOT EXISTS opportunities (
    id SERIAL PRIMARY KEY,
    chain_id INTEGER NOT NULL,
    pool_name VARCHAR(100) NOT NULL,
    pool_address VARCHAR(42) NOT NULL,
    imbalance_pct DECIMAL(10, 4) NOT NULL,
    profit_usd DECIMAL(18, 8) NOT NULL,
    profit_native DECIMAL(18, 8) NOT NULL,
    reserve0 DECIMAL(38, 18) NOT NULL,
    reserve1 DECIMAL(38, 18) NOT NULL,
    block_number BIGINT NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    captured BOOLEAN DEFAULT FALSE,
    captured_by VARCHAR(42),
    capture_tx_hash VARCHAR(66),
    CONSTRAINT opportunities_chain_fk FOREIGN KEY (chain_id) 
        REFERENCES chains(chain_id) ON DELETE CASCADE,
    CONSTRAINT opportunities_imbalance_check CHECK (imbalance_pct >= 0),
    CONSTRAINT opportunities_profit_check CHECK (profit_usd >= 0)
);

-- Transactions table: Store arbitrage transactions
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    chain_id INTEGER NOT NULL,
    tx_hash VARCHAR(66) NOT NULL,
    from_address VARCHAR(42) NOT NULL,
    block_number BIGINT NOT NULL,
    block_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    gas_price_gwei DECIMAL(18, 8) NOT NULL,
    gas_used INTEGER NOT NULL,
    gas_cost_native DECIMAL(18, 8) NOT NULL,
    gas_cost_usd DECIMAL(18, 8) NOT NULL,
    swap_count INTEGER NOT NULL,
    strategy VARCHAR(20) NOT NULL,
    profit_gross_usd DECIMAL(18, 8),
    profit_net_usd DECIMAL(18, 8),
    pools_involved TEXT[] NOT NULL,
    tokens_involved TEXT[] NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT transactions_chain_fk FOREIGN KEY (chain_id) 
        REFERENCES chains(chain_id) ON DELETE CASCADE,
    CONSTRAINT transactions_tx_hash_unique UNIQUE (chain_id, tx_hash),
    CONSTRAINT transactions_swap_count_check CHECK (swap_count >= 2),
    CONSTRAINT transactions_strategy_check CHECK (
        strategy IN ('2-hop', '3-hop', '4-hop', '5-hop', 'multi-hop')
    ),
    CONSTRAINT transactions_gas_check CHECK (gas_used > 0)
);

-- Arbitrageurs table: Store trader profiles and statistics
CREATE TABLE IF NOT EXISTS arbitrageurs (
    id SERIAL PRIMARY KEY,
    address VARCHAR(42) NOT NULL,
    chain_id INTEGER NOT NULL,
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    total_transactions INTEGER DEFAULT 0,
    successful_transactions INTEGER DEFAULT 0,
    failed_transactions INTEGER DEFAULT 0,
    total_profit_usd DECIMAL(18, 8) DEFAULT 0,
    total_gas_spent_usd DECIMAL(18, 8) DEFAULT 0,
    avg_gas_price_gwei DECIMAL(18, 8),
    preferred_strategy VARCHAR(20),
    is_bot BOOLEAN DEFAULT FALSE,
    contract_address BOOLEAN DEFAULT FALSE,
    CONSTRAINT arbitrageurs_chain_fk FOREIGN KEY (chain_id) 
        REFERENCES chains(chain_id) ON DELETE CASCADE,
    CONSTRAINT arbitrageurs_address_chain_unique UNIQUE (address, chain_id),
    CONSTRAINT arbitrageurs_transactions_check CHECK (
        total_transactions = successful_transactions + failed_transactions
    ),
    CONSTRAINT arbitrageurs_profit_check CHECK (total_profit_usd >= 0)
);

-- Chain stats table: Store hourly aggregated statistics
CREATE TABLE IF NOT EXISTS chain_stats (
    id SERIAL PRIMARY KEY,
    chain_id INTEGER NOT NULL,
    hour_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    opportunities_detected INTEGER DEFAULT 0,
    opportunities_captured INTEGER DEFAULT 0,
    small_opportunities_count INTEGER DEFAULT 0,
    small_opps_captured INTEGER DEFAULT 0,
    transactions_detected INTEGER DEFAULT 0,
    unique_arbitrageurs INTEGER DEFAULT 0,
    total_profit_usd DECIMAL(18, 8) DEFAULT 0,
    total_gas_spent_usd DECIMAL(18, 8) DEFAULT 0,
    avg_profit_usd DECIMAL(18, 8),
    median_profit_usd DECIMAL(18, 8),
    max_profit_usd DECIMAL(18, 8),
    min_profit_usd DECIMAL(18, 8),
    p95_profit_usd DECIMAL(18, 8),
    capture_rate DECIMAL(5, 2),
    small_opp_capture_rate DECIMAL(5, 2),
    avg_competition_level DECIMAL(10, 4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chain_stats_chain_fk FOREIGN KEY (chain_id) 
        REFERENCES chains(chain_id) ON DELETE CASCADE,
    CONSTRAINT chain_stats_hour_chain_unique UNIQUE (chain_id, hour_timestamp),
    CONSTRAINT chain_stats_counts_check CHECK (
        opportunities_detected >= 0 AND 
        opportunities_captured >= 0 AND
        transactions_detected >= 0
    )
);

-- Indexes for high-frequency queries

-- Opportunities indexes
CREATE INDEX IF NOT EXISTS idx_opportunities_chain_block 
    ON opportunities(chain_id, block_number DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_profit 
    ON opportunities(profit_usd DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_detected_at 
    ON opportunities(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_captured 
    ON opportunities(captured, chain_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_pool 
    ON opportunities(pool_address, chain_id);

-- Transactions indexes
CREATE INDEX IF NOT EXISTS idx_transactions_chain_block 
    ON transactions(chain_id, block_number DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_from_address 
    ON transactions(from_address, chain_id);
CREATE INDEX IF NOT EXISTS idx_transactions_profit 
    ON transactions(profit_net_usd DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_transactions_detected_at 
    ON transactions(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_block_timestamp 
    ON transactions(block_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_swap_count 
    ON transactions(swap_count, chain_id);

-- Arbitrageurs indexes
CREATE INDEX IF NOT EXISTS idx_arbitrageurs_chain 
    ON arbitrageurs(chain_id, total_transactions DESC);
CREATE INDEX IF NOT EXISTS idx_arbitrageurs_profit 
    ON arbitrageurs(total_profit_usd DESC);
CREATE INDEX IF NOT EXISTS idx_arbitrageurs_last_seen 
    ON arbitrageurs(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_arbitrageurs_address 
    ON arbitrageurs(address);

-- Chain stats indexes
CREATE INDEX IF NOT EXISTS idx_chain_stats_chain_hour 
    ON chain_stats(chain_id, hour_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_chain_stats_timestamp 
    ON chain_stats(hour_timestamp DESC);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at on chains table
DROP TRIGGER IF EXISTS update_chains_updated_at ON chains;
CREATE TRIGGER update_chains_updated_at
    BEFORE UPDATE ON chains
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE chains IS 'Blockchain configuration and monitoring status';
COMMENT ON TABLE opportunities IS 'Detected pool imbalances that could be exploited for profit';
COMMENT ON TABLE transactions IS 'Arbitrage transactions with 2+ swaps';
COMMENT ON TABLE arbitrageurs IS 'Trader profiles with aggregated statistics';
COMMENT ON TABLE chain_stats IS 'Hourly aggregated statistics per chain';

COMMENT ON COLUMN opportunities.imbalance_pct IS 'Pool imbalance percentage calculated from CPMM invariant';
COMMENT ON COLUMN opportunities.captured IS 'Whether this opportunity was captured by an arbitrageur';
COMMENT ON COLUMN transactions.swap_count IS 'Number of Swap events in the transaction (must be >= 2)';
COMMENT ON COLUMN transactions.strategy IS 'Arbitrage strategy based on hop count (2-hop, 3-hop, etc.)';
COMMENT ON COLUMN arbitrageurs.is_bot IS 'Whether this address appears to be an automated bot';
COMMENT ON COLUMN arbitrageurs.contract_address IS 'Whether this address is a smart contract';
COMMENT ON COLUMN chain_stats.small_opportunities_count IS 'Opportunities with profit between $10K-$100K';
COMMENT ON COLUMN chain_stats.capture_rate IS 'Percentage of opportunities that were captured';
"""
