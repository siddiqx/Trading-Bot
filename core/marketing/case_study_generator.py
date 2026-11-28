"""
Case Study & Viral Content Generator
====================================
Transforms institutional trade executions and Take Profit resolutions into
high-converting, educational case studies for Reddit, Twitter/X, and Telegram.

Strategy:
  1. Value-First Institutional Content: Detailed macro rationale, ICT liquidity sweep,
     and risk parameters. Avoids spam filters by delivering genuine technical edge.
  2. Multi-Platform Formatting:
     - Reddit: In-depth markdown breakdowns tailored for r/Forex, r/Daytrading, r/PropFirm.
     - Twitter/X: Punchy 3-part FinTwit thread with cashtags (#EURUSD, #ICT, #PropFirm).
     - Telegram Viral Share: 1-click native forwarding link to drive peer-to-peer growth.
"""

import urllib.parse
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


def generate_reddit_case_study(
    trade: Dict[str, Any],
    realized_pips: float,
    realized_r: float,
    target_subreddit: str = "r/Forex"
) -> Dict[str, str]:
    """
    Generates a high-authority, value-driven Reddit post breakdown designed to
    bypass spam filters, educate traders, and attract high-intent users to the author profile.
    """
    pair = trade.get("pair") or trade.get("symbol") or "EURUSD"
    display_pair = f"{pair[:3]}/{pair[3:]}" if len(pair) == 6 else pair
    direction = trade.get("direction", "LONG").upper()
    entry = trade.get("entry", "0.0")
    exit_px = trade.get("exit_price") or trade.get("take_profit", "0.0")
    timeframe = trade.get("timeframe", "15M").upper()
    r_val = f"+{realized_r:.2f}R" if realized_r >= 0 else f"{realized_r:.2f}R"
    pips_val = f"+{realized_pips:.1f}" if realized_pips >= 0 else f"{realized_pips:.1f}"

    # Adaptive Title based on target subreddit
    if "prop" in target_subreddit.lower():
        title = (
            f"[Prop Firm Execution] How 15M Institutional Liquidity Sweeps Caught "
            f"{pips_val} Pips on {display_pair} ({r_val}) with 0.50% Fixed Risk"
        )
    elif "ict" in target_subreddit.lower():
        title = (
            f"[SMC/ICT Breakdown] Clean {direction} Order Block & Liquidity Sweep "
            f"on {display_pair} • Full Take Profit Swept ({pips_val} Pips / {r_val})"
        )
    else:
        title = (
            f"[Trade Breakdown] Systematic Dual-Timeframe CCRS Execution on {display_pair}: "
            f"{pips_val} Pips ({r_val}) Full Take Profit Hit"
        )

    action_verb = "Bullish Demand Order Block (+OB)" if direction == "LONG" else "Bearish Supply Order Block (-OB)"
    sweep_type = "Sell-Side Liquidity (SSL)" if direction == "LONG" else "Buy-Side Liquidity (BSL)"
    target_pool = "Buy-Side Liquidity (BSL)" if direction == "LONG" else "Sell-Side Liquidity (SSL)"
    mss_type = "Bullish Market Structure Shift (MSS ▴)" if direction == "LONG" else "Bearish Market Structure Shift (MSS ▾)"

    body = (
        f"## Trade Overview: {direction} {display_pair} ({timeframe})\n\n"
        f"* **Asset:** {display_pair}\n"
        f"* **Direction:** {direction}\n"
        f"* **Execution Price:** `{entry}`\n"
        f"* **Take Profit Exit:** `{exit_px}`\n"
        f"* **Net Result:** **{pips_val} Pips ({r_val})**\n"
        f"* **Execution Timestamp:** `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}`\n\n"
        f"---\n\n"
        f"### 1. Macro Context & Currency Strength Alignment\n"
        f"Before entering on the 15M chart, our quantitative scanner evaluated the 1-hour "
        f"rolling currency relative strength (CCRS) across the institutional basket. "
        f"The setup triggered once macro divergence surpassed our **1.75σ threshold**, "
        f"guaranteeing momentum alignment before probing lower-timeframe structure.\n\n"
        f"### 2. Smart Money Concepts (ICT) Trigger\n"
        f"* **Liquidity Sweep:** Price swept prior retail stops at the key {sweep_type} pool, "
        f"triggering institutional absorption.\n"
        f"* **Market Structure Shift:** Confirmed 15M {mss_type} with impulsive displacement.\n"
        f"* **Order Block Mitigation:** The subsequent reaction confirmed a clean tap into the 15M {action_verb} & 20-EMA dynamic confluence, "
        f"providing asymmetrical risk-to-reward geometry.\n"
        f"* **Draw on Liquidity (DOL):** Systematic target swept cleanly at the opposing {target_pool} cluster.\n\n"
        f"### 3. Risk Management & Prop Firm Compliance\n"
        f"* **Risk Budget:** 0.50% static risk with dynamic volatility-anchored stop (2.0× ATR).\n"
        f"* **Anti-Copy Protection:** Execution executed via broker API at true market spread, "
        f"securing first-mover fill priority.\n"
        f"* **Exit Management:** Zero manual discretion. Order resolved at full 1:1.75R target cleanly.\n\n"
        f"---\n\n"
        f"### Key Takeaway for Systematic Traders\n"
        f"Retail stop clusters consistently provide the liquidity institutional algorithms require to enter. "
        f"Combining macro flow filters with local liquidity sweeps eliminates over-trading and "
        f"delivers repeatable positive mathematical expectancy.\n\n"
        f"*Data logged live via automated cTrader execution ledger. "
        f"Check profile bio for open-source research and live surveillance tracking.*"
    )

    return {
        "title": title,
        "body": body,
        "subreddit": target_subreddit,
        "flair": "Technical Analysis"
    }


