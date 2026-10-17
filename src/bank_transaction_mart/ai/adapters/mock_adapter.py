"""
ai/adapters/mock_adapter.py — Mock AI explainer for tests and offline use.

Returns a realistic but deterministic JSON response without calling any API.
Used by default (AI_PROVIDER=mock) and in all automated tests.
"""
from __future__ import annotations

import json

from ..explainer import AIExplainer
from ...anomaly_detection import AnomalyEvidence


class MockExplainer(AIExplainer):
    """
    Deterministic mock explainer.

    Accepts an optional *raise_on_call* flag to simulate failures in tests.
    Accepts *malformed_json* to simulate invalid model responses.
    """

    def __init__(
        self,
        raise_on_call: bool = False,
        malformed_json: bool = False,
        missing_fields: bool = False,
    ) -> None:
        self._raise_on_call = raise_on_call
        self._malformed_json = malformed_json
        self._missing_fields = missing_fields

    def _provider_name(self) -> str:
        return "mock"

    def _call_model(self, prompt: str) -> str:
        if self._raise_on_call:
            raise ConnectionError("Mock: AI service unavailable (simulated failure)")

        if self._malformed_json:
            return "This is not valid JSON { broken"

        if self._missing_fields:
            return json.dumps({"summary": "Only summary field, others missing"})

        # Realistic mock response
        return json.dumps(
            {
                "summary": (
                    "This transaction is flagged because its amount significantly "
                    "exceeds the customer's recent transaction history, suggesting "
                    "an unusual spending or transfer pattern that warrants review."
                ),
                "supporting_evidence": (
                    "The transaction amount is more than 3× the customer's "
                    "30-day median, triggering the statistical anomaly rule. "
                    "The deviation ratio and absolute amount are both unusually high "
                    "compared to baseline activity."
                ),
                "possible_explanations": (
                    "1. Legitimate large one-off payment (e.g., rent, tax, or tuition). "
                    "2. Unauthorised account access or push-payment fraud. "
                    "3. Erroneous duplicate or inflated entry. "
                    "4. Business payment that is normal for this customer's profile."
                ),
                "limitations": (
                    "This analysis is based solely on statistical deviation from "
                    "a 30-day rolling median. It cannot determine intent, verify "
                    "merchant legitimacy, or assess real-time fraud risk. "
                    "Human review and additional KYC checks are required before "
                    "any account action is taken."
                ),
            },
            indent=2,
        )
