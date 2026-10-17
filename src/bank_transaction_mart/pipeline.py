"""
pipeline.py — End-to-end pipeline orchestrator.

Sequence:
  1. Generate synthetic data (if not already present)
  2. Initialize database schema
  3. Ingest raw data
  4. Validate and quarantine
  5. Load dimension and fact tables
  6. Run data quality checks
  7. Detect anomalies
  8. Generate AI explanations
  9. Print execution summary
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import duckdb

from .config import cfg
from .data_generator import generate_all
from .database import execute_sql_file, get_connection, row_count
from .ingestion import ingest_accounts, ingest_customers, ingest_transactions
from .validation import validate_records, write_quarantine
from .anomaly_detection import detect_anomalies
from .ai.explainer import AnomalyExplanation
from .ai.provider_factory import build_explainer

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # src/btm → src → project root
_SQL_DIR = _PROJECT_ROOT / "sql"
_DATA_DIR = _PROJECT_ROOT / "data" / "generated"


def _setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        level=level,
        stream=sys.stdout,
    )


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Execute all schema-creation SQL scripts in order."""
    scripts = [
        "01_create_raw_tables.sql",
        "02_create_dimensions.sql",
        "03_create_fact_tables.sql",
    ]
    for script in scripts:
        logger.info("Executing schema script: %s", script)
        execute_sql_file(conn, _SQL_DIR / script)


def load_date_dimension(conn: duckdb.DuckDBPyConnection) -> int:
    """
    Populate dim_date for years 2020–2028.
    Uses DuckDB's generate_series for efficiency.
    Idempotent — INSERT OR IGNORE.
    """
    conn.execute("""
        INSERT OR IGNORE INTO dim_date
        SELECT
            CAST(strftime(d, '%Y%m%d') AS INTEGER)         AS date_key,
            d::DATE                                          AS full_date,
            YEAR(d)                                          AS year,
            QUARTER(d)                                       AS quarter,
            MONTH(d)                                         AS month,
            strftime(d, '%B')                                AS month_name,
            WEEKOFYEAR(d)                                    AS week_of_year,
            DAY(d)                                           AS day_of_month,
            ISODOW(d)                                        AS day_of_week,
            strftime(d, '%A')                                AS day_name,
            ISODOW(d) IN (6, 7)                              AS is_weekend,
            DAY(d) = 1                                       AS is_month_start,
            d = LAST_DAY(d)                                  AS is_month_end
        FROM (
            SELECT unnest(generate_series(
                '2020-01-01'::TIMESTAMP,
                '2028-12-31'::TIMESTAMP,
                INTERVAL 1 DAY
            )) AS d
        ) dates
    """)
    count = row_count(conn, "dim_date")
    logger.info("dim_date populated: %d rows", count)
    return count


