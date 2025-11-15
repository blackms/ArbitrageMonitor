"""Database manager with connection pooling and retry logic"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

import asyncpg
import structlog

from src.database.models import (
    Arbitrageur,
    ArbitrageurFilters,
    ArbitrageTransaction,
    Opportunity,
    OpportunityFilters,
    TransactionFilters,
)
from src.database.schema import get_schema_sql

logger = structlog.get_logger()


class DatabaseManager:
    """
    Manages PostgreSQL database connections and operations with connection pooling.
    
    Features:
    - Connection pooling (min 5, max 20 connections)
    - Automatic retry logic for transient failures (3 attempts with exponential backoff)
    - Parameterized queries to prevent SQL injection
    - Transaction support for multi-table updates
    """

    def __init__(self, database_url: str, min_pool_size: int = 5, max_pool_size: int = 20):
        """
        Initialize database manager.
        
        Args:
            database_url: PostgreSQL connection URL
            min_pool_size: Minimum number of connections in pool
            max_pool_size: Maximum number of connections in pool
        """
        self.database_url = database_url
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.pool: Optional[asyncpg.Pool] = None
        self._logger = logger.bind(component="database_manager")

    async def connect(self) -> None:
        """Establish connection pool to database"""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=self.min_pool_size,
                max_size=self.max_pool_size,
                command_timeout=60,
            )
            self._logger.info(
                "database_connected",
                min_pool_size=self.min_pool_size,
                max_pool_size=self.max_pool_size,
            )
        except Exception as e:
            self._logger.error("database_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            self._logger.info("database_disconnected")

    async def initialize_schema(self) -> None:
        """Initialize database schema"""
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        schema_sql = get_schema_sql()
        async with self.pool.acquire() as conn:
            await conn.execute(schema_sql)
            self._logger.info("database_schema_initialized")

    async def _retry_operation(self, operation, *args, **kwargs):
        """
        Retry database operation with exponential backoff.
        
        Args:
            operation: Async function to retry
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation
            
        Returns:
            Result of operation
            
        Raises:
            Exception: If all retry attempts fail
        """
        max_attempts = 3
        base_delay = 0.5  # seconds

        for attempt in range(1, max_attempts + 1):
            try:
                return await operation(*args, **kwargs)
            except (asyncpg.PostgresError, asyncpg.InterfaceError) as e:
                if attempt == max_attempts:
                    self._logger.error(
                        "database_operation_failed",
                        operation=operation.__name__,
                        attempts=attempt,
                        error=str(e),
                    )
                    raise

                delay = base_delay * (2 ** (attempt - 1))
                self._logger.warning(
                    "database_operation_retry",
                    operation=operation.__name__,
                    attempt=attempt,
                    delay=delay,
                    error=str(e),
                )
                await asyncio.sleep(delay)

    async def save_opportunity(self, opportunity: Opportunity) -> int:
        """
        Save opportunity to database.
        
        Args:
            opportunity: Opportunity object to save
            
        Returns:
            ID of saved opportunity
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized")

        async def _save():
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO opportunities (
                        chain_id, pool_name, pool_address, imbalance_pct,
                        profit_usd, profit_native, reserve0, reserve1,
                        block_number, detected_at, captured, captured_by, capture_tx_hash
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    RETURNING id
                    """,
                    opportunity.chain_id,
                    opportunity.pool_name,
                    opportunity.pool_address,
                    opportunity.imbalance_pct,
                    opportunity.profit_usd,
                    opportunity.profit_native,
                    opportunity.reserve0,
                    opportunity.reserve1,
                    opportunity.block_number,
                    opportunity.detected_at,
                    opportunity.captured,
                    opportunity.captured_by,
                    opportunity.capture_tx_hash,
                )
                return row["id"]

        opportunity_id = await self._retry_operation(_save)
        self._logger.info(
            "opportunity_saved",
            opportunity_id=opportunity_id,
            chain_id=opportunity.chain_id,
            profit_usd=float(opportunity.profit_usd),
        )
        return opportunity_id

    async def save_transaction(self, transaction: ArbitrageTransaction) -> int:
        """
        Save arbitrage transaction to database.
        
        Args:
            transaction: ArbitrageTransaction object to save
            
        Returns:
            ID of saved transaction
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized")

        async def _save():
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO transactions (
                        chain_id, tx_hash, from_address, block_number, block_timestamp,
                        gas_price_gwei, gas_used, gas_cost_native, gas_cost_usd,
                        swap_count, strategy, profit_gross_usd, profit_net_usd,
                        pools_involved, tokens_involved, detected_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                    ON CONFLICT (chain_id, tx_hash) DO UPDATE SET
                        profit_gross_usd = EXCLUDED.profit_gross_usd,
                        profit_net_usd = EXCLUDED.profit_net_usd
                    RETURNING id
                    """,
                    transaction.chain_id,
                    transaction.tx_hash,
                    transaction.from_address,
                    transaction.block_number,
                    transaction.block_timestamp,
                    transaction.gas_price_gwei,
                    transaction.gas_used,
                    transaction.gas_cost_native,
                    transaction.gas_cost_usd,
                    transaction.swap_count,
                    transaction.strategy,
                    transaction.profit_gross_usd,
                    transaction.profit_net_usd,
                    transaction.pools_involved,
                    transaction.tokens_involved,
                    transaction.detected_at,
                )
                return row["id"]

        transaction_id = await self._retry_operation(_save)
        self._logger.info(
            "transaction_saved",
            transaction_id=transaction_id,
            tx_hash=transaction.tx_hash,
            chain_id=transaction.chain_id,
            swap_count=transaction.swap_count,
        )
        return transaction_id

    async def update_arbitrageur(
        self, address: str, chain_id: int, tx_data: Dict
    ) -> None:
        """
        Update or create arbitrageur profile.
        
        Args:
            address: Arbitrageur address
            chain_id: Chain ID
            tx_data: Transaction data containing:
                - success: bool
                - profit_usd: Decimal
                - gas_spent_usd: Decimal
                - gas_price_gwei: Decimal
                - strategy: str
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized")

        async def _update():
            async with self.pool.acquire() as conn:
                # Check if arbitrageur exists
                existing = await conn.fetchrow(
                    """
                    SELECT id, total_transactions, successful_transactions,
                           failed_transactions, total_profit_usd, total_gas_spent_usd,
                           avg_gas_price_gwei
                    FROM arbitrageurs
                    WHERE address = $1 AND chain_id = $2
                    """,
                    address,
                    chain_id,
                )

                if existing:
                    # Update existing arbitrageur
                    total_txs = existing["total_transactions"] + 1
                    successful = existing["successful_transactions"] + (
                        1 if tx_data.get("success", True) else 0
                    )
                    failed = existing["failed_transactions"] + (
                        0 if tx_data.get("success", True) else 1
                    )
                    total_profit = existing["total_profit_usd"] + tx_data.get(
                        "profit_usd", Decimal("0")
                    )
                    total_gas = existing["total_gas_spent_usd"] + tx_data.get(
                        "gas_spent_usd", Decimal("0")
                    )

                    # Calculate running average for gas price
                    if existing["avg_gas_price_gwei"]:
                        avg_gas = (
                            existing["avg_gas_price_gwei"]
                            * existing["total_transactions"]
                            + tx_data.get("gas_price_gwei", Decimal("0"))
                        ) / total_txs
                    else:
                        avg_gas = tx_data.get("gas_price_gwei", Decimal("0"))

                    await conn.execute(
                        """
                        UPDATE arbitrageurs
                        SET last_seen = $1,
                            total_transactions = $2,
                            successful_transactions = $3,
                            failed_transactions = $4,
                            total_profit_usd = $5,
                            total_gas_spent_usd = $6,
                            avg_gas_price_gwei = $7,
                            preferred_strategy = $8
                        WHERE address = $9 AND chain_id = $10
                        """,
                        datetime.utcnow(),
                        total_txs,
                        successful,
                        failed,
                        total_profit,
                        total_gas,
                        avg_gas,
                        tx_data.get("strategy"),
                        address,
                        chain_id,
                    )
                else:
                    # Create new arbitrageur
                    await conn.execute(
                        """
                        INSERT INTO arbitrageurs (
                            address, chain_id, first_seen, last_seen,
                            total_transactions, successful_transactions, failed_transactions,
                            total_profit_usd, total_gas_spent_usd, avg_gas_price_gwei,
                            preferred_strategy, is_bot, contract_address
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                        """,
                        address,
                        chain_id,
                        datetime.utcnow(),
                        datetime.utcnow(),
                        1,
                        1 if tx_data.get("success", True) else 0,
                        0 if tx_data.get("success", True) else 1,
                        tx_data.get("profit_usd", Decimal("0")),
                        tx_data.get("gas_spent_usd", Decimal("0")),
                        tx_data.get("gas_price_gwei", Decimal("0")),
                        tx_data.get("strategy"),
                        False,  # is_bot - would need additional logic to determine
                        False,  # contract_address - would need to check if address is contract
                    )

        await self._retry_operation(_update)
        self._logger.info(
            "arbitrageur_updated", address=address, chain_id=chain_id
        )

    async def get_opportunities(
        self, filters: OpportunityFilters
    ) -> List[Opportunity]:
        """
        Query opportunities with filters.
        
        Args:
            filters: OpportunityFilters object
            
        Returns:
            List of Opportunity objects
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized")

        query = "SELECT * FROM opportunities WHERE 1=1"
        params = []
        param_count = 1

        if filters.chain_id is not None:
            query += f" AND chain_id = ${param_count}"
            params.append(filters.chain_id)
            param_count += 1

        if filters.min_profit is not None:
            query += f" AND profit_usd >= ${param_count}"
            params.append(filters.min_profit)
            param_count += 1

        if filters.max_profit is not None:
            query += f" AND profit_usd <= ${param_count}"
            params.append(filters.max_profit)
            param_count += 1

        if filters.captured is not None:
            query += f" AND captured = ${param_count}"
            params.append(filters.captured)
            param_count += 1

        query += " ORDER BY detected_at DESC"
        query += f" LIMIT ${param_count} OFFSET ${param_count + 1}"
        params.extend([filters.limit, filters.offset])

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        opportunities = [
            Opportunity(
                id=row["id"],
                chain_id=row["chain_id"],
                pool_name=row["pool_name"],
                pool_address=row["pool_address"],
                imbalance_pct=row["imbalance_pct"],
                profit_usd=row["profit_usd"],
                profit_native=row["profit_native"],
                reserve0=row["reserve0"],
                reserve1=row["reserve1"],
                block_number=row["block_number"],
                detected_at=row["detected_at"],
                captured=row["captured"],
                captured_by=row["captured_by"],
                capture_tx_hash=row["capture_tx_hash"],
            )
            for row in rows
        ]

        return opportunities

    async def get_transactions(
        self, filters: TransactionFilters
    ) -> List[ArbitrageTransaction]:
        """
        Query transactions with filters.
        
        Args:
            filters: TransactionFilters object
            
        Returns:
            List of ArbitrageTransaction objects
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized")

        query = "SELECT * FROM transactions WHERE 1=1"
        params = []
        param_count = 1

        if filters.chain_id is not None:
            query += f" AND chain_id = ${param_count}"
            params.append(filters.chain_id)
            param_count += 1

        if filters.from_address is not None:
            query += f" AND from_address = ${param_count}"
            params.append(filters.from_address)
            param_count += 1

        if filters.min_profit is not None:
            query += f" AND profit_net_usd >= ${param_count}"
            params.append(filters.min_profit)
            param_count += 1

        if filters.min_swaps is not None:
            query += f" AND swap_count >= ${param_count}"
            params.append(filters.min_swaps)
            param_count += 1

        if filters.strategy is not None:
            query += f" AND strategy = ${param_count}"
            params.append(filters.strategy)
            param_count += 1

        query += " ORDER BY detected_at DESC"
        query += f" LIMIT ${param_count} OFFSET ${param_count + 1}"
        params.extend([filters.limit, filters.offset])

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        transactions = [
            ArbitrageTransaction(
                id=row["id"],
                chain_id=row["chain_id"],
                tx_hash=row["tx_hash"],
                from_address=row["from_address"],
                block_number=row["block_number"],
                block_timestamp=row["block_timestamp"],
                gas_price_gwei=row["gas_price_gwei"],
                gas_used=row["gas_used"],
                gas_cost_native=row["gas_cost_native"],
                gas_cost_usd=row["gas_cost_usd"],
                swap_count=row["swap_count"],
                strategy=row["strategy"],
                profit_gross_usd=row["profit_gross_usd"],
                profit_net_usd=row["profit_net_usd"],
                pools_involved=row["pools_involved"],
                tokens_involved=row["tokens_involved"],
                detected_at=row["detected_at"],
            )
            for row in rows
        ]

        return transactions

    async def get_arbitrageurs(
        self, filters: ArbitrageurFilters
    ) -> List[Arbitrageur]:
        """
        Query arbitrageurs with filters.
        
        Args:
            filters: ArbitrageurFilters object
            
        Returns:
            List of Arbitrageur objects
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized")

        query = "SELECT * FROM arbitrageurs WHERE 1=1"
        params = []
        param_count = 1

        if filters.chain_id is not None:
            query += f" AND chain_id = ${param_count}"
            params.append(filters.chain_id)
            param_count += 1

        if filters.min_transactions is not None:
            query += f" AND total_transactions >= ${param_count}"
            params.append(filters.min_transactions)
            param_count += 1

        # Validate sort_by to prevent SQL injection
        allowed_sort_fields = [
            "total_profit_usd",
            "total_transactions",
            "last_seen",
            "total_gas_spent_usd",
        ]
        sort_by = (
            filters.sort_by
            if filters.sort_by in allowed_sort_fields
            else "total_profit_usd"
        )
        sort_order = "DESC" if filters.sort_order.upper() == "DESC" else "ASC"

        query += f" ORDER BY {sort_by} {sort_order}"
        query += f" LIMIT ${param_count} OFFSET ${param_count + 1}"
        params.extend([filters.limit, filters.offset])

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        arbitrageurs = [
            Arbitrageur(
                id=row["id"],
                address=row["address"],
                chain_id=row["chain_id"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                total_transactions=row["total_transactions"],
                successful_transactions=row["successful_transactions"],
                failed_transactions=row["failed_transactions"],
                total_profit_usd=row["total_profit_usd"],
                total_gas_spent_usd=row["total_gas_spent_usd"],
                avg_gas_price_gwei=row["avg_gas_price_gwei"],
                preferred_strategy=row["preferred_strategy"],
                is_bot=row["is_bot"],
                contract_address=row["contract_address"],
            )
            for row in rows
        ]

        return arbitrageurs

    async def get_pool_size(self) -> int:
        """Get current connection pool size"""
        if not self.pool:
            return 0
        return self.pool.get_size()

    async def get_pool_free_size(self) -> int:
        """Get number of free connections in pool"""
        if not self.pool:
            return 0
        return self.pool.get_idle_size()