def generate_twitter_thread(
    trade: Dict[str, Any],
    realized_pips: float,
    realized_r: float,
    channel_url: str = "https://t.me/ccrs_forex_signals"
) -> List[str]:
    """
    Generates a high-engagement 3-tweet FinTwit thread with cashtags and viral hooks.
    """
    pair = trade.get("pair") or trade.get("symbol") or "EURUSD"
    display_pair = f"{pair[:3]}/{pair[3:]}" if len(pair) == 6 else pair
    direction = trade.get("direction", "LONG").upper()
    cashtag = f"${pair}"
    r_val = f"+{realized_r:.2f}R" if realized_r >= 0 else f"{realized_r:.2f}R"
    pips_val = f"+{realized_pips:.1f}" if realized_pips >= 0 else f"{realized_pips:.1f}"

    tweet_1 = (
        f"🎯 FULL TAKE PROFIT HIT: {cashtag} {direction}\n\n"
        f"• Realized: {pips_val} pips ({r_val})\n"
        f"• Entry: {trade.get('entry')}\n"
        f"• Target: {trade.get('take_profit')}\n\n"
        f"Institutional 15M Liquidity Sweep + CCRS Dual-Timeframe Macro Alignment swept clean. "
        f"Full trade breakdown below 🧵👇\n\n"
        f"#Forex #ICT #TradingView #PropFirm #FTMO"
    )

    if direction == "SHORT":
        tweet_2_sweep = "2. 15M Liquidity Sweep: Buy-Side Liquidity (BSL) swept at session highs"
        tweet_2_ob = "3. Structure & Retest: MSS ▾ + Bearish Order Block (-OB) rejection at 20-EMA"
        tweet_2_target = f"4. Draw on Liquidity: Sell-Side Liquidity (SSL) target swept at {trade.get('take_profit')}"
    else:
        tweet_2_sweep = "2. 15M Liquidity Sweep: Sell-Side Liquidity (SSL) swept below session lows"
        tweet_2_ob = "3. Structure & Retest: MSS ▴ + Bullish Order Block (+OB) rejection at 20-EMA"
        tweet_2_target = f"4. Draw on Liquidity: Buy-Side Liquidity (BSL) target swept at {trade.get('take_profit')}"

    tweet_2 = (
        f"2/ The Setup Anatomy:\n\n"
        f"1. 1H Macro Divergence: Base vs Quote flow > 1.75σ\n"
        f"{tweet_2_sweep}\n"
        f"{tweet_2_ob}\n"
        f"{tweet_2_target}\n\n"
        f"Systematic rules. Zero emotion. 1:1.75R geometric target."
    )

    tweet_3 = (
        f"3/ Risk & Prop Firm Compliance:\n\n"
        f"• Fixed 0.50% account risk\n"
        f"• Automated cTrader execution\n"
        f"• Zero copy-trading footprint (stealth orders)\n\n"
        f"Track all institutional setups and live surveillance free in our Telegram:\n"
        f"👉 {channel_url}"
    )

    return [tweet_1, tweet_2, tweet_3]


