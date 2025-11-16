"""Data retention service for managing database cleanup and archival"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

from src.database.manager import DatabaseManager

logger = structlog.get_logger()


class DataRetentionService:
    """
    Service for managing data retention and archival policies.
    
    Features:
    - Delete opportunities older than 30 days
    - Archive transactions older than 90 days
    - Run retention jobs during low-activity hours (2 AM - 4 AM UTC)
    - Maintain referential integrity during deletion/archival
    """

    def __init__(
        self,
        database_manager: DatabaseManager,
        opportunity_retention_days: int = 30,
        transaction_archive_days: int = 90,
        run_hour_utc: int = 2,
    ):
        """
        Initialize data retention service.
        
        Args:
            database_manager: DatabaseManager instance
            opportunity_retention_days: Days to retain opportunities (default: 30)
            transaction_archive_days: Days before archiving transactions (default: 90)
            run_hour_utc: Hour (UTC) to run retention jobs (default: 2 AM)
        """
        self.db = database_manager
        self.opportunity_retention_days = opportunity_retention_days
        self.transaction_archive_days = transaction_archive_days
        self.run_hour_utc = run_hour_utc
        self._logger = logger.bind(component="data_retention_service")
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the data retention service"""
        if self._running:
            self._logger.warning("data_retention_service_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        self._logger.info(
            "data_retention_service_started",
            opportunity_retention_days=self.opportunity_retention_days,
            transaction_archive_days=self.transaction_archive_days,
            run_hour_utc=self.run_hour_utc,
        )

    async def stop(self) -> None:
        """Stop the data retention service"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._logger.info("data_retention_service_stopped")

    async def _run_scheduler(self) -> None:
        """Run the scheduler that executes retention jobs at specified time"""
        while self._running:
            try:
                # Calculate time until next run (2 AM - 4 AM UTC window)
                now = datetime.now(timezone.utc)
                next_run = self._calculate_next_run_time(now)
                wait_seconds = (next_run - now).total_seconds()

                self._logger.info(
                    "data_retention_scheduler_waiting",
                    next_run=next_run.isoformat(),
                    wait_seconds=wait_seconds,
                )

                # Wait until next run time
                await asyncio.sleep(wait_seconds)

                if not self._running:
                    break

                # Execute retention jobs
                await self._execute_retention_jobs()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(
                    "data_retention_scheduler_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Wait 1 hour before retrying on error
                await asyncio.sleep(3600)

    def _calculate_next_run_time(self, now: datetime) -> datetime:
        """
        Calculate the next run time within the 2 AM - 4 AM UTC window.
        
        Args:
            now: Current datetime (UTC)
            
        Returns:
            Next run datetime (UTC)
        """
        # Start of today's window
        today_run = now.replace(
            hour=self.run_hour_utc, minute=0, second=0, microsecond=0
        )

        if now < today_run:
            # Run today if we haven't passed the window yet
            return today_run
        else:
            # Run tomorrow
            return today_run + timedelta(days=1)

    async def _execute_retention_jobs(self) -> None:
        """Execute all retention jobs"""
        self._logger.info("data_retention_jobs_started")
        start_time = datetime.now(timezone.utc)

        try:
            # Delete old opportunities
            opportunities_deleted = await self.delete_old_opportunities()

            # Archive old transactions
            transactions_archived = await self.archive_old_transactions()

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self._logger.info(
                "data_retention_jobs_completed",
                opportunities_deleted=opportunities_deleted,
                transactions_archived=transactions_archived,
                duration_seconds=duration,
            )

        except Exception as e:
            self._logger.error(
                "data_retention_jobs_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def delete_old_opportunities(self) -> int:
        """
        Delete opportunities older than retention period.
        
        Returns:
            Number of opportunities deleted
        """
        if not self.db.pool:
            raise RuntimeError("Database pool not initialized")

        cutoff_date = datetime.now(timezone.utc) - timedelta(
            days=self.opportunity_retention_days
        )

        self._logger.info(
            "deleting_old_opportunities",
            cutoff_date=cutoff_date.isoformat(),
            retention_days=self.opportunity_retention_days,
        )

        try:
            async with self.db.pool.acquire() as conn:
                # Delete opportunities older than cutoff date
                result = await conn.execute(
                    """
                    DELETE FROM opportunities
                    WHERE detected_at < $1
                    """,
                    cutoff_date,
                )

                # Extract count from result string (e.g., "DELETE 42")
                deleted_count = int(result.split()[-1]) if result else 0

                self._logger.info(
                    "old_opportunities_deleted",
                    count=deleted_count,
                    cutoff_date=cutoff_date.isoformat(),
                )

                return deleted_count

        except Exception as e:
            self._logger.error(
                "delete_old_opportunities_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def archive_old_transactions(self) -> int:
        """
        Archive transactions older than archive period.
        
        This implementation moves old transactions to an archive table
        while maintaining referential integrity with arbitrageurs.
        
        Returns:
            Number of transactions archived
        """
        if not self.db.pool:
            raise RuntimeError("Database pool not initialized")

        cutoff_date = datetime.now(timezone.utc) - timedelta(
            days=self.transaction_archive_days
        )

        self._logger.info(
            "archiving_old_transactions",
            cutoff_date=cutoff_date.isoformat(),
            archive_days=self.transaction_archive_days,
        )

        try:
            async with self.db.pool.acquire() as conn:
                # Start transaction to ensure atomicity
                async with conn.transaction():
                    # Create archive table if it doesn't exist
                    await conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS transactions_archive (
                            LIKE transactions INCLUDING ALL
                        )
                        """
                    )

                    # Move old transactions to archive table
                    result = await conn.execute(
                        """
                        WITH moved_rows AS (
                            DELETE FROM transactions
                            WHERE detected_at < $1
                            RETURNING *
                        )
                        INSERT INTO transactions_archive
                        SELECT * FROM moved_rows
                        """,
                        cutoff_date,
                    )

                    # Extract count from result string (e.g., "INSERT 0 42")
                    archived_count = int(result.split()[-1]) if result else 0

                    self._logger.info(
                        "old_transactions_archived",
                        count=archived_count,
                        cutoff_date=cutoff_date.isoformat(),
                    )

                    return archived_count

        except Exception as e:
            self._logger.error(
                "archive_old_transactions_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def run_once(self) -> None:
        """
        Execute retention jobs immediately (useful for testing or manual runs).
        
        This bypasses the scheduler and runs the jobs right away.
        """
        self._logger.info("data_retention_manual_run_started")
        await self._execute_retention_jobs()
