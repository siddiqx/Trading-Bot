"""
Standalone 24/7 Cloud Market Scanner for Forex & Gold
Tracks EURUSD, USDJPY, USDCAD, USDCHF, AUDUSD, and XAUUSD on 15M and 1H timeframes.
Zero external server or TradingView subscription needed.
"""

import sys
import os
import time
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import httpx
import numpy as np
import pandas as pd
from core.post_mortem import record_trade_post_mortem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MarketScanner")

# Telegram Bot Credentials — loaded strictly from environment variables.
# NEVER hardcode fallback values here: if env vars are missing in CI, fail loudly.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    # In CI: secrets must be set. In local dev: use a .env loader or export them.
    # We allow the scanner to run without them (signals logged only, not sent).
    logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set. Alerts will be logged only.")

# Monitored Pairs and Yahoo Finance Ticker Mapping
# Core Alpha Asset Universe (Proven by 2-year backtest to cap portfolio drawdown at 6.0% while maximizing net return)
# Asset universe trimmed to top-performers by forensic audit:
# EURUSD: 56.4% WR, 0.366R expectancy, 2.26 PF
# USDCAD: 65.9% WR, 0.402R expectancy, 2.20 PF
# XAUUSD: 42.9% WR, 0.319R expectancy, 1.72 PF
# GBPUSD (37.7% WR, 0.021R), USDJPY (-0.043R), USDCHF (-0.128R) — permanently excluded
SYMBOLS = {
    "XAUUSD": {"ticker": "PAXGUSDT", "pip": 0.10,   "digits": 2, "donchian_len": 10}, # 1:1 Physical Spot Gold (matches MT5 XAUUSD directly)
    "EURUSD": {"ticker": "EURUSD=X", "pip": 0.0001, "digits": 5, "donchian_len": 15}, # Best performer: 56.4% WR, 2.26 PF
    "USDCAD": {"ticker": "USDCAD=X", "pip": 0.0001, "digits": 5, "donchian_len": 15}, # Best performer: 65.9% WR, 2.20 PF
}

TIMEFRAMES = ["15m", "1h"]

STATE_FILE = "market_scanner_state.json"
TRADE_RECORDS_FILE = "trade_records.json"
WORKER_SYNC_URL = "https://tradingview-telegram-relay.siddiqsiddiq00012.workers.dev/"


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"alerted_signals": []}
    return {"alerted_signals": []}


def save_state(state):
    try:
        # Keep last 500 signal IDs to prevent file bloat while covering long-term dedup
        state["alerted_signals"] = state["alerted_signals"][-500:]
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving state: {e}")


def load_trade_records():
    if os.path.exists(TRADE_RECORDS_FILE):
        try:
            with open(TRADE_RECORDS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "tracking_started": "2026-09-28",
        "active_trades": {},
        "completed_trades": []
    }


