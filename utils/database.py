"""
SQLite access layer.

Callers that only need SELECT statement use `execute()`; callers that need several
statements to commit or roll back together take a cursor with `acquire_cursor()` and
drive the transaction themselves.

Note on debug logging: the SQL text is logged, the parameters never are. They routinely
carry auth tokens and password hashes, and a debug log is not the place for either.
"""

import logging, asqlite
from typing import Any, overload
from collections.abc import AsyncGenerator

from sqlite3 import Row
from contextlib import asynccontextmanager

from utils.general import ENV

logger = logging.getLogger("cdn.database")


class DatabaseManager:
    """
    Owns the connection pool and hands out cursors from it.
    """

    def __init__(self) -> None:
        # Declared but not assigned: the pool cannot be built without a running event
        # loop, so initialize_pools() finishes the job during startup.
        self.MAIN_POOL: asqlite.Pool = None  # type: ignore[assignment]

    async def initialize_pools(self) -> None:
        """
        Open the connection pool. Must be awaited once, before any query is issued.
        """
        self.MAIN_POOL = await asqlite.create_pool("main.db", size=ENV.DB_POOL_SIZE)

        logger.info(f"Database pool ready ('main.db', size {ENV.DB_POOL_SIZE}).")

    @asynccontextmanager
    async def acquire_cursor(self) -> AsyncGenerator[asqlite.Cursor, None]:
        """
        Borrow a cursor for the duration of the `async with` block.

        Use this when a caller needs to commit or roll back several statements as one unit.
        """
        async with self.MAIN_POOL.acquire() as conn:
            async with conn.cursor() as cur:
                yield cur

    @overload
    async def execute(self, sql: str, params: tuple[Any, ...], fetch_one: bool = False) -> Row | None: ...
    @overload
    async def execute(self, sql: str, params: tuple[Any, ...], fetch_one: bool = False) -> list[Row]: ...

    async def execute(self, sql: str, params: tuple[Any, ...], fetch_one: bool = False) -> Row | None | list[Row]:
        """
        Run one parameterised statement and return its rows.

        A query carrying `LIMIT 1` gets the single row (or None) it asked for, anything
        else gets the full list. Nothing is committed here, so this is for reads only.
        """

        logger.debug(f"Executing query with {len(params)} parameter(s): {sql}")

        async with self.acquire_cursor() as cur:
            _ret: asqlite.Cursor = await cur.execute(sql, params)

            if fetch_one:
                row: Row | None = await _ret.fetchone()

                logger.debug(f"Query matched {'one row' if row is not None else 'nothing'}.")
                return row

            rows: list[Row] = await _ret.fetchall()

            logger.debug(f"Query returned {len(rows)} row(s).")
            return rows


db_manager = DatabaseManager()
