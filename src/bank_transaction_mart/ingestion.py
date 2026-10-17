"""
ingestion.py — Load raw CSV files into DuckDB raw_transactions table.

Reads source CSV files, validates schema, and inserts raw records.
Does NOT perform business validation (that is done in validation.py).
Reports ingestion statistics.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

# Required columns in the source transactions CSV
REQUIRED_COLUMNS = {
    "source_transaction_id",
    "account_id",
    "customer_id",
    "transaction_date",
    "amount",
    "currency",
    "transaction_type",
    "status",
}


@dataclass
class IngestionStats:
    source_file: str
    rows_read: int = 0
    rows_inserted: int = 0
    schema_errors: int = 0

    def report(self) -> str:
        return (
            f"[Ingestion] {self.source_file}: "
            f"read={self.rows_read}, inserted={self.rows_inserted}, "
            f"schema_errors={self.schema_errors}"
        )


def read_csv(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Read a CSV file. Returns (records, missing_columns).
    If required columns are missing, returns empty records with missing list.
    """
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            logger.error("Missing required columns in %s: %s", path.name, missing)
            return [], list(missing)
        records = list(reader)
    return records, []


def ingest_transactions(
    conn: duckdb.DuckDBPyConnection,
    csv_path: Path,
) -> IngestionStats:
    """
    Load raw transaction records from *csv_path* into raw_transactions.

    Records are loaded as-is (text). Validation happens downstream.
    """
    stats = IngestionStats(source_file=csv_path.name)
    records, missing = read_csv(csv_path)

    if missing:
        stats.schema_errors = len(missing)
        logger.error("Ingestion aborted — missing columns: %s", missing)
        return stats

    stats.rows_read = len(records)

    # Compute next raw_id sequentially
    max_id_result = conn.execute(
        "SELECT COALESCE(MAX(raw_id), 0) FROM raw_transactions"
    ).fetchone()
    next_id = (max_id_result[0] if max_id_result else 0) + 1

    rows: list[tuple] = []
    for i, rec in enumerate(records):
        rows.append((
            next_id + i,
            rec.get("source_transaction_id", ""),
            rec.get("account_id", ""),
            rec.get("customer_id", ""),
            rec.get("transaction_date", ""),
            rec.get("amount", ""),
            rec.get("currency", ""),
            rec.get("transaction_type", ""),
            rec.get("status", ""),
            rec.get("description", ""),
            rec.get("reference_transaction_id", ""),
            csv_path.name,
        ))

    conn.executemany(
        """
        INSERT INTO raw_transactions
            (raw_id, source_transaction_id, account_id, customer_id,
             transaction_date, amount, currency, transaction_type,
             status, description, reference_transaction_id, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    stats.rows_inserted = len(rows)
    logger.info(stats.report())
    return stats


def ingest_customers(conn: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """
    Load customer CSV into a temporary stg_customers table.
    Returns number of rows loaded.
    """
    conn.execute("DROP TABLE IF EXISTS stg_customers")
    conn.execute(f"CREATE TABLE stg_customers AS SELECT * FROM read_csv_auto('{csv_path}')")
    count = conn.execute("SELECT COUNT(*) FROM stg_customers").fetchone()[0]
    logger.info("Loaded %d customers from %s", count, csv_path.name)
    return count


def ingest_accounts(conn: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """
    Load account CSV into a temporary stg_accounts table.
    Returns number of rows loaded.
    """
    conn.execute("DROP TABLE IF EXISTS stg_accounts")
    conn.execute(f"CREATE TABLE stg_accounts AS SELECT * FROM read_csv_auto('{csv_path}')")
    count = conn.execute("SELECT COUNT(*) FROM stg_accounts").fetchone()[0]
    logger.info("Loaded %d accounts from %s", count, csv_path.name)
    return count
