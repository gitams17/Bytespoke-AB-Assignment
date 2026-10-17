"""
ai/explainer.py — Provider-independent AI explanation interface.

Design decisions:
  • AIExplainer is an abstract base class — new providers implement it.
  • AnomalyExplanation is a validated dataclass (required fields enforced).
  • The pipeline never imports provider SDKs directly — only through adapters.
  • If the adapter fails for any reason, get_fallback_explanation() returns
    a deterministic rule-based summary so the mart remains fully usable.
  • Explanation status distinguishes AI_SUCCESS, AI_FAILED, and FALLBACK.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..anomaly_detection import AnomalyEvidence

logger = logging.getLogger(__name__)

EXPLANATION_STATUS_SUCCESS  = "AI_SUCCESS"
EXPLANATION_STATUS_FAILED   = "AI_FAILED"
EXPLANATION_STATUS_FALLBACK = "FALLBACK"


@dataclass
class AnomalyExplanation:
    """
    Validated AI explanation for one anomaly.

    Required fields: summary, supporting_evidence, possible_explanations, limitations.
    Optional: raw_ai_response for audit.
    """
    source_transaction_id: str
    explanation_status: str                        # AI_SUCCESS | AI_FAILED | FALLBACK
    explanation_provider: str
    summary: str
    supporting_evidence: str
    possible_explanations: str
    limitations: str
    raw_ai_response: str = ""
    error_detail: str = ""

    def is_valid(self) -> bool:
        """Return True if all required text fields are non-empty."""
        return all([
            self.summary.strip(),
            self.supporting_evidence.strip(),
            self.possible_explanations.strip(),
            self.limitations.strip(),
        ])


def get_fallback_explanation(evidence: AnomalyEvidence) -> AnomalyExplanation:
    """
    Deterministic, rule-based fallback explanation.
    Always succeeds — used when AI provider is unavailable or returns invalid output.
    """
    summary = (
        f"Transaction {evidence.source_transaction_id} was flagged as anomalous. "
        f"The amount of {evidence.amount:,.2f} {evidence.currency} is "
        f"{evidence.deviation_ratio:.1f}× the customer's 30-day median "
        f"of {evidence.customer_median_30d:,.2f} {evidence.currency} "
        f"(threshold: {evidence.threshold_multiplier}×)."
    )
    supporting_evidence = (
        f"Transaction ID: {evidence.source_transaction_id} | "
        f"Amount: {evidence.amount:,.2f} {evidence.currency} | "
        f"30-day median: {evidence.customer_median_30d:,.2f} {evidence.currency} | "
        f"Deviation ratio: {evidence.deviation_ratio:.2f}× | "
        f"Detection rule: {evidence.detection_rule_version}"
    )
    possible_explanations = (
        "1. Large one-off payment (e.g., rent, insurance, tax). "
        "2. Erroneous or fraudulent transaction. "
        "3. Irregular but legitimate business transfer. "
        "4. Account takeover or authorised push payment fraud."
    )
    limitations = (
        "This explanation is deterministic and rule-based. "
        "No AI model was consulted. "
        "No fraud determination is made — only statistical deviation is reported. "
        "Human review is required before any action is taken."
    )
    return AnomalyExplanation(
        source_transaction_id=evidence.source_transaction_id,
        explanation_status=EXPLANATION_STATUS_FALLBACK,
        explanation_provider="fallback",
        summary=summary,
        supporting_evidence=supporting_evidence,
        possible_explanations=possible_explanations,
        limitations=limitations,
    )


class AIExplainer(ABC):
    """
    Abstract AI explainer interface.

    Concrete subclasses implement _call_model() with provider-specific logic.
    """

    def explain(self, evidence: AnomalyEvidence) -> AnomalyExplanation:
        """
        Generate an explanation for *evidence*.

        Handles all exceptions and validates the response.
        Returns a fallback explanation if anything goes wrong.
        """
        prompt = self._build_prompt(evidence)
        try:
            raw_response = self._call_model(prompt)
            parsed = self._parse_response(raw_response, evidence)
            if not parsed.is_valid():
                raise ValueError(f"Missing required fields in AI response: {raw_response[:200]}")
            parsed.explanation_status = EXPLANATION_STATUS_SUCCESS
            logger.info("AI explanation generated for %s via %s",
                        evidence.source_transaction_id, parsed.explanation_provider)
            return parsed
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "AI explanation failed for %s (%s: %s) — using fallback",
                evidence.source_transaction_id,
                type(exc).__name__,
                exc,
            )
            fb = get_fallback_explanation(evidence)
            fb.explanation_status = EXPLANATION_STATUS_FAILED
            fb.error_detail = f"{type(exc).__name__}: {exc}"
            return fb

    def _build_prompt(self, evidence: AnomalyEvidence) -> str:
        """Build the structured prompt sent to the model."""
        return f"""You are a banking fraud analyst assistant.
A transaction has been flagged as statistically anomalous by a rule-based detection system.
Your task is to explain the anomaly for a human reviewer. Do NOT make a fraud determination.

Transaction evidence:
- Transaction ID: {evidence.source_transaction_id}
- Timestamp: {evidence.transaction_timestamp}
- Amount: {evidence.amount:,.2f} {evidence.currency}
- Customer 30-day median amount: {evidence.customer_median_30d:,.2f} {evidence.currency}
- Deviation ratio: {evidence.deviation_ratio:.2f}× the median
- Detection threshold: {evidence.threshold_multiplier}×
- Rule version: {evidence.detection_rule_version}

Respond ONLY with valid JSON in exactly this structure:
{{
  "summary": "<one-sentence plain-English summary>",
  "supporting_evidence": "<key facts from the evidence above>",
  "possible_explanations": "<numbered list of 3-4 plausible explanations>",
  "limitations": "<what this analysis cannot determine>"
}}"""

    @abstractmethod
    def _call_model(self, prompt: str) -> str:
        """
        Call the underlying AI model with *prompt*.
        Must return the raw text response string.
        Raise an exception on failure.
        """

    def _parse_response(self, raw: str, evidence: AnomalyEvidence) -> AnomalyExplanation:
        """
        Parse the raw model response into an AnomalyExplanation.
        Raises ValueError if JSON is invalid or required fields are missing.
        """
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in AI response: {exc}") from exc

        required = ["summary", "supporting_evidence", "possible_explanations", "limitations"]
        missing = [k for k in required if not data.get(k)]
        if missing:
            raise ValueError(f"AI response missing required fields: {missing}")

        return AnomalyExplanation(
            source_transaction_id=evidence.source_transaction_id,
            explanation_status=EXPLANATION_STATUS_SUCCESS,  # overridden by caller
            explanation_provider=self._provider_name(),
            summary=str(data["summary"]),
            supporting_evidence=str(data["supporting_evidence"]),
            possible_explanations=str(data["possible_explanations"]),
            limitations=str(data["limitations"]),
            raw_ai_response=raw[:4000],   # truncate for storage
        )

    def _provider_name(self) -> str:
        return self.__class__.__name__.lower().replace("explainer", "")