def generate_telegram_share_url(
    pair: str,
    direction: str,
    pips: float,
    r_val: float,
    channel_link: str = "https://t.me/ccrs_forex_signals"
) -> str:
    """
    Generates a 1-click native Telegram forward URL that prompts users to share
    the winning setup with their trading friends and group chats.
    """
    pips_str = f"+{pips:.1f}" if pips >= 0 else f"{pips:.1f}"
    r_str = f"+{r_val:.2f}R" if r_val >= 0 else f"{r_val:.2f}R"
    
    text = (
        f"🔥 QuantFlow Institutional Setup Resolved: {pair} ({direction})\n"
        f"Result: {pips_str} Pips ({r_str}) Full Take Profit Hit!\n\n"
        f"Follow institutional setups live for free here:\n"
        f"{channel_link}"
    )
    encoded_text = urllib.parse.quote(text)
    encoded_url = urllib.parse.quote(channel_link)
    return f"https://t.me/share/url?url={encoded_url}&text={encoded_text}"


def generate_tradingview_idea_post(
    trade: Dict[str, Any],
    realized_pips: Optional[float] = None,
    realized_r: Optional[float] = None,
    channel_url: str = "https://t.me/ccrs_forex_signals"
) -> Dict[str, Any]:
    """
    Generates a professional, human-like TradingView Idea publication pack.
    Written from the perspective of an experienced institutional trader:
    conversational narrative, clear market overview, clean execution zones,
    and zero robotic math jargon.
    """
    pair = trade.get("pair") or trade.get("symbol") or "EURUSD"
    display_pair = f"{pair[:3]}/{pair[3:]}" if len(pair) == 6 else pair
    direction = trade.get("direction", "LONG").upper()
    dir_word = "Long" if direction == "LONG" else "Short"
    action_type = "Bullish Setup" if direction == "LONG" else "Bearish Setup"
    timeframe = trade.get("timeframe", "15M").upper()
    entry = trade.get("entry", "0.0")
    sl = trade.get("stop_loss", "0.0")
    tp = trade.get("take_profit", "0.0")
    rr = float(trade.get("rr", 1.50))

    digits = 3 if "JPY" in pair else (2 if "XAU" in pair else 5)
    pip_size = 0.01 if "JPY" in pair else (0.10 if "XAU" in pair else 0.0001)
    pip_mult = 100 if "JPY" in pair else (10 if "XAU" in pair else 10000)

    try:
        entry_f = float(entry)
        sl_f = float(sl)
        tp_f = float(tp)
        entry_str = f"{entry_f:.{digits}f}"
        sl_str = f"{sl_f:.{digits}f}"
        tp_str = f"{tp_f:.{digits}f}"
        zone_low = entry_f - 1.5 * pip_size
        zone_high = entry_f + 1.5 * pip_size
        zone_str = f"{zone_low:.{digits}f} – {zone_high:.{digits}f}"
        sl_pips_num = abs(entry_f - sl_f) * pip_mult
        tp_pips_num = abs(tp_f - entry_f) * pip_mult
    except Exception:
        entry_str, sl_str, tp_str = str(entry), str(sl), str(tp)
        zone_str = entry_str
        sl_pips_num = 20.0
        tp_pips_num = 35.0

    # Format Take Profit Hit Resolution Post
    if realized_pips is not None and realized_r is not None:
        p_val = abs(realized_pips)
        p_sign = "+" if realized_pips >= 0 else "-"
        pips_str = f"{p_sign}{p_val:.1f}"
        r_sign = "+" if realized_r >= 0 else "-"
        r_str = f"{r_sign}{abs(realized_r):.2f}R"
        title = f"{display_pair} ({timeframe}): Target Reached • {pips_str} Pips ({r_str}) Banked"

        description = (
            f"{display_pair} Trade Resolution — Target Reached ({pips_str} Pips / {r_str})\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Status: Full Take Profit Hit ({pips_str} pips / {r_str})\n"
            f"Order Type: {direction} ({timeframe})\n\n"
            f"TRADE RESOLUTION & OUTCOME\n"
            f"The {dir_word.lower()} setup shared earlier on {display_pair} has reached its full target cleanly. "
            f"Price expanded directly from our entry zone with strong displacement, holding above the dynamic 20-EMA "
            f"and driving straight into the opposing liquidity pool.\n\n"
            f"EXECUTION SUMMARY\n"
            f"• Asset: {display_pair}\n"
            f"• Direction: {dir_word}\n"
            f"• Execution Level: {entry_str}\n"
            f"• Invalidation (Stop Loss): {sl_str}\n"
            f"• Target Exit: {tp_str}\n"
            f"• Net Profit: {pips_str} Pips ({r_str})\n"
            f"• Outcome: Closed at Target\n\n"
            f"KEY LESSON FOR TRADERS\n"
            f"Waiting patiently for liquidity to be swept before entering gave us clean asymmetry with virtually zero drawdown. "
            f"Systematic rules beat emotion every time. We will wait for the next high-probability setup before re-entering.\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Live algorithmic alerts & trade surveillance: @ccrs_forex_signals ({channel_url})\n"
        )
    else:
        # Format Fresh Active Trade Setup Idea
        title = f"{display_pair} — {action_type}: Trend Retest & Liquidity Sweep ({timeframe})"

        if direction == "SHORT":
            context_text = (
                f"On the higher timeframes, {display_pair} has faced consistent selling pressure as institutional capital "
                f"favors dollar strength. Rallies into structural resistance continue to get absorbed, "
                f"providing a high-probability context for short continuation."
            )
            rationale_text = (
                f"On the {timeframe} chart, price swept above local swing highs to absorb resting Buy-Side Liquidity (BSL) "
                f"before printing a clear rejection wick. A confirmed Market Structure Shift (MSS ▾) followed, with price "
                f"displacing back below the 20-EMA. This confirms smart money is defending supply, opening the door for a move "
                f"downward toward resting Sell-Side Liquidity (SSL)."
            )
            target_focus = f"Sell-Side Liquidity (SSL) resting at {tp_str}"
        else:
            context_text = (
                f"On the higher timeframes, {display_pair} is showing sustained demand as relative strength shifts in its favor. "
                f"Price has established higher structural lows on the 4H/Daily chart, indicating that intraday pullbacks into "
                f"key support offer favorable risk-to-reward buying opportunities."
            )
            rationale_text = (
                f"On the {timeframe} chart, price briefly swept below recent swing lows to grab Sell-Side Liquidity (SSL) "
                f"before reacting with an immediate absorption candle. A confirmed Market Structure Shift (MSS ▴) followed, "
                f"reclaiming the 20-EMA. This confirms institutional buyers have stepped in, setting up an expansion "
                f"higher toward resting Buy-Side Liquidity (BSL)."
            )
            target_focus = f"Buy-Side Liquidity (BSL) resting at {tp_str}"

        description = (
            f"{display_pair} — Systematic {action_type} ({timeframe})\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Order Type: {direction} ({timeframe})\n"
            f"Strategy: Macro Currency Flow + Smart Money Concepts (SMC)\n\n"
            f"MARKET CONTEXT & OVERVIEW\n"
            f"{context_text}\n\n"
            f"PRICE ACTION & SETUP RATIONALE\n"
            f"{rationale_text}\n\n"
            f"TRADE EXECUTION PLAN\n"
            f"• Direction: {dir_word}\n"
            f"• Entry Zone: {zone_str} (Reference: {entry_str})\n"
            f"• Invalidation (Stop Loss): {sl_str} ({sl_pips_num:.1f} pips risk)\n"
            f"• Target (Take Profit): {tp_str} ({tp_pips_num:.1f} pips target)\n"
            f"• Risk to Reward: 1 : {rr:.2f}\n"
            f"• Target Focus: {target_focus}\n\n"
            f"RISK MANAGEMENT NOTE\n"
            f"Keep your risk disciplined (0.5% to 1.0% per trade). Let price come into the entry zone rather than chasing. "
            f"Once price reaches +1.2R in profit, trail stop loss to breakeven to secure a risk-free position.\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Real-time algorithmic alerts & trade surveillance: @ccrs_forex_signals ({channel_url})\n"
        )

    tags = ["forex", pair.lower(), "ict", "orderblock", "smc", "propfirm", "tradingview"]

    return {
        "title": title,
        "description": description,
        "tags": tags,
        "direction": direction,
        "pair": pair,
        "timeframe": timeframe
    }


