#!/usr/bin/env python3
"""
Standalone 24/7 Market Scanner for Spot Gold (XAUUSD / GC=F).
Dedicated Isolated Satellite Engine.

Operates strictly decoupled from the primary Forex market scanner:
1. Uses institutional commodity contract geometry (100 oz / lot, $100/point).
2. Computes the Dual-Timeframe CCRS USD Macro Factor (|Z_USD| >= 1.75σ) on completed 1H bars.
3. Evaluates 1H EMA20 retests and 10-bar Donchian liquidity sweeps on completed bars.
4. Dynamically sizes positions based on 2.0x ATR stops ($20.00 - $35.00/oz).
5. Enforces Volatility Cushion Trailing (+1.20R halving, +1.50R locking, +2.00R runner).
6. Cross-Engine Correlation Interlock: Prevents exceeding Max 2 net USD exposure
   across both Forex and Gold.
7. Rollover Blackout (20:30 - 22:30 UTC) & Friday 16:00 UTC weekend flat rule.
8. Active Floating Trade Management runs unconditionally every cycle during market hours.
9. Synchronizes ledger to Cloudflare Worker KV.
"""

import sys
import os
import time
import json
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import httpx
import numpy as np
import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from satellite.gold_config import (
    GOLD_SYMBOL,
    GOLD_TICKER,
    CONTRACT_SIZE_OZ,
    POINT_VALUE_PER_LOT,
    MIN_LOT,
    LOT_STEP,
    MAX_LOT,
    REFERENCE_ACCOUNT_EQUITY,
    PROP_FIRM_RISK_PCT,
    REFERENCE_RISK_BUDGET_USD,
    ATR_PERIOD,
    ATR_MULTIPLIER,
    MIN_SL_POINTS,
    MAX_SL_POINTS,
    BASE_RISK_REWARD_RATIO,
    VOLATILITY_CUSHION_ENABLED,
    VOLATILITY_CUSHION_TIER1_R,
    VOLATILITY_CUSHION_TIER2_R,
    VOLATILITY_CUSHION_RUNNER_R,
    CCRS_LOOKBACK_HOURS,
    CCRS_Z_WINDOW_HOURS,
    CCRS_USD_THRESHOLD,
    MAX_HOLD_HOURS,
    DAILY_LOSS_CIRCUIT_BREAKER_COUNT,
    POST_LOSS_COOLDOWN_MINUTES,
    ACTIVE_TRADING_HOURS,
    TRANSACTION_COSTS,
    GOLD_TRADE_RECORDS_PATH,
    FOREX_TRADE_RECORDS_PATH,
    STRATEGY_NAME,
    STRATEGY_VERSION,
)
from satellite.gold_validator import (
    calculate_gold_position_size,
    is_rollover_blackout_active,
    is_friday_weekend_cutoff,
    check_correlation_interlock,
    get_gold_usd_bias,
)
from market_scanner import is_forex_market_open

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GOLD] [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("GoldScanner")

TELEGRAM_BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
WORKER_SYNC_URL = "https://tradingview-telegram-relay.siddiqsiddiq00012.workers.dev/"


def send_telegram_alert(text: str, max_retries: int = 3) -> bool:
    """Dispatches Telegram notifications for Gold signals and exits with 429 backoff."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        logger.info(f"[TELEGRAM SUPPRESSED — test mode] {text[:120]}")
        return True
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            logger.warning("Telegram credentials not configured in environment. Outbound alert suppressed.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    logger.info("Telegram alert delivered successfully.")
                    return True
                elif resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 5))
                    logger.warning(f"Telegram rate limited. Waiting {retry_after}s (attempt {attempt+1}/{max_retries})")
                    time.sleep(retry_after)
                else:
                    logger.error(f"Failed to send Telegram alert: HTTP {resp.status_code} {resp.text[:200]}")
                    return False  # Non-retriable client error
        except Exception as e:
            logger.error(f"Telegram dispatch error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    return False


def load_gold_records() -> Dict[str, Any]:
    """Loads state from data/gold_trade_records.json."""
    if not GOLD_TRADE_RECORDS_PATH.exists():
        initial = {"active_trades": {}, "completed_trades": [], "daily_losses": {}, "alerted_bars": []}
        save_gold_records(initial)
        return initial
    try:
        with open(GOLD_TRADE_RECORDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("active_trades", {})
            data.setdefault("completed_trades", [])
            data.setdefault("daily_losses", {})
            data.setdefault("alerted_bars", [])
            return data
    except Exception as e:
        logger.error(f"Error reading {GOLD_TRADE_RECORDS_PATH}: {e}")
        return {"active_trades": {}, "completed_trades": [], "daily_losses": {}, "alerted_bars": []}


def save_gold_records(records: Dict[str, Any]) -> None:
    """Saves state atomically to data/gold_trade_records.json."""
    GOLD_TRADE_RECORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = GOLD_TRADE_RECORDS_PATH.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    temp_path.replace(GOLD_TRADE_RECORDS_PATH)


def sync_gold_worker(records: Dict[str, Any]) -> None:
    """Syncs Gold trade state to Cloudflare Worker KV."""
    if not WORKER_SYNC_URL:
        return
    payload = {
        "event": "sync_gold_trades",
        "active_trades": records.get("active_trades", {}),
        "completed_trades": records.get("completed_trades", []),
        "daily_losses": records.get("daily_losses", {}),
    }
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.post(WORKER_SYNC_URL, json=payload, headers={"User-Agent": "GoldMarketScanner/1.0"})
            if r.status_code == 200:
                logger.info("Gold Worker sync successful.")
            else:
                logger.warning(f"Gold Worker sync returned HTTP {r.status_code}")
    except Exception as e:
        logger.warning(f"Could not sync Gold trades with Cloudflare worker: {e}")


def check_gold_loss_cooldown(records: Dict[str, Any], cooldown_minutes: float = POST_LOSS_COOLDOWN_MINUTES) -> Tuple[bool, float]:
    """Checks if a recent Gold stop-out requires a cooldown period before fresh entries."""
    completed = records.get("completed_trades", [])
    if not completed:
        return False, 0.0
    last_trade = completed[-1]
    if last_trade.get("net_pnl", 0) >= 0:
        return False, 0.0
    exit_time_str = last_trade.get("exit_time")
    if not exit_time_str:
        return False, 0.0
    try:
        exit_dt = datetime.fromisoformat(exit_time_str.replace("Z", "+00:00"))
        if exit_dt.tzinfo is None:
            exit_dt = exit_dt.replace(tzinfo=timezone.utc)
        now_dt = datetime.now(timezone.utc)
        elapsed = (now_dt - exit_dt).total_seconds() / 60.0
        if elapsed < cooldown_minutes:
            return True, round(cooldown_minutes - elapsed, 1)
    except Exception:
        pass
    return False, 0.0


def fetch_candles_1h(ticker: str, range_days: str = "30d") -> pd.DataFrame:
    """Fetches 1H candles from Yahoo Finance and calculates bar close times."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_days}&interval=1h"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"Fetch failed for {ticker}: HTTP {resp.status_code}")
                return pd.DataFrame()
            data = resp.json()
            result = data.get("chart", {}).get("result")
            if not result:
                return pd.DataFrame()
            chart = result[0]
            ts = chart.get("timestamp", [])
            q = chart.get("indicators", {}).get("quote", [{}])[0]
            if not ts or not q:
                return pd.DataFrame()
            df = pd.DataFrame({
                "time": ts,
                "open": q.get("open"),
                "high": q.get("high"),
                "low": q.get("low"),
                "close": q.get("close"),
                "volume": q.get("volume", [0] * len(ts)),
            }).dropna().reset_index(drop=True)
            df["time_dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df["close_time"] = df["time_dt"] + pd.Timedelta(hours=1)
            df = df.sort_values("time_dt").reset_index(drop=True)
            return df
    except Exception as e:
        logger.warning(f"Error fetching {ticker}: {e}")
        return pd.DataFrame()


def compute_ccrs_usd_factor(as_of: Optional[datetime] = None) -> Optional[float]:
    """
    Computes zero-lookahead USD Currency Factor Z-Score (Z_USD)
    derived from the 6 major Forex pairs over the 120h momentum / 200h Z window.
    Strictly filters for COMPLETED 1H candle bars (close_time <= as_of).
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    elif as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)

    forex_tickers = {
        "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "AUDUSD": "AUDUSD=X",
        "USDJPY": "USDJPY=X", "USDCAD": "USDCAD=X", "USDCHF": "USDCHF=X"
    }
    dfs = {}
    for p, tick in forex_tickers.items():
        df = fetch_candles_1h(tick, range_days="60d")
        if df.empty:
            logger.warning(f"Empty data for {p}. CCRS factor unavailable.")
            return None
        # Enforce completed bars
        df_completed = df[df["close_time"] <= as_of]
        if len(df_completed) < (CCRS_LOOKBACK_HOURS + CCRS_Z_WINDOW_HOURS):
            logger.warning(f"Insufficient completed 1H history for {p} ({len(df_completed)} bars). CCRS factor unavailable.")
            return None
        dfs[p] = df_completed.set_index("time_dt")["close"]

    close_df = pd.DataFrame(dfs).dropna()
    lb = CCRS_LOOKBACK_HOURS
    z_win = CCRS_Z_WINDOW_HOURS

    if len(close_df) < (lb + z_win):
        logger.warning(f"Aligned panel length ({len(close_df)}) < required ({lb + z_win}).")
        return None

    ret_eur = np.log(close_df["EURUSD"] / close_df["EURUSD"].shift(lb))
    ret_gbp = np.log(close_df["GBPUSD"] / close_df["GBPUSD"].shift(lb))
    ret_aud = np.log(close_df["AUDUSD"] / close_df["AUDUSD"].shift(lb))
    ret_jpy = -np.log(close_df["USDJPY"] / close_df["USDJPY"].shift(lb))
    ret_cad = -np.log(close_df["USDCAD"] / close_df["USDCAD"].shift(lb))
    ret_chf = -np.log(close_df["USDCHF"] / close_df["USDCHF"].shift(lb))
    ret_usd = -(ret_eur + ret_gbp + ret_aud + ret_jpy + ret_cad + ret_chf) / 6.0

    curr_returns = pd.DataFrame({
        "EUR": ret_eur, "GBP": ret_gbp, "AUD": ret_aud,
        "JPY": ret_jpy, "CAD": ret_cad, "CHF": ret_chf, "USD": ret_usd
    })
    z_scores = (curr_returns - curr_returns.rolling(z_win).mean()) / (curr_returns.rolling(z_win).std() + 1e-9)
    z_usd = z_scores["USD"].iloc[-1]
    return float(z_usd) if not np.isnan(z_usd) else None


def compute_gold_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Computes technical indicators on Gold 1H candle dataframe."""
    d = df.copy()
    d["ema20"] = d["close"].ewm(span=20, adjust=False).mean()
    d["ema50"] = d["close"].ewm(span=50, adjust=False).mean()
    d["ema20_slope"] = d["ema20"] - d["ema20"].shift(2)

    tr = np.maximum(
        d["high"] - d["low"],
        np.maximum(
            np.abs(d["high"] - d["close"].shift(1)),
            np.abs(d["low"] - d["close"].shift(1))
        )
    )
    d["atr14"] = pd.Series(tr).rolling(ATR_PERIOD).mean().bfill()

    delta = d["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-9)
    d["rsi14"] = (100 - (100 / (1 + rs))).bfill()

    d["donch_h10"] = d["high"].shift(1).rolling(10).max()
    d["donch_l10"] = d["low"].shift(1).rolling(10).min()
    d["donch_h20"] = d["high"].shift(1).rolling(20).max()
    d["donch_l20"] = d["low"].shift(1).rolling(20).min()

    # 4H Macro Trend Confluence
    df_idx = d.set_index("time_dt")
    df_4h = df_idx.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna().reset_index()
    df_4h["ema20_4h"] = df_4h["close"].ewm(span=20, adjust=False).mean()
    df_4h["ema50_4h"] = df_4h["close"].ewm(span=50, adjust=False).mean()
    df_4h["bull_4h"] = df_4h["ema20_4h"] > df_4h["ema50_4h"]
    df_4h["bear_4h"] = df_4h["ema20_4h"] < df_4h["ema50_4h"]

    d["h4_time"] = d["time_dt"].dt.floor("4h") - pd.Timedelta(hours=4)
    d["bull_4h"] = d["h4_time"].map(dict(zip(df_4h["time_dt"], df_4h["bull_4h"]))).fillna(True)
    d["bear_4h"] = d["h4_time"].map(dict(zip(df_4h["time_dt"], df_4h["bear_4h"]))).fillna(True)

    return d


def check_active_gold_trades(records: Dict[str, Any], cur_bar: pd.Series, records_path: Optional[Path] = None) -> bool:
    """
    Evaluates exits, Volatility Cushion trailing transitions, and timeouts for active Gold positions.
    Returns True if any position was closed, False otherwise.
    """
    active = records.get("active_trades", {})
    if not active:
        return False

    now_utc = datetime.now(timezone.utc)
    cur_high = cur_bar["high"]
    cur_low = cur_bar["low"]
    cur_close = cur_bar["close"]
    today_str = now_utc.strftime("%Y-%m-%d")

    surviving = {}
    completed = records.get("completed_trades", [])
    daily_losses = records.get("daily_losses", {})
    daily_losses.setdefault(today_str, 0)
    closed_any = False

    for trade_id, tr in active.items():
        entry = tr["entry_price"]
        direction = tr["direction"]
        sl_price = tr["current_sl_price"]
        tp_price = tr["current_tp_price"]
        sl_dist = tr["init_sl_points"]
        lots = tr["lots"]
        oz = lots * CONTRACT_SIZE_OZ
        stage = tr.get("cushion_stage", 0)
        try:
            entry_time = datetime.fromisoformat(tr["entry_time"])
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)
        except Exception:
            entry_time = now_utc

        # Check Weekend Flat Cutoff
        if is_friday_weekend_cutoff(now_utc):
            raw_diff = (cur_close - entry) if direction == "LONG" else (entry - cur_close)
            friction = oz * TRANSACTION_COSTS["total_points"]
            net_pnl = (raw_diff * oz) - friction
            r_val = net_pnl / tr["monetary_risk_usd"]
            tr.update({
                "exit_price": cur_close,
                "exit_time": now_utc.isoformat(),
                "gross_pnl": raw_diff * oz,
                "friction": friction,
                "net_pnl": net_pnl,
                "r": r_val,
                "reason": "WEEKEND_FLAT",
            })
            completed.append(tr)
            closed_any = True
            send_exit_alert(tr, "WEEKEND FLAT CUTOFF")
            continue

        # Volatility Cushion Trailing Stop Update
        if VOLATILITY_CUSHION_ENABLED:
            if direction == "LONG":
                mfe = cur_high - entry
                if stage == 0 and mfe >= (VOLATILITY_CUSHION_TIER1_R * sl_dist):
                    tr["cushion_stage"] = 1
                    tr["current_sl_price"] = entry - (sl_dist * 0.50)  # Halve risk
                    logger.info(f"Gold Trade {trade_id}: Volatility Cushion Tier 1 hit (+1.20R). SL moved to {tr['current_sl_price']:.2f}")
                    if tr.get("ctrader_position_id"):
                        try:
                            from core.ctrader_executor import modify_ctrader_position
                            modify_ctrader_position(tr["ctrader_position_id"], stop_loss=tr["current_sl_price"], take_profit=tr["current_tp_price"])
                        except Exception as e:
                            logger.warning(f"cTrader SL update error: {e}")
                elif stage == 1 and mfe >= (VOLATILITY_CUSHION_TIER2_R * sl_dist):
                    tr["cushion_stage"] = 2
                    tr["current_sl_price"] = entry + (sl_dist * 0.50)  # Lock in +0.50R profit
                    tr["current_tp_price"] = entry + (sl_dist * VOLATILITY_CUSHION_RUNNER_R)  # Extend runner TP
                    logger.info(f"Gold Trade {trade_id}: Volatility Cushion Tier 2 hit (+1.50R). SL locked at {tr['current_sl_price']:.2f}, TP extended to {tr['current_tp_price']:.2f}")
                    if tr.get("ctrader_position_id"):
                        try:
                            from core.ctrader_executor import modify_ctrader_position
                            modify_ctrader_position(tr["ctrader_position_id"], stop_loss=tr["current_sl_price"], take_profit=tr["current_tp_price"])
                        except Exception as e:
                            logger.warning(f"cTrader SL/TP update error: {e}")
            else:
                mfe = entry - cur_low
                if stage == 0 and mfe >= (VOLATILITY_CUSHION_TIER1_R * sl_dist):
                    tr["cushion_stage"] = 1
                    tr["current_sl_price"] = entry + (sl_dist * 0.50)
                    logger.info(f"Gold Trade {trade_id}: Volatility Cushion Tier 1 hit (+1.20R). SL moved to {tr['current_sl_price']:.2f}")
                    if tr.get("ctrader_position_id"):
                        try:
                            from core.ctrader_executor import modify_ctrader_position
                            modify_ctrader_position(tr["ctrader_position_id"], stop_loss=tr["current_sl_price"], take_profit=tr["current_tp_price"])
                        except Exception as e:
                            logger.warning(f"cTrader SL update error: {e}")
                elif stage == 1 and mfe >= (VOLATILITY_CUSHION_TIER2_R * sl_dist):
                    tr["cushion_stage"] = 2
                    tr["current_sl_price"] = entry - (sl_dist * 0.50)
                    tr["current_tp_price"] = entry - (sl_dist * VOLATILITY_CUSHION_RUNNER_R)
                    logger.info(f"Gold Trade {trade_id}: Volatility Cushion Tier 2 hit (+1.50R). SL locked at {tr['current_sl_price']:.2f}, TP extended to {tr['current_tp_price']:.2f}")
                    if tr.get("ctrader_position_id"):
                        try:
                            from core.ctrader_executor import modify_ctrader_position
                            modify_ctrader_position(tr["ctrader_position_id"], stop_loss=tr["current_sl_price"], take_profit=tr["current_tp_price"])
                        except Exception as e:
                            logger.warning(f"cTrader SL/TP update error: {e}")

        sl_price = tr["current_sl_price"]
        tp_price = tr["current_tp_price"]

        hit_sl = False
        hit_tp = False
        exit_price = 0.0
        exit_reason = None

        # Pessimistic Intra-Candle Assumption: Stop Loss takes absolute precedence over Take Profit
        if direction == "LONG":
            if cur_low <= sl_price:
                hit_sl = True
                exit_price = sl_price
                exit_reason = "STOP_LOSS" if tr.get("cushion_stage", 0) < 2 else "PROFIT_LOCK"
            if cur_high >= tp_price:
                hit_tp = True
                if not hit_sl:
                    exit_price = tp_price
                    exit_reason = "TAKE_PROFIT"
        else:
            if cur_high >= sl_price:
                hit_sl = True
                exit_price = sl_price
                exit_reason = "STOP_LOSS" if tr.get("cushion_stage", 0) < 2 else "PROFIT_LOCK"
            if cur_low <= tp_price:
                hit_tp = True
                if not hit_sl:
                    exit_price = tp_price
                    exit_reason = "TAKE_PROFIT"

        # 48-Hour Timeout Exit
        hold_hours = (now_utc - entry_time).total_seconds() / 3600.0
        if not hit_sl and not hit_tp and hold_hours >= MAX_HOLD_HOURS:
            exit_price = cur_close
            exit_reason = "TIMEOUT"
            hit_sl = (exit_price < entry) if direction == "LONG" else (exit_price > entry)
            hit_tp = not hit_sl

        if hit_sl or hit_tp:
            dir_mult = 1 if direction == "LONG" else -1
            raw_diff = (exit_price - entry) * dir_mult
            gross_pnl = raw_diff * oz
            friction = oz * TRANSACTION_COSTS["total_points"]
            net_pnl = gross_pnl - friction
            r_val = net_pnl / tr["monetary_risk_usd"]

            if net_pnl < 0:
                daily_losses[today_str] += 1

            tr.update({
                "exit_price": exit_price,
                "exit_time": now_utc.isoformat(),
                "gross_pnl": gross_pnl,
                "friction": friction,
                "net_pnl": net_pnl,
                "r": r_val,
                "reason": exit_reason,
            })
            completed.append(tr)
            closed_any = True
            send_exit_alert(tr, exit_reason)
        else:
            surviving[trade_id] = tr

    records["active_trades"] = surviving
    records["completed_trades"] = completed
    records["daily_losses"] = daily_losses
    if records_path is not None:
        records_path.parent.mkdir(parents=True, exist_ok=True)
        with open(records_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
    else:
        save_gold_records(records)

    return closed_any


def send_signal_alert(sig: Dict[str, Any]) -> None:
    """Formats and dispatches Telegram notification for fresh Gold entries."""
    is_test = sig.get("is_test") or "TEST" in str(sig.get("id", "")).upper()
    test_banner = (
        "🧪 <b>[SYSTEM VERIFICATION TEST · NOT A LIVE TRADE]</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
    ) if is_test else ""
    text = (
        f"{test_banner}"
        f"🟡 <b>[GOLD SATELLITE ENGINE] FRESH SIGNAL</b>\n\n"
        f"• <b>Instrument:</b> {sig['symbol']} (Spot Gold)\n"
        f"• <b>Direction:</b> <b>{sig['direction']}</b>\n"
        f"• <b>Entry Price:</b> ${sig['entry_price']:.2f}\n"
        f"• <b>Stop Loss:</b> ${sig['sl_price']:.2f} ({sig['sl_points']:.1f} pts)\n"
        f"• <b>Take Profit:</b> ${sig['tp_price']:.2f} ({sig['tp_points']:.1f} pts · 1:{BASE_RISK_REWARD_RATIO:.2f})\n"
        f"• <b>Suggested Lots:</b> {sig['lots']:.2f} Lots ({sig['lots'] * 100:.0f} oz)\n"
        f"• <b>Allocated Risk:</b> ${sig['monetary_risk_usd']:.2f} ({PROP_FIRM_RISK_PCT:.2f}% on ${sig['equity']:.2f})\n\n"
        f"<b>Confluence Factors:</b>\n"
        f"• CCRS USD Factor: <b>{sig['z_usd']:+.2f}σ</b> (Threshold: ±{CCRS_USD_THRESHOLD:.2f}σ)\n"
        f"• Trigger Type: {sig['trigger_type']}\n"
        f"• 4H Trend Alignment: {'BULLISH' if sig['h4_bull'] else 'BEARISH'}\n"
        f"• Correlation Interlock: <b>APPROVED</b> (Net USD Exposure: {sig['usd_exposure']}/{sig['max_usd_exposure']})\n"
        f"• Volatility Cushion: Active (Tier 1: +1.2R risk halving, Tier 2: +1.5R profit lock)"
    )
    send_telegram_alert(text)


def send_exit_alert(tr: Dict[str, Any], reason: str) -> None:
    """Formats and dispatches Telegram notification for Gold trade exits."""
    emoji = "🟢" if tr["net_pnl"] > 0 else "🔴"
    text = (
        f"{emoji} <b>[GOLD SATELLITE ENGINE] TRADE CLOSED</b>\n\n"
        f"• <b>Instrument:</b> {tr['symbol']}\n"
        f"• <b>Direction:</b> {tr['direction']}\n"
        f"• <b>Entry:</b> ${tr['entry_price']:.2f} | <b>Exit:</b> ${tr['exit_price']:.2f}\n"
        f"• <b>Realized Net PnL:</b> <b>${tr['net_pnl']:+.2f} ({tr['r']:+.2f}R)</b>\n"
        f"• <b>Exit Reason:</b> {reason}\n"
        f"• <b>Position Size:</b> {tr['lots']:.2f} Lots ({tr['lots'] * 100:.0f} oz)\n"
        f"• <b>Transaction Friction:</b> ${tr['friction']:.2f}"
    )
    send_telegram_alert(text)


def run_gold_scan_cycle() -> None:
    """Executes a single institutional surveillance cycle on Gold."""
    now_utc = datetime.now(timezone.utc)
    logger.info(f"Initiating Gold scan cycle at {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}...")

    # 1. Market Open Check
    if not is_forex_market_open(now_utc):
        logger.info("Global interbank markets are closed for the weekend. Skipping Gold scan.")
        return

    # 2. Fetch Candle Data
    df_gold = fetch_candles_1h(GOLD_TICKER, range_days="30d")
    if df_gold.empty or len(df_gold) < 50:
        logger.warning("Insufficient Gold candle history returned. Aborting cycle.")
        return

    # 3. Floating Active Positions Check (Evaluated Unconditionally using current live tick/forming bar)
    records = load_gold_records()
    forming_bar = df_gold.iloc[-1]
    closed_any = check_active_gold_trades(records, forming_bar)
    if closed_any:
        sync_gold_worker(records)

    # 4. Filter: Rollover Blackout (20:30 - 22:30 UTC) - Fresh entries suppressed to avoid wide spreads
    if is_rollover_blackout_active(now_utc):
        logger.warning("Rollover Blackout Active (20:30 - 22:30 UTC). Fresh Gold entries suppressed.")
        return

    # 5. Filter: Friday Weekend Cutoff (>= 16:00 UTC) - No fresh entries before weekend
    if is_friday_weekend_cutoff(now_utc):
        logger.info("Friday weekend cutoff active (>= 16:00 UTC). No fresh Gold entries allowed.")
        return

    # 6. Filter: Active Institutional Trading Hours (06:00 - 18:00 UTC)
    if now_utc.hour not in ACTIVE_TRADING_HOURS:
        logger.info(f"Hour {now_utc.hour} UTC outside institutional active volume window (06-18 UTC). Skipping fresh entry scan.")
        return

    # 7. Filter: Daily Loss Circuit Breaker
    today_str = now_utc.strftime("%Y-%m-%d")
    daily_loss_count = records.get("daily_losses", {}).get(today_str, 0)
    if daily_loss_count >= DAILY_LOSS_CIRCUIT_BREAKER_COUNT:
        logger.warning(f"Daily Circuit Breaker Active ({daily_loss_count} stop-outs today). Halting fresh entries.")
        return

    # 8. Filter: Post-Loss Pullback Cooldown (60 minutes)
    in_cooldown, remaining_mins = check_gold_loss_cooldown(records)
    if in_cooldown:
        logger.info(f"Post-Loss Cooldown Active ({remaining_mins:.1f} mins remaining). Standing down.")
        return

    # 9. Filter: Open Position Cap (Max 1 active Gold trade)
    if records.get("active_trades"):
        logger.info("Active Gold position already open. Skipping fresh entry.")
        return

    # 10. Filter: Completed Candle Bars for Signal Evaluation (Look-Ahead Prevention)
    df_gold_completed = df_gold[df_gold["close_time"] <= now_utc].copy()
    if len(df_gold_completed) < 50:
        logger.warning("Insufficient completed Gold 1H candle history. Skipping signal evaluation.")
        return

    df_ind = compute_gold_indicators(df_gold_completed)
    last_bar = df_ind.iloc[-1]
    prev_bar = df_ind.iloc[-2]
    last_bar_time = last_bar["time_dt"].isoformat()

    # Deduplication: Prevent repeated alerts on the exact same completed 1H bar
    alerted_bars = records.get("alerted_bars", [])
    if last_bar_time in alerted_bars:
        logger.info(f"Completed 1H candle ({last_bar_time}) already evaluated. Standing by for next bar.")
        return

    # 11. Compute CCRS USD Macro Factor on Completed 1H Bars
    z_usd = compute_ccrs_usd_factor(now_utc)
    if z_usd is None:
        logger.warning("CCRS USD factor calculation failed. Skipping signal evaluation.")
        return
    logger.info(f"Current CCRS USD Macro Factor: Z_USD = {z_usd:+.2f}σ (Threshold: ±{CCRS_USD_THRESHOLD:.2f}σ)")

    is_long_macro = z_usd <= -CCRS_USD_THRESHOLD  # Aggressive USD weakness -> Long Gold
    is_short_macro = z_usd >= CCRS_USD_THRESHOLD  # Aggressive USD strength -> Short Gold

    if not is_long_macro and not is_short_macro:
        logger.info("CCRS USD Factor is neutral. Market is not in an institutional macro flow regime.")
        return

    # 12. Technical Trigger Evaluation on Completed 1H Bar
    cur_c = last_bar["close"]
    cur_o = last_bar["open"]
    cur_l = last_bar["low"]
    cur_h = last_bar["high"]
    cur_atr = last_bar["atr14"]

    trigger = False
    trigger_type = None
    direction = "LONG" if is_long_macro else "SHORT"

    if is_long_macro:
        tested_ema = (cur_l <= last_bar["ema20"] * 1.0005) and (cur_c > cur_o)
        swept_low = (cur_l < prev_bar["donch_l10"]) and (cur_c > prev_bar["donch_l10"])
        rsi_ok = last_bar["rsi14"] <= 75.0
        # 4H MA filter removed: CCRS USD macro flow and 1H precision triggers govern execution
        if (tested_ema or swept_low) and rsi_ok:
            trigger = True
            trigger_type = "EMA20 Retest Rejection" if tested_ema else "10-Bar Donchian Liquidity Sweep"
    else:
        tested_ema = (cur_h >= last_bar["ema20"] * 0.9995) and (cur_c < cur_o)
        swept_high = (cur_h > prev_bar["donch_h10"]) and (cur_c < prev_bar["donch_h10"])
        rsi_ok = last_bar["rsi14"] >= 25.0
        # 4H MA filter removed: CCRS USD macro flow and 1H precision triggers govern execution
        if (tested_ema or swept_high) and rsi_ok:
            trigger = True
            trigger_type = "EMA20 Retest Rejection" if tested_ema else "10-Bar Donchian Liquidity Sweep"

    if not trigger:
        logger.info(f"Macro flow active ({direction}), but no confirmed precision trigger on closed 1H bar.")
        return

    # 13. Cross-Engine Correlation Interlock Check (Max 2 net USD exposure)
    is_approved, interlock_msg, cur_usd_count = check_correlation_interlock(direction)
    logger.info(interlock_msg)
    if not is_approved:
        logger.warning("Signal aborted by Correlation Interlock.")
        return

    # 14. Calculate Dynamic ATR Stops & Position Sizing
    sl_points = min(max(cur_atr * ATR_MULTIPLIER, MIN_SL_POINTS), MAX_SL_POINTS)
    tp_points = sl_points * BASE_RISK_REWARD_RATIO

    equity = REFERENCE_ACCOUNT_EQUITY
    lots, monetary_risk = calculate_gold_position_size(
        account_equity=equity,
        risk_pct=PROP_FIRM_RISK_PCT,
        sl_points=sl_points
    )

    if lots <= 0.0:
        logger.warning(f"Position sizing rejected (lots: {lots}). Breaches risk budget.")
        return

    entry_price = cur_c
    sl_price = entry_price - sl_points if direction == "LONG" else entry_price + sl_points
    tp_price = entry_price + tp_points if direction == "LONG" else entry_price - tp_points

    trade_id = f"GOLD_{now_utc.strftime('%Y%m%d_%H%M%S')}"
    sig_payload = {
        "trade_id": trade_id,
        "symbol": GOLD_SYMBOL,
        "direction": direction,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "current_sl_price": sl_price,
        "current_tp_price": tp_price,
        "init_sl_points": sl_points,
        "sl_points": sl_points,
        "tp_points": tp_points,
        "lots": lots,
        "monetary_risk_usd": monetary_risk,
        "equity": equity,
        "entry_time": now_utc.isoformat(),
        "z_usd": z_usd,
        "trigger_type": trigger_type,
        "h4_bull": last_bar["bull_4h"],
        "h4_bear": last_bar["bear_4h"],
        "cushion_stage": 0,
        "usd_exposure": cur_usd_count,
        "max_usd_exposure": 2,
    }

    # 15. cTrader Execution (Stage 2 Demo / Live)
    try:
        from core.ctrader_executor import execute_ctrader_order
        c_receipt = execute_ctrader_order({
            "pair": GOLD_SYMBOL,
            "direction": direction,
            "entry": entry_price,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "lots": lots,
            "suggested_lots": lots,
        })
        sig_payload["ctrader_receipt"] = c_receipt
        if c_receipt.get("position_id"):
            sig_payload["ctrader_position_id"] = c_receipt["position_id"]
    except Exception as e:
        logger.warning(f"cTrader execution hook error on Gold: {e}")

    records["active_trades"][trade_id] = sig_payload
    alerted_bars.append(last_bar_time)
    records["alerted_bars"] = alerted_bars[-100:]  # Keep last 100 bars to prevent file growth
    save_gold_records(records)
    logger.info(f"Opened Gold Position: {direction} {lots:.2f} lots @ ${entry_price:.2f} (SL: ${sl_price:.2f}, TP: ${tp_price:.2f})")
    send_signal_alert(sig_payload)
    sync_gold_worker(records)


def main():
    parser = argparse.ArgumentParser(description="Standalone Gold Satellite Market Scanner")
    parser.add_argument("--loop", action="store_true", help="Run in continuous background surveillance loop (60s poll)")
    parser.add_argument("--test", action="store_true", help="Dispatch developer dry-run test alert to Telegram")
    args = parser.parse_args()

    if args.test:
        logger.info("Executing dry-run developer alert dispatch...")
        test_payload = {
            "symbol": GOLD_SYMBOL,
            "direction": "LONG",
            "entry_price": 4125.50,
            "sl_price": 4100.50,
            "tp_price": 4163.00,
            "sl_points": 25.0,
            "tp_points": 37.5,
            "lots": 0.01,
            "monetary_risk_usd": 25.00,
            "equity": 5000.0,
            "z_usd": -1.88,
            "trigger_type": "10-Bar Donchian Liquidity Sweep",
            "h4_bull": True,
            "usd_exposure": 0,
            "max_usd_exposure": 2,
            "is_test": True,
        }
        send_signal_alert(test_payload)
        return

    if args.loop:
        logger.info("Starting continuous 24/7 Gold market scanner loop (60s poll)...")
        while True:
            try:
                run_gold_scan_cycle()
            except Exception as e:
                logger.error(f"Unhandled error in Gold scan cycle: {e}", exc_info=True)
            time.sleep(60.0)
    else:
        run_gold_scan_cycle()


if __name__ == "__main__":
    main()
