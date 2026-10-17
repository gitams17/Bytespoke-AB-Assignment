"""
scripts/run_pipeline.py — Primary entry point for running the pipeline.

Usage:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --regenerate
    python scripts/run_pipeline.py --analytics
    python scripts/run_pipeline.py --anomalies
    python scripts/run_pipeline.py --verbose
    python scripts/run_pipeline.py --provider gemini
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make src importable when running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bank_transaction_mart.pipeline import run_pipeline
from bank_transaction_mart.config import cfg
from bank_transaction_mart.database import get_connection
from bank_transaction_mart.analytics import run_all, anomaly_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bank Transaction Mart — Pipeline Runner"
    )
    parser.add_argument(
        "--regenerate", action="store_true",
        help="Force regeneration of synthetic data files"
    )
    parser.add_argument(
        "--analytics", action="store_true",
        help="Print all analytics queries after pipeline run"
    )
    parser.add_argument(
        "--anomalies", action="store_true",
        help="Print anomaly report after pipeline run"
    )
    parser.add_argument(
        "--provider", default=None,
        choices=["mock", "gemini", "openai"],
        help="Override AI_PROVIDER from .env"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable DEBUG logging"
    )
    args = parser.parse_args()

    summary = run_pipeline(
        regenerate_data=args.regenerate,
        ai_provider=args.provider,
        verbose=args.verbose,
    )

    if args.analytics or args.anomalies:
        conn = get_connection(cfg.db_path())
        if args.analytics:
            run_all(conn)
        elif args.anomalies:
            anomaly_report(conn)
        conn.close()


if __name__ == "__main__":
    main()
