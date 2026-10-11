"""Telegram notification service and message formatting."""

from typing import Dict, Any, Optional, Tuple
import html
import json
from pathlib import Path
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

        # Formatting values safely with dynamic precision for JPY vs non-JPY Forex
        is_jpy = "JPY" in symbol.upper()
        dec_fmt = ".3f" if is_jpy else ".5f"

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

        tf_label = (
            f"{timeframe}m"
            if str(timeframe).isdigit() and int(timeframe) < 60
            else ("1H" if str(timeframe) in ["60", "1H"] else str(timeframe))
        )

        message = (
            f"{test_banner}"
            f"{icon} <b>{symbol} {direction} ({tf_label} Signal)</b>\n"
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
            f"ℹ️ <i>MTF Confirmed signal (1H Trend + {tf_label} Entry) with Order Block & Fib OTE confluence. Follow strict 1% risk management.</i>"
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

    def _load_trade_records(self) -> Dict[str, Any]:
        """Load trade ledger records from trade_records.json, strictly sanitizing gold symbols."""
        raw = {"tracking_started": "2026-10-11", "active_trades": {}, "completed_trades": []}
        for candidate in [Path("trade_records.json"), Path(__file__).resolve().parents[2] / "trade_records.json"]:
            if candidate.exists():
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                        break
                except Exception:
                    pass
        clean_active = {
            k: v for k, v in raw.get("active_trades", {}).items()
            if not any(g in (v.get("pair") or v.get("symbol") or k).upper() for g in ["XAU", "GOLD"])
        }
        clean_completed = [
            t for t in raw.get("completed_trades", [])
            if not any(g in (t.get("pair") or t.get("symbol") or "").upper() for g in ["XAU", "GOLD"])
        ]
        return {
            "tracking_started": raw.get("tracking_started", "2026-10-11"),
            "active_trades": clean_active,
            "completed_trades": clean_completed,
        }

    def generate_command_response(
        self,
        command: str,
        stats: Optional[Dict[str, Any]] = None,
        last_signal: Optional[Any] = None,
    ) -> str:
        """Generate response text for Telegram bot slash commands."""
        parts = command.strip().split()
        cmd = parts[0].lower().split("@")[0] if parts else ""
        records = self._load_trade_records()
        active_trades = records.get("active_trades", {})
        completed_trades = records.get("completed_trades", [])

        if cmd in ["/start", "/help", "/menu"]:
            return (
                "🤖 <b>Institutional Forex Live Signal Bot v4.0</b>\n\n"
                "<b>Available Commands:</b>\n"
                "• /active - Currently running trades & floating positions\n"
                "• /radar - 6-Asset institutional surveillance radar\n"
                "• /prices - Live market quotes table\n"
                "• /history - Completed trade ledger history\n"
                "• /performance - Live forward-testing performance metrics\n"
                "• /strategy - Strategy architecture and rule summary\n"
                "• /status - Health and database operational status\n"
                "• /patterns - Volume trade analytics & failure analysis\n"
                "• /last - Most recent confirmed signal\n"
                "• /help - Display this command overview\n\n"
                "<i>ICT Killzone Liquidity Sweep Model with fixed 15-pip TP and 10-pip SL. Evidence-based execution across 6 institutional Forex pairs. Zero Gold.</i>"
            )

        elif cmd in ["/strategy", "/rules"]:
            return (
                "📈 <b>ICT Killzone Liquidity Sweep Model (v4.0) — Institutional Forex Strategy</b>\n\n"
                "• <b>Evolution:</b> Upgraded from Two-Phase Pullback Engine and Donchian Breakout Impulse to verified ICT liquidity sweeps.\n"
                "• <b>Monitored Assets:</b> 6 Forex Pairs (EURUSD, USDCAD, GBPUSD, USDJPY, USDCHF, AUDUSD — Zero Gold)\n"
                "• <b>Execution Timeframe:</b> 15M Chart within London (07:00–10:00 UTC) & NY (12:00–15:00 UTC) Killzones\n"
                "• <b>Anchor Timeframe:</b> 1H Trend Agreement (EMA20 vs EMA50)\n"
                "• <b>Liquidity Sweep:</b> Sweeps Asian Range (00:00–06:00 UTC) or 10-bar fractal swing by ≥1.0 pip with immediate displacement reclaim\n"
                "• <b>Take Profit:</b> Fixed 15 Pips from entry price\n"
                "• <b>Stop Loss:</b> Fixed 10 Pips from entry price\n"
                "• <b>Risk/Reward Ratio:</b> Fixed 1:1.5 before transaction costs\n"
                "• <b>Capital Protection:</b> $25.00 / trade (0.50% on $5,000 account · 0.25 Lots)\n"
                "• <b>Execution:</b> Confirmed bar close only (100% Non-repainting)\n"
            )

        elif cmd in ["/active", "/open", "/trades", "/positions"]:
            if not active_trades:
                return (
                    "⚡ <b>ACTIVE LIVE TRADES (0)</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "<i>No active positions currently running.</i>\n\n"
                    "Institutional 6-Asset Universe under active surveillance:\n"
                    "<code>EURUSD · USDCAD · GBPUSD · USDJPY · USDCHF · AUDUSD</code>\n\n"
                    "Signals trigger strictly on confirmed candle closes."
                )

            rows = []
            for idx, (k, t) in enumerate(active_trades.items(), 1):
                sym = t.get("symbol") or t.get("pair") or k
                direction = t.get("direction", "LONG")
                icon = "🟢" if direction == "LONG" else "🔴"
                entry = t.get("entry")
                sl = t.get("stop_loss")
                tp = t.get("take_profit")
                rr = t.get("rr", 2.0)
                opened = t.get("opened_at", "N/A")
                status = t.get("status", "OPEN")
                be_tag = " 🛡<b>BE Locked</b>" if t.get("be_active") else ""
                partial_tag = " 💰<b>+0.50R Banked</b>" if t.get("partial_taken") else ""
                rows.append(
                    f"<b>{idx}. {sym}</b> · {icon} <b>{direction}</b> ({t.get('timeframe', '15M')})\n"
                    f"• Status: <code>{status}</code>{be_tag}{partial_tag}\n"
                    f"• Entry: <code>{entry}</code>\n"
                    f"• SL: <code>{sl}</code> | TP: <code>{tp}</code> (1:{rr}R)\n"
                    f"• Opened: <code>{opened}</code>"
                )

            return (
                f"⚡ <b>ACTIVE LIVE TRADES ({len(active_trades)})</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n" +
                "\n\n".join(rows) + "\n\n" +
                "━━━━━━━━━━━━━━━━━━"
            )

        elif cmd == "/status":
            last_sig_text = "None"
            if last_signal:
                last_sig_text = f"{last_signal.symbol} {last_signal.direction} at {last_signal.received_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            elif completed_trades:
                lt = completed_trades[-1]
                last_sig_text = f"{lt.get('symbol', '')} {lt.get('direction', '')} ({lt.get('outcome', '')})"
            elif active_trades:
                at = next(iter(active_trades.values()))
                last_sig_text = f"{at.get('symbol', '')} {at.get('direction', '')} (RUNNING)"

            return (
                "⚡ <b>System Operational Status</b>\n\n"
                "• <b>Engine Core:</b> Online (v3.1 Two-Phase Pullback Engine)\n"
                "• <b>TP/SL Model:</b> Fixed 15-Pip TP / 10-Pip SL (1:1.5 RR)\n"
                "• <b>Eligible Universe:</b> 6 Forex Pairs (Zero Gold)\n"
                "• <b>Active Positions:</b> <code>" + str(len(active_trades)) + " locked</code>\n"
                "• <b>Recorded Trades:</b> <code>" + str(len(completed_trades)) + " closed</code>\n"
                "• <b>Execution Mode:</b> Confirmed Bar Close\n"
                f"• <b>Last Recorded Signal:</b> <code>{last_sig_text}</code>\n"
                f"• <b>Telegram Dispatch:</b> {'Configured' if self.is_configured else 'Mock / Unconfigured'}\n"
                f"• <b>Baseline:</b> <code>2026-10-08</code> (Strategy Reset — Fresh Start)\n"
            )

        elif cmd == "/last":
            if last_signal:
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
            if active_trades:
                at = next(iter(active_trades.values()))
                return (
                    f"📌 <b>Most Recent Active Signal:</b>\n\n"
                    f"• <b>Instrument:</b> {at.get('symbol', at.get('pair'))}\n"
                    f"• <b>Direction:</b> {at.get('direction')}\n"
                    f"• <b>Entry:</b> {at.get('entry')}\n"
                    f"• <b>Stop Loss:</b> {at.get('stop_loss')}\n"
                    f"• <b>Take Profit:</b> {at.get('take_profit')}\n"
                    f"• <b>Risk/Reward:</b> 1:{at.get('rr', 2.0)}\n"
                    f"• <b>Opened:</b> {at.get('opened_at')}\n"
                    f"• <b>Status:</b> {at.get('status')}\n"
                )
            if completed_trades:
                ct = completed_trades[-1]
                return (
                    f"📌 <b>Most Recent Closed Signal:</b>\n\n"
                    f"• <b>Instrument:</b> {ct.get('symbol', ct.get('pair'))}\n"
                    f"• <b>Direction:</b> {ct.get('direction')}\n"
                    f"• <b>Entry:</b> {ct.get('entry')}\n"
                    f"• <b>Exit Price:</b> {ct.get('exit_price')}\n"
                    f"• <b>Outcome:</b> {ct.get('outcome')}\n"
                    f"• <b>Realized:</b> {ct.get('realized_pips')} pips ({ct.get('realized_r')}R)\n"
                    f"• <b>Closed:</b> {ct.get('closed_at')}\n"
                )
            return "ℹ️ No trading signals have been logged yet."

        elif cmd in ["/performance", "/stats"]:
            # Backwards-compatibility for tests passing stats dict
            if stats and "total_signals" in stats:
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

            # Authoritative calculation from trade_records.json
            filter_pair = parts[1].upper().replace("/", "") if len(parts) > 1 else "ALL"
            closed = [t for t in completed_trades if filter_pair in ["ALL", (t.get("symbol") or "").upper()]]
            active_list = [t for t in active_trades.values() if filter_pair in ["ALL", (t.get("symbol") or "").upper()]]

            wins = len([t for t in closed if t.get("outcome") == "WIN"])
            losses = len([t for t in closed if t.get("outcome") == "LOSS"])
            be_count = len([t for t in closed if t.get("outcome") == "BREAK_EVEN"])
            cancelled = len([t for t in closed if t.get("outcome") == "CANCELLED"])
            decided = wins + losses

            win_rate = f"{(wins / decided) * 100:.1f}%" if decided > 0 else "N/A"
            net_pips = sum(float(t.get("realized_pips") or 0.0) for t in closed)
            net_r = sum(float(t.get("realized_r") or 0.0) for t in closed)

            gross_wins = sum(float(t.get("realized_pips") or 0.0) for t in closed if float(t.get("realized_pips") or 0.0) > 0)
            gross_losses = sum(abs(float(t.get("realized_pips") or 0.0)) for t in closed if float(t.get("realized_pips") or 0.0) < 0)

            if gross_losses > 0:
                pf = f"{gross_wins / gross_losses:.2f}"
            elif gross_wins > 0:
                pf = "MAX (0 Loss)"
            else:
                pf = "N/A"

            expectancy = f"{net_r / (decided + be_count):+.3f} R" if (decided + be_count) > 0 else "N/A"
            pips_sign = "+" if net_pips >= 0 else ""
            r_sign = "+" if net_r >= 0 else ""

            return (
                "📈 <b>STRATEGY PERFORMANCE (v3.1 ICT Liquidity Sweep)</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"Scope: <b>{filter_pair}</b>\n"
                "Baseline: <code>2026-10-08</code> (Fresh Start — Strategy Reset)\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "<b>1. TRADE EXECUTION</b>\n"
                f"• Total Closed: <code>{len(closed)}</code>\n"
                f"• Active Live: <code>{len(active_list)} positions</code>\n"
                f"• Win / Loss / BE: <b>{wins}W</b> · <b>{losses}L</b>" + (f" · <b>{be_count} BE</b>" if be_count else "") + "\n"
                f"• Win Rate: <b>{win_rate}</b>\n\n"
                "<b>2. RETURNS & PROFITABILITY</b>\n"
                f"• Net Realized Pips: <b>{pips_sign}{net_pips:.1f} pips</b>\n"
                f"• Net Realized Return: <b>{r_sign}{net_r:.2f} R</b>\n"
                f"• Expectancy / Trade: <b>{expectancy}</b>\n"
                f"• Profit Factor: <code>{pf}</code>\n"
                "• Target R:R: <code>1:1.5 (Fixed 15-Pip TP / 10-Pip SL)</code>\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "⚡ <i>100% out-of-sample forward verification. Baseline reset 2026-10-08.</i>"
            )

        elif cmd == "/history":
            if not completed_trades:
                return (
                    "📜 <b>COMPLETED TRADE HISTORY</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "<i>No completed trades logged in live forward ledger yet.</i>"
                )

            rows = []
            for idx, t in enumerate(completed_trades[-10:], 1):
                sym = t.get("symbol") or t.get("pair") or "TRADE"
                outcome = t.get("outcome", "CLOSED")
                pips = t.get("realized_pips", 0.0)
                r = t.get("realized_r", 0.0)
                sign = "+" if float(pips) >= 0 else ""
                r_sign = "+" if float(r) >= 0 else ""
                rows.append(
                    f"<b>{idx}. {sym}</b> · {t.get('direction', '')} · <b>{outcome}</b>\n"
                    f"• Entry: <code>{t.get('entry')}</code> ➔ Exit: <code>{t.get('exit_price')}</code>\n"
                    f"• Net: <b>{sign}{pips} pips / {r_sign}{r} R</b> · <code>{t.get('closed_at', '')[:10]}</code>"
                )

            return (
                f"📜 <b>COMPLETED TRADE HISTORY ({len(completed_trades)} Total)</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n" +
                "\n\n".join(rows) + "\n\n" +
                "━━━━━━━━━━━━━━━━━━"
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
