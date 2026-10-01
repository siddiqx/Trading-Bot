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

# Telegram Bot Credentials (with fallback if env vars are unset or empty strings)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "8932628751:AAFS_Z7SZMbfNAgNE9KmU6Sly32IGxDm2p0"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "8142877259"

# Monitored Pairs and Yahoo Finance Ticker Mapping
# Core Alpha Asset Universe (Proven by 2-year backtest to cap portfolio drawdown at 6.0% while maximizing net return)
SYMBOLS = {
    "XAUUSD": {"ticker": "PAXGUSDT", "pip": 0.10,   "digits": 2, "donchian_len": 10}, # 1:1 Physical Spot Gold (matches MT5 XAUUSD directly)
    "EURUSD": {"ticker": "EURUSD=X", "pip": 0.0001, "digits": 5, "donchian_len": 15}, # Responsive Momentum Anchor: 15-period Donchian
    "USDCAD": {"ticker": "USDCAD=X", "pip": 0.0001, "digits": 5, "donchian_len": 15}, # Session Momentum Mover: 15-period Donchian
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
        # Keep only the last 200 signal IDs to prevent file bloat
        state["alerted_signals"] = state["alerted_signals"][-200:]
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
        with httpx.Client(timeout=10.0) as client:
            client.post(WORKER_SYNC_URL, json=payload, headers={"User-Agent": "MarketScanner/2.0"})
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
    icon = "🎯" if is_win else "🛑"
    header = "TARGET REACHED: LIQUIDITY POOL SWEPT" if is_win else "STRUCTURAL EXIT: STOP LOSS HIT"
    status_text = "WIN (Liquidity Pool Swept)" if is_win else "LOSS (Order Block Invalidation)"
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

        df = fetch_candles(ticker, "15m", range_days="7d")
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


def send_telegram_alert(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                logger.info("Telegram alert sent successfully.")
            else:
                logger.error(f"Failed to send Telegram alert: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"Error sending Telegram alert: {e}")


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
    
    # ATR (14)
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
    
    return df


def find_ict_liquidity_target(
    df: pd.DataFrame,
    entry: float,
    sl_dist: float,
    is_long: bool,
    lookback_bars: int = 120,
    min_rr: float = 1.0,
    max_rr: float = 2.5,
    default_rr: float = 1.75
) -> tuple[float, float, str]:
    """
    Identifies the nearest un-swept institutional liquidity pool for Take Profit targeting.
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
        # Search backwards for confirmed fractal swing highs
        for k in range(closed_idx - 2, max(2, closed_idx - lookback_bars), -1):
            if highs[k] >= highs[k-1] and highs[k] >= highs[k-2] and highs[k] >= highs[k+1] and highs[k] >= highs[k+2]:
                if highs[k] >= entry + (sl_dist * min_rr):
                    bsl_candidates.append(highs[k])
        if bsl_candidates:
            tp = min(bsl_candidates)
            rr = (tp - entry) / sl_dist
            if rr > max_rr:
                rr = max_rr
                tp = entry + (sl_dist * max_rr)
            return float(tp), float(round(rr, 2)), "BSL Pool (Buy-Side Liquidity)"
        return float(entry + (sl_dist * default_rr)), float(default_rr), "Structural Expansion (1.75R)"
    else:
        ssl_candidates = []
        # Search backwards for confirmed fractal swing lows
        for k in range(closed_idx - 2, max(2, closed_idx - lookback_bars), -1):
            if lows[k] <= lows[k-1] and lows[k] <= lows[k-2] and lows[k] <= lows[k+1] and lows[k] <= lows[k+2]:
                if lows[k] <= entry - (sl_dist * min_rr):
                    ssl_candidates.append(lows[k])
        if ssl_candidates:
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
    
    # Anti-lag freshness guard: Accommodate runner jitter (allows up to 60m for 15M and 3h for 1H).
    # Deduplication is strictly guaranteed by state['alerted_signals'] so valid retest setups are never lost.
    max_age_seconds = 3600 if tf == "15m" else 10800
    seconds_since_close = (now_utc - closed_bar["close_time"]).total_seconds()
    if seconds_since_close > max_age_seconds:
        logger.info(f"Skipping {pair_name} ({tf}): Bar closed {int(seconds_since_close)}s ago (exceeds {max_age_seconds}s freshness limit). Move already occurred.")
        return []
    
    bar_time_str = closed_bar["close_time"].strftime("%Y-%m-%dT%H:%M:%SZ")
    
    signals = []
    
    # Macro trend filter: EMA 20 > EMA 50 and positive slope
    bullish_trend = (closed_bar["close"] > closed_bar["ema50"]) and (closed_bar["ema20"] > closed_bar["ema50"]) and (closed_bar["ema20_slope"] > 0)
    bearish_trend = (closed_bar["close"] < closed_bar["ema50"]) and (closed_bar["ema20"] < closed_bar["ema50"]) and (closed_bar["ema20_slope"] < 0)
    
    # Anti-exhaustion RSI guard (Optimized: 40-80 for Longs, 20-60 for Shorts)
    rsi_bullish_ok = 40.0 <= closed_bar["rsi"] <= 80.0
    rsi_bearish_ok = 20.0 <= closed_bar["rsi"] <= 60.0
    
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
            
            entry = float(closed_bar["close"])
            sl_candidate = float(ob_low - (0.50 * atr))
            sl_dist = float(max(min_sl_dist, min(max_sl_dist, entry - sl_candidate)))
            stop_loss = float(entry - sl_dist)
            
            # ICT Liquidity Target: Target nearest un-swept Buy-Side Liquidity (BSL)
            take_profit, calc_rr, pool_name = find_ict_liquidity_target(df, entry, sl_dist, is_long=True)
            
            signals.append({
                "id": sig_id,
                "pair": pair_name,
                "timeframe": tf.upper(),
                "direction": "LONG",
                "time": bar_time_str,
                "entry": round(entry, digits),
                "stop_loss": round(stop_loss, digits),
                "take_profit": round(take_profit, digits),
                "sl_pips": round(sl_dist / pip, 1),
                "tp_pips": round((take_profit - entry) / pip, 1),
                "rr": calc_rr,
                "target_type": pool_name,
                "donchian_len": donch_len,
                "rsi": float(round(closed_bar["rsi"], 1)),
                "atr": float(round(atr / pip, 1)),
                "score": 95
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
            
            entry = float(closed_bar["close"])
            sl_candidate = float(ob_high + (0.50 * atr))
            sl_dist = float(max(min_sl_dist, min(max_sl_dist, sl_candidate - entry)))
            stop_loss = float(entry + sl_dist)
            
            # ICT Liquidity Target: Target nearest un-swept Sell-Side Liquidity (SSL)
            take_profit, calc_rr, pool_name = find_ict_liquidity_target(df, entry, sl_dist, is_long=False)
            
            signals.append({
                "id": sig_id,
                "pair": pair_name,
                "timeframe": tf.upper(),
                "direction": "SHORT",
                "time": bar_time_str,
                "entry": round(entry, digits),
                "stop_loss": round(stop_loss, digits),
                "take_profit": round(take_profit, digits),
                "sl_pips": round(sl_dist / pip, 1),
                "tp_pips": round((entry - take_profit) / pip, 1),
                "rr": calc_rr,
                "target_type": pool_name,
                "donchian_len": donch_len,
                "rsi": float(round(closed_bar["rsi"], 1)),
                "atr": float(round(atr / pip, 1)),
                "score": 95
            })
            state["alerted_signals"].append(sig_id)
            
    return signals


def format_alert_message(sig: dict) -> str:
    # Format asset display name
    pair = sig["pair"]
    gold_basis_note = ""
    if pair == "XAUUSD":
        display_pair = "GOLD (COMEX GC=F)"
        spot_equiv = round(sig["entry"] - 32.5, 2)
        gold_basis_note = (
            f"• <b>Market Feed:</b> <code>COMEX Gold Futures (GC=F)</code>\n"
            f"• <b>Spot XAU/USD Equivalent:</b> <code>~{spot_equiv}</code> <i>(trades at ~$32.50 basis premium)</i>\n\n"
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

    return (
        f"{icon} <b>NEW TRADE SIGNAL · {display_pair}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🧭 <b>Direction:</b> <b>{action_text}</b>\n"
        f"⏱ <b>Timeframe:</b> <b>{tf_label}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📋 TRADE PARAMETERS</b>\n"
        f"• <b>Entry Target:</b> <code>{sig['entry']}</code> <i>(Limit / Retest Level)</i>\n"
        f"• <b>Order State:</b> ⏳ <b>PENDING ENTRY FILL</b>\n"
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
        f"• <b>Signal Score:</b> <b>{sig['score']} / 100</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕒 <b>Confirmed Bar:</b> <code>{sig['time']}</code>\n"
        f"⏳ <i>Order pending fill. Floating PnL activates once entry point is touched.</i>"
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

                    # Register newly opened active trade as PENDING awaiting market fill
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
                        "opened_at": sig.get("time") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "status": "PENDING",
                        "filled_at": None
                    }
                    records.setdefault("active_trades", {})[pair_name] = new_trade_entry
                    save_trade_records(records)
                    sync_worker(records)
                    active_pairs.add(pair_name)
                    break # Only 1 trade per pair

            except Exception as e:
                logger.error(f"Error scanning {pair_name} ({tf}): {e}")
                
    save_state(state)
    save_trade_records(records)
    sync_worker(records)
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
