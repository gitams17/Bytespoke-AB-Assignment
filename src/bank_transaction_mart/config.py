"""
config.py — Central configuration loader.

Reads from environment variables (populated from .env via python-dotenv).
All other modules import from here; no other module reads os.environ directly.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # config.py → bank_transaction_mart → src → project root
load_dotenv(_PROJECT_ROOT / ".env", override=False)


class Config:
    """Central configuration object — read once, reuse everywhere."""

    # Database
    DB_PATH: str = os.getenv("DB_PATH", "data/bank_mart.duckdb")

    # Data generation
    DATA_SEED: int = int(os.getenv("DATA_SEED", "42"))

    # Anomaly detection
    ANOMALY_THRESHOLD: float = float(os.getenv("ANOMALY_THRESHOLD", "3.0"))
    ANOMALY_MIN_HISTORY: int = int(os.getenv("ANOMALY_MIN_HISTORY", "3"))
    ANOMALY_RULE_VERSION: str = "v1.0"

    # AI provider
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "mock").lower()
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")

    # Supported statuses
    VALID_STATUSES: tuple[str, ...] = ("COMPLETED", "PENDING", "FAILED", "REVERSED")
    VALID_CURRENCIES: tuple[str, ...] = ("USD", "EUR", "GBP", "SEK")

    @classmethod
    def db_path(cls) -> Path:
        return _PROJECT_ROOT / cls.DB_PATH

    @classmethod
    def sql_dir(cls) -> Path:
        return _PROJECT_ROOT / "sql"


cfg = Config()