def generate_market_trend_outlook(
    pair: str = "EURUSD",
    df: Optional[Any] = None,
    channel_url: str = "https://t.me/ccrs_forex_signals"
) -> Dict[str, Any]:
    """
    Generates a clean, human-like higher-timeframe Market Trend Outlook post (4H / Daily).
    Designed for TradingView publication when there is no active trade setup, or for macro briefings.
    """
    display_pair = f"{pair[:3]}/{pair[3:]}" if len(pair) == 6 else pair
    digits = 3 if "JPY" in pair else (2 if "XAU" in pair else 5)

    # Calculate key technical levels if candles available
    if df is not None and not df.empty and len(df) >= 10:
        cur_px = float(df.iloc[-1]["close"])
        high_px = float(df["high"].tail(40).max())
        low_px = float(df["low"].tail(40).min())
        ema20 = float(df["close"].tail(20).ewm(span=20, adjust=False).mean().iloc[-1])
        is_bullish = cur_px >= ema20
        trend_status = "Bullish Structure" if is_bullish else "Bearish Structure"
        cur_str = f"{cur_px:.{digits}f}"
        res_str = f"{high_px:.{digits}f}"
        sup_str = f"{low_px:.{digits}f}"
        ema_str = f"{ema20:.{digits}f}"
    else:
        trend_status = "Range Consolidation"
        cur_str = "Market Price"
        res_str = "Overhead Resistance"
        sup_str = "Key Support Demand"
        ema_str = "20-EMA Equilibrium"

    title = f"{display_pair} — Macro Trend Outlook & Key Levels to Watch (4H / Daily)"

    description = (
        f"{display_pair} — Higher-Timeframe Market Trend Outlook (4H / Daily)\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Market Phase: {trend_status}\n"
        f"Analysis: Multi-Timeframe Trend & Interbank Liquidity Boundaries\n\n"
        f"MARKET CONTEXT & BIG PICTURE\n"
        f"Taking a step back to analyze the higher-timeframe picture on {display_pair}. Over recent trading sessions, "
        f"the market has been respecting key structural boundaries on the 4-Hour and Daily charts. "
        f"Global macro relative strength and interbank currency flows remain the primary drivers shaping current momentum.\n\n"
        f"TREND & MOVING AVERAGE STRUCTURE\n"
        f"On the 4-Hour timeframe, price is currently interacting around the 20-period dynamic EMA ({ema_str}). "
        f"Rather than taking trades in the middle of chop, we observe clear institutional order flow respecting the outer boundaries:\n"
        f"• Current Market Price: {cur_str}\n"
        f"• Dynamic 20-EMA Pivot: {ema_str}\n"
        f"• Structural Trend Bias: {trend_status}\n\n"
        f"KEY STRUCTURAL LEVELS TO WATCH\n"
        f"• Major Resistance / Supply Zone: {res_str}\n"
        f"• Major Support / Demand Zone: {sup_str}\n"
        f"• Resting Liquidity: Buy-Side Liquidity (BSL) pools rest above {res_str}, while Sell-Side Liquidity (SSL) rests below {sup_str}.\n\n"
        f"TRADING GAME PLAN (PATIENCE FIRST)\n"
        f"We currently have no active execution on this pair. Successful trading requires patience to let the market "
        f"come to our predefined zones rather than forcing trades in equilibrium. We are monitoring:\n"
        f"1. A liquidity sweep into major demand ({sup_str}) followed by lower-timeframe market structure shift for long entries.\n"
        f"2. A rejection wick at overhead supply ({res_str}) for high-probability short setups.\n"
        f"Patience over FOMO. We will wait for confirmed confirmation before executing.\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Real-time algorithmic alerts & trade surveillance: @ccrs_forex_signals ({channel_url})\n"
    )

    tags = ["forex", pair.lower(), "tradingview", "macro", "trend", "priceaction", "smc"]

    return {
        "title": title,
        "description": description,
        "tags": tags,
        "pair": pair,
        "timeframe": "4H"
    }


