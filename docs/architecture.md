# Architecture — Bank Transaction Mart

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA SOURCES                                │
│  data_generator.py (Faker + fixed seed)                        │
│  customers.csv │ accounts.csv │ transactions.csv               │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                      RAW LAYER                                  │
│  ingestion.py → raw_transactions (text, no transforms)         │
│  Schema validation: required columns checked before insert     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                   VALIDATION LAYER                              │
│  validation.py → 10 named rules (VAL-001 to VAL-010)          │
│  Valid records → continue                                      │
│  Invalid records → raw_quarantine (with rule code + reason)    │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                   STAGING LAYER                                 │
│  stg_transactions: typed, deduplicated via QUALIFY ROW_NUM=1   │
│  stg_customers, stg_accounts: temp tables from CSV             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│               DIMENSIONAL MODEL (Star Schema)                   │
│  dim_customer ──┐                                              │
│  dim_account  ──┤→ fact_transactions ←── dim_date             │
│  dim_txn_type ──┘                                              │
│                                                                 │
│  Surrogate keys: ABS(hash(natural_key)) % 2^31                 │
│  Idempotent: INSERT OR IGNORE on source_transaction_id         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                DATA QUALITY CHECKS                              │
│  12 SQL checks: key uniqueness, FK integrity, valid statuses   │
│  Source-to-target reconciliation view                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                  ANOMALY DETECTION                              │
│  Rule: amount > 3× 30-day historical median (same currency)    │
│  Minimum history: 3 prior COMPLETED transactions               │
│  No data leakage: only history before candidate timestamp      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                  AI EXPLANATION LAYER                           │
│  AIExplainer (abstract) → MockExplainer / GeminiExplainer      │
│  Prompt: structured evidence → JSON response validated         │
│  Failures: fallback deterministic explanation always returned  │
│  Persisted: anomaly_explanations table                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                      ANALYTICS                                  │
│  analytics.py: customer, account, daily, type, anomaly views   │
│  SQL scripts in sql/06_analytics.sql                           │
└─────────────────────────────────────────────────────────────────┘
```

## Configuration Boundary

```
.env (never committed)
  ├── AI_PROVIDER    → provider_factory.py → AIExplainer adapter
  ├── DB_PATH        → config.py → database.py
  ├── ANOMALY_THRESHOLD → anomaly_detection.py
  └── DATA_SEED      → data_generator.py
```

## Test Isolation

```
pytest
  ├── conftest.py
  │    ├── mem_conn   → :memory: DuckDB, schema only
  │    └── full_pipeline_conn → tmp_path DuckDB, full pipeline
  ├── test_pipeline.py        (integration)
  ├── test_data_quality.py    (unit + integration)
  └── test_anomaly_and_ai.py  (unit)
```

## Technology Rationale

| Technology | Why chosen |
|-----------|------------|
| DuckDB | Embedded, columnar, full SQL, QUALIFY/window functions, zero config |
| Python 3.13 | Current stable; matches available system interpreter |
| Faker | Realistic synthetic data, deterministic with seed |
| pytest | Standard; fixture model ideal for DB isolation |
| tabulate | Pretty-print query results; optional, graceful fallback |
| python-dotenv | Secrets from .env without hardcoding |
