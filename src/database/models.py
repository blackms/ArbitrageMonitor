"""Data models for database entities"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional


@dataclass
class Opportunity:
    """Detected pool imbalance opportunity"""

    chain_id: int
    pool_name: str
    pool_address: str
    imbalance_pct: Decimal
    profit_usd: Decimal
    profit_native: Decimal
    reserve0: Decimal
    reserve1: Decimal
    block_number: int
    detected_at: datetime
    id: Optional[int] = None
    captured: bool = False
    captured_by: Optional[str] = None
    capture_tx_hash: Optional[str] = None


@dataclass
class ArbitrageTransaction:
    """Arbitrage transaction with multiple swaps"""

    chain_id: int
    tx_hash: str
    from_address: str
    block_number: int
    block_timestamp: datetime
    gas_price_gwei: Decimal
    gas_used: int
    gas_cost_native: Decimal
    gas_cost_usd: Decimal
    swap_count: int
    strategy: str
    pools_involved: List[str]
    tokens_involved: List[str]
    detected_at: datetime
    id: Optional[int] = None
    profit_gross_usd: Optional[Decimal] = None
    profit_net_usd: Optional[Decimal] = None


@dataclass
class Arbitrageur:
    """Arbitrageur profile with statistics"""

    address: str
    chain_id: int
    first_seen: datetime
    last_seen: datetime
    total_transactions: int
    successful_transactions: int
    failed_transactions: int
    total_profit_usd: Decimal
    total_gas_spent_usd: Decimal
    id: Optional[int] = None
    avg_gas_price_gwei: Optional[Decimal] = None
    preferred_strategy: Optional[str] = None
    is_bot: bool = False
    contract_address: bool = False


@dataclass
class OpportunityFilters:
    """Filters for querying opportunities"""

    chain_id: Optional[int] = None
    min_profit: Optional[Decimal] = None
    max_profit: Optional[Decimal] = None
    captured: Optional[bool] = None
    limit: int = 100
    offset: int = 0


@dataclass
class TransactionFilters:
    """Filters for querying transactions"""

    chain_id: Optional[int] = None
    from_address: Optional[str] = None
    min_profit: Optional[Decimal] = None
    min_swaps: Optional[int] = None
    strategy: Optional[str] = None
    limit: int = 100
    offset: int = 0


@dataclass
class ArbitrageurFilters:
    """Filters for querying arbitrageurs"""

    chain_id: Optional[int] = None
    min_transactions: Optional[int] = None
    sort_by: str = "total_profit_usd"
    sort_order: str = "DESC"
    limit: int = 100
    offset: int = 0
