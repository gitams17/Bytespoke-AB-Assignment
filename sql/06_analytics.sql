-- =============================================================================
-- Script  : 06_analytics.sql
-- Purpose : Business analytics queries for the bank transaction mart.
--           All currency aggregations filter to a single currency (USD).
-- =============================================================================

-- ─── CUSTOMER ANALYTICS ────────────────────────────────────────────────────

-- AN-C01: Transaction count and completed value by customer
SELECT
    dc.customer_id,
    dc.full_name,
    dc.customer_segment,
    COUNT(ft.transaction_key)                        AS total_transactions,
    COUNT(CASE WHEN ft.status = 'COMPLETED' THEN 1 END) AS completed_count,
    SUM(CASE WHEN ft.status = 'COMPLETED'
             AND ft.currency = 'USD' THEN ft.amount ELSE 0 END) AS completed_value_usd,
    AVG(CASE WHEN ft.currency = 'USD' THEN ft.amount END) AS avg_amount_usd
FROM fact_transactions ft
JOIN dim_customer dc ON dc.customer_key = ft.customer_key
GROUP BY dc.customer_id, dc.full_name, dc.customer_segment
ORDER BY completed_value_usd DESC;

-- AN-C02: Most active customers (last 30 calendar days)
SELECT
    dc.customer_id,
    dc.full_name,
    COUNT(ft.transaction_key)                        AS txn_count_30d,
    SUM(CASE WHEN ft.currency = 'USD' THEN ft.amount ELSE 0 END) AS value_30d_usd
FROM fact_transactions ft
JOIN dim_customer dc ON dc.customer_key = ft.customer_key
JOIN dim_date     dd ON dd.date_key      = ft.date_key
WHERE dd.full_date >= CURRENT_DATE - INTERVAL 30 DAY
GROUP BY dc.customer_id, dc.full_name
ORDER BY txn_count_30d DESC
LIMIT 10;

-- ─── ACCOUNT ANALYTICS ─────────────────────────────────────────────────────

-- AN-A01: Transaction count and completed value by account
SELECT
    da.account_id,
    da.account_type,
    dc.customer_id,
    COUNT(ft.transaction_key)                        AS total_transactions,
    COUNT(CASE WHEN ft.status = 'COMPLETED' THEN 1 END) AS completed_count,
    SUM(CASE WHEN ft.status = 'COMPLETED'
             AND ft.currency = 'USD' THEN ft.amount ELSE 0 END) AS completed_value_usd,
    COUNT(CASE WHEN ft.status = 'FAILED'   THEN 1 END) AS failed_count,
    COUNT(CASE WHEN ft.status = 'PENDING'  THEN 1 END) AS pending_count
FROM fact_transactions ft
JOIN dim_account  da ON da.account_key  = ft.account_key
JOIN dim_customer dc ON dc.customer_key = da.customer_key
GROUP BY da.account_id, da.account_type, dc.customer_id
ORDER BY completed_value_usd DESC;

-- AN-A02: Daily account activity (last 7 days)
SELECT
    dd.full_date,
    da.account_id,
    COUNT(ft.transaction_key)                        AS txn_count,
    SUM(CASE WHEN ft.currency = 'USD' THEN ft.amount ELSE 0 END) AS daily_value_usd
FROM fact_transactions ft
JOIN dim_account da ON da.account_key = ft.account_key
JOIN dim_date    dd ON dd.date_key    = ft.date_key
WHERE dd.full_date >= CURRENT_DATE - INTERVAL 7 DAY
GROUP BY dd.full_date, da.account_id
ORDER BY dd.full_date DESC, txn_count DESC;

-- ─── TRANSACTION ANALYTICS ─────────────────────────────────────────────────

-- AN-T01: Daily transaction volume and value
SELECT
    dd.full_date,
    dd.day_name,
    COUNT(ft.transaction_key)                        AS txn_count,
    SUM(CASE WHEN ft.currency = 'USD' THEN ft.amount ELSE 0 END) AS total_value_usd,
    AVG(CASE WHEN ft.currency = 'USD' THEN ft.amount END) AS avg_value_usd
FROM fact_transactions ft
JOIN dim_date dd ON dd.date_key = ft.date_key
GROUP BY dd.full_date, dd.day_name
ORDER BY dd.full_date;

-- AN-T02: Transaction type distribution
SELECT
    dtt.type_code,
    dtt.type_label,
    dtt.type_category,
    COUNT(ft.transaction_key)                        AS txn_count,
    ROUND(100.0 * COUNT(ft.transaction_key)
          / SUM(COUNT(ft.transaction_key)) OVER (), 2) AS pct_of_total,
    SUM(CASE WHEN ft.currency = 'USD' THEN ft.amount ELSE 0 END) AS total_value_usd
FROM fact_transactions ft
JOIN dim_transaction_type dtt ON dtt.transaction_type_key = ft.transaction_type_key
GROUP BY dtt.type_code, dtt.type_label, dtt.type_category
ORDER BY txn_count DESC;

-- AN-T03: Status distribution
SELECT
    status,
    COUNT(*)                                         AS txn_count,
    ROUND(100.0 * COUNT(*)
          / SUM(COUNT(*)) OVER (), 2)                AS pct_of_total,
    SUM(CASE WHEN currency = 'USD' THEN amount ELSE 0 END) AS total_value_usd
FROM fact_transactions
GROUP BY status
ORDER BY txn_count DESC;

-- AN-T04: Reversal analysis
SELECT
    ft_rev.source_transaction_id                     AS reversal_txn_id,
    ft_rev.transaction_timestamp                     AS reversal_timestamp,
    ft_orig.source_transaction_id                    AS original_txn_id,
    ft_orig.transaction_timestamp                    AS original_timestamp,
    ft_rev.amount                                    AS reversal_amount,
    ft_rev.currency
FROM fact_transactions ft_rev
JOIN fact_transactions ft_orig
    ON ft_orig.source_transaction_id = ft_rev.reference_transaction_id
WHERE ft_rev.transaction_type_key = (
    SELECT transaction_type_key FROM dim_transaction_type WHERE type_code = 'REVERSAL'
);

-- AN-T05: Detected anomalies with evidence
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
LEFT JOIN anomaly_explanations ae ON ae.source_transaction_id = ft.source_transaction_id
WHERE ft.is_anomaly = TRUE
ORDER BY ft.transaction_timestamp;
