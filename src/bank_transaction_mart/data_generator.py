"""
data_generator.py — Synthetic banking data generator.

Generates reproducible, fictional customers, accounts, and transactions.
Uses Faker with a fixed seed for determinism.
Intentionally seeds:
  • Duplicate transactions (same source_transaction_id)
  • Invalid records (null amount, bad currency, malformed date)
  • One anomalous high-value transaction (amount >> customer median)
  • One reversal transaction

All data is purely fictional. No real banking data is used.
"""
from __future__ import annotations

import csv
import logging
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from faker import Faker

from .config import cfg

logger = logging.getLogger(__name__)

fake = Faker("en_US")

# ── Constants ──────────────────────────────────────────────────────────────
CUSTOMER_SEGMENTS = ["RETAIL", "SME", "CORPORATE"]
RISK_RATINGS = ["LOW", "MEDIUM", "HIGH"]
ACCOUNT_TYPES = ["CHECKING", "SAVINGS", "CREDIT"]
TRANSACTION_TYPES = ["PURCHASE", "TRANSFER", "WITHDRAWAL", "DEPOSIT", "FEE"]
STATUSES = ["COMPLETED", "COMPLETED", "COMPLETED", "PENDING", "FAILED"]  # weighted
BASE_DATE = date(2024, 1, 1)
NUM_CUSTOMERS = 8
NUM_ACCOUNTS = 12
NUM_TRANSACTIONS = 120


def _txn_id() -> str:
    # random.randbytes keeps IDs deterministic under random.seed(); uuid4 does not
    return f"TXN-{random.randbytes(6).hex().upper()}"


def _cust_id(i: int) -> str:
    return f"CUST-{i:04d}"


def _acct_id(i: int) -> str:
    return f"ACCT-{i:04d}"


def generate_customers(seed: int = cfg.DATA_SEED) -> list[dict[str, Any]]:
    """Generate a list of synthetic customer records."""
    Faker.seed(seed)
    random.seed(seed)
    customers = []
    for i in range(1, NUM_CUSTOMERS + 1):
        customers.append(
            {
                "customer_id": _cust_id(i),
                "customer_name": fake.name(),
                "email": fake.email(),
                "phone": fake.phone_number()[:20],
                "country": random.choice(["US", "SE", "GB", "DE"]),
                "customer_segment": random.choice(CUSTOMER_SEGMENTS),
                "risk_rating": random.choice(RISK_RATINGS),
                "onboarded_date": (BASE_DATE - timedelta(days=random.randint(30, 1200))).isoformat(),
            }
        )
    return customers


def generate_accounts(customers: list[dict], seed: int = cfg.DATA_SEED) -> list[dict[str, Any]]:
    """Generate synthetic accounts — 1–2 accounts per customer."""
    random.seed(seed + 1)
    accounts = []
    acct_counter = 1
    for cust in customers:
        num_accounts = random.randint(1, 2)
        for _ in range(num_accounts):
            if acct_counter > NUM_ACCOUNTS:
                break
            accounts.append(
                {
                    "account_id": _acct_id(acct_counter),
                    "customer_id": cust["customer_id"],
                    "account_type": random.choice(ACCOUNT_TYPES),
                    "currency": "USD",
                    "opened_date": cust["onboarded_date"],
                    "credit_limit": round(random.uniform(1000, 20000), 2)
                    if random.random() > 0.5
                    else None,
                }
            )
            acct_counter += 1
    return accounts


