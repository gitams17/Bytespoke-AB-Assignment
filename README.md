# Bank Transaction Mart

An end-to-end analytical data mart and AI-assisted anomaly explanation pipeline for banking transaction data, built with Python, DuckDB, and a dimensional star schema.

---

## Overview

The **Bank Transaction Mart** processes raw, synthetic transactional banking data through a multi-stage data engineering and analytics pipeline:
1. **Synthetic Data Generation**: Deterministic, reproducible data generation with seeded edge cases (duplicates, null/invalid values, reversals, and high-value anomalies).
2. **Ingestion & Quarantine**: Ingests raw data with schema validation and quarantines invalid records using granular rule codes (`VAL-001` through `VAL-010`) rather than silently dropping data.
3. **Dimensional Modeling**: Transforms and deduplicates staged data into a star schema (`fact_transactions`, `dim_customer`, `dim_account`, `dim_date`, `dim_transaction_type`).
4. **Data Quality Checks**: Automatically executes 12 SQL-based data quality checks (key uniqueness, referential integrity, domain validation, and reconciliation).
5. **Anomaly Detection**: Evaluates completed transactions against a rolling 30-day historical customer baseline (amount > 3× median) with zero forward data leakage.
6. **Pluggable AI Explanation Layer**: Generates structured explanations for detected anomalies via modular adapters (`Mock` for offline tests, `Gemini` for live LLM inference) with a deterministic fallback mechanism.
7. **Business Analytics**: Built-in reporting for customer metrics, account activity, daily volumes, status distributions, and anomaly summaries.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       RAW LAYER                             │
│  ingestion.py → raw_transactions (unaltered CSV data)       │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                    VALIDATION LAYER                         │
│  validation.py → VAL-001 to VAL-010                         │
│  Invalid records → raw_quarantine (rule code + error)       │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                     STAGING LAYER                           │
│  stg_transactions: typed, deduplicated via QUALIFY ROW_NUM  │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                STAR SCHEMA DATA MART                        │
│  dim_customer ──┐                                           │
│  dim_account  ──┼──> fact_transactions <── dim_date         │
│  dim_txn_type ──┘                                           │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│              ANOMALY DETECTION & AI EXPLANATION             │
│  anomaly_detection.py → 3× 30-day median baseline           │
│  explainer.py → AIExplainer (Gemini / Mock / Fallback)      │
│  anomaly_explanations table (audit trail)                   │
└─────────────────────────────────────────────────────────────┘
```

Detailed architectural diagrams, decisions, and demo walkthrough script are documented in [`docs/architecture.md`](docs/architecture.md), [`docs/data_model.md`](docs/data_model.md), [`docs/design_decisions.md`](docs/design_decisions.md), and [`docs/demo_script.md`](docs/demo_script.md).

---

## Project Structure

```
bank-transaction-mart/
├── .env.example              # Template for environment configuration
├── .gitignore                # Git ignore patterns (ignores DB files, env, output)
├── README.md                 # Project documentation
├── requirements.txt          # Python dependencies
├── data/
│   └── README.md             # Data layer description
├── docs/
│   ├── architecture.md       # Pipeline architecture & technology rationale
│   ├── data_model.md         # Star schema definitions & entity relationships
│   ├── design_decisions.md   # Design choices and trade-offs
│   └── demo_script.md        # 5–8 min demo video script & recording checklist
├── scripts/
│   └── run_pipeline.py       # Primary CLI pipeline entry point
├── sql/
│   ├── 01_create_raw_tables.sql       # Raw layer and quarantine tables
│   ├── 02_create_dimensions.sql       # Dimension tables (Type 1 SCD, calendar)
│   ├── 03_create_fact_tables.sql      # Central fact table & explanation schema
│   ├── 04_transform_data.sql          # Staging, deduplication, and loading
│   ├── 05_data_quality_checks.sql     # 12 automated DQ verification queries
│   └── 06_analytics.sql               # Analytical reporting queries
├── src/
│   └── bank_transaction_mart/
│       ├── __init__.py
│       ├── config.py                  # Environment and application configuration
│       ├── database.py                # DuckDB connection factory & SQL execution
│       ├── data_generator.py          # Synthetic banking dataset generator
│       ├── ingestion.py               # Raw CSV ingestion
│       ├── validation.py              # Data quality rules & quarantine logic
│       ├── pipeline.py                # Pipeline orchestration
│       ├── anomaly_detection.py       # Statistical anomaly detection
│       ├── analytics.py               # Analytical queries & reporting
│       └── ai/
│           ├── __init__.py
│           ├── explainer.py           # Abstract explainer interface & dataclass
│           ├── provider_factory.py    # Adapter factory
│           └── adapters/
│               ├── mock_adapter.py    # Deterministic mock adapter (offline/test)
│               └── gemini_adapter.py  # Google Gemini LLM adapter
└── tests/
    ├── __init__.py
    ├── conftest.py                    # Pytest fixtures (in-memory DuckDB)
    ├── test_pipeline.py               # End-to-end integration tests
    ├── test_data_quality.py           # Validation & data quality tests
    └── test_anomaly_and_ai.py         # Anomaly detection & AI fallback tests
```

---

## Getting Started

### 1. Prerequisites
- Python 3.10+ (tested with Python 3.13)
- PowerShell, Bash, or terminal of choice

### 2. Environment Setup

Clone the repository and create a virtual environment:

```bash
# Clone the repository
git clone <your-repo-url>
cd bank-transaction-mart

# Create and activate virtual environment
python -m venv .venv

# Windows PowerShell:
.venv\Scripts\Activate.ps1

# Linux / macOS:
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### 3. Configuration

Copy `.env.example` to `.env`:

```bash
# Windows PowerShell:
Copy-Item .env.example .env

# Linux / macOS:
cp .env.example .env
```

Default configuration uses offline mock mode (`AI_PROVIDER=mock`). To use Google Gemini for live AI explanations, update `.env`:
```ini
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
```

---

## Running the Pipeline

Execute the end-to-end pipeline:

```bash
python scripts/run_pipeline.py
```

### Additional Options

- **View Analytics Summary**:
  ```bash
  python scripts/run_pipeline.py --analytics
  ```
- **View Anomaly Report**:
  ```bash
  python scripts/run_pipeline.py --anomalies
  ```
- **Force Data Regeneration**:
  ```bash
  python scripts/run_pipeline.py --regenerate
  ```
- **Verbose Debug Logging**:
  ```bash
  python scripts/run_pipeline.py --verbose
  ```
- **Specify AI Provider at Runtime**:
  ```bash
  python scripts/run_pipeline.py --provider gemini
  ```

---

## Running Tests

The test suite runs 29 automated tests against an isolated, in-memory DuckDB database:

```bash
pytest
```

To run with coverage reporting:

```bash
pytest --cov=bank_transaction_mart tests/
```

---

## License

This project is licensed under the MIT License.
