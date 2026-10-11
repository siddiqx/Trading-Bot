"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Server
    PROJECT_NAME: str = "Forex Live Signal Bot"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # Security
    WEBHOOK_SECRET: str = Field(
        default="test-secret-key-12345",
        description="Shared secret for TradingView webhook authentication",
    )

    # Telegram
    TELEGRAM_BOT_TOKEN: str = Field(
        default="",
        description="Telegram bot token obtained from @BotFather",
    )
    TELEGRAM_CHAT_ID: str = Field(
        default="",
        description="Telegram chat or channel ID where signals should be delivered",
    )

    # Database
    DATABASE_URL: str = Field(
        default="sqlite:///./forex_signals.db",
        description="SQLAlchemy database connection string",
    )

    # Strategy Parameters
    STRATEGY_VERSION: str = "1.0.0"
    DEFAULT_ADX_MIN: float = 18.0
    DEFAULT_ADX_STRONG: float = 25.0
    DEFAULT_ROC_LOOKBACK: int = 20
    DEFAULT_DONCHIAN_LENGTH: int = 20
    DEFAULT_ATR_PERIOD: int = 14
    DEFAULT_ATR_MULTIPLIER: float = 1.0
    DEFAULT_RISK_REWARD: float = 1.5
    MIN_SIGNAL_SCORE: float = 60.0

    # Fixed Trade Exits
    TAKE_PROFIT_PIPS: float = 15.0
    STOP_LOSS_PIPS: float = 10.0

    # Gold Exclusion Flag
    GOLD_ENABLED: bool = False

    # Session Filter
    SESSION_FILTER_ENABLED: bool = False
    ALLOWED_SESSIONS: str = "LONDON,NEW_YORK,OVERLAP"

    # News Filter
    NEWS_FILTER_ENABLED: bool = False

    # Anti-Wick Strong Body Filter
    ANTI_WICK_FILTER_ENABLED: bool = True
    MIN_BODY_RATIO: float = 0.65

    # Friday Cutoff Hour
    FOREX_FRIDAY_CUTOFF_HOUR: int = 12

    # Prop Firm Challenge Acceleration Sizing
    PROP_PHASE_1_RISK_PCT: float = 1.0
    PROP_PHASE_2_RISK_PCT: float = 0.5

    # Post-Loss Pullback Protection
    FOREX_LOSS_COOLDOWN_HOURS: int = 6

    # Supported Symbols - Strictly Verified Institutional Forex Whitelist Only (No Gold)
    SUPPORTED_SYMBOLS: List[str] = [
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "USDCAD",
        "USDCHF",
        "AUDUSD",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    @property
    def allowed_sessions_list(self) -> List[str]:
        return [s.strip().upper() for s in self.ALLOWED_SESSIONS.split(",") if s.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
