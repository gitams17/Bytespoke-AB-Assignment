"""
test_data_quality.py — Data quality and validation tests.

Tests:
  T05 — Duplicate transaction handling
  T06 — Invalid/missing data quarantined correctly
  T07 — Fact surrogate key uniqueness
  T08 — Referential integrity (all FK keys resolve)
  T09 — Valid status values only in fact table
"""
from __future__ import annotations

import pytest

from bank_transaction_mart.validation import validate_records, write_quarantine
from bank_transaction_mart.database import row_count


class TestDuplicateHandling:
    """T05 — Duplicate source_transaction_ids detected and handled."""

    def test_duplicates_detected(self):
        records = [
            {"source_transaction_id": "TXN-001", "account_id": "ACCT-0001",
             "customer_id": "CUST-0001", "transaction_date": "2024-01-01T10:00:00",
             "amount": "100.00", "currency": "USD", "transaction_type": "PURCHASE",
             "status": "COMPLETED", "description": "Test"},
            {"source_transaction_id": "TXN-001", "account_id": "ACCT-0001",
             "customer_id": "CUST-0001", "transaction_date": "2024-01-01T10:00:00",
             "amount": "100.00", "currency": "USD", "transaction_type": "PURCHASE",
             "status": "COMPLETED", "description": "Duplicate"},
        ]
        result = validate_records(records)
        assert result.duplicate_count == 1, (
            f"Expected 1 duplicate, got {result.duplicate_count}"
        )

    def test_duplicates_do_not_create_extra_facts(self, full_pipeline_conn):
        """Verify that duplicate source records produce only one fact row each."""
        count_result = full_pipeline_conn.execute(
            """
            SELECT COUNT(*) - COUNT(DISTINCT source_transaction_id)
            FROM fact_transactions
            """
        ).fetchone()
        assert count_result[0] == 0, (
            "Fact table contains duplicate source_transaction_ids"
        )


class TestInvalidDataHandling:
    """T06 — Invalid records are quarantined, not silently dropped."""

    def test_null_amount_quarantined(self, mem_conn):
        invalid_records = [
            {"source_transaction_id": "TXN-BAD-001", "account_id": "ACCT-0001",
             "customer_id": "CUST-0001", "transaction_date": "2024-01-01T10:00:00",
             "amount": "", "currency": "USD", "transaction_type": "PURCHASE",
             "status": "COMPLETED", "description": "Missing amount"},
        ]
        result = validate_records(invalid_records)
        assert result.invalid_count == 1
        quarantine_count = write_quarantine(mem_conn, result.invalid, "test.csv")
        assert quarantine_count > 0

        in_quarantine = mem_conn.execute(
            "SELECT COUNT(*) FROM raw_quarantine WHERE source_transaction_id = 'TXN-BAD-001'"
        ).fetchone()[0]
        assert in_quarantine > 0, "Invalid record should appear in raw_quarantine"

    def test_invalid_currency_quarantined(self):
        records = [
            {"source_transaction_id": "TXN-BAD-002", "account_id": "ACCT-0001",
             "customer_id": "CUST-0001", "transaction_date": "2024-01-01T10:00:00",
             "amount": "200.00", "currency": "XXX", "transaction_type": "DEPOSIT",
             "status": "COMPLETED", "description": "Bad currency"},
        ]
        result = validate_records(records)
        assert result.invalid_count == 1

    def test_quarantine_has_rule_code(self, mem_conn):
        invalid = [
            {"source_transaction_id": "TXN-BAD-003", "account_id": "ACCT-0001",
             "customer_id": "CUST-0001", "transaction_date": "2024-01-01T10:00:00",
             "amount": "", "currency": "USD", "transaction_type": "PURCHASE",
             "status": "COMPLETED", "description": "x",
             "_quarantine_rules": [("VAL-004", "amount is null or empty")],
             "_source_file": "test.csv"},
        ]
        write_quarantine(mem_conn, invalid, "test.csv")
        row = mem_conn.execute(
            "SELECT quarantine_rule FROM raw_quarantine LIMIT 1"
        ).fetchone()
        assert row is not None and row[0].startswith("VAL-"), (
            "Quarantine rule code must start with 'VAL-'"
        )

    def test_invalid_records_excluded_from_facts(self, full_pipeline_conn):
        """The two seeded invalid records (TXN-INVALID*) must not appear in facts."""
        count = full_pipeline_conn.execute(
            """
            SELECT COUNT(*) FROM fact_transactions
            WHERE source_transaction_id LIKE 'TXN-INVALID%'
            """
        ).fetchone()[0]
        assert count == 0, (
            f"Invalid records TXN-INVALID* should not be in fact_transactions, found {count}"
        )


class TestDataQualityChecks:
    """T07-T09 — Structural integrity checks on the populated mart."""

    def test_fact_key_uniqueness(self, full_pipeline_conn):
        result = full_pipeline_conn.execute(
            "SELECT COUNT(*) - COUNT(DISTINCT transaction_key) FROM fact_transactions"
        ).fetchone()[0]
        assert result == 0, "transaction_key must be unique in fact_transactions"

    def test_fk_customer_integrity(self, full_pipeline_conn):
        orphans = full_pipeline_conn.execute(
            """
            SELECT COUNT(*) FROM fact_transactions ft
            LEFT JOIN dim_customer dc ON dc.customer_key = ft.customer_key
            WHERE dc.customer_key IS NULL
            """
        ).fetchone()[0]
        assert orphans == 0, f"{orphans} fact rows have no matching customer"

    def test_fk_account_integrity(self, full_pipeline_conn):
        orphans = full_pipeline_conn.execute(
            """
            SELECT COUNT(*) FROM fact_transactions ft
            LEFT JOIN dim_account da ON da.account_key = ft.account_key
            WHERE da.account_key IS NULL
            """
        ).fetchone()[0]
        assert orphans == 0, f"{orphans} fact rows have no matching account"

    def test_valid_status_values(self, full_pipeline_conn):
        invalid = full_pipeline_conn.execute(
            """
            SELECT COUNT(*) FROM fact_transactions
            WHERE status NOT IN ('COMPLETED', 'PENDING', 'FAILED', 'REVERSED')
            """
        ).fetchone()[0]
        assert invalid == 0, f"{invalid} rows have an invalid status value"