def generate_transactions(
    accounts: list[dict],
    seed: int = cfg.DATA_SEED,
    num_transactions: int = NUM_TRANSACTIONS,
) -> list[dict[str, Any]]:
    """
    Generate synthetic transactions including intentional edge cases:
      - 2 duplicate source_transaction_ids
      - 2 invalid records (null amount, bad currency)
      - 1 seeded anomaly (amount = 50× a customer's typical amount)
      - 1 reversal linked to a prior completed transaction
    """
    random.seed(seed + 2)
    Faker.seed(seed + 2)
    transactions: list[dict[str, Any]] = []
    acct_ids = [a["account_id"] for a in accounts]
    acct_to_cust = {a["account_id"]: a["customer_id"] for a in accounts}

    # Normal transactions
    completed_txn_ids: list[str] = []
    for i in range(num_transactions):
        acct_id = random.choice(acct_ids)
        amount = round(random.uniform(10, 800), 2)
        status = random.choice(STATUSES)
        txn_id = _txn_id()
        txn_date = BASE_DATE + timedelta(days=random.randint(0, 180))
        txn_ts = datetime(txn_date.year, txn_date.month, txn_date.day,
                          random.randint(8, 18), random.randint(0, 59))
        rec = {
            "source_transaction_id": txn_id,
            "account_id": acct_id,
            "customer_id": acct_to_cust[acct_id],
            "transaction_date": txn_ts.isoformat(),
            "amount": amount,
            "currency": "USD",
            "transaction_type": random.choice(TRANSACTION_TYPES),
            "status": status,
            "description": fake.bs()[:80],
            "reference_transaction_id": "",
        }
        transactions.append(rec)
        if status == "COMPLETED":
            completed_txn_ids.append(txn_id)

    # ── Seeded anomaly: CUST-0001's first account with 50× median amount ──
    anomaly_acct = accounts[0]["account_id"]
    anomaly_cust = accounts[0]["customer_id"]
    anomaly_txn_id = "TXN-ANOMALY000001"
    anomaly_ts = datetime(2024, 6, 15, 14, 30)
    transactions.append(
        {
            "source_transaction_id": anomaly_txn_id,
            "account_id": anomaly_acct,
            "customer_id": anomaly_cust,
            "transaction_date": anomaly_ts.isoformat(),
            "amount": 45000.00,   # seeded anomaly — far above typical ~400 median
            "currency": "USD",
            "transaction_type": "TRANSFER",
            "status": "COMPLETED",
            "description": "Large international wire transfer — anomaly seed",
            "reference_transaction_id": "",
        }
    )

    # ── Guaranteed 30-day baseline for anomaly detection ──────────────────
    # Anomaly detector requires >=3 COMPLETED transactions in the 30-day window
    # before the anomaly timestamp. These fixed records ensure TXN-ANOMALY000001
    # is always flagged regardless of the random seed's transaction distribution.
    _history_dates = [
        datetime(2024, 5, 20, 9, 0),
        datetime(2024, 5, 28, 11, 30),
        datetime(2024, 6, 5, 14, 15),
        datetime(2024, 6, 10, 16, 45),
    ]
    _history_amounts = [85.50, 120.00, 95.75, 110.25]
    for _i, (_hts, _hamt) in enumerate(zip(_history_dates, _history_amounts)):
        transactions.append(
            {
                "source_transaction_id": f"TXN-HISTORY00000{_i + 1}",
                "account_id": anomaly_acct,
                "customer_id": anomaly_cust,
                "transaction_date": _hts.isoformat(),
                "amount": _hamt,
                "currency": "USD",
                "transaction_type": "PURCHASE",
                "status": "COMPLETED",
                "description": f"Normal history transaction {_i + 1} — anomaly baseline",
                "reference_transaction_id": "",
            }
        )

    # ── Seeded reversal ────────────────────────────────────────────────────
    if completed_txn_ids:
        orig_id = completed_txn_ids[0]
        reversal_ts = datetime(2024, 3, 20, 10, 0)
        transactions.append(
            {
                "source_transaction_id": "TXN-REVERSAL000001",
                "account_id": acct_ids[0],
                "customer_id": acct_to_cust[acct_ids[0]],
                "transaction_date": reversal_ts.isoformat(),
                "amount": 150.00,
                "currency": "USD",
                "transaction_type": "REVERSAL",
                "status": "COMPLETED",
                "description": "Chargeback — disputed purchase",
                "reference_transaction_id": orig_id,
            }
        )

    # ── Intentional duplicates ─────────────────────────────────────────────
    if transactions:
        dup = dict(transactions[5])          # copy of a valid transaction
        transactions.append(dup)             # exact duplicate
        dup2 = dict(transactions[10])
        transactions.append(dup2)

    # ── Intentional invalid records ────────────────────────────────────────
    # Invalid 1: NULL amount
    transactions.append(
        {
            "source_transaction_id": "TXN-INVALID000001",
            "account_id": acct_ids[0],
            "customer_id": acct_to_cust[acct_ids[0]],
            "transaction_date": "2024-04-01T10:00:00",
            "amount": "",           # empty → NULL after cast
            "currency": "USD",
            "transaction_type": "PURCHASE",
            "status": "COMPLETED",
            "description": "Invalid record — missing amount",
            "reference_transaction_id": "",
        }
    )
    # Invalid 2: unrecognised currency
    transactions.append(
        {
            "source_transaction_id": "TXN-INVALID000002",
            "account_id": acct_ids[1],
            "customer_id": acct_to_cust[acct_ids[1]],
            "transaction_date": "2024-04-02T11:00:00",
            "amount": "200.00",
            "currency": "XXX",      # not a supported currency
            "transaction_type": "DEPOSIT",
            "status": "COMPLETED",
            "description": "Invalid record — unknown currency XXX",
            "reference_transaction_id": "",
        }
    )

    return transactions


def save_to_csv(data: list[dict], path: Path, fieldnames: list[str]) -> None:
    """Write a list of dicts to a CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    logger.info("Wrote %d rows to %s", len(data), path)


def generate_all(output_dir: Path, seed: int = cfg.DATA_SEED) -> dict[str, Path]:
    """
    Generate all synthetic data files and write them to *output_dir*.
    Returns a dict of {dataset_name: path}.
    """
    logger.info("Generating synthetic data (seed=%d) …", seed)
    customers = generate_customers(seed)
    accounts = generate_accounts(customers, seed)
    transactions = generate_transactions(accounts, seed)

    paths: dict[str, Path] = {}

    paths["customers"] = output_dir / "customers.csv"
    save_to_csv(
        customers,
        paths["customers"],
        ["customer_id", "customer_name", "email", "phone", "country",
         "customer_segment", "risk_rating", "onboarded_date"],
    )

    paths["accounts"] = output_dir / "accounts.csv"
    save_to_csv(
        accounts,
        paths["accounts"],
        ["account_id", "customer_id", "account_type", "currency",
         "opened_date", "credit_limit"],
    )

    paths["transactions"] = output_dir / "transactions.csv"
    save_to_csv(
        transactions,
        paths["transactions"],
        ["source_transaction_id", "account_id", "customer_id",
         "transaction_date", "amount", "currency", "transaction_type",
         "status", "description", "reference_transaction_id"],
    )

    logger.info(
        "Generated: %d customers, %d accounts, %d transaction rows "
        "(includes duplicates and invalid records)",
        len(customers), len(accounts), len(transactions),
    )
    return paths
