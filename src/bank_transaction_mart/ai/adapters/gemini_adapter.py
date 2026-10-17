"""
ai/adapters/gemini_adapter.py — Google Gemini AI explainer adapter.

Only imported when AI_PROVIDER=gemini.
Requires GEMINI_API_KEY in environment.
Raises ImportError cleanly if google-generativeai is not installed.
"""
from __future__ import annotations

import logging

from ..explainer import AIExplainer

logger = logging.getLogger(__name__)


class GeminiExplainer(AIExplainer):
    """
    Adapter for Google Gemini (gemini-1.5-flash).
    """

    MODEL_NAME = "gemini-1.5-flash"

    def __init__(self, api_key: str) -> None:
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "google-generativeai not installed. Run: pip install google-generativeai"
            ) from exc

        if not api_key or api_key == "your_gemini_api_key_here":
            raise ValueError(
                "GEMINI_API_KEY is missing or is the placeholder value. "
                "Set it in .env or use AI_PROVIDER=mock."
            )

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(self.MODEL_NAME)
        logger.info("GeminiExplainer initialised with model %s", self.MODEL_NAME)

    def _provider_name(self) -> str:
        return "gemini"

    def _call_model(self, prompt: str) -> str:
        response = self._model.generate_content(prompt)
        return response.text
