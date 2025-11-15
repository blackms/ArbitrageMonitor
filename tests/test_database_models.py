"""Unit tests for database models and schema"""

from datetime import datetime
from decimal import Decimal

import pytest

from src.database import (
    Arbitrageur,
    ArbitrageurFilters,
    ArbitrageTransaction,
    Opportunity,
    OpportunityFilters,
    TransactionFilters,
    get_schema_sql,
)


def test_opportunity_model_creation():
    """Test Opportunity model creation"""
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
    
    assert opportunity.chain_id == 56
    assert opportunity.pool_name == "WBNB-BUSD"
    assert opportunity.imbalance_pct == Decimal("7.5")
    assert opportunity.profit_usd == Decimal("15000.50")
    assert opportunity.captured is False
    assert opportunity.id is None


def test_arbitrage_transaction_model_creation():
    """Test ArbitrageTransaction model creation"""
    transaction = ArbitrageTransaction(
        chain_id=56,
        tx_hash="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        from_address="0xabcdef1234567890abcdef1234567890abcdef12",
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
    
    assert transaction.chain_id == 56
    assert transaction.swap_count == 3
    assert transaction.strategy == "3-hop"
    assert len(transaction.pools_involved) == 3
    assert len(transaction.tokens_involved) == 3
    assert transaction.id is None


def test_arbitrageur_model_creation():
    """Test Arbitrageur model creation"""
    arbitrageur = Arbitrageur(
        address="0x1234567890123456789012345678901234567890",
        chain_id=56,
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        total_transactions=10,
        successful_transactions=8,
        failed_transactions=2,
        total_profit_usd=Decimal("50000.0"),
        total_gas_spent_usd=Decimal("500.0"),
        avg_gas_price_gwei=Decimal("5.5"),
        preferred_strategy="2-hop",
    )
    
    assert arbitrageur.address == "0x1234567890123456789012345678901234567890"
    assert arbitrageur.total_transactions == 10
    assert arbitrageur.successful_transactions == 8
    assert arbitrageur.failed_transactions == 2
    assert arbitrageur.total_profit_usd == Decimal("50000.0")
    assert arbitrageur.preferred_strategy == "2-hop"
    assert arbitrageur.is_bot is False


def test_opportunity_filters_defaults():
    """Test OpportunityFilters default values"""
    filters = OpportunityFilters()
    
    assert filters.chain_id is None
    assert filters.min_profit is None
    assert filters.max_profit is None
    assert filters.captured is None
    assert filters.limit == 100
    assert filters.offset == 0


def test_opportunity_filters_custom():
    """Test OpportunityFilters with custom values"""
    filters = OpportunityFilters(
        chain_id=56,
        min_profit=Decimal("10000.0"),
        max_profit=Decimal("50000.0"),
        captured=True,
        limit=50,
        offset=10,
    )
    
    assert filters.chain_id == 56
    assert filters.min_profit == Decimal("10000.0")
    assert filters.max_profit == Decimal("50000.0")
    assert filters.captured is True
    assert filters.limit == 50
    assert filters.offset == 10


def test_transaction_filters_defaults():
    """Test TransactionFilters default values"""
    filters = TransactionFilters()
    
    assert filters.chain_id is None
    assert filters.from_address is None
    assert filters.min_profit is None
    assert filters.min_swaps is None
    assert filters.strategy is None
    assert filters.limit == 100
    assert filters.offset == 0


def test_transaction_filters_custom():
    """Test TransactionFilters with custom values"""
    filters = TransactionFilters(
        chain_id=137,
        from_address="0xabcdef1234567890abcdef1234567890abcdef12",
        min_profit=Decimal("1000.0"),
        min_swaps=3,
        strategy="3-hop",
        limit=25,
        offset=5,
    )
    
    assert filters.chain_id == 137
    assert filters.from_address == "0xabcdef1234567890abcdef1234567890abcdef12"
    assert filters.min_profit == Decimal("1000.0")
    assert filters.min_swaps == 3
    assert filters.strategy == "3-hop"
    assert filters.limit == 25
    assert filters.offset == 5


def test_arbitrageur_filters_defaults():
    """Test ArbitrageurFilters default values"""
    filters = ArbitrageurFilters()
    
    assert filters.chain_id is None
    assert filters.min_transactions is None
    assert filters.sort_by == "total_profit_usd"
    assert filters.sort_order == "DESC"
    assert filters.limit == 100
    assert filters.offset == 0


def test_arbitrageur_filters_custom():
    """Test ArbitrageurFilters with custom values"""
    filters = ArbitrageurFilters(
        chain_id=56,
        min_transactions=10,
        sort_by="total_transactions",
        sort_order="ASC",
        limit=20,
        offset=2,
    )
    
    assert filters.chain_id == 56
    assert filters.min_transactions == 10
    assert filters.sort_by == "total_transactions"
    assert filters.sort_order == "ASC"
    assert filters.limit == 20
    assert filters.offset == 2


def test_schema_sql_generation():
    """Test that schema SQL is generated correctly"""
    schema_sql = get_schema_sql()
    
    # Verify all required tables are in schema
    assert "CREATE TABLE IF NOT EXISTS chains" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS opportunities" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS transactions" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS arbitrageurs" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS chain_stats" in schema_sql
    
    # Verify key indexes are created
    assert "idx_opportunities_chain_block" in schema_sql
    assert "idx_opportunities_profit" in schema_sql
    assert "idx_transactions_chain_block" in schema_sql
    assert "idx_transactions_from_address" in schema_sql
    assert "idx_arbitrageurs_chain" in schema_sql
    
    # Verify foreign key constraints
    assert "FOREIGN KEY (chain_id)" in schema_sql
    
    # Verify check constraints
    assert "CHECK (swap_count >= 2)" in schema_sql
    assert "CHECK (imbalance_pct >= 0)" in schema_sql
    
    # Verify trigger function
    assert "update_updated_at_column" in schema_sql


def test_schema_sql_has_comments():
    """Test that schema includes documentation comments"""
    schema_sql = get_schema_sql()
    
    assert "COMMENT ON TABLE chains" in schema_sql
    assert "COMMENT ON TABLE opportunities" in schema_sql
    assert "COMMENT ON TABLE transactions" in schema_sql
    assert "COMMENT ON TABLE arbitrageurs" in schema_sql
    assert "COMMENT ON COLUMN" in schema_sql


def test_database_manager_initialization():
    """Test DatabaseManager initialization without connection"""
    from src.database import DatabaseManager
    
    db_url = "postgresql://user:pass@localhost/test"
    manager = DatabaseManager(db_url, min_pool_size=3, max_pool_size=10)
    
    assert manager.database_url == db_url
    assert manager.min_pool_size == 3
    assert manager.max_pool_size == 10
    assert manager.pool is None  # Not connected yet


def test_database_manager_default_pool_sizes():
    """Test DatabaseManager default pool sizes"""
    from src.database import DatabaseManager
    
    manager = DatabaseManager("postgresql://user:pass@localhost/test")
    
    assert manager.min_pool_size == 5
    assert manager.max_pool_size == 20
