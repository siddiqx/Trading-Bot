"""Telegram notification service and message formatting."""

from typing import Dict, Any, Optional, Tuple
import html
import httpx
from app.config import get_settings
from app.utils.logging import logger


class TelegramService:
    """Service to handle Telegram notification delivery and formatting."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout: float = 10.0,
    ):
        settings = get_settings()
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID
        self.timeout = timeout
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    @property
    def is_configured(self) -> bool:
        """Check whether telegram bot credentials are configured."""
        return bool(
            self.bot_token
            and self.chat_id
            and self.bot_token != "mock_or_real_telegram_token"
            and self.chat_id != "mock_or_real_chat_id"
            and not self.bot_token.startswith("your_")
        )

    def format_signal_message(self, signal: Dict[str, Any]) -> str:
        """Format signal data into professional Telegram HTML message."""
        direction = str(signal.get("direction", "")).upper()
        symbol = html.escape(str(signal.get("symbol", "")))
        strategy_name = html.escape(str(signal.get("strategy", "Adaptive Trend-Momentum Breakout")))
        score = signal.get("signal_score", 0)
        timeframe = html.escape(str(signal.get("timeframe", "60")))
        htf_regime = html.escape(str(signal.get("htf_regime", "NEUTRAL")))
        adx = signal.get("adx", 0.0)
        roc = signal.get("roc", 0.0)
        atr = signal.get("atr", 0.0)
        donchian_length = signal.get("breakout_length", 20)
        entry = signal.get("entry", 0.0)
        stop_loss = signal.get("stop_loss", 0.0)
        take_profit = signal.get("take_profit", 0.0)
        risk_reward = signal.get("risk_reward", 2.0)
        signal_time = html.escape(str(signal.get("signal_time", "N/A")))
        strategy_version = html.escape(str(signal.get("strategy_version", "1.0.0")))
        is_test = str(signal.get("environment", "")).upper() == "TEST"

        icon = "🟢" if direction == "LONG" else "🔴"
        test_banner = "⚠️ <b>[TEST SIGNAL - SIMULATED ENVIRONMENT]</b>\n" if is_test else ""

        # Formatting values safely with dynamic precision for Gold vs FX
        is_gold = "XAU" in symbol.upper() or (isinstance(entry, (int, float)) and entry > 500)
        dec_fmt = ".2f" if is_gold else ".5f"

        entry_str = f"{float(entry):{dec_fmt}}" if isinstance(entry, (int, float)) else str(entry)
        sl_str = f"{float(stop_loss):{dec_fmt}}" if isinstance(stop_loss, (int, float)) else str(stop_loss)
        tp_str = f"{float(take_profit):{dec_fmt}}" if isinstance(take_profit, (int, float)) else str(take_profit)
        adx_str = f"{float(adx):.2f}" if isinstance(adx, (int, float)) else str(adx)
        roc_str = f"{float(roc):+.2f}%" if isinstance(roc, (int, float)) else str(roc)
        atr_str = f"{float(atr):{dec_fmt}}" if isinstance(atr, (int, float)) else str(atr)
        score_val = int(score) if isinstance(score, (int, float)) else score
        body_ratio = signal.get("candle_body_ratio")
        body_str = f" • Body Quality: <b>{float(body_ratio)*100:.0f}% Solid</b>\n" if body_ratio is not None else ""

        suggested_lots = signal.get("suggested_lots")
        risk_pct = signal.get("risk_percent", 1.0)
        lot_str = f"• Sizing ({risk_pct}% Risk): <b>{float(suggested_lots):.2f} Lots</b>\n" if suggested_lots is not None else ""
        inter_regime = signal.get("intermediate_regime")
        entry_type = signal.get("entry_type", "MOMENTUM_BREAKOUT")

        entry_min = signal.get("entry_range_min")
        entry_max = signal.get("entry_range_max")
        if entry_min is not None and entry_max is not None:
            min_fmt = f"{float(entry_min):{dec_fmt}}"
            max_fmt = f"{float(entry_max):{dec_fmt}}"
            entry_range_str = f"• Optimal Entry Range: <code>{min_fmt} – {max_fmt}</code>\n"
        else:
            entry_range_str = ""

        rsi_val = signal.get("rsi")
        rsi_str = f" | RSI <code>{float(rsi_val):.1f}</code>" if rsi_val is not None else ""

        if inter_regime:
            regime_section = (
                f"<b>MULTI-TIMEFRAME ANALYSIS</b>\n"
                f"• Signal Timeframe: <b>1H (60m Anchor)</b>\n"
                f"• Execution View: <b>{timeframe}m Chart</b>\n"
                f"• 4H Trend: <code>{htf_regime}</code>\n"
                f"• 1H ADX(14): <code>{adx_str}</code>\n"
                f"• Momentum ROC: <code>{roc_str}</code>{rsi_str}\n\n"
            )
        else:
            regime_section = (
                f"<b>MARKET REGIME</b>\n"
                f"• 4H Trend: <code>{htf_regime}</code>\n"
                f"• 1H ADX(14): <code>{adx_str}</code>\n"
                f"• Momentum ROC: <code>{roc_str}</code>{rsi_str}\n\n"
            )

        ob_high = signal.get("order_block_high")
        ob_low = signal.get("order_block_low")
        f50 = signal.get("fib_50")
        f618 = signal.get("fib_618")
        fib_tp = signal.get("fib_ext_tp")

        smc_lines = []
        if ob_high is not None and ob_low is not None:
            smc_lines.append(f"• Origin Order Block (OB): <code>{float(ob_low):{dec_fmt}} – {float(ob_high):{dec_fmt}}</code>\n")
        if f50 is not None and f618 is not None:
            smc_lines.append(f"• Fib OTE (50% – 61.8%): <code>{float(f618):{dec_fmt}} – {float(f50):{dec_fmt}}</code>\n")
        if fib_tp is not None:
            smc_lines.append(f"• Fib Extension TP Target: <code>{float(fib_tp):{dec_fmt}}</code>\n")
        smc_section = "".join(smc_lines)

        targets_header = "ORDER BLOCK & FIBONACCI TARGETS" if smc_section else "REFINED ENTRY & RISK TARGETS"

        message = (
            f"{test_banner}"
            f"{icon} <b>{symbol} {direction} (1H Signal)</b>\n"
            f"<i>{strategy_name}</i>\n"
            f"<b>Signal Quality:</b> {score_val}/100\n\n"
            f"{regime_section}"
            f"<b>{targets_header}</b>\n"
            f"{smc_section}"
            f"{entry_range_str}"
            f"• Ideal Entry: <code>{entry_str}</code>\n"
            f"• Stop Loss: <code>{sl_str}</code>\n"
            f"• Take Profit: <code>{tp_str}</code>\n"
            f"• Risk/Reward: <code>1:{risk_reward}</code>\n"
            f"{lot_str}"
            f"• ATR(14): <code>{atr_str}</code>\n\n"
            f"<b>METADATA</b>\n"
            f"• Signal Time: <code>{signal_time}</code>\n"
            f"• Strategy Version: <code>v{strategy_version}</code>\n\n"
            f"ℹ️ <i>1H Confirmed signal with Order Block & Fib OTE confluence. Follow strict 1% risk management.</i>"
        )
        return message

    async def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: str = "HTML",
    ) -> Tuple[bool, Optional[int]]:
        """Send message via Telegram Bot HTTP API."""
        target_chat = chat_id or self.chat_id
        if not self.is_configured:
            logger.info("Telegram not configured or in mock mode. Signal message logged instead of transmitted.")
            return True, 999999

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    message_id = data.get("result", {}).get("message_id")
                    logger.info(f"Telegram message delivered successfully. Message ID: {message_id}")
                    return True, message_id
                else:
                    logger.error(
                        f"Telegram API responded with status {response.status_code}: {response.text}"
                    )
                    return False, None
        except Exception as e:
            logger.error(f"Unexpected exception while communicating with Telegram API: {type(e).__name__}: {str(e)}")
            return False, None

    async def send_signal(self, signal_data: Dict[str, Any]) -> Tuple[bool, Optional[int]]:
        """Format and send signal notification."""
        message = self.format_signal_message(signal_data)
        return await self.send_message(message)

    def generate_command_response(
        self,
        command: str,
        stats: Optional[Dict[str, Any]] = None,
        last_signal: Optional[Any] = None,
    ) -> str:
        """Generate response text for Telegram bot slash commands."""
        cmd = command.strip().lower()

        if cmd in ["/start", "/help"]:
            return (
                "🤖 <b>Forex Live Signal Bot v1.0.0</b>\n\n"
                "<b>Available Commands:</b>\n"
                "• /status - Health and database operational status\n"
                "• /last - Most recent confirmed signal\n"
                "• /stats - Live forward-testing statistics\n"
                "• /strategy - Strategy architecture and rule summary\n"
                "• /help - Display this command overview\n\n"
                "<i>Evidence-based forward-testing. No fabricated win rates.</i>"
            )

        elif cmd == "/strategy":
            return (
                "📈 <b>Adaptive Trend-Momentum Breakout Strategy</b>\n\n"
                "• <b>Primary Timeframe:</b> 1H (Execution)\n"
                "• <b>Higher Timeframe:</b> 4H (EMA 200 Regime Filter)\n"
                "• <b>Trend Filter:</b> 4H Close vs EMA 200 + Positive/Negative Slope\n"
                "• <b>Regime Filter:</b> ADX(14) ≥ 18 (Trend strength)\n"
                "• <b>Momentum:</b> ROC(20) > 0 (Long) / ROC(20) &lt; 0 (Short)\n"
                "• <b>Breakout:</b> 20-bar Donchian channel (strictly completed bars)\n"
                "• <b>Risk Model:</b> SL = 1.75 × ATR(14), TP = 2.0R\n"
                "• <b>Execution:</b> Confirmed bar close only (Non-repainting)\n"
            )

        elif cmd == "/status":
            last_sig_text = "None"
            if last_signal:
                last_sig_text = f"{last_signal.symbol} {last_signal.direction} at {last_signal.received_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            return (
                "⚡ <b>System Operational Status</b>\n\n"
                "• <b>Bot Service:</b> Online (FastAPI)\n"
                "• <b>Database:</b> SQLite (Connected & Healthy)\n"
                "• <b>Execution Mode:</b> Confirmed Bar Webhook\n"
                f"• <b>Last Recorded Signal:</b> <code>{last_sig_text}</code>\n"
                f"• <b>Telegram Dispatch:</b> {'Configured' if self.is_configured else 'Mock / Unconfigured'}\n"
            )

        elif cmd == "/last":
            if not last_signal:
                return "ℹ️ No trading signals have been logged yet."
            return (
                f"📌 <b>Most Recent Signal:</b>\n\n"
                f"• <b>Instrument:</b> {last_signal.symbol}\n"
                f"• <b>Direction:</b> {last_signal.direction}\n"
                f"• <b>Entry:</b> {last_signal.entry}\n"
                f"• <b>Stop Loss:</b> {last_signal.stop_loss}\n"
                f"• <b>Take Profit:</b> {last_signal.take_profit}\n"
                f"• <b>Risk/Reward:</b> 1:{last_signal.risk_reward}\n"
                f"• <b>Score:</b> {last_signal.signal_score}/100\n"
                f"• <b>Timestamp:</b> {last_signal.received_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                f"• <b>Environment:</b> {last_signal.environment}\n"
            )

        elif cmd == "/stats":
            if not stats:
                return "ℹ️ No statistics available."
            total = stats.get("total_signals", 0)
            longs = stats.get("long_signals", 0)
            shorts = stats.get("short_signals", 0)
            live = stats.get("live_signals", 0)
            pairs = stats.get("signals_by_pair", {})
            pair_lines = "\n".join([f"  • {k}: {v}" for k, v in pairs.items()]) or "  • None"

            return (
                "📊 <b>Forward-Testing Performance Metrics</b>\n\n"
                f"• <b>Total Signals Recorded:</b> {total}\n"
                f"• <b>Long Signals:</b> {longs}\n"
                f"• <b>Short Signals:</b> {shorts}\n"
                f"• <b>Live Environment Signals:</b> {live}\n\n"
                f"<b>Signals by Currency Pair:</b>\n{pair_lines}\n\n"
                "<i>Note: Forward profitability metrics (win rate, profit factor, expectancy) "
                "require sufficient live sample size before statistical reporting.</i>"
            )

        return "Unknown command. Type /help to see available commands."

    async def run_polling(self, stop_event):
        """Continuously poll Telegram for user commands (/status, /last, /stats, /help, /strategy)."""
        import asyncio
        if not self.is_configured:
            logger.info("Telegram not configured. Polling listener skipped.")
            return

        logger.info("Starting Telegram bot command polling listener...")
        offset = 0
        timeout = 5
        url = f"{self.base_url}/getUpdates"

        async with httpx.AsyncClient(timeout=timeout + 5) as client:
            while not stop_event.is_set():
                try:
                    res = await client.get(f"{url}?offset={offset}&timeout={timeout}")
                    if res.status_code == 200:
                        updates = res.json().get("result", [])
                        for update in updates:
                            update_id = update.get("update_id", 0)
                            offset = max(offset, update_id + 1)
                            message = update.get("message", {})
                            text = message.get("text", "").strip()
                            chat_id = str(message.get("chat", {}).get("id", ""))

                            if text.startswith("/"):
                                logger.info(f"Telegram command received: {text} from chat_id={chat_id}")
                                from app.database.database import SessionLocal
                                from app.database.repository import SignalRepository

                                db = SessionLocal()
                                try:
                                    stats = SignalRepository.get_stats(db)
                                    last_sig = SignalRepository.get_latest_signal(db)
                                finally:
                                    db.close()

                                reply = self.generate_command_response(text, stats, last_sig)
                                await self.send_message(reply, chat_id=chat_id)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.debug(f"Polling exception: {e}")
                    await asyncio.sleep(2)

                await asyncio.sleep(0.5)

        logger.info("Telegram bot command polling listener stopped.")
