"""
analytics.py — Run and display analytical SQL queries.

Each public function returns a list of dicts and optionally prints a table.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb

try:
    from tabulate import tabulate
    _HAS_TABULATE = True
except ImportError:
    _HAS_TABULATE = False

logger = logging.getLogger(__name__)


def _rows_to_dicts(conn: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    result = conn.execute(sql)
    columns = [d[0] for d in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def _print_table(title: str, rows: list[dict[str, Any]], max_rows: int = 20) -> None:
    if not rows:
        print(f"\n{title}\n  (no rows)\n")
        return
    displayed = rows[:max_rows]
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")
    if _HAS_TABULATE:
        print(tabulate(displayed, headers="keys", tablefmt="psql", floatfmt=".2f"))
    else:
        headers = list(displayed[0].keys())
        print("  " + " | ".join(headers))
        for row in displayed:
            print("  " + " | ".join(str(v) for v in row.values()))
    if len(rows) > max_rows:
        print(f"  … {len(rows) - max_rows} more rows not shown")
    print()


def customer_summary(conn: duckdb.DuckDBPyConnection, print_output: bool = True) -> list[dict]:
    sql = """
    SELECT
        dc.customer_id,
        dc.full_name,
        dc.customer_segment,
        COUNT(ft.transaction_key)                                     AS total_txns,
        COUNT(CASE WHEN ft.status = 'COMPLETED' THEN 1 END)           AS completed,
        ROUND(SUM(CASE WHEN ft.status='COMPLETED' AND ft.currency='USD'
                       THEN ft.amount ELSE 0 END), 2)                 AS completed_usd,
        ROUND(AVG(CASE WHEN ft.currency='USD' THEN ft.amount END), 2) AS avg_amount_usd
    FROM fact_transactions ft
    JOIN dim_customer dc ON dc.customer_key = ft.customer_key
    GROUP BY dc.customer_id, dc.full_name, dc.customer_segment
    ORDER BY completed_usd DESC
    """
    rows = _rows_to_dicts(conn, sql)
    if print_output:
        _print_table("CUSTOMER ANALYTICS — Transaction Count & Completed Value", rows)
    return rows


def account_summary(conn: duckdb.DuckDBPyConnection, print_output: bool = True) -> list[dict]:
    sql = """
    SELECT
        da.account_id,
        da.account_type,
        dc.customer_id,
        COUNT(ft.transaction_key)                                           AS total_txns,
        ROUND(SUM(CASE WHEN ft.status='COMPLETED' AND ft.currency='USD'
                       THEN ft.amount ELSE 0 END), 2)                       AS completed_usd,
        COUNT(CASE WHEN ft.status = 'FAILED'  THEN 1 END)                  AS failed,
        COUNT(CASE WHEN ft.status = 'PENDING' THEN 1 END)                  AS pending
    FROM fact_transactions ft
    JOIN dim_account  da ON da.account_key  = ft.account_key
    JOIN dim_customer dc ON dc.customer_key = da.customer_key
    GROUP BY da.account_id, da.account_type, dc.customer_id
    ORDER BY completed_usd DESC
    """
    rows = _rows_to_dicts(conn, sql)
    if print_output:
        _print_table("ACCOUNT ANALYTICS — Transaction Count & Completed Value", rows)
    return rows


def daily_volume(conn: duckdb.DuckDBPyConnection, print_output: bool = True) -> list[dict]:
    sql = """
    SELECT
        dd.full_date::VARCHAR                                               AS date,
        dd.day_name,
        COUNT(ft.transaction_key)                                           AS txn_count,
        ROUND(SUM(CASE WHEN ft.currency='USD' THEN ft.amount ELSE 0 END), 2) AS total_usd
    FROM fact_transactions ft
    JOIN dim_date dd ON dd.date_key = ft.date_key
    GROUP BY dd.full_date, dd.day_name
    ORDER BY dd.full_date
    """
    rows = _rows_to_dicts(conn, sql)
    if print_output:
        _print_table("DAILY TRANSACTION VOLUME", rows, max_rows=15)
    return rows


def status_distribution(conn: duckdb.DuckDBPyConnection, print_output: bool = True) -> list[dict]:
    sql = """
    SELECT
        status,
        COUNT(*)                                       AS count,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) AS pct
    FROM fact_transactions
    GROUP BY status
    ORDER BY count DESC
    """
    rows = _rows_to_dicts(conn, sql)
    if print_output:
        _print_table("STATUS DISTRIBUTION", rows)
    return rows


def type_distribution(conn: duckdb.DuckDBPyConnection, print_output: bool = True) -> list[dict]:
    sql = """
    SELECT
        dtt.type_code,
        dtt.type_category,
        COUNT(ft.transaction_key)                      AS count,
        ROUND(SUM(CASE WHEN ft.currency='USD' THEN ft.amount ELSE 0 END), 2) AS total_usd
    FROM fact_transactions ft
    JOIN dim_transaction_type dtt ON dtt.transaction_type_key = ft.transaction_type_key
    GROUP BY dtt.type_code, dtt.type_category
    ORDER BY count DESC
    """
    rows = _rows_to_dicts(conn, sql)
    if print_output:
        _print_table("TRANSACTION TYPE DISTRIBUTION", rows)
    return rows


def anomaly_report(conn: duckdb.DuckDBPyConnection, print_output: bool = True) -> list[dict]:
    sql = """
    SELECT
        ft.source_transaction_id,
        dc.customer_id,
        dc.full_name,
        ft.transaction_timestamp::VARCHAR               AS timestamp,
        ft.amount,
        ft.currency,
        ae.customer_median_30d,
        ae.deviation_ratio,
        ae.explanation_status,
        ae.summary
    FROM fact_transactions ft
    JOIN dim_customer dc ON dc.customer_key = ft.customer_key
    LEFT JOIN anomaly_explanations ae
          ON ae.source_transaction_id = ft.source_transaction_id
    WHERE ft.is_anomaly = TRUE
    ORDER BY ft.transaction_timestamp
    """
    rows = _rows_to_dicts(conn, sql)
    if print_output:
        _print_table("ANOMALY REPORT", rows)
    return rows


def run_all(conn: duckdb.DuckDBPyConnection) -> None:
    """Run all analytics queries and print results."""
    customer_summary(conn)
    account_summary(conn)
    daily_volume(conn)
    status_distribution(conn)
    type_distribution(conn)
    anomaly_report(conn)
