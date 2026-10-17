-- =============================================================================
-- Script  : 05_data_quality_checks.sql
-- Purpose : Post-load validation queries used by the test suite and pipeline.
--           Each check returns a result_name and either passes (issue_count=0)
--           or fails (issue_count > 0).
-- =============================================================================

-- DQ-01: Fact surrogate key uniqueness
SELECT
    'DQ-01 fact_key_unique'        AS result_name,
    COUNT(*) - COUNT(DISTINCT transaction_key) AS issue_count
FROM fact_transactions;

-- DQ-02: Source transaction ID uniqueness in facts
SELECT
    'DQ-02 source_id_unique'       AS result_name,
    COUNT(*) - COUNT(DISTINCT source_transaction_id) AS issue_count
FROM fact_transactions;

-- DQ-03: Referential integrity — customer key
SELECT
    'DQ-03 fk_customer'            AS result_name,
    COUNT(*)                       AS issue_count
FROM fact_transactions ft
LEFT JOIN dim_customer dc ON dc.customer_key = ft.customer_key
WHERE dc.customer_key IS NULL;

-- DQ-04: Referential integrity — account key
SELECT
    'DQ-04 fk_account'             AS result_name,
    COUNT(*)                       AS issue_count
FROM fact_transactions ft
LEFT JOIN dim_account da ON da.account_key = ft.account_key
WHERE da.account_key IS NULL;

-- DQ-05: Referential integrity — date key
SELECT
    'DQ-05 fk_date'                AS result_name,
    COUNT(*)                       AS issue_count
FROM fact_transactions ft
LEFT JOIN dim_date dd ON dd.date_key = ft.date_key
WHERE dd.date_key IS NULL;

-- DQ-06: Valid status values
SELECT
    'DQ-06 valid_status'           AS result_name,
    COUNT(*)                       AS issue_count
FROM fact_transactions
WHERE status NOT IN ('COMPLETED', 'PENDING', 'FAILED', 'REVERSED');

-- DQ-07: Non-negative amounts
SELECT
    'DQ-07 non_negative_amount'    AS result_name,
    COUNT(*)                       AS issue_count
FROM fact_transactions
WHERE amount < 0;

-- DQ-08: No NULL amounts
SELECT
    'DQ-08 no_null_amount'         AS result_name,
    COUNT(*)                       AS issue_count
FROM fact_transactions
WHERE amount IS NULL;

-- DQ-09: Quarantine table has documented reasons
SELECT
    'DQ-09 quarantine_reasons'     AS result_name,
    COUNT(*)                       AS issue_count
FROM raw_quarantine
WHERE quarantine_reason IS NULL OR quarantine_rule IS NULL;

-- DQ-10: Customer dimension surrogate key uniqueness
SELECT
    'DQ-10 dim_customer_key_unique' AS result_name,
    COUNT(*) - COUNT(DISTINCT customer_key) AS issue_count
FROM dim_customer;

-- DQ-11: Account dimension surrogate key uniqueness
SELECT
    'DQ-11 dim_account_key_unique' AS result_name,
    COUNT(*) - COUNT(DISTINCT account_key) AS issue_count
FROM dim_account;

-- DQ-12: Source-to-target reconciliation (staged vs loaded)
SELECT
    'DQ-12 stg_vs_fact_count'      AS result_name,
    CASE
        WHEN (SELECT COUNT(*) FROM stg_transactions)
           - (SELECT COUNT(*) FROM fact_transactions) < 0
        THEN ABS((SELECT COUNT(*) FROM stg_transactions)
                - (SELECT COUNT(*) FROM fact_transactions))
        ELSE 0
    END                             AS issue_count;
