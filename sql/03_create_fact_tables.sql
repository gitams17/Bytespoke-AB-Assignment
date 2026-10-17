-- =============================================================================
-- Script  : 03_create_fact_tables.sql
-- Purpose : Create the central fact table and the anomaly explanations table.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- fact_transactions — grain: one row per unique source transaction event
--
-- Design decisions:
--   • Grain is the source_transaction_id. One event from the source system
--     becomes exactly one fact row.
--   • Reversals are stored as separate fact rows (type='REVERSAL') linked via
--     reference_transaction_id back to the original fact. They are NOT deleted.
--   • Failed/pending transactions ARE stored (status column carries the truth).
--     Analytics filter on status as appropriate.
--   • Duplicates in the source are deduplicated on source_transaction_id during
--     staging and only one fact row is created.
--   • Currency is stored per row; aggregations must filter to a single currency
--     to avoid mixing values.
--   • date_key is an integer YYYYMMDD foreign key to dim_date.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_transactions (
    transaction_key         INTEGER PRIMARY KEY,          -- surrogate key (auto)
    source_transaction_id   VARCHAR NOT NULL UNIQUE,      -- natural / idempotency key
    customer_key            INTEGER NOT NULL,             -- logical FK to dim_customer; integrity checked via DQ-03
    account_key             INTEGER NOT NULL,             -- logical FK to dim_account;  integrity checked via DQ-04
    transaction_type_key    INTEGER NOT NULL,             -- logical FK to dim_transaction_type
    date_key                INTEGER NOT NULL,             -- logical FK to dim_date; integrity checked via DQ-05
    transaction_timestamp   TIMESTAMP NOT NULL,
    amount                  DECIMAL(18, 2) NOT NULL,
    currency                VARCHAR(3) NOT NULL,
    status                  VARCHAR NOT NULL,             -- COMPLETED, PENDING, FAILED, REVERSED
    description             VARCHAR,
    reference_transaction_id VARCHAR,                     -- FK to source_transaction_id of original
    is_anomaly              BOOLEAN DEFAULT FALSE,
    loaded_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- anomaly_explanations — persists AI or fallback explanations
-- Separate from fact_transactions to keep facts clean and atomic.
-- ---------------------------------------------------------------------------
-- DuckDB uses CREATE SEQUENCE + DEFAULT nextval() for auto-increment primary keys
CREATE SEQUENCE IF NOT EXISTS seq_explanation_id START 1;

CREATE TABLE IF NOT EXISTS anomaly_explanations (
    explanation_id          INTEGER DEFAULT nextval('seq_explanation_id') PRIMARY KEY,
    source_transaction_id   VARCHAR NOT NULL,             -- FK to fact_transactions
    customer_key            INTEGER NOT NULL,
    account_key             INTEGER NOT NULL,
    transaction_timestamp   TIMESTAMP NOT NULL,
    amount                  DECIMAL(18, 2) NOT NULL,
    currency                VARCHAR(3) NOT NULL,
    customer_median_30d     DECIMAL(18, 2),               -- baseline statistic
    threshold_multiplier    DECIMAL(5, 2),
    deviation_ratio         DECIMAL(8, 2),                -- amount / median
    detection_rule_version  VARCHAR NOT NULL,
    -- AI explanation fields
    explanation_status      VARCHAR NOT NULL,             -- AI_SUCCESS, AI_FAILED, FALLBACK
    explanation_provider    VARCHAR,                      -- mock, gemini, openai
    summary                 VARCHAR,
    supporting_evidence     VARCHAR,
    possible_explanations   VARCHAR,
    limitations             VARCHAR,
    raw_ai_response         VARCHAR,                      -- full JSON for audit
    explained_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
