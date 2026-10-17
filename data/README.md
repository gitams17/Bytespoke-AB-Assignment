# docs/data/README.md

## Data Directory

```
data/
├── sample/          Static sample CSV files (committed to git — illustrative only)
└── generated/       Runtime-generated synthetic data (NOT committed — in .gitignore)
```

### Generated files (created by `python scripts/run_pipeline.py --regenerate`)

| File | Rows | Description |
|------|------|-------------|
| `customers.csv` | 8 | Synthetic customer master data |
| `accounts.csv` | 8–12 | Synthetic bank accounts (1–2 per customer) |
| `transactions.csv` | ~126 | Synthetic transactions including edge cases |

### Intentional edge cases in transactions.csv

| Record | Type | Purpose |
|--------|------|---------|
| `TXN-ANOMALY000001` | Anomaly seed | Amount $45,000 — ~128× median → detected by anomaly rule |
| `TXN-REVERSAL000001` | Reversal | REVERSAL type linked to a prior COMPLETED transaction |
| Two duplicated rows | Exact duplicates | Deduplication test — must not create two fact rows |
| `TXN-INVALID000001` | Null amount | Quarantine test — VAL-004 rule |
| `TXN-INVALID000002` | Currency XXX | Quarantine test — VAL-007 rule |

### Schema

#### customers.csv
| Column | Type | Notes |
|--------|------|-------|
| customer_id | string | Natural key (CUST-NNNN) |
| customer_name | string | Faker-generated |
| email | string | Faker-generated |
| phone | string | Faker-generated |
| country | string | US, SE, GB, DE |
| customer_segment | string | RETAIL, SME, CORPORATE |
| risk_rating | string | LOW, MEDIUM, HIGH |
| onboarded_date | ISO date | |

#### accounts.csv
| Column | Type | Notes |
|--------|------|-------|
| account_id | string | Natural key (ACCT-NNNN) |
| customer_id | string | FK to customers.csv |
| account_type | string | CHECKING, SAVINGS, CREDIT |
| currency | string | USD |
| opened_date | ISO date | |
| credit_limit | decimal | NULL for non-credit accounts |

#### transactions.csv
| Column | Type | Notes |
|--------|------|-------|
| source_transaction_id | string | Natural key (TXN-...) |
| account_id | string | FK to accounts.csv |
| customer_id | string | FK to customers.csv |
| transaction_date | ISO timestamp | |
| amount | decimal | May be empty (edge case) |
| currency | string | USD or XXX (edge case) |
| transaction_type | string | PURCHASE, TRANSFER, etc. |
| status | string | COMPLETED, PENDING, FAILED |
| description | string | |
| reference_transaction_id | string | For REVERSAL type; empty otherwise |
