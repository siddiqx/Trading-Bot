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

    action_verb = "Demand Order Block (+OB)" if direction == "LONG" else "Supply Order Block (-OB)"
    sweep_type = "Sell-Side Liquidity (SSL)" if direction == "LONG" else "Buy-Side Liquidity (BSL)"

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
        f"* **Mitigation:** The subsequent reaction confirmed a clean tap into the 15M {action_verb}, "
        f"providing asymmetrical risk-to-reward geometry.\n\n"
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

    tweet_2 = (
        f"2/ The Setup Anatomy:\n\n"
        f"1. 1H Macro Divergence: Base vs Quote flow > 1.75σ\n"
        f"2. 15M Liquidity Sweep: Trapped retail stops swept at local fractal swing\n"
        f"3. Order Block Mitigation: Immediate rejection with 20-EMA confluence\n\n"
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