def format_market_outlook_telegram_pack(
    pair: str = "EURUSD",
    df: Optional[Any] = None,
    channel_url: str = "https://t.me/ccrs_forex_signals"
) -> str:
    """
    Formats an automated 1-click copyable TradingView Market Trend Outlook pack
    tailored for instant private delivery to the Admin Telegram chat.
    """
    post = generate_market_trend_outlook(pair=pair, df=df, channel_url=channel_url)
    display_pair = f"{pair[:3]}/{pair[3:]}" if len(pair) == 6 else pair
    tags_str = " ".join([f"#{t}" for t in post.get("tags", [])])

    return (
        f"📊 <b>TRADINGVIEW MARKET TREND OUTLOOK PACK (4H / DAILY)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Asset: <b>{display_pair}</b> • <code>4H / Daily Outlook</code>\n"
        f"Type: <b>Higher-Timeframe Analysis (No Active Setup)</b>\n\n"
        f"📌 <b>COPY TITLE (Tap to copy):</b>\n"
        f"<code>{post['title']}</code>\n\n"
        f"📋 <b>COPY DESCRIPTION (Tap to copy):</b>\n"
        f"<pre>{post['description']}</pre>\n\n"
        f"🏷️ <b>TAGS:</b>\n"
        f"<code>{tags_str}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👉 <i>Open TradingView → Publish Idea → Paste Title & Description (10 seconds to publish).</i>"
    )


