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
SYMBOLS = {
    "EURUSD": {"ticker": "EURUSD=X", "pip": 0.0001, "digits": 5},
    "USDJPY": {"ticker": "USDJPY=X", "pip": 0.01,   "digits": 3},
    "USDCAD": {"ticker": "USDCAD=X", "pip": 0.0001, "digits": 5},
    "USDCHF": {"ticker": "USDCHF=X", "pip": 0.0001, "digits": 5},
    "AUDUSD": {"ticker": "AUDUSD=X", "pip": 0.0001, "digits": 5},
    "XAUUSD": {"ticker": "GC=F",     "pip": 0.10,   "digits": 2}, # Gold Futures tracking Spot XAUUSD
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
        payload = {
            "event": "sync_trades",
            "active_trades": records.get("active_trades", {}),
            "completed_trades": records.get("completed_trades", [])
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
    header = "TARGET REACHED: TAKE PROFIT HIT" if is_win else "STRUCTURAL EXIT: STOP LOSS HIT"
    status_text = "WIN (Target Achieved)" if is_win else "LOSS (Order Block Invalidation)"
    sign = "+" if realized_pips >= 0 else ""
    r_sign = "+" if realized_r >= 0 else ""
    pair_name = trade.get('pair', trade.get('symbol'))

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

    for pair, trade in list(active.items()):
        ticker = trade.get("ticker")
        if not ticker:
            continue

        df = fetch_candles(ticker, "15m", range_days="3d")
        if df.empty or len(df) < 5:
            continue

        opened_at_str = trade.get("opened_at")
        if opened_at_str:
            try:
                open_ts = pd.to_datetime(opened_at_str)
                df_trade = df[df["time"] >= open_ts]
            except Exception:
                df_trade = df.iloc[-8:]
        else:
            df_trade = df.iloc[-8:]

        if df_trade.empty:
            df_trade = df.iloc[-2:]

        is_long = (trade.get("direction") == "LONG")
        tp = trade["take_profit"]
        sl = trade["stop_loss"]

        hit_tp = False
        hit_sl = False

        # Chronological bar-by-bar evaluation to accurately determine which price extreme was touched first
        for row in df_trade.itertuples():
            b_high = row.high
            b_low = row.low

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

        if hit_tp:
            exit_price = tp
            realized_pips = trade.get("tp_pips", 0.0)
            realized_r = trade.get("rr", 1.75)
            outcome = "WIN"

            logger.info(f"==> TRADE RESOLVED (TP): {pair} {trade.get('direction')} (+{realized_pips} pips)")

            completed_record = {
                **trade,
                "exit_price": exit_price,
                "outcome": outcome,
                "realized_pips": round(realized_pips, 1),
                "realized_r": round(realized_r, 2),
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
                "exit_price": exit_price,
                "outcome": outcome,
                "realized_pips": round(realized_pips, 1),
                "realized_r": round(realized_r, 2),
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

    if resolved_pairs:
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
    """Fetch candles from Yahoo Finance chart API."""
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


def scan_pair_timeframe(pair_name: str, config: dict, tf: str, state: dict) -> list:
    """Scans a single pair and timeframe for confirmed structural breakout setups."""
    ticker = config["ticker"]
    pip = config["pip"]
    digits = config["digits"]
    
    df = fetch_candles(ticker, tf, range_days="7d")
    if df.empty or len(df) < 50:
        return []
    
    df = compute_indicators(df, donchian_len=20)
    
    # In Yahoo Finance, bar timestamp is the OPEN time.
    # Compute the true CLOSE time for each bar.
    tf_delta = pd.Timedelta(minutes=15) if tf == "15m" else pd.Timedelta(hours=1)
    df["close_time"] = df["time"] + tf_delta
    
    now_utc = datetime.now(timezone.utc)
    
    # Strictly select bars that have finished closing
    closed_bars = df[df["close_time"] <= now_utc]
    if len(closed_bars) < 30:
        return []
    
    closed_bar = closed_bars.iloc[-1]
    prev_bar = closed_bars.iloc[-2]
    
    # Freshness check: only alert if the candle closed recently
    max_age_seconds = 1800 if tf == "15m" else 3600
    seconds_since_close = (now_utc - closed_bar["close_time"]).total_seconds()
    if seconds_since_close > max_age_seconds:
        return []
    
    bar_time_str = closed_bar["close_time"].strftime("%Y-%m-%dT%H:%M:%SZ")
    
    signals = []
    
    # Macro trend filter: EMA 20 > EMA 50 and positive slope
    bullish_trend = (closed_bar["close"] > closed_bar["ema50"]) and (closed_bar["ema20"] > closed_bar["ema50"]) and (closed_bar["ema20_slope"] > 0)
    bearish_trend = (closed_bar["close"] < closed_bar["ema50"]) and (closed_bar["ema20"] < closed_bar["ema50"]) and (closed_bar["ema20_slope"] < 0)
    
    # Anti-exhaustion RSI guard (Avoid chasing overbought/oversold)
    rsi_bullish_ok = 45.0 <= closed_bar["rsi"] <= 75.0
    rsi_bearish_ok = 25.0 <= closed_bar["rsi"] <= 55.0
    
    # 20-period Donchian Breakout on completed bar
    long_breakout = (closed_bar["close"] > closed_bar["donch_high"]) and (prev_bar["close"] <= prev_bar["donch_high"])
    short_breakout = (closed_bar["close"] < closed_bar["donch_low"]) and (prev_bar["close"] >= prev_bar["donch_low"])
    
    atr = closed_bar["atr"]
    min_sl_dist = 18.0 * pip
    max_sl_dist = 60.0 * pip
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
            
            entry = closed_bar["close"]
            sl_candidate = ob_low - (0.50 * atr)
            sl_dist = max(min_sl_dist, min(max_sl_dist, entry - sl_candidate))
            stop_loss = entry - sl_dist
            take_profit = entry + (sl_dist * rr_ratio)
            
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
                "rr": rr_ratio,
                "rsi": round(closed_bar["rsi"], 1),
                "atr": round(atr / pip, 1),
                "score": 92
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
            
            entry = closed_bar["close"]
            sl_candidate = ob_high + (0.50 * atr)
            sl_dist = max(min_sl_dist, min(max_sl_dist, sl_candidate - entry))
            stop_loss = entry + sl_dist
            take_profit = entry - (sl_dist * rr_ratio)
            
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
                "rr": rr_ratio,
                "rsi": round(closed_bar["rsi"], 1),
                "atr": round(atr / pip, 1),
                "score": 92
            })
            state["alerted_signals"].append(sig_id)
            
    return signals


def format_alert_message(sig: dict) -> str:
    # Format asset display name
    pair = sig["pair"]
    if pair == "XAUUSD":
        display_pair = "GOLD (XAU/USD)"
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

    return (
        f"{icon} <b>NEW TRADE SIGNAL · {display_pair}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🧭 <b>Direction:</b> <b>{action_text}</b>\n"
        f"⏱ <b>Timeframe:</b> <b>{tf_label}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>📋 TRADE PARAMETERS</b>\n"
        f"• <b>Entry Price:</b> <code>{sig['entry']}</code>\n"
        f"• <b>Stop Loss:</b> <code>{sig['stop_loss']}</code> <i>({sl_sign}{sig['sl_pips']} pips)</i>\n"
        f"• <b>Take Profit:</b> <code>{sig['take_profit']}</code> <i>({tp_sign}{sig['tp_pips']} pips)</i>\n"
        f"• <b>Risk / Reward:</b> <b>1 : {sig['rr']}</b>\n"
        f"• <b>Suggested Risk:</b> <b>1.0% Equity</b>\n\n"
        f"<b>🔬 CONFLUENCE MODEL</b>\n"
        f"• <b>Setup:</b> 20-Bar Structural Breakout\n"
        f"• <b>Structure:</b> {structure_text}\n"
        f"• <b>Trend Alignment:</b> {trend_text}\n"
        f"• <b>Momentum RSI:</b> <code>{sig['rsi']}</code> (Optimal Zone)\n"
        f"• <b>Volatility ATR:</b> <code>{sig['atr']}</code> pips\n"
        f"• <b>Signal Score:</b> <b>{sig['score']} / 100</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🕒 <b>Confirmed Bar:</b> <code>{sig['time']}</code>\n"
        f"⚠️ <i>Bar strictly closed. Execute with strict risk discipline.</i>"
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

                    # Register newly opened active trade into ledger
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
                        "opened_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "status": "OPEN"
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
