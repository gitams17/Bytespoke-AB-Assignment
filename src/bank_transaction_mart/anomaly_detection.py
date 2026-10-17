"""
anomaly_detection.py — Deterministic anomaly detection.

Rule: A transaction is flagged anomalous if its amount exceeds
ANOMALY_THRESHOLD × the customer's 30-day historical median amount
for completed transactions in the same currency, AND the customer
has at least ANOMALY_MIN_HISTORY prior completed transactions.

Design notes:
  • Uses only transactions BEFORE the candidate timestamp (no data leakage).
  • Stores evidence (median, threshold, deviation) alongside the flag.
  • Deterministic: same inputs always produce the same flags.
  • The AI explanation step is separate (see ai/explainer.py).
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import duckdb

from .config import cfg

logger = logging.getLogger(__name__)


@dataclass
class AnomalyEvidence:
    """Structured evidence for one detected anomaly."""
    source_transaction_id: str
    customer_key: int
    account_key: int
    transaction_timestamp: datetime
    amount: float
    currency: str
    customer_median_30d: float
    threshold_multiplier: float
    deviation_ratio: float
    detection_rule_version: str


def _get_historical_amounts(
    conn: duckdb.DuckDBPyConnection,
    customer_key: int,
    before_timestamp: datetime,
    currency: str,
) -> list[float]:
    """
    Return completed transaction amounts for a customer in the 30 days
    BEFORE *before_timestamp*, in the given currency.
    Excludes REVERSAL type to avoid distorting the baseline.
    """
    cutoff_start = before_timestamp.timestamp() - 30 * 86400
    rows = conn.execute(
        """
        SELECT ft.amount
        FROM fact_transactions ft
        JOIN dim_transaction_type dtt
            ON dtt.transaction_type_key = ft.transaction_type_key
        WHERE ft.customer_key = ?
          AND ft.status = 'COMPLETED'
          AND ft.currency = ?
          AND ft.transaction_timestamp < ?
          AND ft.transaction_timestamp >= to_timestamp(?)
          AND dtt.type_code != 'REVERSAL'
        """,
        [customer_key, currency, before_timestamp,
         cutoff_start],
    ).fetchall()
    return [float(r[0]) for r in rows]


def detect_anomalies(conn: duckdb.DuckDBPyConnection) -> list[AnomalyEvidence]:
    """
    Scan all COMPLETED, non-REVERSAL transactions in fact_transactions
    and flag those exceeding the configured threshold.

    Returns a list of AnomalyEvidence dataclasses.
    """
    # Reset existing flags (idempotent re-run)
    conn.execute("UPDATE fact_transactions SET is_anomaly = FALSE")

    candidates = conn.execute(
        """
        SELECT
            ft.source_transaction_id,
            ft.customer_key,
            ft.account_key,
            ft.transaction_timestamp,
            ft.amount,
            ft.currency
        FROM fact_transactions ft
        JOIN dim_transaction_type dtt
            ON dtt.transaction_type_key = ft.transaction_type_key
        WHERE ft.status = 'COMPLETED'
          AND dtt.type_code != 'REVERSAL'
        ORDER BY ft.transaction_timestamp
        """
    ).fetchall()

    evidence_list: list[AnomalyEvidence] = []

    for row in candidates:
        txn_id, cust_key, acct_key, ts, amount, currency = row
        amount = float(amount)

        history = _get_historical_amounts(conn, cust_key, ts, currency)

        if len(history) < cfg.ANOMALY_MIN_HISTORY:
            continue  # insufficient history — do not flag

        median_val = statistics.median(history)

        if median_val <= 0:
            continue  # zero baseline — cannot compute meaningful ratio

        deviation = amount / median_val

        if deviation >= cfg.ANOMALY_THRESHOLD:
            conn.execute(
                "UPDATE fact_transactions SET is_anomaly = TRUE "
                "WHERE source_transaction_id = ?",
                [txn_id],
            )
            ev = AnomalyEvidence(
                source_transaction_id=str(txn_id),
                customer_key=int(cust_key),
                account_key=int(acct_key),
                transaction_timestamp=ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts)),
                amount=amount,
                currency=str(currency),
                customer_median_30d=round(median_val, 2),
                threshold_multiplier=cfg.ANOMALY_THRESHOLD,
                deviation_ratio=round(deviation, 2),
                detection_rule_version=cfg.ANOMALY_RULE_VERSION,
            )
            evidence_list.append(ev)
            logger.info(
                "Anomaly detected: %s | amount=%.2f | median=%.2f | ratio=%.2f×",
                txn_id, amount, median_val, deviation,
            )

    logger.info("Anomaly detection complete: %d anomalies flagged", len(evidence_list))
    return evidence_list


def get_anomaly_summary(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Return a list of dicts describing all flagged anomalies with their explanations."""
    rows = conn.execute(
        """
        SELECT
            ft.source_transaction_id,
            dc.customer_id,
            dc.full_name,
            da.account_id,
            ft.transaction_timestamp,
            ft.amount,
            ft.currency,
            ae.customer_median_30d,
            ae.threshold_multiplier,
            ae.deviation_ratio,
            ae.explanation_status,
            ae.summary
        FROM fact_transactions ft
        JOIN dim_customer dc ON dc.customer_key = ft.customer_key
        JOIN dim_account  da ON da.account_key  = ft.account_key
        LEFT JOIN anomaly_explanations ae
            ON ae.source_transaction_id = ft.source_transaction_id
        WHERE ft.is_anomaly = TRUE
        ORDER BY ft.transaction_timestamp
        """
    ).fetchall()

    keys = [
        "source_transaction_id", "customer_id", "full_name", "account_id",
        "transaction_timestamp", "amount", "currency",
        "customer_median_30d", "threshold_multiplier", "deviation_ratio",
        "explanation_status", "summary",
    ]
    return [dict(zip(keys, row)) for row in rows]
