"""Pydantic schemas for TradingView incoming webhooks and signal validation."""

import re
from typing import Optional, Literal
from pydantic import BaseModel, Field, model_validator


def normalize_forex_symbol(raw_symbol: str) -> str:
    """Normalize symbols like 'OANDA:EUR_USD', 'FX:EURUSD', 'EUR/USD' to 'EURUSD'."""
    clean = raw_symbol.strip().upper()
    if ":" in clean:
        clean = clean.split(":")[-1]
    clean = re.sub(r"[^A-Z]", "", clean)
    return clean


class SignalPayload(BaseModel):
    """Schema representing incoming TradingView alert JSON payload."""

    event: str = Field(default="forex_signal", description="Event name identifier")
    strategy: str = Field(
        default="adaptive_trend_momentum_breakout",
        description="Name of the Pine Script strategy",
    )
    version: str = Field(default="1.0.0", description="Payload specification version")
    symbol: str = Field(..., description="Forex instrument ticker")
    exchange: Optional[str] = Field(default="FX", description="Exchange / broker source")
    timeframe: str = Field(default="60", description="Execution candle timeframe in minutes")
    direction: Literal["LONG", "SHORT"] = Field(
        ..., description="Direction must be either LONG or SHORT"
    )
    signal_time: str = Field(..., description="Timestamp of the confirmed candle")
    price: float = Field(..., gt=0, description="Last close or trigger price")
    entry: float = Field(..., gt=0, description="Calculated theoretical entry price")
    stop_loss: float = Field(..., gt=0, description="Calculated stop loss price")
    take_profit: float = Field(..., gt=0, description="Calculated take profit target")
    risk_reward: float = Field(
        default=2.0, gt=0, description="Planned risk to reward multiple"
    )
    signal_score: float = Field(
        ..., ge=0, le=100, description="Deterministic signal quality score (0-100)"
    )
    adx: float = Field(..., ge=0, description="ADX(14) reading at candle close")
    atr: float = Field(..., gt=0, description="ATR(14) volatility reading")
    roc: float = Field(..., description="Rate of Change momentum value")
    htf_regime: Literal["BULLISH", "BEARISH"] = Field(
        ..., description="4H trend regime state"
    )
    breakout_length: int = Field(
        default=20, gt=0, description="Donchian breakout channel lookback"
    )
    atr_multiplier: float = Field(
        default=1.75, gt=0, description="ATR multiplier applied for SL"
    )
    strategy_version: str = Field(
        default="1.0.0", description="Pine Script strategy version"
    )
    candle_body_ratio: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Anti-wick candle body ratio (0.0 - 1.0)"
    )
    rsi: Optional[float] = Field(
        default=None, description="RSI(14) reading at candle close"
    )
    suggested_lots: Optional[float] = Field(
        default=None, gt=0, description="Recommended position sizing in lots (e.g. 0.45)"
    )
    risk_percent: Optional[float] = Field(
        default=1.0, gt=0, description="Risk percentage per trade (e.g. 1.0%)"
    )
    entry_type: Optional[str] = Field(
        default="MOMENTUM_BREAKOUT", description="Execution trigger: MOMENTUM_BREAKOUT or PULLBACK_CONTINUATION"
    )
    entry_range_min: Optional[float] = Field(
        default=None, description="Lower bound of optimal entry range"
    )
    entry_range_max: Optional[float] = Field(
        default=None, description="Upper bound of optimal entry range"
    )
    order_block_high: Optional[float] = Field(
        default=None, description="Upper boundary of the origin Order Block"
    )
    order_block_low: Optional[float] = Field(
        default=None, description="Lower boundary / invalidation level of the origin Order Block"
    )
    fib_50: Optional[float] = Field(
        default=None, description="50.0% Fibonacci Equilibrium level"
    )
    fib_618: Optional[float] = Field(
        default=None, description="61.8% Fibonacci Golden Pocket level"
    )
    fib_ext_tp: Optional[float] = Field(
        default=None, description="Fibonacci Extension Take Profit target level"
    )
    intermediate_regime: Optional[str] = Field(
        default=None, description="Intermediate timeframe regime (e.g. 15m structure: BULLISH, BEARISH)"
    )
    webhook_secret: str = Field(
        ..., description="Shared authentication secret sent by TradingView"
    )
    environment: Optional[str] = Field(
        default="LIVE", description="'LIVE' or 'TEST' indicator"
    )
    signal_id: Optional[str] = Field(
        default=None, description="Optional unique signal ID; generated if omitted"
    )

    @model_validator(mode="before")
    @classmethod
    def preprocess_payload(cls, data: dict):
        """Coerce strings to floats where TradingView outputs string numbers."""
        if not isinstance(data, dict):
            return data

        # Normalize direction
        if "direction" in data and isinstance(data["direction"], str):
            data["direction"] = data["direction"].strip().upper()

        # Normalize htf_regime
        if "htf_regime" in data and isinstance(data["htf_regime"], str):
            data["htf_regime"] = data["htf_regime"].strip().upper()

        # Normalize float fields
        float_fields = [
            "price",
            "entry",
            "stop_loss",
            "take_profit",
            "risk_reward",
            "signal_score",
            "adx",
            "atr",
            "roc",
            "atr_multiplier",
        ]
        for field in float_fields:
            if field in data and isinstance(data[field], str):
                try:
                    data[field] = float(data[field])
                except ValueError:
                    pass

        # Normalize symbol
        if "symbol" in data and isinstance(data["symbol"], str):
            data["symbol"] = normalize_forex_symbol(data["symbol"])

        return data

    @model_validator(mode="after")
    def validate_trade_geometry_and_id(self):
        """Validate logical SL/TP relationships and construct deterministic signal_id."""
        # Validate direction-specific price relationships
        if self.direction == "LONG":
            if not (self.stop_loss < self.entry < self.take_profit):
                raise ValueError(
                    f"Invalid trade geometry for LONG: Stop Loss ({self.stop_loss}) "
                    f"must be below Entry ({self.entry}) and Take Profit ({self.take_profit}) "
                    f"must be above Entry."
                )
            if self.htf_regime != "BULLISH":
                raise ValueError(
                    f"Contradictory regime for LONG: 4H regime is {self.htf_regime}, expected BULLISH."
                )
        elif self.direction == "SHORT":
            if not (self.take_profit < self.entry < self.stop_loss):
                raise ValueError(
                    f"Invalid trade geometry for SHORT: Stop Loss ({self.stop_loss}) "
                    f"must be above Entry ({self.entry}) and Take Profit ({self.take_profit}) "
                    f"must be below Entry."
                )
            if self.htf_regime != "BEARISH":
                raise ValueError(
                    f"Contradictory regime for SHORT: 4H regime is {self.htf_regime}, expected BEARISH."
                )

        # Generate deterministic signal_id if not present
        if not self.signal_id:
            # Clean timestamp characters for safe key
            clean_time = re.sub(r"[^0-9A-Za-z]", "", str(self.signal_time))
            self.signal_id = f"{self.symbol}_{self.timeframe}_{clean_time}_{self.direction}"

        return self


class SignalResponse(BaseModel):
    """Structured response returned by webhook endpoint."""

    status: str
    message: str
    signal_id: Optional[str] = None
    telegram_delivered: bool = False
