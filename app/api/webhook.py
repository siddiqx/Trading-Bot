"""TradingView and Telegram Webhook API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.config import get_settings, Settings
from app.database.database import get_db
from app.schemas.signal import SignalPayload, SignalResponse
from app.services.telegram import TelegramService
from app.services.signal_processor import SignalProcessor
from app.database.repository import SignalRepository

router = APIRouter(prefix="/webhook", tags=["Webhooks"])


def get_signal_processor(settings: Settings = Depends(get_settings)) -> SignalProcessor:
    telegram_service = TelegramService(
        bot_token=settings.TELEGRAM_BOT_TOKEN,
        chat_id=settings.TELEGRAM_CHAT_ID,
    )
    return SignalProcessor(settings=settings, telegram_service=telegram_service)


@router.post(
    "/tradingview",
    response_model=SignalResponse,
    status_code=status.HTTP_200_OK,
    summary="Receive TradingView alert webhook",
)
async def receive_tradingview_signal(
    payload: SignalPayload,
    processor: SignalProcessor = Depends(get_signal_processor),
    db: Session = Depends(get_db),
):
    """Receive, authenticate, deduplicate, store, and broadcast real-time TradingView signals."""
    result = await processor.process_signal(payload, db)

    if result.status == "UNAUTHORIZED":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.message,
        )

    return result


@router.get(
    "/stats",
    summary="Get current forward-testing signal statistics",
)
def get_signal_statistics(db: Session = Depends(get_db)):
    """Retrieve forward-testing database statistics."""
    return SignalRepository.get_stats(db)


@router.get(
    "/last",
    summary="Get the most recent signal",
)
def get_last_signal(db: Session = Depends(get_db)):
    """Retrieve the most recent signal."""
    signal = SignalRepository.get_latest_signal(db)
    if not signal:
        return {"status": "empty", "message": "No signals recorded yet."}
    return signal


@router.post(
    "/telegram",
    summary="Receive Telegram Bot Webhook Updates for slash commands",
)
async def receive_telegram_update(
    update: dict,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Handle incoming Telegram commands (/status, /last, /stats, /help, /strategy)."""
    message = update.get("message", {})
    text = message.get("text", "").strip()
    chat_id = str(message.get("chat", {}).get("id", ""))

    if text.startswith("/"):
        telegram_service = TelegramService(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            chat_id=chat_id or settings.TELEGRAM_CHAT_ID,
        )
        stats = SignalRepository.get_stats(db)
        last_sig = SignalRepository.get_latest_signal(db)
        reply_text = telegram_service.generate_command_response(text, stats, last_sig)
        await telegram_service.send_message(reply_text, chat_id=chat_id)
        return {"ok": True}

    return {"ok": True}
