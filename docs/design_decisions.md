# Design Decisions — Bank Transaction Mart

*ByteSpoke AB Data & AI Internship — Technical Screening Assignment*  
*Author: Candidate | Date: October 2026*

---

## 1. Problem Statement

Design and implement a dimensional data mart for synthetic bank transactions, demonstrating data modeling, Python/SQL pipelines, anomaly detection, AI explanation, and engineering quality.

---

## 2. Architecture and Technology Choices

| Decision | Choice | Alternative Rejected | Rationale |
|----------|--------|---------------------|-----------|
| Storage | DuckDB (embedded) | PostgreSQL, SQLite | Zero-config, columnar, full SQL, QUALIFY window function support |
| Language | Python 3.11 + SQL | Spark, dbt | Minimal stack; no cluster overhead; easy to demo locally |
| Orchestration | Python pipeline.py | Airflow, Prefect | One-shot assignment scope; add orchestration in production |
| Testing | pytest | unittest | Industry standard; fixture model clean for DB isolation |
| Data gen | Faker + random | Public dataset | No confidential data; fully controlled edge cases |
| AI interface | Abstract AIExplainer | Direct API calls | Provider-independent; swap mock ↔ real without code changes |

**Architecture flow:**
```
Faker seed data → CSV files → raw_transactions (text)
   → Python validation → raw_quarantine (rejects)
   → stg_transactions (typed, deduped)
   → dim_customer / dim_account / dim_date / dim_transaction_type
   → fact_transactions (star schema)
   → anomaly_detection (rule-based)
   → AIExplainer (mock / Gemini)
   → anomaly_explanations (persisted)
```

---

## 3. Fact Grain and Dimensional Schema

**Grain:** One row per unique `source_transaction_id`. Each business event = one fact row.

**Surrogate keys:** Deterministic `ABS(hash(natural_key)) % 2^31` — avoids auto-increment, enables idempotent upserts without sequences.

**Star schema:** `fact_transactions` + four dimensions: `dim_customer`, `dim_account`, `dim_date`, `dim_transaction_type`.

**SCD choice:** Type 1 for customer and account (last-write-wins). Type 2 was considered and rejected — historical attribute tracking adds schema complexity not required by this assignment. A production system would use Type 2 for customer name/segment changes.

---

## 4. Data Quality and Deduplication Policy

Ten validation rules (VAL-001 through VAL-010) check: null IDs, null/non-numeric/negative amounts, unsupported currencies, invalid statuses, unparseable timestamps.

- **Invalid records** → `raw_quarantine` with per-rule rows. Never silently dropped.
- **Duplicates** (same `source_transaction_id`) → Python detects and flags; SQL `QUALIFY ROW_NUMBER()=1` keeps the first occurrence.
- **Valid records** → `stg_transactions` → `fact_transactions`.

---

## 5. Transaction Status and Reversal Treatment

Four statuses: COMPLETED, PENDING, FAILED, REVERSED.

- All statuses stored in facts — analytics filter by status.
- Reversals are separate REVERSAL-type transactions linked to originals via `reference_transaction_id`. The original transaction is NOT deleted or modified.
- This preserves a full audit trail and allows reversal analysis without data mutation.

---

## 6. Anomaly Detection Methodology

**Rule:** `amount > ANOMALY_THRESHOLD × median(customer_30d_history)`  
**Default threshold:** 3.0×  
**Minimum history:** 3 prior COMPLETED, non-REVERSAL transactions

**Data leakage prevention:** History uses only transactions with `timestamp < candidate_timestamp`. No future information is used.

**Baseline:** 30-day rolling median, not mean — robust to outliers in history.

**Seeded anomaly:** `TXN-ANOMALY000001` with amount $45,000 (~128× typical median of ~$350) — reliably detected.

---

## 7. AI Integration and Failure Handling

**Interface:** Abstract `AIExplainer` class — one method `explain(evidence)` → `AnomalyExplanation`.

**Adapters:** MockExplainer (default), GeminiExplainer (optional). Provider selected via `AI_PROVIDER` env var.

**Failure modes handled:**
1. Service unavailable (ConnectionError) → FALLBACK
2. Malformed JSON response → FALLBACK  
3. Missing required fields → FALLBACK
4. Invalid/placeholder API key → FALLBACK

**Explanation status:** `AI_SUCCESS`, `AI_FAILED`, or `FALLBACK` — always distinguishable.

**Persisted separately** in `anomaly_explanations` table — facts remain clean regardless of AI status.

---

## 8. Testing Strategy

8 pytest tests across three files:
- **test_pipeline.py:** Table existence, population counts, idempotency
- **test_data_quality.py:** Duplicate handling, quarantine correctness, FK integrity, status validation
- **test_anomaly_and_ai.py:** Seeded anomaly detection, normal-tx negative case, all AI failure modes

All tests use isolated in-memory DuckDB or tmp_path — no production DB touched.

---

## 9. Important Trade-offs

| Trade-off | Decision | Implication |
|-----------|----------|-------------|
| Hash surrogate keys | Deterministic, collision possible | Acceptable for ~thousands of rows; use SEQUENCE in production |
| Full-refresh staging | Simple, correct, idempotent | Inefficient at scale; add CDC/merge for millions of rows |
| Type 1 SCD | Simple, no history | Cannot analyse attribute changes over time |
| Single currency analytics | Filter to USD only | Multi-currency requires FX rates; out of scope |
| No dbt | Raw SQL scripts | Lineage and documentation less visible; add dbt in production |

---

## 10. Limitations and Production Improvements

**Limitations:**
- Hash surrogate keys have theoretical collision risk at high cardinality
- No incremental loading — full staging refresh on every run
- Single-currency aggregation only
- Type 1 SCD — no customer history
- AI model not validated for factual accuracy (it is a language model)

**Production improvements:**
- Replace hash keys with database sequences or UUIDs
- Add CDC-based incremental loading (Debezium, Airbyte)
- Add dbt for SQL lineage and documentation
- Implement Type 2 SCD for customer and account
- Add multi-currency FX rate dimension and conversion
- Deploy on Airflow or Prefect for scheduling
- Add Great Expectations for declarative data quality contracts
- Implement model monitoring for anomaly threshold drift
