"""
validation.py — Data quality validation and quarantine logic.

All validation rules are defined here as explicit, named functions.
Records that fail validation go to raw_quarantine with a rule code.
This module does NOT silently drop records.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import duckdb

from .config import cfg

logger = logging.getLogger(__name__)

# ── Rule codes ─────────────────────────────────────────────────────────────
RULE_NULL_TRANSACTION_ID  = "VAL-001"
RULE_NULL_ACCOUNT_ID      = "VAL-002"
RULE_NULL_CUSTOMER_ID     = "VAL-003"
RULE_NULL_AMOUNT          = "VAL-004"
RULE_INVALID_AMOUNT       = "VAL-005"
RULE_NEGATIVE_AMOUNT      = "VAL-006"
RULE_INVALID_CURRENCY     = "VAL-007"
RULE_INVALID_STATUS       = "VAL-008"
RULE_INVALID_TIMESTAMP    = "VAL-009"
RULE_NULL_TRANSACTION_TYPE = "VAL-010"


@dataclass
class ValidationResult:
    valid: list[dict[str, Any]] = field(default_factory=list)
    invalid: list[dict[str, Any]] = field(default_factory=list)   # with quarantine_reason added
    duplicate_ids: list[str] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return len(self.valid)

    @property
    def invalid_count(self) -> int:
        return len(self.invalid)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicate_ids)


def _try_parse_amount(value: Any) -> float | None:
    """Return float if value is a valid positive number, else None."""
    if value is None or str(value).strip() == "":
        return None
    try:
        f = float(str(value).strip())
        return f
    except (ValueError, TypeError):
        return None


def _try_parse_timestamp(value: Any) -> datetime | None:
    """Attempt common timestamp formats; return None on failure."""
    if not value:
        return None
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    return None


def validate_records(
    records: list[dict[str, Any]],
    source_file: str = "unknown",
) -> ValidationResult:
    """
    Validate a list of raw transaction records.

    Returns a ValidationResult containing:
      - valid:    records that passed all rules
      - invalid:  records that failed at least one rule (with reason added)
      - duplicate_ids: source_transaction_ids seen more than once
    """
    result = ValidationResult()
    seen_ids: dict[str, int] = {}   # id → first index

    for idx, rec in enumerate(records):
        errors: list[tuple[str, str]] = []  # (rule_code, human_reason)

        # Rule VAL-001: source_transaction_id must be present
        txn_id = rec.get("source_transaction_id", "")
        if not txn_id or str(txn_id).strip() == "":
            errors.append((RULE_NULL_TRANSACTION_ID, "source_transaction_id is null or empty"))

        # Rule VAL-002: account_id
        if not rec.get("account_id"):
            errors.append((RULE_NULL_ACCOUNT_ID, "account_id is null or empty"))

        # Rule VAL-003: customer_id
        if not rec.get("customer_id"):
            errors.append((RULE_NULL_CUSTOMER_ID, "customer_id is null or empty"))

        # Rule VAL-010: transaction_type
        if not rec.get("transaction_type"):
            errors.append((RULE_NULL_TRANSACTION_TYPE, "transaction_type is null or empty"))

        # Rule VAL-004/005/006: amount
        raw_amount = rec.get("amount")
        parsed_amount = _try_parse_amount(raw_amount)
        if parsed_amount is None:
            if raw_amount is None or str(raw_amount).strip() == "":
                errors.append((RULE_NULL_AMOUNT, "amount is null or empty"))
            else:
                errors.append((RULE_INVALID_AMOUNT, f"amount '{raw_amount}' is not numeric"))
        elif parsed_amount < 0:
            errors.append((RULE_NEGATIVE_AMOUNT, f"amount {parsed_amount} is negative"))

        # Rule VAL-007: currency
        currency = rec.get("currency", "")
        if str(currency).strip().upper() not in cfg.VALID_CURRENCIES:
            errors.append((RULE_INVALID_CURRENCY,
                           f"currency '{currency}' not in {cfg.VALID_CURRENCIES}"))

        # Rule VAL-008: status
        status = rec.get("status", "")
        if str(status).strip().upper() not in cfg.VALID_STATUSES:
            errors.append((RULE_INVALID_STATUS,
                           f"status '{status}' not in {cfg.VALID_STATUSES}"))

        # Rule VAL-009: transaction_date parseable
        ts = _try_parse_timestamp(rec.get("transaction_date"))
        if ts is None:
            errors.append((RULE_INVALID_TIMESTAMP,
                           f"transaction_date '{rec.get('transaction_date')}' unparseable"))

        if errors:
            bad = dict(rec)
            bad["_quarantine_rules"] = errors
            bad["_source_file"] = source_file
            result.invalid.append(bad)
        else:
            # Duplicate detection (after per-record validation)
            if txn_id in seen_ids:
                result.duplicate_ids.append(str(txn_id))
                # The duplicate is still appended to valid — the pipeline deduplicates via SQL QUALIFY
            seen_ids.setdefault(str(txn_id), idx)
            result.valid.append(rec)

    logger.info(
        "Validation: %d valid, %d invalid, %d duplicate ids",
        result.valid_count, result.invalid_count, result.duplicate_count,
    )
    return result


def write_quarantine(
    conn: duckdb.DuckDBPyConnection,
    invalid_records: list[dict[str, Any]],
    source_file: str = "unknown",
) -> int:
    """Write quarantined records into raw_quarantine. Returns count inserted."""
    if not invalid_records:
        return 0

    rows: list[tuple] = []
    # Compute next quarantine_id
    max_q = conn.execute("SELECT COALESCE(MAX(quarantine_id), 0) FROM raw_quarantine").fetchone()
    next_q_id = (max_q[0] if max_q else 0) + 1
    counter = 0
    for rec in invalid_records:
        rules = rec.get("_quarantine_rules", [])
        # One quarantine row per failing rule for granular reporting
        for rule_code, reason in rules:
            raw_copy = {k: v for k, v in rec.items()
                        if not k.startswith("_")}
            rows.append((
                next_q_id + counter,
                rec.get("source_transaction_id"),
                json.dumps(raw_copy, default=str),
                reason,
                rule_code,
                source_file,
            ))
            counter += 1

    conn.executemany(
        """
        INSERT INTO raw_quarantine
            (quarantine_id, source_transaction_id, raw_record, quarantine_reason,
             quarantine_rule, source_file)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    logger.info("Quarantined %d rule violations from %d invalid records",
                len(rows), len(invalid_records))
    return len(rows)

