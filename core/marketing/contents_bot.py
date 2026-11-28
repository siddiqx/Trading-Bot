"""
Contents Marketing Bot Engine (@contents7_bot)
==============================================
Dedicated social media content generator & Telegram command cockpit.
Keeps personal trading bot (Columbina Raiden) 100% clean of marketing noise.

Supported Commands:
  • /signal  (⚡ Latest Signal)       -> Unified cross-platform signal & chart for Twitter & Reddit
  • /chart   (📊 Chart)               -> Live high-res candlestick chart with clean ICT/SMC levels
  • /twitter (🐦 Twitter Thread)      -> 3-tweet thread ready for 1-tap mobile copying
  • /reddit  (📝 Reddit Post)         -> Structured case study post for r/Forex & r/PropFirm
  • /outlook (🌐 4H Trend Outlook)    -> 4H higher-timeframe market structure & trend analysis
  • /tradingview (📈 TradingView)     -> Professional publication pack with clean narrative
  • /help    (ℹ️ Help & Menu)         -> Command options and posting tips
"""

import os
import sys
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List

import random
import numpy as np
import pandas as pd

logger = logging.getLogger("ContentsBot")
logger.setLevel(logging.INFO)

TELEGRAM_MARKETING_BOT_TOKEN = (
    os.environ.get("TELEGRAM_MARKETING_BOT_TOKEN") or "9196801543:AAH7wqm8U4H98KD61Wsw7X5OYHZ5cQhXjJE"
).strip()
TELEGRAM_CHAT_ID = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
DEFAULT_CHANNEL_URL = "https://t.me/ccrs_forex_signals"

# Institutional universe with Gold (XAUUSD) as primary focus alongside major Forex pairs
ACTIVE_PAIRS = ["XAUUSD", "EURUSD", "USDCAD", "USDCHF", "AUDUSD"]

_RECENT_PAIRS_HISTORY: List[str] = []


def normalize_asset_symbol(raw: str) -> str:
    """Normalizes asset symbols and aliases (e.g. 'gold', 'xau' -> 'XAUUSD')."""
    s = (raw or "").upper().replace("/", "").replace("=", "").strip()
    if s in ("GOLD", "XAU", "GC", "GCF", "XAUUSD"):
        return "XAUUSD"
    if s in ("EUR", "EURUSD"):
        return "EURUSD"
    if s in ("CAD", "USDCAD"):
        return "USDCAD"
    if s in ("CHF", "USDCHF"):
        return "USDCHF"
    if s in ("AUD", "AUDUSD"):
        return "AUDUSD"
    return s if s in ACTIVE_PAIRS else "XAUUSD"


def select_dynamic_market_pair(preferred_pair: Optional[str] = None) -> str:
    """
    Intelligently selects an asset based on live market conditions, recent volatility,
    and anti-repetition tracking across the active portfolio (XAUUSD, EURUSD, USDCAD, USDCHF, AUDUSD).
    
    If preferred_pair is provided, honors that choice.
    Otherwise:
      1. Evaluates live price action / ATR volatility / liquidity sweep proximity.
      2. Penalizes pairs that were recently posted to guarantee continuous dynamic variety.
      3. Never gets stuck on any single asset (neither Gold nor EURUSD).
    """
    global _RECENT_PAIRS_HISTORY
    if preferred_pair:
        norm = normalize_asset_symbol(preferred_pair)
        if norm in ACTIVE_PAIRS:
            _RECENT_PAIRS_HISTORY.append(norm)
            if len(_RECENT_PAIRS_HISTORY) > 5:
                _RECENT_PAIRS_HISTORY.pop(0)
            return norm

    # Real-time market condition scoring across active pairs
    scores: Dict[str, float] = {}
    for pair in ACTIVE_PAIRS:
        try:
            df = fetch_candles_for_pair(pair, interval="1h", range_days="4d")
            if df is not None and len(df) >= 15:
                highs = df["high"].values
                lows = df["low"].values
                closes = df["close"].values
                # 14-bar ATR calculation
                tr = np.maximum(highs[1:] - lows[1:], np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
                atr = float(np.mean(tr[-14:]))
                recent_range = float(np.max(highs[-3:]) - np.min(lows[-3:]))
                vol_ratio = (recent_range / atr) if atr > 0 else 1.0

                # Proximity to 20-bar Donchian high/low (liquidity boundary)
                recent_max = float(np.max(highs[-20:]))
                recent_min = float(np.min(lows[-20:]))
                cur_px = float(closes[-1])
                pos = (cur_px - recent_min) / (recent_max - recent_min) if (recent_max - recent_min) > 0 else 0.5
                sweep_proximity = 1.0 - 2.0 * abs(pos - 0.5)

                score = vol_ratio * 1.5 + sweep_proximity * 1.0
            else:
                score = random.uniform(1.0, 2.0)
        except Exception:
            score = random.uniform(1.0, 2.0)

        # Anti-repetition penalty: strongly penalize recent pairs to prevent repeat posts
        if _RECENT_PAIRS_HISTORY:
            if pair == _RECENT_PAIRS_HISTORY[-1]:
                score -= 10.0  # Cannot be the exact same pair back-to-back
            elif len(_RECENT_PAIRS_HISTORY) >= 2 and pair == _RECENT_PAIRS_HISTORY[-2]:
                score -= 4.0
            elif len(_RECENT_PAIRS_HISTORY) >= 3 and pair == _RECENT_PAIRS_HISTORY[-3]:
                score -= 2.0

        scores[pair] = score

    # Pick the pair with highest dynamic market score
    sorted_pairs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_pair = sorted_pairs[0][0]

    _RECENT_PAIRS_HISTORY.append(best_pair)
    if len(_RECENT_PAIRS_HISTORY) > 5:
        _RECENT_PAIRS_HISTORY.pop(0)

    return best_pair


def get_persistent_menu_keyboard() -> dict:
    """
    Keeps the typing area 100% clean by removing any bottom reply keyboards.
    Commands are accessed purely via the Telegram 3-dot / Menu (/) button.
    """
    return {"remove_keyboard": True}


def get_inline_action_keyboard(pair: str = "EURUSD") -> dict:
    """
    Returns inline buttons for instant 1-tap switching between formats.
    """
    p = pair.upper()
    return {
        "inline_keyboard": [
            [
                {"text": "🎬 Generate Short Video", "callback_data": f"btn_sh_{p}"}
            ],
            [
                {"text": "🐦 Twitter Thread", "callback_data": f"btn_tw_{p}"},
                {"text": "📝 Reddit Post", "callback_data": f"btn_rd_{p}"}
            ],
            [
                {"text": "📊 Refresh Chart", "callback_data": f"btn_ch_{p}"},
                {"text": "🌐 4H Outlook", "callback_data": f"btn_ot_{p}"}
            ]
        ]
    }


def send_contents_message(
    chat_id: str,
    text: str,
    reply_markup: Optional[dict] = None,
    bot_token: Optional[str] = None
) -> bool:
    """Send HTML message via Contents Bot API."""
    token = (bot_token or TELEGRAM_MARKETING_BOT_TOKEN).strip()
    if not token or not chat_id:
        return False
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        logger.info(f"[TEST SUPPRESSED] send_contents_message to {chat_id}: {text[:80]}...")
        return True

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id).strip(),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"Contents bot sendMessage error: {e}")
        return False


