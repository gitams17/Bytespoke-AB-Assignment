-- =============================================================================
-- Script  : 04_transform_data.sql
-- Purpose : Stage, clean, deduplicate, and load dimensions and facts.
--           Executed by pipeline.py via Python parameter binding.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- STEP 1 — Create staging table from valid raw records
-- Filters out records already quarantined; casts types.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE stg_transactions AS
SELECT
    source_transaction_id,
    account_id,
    customer_id,
    CAST(transaction_date AS TIMESTAMP)  AS transaction_timestamp,
    CAST(amount           AS DECIMAL(18,2)) AS amount,
    UPPER(TRIM(currency))                AS currency,
    UPPER(TRIM(transaction_type))        AS transaction_type,
    UPPER(TRIM(status))                  AS status,
    description,
    reference_transaction_id,
    source_file,
    loaded_at
FROM raw_transactions rt
WHERE source_transaction_id NOT IN (
    SELECT source_transaction_id
    FROM raw_quarantine
    WHERE source_transaction_id IS NOT NULL
)
-- Deduplication: keep the first loaded copy of each source_transaction_id
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY source_transaction_id
    ORDER BY loaded_at ASC, raw_id ASC
) = 1;

-- ---------------------------------------------------------------------------
-- STEP 2 — Load dim_customer (Type 1 upsert)
-- ---------------------------------------------------------------------------
INSERT OR REPLACE INTO dim_customer (
    customer_key, customer_id, full_name, email, phone,
    country, customer_segment, risk_rating, onboarded_date,
    is_active, updated_at
)
SELECT
    -- Deterministic surrogate key from customer_id
    ABS(hash(customer_id)) % 2147483647 AS customer_key,
    customer_id,
    customer_name       AS full_name,
    email,
    phone,
    country,
    customer_segment,
    risk_rating,
    CAST(onboarded_date AS DATE),
    TRUE                AS is_active,
    CURRENT_TIMESTAMP   AS updated_at
FROM stg_customers;

-- ---------------------------------------------------------------------------
-- STEP 3 — Load dim_account (Type 1 upsert)
-- ---------------------------------------------------------------------------
INSERT OR REPLACE INTO dim_account (
    account_key, account_id, customer_key, account_type,
    currency, opened_date, is_active, credit_limit, updated_at
)
SELECT
    ABS(hash(a.account_id)) % 2147483647 AS account_key,
    a.account_id,
    ABS(hash(a.customer_id)) % 2147483647 AS customer_key,
    a.account_type,
    a.currency,
    CAST(a.opened_date AS DATE),
    TRUE                AS is_active,
    a.credit_limit,
    CURRENT_TIMESTAMP   AS updated_at
FROM stg_accounts a;

-- ---------------------------------------------------------------------------
-- STEP 4 — Load fact_transactions
-- Uses INSERT OR IGNORE to enforce idempotency on source_transaction_id.
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO fact_transactions (
    transaction_key,
    source_transaction_id,
    customer_key,
    account_key,
    transaction_type_key,
    date_key,
    transaction_timestamp,
    amount,
    currency,
    status,
    description,
    reference_transaction_id,
    is_anomaly,
    loaded_at
)
SELECT
    ABS(hash(st.source_transaction_id)) % 2147483647  AS transaction_key,
    st.source_transaction_id,
    dc.customer_key,
    da.account_key,
    COALESCE(dtt.transaction_type_key, 10)             AS transaction_type_key,
    CAST(strftime(st.transaction_timestamp, '%Y%m%d') AS INTEGER) AS date_key,
    st.transaction_timestamp,
    st.amount,
    st.currency,
    st.status,
    st.description,
    st.reference_transaction_id,
    FALSE                                              AS is_anomaly,
    CURRENT_TIMESTAMP
FROM stg_transactions st
JOIN dim_customer dc ON dc.customer_id = st.customer_id
JOIN dim_account  da ON da.account_id  = st.account_id
LEFT JOIN dim_transaction_type dtt ON dtt.type_code = st.transaction_type;

-- ---------------------------------------------------------------------------
-- STEP 5 — Source-to-target reconciliation view
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_reconciliation AS
SELECT
    'raw_transactions'  AS layer,
    COUNT(*)            AS row_count
FROM raw_transactions
UNION ALL
SELECT 'stg_transactions',  COUNT(*) FROM stg_transactions
UNION ALL
SELECT 'fact_transactions',  COUNT(*) FROM fact_transactions
UNION ALL
SELECT 'raw_quarantine',     COUNT(*) FROM raw_quarantine;
