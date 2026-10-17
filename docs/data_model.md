# Data Model — Bank Transaction Mart

## Fact Grain

**Table:** `fact_transactions`  
**Grain:** One row per unique source transaction event, identified by `source_transaction_id`.

A "transaction event" is a single business action recorded in the source system:
- Purchases, transfers, deposits, withdrawals, and fees each produce one event.
- **Reversals** are separate events (type = REVERSAL) linked to the original via `reference_transaction_id`.
- **Duplicates** (same `source_transaction_id`) are deduplicated to one fact row.
- **Failed and pending** transactions are stored — status carries the truth.

---

## Star Schema Diagram

```
                        ┌──────────────────┐
                        │   dim_date       │
                        │──────────────────│
                        │ date_key (PK)    │
                        │ full_date        │
                        │ year, quarter    │
                        │ month, month_name│
                        │ day_of_week      │
                        │ is_weekend       │
                        └────────┬─────────┘
                                 │ FK date_key
              ┌──────────────────┼──────────────────────┐
              │                  │                      │
   ┌──────────┴──────┐  ┌────────┴──────────┐  ┌───────┴──────────────┐
   │  dim_customer   │  │  fact_transactions │  │ dim_transaction_type │
   │─────────────────│  │────────────────────│  │──────────────────────│
   │ customer_key(PK)│◄─┤ customer_key (FK)  │  │ transaction_type_    │
   │ customer_id     │  │ account_key (FK)   ├─►│ key (PK)             │
   │ full_name       │  │ transaction_type_  │  │ type_code            │
   │ email, phone    │  │ key (FK)           │  │ type_label           │
   │ country         │  │ date_key (FK)      │  │ type_category        │
   │ customer_segment│  │──────────────────  │  │ description          │
   │ risk_rating     │  │ transaction_key(PK)│  └──────────────────────┘
   └─────────────────┘  │ source_txn_id(NK)  │
                        │ transaction_ts     │
   ┌─────────────────┐  │ amount             │
   │  dim_account    │  │ currency           │
   │─────────────────│  │ status             │
   │ account_key (PK)│◄─┤ account_key (FK)   │
   │ account_id      │  │ description        │
   │ customer_key(FK)│  │ reference_txn_id   │
   │ account_type    │  │ is_anomaly         │
   │ currency        │  │ loaded_at          │
   │ opened_date     │  └────────────────────┘
   │ credit_limit    │
   └─────────────────┘
```

---

## Table Definitions

### fact_transactions

| Column | Type | Notes |
|--------|------|-------|
| `transaction_key` | INTEGER PK | Deterministic hash surrogate key |
| `source_transaction_id` | VARCHAR UNIQUE | Natural key from source; idempotency key |
| `customer_key` | INTEGER FK | → dim_customer |
| `account_key` | INTEGER FK | → dim_account |
| `transaction_type_key` | INTEGER FK | → dim_transaction_type |
| `date_key` | INTEGER FK | → dim_date (YYYYMMDD) |
| `transaction_timestamp` | TIMESTAMP | Full precision event time |
| `amount` | DECIMAL(18,2) | Transaction amount (always ≥ 0) |
| `currency` | VARCHAR(3) | ISO 4217 currency code |
| `status` | VARCHAR | COMPLETED \| PENDING \| FAILED \| REVERSED |
| `description` | VARCHAR | Merchant or transfer description |
| `reference_transaction_id` | VARCHAR | For REVERSAL: source_transaction_id of original |
| `is_anomaly` | BOOLEAN | Set by anomaly detection rule |
| `loaded_at` | TIMESTAMP | ETL audit timestamp |

### dim_customer

| Column | Type | Notes |
|--------|------|-------|
| `customer_key` | INTEGER PK | Deterministic hash surrogate key |
| `customer_id` | VARCHAR UNIQUE | Natural key (CUST-NNNN) |
| `full_name` | VARCHAR | |
| `email` | VARCHAR | |
| `country` | VARCHAR | ISO country code |
| `customer_segment` | VARCHAR | RETAIL \| SME \| CORPORATE |
| `risk_rating` | VARCHAR | LOW \| MEDIUM \| HIGH |
| `onboarded_date` | DATE | |
| `is_active` | BOOLEAN | |
| `updated_at` | TIMESTAMP | Type 1 SCD timestamp |

**SCD Type:** 1 — last-write-wins. Historical attribute changes not tracked.

### dim_account

| Column | Type | Notes |
|--------|------|-------|
| `account_key` | INTEGER PK | Deterministic hash surrogate key |
| `account_id` | VARCHAR UNIQUE | Natural key (ACCT-NNNN) |
| `customer_key` | INTEGER FK | → dim_customer |
| `account_type` | VARCHAR | CHECKING \| SAVINGS \| CREDIT |
| `currency` | VARCHAR(3) | ISO 4217 |
| `opened_date` | DATE | |
| `credit_limit` | DECIMAL(18,2) | NULL for non-credit accounts |
| `updated_at` | TIMESTAMP | Type 1 SCD timestamp |

**SCD Type:** 1.

### dim_date

| Column | Type | Notes |
|--------|------|-------|
| `date_key` | INTEGER PK | YYYYMMDD integer |
| `full_date` | DATE UNIQUE | Calendar date |
| `year`, `quarter`, `month` | INTEGER | |
| `month_name`, `day_name` | VARCHAR | |
| `week_of_year` | INTEGER | ISO week |
| `day_of_week` | INTEGER | 1=Mon … 7=Sun |
| `is_weekend` | BOOLEAN | Saturday or Sunday |
| `is_month_start`, `is_month_end` | BOOLEAN | |

**Coverage:** 2020-01-01 to 2028-12-31 (pre-populated).

### dim_transaction_type (Type 0 — static reference)

| type_code | type_label | type_category |
|-----------|-----------|---------------|
| PURCHASE | Purchase | DEBIT |
| TRANSFER | Transfer | DEBIT |
| WITHDRAWAL | Withdrawal | DEBIT |
| DEPOSIT | Deposit | CREDIT |
| REFUND | Refund | CREDIT |
| FEE | Fee | DEBIT |
| INTEREST | Interest | CREDIT |
| REVERSAL | Reversal | CREDIT |
| PAYMENT | Payment | CREDIT |
| OTHER | Other | DEBIT |

---

## Analytical Measures

| Measure | Definition | Filter |
|---------|-----------|--------|
| Completed transaction count | COUNT(*) WHERE status='COMPLETED' | Excludes pending, failed, reversed |
| Completed value (USD) | SUM(amount) WHERE status='COMPLETED' AND currency='USD' | Single currency only |
| Average transaction amount | AVG(amount) WHERE currency='USD' | Currency-filtered |
| Customer transaction frequency | COUNT(*) per customer_key | All statuses unless specified |
| Daily volume | COUNT(*) GROUP BY date_key | |
| Daily value | SUM(amount) WHERE currency='USD' GROUP BY date_key | |
| Failed count | COUNT(*) WHERE status='FAILED' | |
| Pending count | COUNT(*) WHERE status='PENDING' | |
| Reversal count | COUNT(*) WHERE transaction_type='REVERSAL' | |
| Anomaly count | COUNT(*) WHERE is_anomaly=TRUE | |

---

## Unknown Members

- If `transaction_type` has no match in `dim_transaction_type`, `type_key=10` (OTHER) is used.
- Foreign key integrity is validated post-load by DQ checks DQ-03 through DQ-05.
