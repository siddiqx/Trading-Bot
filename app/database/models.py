"""Database models for forex live signal records."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Index,
)
from app.database.database import Base


class SignalModel(Base):
    """Stores every verified forex signal and its forward-testing lifecycle state."""

    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    signal_id = Column(String(64), unique=True, index=True, nullable=False)
    received_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    signal_time = Column(String(64), nullable=False)
    symbol = Column(String(20), index=True, nullable=False)
    exchange = Column(String(32), nullable=True, default="FX")
    timeframe = Column(String(10), nullable=False, default="60")
    direction = Column(String(10), nullable=False)  # LONG or SHORT
    entry = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    risk_reward = Column(Float, nullable=False, default=2.0)
    signal_score = Column(Float, nullable=False)
    adx = Column(Float, nullable=False)
    atr = Column(Float, nullable=False)
    roc = Column(Float, nullable=False)
    htf_regime = Column(String(20), nullable=False)  # BULLISH or BEARISH
    breakout_length = Column(Integer, nullable=False, default=20)
    atr_multiplier = Column(Float, nullable=False, default=1.75)
    strategy_version = Column(String(20), nullable=False, default="1.0.0")
    environment = Column(String(20), nullable=False, default="LIVE")
    status = Column(String(32), nullable=False, default="ACCEPTED")

    # Telegram notification audit
    telegram_sent = Column(Boolean, default=False, nullable=False)
    telegram_message_id = Column(Integer, nullable=True)

    # Forward performance & outcome tracking fields (for live testing)
    outcome = Column(String(20), nullable=True, default="PENDING")  # WIN, LOSS, BREAKEVEN, EXPIRED
    exit_price = Column(Float, nullable=True)
    exit_time = Column(String(64), nullable=True)
    r_multiple = Column(Float, nullable=True)
    maximum_favorable_excursion = Column(Float, nullable=True)  # MFE
    maximum_adverse_excursion = Column(Float, nullable=True)  # MAE

    __table_args__ = (
        Index("idx_symbol_direction", "symbol", "direction"),
        Index("idx_received_at", "received_at"),
    )
