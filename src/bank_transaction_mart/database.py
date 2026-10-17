"""
database.py — DuckDB connection management.

Single connection factory used by the entire pipeline.
DuckDB is an embedded analytical database — no server needed.
"""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from .config import cfg

logger = logging.getLogger(__name__)


def get_connection(db_path: str | Path | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """
    Return a DuckDB connection.

    Parameters
    ----------
    db_path : str | Path | None
        Override the default path from config. Use ":memory:" for in-memory DB.
    read_only : bool
        Open in read-only mode.
    """
    path = Path(db_path) if db_path is not None else cfg.db_path()

    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug("Opening DuckDB at %s (read_only=%s)", path, read_only)

    conn = duckdb.connect(str(path), read_only=read_only)
    return conn


def execute_sql_file(conn: duckdb.DuckDBPyConnection, sql_file: Path) -> None:
    """Execute a .sql file against *conn*."""
    sql = sql_file.read_text(encoding="utf-8")
    try:
        conn.execute(sql)
    except duckdb.Error as exc:
        logger.error("SQL error in %s: %s", sql_file.name, exc)
        raise



def table_exists(conn: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    """Return True if *table_name* exists in the connected database."""
    result = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [table_name],
    ).fetchone()
    return bool(result and result[0] > 0)


def row_count(conn: duckdb.DuckDBPyConnection, table_name: str) -> int:
    """Return the row count of *table_name*."""
    result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()  # noqa: S608
    return result[0] if result else 0