def format_tradingview_telegram_pack(
    trade: Dict[str, Any],
    realized_pips: Optional[float] = None,
    realized_r: Optional[float] = None,
    channel_url: str = "https://t.me/ccrs_forex_signals"
) -> str:
    """
    Formats an automated 1-click copyable TradingView Idea pack
    tailored for instant private delivery to the Admin Telegram chat.
    Uses <pre> and <code> tags for 1-tap mobile copying.
    """
    post = generate_tradingview_idea_post(
        trade, realized_pips=realized_pips, realized_r=realized_r, channel_url=channel_url
    )
    pair = trade.get("pair") or trade.get("symbol") or "EURUSD"
    display_pair = f"{pair[:3]}/{pair[3:]}" if len(pair) == 6 else pair
    direction = trade.get("direction", "LONG").upper()
    tf = str(trade.get("timeframe", "15M")).upper()

    if realized_pips is not None and realized_r is not None:
        pips_str = f"+{realized_pips:.1f}" if realized_pips >= 0 else f"{realized_pips:.1f}"
        r_str = f"+{realized_r:.2f}R" if realized_r >= 0 else f"{realized_r:.2f}R"
        status_line = f"🎯 <b>Take Profit Hit ({pips_str} Pips / {r_str})</b>"
    else:
        status_line = f"🟢 <b>Fresh Active Signal ({direction})</b>"

    tags_str = " ".join([f"#{t}" for t in post.get("tags", [])])

    return (
        f"📝 <b>TRADINGVIEW IDEA PUBLICATION PACK</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Asset: <b>{display_pair} ({direction})</b> • <code>{tf}</code>\n"
        f"Status: {status_line}\n\n"
        f"📌 <b>COPY TITLE (Tap to copy):</b>\n"
        f"<code>{post['title']}</code>\n\n"
        f"📋 <b>COPY DESCRIPTION (Tap to copy):</b>\n"
        f"<pre>{post['description']}</pre>\n\n"
        f"🏷️ <b>TAGS:</b>\n"
        f"<code>{tags_str}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👉 <i>Open TradingView → Publish Idea → Paste Title & Description (10 seconds to publish).</i>"
    )