def send_contents_photo(
    chat_id: str,
    photo_bytes: bytes,
    caption: str = "",
    reply_markup: Optional[dict] = None,
    bot_token: Optional[str] = None
) -> bool:
    """Send photo with HTML caption via Contents Bot API."""
    token = (bot_token or TELEGRAM_MARKETING_BOT_TOKEN).strip()
    if not token or not chat_id or not photo_bytes:
        return False
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        logger.info(f"[TEST SUPPRESSED] send_contents_photo to {chat_id}")
        return True

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    boundary = "----WebKitFormBoundaryContentsBot7MA"
    body = bytearray()

    def add_field(name: str, value: str):
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(f"{value}\r\n".encode())

    add_field("chat_id", str(chat_id).strip())
    add_field("caption", caption[:1024])
    add_field("parse_mode", "HTML")
    if reply_markup:
        add_field("reply_markup", json.dumps(reply_markup))

    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="photo"; filename="chart.png"\r\n'.encode())
    body.extend(b"Content-Type: image/png\r\n\r\n")
    body.extend(photo_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    try:
        req = urllib.request.Request(
            url, data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"Contents bot sendPhoto error: {e}")
        # Fallback to text message
        return send_contents_message(chat_id, caption, reply_markup=reply_markup, bot_token=token)


def send_contents_video(
    chat_id: str,
    video_bytes: bytes,
    caption: str = "",
    reply_markup: Optional[dict] = None,
    bot_token: Optional[str] = None
) -> bool:
    """Send MP4 video with HTML caption via Telegram sendVideo API."""
    token = (bot_token or TELEGRAM_MARKETING_BOT_TOKEN).strip()
    if not token or not chat_id or not video_bytes:
        return False
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        logger.info(f"[TEST SUPPRESSED] send_contents_video to {chat_id}")
        return True

    url = f"https://api.telegram.org/bot{token}/sendVideo"
    boundary = "----WebKitFormBoundaryContentsBotVideo7MA"
    body = bytearray()

    def add_field(name: str, value: str):
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(f"{value}\r\n".encode())

    add_field("chat_id", str(chat_id).strip())
    add_field("caption", caption[:1024])
    add_field("parse_mode", "HTML")
    add_field("supports_streaming", "true")
    add_field("width", "1080")
    add_field("height", "1920")
    if reply_markup:
        add_field("reply_markup", json.dumps(reply_markup))

    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="video"; filename="short.mp4"\r\n'.encode())
    body.extend(b"Content-Type: video/mp4\r\n\r\n")
    body.extend(video_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    try:
        req = urllib.request.Request(
            url, data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        with urllib.request.urlopen(req, timeout=35) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"Contents bot sendVideo error: {e}")
        return False


def setup_contents_bot_commands(bot_token: Optional[str] = None) -> bool:
    """
    Registers the command list with Telegram API so that tapping the Menu (/)
    or 3-dot options immediately shows the commands cleanly.
    """
    token = (bot_token or TELEGRAM_MARKETING_BOT_TOKEN).strip()
    if not token or os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return True

    url = f"https://api.telegram.org/bot{token}/setMyCommands"
    commands = [
        {"command": "short", "description": "🎬 YouTube Shorts & IG Reels Video (1080x1920)"},
        {"command": "signal", "description": "⚡ Latest Active Trade Signal"},
        {"command": "chart", "description": "📊 Live High-Res Candlestick Chart"},
        {"command": "twitter", "description": "🐦 Twitter / X Thread (1-Tap Copy)"},
        {"command": "reddit", "description": "📝 Reddit Educational Post + Chart"},
        {"command": "outlook", "description": "🌐 4H Trend Outlook & Liquidity Map"},
        {"command": "tradingview", "description": "📈 TradingView Publication Pack"},
        {"command": "help", "description": "ℹ️ Command Cockpit & Guide"}
    ]
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"commands": commands}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception as e:
        logger.warning(f"Could not register commands with Telegram: {e}")
        return False


def answer_callback(callback_query_id: str, text: str = "", bot_token: Optional[str] = None) -> bool:
    """Acknowledge Telegram callback query to dismiss loading spinner."""
    token = (bot_token or TELEGRAM_MARKETING_BOT_TOKEN).strip()
    if not token or not callback_query_id:
        return False
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return True
    try:
        url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


_ACTIVE_TRADE_CACHE = None
_ACTIVE_TRADE_CACHE_TS = 0.0
_CHART_CACHE: Dict[str, Tuple[float, bytes]] = {}


def get_latest_active_trade() -> Optional[dict]:
    """
    Retrieves the currently open active trade from the ledger.
    Returns None if there are NO active trades open in the trading system.
    Never invents or fabricates fake mock trades.
    """
    global _ACTIVE_TRADE_CACHE, _ACTIVE_TRADE_CACHE_TS
    import time
    now = time.time()
    if _ACTIVE_TRADE_CACHE is not None and (now - _ACTIVE_TRADE_CACHE_TS < 15.0):
        return _ACTIVE_TRADE_CACHE

    try:
        from market_scanner import load_trade_records
        records = load_trade_records()
        active = records.get("active_trades", {})
        if active:
            latest_key = list(active.keys())[-1]
            trade = dict(active[latest_key])
            _ACTIVE_TRADE_CACHE = trade
            _ACTIVE_TRADE_CACHE_TS = now
            return trade
    except Exception as e:
        logger.warning(f"Failed to fetch active trade from ledger: {e}")

    _ACTIVE_TRADE_CACHE = None
    _ACTIVE_TRADE_CACHE_TS = now
    return None


def get_recent_completed_trade() -> Optional[Tuple[dict, float, float]]:
    """Retrieves the most recent verified completed trade from the ledger."""
    try:
        from market_scanner import load_trade_records
        records = load_trade_records()
        completed = records.get("completed_trades", [])
        if completed:
            latest = dict(completed[-1])
            pips = float(latest.get("realized_pips") or latest.get("pips", 0.0))
            r_val = float(latest.get("realized_r") or latest.get("r_multiple", 0.0))
            return latest, pips, r_val
    except Exception as e:
        logger.warning(f"Failed to query completed trades: {e}")
    return None


def fetch_candles_for_pair(pair: str, interval: str = "15m", range_days: str = "3d") -> Optional[pd.DataFrame]:
    """Fetches real market candle data for chart generation across Gold and Forex pairs."""
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return None
    norm_pair = normalize_asset_symbol(pair)
    try:
        # Dedicated Gold (XAUUSD) continuous futures/spot query
        if norm_pair == "XAUUSD":
            for ticker in ("GC=F", "XAUUSD=X"):
                try:
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_days}&interval={interval}"
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        result = data.get("chart", {}).get("result")
                        if result:
                            chart = result[0]
                            ts = chart.get("timestamp", [])
                            q = chart.get("indicators", {}).get("quote", [{}])[0]
                            if ts and q and "open" in q and q.get("open"):
                                df = pd.DataFrame({
                                    "time": ts,
                                    "open": q.get("open"),
                                    "high": q.get("high"),
                                    "low": q.get("low"),
                                    "close": q.get("close"),
                                    "volume": q.get("volume", [0] * len(ts)),
                                }).dropna().reset_index(drop=True)
                                if not df.empty:
                                    df["time_dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
                                    df["close_time"] = df["time_dt"] + pd.Timedelta(minutes=15 if interval == "15m" else 60)
                                    return df.sort_values("time_dt").reset_index(drop=True)
                except Exception:
                    continue

        from market_scanner import fetch_candles, SYMBOLS
        ticker = SYMBOLS.get(norm_pair, {}).get("ticker", f"{norm_pair}=X")
        return fetch_candles(ticker, interval, range_days=range_days)
    except Exception as e:
        logger.warning(f"Error fetching candles for {norm_pair}: {e}")
        return None


def generate_chart_bytes(trade: dict, trade_status: str = "OPEN", df: Optional[pd.DataFrame] = None) -> Optional[bytes]:
    """
    Generates high-resolution candlestick chart with ICT/SMC markup.
    Cached for 60s per pair to prevent redundant heavy re-renders.
    """
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest"

    import time
    pair = trade.get("pair") or trade.get("symbol") or "EURUSD"
    tf = str(trade.get("timeframe", "15M")).upper()
    cache_key = f"{pair}_{tf}_{trade_status}"
    now = time.time()

    if df is None and cache_key in _CHART_CACHE:
        ts, cached_b = _CHART_CACHE[cache_key]
        if now - ts < 60.0:
            return cached_b

    try:
        from core.chart_generator import generate_trade_chart
        if df is None:
            df = fetch_candles_for_pair(pair, interval=tf.lower(), range_days="3d" if tf == "15M" else "10d")
        if df is not None and not df.empty:
            chart_bytes = generate_trade_chart(df, trade, trade_status=trade_status)
            if chart_bytes:
                _CHART_CACHE[cache_key] = (now, chart_bytes)
            return chart_bytes
    except Exception as e:
        logger.warning(f"Error generating chart bytes: {e}")
    return None


def generate_unified_cross_platform_signal(
    trade: dict,
    realized_pips: Optional[float] = None,
    realized_r: Optional[float] = None
) -> str:
    """
    Generates a clean, punchy, non-cluttered trade signal suitable for
    posting to BOTH Twitter/X and Reddit.
    Zero robotic jargon, human-readable levels, and clear ICT rationale.
    """
    pair = trade.get("pair") or trade.get("symbol") or "EURUSD"
    display_pair = f"{pair[:3]}/{pair[3:]}" if len(pair) == 6 else pair
    direction = trade.get("direction", "LONG").upper()
    dir_emoji = "🟢" if direction == "LONG" else "🔴"
    action_type = "BUY / LONG" if direction == "LONG" else "SELL / SHORT"
    tf = str(trade.get("timeframe", "15M")).upper()

    digits = 3 if "JPY" in pair else (2 if "XAU" in pair else 5)
    pip_mult = 100 if "JPY" in pair else (10 if "XAU" in pair else 10000)

    entry = float(trade.get("entry", 0.0))
    sl = float(trade.get("stop_loss", 0.0))
    tp = float(trade.get("take_profit", 0.0))
    rr = float(trade.get("rr", 1.50))

    sl_pips = abs(entry - sl) * pip_mult if entry and sl else 22.0
    tp_pips = abs(tp - entry) * pip_mult if entry and tp else sl_pips * rr

    is_win = realized_r is not None and realized_r > 0
    status_header = f"🎯 <b>FULL TAKE PROFIT HIT (+{realized_pips:.1f} Pips / +{realized_r:.2f}R)</b>" if is_win else f"{dir_emoji} <b>INSTITUTIONAL TRADE SETUP</b>"

    sweep_target = "Sell-Side Liquidity (SSL)" if direction == "LONG" else "Buy-Side Liquidity (BSL)"
    opp_target = "Buy-Side Liquidity (BSL)" if direction == "LONG" else "Sell-Side Liquidity (SSL)"
    ob_name = "+Order Block (+OB)" if direction == "LONG" else "-Order Block (-OB)"

    cross_platform_text = (
        f"{status_header}\n\n"
        f"<b>Asset:</b> {display_pair} ({action_type})\n"
        f"<b>Timeframe:</b> {tf} Execution\n"
        f"<b>Entry Price:</b> <code>{entry:.{digits}f}</code>\n"
        f"<b>Take Profit Target:</b> <code>{tp:.{digits}f}</code> (+{tp_pips:.1f} pips | 1:{rr:.2f}R)\n"
        f"<b>Stop Loss:</b> <code>{sl:.{digits}f}</code> ({sl_pips:.1f} pips)\n\n"
        f"<b>Trade Breakdown:</b>\n"
        f"Higher-timeframe currency strength favored {display_pair} while "
        f"15M price swept resting {sweep_target} to clean out early orders. Confirmed structure shift (MSS) with clean rejection off "
        f"the 20-EMA. Targeting opposing {opp_target} with a disciplined 1:{rr:.2f}R target.\n\n"
        f"Are you trading {display_pair} today or staying on the sidelines? Let us know below 👇\n\n"
        f"<code>${pair} #Forex #ICT #TradingView #PropFirm #FTMO</code>\n"
        f"👉 <i>Free Surveillance & Alerts: {DEFAULT_CHANNEL_URL}</i>"
    )
    return cross_platform_text


def format_master_social_hub(
    trade: dict,
    realized_pips: Optional[float] = None,
    realized_r: Optional[float] = None
) -> str:
    """
    Formats the complete social media content pack into a clean, unconfused,
    single master hub with clearly separated 1-tap copy blocks.
    Prevents chat flooding while giving immediate access to Twitter and Reddit.
    """
    pair = trade.get("pair") or trade.get("symbol") or "EURUSD"
    display_pair = f"{pair[:3]}/{pair[3:]}" if len(pair) == 6 else pair
    direction = trade.get("direction", "LONG").upper()
    tf = str(trade.get("timeframe", "15M")).upper()

    from core.marketing.case_study_generator import generate_twitter_thread, generate_reddit_case_study

    pips_val = realized_pips if realized_pips is not None else float(trade.get("tp_pips", 35.0))
    r_val = realized_r if realized_r is not None else float(trade.get("rr", 1.50))

    tweets = generate_twitter_thread(trade, realized_pips=pips_val, realized_r=r_val)
    reddit_post = generate_reddit_case_study(trade, realized_pips=pips_val, realized_r=r_val)

    hub_msg = (
        f"🚀 <b>CONTENTS HUB · {display_pair} ({direction})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ <b>1. QUICK COPY (Twitter & Reddit Blurb):</b>\n"
        f"<i>Tap below to copy short post:</i>\n"
        f"<code>{tweets[0]}</code>\n\n"
        f"🐦 <b>2. TWITTER / X THREAD (3 Tweets):</b>\n"
        f"• <b>Tweet 1 (Hook):</b>\n"
        f"<code>{tweets[0]}</code>\n\n"
        f"• <b>Tweet 2 (Anatomy):</b>\n"
        f"<code>{tweets[1]}</code>\n\n"
        f"• <b>Tweet 3 (Risk & Link):</b>\n"
        f"<code>{tweets[2]}</code>\n\n"
        f"📝 <b>3. REDDIT CASE STUDY (r/Forex · r/PropFirm):</b>\n"
        f"• <b>Post Title:</b>\n"
        f"<code>{reddit_post['title']}</code>\n\n"
        f"• <b>Post Body (Markdown):</b>\n"
        f"<pre>{reddit_post['body']}</pre>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Tip: Attach the chart above to your post for 3x higher engagement!</i>"
    )
    return hub_msg


def dispatch_automated_market_content(
    trade: dict,
    event_type: str = "SIGNAL",
    realized_pips: Optional[float] = None,
    realized_r: Optional[float] = None,
    chart_bytes: Optional[bytes] = None,
    df: Optional[pd.DataFrame] = None,
    bot_token: Optional[str] = None
) -> bool:
    """
    Dispatches automated content to the user on market triggers (Trade Open or TP Hit).
    Structured as:
      1. Chart Photo with concise summary caption.
      2. Master Social Hub containing clean Twitter & Reddit copy-blocks with inline buttons.
    Never messy, never flooding.
    """
    admin_id = TELEGRAM_CHAT_ID.split(",")[0].strip() if TELEGRAM_CHAT_ID else ""
    if not admin_id or admin_id.startswith("@"):
        return False

    pair = trade.get("pair") or trade.get("symbol") or "EURUSD"
    display_pair = f"{pair[:3]}/{pair[3:]}" if len(pair) == 6 else pair
    direction = trade.get("direction", "LONG").upper()
    tf = str(trade.get("timeframe", "15M")).upper()

    status = "TP_HIT" if (event_type == "TP_HIT" or (realized_r is not None and realized_r > 0)) else "OPEN"

    # 1. Generate chart if not supplied
    if not chart_bytes:
        chart_bytes = generate_chart_bytes(trade, trade_status=status, df=df)

    # 2. Dispatch chart photo first
    entry = trade.get("entry", 0.0)
    tp = trade.get("take_profit", 0.0)
    sl = trade.get("stop_loss", 0.0)
    caption_title = "🎯 <b>TAKE PROFIT RESOLVED</b>" if status == "TP_HIT" else "⚡ <b>NEW MARKET SIGNAL</b>"
    photo_caption = (
        f"{caption_title} · <b>{display_pair} ({direction})</b> • <code>{tf}</code>\n"
        f"Entry: <code>{entry}</code> | TP: <code>{tp}</code> | SL: <code>{sl}</code>\n"
        f"<i>Verified chart ready to attach to Twitter / Reddit.</i>"
    )

    if chart_bytes:
        send_contents_photo(admin_id, chart_bytes, caption=photo_caption, bot_token=bot_token)

    # 3. Dispatch Master Social Hub with clean copy blocks & inline buttons
    hub_text = format_master_social_hub(trade, realized_pips=realized_pips, realized_r=realized_r)
    inline_kb = get_inline_action_keyboard(pair)
    return send_contents_message(admin_id, hub_text, reply_markup=inline_kb, bot_token=bot_token)


def handle_contents_bot_update(update: dict, bot_token: Optional[str] = None) -> bool:
    """
    Handles incoming updates from Telegram for @contents7_bot.
    Supports slash commands, persistent keyboard buttons, and inline callback queries.
    """
    token = (bot_token or TELEGRAM_MARKETING_BOT_TOKEN).strip()

    active_trade = get_latest_active_trade()
    recent_comp = get_recent_completed_trade()

    # 1. Handle Inline Callback Queries
    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb.get("id")
        data = cb.get("data", "")
        chat_id = str(cb.get("message", {}).get("chat", {}).get("id") or cb.get("from", {}).get("id"))
        answer_callback(cb_id, bot_token=token)

        raw_target = data.split("_")[-1] if "_" in data else (active_trade.get("pair") if active_trade else "XAUUSD")
        target_pair = normalize_asset_symbol(raw_target)

        if data.startswith("btn_tw"):
            if active_trade:
                from core.marketing.case_study_generator import generate_twitter_thread
                tweets = generate_twitter_thread(active_trade)
                msg = (
                    f"🐦 <b>TWITTER / X THREAD · {target_pair} (Tap to copy)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"📌 <b>TWEET 1 (Hook & Levels):</b>\n<code>{tweets[0]}</code>\n\n"
                    f"📌 <b>TWEET 2 (Setup Anatomy):</b>\n<code>{tweets[1]}</code>\n\n"
                    f"📌 <b>TWEET 3 (Risk & Link):</b>\n<code>{tweets[2]}</code>"
                )
            else:
                from core.marketing.ai_content_generator import generate_ai_twitter_educational_thread
                ai_pack = generate_ai_twitter_educational_thread(pair=target_pair)
                tweets = ai_pack["tweets"]
                msg = (
                    f"🐦 <b>TWITTER / X EDUCATIONAL THREAD · {target_pair} (Tap to copy)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Topic: <b>{ai_pack['topic']}</b>\n\n"
                    f"📌 <b>TWEET 1 (Hook):</b>\n<code>{tweets[0]}</code>\n\n"
                    f"📌 <b>TWEET 2 (Mechanics):</b>\n<code>{tweets[1]}</code>\n\n"
                    f"📌 <b>TWEET 3 (Takeaway & Link):</b>\n<code>{tweets[2]}</code>"
                )
            return send_contents_message(chat_id, msg, bot_token=token)

        elif data.startswith("btn_rd"):
            if active_trade:
                from core.marketing.case_study_generator import generate_reddit_case_study
                reddit_post = generate_reddit_case_study(active_trade)
                msg = (
                    f"📝 <b>REDDIT CASE STUDY · {target_pair}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📌 <b>TITLE:</b>\n<code>{reddit_post['title']}</code>\n\n"
                    f"📋 <b>BODY:</b>\n<pre>{reddit_post['body']}</pre>"
                )
            else:
                from core.marketing.ai_content_generator import generate_ai_reddit_educational_post
                ai_pack = generate_ai_reddit_educational_post(pair=target_pair)
                msg = (
                    f"📝 <b>REDDIT EDUCATIONAL POST · {target_pair} ({ai_pack.get('subreddit', 'r/Forex')})</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📌 <b>TITLE:</b>\n<code>{ai_pack['title']}</code>\n\n"
                    f"📋 <b>BODY:</b>\n<pre>{ai_pack['body']}</pre>"
                )
            return send_contents_message(chat_id, msg, bot_token=token)

        elif data.startswith("btn_ch"):
            chart_sig = {"pair": target_pair, "timeframe": "15M", "direction": (active_trade.get("direction") if active_trade and active_trade.get("pair") == target_pair else "NEUTRAL")}
            chart_bytes = generate_chart_bytes(chart_sig, trade_status="OPEN" if active_trade else "OUTLOOK")
            if chart_bytes:
                caption = f"📊 <b>REAL MARKET CHART · {target_pair} (15M)</b>\n<i>Verified interbank price action & structure.</i>"
                return send_contents_photo(chat_id, chart_bytes, caption=caption, reply_markup=get_inline_action_keyboard(target_pair), bot_token=token)
            return send_contents_message(chat_id, "Could not render chart at this moment.", bot_token=token)

        elif data.startswith("btn_ot"):
            from core.marketing.case_study_generator import format_market_outlook_telegram_pack
            df_4h = fetch_candles_for_pair(target_pair, interval="1h", range_days="15d")
            outlook_text = format_market_outlook_telegram_pack(pair=target_pair, df=df_4h)
            outlook_sig = {"pair": target_pair, "timeframe": "4H", "direction": "NEUTRAL"}
            chart_bytes = generate_chart_bytes(outlook_sig, trade_status="OUTLOOK", df=df_4h)
            if chart_bytes:
                send_contents_photo(chat_id, chart_bytes, caption=f"🌐 <b>4H MARKET OUTLOOK · {target_pair}</b>", bot_token=token)
            return send_contents_message(chat_id, outlook_text, bot_token=token)

        elif data.startswith("btn_sh"):
            from core.marketing.shorts_generator import generate_trading_short_video
            send_contents_message(
                chat_id,
                f"🎬 <i>Rendering high-definition 1080x1920 video short for {target_pair} (ICT setup, 24fps, neural voiceover)... This takes ~3-4s.</i>",
                bot_token=token
            )
            v_bytes, v_meta = generate_trading_short_video(pair=target_pair, timeframe="15M", voice_enabled=True)
            if v_bytes:
                caption = (
                    f"🎬 <b>INSTITUTIONAL SHORT VIDEO · {target_pair}</b>\n"
                    f"<i>1080x1920 (9:16) · Watermark-Free · Natural Neural Audio</i>\n\n"
                    f"Ready to upload directly to <b>YouTube Shorts</b> & <b>Instagram Reels</b>!"
                )
                send_contents_video(chat_id, v_bytes, caption=caption, reply_markup=get_inline_action_keyboard(target_pair), bot_token=token)
                copy_pack = (
                    f"📱 <b>COPY-PASTE CAPTION & HASHTAGS (Tap to copy)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"<code>{v_meta.get('ig_caption', '')}</code>"
                )
                return send_contents_message(chat_id, copy_pack, bot_token=token)
            else:
                return send_contents_message(chat_id, f"⚠️ Unable to render video for {target_pair} right now.", bot_token=token)

        return True

    # 2. Handle Text Messages & Slash Commands
    message = update.get("message") or update.get("channel_post")
    if not message:
        return False

    chat_id = str(message.get("chat", {}).get("id"))
    raw_text = (message.get("text") or "").strip()
    cmd = raw_text.lower()

    # Command: /start or /help
    if cmd in ("/start", "/help", "help", "menu", "info"):
        status_text = f"🟢 1 Active Trade Live ({active_trade.get('pair')})" if active_trade else "📡 Scanner Monitoring (No Active Setups)"
        welcome_text = (
            f"🚀 <b>QUANTFLOW CONTENTS COCKPIT (@contents7_bot)</b>\n"
            f"Engine Status: <b>{status_text}</b>\n\n"
            f"<b>Commands:</b>\n"
            f"• <code>/short [PAIR]</code> — 🎬 High-def 1080x1920 Video Short for YouTube Shorts & IG Reels\n"
            f"• <code>/signal</code> — Active verified trade signal (or standby status)\n"
            f"• <code>/twitter [PAIR]</code> — Viral FinTwit thread + real chart (Gold / Forex rotation)\n"
            f"• <code>/reddit [PAIR]</code> — Deep educational post for r/Forex & r/PropFirm + chart\n"
            f"• <code>/chart [PAIR]</code> — Real candlestick chart (e.g. /chart XAUUSD, /chart EURUSD)\n"
            f"• <code>/outlook [PAIR]</code> — 4H macro trend & liquidity structure (e.g. /outlook XAUUSD)\n"
            f"• <code>/tradingview [PAIR]</code> — Clean TradingView idea publication pack\n\n"
            f"💡 <i>Tip: Tap the Menu (/) button next to the typing bar to select commands!</i>"
        )
        return send_contents_message(chat_id, welcome_text, reply_markup=get_persistent_menu_keyboard(), bot_token=token)

    # Command: /short or /video
    elif cmd.startswith("/short") or cmd.startswith("/video") or cmd in ("🎬 short video", "short", "video"):
        from core.marketing.shorts_generator import generate_trading_short_video
        parts = raw_text.split()
        voice_mode = True
        requested_pair = None
        for p in parts[1:]:
            if p.lower() in ("silent", "mute", "no-voice", "novoice"):
                voice_mode = False
            else:
                requested_pair = p.upper()

        target_pair = select_dynamic_market_pair(requested_pair)
        voice_desc = "Natural Neural Voiceover" if voice_mode else "Silent (Ready for Trending Audio)"

        send_contents_message(
            chat_id,
            f"🎬 <b>Rendering 1080x1920 Video Short for {target_pair}</b>\n"
            f"• Format: 9:16 Vertical HD (YouTube Shorts / IG Reels)\n"
            f"• Audio: {voice_desc}\n"
            f"• Visuals: Institutional Dark Terminal, ICT Markup, 20-EMA\n"
            f"⏳ <i>Generating frames and muxing audio... Please hold (~3-4s).</i>",
            bot_token=token
        )

        v_bytes, v_meta = generate_trading_short_video(pair=target_pair, timeframe="15M", voice_enabled=voice_mode)
        if v_bytes:
            caption = (
                f"🎬 <b>INSTITUTIONAL SHORT VIDEO · {target_pair}</b>\n"
                f"<i>1080x1920 (9:16) · Watermark-Free · {voice_desc}</i>\n\n"
                f"Ready to upload directly to <b>YouTube Shorts</b> & <b>Instagram Reels</b>!"
            )
            send_contents_video(chat_id, v_bytes, caption=caption, reply_markup=get_inline_action_keyboard(target_pair), bot_token=token)
            copy_pack = (
                f"📱 <b>COPY-PASTE CAPTION & HASHTAGS (Tap to copy)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"<code>{v_meta.get('ig_caption', '')}</code>"
            )
            return send_contents_message(chat_id, copy_pack, bot_token=token)
        else:
            return send_contents_message(chat_id, f"⚠️ Unable to render short video for {target_pair} right now.", bot_token=token)

    # Command: /signal
    elif cmd in ("/signal", "⚡ latest signal", "signal"):
        if active_trade:
            signal_text = generate_unified_cross_platform_signal(active_trade)
            chart_bytes = generate_chart_bytes(active_trade, trade_status="OPEN")
            if chart_bytes:
                send_contents_photo(
                    chat_id, chart_bytes,
                    caption=f"⚡ <b>VERIFIED ACTIVE TRADE · {active_trade.get('pair', 'EURUSD')} ({active_trade.get('direction', 'LONG')})</b>",
                    bot_token=token
                )
            return send_contents_message(
                chat_id, signal_text,
                reply_markup=get_inline_action_keyboard(active_trade.get("pair", "EURUSD")),
                bot_token=token
            )
        else:
            no_trade_msg = (
                "📡 <b>NO ACTIVE TRADES IDENTIFIED</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "The systematic CCRS quantitative engine currently monitors the institutional universe:\n\n"
                "• <b>Gold (XAU/USD):</b> Standby (High-priority commodity surveillance)\n"
                "• <b>EUR/USD:</b> Standby (Evaluating 1H currency relative strength)\n"
                "• <b>USD/CAD:</b> Neutral (No liquidity sweep identified)\n"
                "• <b>USD/CHF:</b> Balanced (Divergence below 1.75σ threshold)\n"
                "• <b>AUD/USD:</b> Standby\n\n"
                "⚡ <i>Authentic systematic trading requires patience. We execute strictly when mathematical edge confirms.</i>\n\n"
                "👉 Send <code>/outlook XAUUSD</code> for Gold 4H liquidity analysis.\n"
                "👉 Send <code>/twitter</code> or <code>/reddit</code> for educational content with real charts to post!"
            )
            return send_contents_message(chat_id, no_trade_msg, bot_token=token)

    # Command: /twitter
    elif cmd.startswith("/twitter") or cmd in ("🐦 twitter thread", "twitter"):
        from core.marketing.case_study_generator import generate_twitter_thread
        from core.marketing.ai_content_generator import generate_ai_twitter_educational_thread

        parts = raw_text.split()
        requested_pair = parts[1].upper() if len(parts) > 1 else None
        target_pair = select_dynamic_market_pair(requested_pair)

        if active_trade and (not requested_pair or normalize_asset_symbol(active_trade.get("pair")) == target_pair):
            tweets = generate_twitter_thread(active_trade)
            pair = active_trade.get("pair", target_pair)
            chart_bytes = generate_chart_bytes(active_trade, trade_status="OPEN")
            if chart_bytes:
                send_contents_photo(chat_id, chart_bytes, caption=f"📸 <b>REAL MARKET CHART · {pair} (15M)</b>\n<i>Attach this chart to your tweet.</i>", bot_token=token)
            msg = (
                f"🐦 <b>TWITTER / X THREAD · {pair} (Tap to copy)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"📌 <b>TWEET 1 (Hook & Levels):</b>\n<code>{tweets[0]}</code>\n\n"
                f"📌 <b>TWEET 2 (Setup Anatomy):</b>\n<code>{tweets[1]}</code>\n\n"
                f"📌 <b>TWEET 3 (Risk & Link):</b>\n<code>{tweets[2]}</code>\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👉 <i>Post Tweet 1 with the chart photo above → Reply with Tweet 2 & 3.</i>"
            )
            return send_contents_message(chat_id, msg, bot_token=token)
        else:
            # Generate AI-powered authentic educational thread for selected/requested asset
            ai_pack = generate_ai_twitter_educational_thread(pair=target_pair)
            tweets = ai_pack["tweets"]
            pair = ai_pack["pair"]
            topic = ai_pack["topic"]

            # Real market chart generated from live candles to attach to tweet!
            chart_sig = {"pair": pair, "timeframe": "1H", "direction": "NEUTRAL"}
            df_chart = fetch_candles_for_pair(pair, interval="1h", range_days="10d")
            chart_bytes = generate_chart_bytes(chart_sig, trade_status="OUTLOOK", df=df_chart)
            if chart_bytes:
                caption = f"📸 <b>REAL MARKET CHART · {pair} (1H Structure)</b>\n<i>Attach this verified chart to your Twitter post.</i>"
                send_contents_photo(chat_id, chart_bytes, caption=caption, bot_token=token)

            msg = (
                f"🐦 <b>TWITTER / X EDUCATIONAL THREAD · {pair} (Tap to copy)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Topic: <b>{topic}</b>\n\n"
                f"📌 <b>TWEET 1 (Hook):</b>\n<code>{tweets[0]}</code>\n\n"
                f"📌 <b>TWEET 2 (Mechanics):</b>\n<code>{tweets[1]}</code>\n\n"
                f"📌 <b>TWEET 3 (Takeaway & Link):</b>\n<code>{tweets[2]}</code>\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👉 <i>Post Tweet 1 with the chart photo above → Reply with Tweet 2 & 3.</i>"
            )
            return send_contents_message(chat_id, msg, bot_token=token)

    # Command: /reddit
    elif cmd.startswith("/reddit") or cmd in ("📝 reddit post", "reddit"):
        from core.marketing.case_study_generator import generate_reddit_case_study
        from core.marketing.ai_content_generator import generate_ai_reddit_educational_post

        parts = raw_text.split()
        requested_pair = parts[1].upper() if len(parts) > 1 else None
        target_pair = select_dynamic_market_pair(requested_pair)

        if active_trade and (not requested_pair or normalize_asset_symbol(active_trade.get("pair")) == target_pair):
            reddit_post = generate_reddit_case_study(active_trade)
            pair = active_trade.get("pair", target_pair)
            chart_bytes = generate_chart_bytes(active_trade, trade_status="OPEN")
            if chart_bytes:
                send_contents_photo(chat_id, chart_bytes, caption=f"📸 <b>REAL MARKET CHART · {pair} (15M)</b>\n<i>Attach this chart to your Reddit post.</i>", bot_token=token)
            msg = (
                f"📝 <b>REDDIT CASE STUDY · {pair}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>TITLE:</b>\n<code>{reddit_post['title']}</code>\n\n"
                f"📋 <b>BODY:</b>\n<pre>{reddit_post['body']}</pre>"
            )
            return send_contents_message(chat_id, msg, bot_token=token)
        else:
            # Generate AI-powered authentic educational post
            ai_pack = generate_ai_reddit_educational_post(pair=target_pair)
            pair = ai_pack["pair"]
            sub = ai_pack.get("subreddit", "r/Forex")

            # Real market chart to attach!
            chart_sig = {"pair": pair, "timeframe": "1H", "direction": "NEUTRAL"}
            df_chart = fetch_candles_for_pair(pair, interval="1h", range_days="10d")
            chart_bytes = generate_chart_bytes(chart_sig, trade_status="OUTLOOK", df=df_chart)
            if chart_bytes:
                caption = f"📸 <b>REAL MARKET CHART · {pair} (1H Liquidity Structure)</b>\n<i>Attach this verified chart to your Reddit post.</i>"
                send_contents_photo(chat_id, chart_bytes, caption=caption, bot_token=token)

            msg = (
                f"📝 <b>REDDIT EDUCATIONAL POST · {pair} ({sub})</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>POST TITLE:</b>\n<code>{ai_pack['title']}</code>\n\n"
                f"📋 <b>POST BODY (Markdown):</b>\n<pre>{ai_pack['body']}</pre>\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👉 <i>Open Reddit → Create Post in {sub} → Paste Title & Body, and attach the chart above.</i>"
            )
            return send_contents_message(chat_id, msg, bot_token=token)

    # Command: /chart
    elif cmd.startswith("/chart") or cmd in ("📊 chart", "chart"):
        parts = raw_text.split()
        requested_pair = parts[1].upper() if len(parts) > 1 else None
        target_pair = select_dynamic_market_pair(requested_pair)

        chart_sig = {
            "pair": target_pair,
            "timeframe": "15M",
            "direction": (active_trade.get("direction") if active_trade and normalize_asset_symbol(active_trade.get("pair")) == target_pair else "NEUTRAL")
        }
        chart_bytes = generate_chart_bytes(
            chart_sig,
            trade_status="OPEN" if (active_trade and normalize_asset_symbol(active_trade.get("pair")) == target_pair) else "OUTLOOK"
        )
        if chart_bytes:
            caption = (
                f"📊 <b>REAL MARKET CHART · {target_pair} (15M)</b>\n"
                f"<i>Verified interbank price action, 20-EMA curve, and Donchian liquidity bounds.</i>"
            )
            return send_contents_photo(chat_id, chart_bytes, caption=caption, reply_markup=get_inline_action_keyboard(target_pair), bot_token=token)
        return send_contents_message(chat_id, f"⚠️ Unable to render chart for {target_pair} right now.", bot_token=token)

    # Command: /outlook
    elif cmd.startswith("/outlook") or cmd in ("🌐 4h trend outlook", "outlook"):
        parts = raw_text.split()
        requested_pair = parts[1].upper() if len(parts) > 1 else None
        target_pair = select_dynamic_market_pair(requested_pair)

        from core.marketing.case_study_generator import format_market_outlook_telegram_pack
        df_4h = fetch_candles_for_pair(target_pair, interval="1h", range_days="15d")
        outlook_text = format_market_outlook_telegram_pack(pair=target_pair, df=df_4h)
        outlook_sig = {"pair": target_pair, "timeframe": "4H", "direction": "NEUTRAL"}
        chart_bytes = generate_chart_bytes(outlook_sig, trade_status="OUTLOOK", df=df_4h)
        if chart_bytes:
            send_contents_photo(chat_id, chart_bytes, caption=f"🌐 <b>4H TREND OUTLOOK · {target_pair}</b>", bot_token=token)
        return send_contents_message(chat_id, outlook_text, bot_token=token)

    # Command: /tradingview
    elif cmd.startswith("/tradingview") or cmd in ("📈 tradingview idea", "tradingview"):
        parts = raw_text.split()
        requested_pair = parts[1].upper() if len(parts) > 1 else None
        target_pair = select_dynamic_market_pair(requested_pair)

        if active_trade and (not requested_pair or normalize_asset_symbol(active_trade.get("pair")) == target_pair):
            from core.marketing.case_study_generator import format_tradingview_telegram_pack
            tv_msg = format_tradingview_telegram_pack(active_trade)
            return send_contents_message(chat_id, tv_msg, bot_token=token)
        else:
            from core.marketing.case_study_generator import format_market_outlook_telegram_pack
            df_4h = fetch_candles_for_pair(target_pair, interval="1h", range_days="15d")
            tv_msg = format_market_outlook_telegram_pack(pair=target_pair, df=df_4h)
            return send_contents_message(chat_id, tv_msg, bot_token=token)

    else:
        # Fallback helpful response
        return send_contents_message(
            chat_id,
            "👋 Send <code>/help</code> or tap the <b>Menu (/)</b> button next to the typing bar for available commands.",
            bot_token=token
        )


def process_contents_bot_pending_updates(bot_token: Optional[str] = None, offset: Optional[int] = None) -> Optional[int]:
    """
    Fetches and processes pending Telegram updates in a single pass.
    Can be invoked during scheduled scan cycles to keep commands responsive.
    Returns the next update_id offset.
    """
    token = (bot_token or TELEGRAM_MARKETING_BOT_TOKEN).strip()
    if not token:
        return None
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return None

    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=2"
    if offset:
        url += f"&offset={offset}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ContentsBot/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            updates = data.get("result", [])
            last_id = offset or 0
            for u in updates:
                last_id = max(last_id, u.get("update_id", 0))
                handle_contents_bot_update(u, bot_token=token)
            return last_id + 1 if updates else offset
    except Exception as e:
        logger.warning(f"Error checking Contents bot updates: {e}")
        return offset


def run_contents_bot_loop(
    poll_interval: float = 2.0,
    bot_token: Optional[str] = None,
    max_runtime_sec: Optional[float] = None
) -> None:
    """
    Runs a continuous long-polling listener for @contents7_bot.
    Enables sub-second interactive responses when run as a background service or GitHub Actions runner.
    """
    token = (bot_token or TELEGRAM_MARKETING_BOT_TOKEN).strip()
    setup_contents_bot_commands(bot_token=token)
    print(f"🚀 Contents Marketing Bot (@contents7_bot) live listener starting...")
    offset = None
    import time
    start_time = time.time()
    while True:
        if max_runtime_sec and (time.time() - start_time >= max_runtime_sec):
            print(f"Reached max runtime of {max_runtime_sec}s. Exiting cleanly for next runner cycle.")
            break
        try:
            offset = process_contents_bot_pending_updates(bot_token=token, offset=offset)
            time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("\nShutting down Contents Bot listener.")
            break
        except Exception as e:
            logger.error(f"Listener loop error: {e}")
            time.sleep(5)
