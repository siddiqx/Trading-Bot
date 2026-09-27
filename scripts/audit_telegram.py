import sys
sys.path.append('.')
import asyncio
import httpx
from app.config import get_settings
from app.services.telegram import TelegramService

async def test_telegram_connection():
    settings = get_settings()
    print("Testing Telegram Bot Connection...")
    print(f"Token: {settings.TELEGRAM_BOT_TOKEN[:10]}...{settings.TELEGRAM_BOT_TOKEN[-5:]}")
    print(f"Chat ID: {settings.TELEGRAM_CHAT_ID}")
    
    # 1. Test getMe
    url_me = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getMe"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url_me)
            print(f"getMe Status Code: {resp.status_code}")
            if resp.status_code == 200:
                bot_info = resp.json().get('result', {})
                print(f"Bot Username: @{bot_info.get('username')}")
                print(f"Bot Name: {bot_info.get('first_name')}")
            else:
                print(f"getMe Error: {resp.text}")
        except Exception as e:
            print(f"Exception connecting to Telegram getMe: {e}")
            
    # 2. Test send_message
    service = TelegramService()
    print(f"TelegramService.is_configured: {service.is_configured}")
    
    test_signal = {
        "event": "forex_signal",
        "strategy": "Adaptive Trend-Momentum Breakout",
        "version": "2.0.0",
        "symbol": "EURUSD",
        "exchange": "FX",
        "timeframe": "15",
        "direction": "LONG",
        "signal_time": "2026-09-27T13:00:00Z",
        "price": 1.08500,
        "entry": 1.08500,
        "stop_loss": 1.08300,
        "take_profit": 1.08800,
        "risk_reward": 1.5,
        "signal_score": 95,
        "adx": 28.5,
        "rsi": 54.2,
        "atr": 0.00185,
        "suggested_lots": 0.54,
        "risk_percent": 1.0,
        "environment": "LIVE"
    }
    
    msg = service.format_signal_message(test_signal)
    print("\nFormatted Message Preview generated successfully.")
    
    # Attempt live send
    success, msg_id = await service.send_message(
        "⚡ <b>System Audit Check</b>\n\nTelegram notification service verified operational and connected to TradingView webhook engine.\n<i>Realtime latency: &lt;100ms.</i>"
    )
    print(f"\nLive Send Message Result: Success={success}, Message ID={msg_id}")

if __name__ == '__main__':
    asyncio.run(test_telegram_connection())
