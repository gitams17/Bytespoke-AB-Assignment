"""
test_pipeline.py — Integration tests: end-to-end pipeline execution.

Tests:
  T01 — Pipeline runs successfully and creates expected tables
  T02 — Fact table has records after pipeline run
  T03 — Dimension tables populated correctly
  T04 — Idempotency: re-running pipeline does not duplicate facts
"""
from __future__ import annotations

import pytest

from bank_transaction_mart.database import row_count, table_exists


class TestPipelineSuccess:
    """T01 — Pipeline creates all expected tables."""

    def test_fact_table_exists(self, full_pipeline_conn):
        assert table_exists(full_pipeline_conn, "fact_transactions")

    def test_dim_customer_exists(self, full_pipeline_conn):
        assert table_exists(full_pipeline_conn, "dim_customer")

    def test_dim_account_exists(self, full_pipeline_conn):
        assert table_exists(full_pipeline_conn, "dim_account")

    def test_dim_date_exists(self, full_pipeline_conn):
        assert table_exists(full_pipeline_conn, "dim_date")

    def test_dim_transaction_type_seeded(self, full_pipeline_conn):
        count = row_count(full_pipeline_conn, "dim_transaction_type")
        assert count == 10, f"Expected 10 transaction types, got {count}"


class TestFactTablePopulated:
    """T02 — Fact table contains records after pipeline."""

    def test_fact_rows_loaded(self, full_pipeline_conn):
        count = row_count(full_pipeline_conn, "fact_transactions")
        assert count > 0, "fact_transactions should have rows after pipeline run"

    def test_fact_rows_reasonable_count(self, full_pipeline_conn):
        count = row_count(full_pipeline_conn, "fact_transactions")
        # Generated ~120 normal + special records, minus invalids/dupes
        assert count >= 100, f"Expected ≥100 fact rows, got {count}"


class TestDimensionsPopulated:
    """T03 — Dimensions populated with expected data."""

    def test_customers_loaded(self, full_pipeline_conn):
        count = row_count(full_pipeline_conn, "dim_customer")
        assert count == 8, f"Expected 8 customers, got {count}"

    def test_accounts_loaded(self, full_pipeline_conn):
        count = row_count(full_pipeline_conn, "dim_account")
        assert count >= 8, f"Expected ≥8 accounts, got {count}"

    def test_date_dimension_populated(self, full_pipeline_conn):
        count = row_count(full_pipeline_conn, "dim_date")
        assert count > 3000, f"dim_date should cover years 2020–2028 (≥3000 rows), got {count}"


class TestIdempotency:
    """T04 — Idempotency: re-running does not create duplicate facts."""

    def test_rerun_does_not_duplicate_facts(self, tmp_path):
        from bank_transaction_mart.pipeline import run_pipeline
        from bank_transaction_mart.database import get_connection

        db_path = tmp_path / "idempotent.duckdb"
        data_dir = tmp_path / "data"

        # First run
        s1 = run_pipeline(db_path=db_path, data_dir=data_dir,
                          ai_provider="mock", regenerate_data=True)
        first_count = s1["fact_rows_loaded"]

        # Second run — same data, same DB
        s2 = run_pipeline(db_path=db_path, data_dir=data_dir,
                          ai_provider="mock", regenerate_data=False)

        conn = get_connection(db_path)
        actual_count = row_count(conn, "fact_transactions")
        conn.close()

        assert actual_count == first_count, (
            f"Idempotency violated: expected {first_count} rows after re-run, "
            f"got {actual_count}"
        )
