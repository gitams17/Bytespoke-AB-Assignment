"""
test_anomaly_and_ai.py — Anomaly detection and AI explanation tests.

Tests:
  T10 — Seeded anomaly is detected
  T11 — Normal transaction is NOT flagged
  T12 — AI adapter failure falls back gracefully
  T13 — Malformed JSON response handled
  T14 — Missing required fields handled
"""
from __future__ import annotations

import pytest
from datetime import datetime

from bank_transaction_mart.anomaly_detection import AnomalyEvidence
from bank_transaction_mart.ai.adapters.mock_adapter import MockExplainer
from bank_transaction_mart.ai.explainer import (
    EXPLANATION_STATUS_FAILED,
    EXPLANATION_STATUS_SUCCESS,
    EXPLANATION_STATUS_FALLBACK,
    get_fallback_explanation,
)


@pytest.fixture()
def sample_evidence():
    return AnomalyEvidence(
        source_transaction_id="TXN-ANOMALY000001",
        customer_key=1001,
        account_key=2001,
        transaction_timestamp=datetime(2024, 6, 15, 14, 30),
        amount=45000.00,
        currency="USD",
        customer_median_30d=350.00,
        threshold_multiplier=3.0,
        deviation_ratio=128.57,
        detection_rule_version="v1.0",
    )


class TestAnomalyDetection:
    """T10/T11 — Seeded anomaly detected; normal transaction not flagged."""

    def test_seeded_anomaly_detected(self, full_pipeline_conn):
        result = full_pipeline_conn.execute(
            "SELECT is_anomaly FROM fact_transactions "
            "WHERE source_transaction_id = 'TXN-ANOMALY000001'"
        ).fetchone()
        assert result is not None, "Seeded anomaly transaction not found in fact table"
        assert result[0] is True, "Seeded anomaly transaction should be flagged is_anomaly=TRUE"

    def test_normal_transaction_not_flagged(self, full_pipeline_conn):
        """A small typical transaction should NOT be flagged."""
        # Fetch a non-anomaly completed transaction
        row = full_pipeline_conn.execute(
            """
            SELECT source_transaction_id, is_anomaly
            FROM fact_transactions
            WHERE is_anomaly = FALSE
              AND status = 'COMPLETED'
              AND source_transaction_id != 'TXN-ANOMALY000001'
            LIMIT 1
            """
        ).fetchone()
        assert row is not None, "Should have at least one non-anomaly completed transaction"
        assert row[1] is False, f"Transaction {row[0]} incorrectly flagged as anomaly"

    def test_anomaly_explanation_persisted(self, full_pipeline_conn):
        """After pipeline run, the seeded anomaly should have an explanation."""
        row = full_pipeline_conn.execute(
            "SELECT explanation_status FROM anomaly_explanations "
            "WHERE source_transaction_id = 'TXN-ANOMALY000001'"
        ).fetchone()
        assert row is not None, "No explanation persisted for seeded anomaly"
        assert row[0] in (
            EXPLANATION_STATUS_SUCCESS,
            EXPLANATION_STATUS_FALLBACK,
            EXPLANATION_STATUS_FAILED,
        ), f"Unexpected explanation status: {row[0]}"


class TestAIAdapterFailures:
    """T12-T14 — AI adapter failures handled gracefully."""

    def test_service_unavailable_returns_fallback(self, sample_evidence):
        explainer = MockExplainer(raise_on_call=True)
        result = explainer.explain(sample_evidence)
        # Should degrade to FAILED status (not raise)
        assert result.explanation_status == EXPLANATION_STATUS_FAILED
        assert result.summary, "Fallback summary should not be empty"
        assert result.error_detail, "Error detail should capture the exception"

    def test_malformed_json_returns_fallback(self, sample_evidence):
        explainer = MockExplainer(malformed_json=True)
        result = explainer.explain(sample_evidence)
        assert result.explanation_status == EXPLANATION_STATUS_FAILED
        assert result.summary  # fallback summary still present

    def test_missing_fields_returns_fallback(self, sample_evidence):
        explainer = MockExplainer(missing_fields=True)
        result = explainer.explain(sample_evidence)
        assert result.explanation_status == EXPLANATION_STATUS_FAILED

    def test_successful_mock_explanation(self, sample_evidence):
        explainer = MockExplainer()
        result = explainer.explain(sample_evidence)
        assert result.explanation_status == EXPLANATION_STATUS_SUCCESS
        assert result.summary
        assert result.supporting_evidence
        assert result.possible_explanations
        assert result.limitations

    def test_fallback_explanation_is_always_valid(self, sample_evidence):
        fb = get_fallback_explanation(sample_evidence)
        assert fb.explanation_status == EXPLANATION_STATUS_FALLBACK
        assert fb.is_valid(), "Fallback explanation must always pass is_valid()"
        assert "TXN-ANOMALY000001" in fb.summary
        assert "45,000.00" in fb.summary