def save_trade_records(records):
    try:
        with open(TRADE_RECORDS_FILE, "w") as f:
            json.dump(records, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving trade records: {e}")


def sync_worker(records):
    """Sync trade state to Cloudflare Worker KV. Retries once on transient failure."""
    try:
        volume_summary = None
        try:
            summary_path = Path(__file__).resolve().parent / "data" / "patterns" / "volumes" / "vol_01" / "volume_summary.json"
            if summary_path.exists():
                with open(summary_path, "r", encoding="utf-8") as f:
                    volume_summary = json.load(f)
        except Exception:
            pass

        payload = {
            "event": "sync_trades",
            "active_trades": records.get("active_trades", {}),
            "completed_trades": records.get("completed_trades", []),
            "volume_summary": volume_summary
        }
        for attempt in range(2):  # retry once on failure
            try:
                with httpx.Client(timeout=10.0) as client:
                    r = client.post(WORKER_SYNC_URL, json=payload, headers={"User-Agent": "MarketScanner/2.0"})
                    if r.status_code == 200:
                        logger.info("Worker sync successful.")
                        return
                    logger.warning(f"Worker sync returned {r.status_code} (attempt {attempt+1})")
            except Exception as req_e:
                logger.warning(f"Worker sync request error (attempt {attempt+1}): {req_e}")
            time.sleep(2)
    except Exception as e:
        logger.warning(f"Could not sync with worker: {e}")


def format_exit_message(
    trade: dict,
    outcome: str,
    exit_price: float,
    realized_pips: float,
    realized_r: float,
    post_mortem_record: dict = None
) -> str:
    is_win = outcome == "WIN"
    is_be = outcome == "BREAK_EVEN"
    icon = "🎯" if is_win else ("🛡️" if is_be else "🛑")
    header = "TARGET REACHED: LIQUIDITY POOL SWEPT" if is_win else ("CAPITAL PRESERVED: BREAK-EVEN EXIT" if is_be else "STRUCTURAL EXIT: STOP LOSS HIT")
    status_text = "WIN (Liquidity Pool Swept)" if is_win else ("BREAK-EVEN (Capital Protected at +1.0R)" if is_be else "LOSS (Order Block Invalidation)")
    sign = "+" if realized_pips >= 0 else ""
    r_sign = "+" if realized_r >= 0 else ""
    pair_name = trade.get('pair') or trade.get('symbol') or 'ASSET'

    vol_text = ""
    diag_text = ""
    if post_mortem_record:
        trk = post_mortem_record.get("tracking", {})
        vol_trade = trk.get("volume_trade_no", 1)
        global_trade = trk.get("global_trade_no", 1)
        vol_num = trk.get("volume_no", 1)
        vol_text = f"📚 <b>Volume:</b> <b>Volume {vol_num} · Trade #{vol_trade}/100</b> (Global #{global_trade})\n"

        diag = post_mortem_record.get("diagnostic", {})
        ex = post_mortem_record.get("excursion_metrics", {})
        mfe_sign = "+" if ex.get("mfe_pips", 0) >= 0 else ""
        diag_text = (
            f"<b>🔬 POST-MORTEM DIAGNOSTIC</b>\n"
            f"• <b>Classification:</b> <code>{diag.get('primary_factor', 'STRUCTURAL_INVALIDATION')}</code>\n"
            f"• <b>Max Profit (MFE):</b> <code>{mfe_sign}{ex.get('mfe_pips', 0)} pips</code> ({ex.get('tp_distance_pct_reached', 0)}% of TP)\n"
            f"• <b>Drawdown (MAE):</b> <code>{ex.get('mae_pips', 0)} pips</code>\n"
            f"💡 <i>Insight: {diag.get('actionable_insight', '')}</i>\n\n"
        )

    return (
        f"{icon} <b>{header}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Asset:</b> <b>{pair_name}</b> ({trade.get('timeframe', '1H')})\n"
        f"🧭 <b>Position:</b> <b>{trade.get('direction', 'TRADE')} CLOSED</b>\n"
        f"{vol_text}"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📋 EXECUTION OUTCOME</b>\n"
        f"• <b>Entry Price:</b> <code>{trade.get('entry')}</code>\n"
        f"• <b>Exit Price:</b> <code>{exit_price}</code>\n"
        f"• <b>Net Realized:</b> <b>{sign}{realized_pips:.1f} pips</b>\n"
        f"• <b>Realized Return:</b> <b>{r_sign}{realized_r:.2f} R</b>\n"
        f"• <b>Outcome:</b> <b>{status_text}</b>\n\n"
        f"{diag_text}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕒 <b>Closed At:</b> <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</code>\n"
        f"🔓 <i>Pair unlocked. Surveillance resumed.</i>"
    )


def check_active_trades(records: dict):
    """Monitors live market prices against active trades for Take Profit and Stop Loss."""
    active = records.get("active_trades", {})
    if not active:
        return

    resolved_pairs = []
    modified_pairs = []

    for pair, trade in list(active.items()):
        ticker = trade.get("ticker")
        if not ticker:
            continue

        df = fetch_candles(ticker, "15m", range_days="2d")  # 2d is sufficient for monitoring, 7d is wasteful
        if df.empty:
            continue
        if len(df) >= 30:
            df = compute_indicators(df, donchian_len=SYMBOLS.get(pair, {}).get("donchian_len", 20))

        opened_at_str = trade.get("opened_at")
        if opened_at_str:
            try:
                open_ts = pd.to_datetime(opened_at_str)
                df_trade = df[df["time"] >= open_ts]
            except Exception:
                df_trade = df.iloc[-4:]
        else:
            df_trade = df.iloc[-4:]

        is_pending = (trade.get("status") == "PENDING")

        if df_trade.empty:
            # If no candle has opened >= open_ts yet, check if the latest available candle qualifies
            if not df.empty and df.iloc[-1]["time"] >= open_ts:
                df_trade = df.iloc[-1:]
            else:
                # If pending order has waited beyond timeout without new candle filling it, expire it
                if is_pending and open_ts:
                    now_curr = datetime.now(timezone.utc)
                    timeout_hours = 2.0 if trade.get("timeframe") == "15M" else 4.0
                    elapsed_hours = (now_curr - open_ts).total_seconds() / 3600.0
                    if elapsed_hours >= timeout_hours:
                        logger.info(f"==> SETUP EXPIRED (Unfilled after {elapsed_hours:.1f}h): {pair} {trade.get('direction')}")
                        completed_record = {
                            **trade,
                            "exit_price": float(trade.get("entry")),
                            "outcome": "EXPIRED_UNFILLED",
                            "realized_pips": 0.0,
                            "realized_r": 0.0,
                            "closed_at": now_curr.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "status": "EXPIRED"
                        }
                        msg = (
                            f"⌛ <b>SETUP EXPIRED (UNFILLED) · {pair} {trade.get('direction')}</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"• <b>Entry Target:</b> <code>{trade.get('entry')}</code>\n"
                            f"• <b>Time Elapsed:</b> <code>{elapsed_hours:.1f} hours</code> (exceeded {int(timeout_hours)}h session window)\n"
                            f"• <b>Reason:</b> Limit order remained unfilled. Market structure transitioned.\n"
                            f"• <b>Net Realized:</b> <b>0.0 pips / 0.00 R (Zero Loss)</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"🔓 <i>Pair unlocked. Surveillance resumed immediately.</i>"
                        )
                        send_telegram_alert(msg)
                        records.setdefault("completed_trades", []).append(completed_record)
                        del records["active_trades"][pair]
                        resolved_pairs.append(pair)
                continue

        is_long = (trade.get("direction") == "LONG")
        entry = trade["entry"]
        tp = trade["take_profit"]
        sl = trade["stop_loss"]
        is_pending = (trade.get("status") == "PENDING")

        hit_tp = False
        hit_sl = False
        hit_ema_exit = False
        ema_exit_price = None
        cancelled_before_fill = False

        # Chronological bar-by-bar evaluation to accurately determine order fill and exit triggers
        for row in df_trade.itertuples():
            b_high = row.high
            b_low = row.low

            if is_pending:
                if is_long:
                    # Invalidation: If price breaches SL before ever reaching entry, cancel order
                    if b_low <= sl:
                        cancelled_before_fill = True
                        break
                    # Fill execution: price touched or traded through entry price
                    elif b_low <= entry:
                        trade["status"] = "OPEN"
                        fill_time_str = row.time.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(row.time, "strftime") else str(row.time)
                        trade["filled_at"] = fill_time_str
                        is_pending = False
                        modified_pairs.append(pair)
                        logger.info(f"==> ORDER FILLED: {pair} LONG @ {entry} (Bar time: {fill_time_str})")

                        fill_msg = (
                            f"🎯 <b>ORDER FILLED · {pair} LONG</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"• <b>Fill Price:</b> <code>{entry}</code>\n"
                            f"• <b>Stop Loss:</b> <code>{sl}</code> <i>(-{trade.get('sl_pips', 0.0)} pips)</i>\n"
                            f"• <b>Take Profit:</b> <code>{tp}</code> <i>(+{trade.get('tp_pips', 0.0)} pips)</i>\n"
                            f"• <b>Risk / Reward:</b> <b>1 : {trade.get('rr', 1.75)}</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"🟢 <i>Order executed. Position is now actively floating in market.</i>"
                        )
                        send_telegram_alert(fill_msg)

                        # Evaluate if the remainder of this fill candle hit TP or SL
                        if b_high >= tp:
                            hit_tp = True
                            break
                        elif b_low <= sl:
                            hit_sl = True
                            break
                else:
                    # SHORT
                    # Invalidation: If price breaches SL before ever reaching entry, cancel order
                    if b_high >= sl:
                        cancelled_before_fill = True
                        break
                    # Fill execution: price touched or traded through entry price
                    elif b_high >= entry:
                        trade["status"] = "OPEN"
                        fill_time_str = row.time.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(row.time, "strftime") else str(row.time)
                        trade["filled_at"] = fill_time_str
                        is_pending = False
                        modified_pairs.append(pair)
                        logger.info(f"==> ORDER FILLED: {pair} SHORT @ {entry} (Bar time: {fill_time_str})")

                        fill_msg = (
                            f"🎯 <b>ORDER FILLED · {pair} SHORT</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"• <b>Fill Price:</b> <code>{entry}</code>\n"
                            f"• <b>Stop Loss:</b> <code>{sl}</code> <i>(-{trade.get('sl_pips', 0.0)} pips)</i>\n"
                            f"• <b>Take Profit:</b> <code>{tp}</code> <i>(+{trade.get('tp_pips', 0.0)} pips)</i>\n"
                            f"• <b>Risk / Reward:</b> <b>1 : {trade.get('rr', 1.75)}</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"🔴 <i>Order executed. Position is now actively floating in market.</i>"
                        )
                        send_telegram_alert(fill_msg)

                        # Evaluate if the remainder of this fill candle hit TP or SL
                        if b_low <= tp:
                            hit_tp = True
                            break
                        elif b_high >= sl:
                            hit_sl = True
                            break
            else:
                # Trade is active and OPEN
                pip = trade.get("pip", 0.0001)
                digits = trade.get("digits", 5)
                sl_pips = float(trade.get("sl_pips", 20.0))
                sl_dist = sl_pips * pip
                be_active = trade.get("be_active", False)

                # Dynamic Capital Protection Rule (Model H: Break-Even at +1.0R):
                # When floating profit reaches +1.0R, advance Stop Loss to Entry + 1.0 pip to eliminate risk
                if not be_active and sl_dist > 0:
                    if is_long and (b_high - entry) >= sl_dist:
                        new_sl = round(entry + (1.0 * pip), digits)
                        trade["stop_loss"] = new_sl
                        trade["be_active"] = True
                        sl = new_sl
                        modified_pairs.append(pair)
                        logger.info(f"==> BREAK-EVEN ACTIVATED: {pair} LONG SL moved to {new_sl} (+1.0R reached)")
                        be_msg = (
                            f"🛡️ <b>BREAK-EVEN ACTIVATED · {pair} LONG</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"• <b>Milestone:</b> Position reached <b>+1.0 R</b> (+{sl_pips:.1f} pips)\n"
                            f"• <b>New Stop Loss:</b> <code>{new_sl}</code> <i>(Locked at Entry + Spread)</i>\n"
                            f"• <b>Risk Status:</b> <b>ZERO RISK (Capital Protected)</b>\n"
                            f"• <b>Target:</b> <code>{tp}</code> <i>(Full Take Profit Intact)</i>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"🔒 <i>Position protected against counter-trend reversals.</i>"
                        )
                        send_telegram_alert(be_msg)
                    elif (not is_long) and (entry - b_low) >= sl_dist:
                        new_sl = round(entry - (1.0 * pip), digits)
                        trade["stop_loss"] = new_sl
                        trade["be_active"] = True
                        sl = new_sl
                        modified_pairs.append(pair)
                        logger.info(f"==> BREAK-EVEN ACTIVATED: {pair} SHORT SL moved to {new_sl} (+1.0R reached)")
                        be_msg = (
                            f"🛡️ <b>BREAK-EVEN ACTIVATED · {pair} SHORT</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"• <b>Milestone:</b> Position reached <b>+1.0 R</b> (+{sl_pips:.1f} pips)\n"
                            f"• <b>New Stop Loss:</b> <code>{new_sl}</code> <i>(Locked at Entry - Spread)</i>\n"
                            f"• <b>Risk Status:</b> <b>ZERO RISK (Capital Protected)</b>\n"
                            f"• <b>Target:</b> <code>{tp}</code> <i>(Full Take Profit Intact)</i>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"🔒 <i>Position protected against counter-trend reversals.</i>"
                        )
                        send_telegram_alert(be_msg)

                if is_long:
                    if b_low <= sl:
                        hit_sl = True
                        break
                    elif b_high >= tp:
                        hit_tp = True
                        break
                else:
                    if b_high >= sl:
                        hit_sl = True
                        break
                    elif b_low <= tp:
                        hit_tp = True
                        break

                # Intraday Trend Invalidation Rule:
                # If trade held >= 24h (or 12h for 15M) and closes opposite to 20-EMA, exit early to protect capital
                if hasattr(row, 'ema20') and hasattr(row, 'time') and opened_at_str:
                    try:
                        fill_ref_ts = pd.to_datetime(trade.get("filled_at") or opened_at_str)
                        if fill_ref_ts.tzinfo is None:
                            fill_ref_ts = fill_ref_ts.replace(tzinfo=timezone.utc)
                        h_held = (row.time - fill_ref_ts).total_seconds() / 3600.0
                        inval_thresh = 12.0 if trade.get("timeframe") == "15M" else 24.0
                        if h_held >= inval_thresh:
                            if is_long and row.close < row.ema20:
                                hit_ema_exit = True
                                ema_exit_price = float(row.close)
                                break
                            elif (not is_long) and row.close > row.ema20:
                                hit_ema_exit = True
                                ema_exit_price = float(row.close)
                                break
                    except Exception:
                        pass

        # Check if setup remained PENDING beyond session timeout
        is_still_pending = (trade.get("status") == "PENDING")
        is_expired = False
        elapsed_hours = 0.0
        timeout_hours = 2.0 if trade.get("timeframe") == "15M" else 4.0
        if is_still_pending and opened_at_str:
            try:
                open_ts = pd.to_datetime(opened_at_str)
                if open_ts.tzinfo is None:
                    open_ts = open_ts.replace(tzinfo=timezone.utc)
                now_curr = datetime.now(timezone.utc)
                elapsed_hours = (now_curr - open_ts).total_seconds() / 3600.0
                if elapsed_hours >= timeout_hours:
                    is_expired = True
            except Exception as e:
                logger.error(f"Error checking pending timeout for {pair}: {e}")

        if cancelled_before_fill:
            logger.info(f"==> SETUP CANCELLED (SL breached prior to entry fill): {pair} {trade.get('direction')}")
            completed_record = {
                **trade,
                "exit_price": float(sl),
                "outcome": "CANCELLED",
                "realized_pips": 0.0,
                "realized_r": 0.0,
                "closed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "CANCELLED"
            }
            msg = (
                f"⚠️ <b>SETUP CANCELLED · {pair} {trade.get('direction')}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Entry Target:</b> <code>{trade.get('entry')}</code>\n"
                f"• <b>Stop Loss:</b> <code>{trade.get('stop_loss')}</code>\n"
                f"• <b>Reason:</b> Price breached Stop Loss prior to entry fill.\n"
                f"• <b>Net Realized:</b> <b>0.0 pips / 0.00 R (Zero Loss · Unfilled)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔓 <i>Pair unlocked. Surveillance resumed.</i>"
            )
            send_telegram_alert(msg)
            records.setdefault("completed_trades", []).append(completed_record)
            del records["active_trades"][pair]
            resolved_pairs.append(pair)

        elif is_expired:
            logger.info(f"==> SETUP EXPIRED (Unfilled after {elapsed_hours:.1f}h): {pair} {trade.get('direction')}")
            completed_record = {
                **trade,
                "exit_price": float(entry),
                "outcome": "EXPIRED_UNFILLED",
                "realized_pips": 0.0,
                "realized_r": 0.0,
                "closed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "EXPIRED"
            }
            msg = (
                f"⌛ <b>SETUP EXPIRED (UNFILLED) · {pair} {trade.get('direction')}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Entry Target:</b> <code>{trade.get('entry')}</code>\n"
                f"• <b>Time Elapsed:</b> <code>{elapsed_hours:.1f} hours</code> (exceeded {int(timeout_hours)}h session window)\n"
                f"• <b>Reason:</b> Limit order remained unfilled. Market structure transitioned.\n"
                f"• <b>Net Realized:</b> <b>0.0 pips / 0.00 R (Zero Loss)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔓 <i>Pair unlocked. Surveillance resumed immediately.</i>"
            )
            send_telegram_alert(msg)
            records.setdefault("completed_trades", []).append(completed_record)
            del records["active_trades"][pair]
            resolved_pairs.append(pair)

        elif hit_tp:
            exit_price = tp
            realized_pips = trade.get("tp_pips", 0.0)
            realized_r = trade.get("rr", 1.75)
            outcome = "WIN"

            logger.info(f"==> TRADE RESOLVED (TP): {pair} {trade.get('direction')} (+{realized_pips} pips)")

            completed_record = {
                **trade,
                "exit_price": float(exit_price),
                "outcome": outcome,
                "realized_pips": float(round(realized_pips, 1)),
                "realized_r": float(round(realized_r, 2)),
                "closed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "CLOSED"
            }

            # Run Institutional Post-Mortem Diagnostics and Volume Logging
            pm_record = None
            try:
                pm_record = record_trade_post_mortem(completed_record, df_trade)
            except Exception as e:
                logger.error(f"Error recording post-mortem for {pair}: {e}")

            msg = format_exit_message(trade, outcome, exit_price, realized_pips, realized_r, pm_record)
            send_telegram_alert(msg)

            records.setdefault("completed_trades", []).append(completed_record)
            del records["active_trades"][pair]
            resolved_pairs.append(pair)

        elif hit_sl:
            exit_price = sl
            is_be = trade.get("be_active", False)
            pip = trade.get("pip", 0.0001)
            init_sl_pips = float(trade.get("sl_pips", 20.0))

            if is_be:
                if is_long:
                    realized_pips = float(round((exit_price - entry) / pip, 1))
                else:
                    realized_pips = float(round((entry - exit_price) / pip, 1))
                realized_r = float(round(realized_pips / (init_sl_pips + 1e-9), 2))
                outcome = "BREAK_EVEN"
                logger.info(f"==> TRADE RESOLVED (BREAK-EVEN): {pair} {trade.get('direction')} ({realized_pips:+.1f} pips, {realized_r:+.2f}R)")
            else:
                realized_pips = -trade.get("sl_pips", 0.0)
                realized_r = -1.00
                outcome = "LOSS"
                logger.info(f"==> TRADE RESOLVED (SL): {pair} {trade.get('direction')} ({realized_pips} pips)")

            completed_record = {
                **trade,
                "exit_price": float(exit_price),
                "outcome": outcome,
                "realized_pips": float(round(realized_pips, 1)),
                "realized_r": float(round(realized_r, 2)),
                "closed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "CLOSED"
            }

            # Run Institutional Post-Mortem Diagnostics and Volume Logging
            pm_record = None
            try:
                pm_record = record_trade_post_mortem(completed_record, df_trade)
            except Exception as e:
                logger.error(f"Error recording post-mortem for {pair}: {e}")

            msg = format_exit_message(trade, outcome, exit_price, realized_pips, realized_r, pm_record)
            send_telegram_alert(msg)

            records.setdefault("completed_trades", []).append(completed_record)
            del records["active_trades"][pair]
            resolved_pairs.append(pair)

        elif hit_ema_exit:
            exit_price = float(ema_exit_price)
            pip = trade.get("pip", 0.0001)
            sl_dist = trade.get("sl_pips", 20.0) * pip
            if is_long:
                realized_pips = (exit_price - entry) / pip
                realized_r = (exit_price - entry) / (sl_dist + 1e-9)
            else:
                realized_pips = (entry - exit_price) / pip
                realized_r = (entry - exit_price) / (sl_dist + 1e-9)

            outcome = "WIN" if realized_r > 0 else "LOSS"
            logger.info(f"==> TRADE RESOLVED (EMA INVALIDATION): {pair} {trade.get('direction')} ({realized_pips:+.1f} pips, {realized_r:+.2f}R)")

            completed_record = {
                **trade,
                "exit_price": float(exit_price),
                "outcome": outcome,
                "realized_pips": float(round(realized_pips, 1)),
                "realized_r": float(round(realized_r, 2)),
                "closed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "CLOSED",
                "exit_reason": "EMA20_INVALIDATION"
            }

            pm_record = None
            try:
                pm_record = record_trade_post_mortem(completed_record, df_trade)
            except Exception as e:
                logger.error(f"Error recording post-mortem for {pair}: {e}")

            icon = "🎯" if realized_r > 0 else "🛑"
            sign = "+" if realized_pips >= 0 else ""
            r_sign = "+" if realized_r >= 0 else ""
            thresh_h = 12 if trade.get("timeframe") == "15M" else 24
            inval_msg = (
                f"{icon} <b>TREND INVALIDATION EXIT · {pair} {trade.get('direction')}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Entry Price:</b> <code>{entry}</code>\n"
                f"• <b>Exit Price:</b> <code>{exit_price}</code>\n"
                f"• <b>Net Realized:</b> <b>{sign}{realized_pips:.1f} pips ({r_sign}{realized_r:.2f} R)</b>\n"
                f"• <b>Reason:</b> Position held > {thresh_h}h with 20-EMA counter-trend close.\n"
                f"• <b>Action:</b> Position closed early to protect capital and prevent multi-day chop.\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔓 <i>Pair unlocked. Capital freed for fresh high-probability setups.</i>"
            )
            send_telegram_alert(inval_msg)

            records.setdefault("completed_trades", []).append(completed_record)
            del records["active_trades"][pair]
            resolved_pairs.append(pair)

    if resolved_pairs or modified_pairs:
        save_trade_records(records)
        sync_worker(records)


def send_telegram_alert(text: str, max_retries: int = 3):
    """Send Telegram message with exponential backoff on rate limit (HTTP 429)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info(f"[TELEGRAM SKIPPED — no credentials] {text[:120]}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    logger.info("Telegram alert sent successfully.")
                    return
                elif resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 5))
                    logger.warning(f"Telegram rate limited. Waiting {retry_after}s (attempt {attempt+1}/{max_retries})")
                    time.sleep(retry_after)
                else:
                    logger.error(f"Failed to send Telegram alert: {resp.status_code} {resp.text[:200]}")
                    return  # Non-retriable error
        except Exception as e:
            logger.error(f"Error sending Telegram alert (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)


def get_live_price(ticker: str, pip: float, digits: int) -> float | None:
    """
    Fetch the true current live price for a ticker.
    Uses the most recent bar (including in-progress) from Yahoo Finance / Binance,
    falling back to None if unavailable.
    For XAUUSD uses gold-api.com spot price directly.
    """
    try:
        if ticker in ["PAXGUSDT", "XAUUSD", "GC=F"]:
            # Prefer direct spot gold API — most accurate
            try:
                with httpx.Client(timeout=4.0) as g:
                    r = g.get("https://api.gold-api.com/price/XAU", headers={"User-Agent": "Mozilla/5.0"})
                    if r.status_code == 200:
                        p = float(r.json().get("price", 0))
                        if p > 0:
                            return round(p, digits)
            except Exception:
                pass
            # Fallback: Binance latest close
            try:
                url = "https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT"
                with httpx.Client(timeout=4.0) as g:
                    r = g.get(url, headers={"User-Agent": "MarketScanner/2.0"})
                    if r.status_code == 200:
                        p = float(r.json().get("price", 0))
                        if p > 0:
                            # get live spot offset: apply same offset logic
                            df_tmp = fetch_candles("PAXGUSDT", "5m", range_days="1d")
                            if not df_tmp.empty:
                                raw_last = df_tmp.iloc[-1]["close"]
                                # offset = spot - raw_last (already applied inside fetch_candles)
                                # Just return the calibrated last close
                                return round(df_tmp.iloc[-1]["close"], digits)
            except Exception:
                pass
            return None
        else:
            # Yahoo Finance: use 1m range to get the freshest tick
            yf_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=5m"
            with httpx.Client(timeout=6.0) as c:
                r = c.get(yf_url, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    result = r.json().get("chart", {}).get("result")
                    if result:
                        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
                        closes = [x for x in (quotes.get("close") or []) if x is not None]
                        if closes:
                            return round(closes[-1], digits)
        return None
    except Exception as e:
        logger.debug(f"get_live_price notice for {ticker}: {e}")
        return None


def fetch_candles(ticker: str, interval: str, range_days: str = "7d") -> pd.DataFrame:
    """Fetch candles from real-time API (Calibrated MT5 Spot Gold for XAUUSD, Yahoo Finance for Forex)."""
    # 1:1 MT5 Spot Gold Feed (Calibrated directly to spot London gold / MT5 XAUUSD price)
    if ticker in ["PAXGUSDT", "XAUUSD", "GC=F"]:
        try:
            # 1. Query live MT5/Spot Gold price with instant fallback
            live_spot = None
            try:
                # Primary: gold-api.com (100% uptime, zero Cloudflare/IP blocking, spot London/MT5 gold)
                with httpx.Client(timeout=4.0) as g_client:
                    g_resp = g_client.get("https://api.gold-api.com/price/XAU", headers={"User-Agent": "Mozilla/5.0"})
                    if g_resp.status_code == 200:
                        g_data = g_resp.json()
                        p = float(g_data.get("price", 0))
                        if p > 0:
                            live_spot = p
            except Exception as ge:
                logger.debug(f"gold-api query notice: {ge}")

            if live_spot is None:
                try:
                    # Secondary: TradingView CFD scanner
                    url_tv = "https://scanner.tradingview.com/cfd/scan"
                    payload = {"symbols": {"tickers": ["OANDA:XAUUSD", "FX:XAUUSD"]}, "columns": ["close"]}
                    with httpx.Client(timeout=4.0) as tv_client:
                        tv_resp = tv_client.post(url_tv, json=payload, headers={"User-Agent": "Mozilla/5.0"})
                        if tv_resp.status_code == 200:
                            tv_data = tv_resp.json()
                            prices = [row["d"][0] for row in tv_data.get("data", []) if row.get("d")]
                            if prices:
                                live_spot = float(prices[0])
                except Exception as tve:
                    logger.debug(f"TradingView spot query notice: {tve}")

            # 2. Fetch candle series: Try Binance PAXG first, if blocked or fails, use Yahoo Finance GC=F
            df_gold = pd.DataFrame()
            try:
                b_interval = "15m" if interval == "15m" else "1h"
                limit = 400 if interval == "15m" else 200
                url = f"https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval={b_interval}&limit={limit}"
                with httpx.Client(timeout=6.0) as client:
                    resp = client.get(url, headers={"User-Agent": "MarketScanner/2.0"})
                    if resp.status_code == 200:
                        data = resp.json()
                        records = []
                        for b in data:
                            records.append({
                                "timestamp": int(b[0] / 1000),
                                "time": pd.to_datetime(b[0], unit="ms", utc=True),
                                "open": float(b[1]),
                                "high": float(b[2]),
                                "low": float(b[3]),
                                "close": float(b[4]),
                                "volume": float(b[5])
                            })
                        df_gold = pd.DataFrame(records)
            except Exception:
                pass

            # If Binance was blocked (e.g., HTTP 451 in US / Cloud environments), fall back to Yahoo GC=F
            if df_gold.empty or len(df_gold) < 30:
                try:
                    yf_url = f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F?range={range_days}&interval={interval}"
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.get(yf_url, headers={"User-Agent": "Mozilla/5.0"})
                        if resp.status_code == 200:
                            data = resp.json()
                            result = data.get("chart", {}).get("result")
                            if result:
                                timestamps = result[0].get("timestamp", [])
                                quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
                                if timestamps and "close" in quotes:
                                    df_gold = pd.DataFrame({
                                        "timestamp": timestamps,
                                        "open": quotes.get("open", []),
                                        "high": quotes.get("high", []),
                                        "low": quotes.get("low", []),
                                        "close": quotes.get("close", []),
                                        "volume": quotes.get("volume", [0] * len(timestamps))
                                    })
                except Exception as yfe:
                    logger.warning(f"Yahoo Gold fallback notice: {yfe}")

            if not df_gold.empty:
                df_gold.dropna(subset=["open", "high", "low", "close"], inplace=True)
                if "time" not in df_gold.columns:
                    df_gold["time"] = pd.to_datetime(df_gold["timestamp"], unit="s", utc=True)
                df_gold.sort_values("time", inplace=True)
                df_gold.reset_index(drop=True, inplace=True)

                # 3. Calibrate offset so all candle prices match MT5 XAUUSD spot directly
                if live_spot is not None and not df_gold.empty:
                    offset = live_spot - df_gold.iloc[-1]["close"]
                    for col in ["open", "high", "low", "close"]:
                        df_gold[col] = (df_gold[col] + offset).round(2)

                return df_gold
        except Exception as e:
            logger.warning(f"Spot gold feed notice: {e}, attempting secondary source...")

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_days}&interval={interval}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"Fetch failed for {ticker} ({interval}): HTTP {resp.status_code}")
                return pd.DataFrame()
            
            data = resp.json()
            result = data.get("chart", {}).get("result")
            if not result:
                return pd.DataFrame()
            
            timestamps = result[0].get("timestamp", [])
            quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
            
            if not timestamps or "close" not in quotes:
                return pd.DataFrame()
            
            df = pd.DataFrame({
                "timestamp": timestamps,
                "open": quotes.get("open", []),
                "high": quotes.get("high", []),
                "low": quotes.get("low", []),
                "close": quotes.get("close", []),
                "volume": quotes.get("volume", [0] * len(timestamps))
            })
            
            # Clean missing data (weekends / empty ticks)
            df.dropna(subset=["open", "high", "low", "close"], inplace=True)
            df["time"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
            df.sort_values("time", inplace=True)
            df.reset_index(drop=True, inplace=True)
            return df
    except Exception as e:
        logger.error(f"Error fetching {ticker} ({interval}): {e}")
        return pd.DataFrame()


def fetch_5m_entry_trigger(
    ticker: str,
    direction: str,
    ote_zone_low: float,
    ote_zone_high: float,
    entry_ref: float,
    pip: float,
    digits: int
) -> dict:
    """
    ICT Lower-Timeframe Entry Trigger Analysis (5M Precision Entry).

    Fetches the live 5-minute chart and identifies the best entry signal
    currently forming within the 15M OTE zone. Uses ICT micro-structure:
    - Rejection Wick: Long lower wick on a bullish 5M bar (for longs) near OTE
    - Bearish Engulfing: 5M bar that fully engulfs previous bullish bar (for shorts)
    - Fair Value Gap (FVG): 3-bar pattern gap retest near OTE
    - Momentum Continuation: current 5M bar direction confirming 15M signal

    Returns a dict with 'trigger_type', 'precision_entry', 'confidence', and 'action_text'.
    Returns None if no clear trigger is found.
    """
    try:
        df5 = fetch_candles(ticker, "5m", range_days="2d")
        if df5.empty or len(df5) < 10:
            return None

        now_utc = datetime.now(timezone.utc)
        tf_delta_5m = pd.Timedelta(minutes=5)
        df5["close_time"] = df5["time"] + tf_delta_5m
        # Only consider fully closed 5M bars
        closed_5m = df5[df5["close_time"] <= now_utc]
        if len(closed_5m) < 4:
            return None

        c0 = closed_5m.iloc[-1]   # Most recent closed 5M bar
        c1 = closed_5m.iloc[-2]   # Bar before that
        c2 = closed_5m.iloc[-3]   # Two bars back

        is_long = (direction == "LONG")
        trigger_found = None
        precision_entry = None
        confidence = 0
        action_text = ""
        trigger_type = ""

        def in_ote_zone(price):
            """Check if price is near the OTE zone (within 3 pips for forex, 15 pips for gold)."""
            buffer = 15.0 * pip if pip >= 0.1 else 3.0 * pip
            return (ote_zone_low - buffer) <= price <= (ote_zone_high + buffer)

        if is_long:
            # --- Pattern 1: Rejection Wick (Bullish Pin Bar on 5M) ---
            # Lower wick > 2x body, close near high, price near OTE
            body = abs(c0["close"] - c0["open"])
            lower_wick = c0["open"] - c0["low"] if c0["close"] >= c0["open"] else c0["close"] - c0["low"]
            upper_wick = c0["high"] - c0["close"] if c0["close"] >= c0["open"] else c0["high"] - c0["open"]
            is_bullish_bar = c0["close"] > c0["open"]
            if (lower_wick > 2.0 * max(body, pip) and
                    lower_wick > upper_wick and
                    is_bullish_bar and
                    in_ote_zone(c0["low"])):
                trigger_found = True
                precision_entry = round(c0["close"], digits)
                confidence = 92
                trigger_type = "5M Rejection Wick"
                action_text = f"Bullish pin bar on 5M — enter at close <code>{precision_entry}</code>"

            # --- Pattern 2: Bullish Engulfing on 5M (strong reversal from OTE) ---
            elif (not trigger_found and
                  c0["close"] > c0["open"] and
                  c1["close"] < c1["open"] and
                  c0["close"] > c1["open"] and
                  c0["open"] <= c1["close"] and
                  in_ote_zone(c0["low"])):
                trigger_found = True
                precision_entry = round(c0["close"], digits)
                confidence = 88
                trigger_type = "5M Bullish Engulf"
                action_text = f"Bullish engulfing off OTE zone — enter at close <code>{precision_entry}</code>"

            # --- Pattern 3: Fair Value Gap (FVG) Retest ---
            # Gap = c2.high < c0.low  → price retraces into the gap area on c0
            elif not trigger_found:
                fvg_low = c2["high"]
                fvg_high = c0["low"]
                if (fvg_low < fvg_high and
                        in_ote_zone(c1["low"]) and
                        c0["close"] > c0["open"]):
                    trigger_found = True
                    precision_entry = round(c0["close"], digits)
                    confidence = 84
                    trigger_type = "5M FVG Retest"
                    action_text = f"5M Fair Value Gap filled and bouncing — enter at close <code>{precision_entry}</code>"

            # --- Pattern 4: Momentum continuation (last 2 x bullish 5M bars) ---
            elif not trigger_found:
                if (c0["close"] > c0["open"] and
                        c1["close"] > c1["open"] and
                        c0["close"] > entry_ref and
                        c0["close"] <= ote_zone_high + (10 * pip)):
                    trigger_found = True
                    precision_entry = round(c0["close"], digits)
                    confidence = 75
                    trigger_type = "5M Momentum Continuation"
                    action_text = f"2 consecutive bullish 5M bars — momentum entry at <code>{precision_entry}</code>"

        else:  # SHORT
            # --- Pattern 1: Rejection Wick (Bearish Pin Bar on 5M) ---
            body = abs(c0["close"] - c0["open"])
            upper_wick = c0["high"] - c0["open"] if c0["close"] <= c0["open"] else c0["high"] - c0["close"]
            lower_wick = c0["open"] - c0["low"] if c0["close"] <= c0["open"] else c0["close"] - c0["low"]
            is_bearish_bar = c0["close"] < c0["open"]
            if (upper_wick > 2.0 * max(body, pip) and
                    upper_wick > lower_wick and
                    is_bearish_bar and
                    in_ote_zone(c0["high"])):
                trigger_found = True
                precision_entry = round(c0["close"], digits)
                confidence = 92
                trigger_type = "5M Rejection Wick"
                action_text = f"Bearish pin bar on 5M — enter at close <code>{precision_entry}</code>"

            # --- Pattern 2: Bearish Engulfing on 5M ---
            elif (not trigger_found and
                  c0["close"] < c0["open"] and
                  c1["close"] > c1["open"] and
                  c0["close"] < c1["open"] and
                  c0["open"] >= c1["close"] and
                  in_ote_zone(c0["high"])):
                trigger_found = True
                precision_entry = round(c0["close"], digits)
                confidence = 88
                trigger_type = "5M Bearish Engulf"
                action_text = f"Bearish engulfing at OTE zone — enter at close <code>{precision_entry}</code>"

            # --- Pattern 3: FVG Retest (bearish) ---
            elif not trigger_found:
                fvg_high = c2["low"]
                fvg_low = c0["high"]
                if (fvg_high > fvg_low and
                        in_ote_zone(c1["high"]) and
                        c0["close"] < c0["open"]):
                    trigger_found = True
                    precision_entry = round(c0["close"], digits)
                    confidence = 84
                    trigger_type = "5M FVG Retest"
                    action_text = f"5M Fair Value Gap filled and rejecting — enter at close <code>{precision_entry}</code>"

            # --- Pattern 4: Momentum continuation (last 2 x bearish 5M bars) ---
            elif not trigger_found:
                if (c0["close"] < c0["open"] and
                        c1["close"] < c1["open"] and
                        c0["close"] < entry_ref and
                        c0["close"] >= ote_zone_low - (10 * pip)):
                    trigger_found = True
                    precision_entry = round(c0["close"], digits)
                    confidence = 75
                    trigger_type = "5M Momentum Continuation"
                    action_text = f"2 consecutive bearish 5M bars — momentum entry at <code>{precision_entry}</code>"

        if trigger_found and precision_entry is not None:
            return {
                "trigger_type": trigger_type,
                "precision_entry": precision_entry,
                "confidence": confidence,
                "action_text": action_text,
                "bar_close_time": c0["close_time"].strftime("%H:%M UTC")
            }
        return None
    except Exception as e:
        logger.debug(f"5M entry trigger analysis notice for {ticker}: {e}")
        return None


def compute_indicators(df: pd.DataFrame, donchian_len: int = 20) -> pd.DataFrame:
    """Compute technical indicators matching strategy specifications."""
    df = df.copy()
    
    # EMAs
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema20_slope"] = df["ema20"] - df["ema20"].shift(2)
    
    # Donchian Breakout Levels (using previous completed bars)
    df["donch_high"] = df["high"].shift(1).rolling(donchian_len).max()
    df["donch_low"] = df["low"].shift(1).rolling(donchian_len).min()
    
    # ATR (14) — Wilder smoothing
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1.0/14.0, adjust=False).mean()
    
    # RSI (14)
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0/14.0, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/14.0, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df["rsi"] = 100.0 - (100.0 / (1.0 + rs))

    # ADX (14) — Wilder smoothing
    # Forensic audit: ADX 20-30 regime has -0.09R expectancy and 0.83 PF (net-losing).
    # ADX <20 = 0.32R expectancy, 1.88 PF. ADX >30 = 0.092R expectancy, 1.19 PF.
    # We use ADX to SKIP moderate-trend chop (the killer of our system).
    high = df["high"]
    low = df["low"]
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = df["close"].shift(1)
    plus_dm = (high - prev_high).clip(lower=0)
    minus_dm = (prev_low - low).clip(lower=0)
    # When +DM < -DM, +DM = 0 and vice versa
    cond_plus = plus_dm > minus_dm
    cond_minus = minus_dm > plus_dm
    plus_dm_clean = np.where(cond_plus, plus_dm, 0.0)
    minus_dm_clean = np.where(cond_minus, minus_dm, 0.0)
    tr14 = tr.ewm(alpha=1.0/14.0, adjust=False).mean()
    plus_di = 100.0 * pd.Series(plus_dm_clean, index=df.index).ewm(alpha=1.0/14.0, adjust=False).mean() / (tr14 + 1e-9)
    minus_di = 100.0 * pd.Series(minus_dm_clean, index=df.index).ewm(alpha=1.0/14.0, adjust=False).mean() / (tr14 + 1e-9)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    df["adx"] = dx.ewm(alpha=1.0/14.0, adjust=False).mean()
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di
    
    return df


def get_session_quality(now_utc: datetime) -> tuple[str, float, str]:
    """
    Returns (session_name, score_multiplier, session_icon) based on UTC hour.
    Score multipliers derived from forensic audit session performance:
      London          : 51.1% WR, +0.272R expectancy, 1.63 PF  -> best active session
      NY Afternoon    : 52.8% WR, +0.099R expectancy, 1.28 PF  -> solid
      Asian/Tokyo     : 47.8% WR, +0.187R expectancy, 1.43 PF  -> decent
      London/NY Overlap: 33.3% WR, -0.218R expectancy, 0.62 PF -> blocked upstream
      Late NY/Pacific : 66.7% WR, +0.833R expectancy (n=3, too small) -> allow cautiously
    """
    h = now_utc.hour
    if 5 <= h < 12:
        return "London Session", 1.05, "🇬🇧"
    elif 16 <= h < 20:
        return "New York Afternoon", 1.0, "🇺🇸"
    elif 0 <= h < 5 or h >= 20:
        return "Asian / Tokyo Session", 0.95, "🌏"
    else:
        # 12-16 overlap — blocked upstream, but label it if we ever reach here
        return "London/NY Overlap", 0.80, "⚠️"


def find_ict_liquidity_target(
    df: pd.DataFrame,
    entry: float,
    sl_dist: float,
    is_long: bool,
    lookback_bars: int = 120,
    min_rr: float = 1.5,
    max_rr: float = 2.5,
    default_rr: float = 1.75
) -> tuple[float, float, str]:
    """
    Identifies the nearest un-swept institutional liquidity pool for Take Profit targeting.
    Implements Model F (Pure Structural Target) from forensic audit:
      - Model F: 0.281R expectancy, 1.52 PF, 8.11R max drawdown
      - Model A (current): 0.111R expectancy, 1.24 PF, 15.96R max drawdown
    
    Key change: Multi-fractal validation — a swing high/low must be confirmed by
    TWO neighbouring bars on each side (3-bar minimum strength) rather than one.
    This eliminates noisy micro-swings that get swept before our TP is hit.
    
    - Longs target un-swept Buy-Side Liquidity (BSL) above previous swing highs.
    - Shorts target un-swept Sell-Side Liquidity (SSL) below previous swing lows.
    Returns (take_profit_price, realized_rr, liquidity_target_name).
    """
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)
    closed_idx = n - 1

    if is_long:
        bsl_candidates = []
        # Search backwards for confirmed 3-bar fractal swing highs (stronger validation)
        for k in range(closed_idx - 3, max(3, closed_idx - lookback_bars), -1):
            # Strong fractal: higher than both neighbours on each side
            if (highs[k] >= highs[k-1] and highs[k] >= highs[k-2] and
                    highs[k] >= highs[k+1] and highs[k] >= highs[k+2]):
                if highs[k] >= entry + (sl_dist * min_rr):
                    bsl_candidates.append(highs[k])
        if bsl_candidates:
            # Target nearest BSL pool (minimum, nearest resistance cluster)
            tp = min(bsl_candidates)
            rr = (tp - entry) / sl_dist
            if rr > max_rr:
                rr = max_rr
                tp = entry + (sl_dist * max_rr)
            return float(tp), float(round(rr, 2)), "BSL Pool (Buy-Side Liquidity)"
        # No clear structural BSL: use default_rr but flag it as expansion
        return float(entry + (sl_dist * default_rr)), float(default_rr), "Structural Expansion (1.75R)"
    else:
        ssl_candidates = []
        # Search backwards for confirmed 3-bar fractal swing lows
        for k in range(closed_idx - 3, max(3, closed_idx - lookback_bars), -1):
            if (lows[k] <= lows[k-1] and lows[k] <= lows[k-2] and
                    lows[k] <= lows[k+1] and lows[k] <= lows[k+2]):
                if lows[k] <= entry - (sl_dist * min_rr):
                    ssl_candidates.append(lows[k])
        if ssl_candidates:
            # Target nearest SSL pool (maximum, nearest support cluster)
            tp = max(ssl_candidates)
            rr = (entry - tp) / sl_dist
            if rr > max_rr:
                rr = max_rr
                tp = entry - (sl_dist * max_rr)
            return float(tp), float(round(rr, 2)), "SSL Pool (Sell-Side Liquidity)"
        return float(entry - (sl_dist * default_rr)), float(default_rr), "Structural Expansion (1.75R)"


def scan_pair_timeframe(pair_name: str, config: dict, tf: str, state: dict) -> list:
    """Scans a single pair and timeframe for confirmed structural breakout setups."""
    ticker = config["ticker"]
    pip = config["pip"]
    digits = config["digits"]
    
    df = fetch_candles(ticker, tf, range_days="7d")
    if df.empty or len(df) < 50:
        return []
    
    now_utc = datetime.now(timezone.utc)

    # High-liquidity Session Guard: Restrict new signal generation to Frankfurt/London/NY hours (05:00 to 21:00 UTC).
    # Captures European open momentum through late NY session while protecting against overnight Asian chop.
    if not (5 <= now_utc.hour <= 21):
        logger.info(f"Skipping {pair_name} ({tf}): Current time {now_utc.strftime('%H:%M')} UTC outside active liquidity hours (05:00 - 21:00 UTC).")
        return []

    # London/New York Overlap Whipsaw Guard: Restrict new breakout signal generation between 12:00 and 16:00 UTC.
    # Forensic audit: 33.3% WR, -0.218R expectancy, 0.62 PF — the single worst session window.
    # Active floating positions remain fully monitored and protected with break-even stops.
    if 12 <= now_utc.hour < 16:
        logger.info(f"Skipping {pair_name} ({tf}): Current time {now_utc.strftime('%H:%M')} UTC inside London/NY Overlap news volatility window (12:00 - 16:00 UTC).")
        return []

    # Determine session quality context (used for signal scoring below)
    session_name, session_multiplier, session_icon = get_session_quality(now_utc)

    donch_len = config.get("donchian_len", 20)
    df = compute_indicators(df, donchian_len=donch_len)
    
    # In Yahoo Finance, bar timestamp is the OPEN time.
    # Compute the true CLOSE time for each bar.
    tf_delta = pd.Timedelta(minutes=15) if tf == "15m" else pd.Timedelta(hours=1)
    df["close_time"] = df["time"] + tf_delta
    
    # Strictly select bars that have finished closing
    closed_bars = df[df["close_time"] <= now_utc]
    if len(closed_bars) < 30:
        return []
    
    closed_bar = closed_bars.iloc[-1]
    prev_bar = closed_bars.iloc[-2]
    
    # Freshness guard: Only fire a signal within 5 minutes of the bar closing (15M) or 20 minutes (1H).
    # This prevents stale signals where price has already moved far from entry.
    # Deduplication via state['alerted_signals'] ensures no double-firing.
    max_age_seconds = 300 if tf == "15m" else 1200
    seconds_since_close = (now_utc - closed_bar["close_time"]).total_seconds()
    if seconds_since_close > max_age_seconds:
        logger.info(f"Skipping {pair_name} ({tf}): Bar closed {int(seconds_since_close)}s ago (exceeds {max_age_seconds}s freshness limit). Live price may have drifted.")
        return []
    
    bar_time_str = closed_bar["close_time"].strftime("%Y-%m-%dT%H:%M:%SZ")
    
    signals = []
    
    # Macro trend filter: EMA 20 > EMA 50 and positive slope
    bullish_trend = (closed_bar["close"] > closed_bar["ema50"]) and (closed_bar["ema20"] > closed_bar["ema50"]) and (closed_bar["ema20_slope"] > 0)
    bearish_trend = (closed_bar["close"] < closed_bar["ema50"]) and (closed_bar["ema20"] < closed_bar["ema50"]) and (closed_bar["ema20_slope"] < 0)
    
    # Anti-exhaustion RSI guard (Optimized: 40-80 for Longs, 20-60 for Shorts)
    rsi_bullish_ok = 40.0 <= closed_bar["rsi"] <= 80.0
    rsi_bearish_ok = 20.0 <= closed_bar["rsi"] <= 60.0
    
    # Candle Body Quality Guard:
    # On 15M, prevent entering on breakout candles with large rejection wicks (>45% wick / <55% body)
    bar_range = closed_bar["high"] - closed_bar["low"]
    bar_body = abs(closed_bar["close"] - closed_bar["open"])
    body_ratio = bar_body / (bar_range + 1e-9)
    if tf == "15m" and body_ratio < 0.55:
        logger.info(f"Skipping {pair_name} ({tf}): Breakout candle body ratio too low ({body_ratio:.1%}). Rejection wick risk.")
        return []

    # ADX Regime Filter — Forensic Audit Critical Finding:
    # ADX 20-30 (Moderate Trend) = 38.4% WR, -0.09R expectancy, 0.83 PF (net-losing regime).
    # ADX <20  (Low ADX / Choppy) = 54.5% WR, +0.32R expectancy, 1.88 PF (paradoxically best).
    # ADX >30  (Strong Trend)     = 45.9% WR, +0.092R expectancy, 1.19 PF (acceptable).
    # ACTION: Block new signals when ADX is in the 20-30 killing zone.
    adx = closed_bar.get("adx", 0) if hasattr(closed_bar, 'get') else getattr(closed_bar, 'adx', 0)
    adx_val = float(adx) if adx and not np.isnan(float(adx)) else 0.0
    if 20.0 < adx_val < 30.0:
        logger.info(
            f"Skipping {pair_name} ({tf}): ADX={adx_val:.1f} is in the moderate-trend killing zone (20-30). "
            f"Historical expectancy: -0.09R / 38.4% WR. Waiting for clear regime."
        )
        return []

    # Donchian Breakout on completed bar
    long_breakout = (closed_bar["close"] > closed_bar["donch_high"]) and (prev_bar["close"] <= prev_bar["donch_high"])
    short_breakout = (closed_bar["close"] < closed_bar["donch_low"]) and (prev_bar["close"] >= prev_bar["donch_low"])
    
    atr = closed_bar["atr"]
    if pair_name == "XAUUSD":
        min_sl_dist = 60.0 * pip   # $6.00 minimum
        max_sl_dist = 350.0 * pip  # $35.00 maximum
    else:
        min_sl_dist = 18.0 * pip
        max_sl_dist = 65.0 * pip
    rr_ratio = 1.75

    # ADX regime label for signal metadata
    if adx_val < 20.0:
        adx_regime = "Low ADX / Range (Optimal)"
    elif adx_val >= 30.0:
        adx_regime = "Strong Trend"
    else:
        adx_regime = "Moderate Trend (Caution)"  # Should never reach here after filter above
    
    # LONG SIGNAL CHECK
    if long_breakout and bullish_trend and rsi_bullish_ok:
        sig_id = f"{pair_name}_{tf.upper()}_{bar_time_str}_LONG"
        if sig_id not in state["alerted_signals"]:
            # Find Origin Order Block: last down-close candle prior to displacement
            ob_low = closed_bar["low"]
            closed_idx = closed_bars.index[-1]
            for i in range(closed_idx - 1, max(0, closed_idx - 10), -1):
                c = df.loc[i]
                if c["close"] < c["open"]:
                    ob_low = c["low"]
                    break

            # --- LIVE PRICE VALIDATION ---
            # Use the current live market price instead of the stale bar close.
            # This ensures the entry shown is always the REAL current price.
            bar_close_price = float(closed_bar["close"])
            live_price = get_live_price(ticker, pip, digits)
            if live_price is None:
                live_price = bar_close_price  # fallback to bar close if live fetch fails

            # For a LONG, if live price is *below* the breakout level, setup may have failed.
            # If live price has run more than max_chase_pips ABOVE bar close, price is extended — skip.
            max_chase_pips = 25.0 if pair_name == "XAUUSD" else 3.5
            max_chase_price_check = bar_close_price + (max_chase_pips * pip)
            if live_price > max_chase_price_check:
                logger.info(f"Skipping {pair_name} ({tf}) LONG: Live price {live_price} extended {round((live_price - bar_close_price)/pip, 1)}p above bar close. Setup overextended.")
                state["alerted_signals"].append(sig_id)  # mark as seen to avoid re-alerting
                return signals

            # Use live price as entry — it is what the user will actually fill at
            entry = live_price
            sl_candidate = float(ob_low - (0.50 * atr))
            sl_dist = float(max(min_sl_dist, min(max_sl_dist, entry - sl_candidate)))
            stop_loss = float(entry - sl_dist)

            # ICT Liquidity Target: Target nearest un-swept Buy-Side Liquidity (BSL)
            take_profit, calc_rr, pool_name = find_ict_liquidity_target(df, entry, sl_dist, is_long=True)

            # ICT Multi-Timeframe Entry Modeling (50% Consequent Encroachment / OTE Retest)
            # OTE zone is still based on bar-close structure (the origin OB)
            disp_range = bar_close_price - ob_low
            ote_entry = round(bar_close_price - (0.50 * disp_range), digits)
            max_chase_price = round(bar_close_price + (max_chase_pips * pip), digits)
            valid_zone_low = round(ote_entry, digits)
            valid_zone_high = round(max_chase_price, digits)

            # ICT 5M Precision Entry Trigger (lower-timeframe confirmation)
            lf_trigger = fetch_5m_entry_trigger(
                ticker, "LONG", valid_zone_low, valid_zone_high, bar_close_price, pip, digits
            )
            # If 5M trigger found a better price, prefer it
            if lf_trigger and lf_trigger.get("precision_entry"):
                entry = lf_trigger["precision_entry"]
                sl_dist = float(max(min_sl_dist, min(max_sl_dist, entry - float(ob_low - 0.50 * atr))))
                stop_loss = float(entry - sl_dist)
                take_profit, calc_rr, pool_name = find_ict_liquidity_target(df, entry, sl_dist, is_long=True)

            # --- Signal Score Calculation (0-100) ---
            # Base score for a clean structural breakout with trend + RSI confluence
            sig_score = 92
            # Boost for 5M precision entry confirmation
            if lf_trigger:
                if lf_trigger["confidence"] >= 90:
                    sig_score += 8   # = 100
                elif lf_trigger["confidence"] >= 80:
                    sig_score += 5   # = 97
                else:
                    sig_score += 2   # = 94
            # Session quality adjustment (forensic audit: London +7.3% win delta vs losers)
            sig_score = round(sig_score * session_multiplier)
            # ADX regime quality bonus: Low ADX (best regime) gets +2, Strong trend gets +1
            if adx_val < 20.0:
                sig_score = min(100, sig_score + 2)
            # Wide SL penalty: forensic audit shows High ATR (SL >30p) = -9.9% win delta
            sl_pips_val = round(sl_dist / pip, 1)
            if sl_pips_val > 30.0 and pair_name != "XAUUSD":
                sig_score = max(60, sig_score - 5)
            sig_score = min(100, max(50, sig_score))

            signals.append({
                "id": sig_id,
                "pair": pair_name,
                "timeframe": tf.upper(),
                "direction": "LONG",
                "time": bar_time_str,
                "entry": round(entry, digits),
                "bar_close_price": round(bar_close_price, digits),
                "ote_entry": ote_entry,
                "valid_zone_low": valid_zone_low,
                "valid_zone_high": valid_zone_high,
                "max_chase_price": max_chase_price,
                "max_chase_pips": max_chase_pips,
                "stop_loss": round(stop_loss, digits),
                "take_profit": round(take_profit, digits),
                "sl_pips": sl_pips_val,
                "tp_pips": round((take_profit - entry) / pip, 1),
                "rr": calc_rr,
                "target_type": pool_name,
                "donchian_len": donch_len,
                "rsi": float(round(closed_bar["rsi"], 1)),
                "atr": float(round(atr / pip, 1)),
                "adx": float(round(adx_val, 1)),
                "adx_regime": adx_regime,
                "session": session_name,
                "session_icon": session_icon,
                "score": sig_score,
                "lf_trigger": lf_trigger
            })
            state["alerted_signals"].append(sig_id)

    # SHORT SIGNAL CHECK
    if short_breakout and bearish_trend and rsi_bearish_ok:
        sig_id = f"{pair_name}_{tf.upper()}_{bar_time_str}_SHORT"
        if sig_id not in state["alerted_signals"]:
            # Find Origin Order Block: last up-close candle prior to displacement
            ob_high = closed_bar["high"]
            closed_idx = closed_bars.index[-1]
            for i in range(closed_idx - 1, max(0, closed_idx - 10), -1):
                c = df.loc[i]
                if c["close"] > c["open"]:
                    ob_high = c["high"]
                    break

            # --- LIVE PRICE VALIDATION ---
            bar_close_price = float(closed_bar["close"])
            live_price = get_live_price(ticker, pip, digits)
            if live_price is None:
                live_price = bar_close_price

            # For a SHORT, if live price has dropped more than max_chase_pips BELOW bar close, extended — skip.
            max_chase_pips = 25.0 if pair_name == "XAUUSD" else 3.5
            max_chase_price_check = bar_close_price - (max_chase_pips * pip)
            if live_price < max_chase_price_check:
                logger.info(f"Skipping {pair_name} ({tf}) SHORT: Live price {live_price} extended {round((bar_close_price - live_price)/pip, 1)}p below bar close. Setup overextended.")
                state["alerted_signals"].append(sig_id)
                return signals

            entry = live_price
            sl_candidate = float(ob_high + (0.50 * atr))
            sl_dist = float(max(min_sl_dist, min(max_sl_dist, sl_candidate - entry)))
            stop_loss = float(entry + sl_dist)

            # ICT Liquidity Target: Target nearest un-swept Sell-Side Liquidity (SSL)
            take_profit, calc_rr, pool_name = find_ict_liquidity_target(df, entry, sl_dist, is_long=False)

            # ICT Multi-Timeframe Entry Modeling (50% Consequent Encroachment / OTE Retest)
            disp_range = ob_high - bar_close_price
            ote_entry = round(bar_close_price + (0.50 * disp_range), digits)
            max_chase_price = round(bar_close_price - (max_chase_pips * pip), digits)
            valid_zone_low = round(max_chase_price, digits)
            valid_zone_high = round(ote_entry, digits)

            # ICT 5M Precision Entry Trigger (lower-timeframe confirmation)
            lf_trigger = fetch_5m_entry_trigger(
                ticker, "SHORT", valid_zone_low, valid_zone_high, bar_close_price, pip, digits
            )
            # If 5M trigger found a better price, prefer it
            if lf_trigger and lf_trigger.get("precision_entry"):
                entry = lf_trigger["precision_entry"]
                sl_dist = float(max(min_sl_dist, min(max_sl_dist, float(ob_high + 0.50 * atr) - entry)))
                stop_loss = float(entry + sl_dist)
                take_profit, calc_rr, pool_name = find_ict_liquidity_target(df, entry, sl_dist, is_long=False)

            # --- Signal Score Calculation (0-100) ---
            sig_score = 92
            if lf_trigger:
                if lf_trigger["confidence"] >= 90:
                    sig_score += 8
                elif lf_trigger["confidence"] >= 80:
                    sig_score += 5
                else:
                    sig_score += 2
            sig_score = round(sig_score * session_multiplier)
            if adx_val < 20.0:
                sig_score = min(100, sig_score + 2)
            sl_pips_val = round(sl_dist / pip, 1)
            if sl_pips_val > 30.0 and pair_name != "XAUUSD":
                sig_score = max(60, sig_score - 5)
            sig_score = min(100, max(50, sig_score))

            signals.append({
                "id": sig_id,
                "pair": pair_name,
                "timeframe": tf.upper(),
                "direction": "SHORT",
                "time": bar_time_str,
                "entry": round(entry, digits),
                "bar_close_price": round(bar_close_price, digits),
                "ote_entry": ote_entry,
                "valid_zone_low": valid_zone_low,
                "valid_zone_high": valid_zone_high,
                "max_chase_price": max_chase_price,
                "max_chase_pips": max_chase_pips,
                "stop_loss": round(stop_loss, digits),
                "take_profit": round(take_profit, digits),
                "sl_pips": sl_pips_val,
                "tp_pips": round((entry - take_profit) / pip, 1),
                "rr": calc_rr,
                "target_type": pool_name,
                "donchian_len": donch_len,
                "rsi": float(round(closed_bar["rsi"], 1)),
                "atr": float(round(atr / pip, 1)),
                "adx": float(round(adx_val, 1)),
                "adx_regime": adx_regime,
                "session": session_name,
                "session_icon": session_icon,
                "score": sig_score,
                "lf_trigger": lf_trigger
            })
            state["alerted_signals"].append(sig_id)
            
    return signals


def format_alert_message(sig: dict) -> str:
    # Format asset display name
    pair = sig["pair"]
    gold_basis_note = ""
    if pair == "XAUUSD":
        display_pair = "GOLD (XAU/USD)"
        gold_basis_note = (
            f"• <b>Market Feed:</b> <code>Spot Gold (XAU/USD) — Calibrated Live Institutional Feed</code>\n"
            f"• <b>Pip Scale:</b> <code>$0.10 / pip ($1.00 move = 10 pips)</code>\n\n"
        )
    elif len(pair) == 6:
        display_pair = f"{pair[:3]}/{pair[3:]}"
    else:
        display_pair = pair

    is_long = sig["direction"] == "LONG"
    icon = "🟢" if is_long else "🔴"
    action_text = "BUY / LONG" if is_long else "SELL / SHORT"
    structure_text = "Origin Order Block Support" if is_long else "Origin Order Block Resistance"
    trend_text = "Bullish (EMA 20 above EMA 50)" if is_long else "Bearish (EMA 20 below EMA 50)"
    sl_sign = "-"
    tp_sign = "+"

    tf_label = "1-HOUR (1H)" if sig["timeframe"] == "1H" else "15-MINUTE (15M)"
    setup_len = sig.get("donchian_len", 20)

    # --- 5M Precision Entry Block ---
    lf = sig.get("lf_trigger")  # May be None if no 5M trigger found
    if lf:
        lf_block = (
            f"\n<b>⚡ 5M PRECISION ENTRY TRIGGER</b>\n"
            f"• <b>Pattern:</b> <b>{lf['trigger_type']}</b> (Confidence: {lf['confidence']}%)\n"
            f"• <b>Action:</b> {lf['action_text']}\n"
            f"• <b>5M Bar Closed:</b> <code>{lf['bar_close_time']}</code>\n"
            f"• <b>⚠️ Use this entry NOW</b> — 5M structure confirmed 15M signal\n\n"
        )
        immediate_entry = lf["precision_entry"]
    else:
        lf_block = (
            f"\n<b>⚡ 5M ENTRY TRIGGER</b>\n"
            f"• No 5M reversal pattern detected yet in OTE zone\n"
            f"• Wait for next 5M bar close near <code>{sig.get('ote_entry', sig['entry'])}</code>\n"
            f"  and look for rejection wick or engulfing before entering\n\n"
        )
        immediate_entry = sig["entry"]

    return (
        f"{icon} <b>NEW TRADE SIGNAL · {display_pair}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🧭 <b>Direction:</b> <b>{action_text}</b>\n"
        f"⏱ <b>Timeframe:</b> <b>{tf_label}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>🚀 IMMEDIATE ENTRY PRICE: <code>{immediate_entry}</code></b>\n"
        f"<i>Enter at market within 3 minutes of this alert</i>\n\n"
        f"{lf_block}"
        f"<b>📋 ICT ENTRY ZONE (15M)</b>\n"
        f"• <b>15M Bar Close:</b> <code>{sig['entry']}</code>\n"
        f"• <b>OTE Zone (50% CE):</b> <code>{sig.get('ote_entry', sig['entry'])}</code> <i>(ideal pullback entry)</i>\n"
        f"• <b>Valid Zone:</b> <code>{sig.get('valid_zone_low', sig['entry'])} — {sig.get('valid_zone_high', sig['entry'])}</code>\n"
        f"• <b>Max Chase:</b> <code>{sig.get('max_chase_price', sig['entry'])}</code> <i>(hard limit — skip beyond this)</i>\n\n"
        f"<b>🎯 TARGETS & RISK</b>\n"
        f"• <b>Stop Loss:</b> <code>{sig['stop_loss']}</code> <i>({sl_sign}{sig['sl_pips']} pips)</i>\n"
        f"• <b>Take Profit:</b> <code>{sig['take_profit']}</code> <i>({tp_sign}{sig['tp_pips']} pips · {sig.get('target_type', 'Target')})</i>\n"
        f"• <b>Risk / Reward:</b> <b>1 : {sig['rr']}</b>\n"
        f"• <b>Suggested Risk:</b> <b>0.5% Equity (Max DD Guard: &lt;6.0% Cap)</b>\n\n"
        f"{gold_basis_note}"
        f"<b>🔬 CONFLUENCE MODEL</b>\n"
        f"• <b>Setup:</b> {setup_len}-Bar Structural Breakout\n"
        f"• <b>Structure:</b> {structure_text}\n"
        f"• <b>Liquidity Target:</b> {sig.get('target_type', 'BSL/SSL Pool')}\n"
        f"• <b>Trend Alignment:</b> {trend_text}\n"
        f"• <b>Momentum RSI:</b> <code>{sig['rsi']}</code> (Optimal Zone)\n"
        f"• <b>Volatility ATR:</b> <code>{sig['atr']}</code> pips\n"
        f"• <b>ADX Regime:</b> <code>{sig.get('adx', 'N/A')}</code> — {sig.get('adx_regime', 'N/A')}\n"
        f"• <b>Session:</b> {sig.get('session_icon', '')} {sig.get('session', 'Active Session')}\n"
        f"• <b>Signal Score:</b> <b>{sig['score']} / 100</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕒 <b>Confirmed Bar:</b> <code>{sig['time']}</code>\n"
        f"💡 <b>Execution Rules:</b>\n"
        f"1️⃣ <b>Immediate (0–3 min):</b> Enter at <code>{immediate_entry}</code> — market order NOW.\n"
        f"2️⃣ <b>Delayed (3–10 min):</b> If price is inside zone <code>{sig.get('valid_zone_low', sig['entry'])} — {sig.get('valid_zone_high', sig['entry'])}</code>, enter market.\n"
        f"3️⃣ <b>Late / Missed:</b> Set limit at OTE <code>{sig.get('ote_entry', sig['entry'])}</code> — wait for pullback. Never chase beyond <code>{sig.get('max_chase_price', sig['entry'])}</code>."
    )


def run_scan_cycle():
    """Performs one full scan cycle across all pairs and timeframes."""
    state = load_state()
    records = load_trade_records()
    total_signals = 0

    # 1. Monitor active floating positions for Take Profit / Stop Loss hits
    check_active_trades(records)
    active_pairs = set(records.get("active_trades", {}).keys())
    
    logger.info(f"Starting scan cycle. Active locked pairs: {list(active_pairs)}")
    
    for pair_name, cfg in SYMBOLS.items():
        # Enforce strict single-trade lock: skip scanning if pair is already in a trade
        if pair_name in active_pairs:
            logger.info(f"Skipping {pair_name}: Active position currently floating.")
            continue

        for tf in TIMEFRAMES:
            try:
                signals = scan_pair_timeframe(pair_name, cfg, tf, state)
                for sig in signals:
                    total_signals += 1
                    logger.info(f"==> NEW SIGNAL: {sig['pair']} {sig['timeframe']} {sig['direction']} @ {sig['entry']}")
                    msg = format_alert_message(sig)
                    send_telegram_alert(msg)

                    # Register newly opened active trade as OPEN market execution
                    bar_time = sig.get("time") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    new_trade_entry = {
                        "trade_id": sig["id"],
                        "pair": sig["pair"],
                        "symbol": pair_name,
                        "ticker": cfg["ticker"],
                        "direction": sig["direction"],
                        "timeframe": sig["timeframe"],
                        "entry": sig["entry"],
                        "stop_loss": sig["stop_loss"],
                        "take_profit": sig["take_profit"],
                        "sl_pips": sig["sl_pips"],
                        "tp_pips": sig["tp_pips"],
                        "rr": sig["rr"],
                        "pip": cfg["pip"],
                        "digits": cfg["digits"],
                        "opened_at": bar_time,
                        "status": "OPEN",
                        "filled_at": bar_time
                    }
                    records.setdefault("active_trades", {})[pair_name] = new_trade_entry
                    save_trade_records(records)
                    # Do NOT sync_worker here — a final sync at end of run_scan_cycle covers it
                    active_pairs.add(pair_name)
                    break  # Only 1 trade per pair

            except Exception as e:
                logger.error(f"Error scanning {pair_name} ({tf}): {e}")
                
    save_state(state)
    save_trade_records(records)
    sync_worker(records)  # Single final sync — covers all new trades and resolutions
    logger.info(f"Scan cycle complete. Dispatched {total_signals} new signal(s).")
    return total_signals


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        df = fetch_candles("EURUSD=X", "15m", range_days="2d")
        if not df.empty:
            df = compute_indicators(df, 20)
            c = df.iloc[-1]
            live_price = round(c["close"], 5)
            atr = c["atr"]
            sl = round(live_price - (1.5 * atr), 5)
            tp = round(live_price + (1.5 * atr * 1.75), 5)
            test_sig = {
                "pair": "EURUSD",
                "timeframe": "15M",
                "direction": "LONG",
                "entry": live_price,
                "stop_loss": sl,
                "take_profit": tp,
                "sl_pips": round((live_price - sl) / 0.0001, 1),
                "tp_pips": round((tp - live_price) / 0.0001, 1),
                "rr": 1.75,
                "rsi": round(c["rsi"], 1),
                "atr": round(atr / 0.0001, 1),
                "score": 95,
                "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            }
        else:
            test_sig = {
                "pair": "EURUSD", "timeframe": "15M", "direction": "LONG",
                "entry": 1.1382, "stop_loss": 1.1350, "take_profit": 1.1438,
                "sl_pips": 32.0, "tp_pips": 56.0, "rr": 1.75, "rsi": 54.0,
                "atr": 12.0, "score": 95, "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            }
        msg = format_alert_message(test_sig)
        send_telegram_alert(msg)
        print("Real-time live test alert dispatched to Telegram.")
    elif len(sys.argv) > 1 and sys.argv[1] == "--loop":
        logger.info("Running market scanner in 24/7 background loop...")
        while True:
            try:
                run_scan_cycle()
            except Exception as e:
                logger.error(f"Loop cycle error: {e}")
            # Wait 60 seconds before checking next interval
            time.sleep(60)
    else:
        # Default: Single scan execution (ideal for cron or test)
        run_scan_cycle()
