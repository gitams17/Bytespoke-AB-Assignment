"""
conftest.py — Shared pytest fixtures.

All tests use in-memory DuckDB to avoid touching the production database.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bank_transaction_mart.database import get_connection
from bank_transaction_mart.pipeline import init_schema, load_date_dimension


@pytest.fixture()
def mem_conn():
    """
    An in-memory DuckDB connection with the full schema initialised.
    Isolated per test — no file I/O.
    """
    conn = get_connection(":memory:")
    init_schema(conn)
    load_date_dimension(conn)
    yield conn
    conn.close()


@pytest.fixture()
def full_pipeline_conn(tmp_path):
    """
    Run the complete pipeline against a temporary DuckDB file.
    Returns the open connection for post-pipeline assertions.
    """
    from bank_transaction_mart.pipeline import run_pipeline

    db_path = tmp_path / "test_mart.duckdb"
    data_dir = tmp_path / "data"

    run_pipeline(
        db_path=db_path,
        data_dir=data_dir,
        ai_provider="mock",
        regenerate_data=True,
    )

    conn = get_connection(db_path)
    yield conn
    conn.close()
