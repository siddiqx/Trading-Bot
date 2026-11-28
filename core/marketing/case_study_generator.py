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
    Generates a complete, TradingView-compliant Idea publication pack.
    Formats title, tags, and rich technical analysis ready to publish in 1 click.
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
    try:
        entry_str = f"{float(entry):.{digits}f}"
        sl_str = f"{float(sl):.{digits}f}"
        tp_str = f"{float(tp):.{digits}f}"
    except Exception:
        entry_str, sl_str, tp_str = str(entry), str(sl), str(tp)

    if realized_pips is not None and realized_r is not None:
        pips_str = f"+{realized_pips:.1f}" if realized_pips >= 0 else f"{realized_pips:.1f}"
        r_str = f"+{realized_r:.2f}R" if realized_r >= 0 else f"{realized_r:.2f}R"
        title = f"{display_pair}: 15M Institutional Order Block Reversal • {pips_str} Pips ({r_str}) Target Hit"
        intro_status = f"Status: Full Take Profit Hit (+{pips_str} pips / {r_str})\n"
    else:
        title = f"{display_pair} ({timeframe}): Institutional Order Block Retest & CCRS Divergence {dir_word}"
        intro_status = f"Order Type: {direction} ({timeframe})\n"

    if direction == "SHORT":
        sweep_desc = "• Liquidity Sweep: Buy-Side Liquidity (BSL) swept at local fractal highs, trapping premature breakout buyers."
        mss_desc = "• Structure Confirmation: Confirmed 15M Market Structure Shift (MSS ▾) breaking lower with displacement."
        ob_desc = "• Order Block Mitigation: Clean tap into Bearish Order Block (-OB / Supply) with 20-EMA dynamic resistance."
        target_desc = f"• Draw on Liquidity (DOL): Targeting resting Sell-Side Liquidity (SSL) pool at {tp_str}"
    else:
        sweep_desc = "• Liquidity Sweep: Sell-Side Liquidity (SSL) swept below local fractal lows, clearing retail sell stops."
        mss_desc = "• Structure Confirmation: Confirmed 15M Market Structure Shift (MSS ▴) breaking higher with displacement."
        ob_desc = "• Order Block Mitigation: Clean tap into Bullish Order Block (+OB / Demand) with 20-EMA dynamic support."
        target_desc = f"• Draw on Liquidity (DOL): Targeting resting Buy-Side Liquidity (BSL) pool at {tp_str}"

    description = (
        f"{display_pair} Systematic {action_type} ({timeframe})\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{intro_status}"
        f"Strategy: Dual-Timeframe CCRS Macro Flow + ICT Order Block Retest\n\n"
        f"1. MACRO & RELATIVE STRENGTH CONFLUENCE\n"
        f"• 7-Currency Factor Engine: Rolling 120-hour CCRS divergence (|D| ≥ 1.75σ) normalized by 200-hour volatility.\n"
        f"• The synthetic currency basket confirms institutional order flow backing the {direction.lower()} move.\n\n"
        f"2. PRECISION EXECUTION (15M SMC ORDER FLOW)\n"
        f"{sweep_desc}\n"
        f"{mss_desc}\n"
        f"{ob_desc}\n"
        f"• Execution Level: {entry_str}\n"
        f"• Invalidation (Stop Loss): {sl_str} (2.0× ATR Volatility Buffer)\n"
        f"{target_desc} (1:{rr:.2f}R Geometric Target)\n\n"
        f"3. CAPITAL PRESERVATION & RISK MANAGEMENT\n"
        f"• Position Sizing: Strict 0.50% to 1.00% risk per trade (Prop Firm Compliant).\n"
        f"• Dynamic Trailing: Volatility cushion stop trailing active at +1.20R to eliminate drawdown.\n\n"
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


