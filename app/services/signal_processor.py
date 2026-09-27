"""Signal processing orchestrator managing validation, deduplication, persistence, and alerts."""

from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.config import Settings
from app.schemas.signal import SignalPayload, SignalResponse
from app.database.repository import SignalRepository
from app.services.validation import SignalValidator
from app.services.telegram import TelegramService
from app.utils.security import verify_webhook_secret
from app.utils.logging import logger


class SignalProcessor:
    """Core processor coordinating incoming alerts."""

    def __init__(self, settings: Settings, telegram_service: TelegramService):
        self.settings = settings
        self.telegram_service = telegram_service
        self.validator = SignalValidator(settings)

    async def process_signal(self, payload: SignalPayload, db: Session) -> SignalResponse:
        """Process incoming signal payload safely and quickly."""
        # 1. Security Check: Authenticate webhook secret
        if not verify_webhook_secret(payload.webhook_secret, self.settings.WEBHOOK_SECRET):
            logger.warning(f"Unauthorized webhook attempt rejected for symbol={payload.symbol}")
            return SignalResponse(
                status="UNAUTHORIZED",
                message="Invalid or missing webhook secret.",
                signal_id=None,
                telegram_delivered=False,
            )

        logger.info(
            f"Webhook received: {payload.symbol} {payload.direction} "
            f"at {payload.entry} (Signal ID: {payload.signal_id}, Env: {payload.environment})"
        )

        # 2. Duplicate Protection (Idempotency)
        existing = SignalRepository.get_by_signal_id(db, payload.signal_id)
        if existing:
            logger.warning(
                f"Duplicate signal detected and ignored: signal_id={payload.signal_id} "
                f"already received at {existing.received_at}"
            )
            return SignalResponse(
                status="DUPLICATE_IGNORED",
                message="Duplicate signal event. Already processed previously.",
                signal_id=payload.signal_id,
                telegram_delivered=existing.telegram_sent,
            )

        # 3. Strategy & Filter Validation
        is_valid, reason = self.validator.validate(payload)
        if not is_valid:
            logger.warning(f"Signal rejected by strategy filters: {reason}")
            return SignalResponse(
                status="REJECTED",
                message=reason,
                signal_id=payload.signal_id,
                telegram_delivered=False,
            )

        # 4. Database Persistence
        signal_dict = payload.model_dump()
        saved_signal = SignalRepository.create_signal(db, signal_dict)
        logger.info(f"Signal successfully accepted and logged to database: id={saved_signal.id}")

        # 5. Telegram Notification
        sent, message_id = await self.telegram_service.send_signal(signal_dict)
        if sent:
            logger.info(f"Telegram notification dispatched for signal_id={payload.signal_id}")
            SignalRepository.update_telegram_status(db, payload.signal_id, sent=True, message_id=message_id)
        else:
            logger.error(f"Failed to dispatch Telegram notification for signal_id={payload.signal_id}")

        return SignalResponse(
            status="ACCEPTED",
            message="Signal verified, stored, and notification dispatched.",
            signal_id=payload.signal_id,
            telegram_delivered=sent,
        )