def persist_explanations(
    conn: duckdb.DuckDBPyConnection,
    explanations: list[AnomalyExplanation],
    evidences: list[Any],
) -> None:
    """Write AI explanations to anomaly_explanations table."""
    ev_map = {e.source_transaction_id: e for e in evidences}

    rows = []
    for exp in explanations:
        ev = ev_map.get(exp.source_transaction_id)
        if ev is None:
            continue
        rows.append((
            exp.source_transaction_id,
            ev.customer_key,
            ev.account_key,
            ev.transaction_timestamp,
            ev.amount,
            ev.currency,
            ev.customer_median_30d,
            ev.threshold_multiplier,
            ev.deviation_ratio,
            ev.detection_rule_version,
            exp.explanation_status,
            exp.explanation_provider,
            exp.summary,
            exp.supporting_evidence,
            exp.possible_explanations,
            exp.limitations,
            exp.raw_ai_response[:4000] if exp.raw_ai_response else "",
        ))

    if rows:
        conn.executemany(
            """
            INSERT OR REPLACE INTO anomaly_explanations (
                source_transaction_id, customer_key, account_key,
                transaction_timestamp, amount, currency,
                customer_median_30d, threshold_multiplier, deviation_ratio,
                detection_rule_version, explanation_status, explanation_provider,
                summary, supporting_evidence, possible_explanations, limitations,
                raw_ai_response
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
    logger.info("Persisted %d explanations", len(rows))


def run_dq_checks(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """
    Run all data quality checks from 05_data_quality_checks.sql.
    Returns dict of {check_name: issue_count}.
    """
    sql = (_SQL_DIR / "05_data_quality_checks.sql").read_text(encoding="utf-8")
    results: dict[str, int] = {}
    for stmt in sql.split(";"):
        lines = [line for line in stmt.splitlines() if not line.strip().startswith("--")]
        clean_stmt = "\n".join(lines).strip()
        if not clean_stmt:
            continue
        try:
            row = conn.execute(clean_stmt).fetchone()
            if row and len(row) == 2:
                results[str(row[0])] = int(row[1])
        except duckdb.Error:
            pass  # skip non-select statements
    return results


def run_pipeline(
    db_path: str | Path | None = None,
    data_dir: Path | None = None,
    ai_provider: str | None = None,
    regenerate_data: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    """
    Execute the full pipeline end-to-end.

    Parameters
    ----------
    db_path       : Override database path (useful for tests).
    data_dir      : Override data directory (useful for tests).
    ai_provider   : Override AI provider (useful for tests).
    regenerate_data: Force re-generation of synthetic data.
    verbose       : Enable DEBUG logging.

    Returns
    -------
    A summary dictionary with pipeline statistics.
    """
    _setup_logging(logging.DEBUG if verbose else logging.INFO)
    logger.info("=" * 60)
    logger.info("Bank Transaction Mart — Pipeline Start")
    logger.info("=" * 60)

    effective_data_dir = Path(data_dir) if data_dir else _DATA_DIR
    summary: dict[str, Any] = {}

    # ── Step 1: Generate synthetic data ────────────────────────────────────
    customers_csv = effective_data_dir / "customers.csv"
    if regenerate_data or not customers_csv.exists():
        paths = generate_all(effective_data_dir, seed=cfg.DATA_SEED)
    else:
        paths = {
            "customers": effective_data_dir / "customers.csv",
            "accounts":  effective_data_dir / "accounts.csv",
            "transactions": effective_data_dir / "transactions.csv",
        }
        logger.info("Using existing data files in %s", effective_data_dir)

    # ── Step 2: Connect and initialise schema ───────────────────────────────
    conn = get_connection(db_path)
    init_schema(conn)
    load_date_dimension(conn)

    # ── Step 3: Ingest raw data ─────────────────────────────────────────────
    cust_count = ingest_customers(conn, paths["customers"])
    acct_count = ingest_accounts(conn, paths["accounts"])
    ingest_stats = ingest_transactions(conn, paths["transactions"])
    summary["source_rows"] = ingest_stats.rows_read

    # ── Step 4: Validate and quarantine ────────────────────────────────────
    # Read raw records for Python-side validation
    import csv as _csv
    raw_records: list[dict] = []
    with open(paths["transactions"], newline="", encoding="utf-8") as f:
        raw_records = list(_csv.DictReader(f))

    val_result = validate_records(raw_records, source_file=paths["transactions"].name)
    quarantine_count = write_quarantine(conn, val_result.invalid, paths["transactions"].name)
    summary["duplicates_detected"] = val_result.duplicate_count
    summary["quarantined"] = quarantine_count
    summary["invalid_records"] = val_result.invalid_count

    # Load customers dimension (Type 1 upsert on customer_key)
    conn.execute("""
        INSERT INTO dim_customer
            (customer_key, customer_id, full_name, email, phone,
             country, customer_segment, risk_rating, onboarded_date, is_active, updated_at)
        SELECT
            ABS(hash(customer_id)) % 2147483647,
            customer_id, customer_name, email, phone,
            country, customer_segment, risk_rating,
            CAST(onboarded_date AS DATE), TRUE, CURRENT_TIMESTAMP
        FROM stg_customers
        ON CONFLICT (customer_key) DO UPDATE SET
            customer_id      = excluded.customer_id,
            full_name        = excluded.full_name,
            email            = excluded.email,
            phone            = excluded.phone,
            country          = excluded.country,
            customer_segment = excluded.customer_segment,
            risk_rating      = excluded.risk_rating,
            onboarded_date   = excluded.onboarded_date,
            updated_at       = excluded.updated_at
    """)

    # Load accounts dimension (Type 1 upsert on account_key)
    conn.execute("""
        INSERT INTO dim_account
            (account_key, account_id, customer_key, account_type,
             currency, opened_date, is_active, credit_limit, updated_at)
        SELECT
            ABS(hash(a.account_id)) % 2147483647,
            a.account_id,
            ABS(hash(a.customer_id)) % 2147483647,
            a.account_type, a.currency,
            CAST(a.opened_date AS DATE), TRUE,
            TRY_CAST(a.credit_limit AS DECIMAL(18,2)),
            CURRENT_TIMESTAMP
        FROM stg_accounts a
        ON CONFLICT (account_key) DO UPDATE SET
            account_id   = excluded.account_id,
            account_type = excluded.account_type,
            currency     = excluded.currency,
            credit_limit = excluded.credit_limit,
            updated_at   = excluded.updated_at
    """)

    # Deduplicated staging
    conn.execute("""
        CREATE OR REPLACE TABLE stg_transactions AS
        SELECT
            source_transaction_id,
            account_id,
            customer_id,
            CAST(transaction_date AS TIMESTAMP)     AS transaction_timestamp,
            CAST(amount AS DECIMAL(18,2))           AS amount,
            UPPER(TRIM(currency))                   AS currency,
            UPPER(TRIM(transaction_type))           AS transaction_type,
            UPPER(TRIM(status))                     AS status,
            description,
            reference_transaction_id,
            source_file,
            loaded_at
        FROM raw_transactions rt
        WHERE source_transaction_id NOT IN (
            SELECT DISTINCT source_transaction_id
            FROM raw_quarantine
            WHERE source_transaction_id IS NOT NULL
        )
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY source_transaction_id
            ORDER BY loaded_at ASC, raw_id ASC
        ) = 1
    """)

    # Load facts (idempotent)
    conn.execute("""
        INSERT OR IGNORE INTO fact_transactions (
            transaction_key, source_transaction_id,
            customer_key, account_key, transaction_type_key,
            date_key, transaction_timestamp,
            amount, currency, status, description,
            reference_transaction_id, is_anomaly, loaded_at
        )
        SELECT
            ABS(hash(st.source_transaction_id)) % 2147483647,
            st.source_transaction_id,
            ABS(hash(st.customer_id)) % 2147483647,
            ABS(hash(st.account_id)) % 2147483647,
            COALESCE(dtt.transaction_type_key, 10),
            CAST(strftime(st.transaction_timestamp, '%Y%m%d') AS INTEGER),
            st.transaction_timestamp,
            st.amount, st.currency, st.status, st.description,
            st.reference_transaction_id,
            FALSE, CURRENT_TIMESTAMP
        FROM stg_transactions st
        LEFT JOIN dim_transaction_type dtt ON dtt.type_code = st.transaction_type
        WHERE EXISTS (SELECT 1 FROM dim_customer dc WHERE dc.customer_id = st.customer_id)
          AND EXISTS (SELECT 1 FROM dim_account  da WHERE da.account_id  = st.account_id)
    """)

    fact_rows = row_count(conn, "fact_transactions")
    summary["fact_rows_loaded"] = fact_rows
    summary["customers_loaded"] = row_count(conn, "dim_customer")
    summary["accounts_loaded"] = row_count(conn, "dim_account")

    # ── Step 6: Data quality checks ─────────────────────────────────────────
    dq_results = run_dq_checks(conn)
    failed_checks = {k: v for k, v in dq_results.items() if v > 0}
    summary["dq_checks_run"] = len(dq_results)
    summary["dq_checks_failed"] = len(failed_checks)
    if failed_checks:
        logger.warning("DQ failures: %s", failed_checks)
    else:
        logger.info("All %d DQ checks passed", len(dq_results))

    # ── Step 7: Anomaly detection ───────────────────────────────────────────
    anomaly_evidences = detect_anomalies(conn)
    summary["anomalies_detected"] = len(anomaly_evidences)

    # ── Step 8: AI explanations ─────────────────────────────────────────────
    explainer = build_explainer(ai_provider)
    explanations: list[AnomalyExplanation] = []
    for ev in anomaly_evidences:
        exp = explainer.explain(ev)
        explanations.append(exp)

    persist_explanations(conn, explanations, anomaly_evidences)

    ai_success = sum(1 for e in explanations if e.explanation_status == "AI_SUCCESS")
    ai_fallback = sum(1 for e in explanations if e.explanation_status == "FALLBACK")
    ai_failed   = sum(1 for e in explanations if e.explanation_status == "AI_FAILED")
    summary["ai_explanations_success"] = ai_success
    summary["ai_explanations_fallback"] = ai_fallback
    summary["ai_explanations_failed"] = ai_failed

    conn.close()

    # ── Step 9: Print summary ───────────────────────────────────────────────
    _print_summary(summary)
    return summary


def _print_summary(s: dict[str, Any]) -> None:
    logger.info("=" * 60)
    logger.info("PIPELINE EXECUTION SUMMARY")
    logger.info("=" * 60)
    logger.info("Source rows read        : %s", s.get("source_rows", "?"))
    logger.info("Invalid records         : %s", s.get("invalid_records", "?"))
    logger.info("Duplicate IDs detected  : %s", s.get("duplicates_detected", "?"))
    logger.info("Quarantine rows written : %s", s.get("quarantined", "?"))
    logger.info("Customers loaded        : %s", s.get("customers_loaded", "?"))
    logger.info("Accounts loaded         : %s", s.get("accounts_loaded", "?"))
    logger.info("Fact rows loaded        : %s", s.get("fact_rows_loaded", "?"))
    logger.info("DQ checks run / failed  : %s / %s",
                s.get("dq_checks_run", "?"), s.get("dq_checks_failed", "?"))
    logger.info("Anomalies detected      : %s", s.get("anomalies_detected", "?"))
    logger.info("AI explanations success : %s", s.get("ai_explanations_success", "?"))
    logger.info("AI explanations fallback: %s", s.get("ai_explanations_fallback", "?"))
    logger.info("AI explanations failed  : %s", s.get("ai_explanations_failed", "?"))
    logger.info("=" * 60)
