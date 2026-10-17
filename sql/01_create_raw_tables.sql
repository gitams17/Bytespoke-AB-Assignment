-- =============================================================================
-- Script  : 01_create_raw_tables.sql
-- Purpose : Create the raw ingestion layer and quarantine table.
--           Raw tables store data exactly as received — no transformations.
-- Layer   : Raw
-- =============================================================================

-- Raw transactions - one row per CSV source record (no deduplication yet)
CREATE TABLE IF NOT EXISTS raw_transactions (
    raw_id              INTEGER,
    source_transaction_id VARCHAR NOT NULL,
    account_id          VARCHAR NOT NULL,
    customer_id         VARCHAR NOT NULL,
    transaction_date    VARCHAR,
    amount              VARCHAR,
    currency            VARCHAR,
    transaction_type    VARCHAR,
    status              VARCHAR,
    description         VARCHAR,
    reference_transaction_id VARCHAR,
    loaded_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_file         VARCHAR
);

-- Raw quarantine - records that failed validation rules
CREATE TABLE IF NOT EXISTS raw_quarantine (
    quarantine_id       INTEGER,
    source_transaction_id VARCHAR,
    raw_record          VARCHAR,
    quarantine_reason   VARCHAR NOT NULL,
    quarantine_rule     VARCHAR NOT NULL,
    quarantined_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_file         VARCHAR
);
