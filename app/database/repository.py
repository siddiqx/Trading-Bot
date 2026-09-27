"""Database repository operations for signals."""

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.models import SignalModel


class SignalRepository:
    """Repository handling CRUD operations for trading signals."""

    @staticmethod
    def get_by_signal_id(db: Session, signal_id: str) -> Optional[SignalModel]:
        """Fetch signal by its unique idempotency identifier."""
        return db.query(SignalModel).filter(SignalModel.signal_id == signal_id).first()

    @staticmethod
    def create_signal(db: Session, data: Dict[str, Any]) -> SignalModel:
        """Create and commit a new signal record."""
        signal = SignalModel(
            signal_id=data["signal_id"],
            signal_time=str(data.get("signal_time", "")),
            symbol=str(data["symbol"]).upper().strip(),
            exchange=data.get("exchange", "FX"),
            timeframe=str(data.get("timeframe", "60")),
            direction=str(data["direction"]).upper().strip(),
            entry=float(data["entry"]),
            stop_loss=float(data["stop_loss"]),
            take_profit=float(data["take_profit"]),
            risk_reward=float(data.get("risk_reward", 2.0)),
            signal_score=float(data.get("signal_score", 0.0)),
            adx=float(data.get("adx", 0.0)),
            atr=float(data.get("atr", 0.0)),
            roc=float(data.get("roc", 0.0)),
            htf_regime=str(data.get("htf_regime", "NEUTRAL")).upper().strip(),
            breakout_length=int(data.get("breakout_length", 20)),
            atr_multiplier=float(data.get("atr_multiplier", 1.75)),
            strategy_version=str(data.get("strategy_version", "1.0.0")),
            environment=str(data.get("environment", "LIVE")).upper().strip(),
            status=str(data.get("status", "ACCEPTED")),
            telegram_sent=bool(data.get("telegram_sent", False)),
            telegram_message_id=data.get("telegram_message_id"),
        )
        db.add(signal)
        db.commit()
        db.refresh(signal)
        return signal

    @staticmethod
    def update_telegram_status(
        db: Session,
        signal_id: str,
        sent: bool,
        message_id: Optional[int] = None,
    ) -> Optional[SignalModel]:
        """Update Telegram dispatch result."""
        signal = db.query(SignalModel).filter(SignalModel.signal_id == signal_id).first()
        if signal:
            signal.telegram_sent = sent
            signal.telegram_message_id = message_id
            db.commit()
            db.refresh(signal)
        return signal

    @staticmethod
    def get_recent_signals(db: Session, limit: int = 10) -> List[SignalModel]:
        """Fetch the most recent signals."""
        return (
            db.query(SignalModel)
            .order_by(SignalModel.received_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_latest_signal(db: Session) -> Optional[SignalModel]:
        """Fetch the single most recent signal."""
        return (
            db.query(SignalModel)
            .order_by(SignalModel.received_at.desc())
            .first()
        )

    @staticmethod
    def get_stats(db: Session) -> Dict[str, Any]:
        """Calculate forward-testing summary statistics."""
        total = db.query(func.count(SignalModel.id)).scalar() or 0
        long_count = (
            db.query(func.count(SignalModel.id))
            .filter(SignalModel.direction == "LONG")
            .scalar()
            or 0
        )
        short_count = (
            db.query(func.count(SignalModel.id))
            .filter(SignalModel.direction == "SHORT")
            .scalar()
            or 0
        )
        live_count = (
            db.query(func.count(SignalModel.id))
            .filter(SignalModel.environment == "LIVE")
            .scalar()
            or 0
        )
        test_count = (
            db.query(func.count(SignalModel.id))
            .filter(SignalModel.environment == "TEST")
            .scalar()
            or 0
        )

        # By pair
        pair_counts = (
            db.query(SignalModel.symbol, func.count(SignalModel.id))
            .group_by(SignalModel.symbol)
            .all()
        )
        pairs_dict = {p[0]: p[1] for p in pair_counts}

        # Outcomes tracking
        completed_outcomes = (
            db.query(SignalModel.outcome, func.count(SignalModel.id))
            .group_by(SignalModel.outcome)
            .all()
        )
        outcomes_dict = {o[0]: o[1] for o in completed_outcomes if o[0]}

        return {
            "total_signals": total,
            "long_signals": long_count,
            "short_signals": short_count,
            "live_signals": live_count,
            "test_signals": test_count,
            "signals_by_pair": pairs_dict,
            "outcomes": outcomes_dict,
        }
