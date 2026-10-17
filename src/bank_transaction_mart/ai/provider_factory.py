"""
ai/provider_factory.py — Build the correct AIExplainer from config.

Centralises all provider selection logic. No other module makes this decision.
"""
from __future__ import annotations

import logging

from .explainer import AIExplainer
from ..config import cfg

logger = logging.getLogger(__name__)


def build_explainer(provider: str | None = None) -> AIExplainer:
    """
    Return an AIExplainer for the configured (or overridden) provider.

    Parameters
    ----------
    provider : str | None
        Override AI_PROVIDER from config. Useful in tests.

    Supported values: "mock", "gemini", "openai"
    Falls back to MockExplainer if provider is unsupported.
    """
    selected = (provider or cfg.AI_PROVIDER).lower()
    logger.info("Building AI explainer: provider=%s", selected)

    if selected == "mock":
        from .adapters.mock_adapter import MockExplainer
        return MockExplainer()

    if selected == "gemini":
        try:
            from .adapters.gemini_adapter import GeminiExplainer
            return GeminiExplainer(api_key=cfg.GEMINI_API_KEY or "")
        except (ImportError, ValueError) as exc:
            logger.warning("Gemini unavailable (%s) — falling back to mock", exc)
            from .adapters.mock_adapter import MockExplainer
            return MockExplainer()

    if selected == "openai":
        logger.warning("OpenAI adapter not yet implemented — using mock")
        from .adapters.mock_adapter import MockExplainer
        return MockExplainer()

    logger.warning("Unknown AI_PROVIDER '%s' — using mock", selected)
    from .adapters.mock_adapter import MockExplainer
    return MockExplainer()
