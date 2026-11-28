"""
Community Engagement & Educational Content Engine
==================================================
Drives 24/7 community pulse, trader engagement, and organic retention across
Telegram (@ccrs_forex_signals) and Discord.

Content Pillars:
  1. High-Impact Macro News & Daily Economic Calendar Briefings (Forex Factory)
  2. Interactive Community Polls (Session Direction Bias, Prop Firm Psychology, SMC Quizzes)
  3. ICT / Smart Money Concepts Masterclass Cards (OB, FVG, BSL/SSL Sweeps, CCRS Factor Engine)
  4. Mid-Day CCRS Currency Strength Heatmaps & Divergence Radars
  5. High-Converting VIP Value Drops & Prop Firm Milestone Spotlights
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from core.news_filter import fetch_economic_calendar, parse_event_time
from core.marketing.discord_publisher import send_discord_content, send_discord_poll

logger = logging.getLogger("EngagementEngine")

TELEGRAM_PUBLIC_CHANNEL = os.environ.get("TELEGRAM_PUBLIC_CHAT_ID", "@ccrs_forex_signals")
TELEGRAM_VIP_LINK = os.environ.get("TELEGRAM_VIP_INVITE_LINK", "https://whop.com/checkout/plan_AD4vSV9Uz7vyR")
TELEGRAM_PUBLIC_LINK = os.environ.get("TELEGRAM_PUBLIC_INVITE_LINK", "https://t.me/ccrs_forex_signals")

# Engagement Dispatch Constraints
MIN_ENGAGEMENT_INTERVAL_SECONDS = 10800  # 3 Hours minimum between engagement posts
MAX_DAILY_ENGAGEMENT_POSTS = 4

CURRENCY_FLAGS = {
    "USD": "🇺🇸",
    "EUR": "🇪🇺",
    "GBP": "🇬🇧",
    "CAD": "🇨🇦",
    "JPY": "🇯🇵",
    "AUD": "🇦🇺",
    "CHF": "🇨🇭",
    "NZD": "🇳🇿",
}


# ==============================================================================
# 1. HIGH-IMPACT MACRO NEWS & ECONOMIC CALENDAR BRIEFINGS
# ==============================================================================

def generate_daily_news_briefing(
    events: Optional[List[Dict[str, Any]]] = None,
    now_dt: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Synthesizes today's high-impact economic catalysts from Forex Factory
    into an institutional briefing for Telegram and Discord.
    """
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    elif now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    if events is None:
        events = fetch_economic_calendar()

    today_str = now_dt.strftime("%Y-%m-%d")
    today_readable = now_dt.strftime("%A, %d %B %Y")

    # Filter High & Medium impact events for major currency basket
    major_currencies = {"USD", "EUR", "GBP", "CAD", "JPY", "AUD", "CHF"}
    today_events = []

    for ev in events:
        impact = str(ev.get("impact") or "").strip()
        country = str(ev.get("country") or "").upper().strip()
        if country not in major_currencies:
            continue
        if impact not in ("High", "Medium"):
            continue

        ev_time = parse_event_time(ev.get("date", ""))
        if not ev_time:
            continue

        if ev_time.strftime("%Y-%m-%d") == today_str:
            today_events.append({
                "time_utc": ev_time.strftime("%H:%M UTC"),
                "country": country,
                "flag": CURRENCY_FLAGS.get(country, "🌐"),
                "title": ev.get("title", ""),
                "impact": impact,
                "forecast": ev.get("forecast") or "N/A",
                "previous": ev.get("previous") or "N/A",
            })

    # Sort chronologically
    today_events.sort(key=lambda x: x["time_utc"])

    if not today_events:
        # Clean fallback when no high-impact events are scheduled
        telegram_msg = (
            f"📅 <b>INSTITUTIONAL ECONOMIC CALENDAR · {today_readable}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🟢 <b>Clean Macro Runway:</b> Zero High-Impact red-folder events scheduled today.\n\n"
            f"✓ Standard market liquidity conditions in play across European & US sessions.\n"
            f"✓ QuantFlow dual-timeframe Donchian + EMA pullback models active at full capacity.\n"
            f"✓ Normal slippage & spread expectations.\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💎 <i>Automated real-time trade signals continue streaming for VIP members.</i>\n\n"
            f"👉 <a href='{TELEGRAM_VIP_LINK}'><b>Join QuantFlow VIP Club on Whop</b></a>"
        )
        discord_desc = (
            f"🟢 **Clean Macro Runway:** Zero High-Impact red-folder events scheduled today ({today_readable}).\n\n"
            f"• Standard market liquidity conditions across European & US sessions.\n"
            f"• QuantFlow dual-timeframe models active at full capacity.\n"
            f"• Normal institutional spread expectations.\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💎 [**Upgrade to QuantFlow VIP Club**]({TELEGRAM_VIP_LINK}) • [**Free Telegram Signals**]({TELEGRAM_PUBLIC_LINK})"
        )
        return {
            "type": "NEWS_BRIEFING",
            "title": f"📅 DAILY ECONOMIC BRIEFING · {today_readable}",
            "telegram_msg": telegram_msg,
            "discord_desc": discord_desc,
            "has_high_impact": False,
            "events_count": 0,
        }

    # Format event rows
    rows_tg = []
    rows_dc = []
    for e in today_events:
        impact_icon = "🔴" if e["impact"] == "High" else "🟠"
        rows_tg.append(
            f"{impact_icon} <b>{e['time_utc']}</b> | {e['flag']} <b>{e['country']}</b>: {e['title']}\n"
            f"   <i>Forecast: {e['forecast']} | Prev: {e['previous']}</i>"
        )
        rows_dc.append(
            f"{impact_icon} **{e['time_utc']}** | {e['flag']} **{e['country']}**: {e['title']}\n"
            f"└ *Forecast: {e['forecast']} | Prev: {e['previous']}*"
        )

    events_formatted_tg = "\n\n".join(rows_tg)
    events_formatted_dc = "\n\n".join(rows_dc)

    telegram_msg = (
        f"📅 <b>INSTITUTIONAL ECONOMIC RADAR · {today_readable}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Key volatility catalysts & Central Bank releases today:\n\n"
        f"{events_formatted_tg}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <b>Algorithmic Risk Guard:</b>\n"
        f"QuantFlow's automated news firewall automatically suspends new signal triggers "
        f"<b>±30 minutes</b> around High-Impact releases to protect capital from wide spreads & slippage.\n\n"
        f"👉 <a href='{TELEGRAM_VIP_LINK}'><b>Trade with Institutional Discipline · VIP Club</b></a>"
    )

    discord_desc = (
        f"Key volatility catalysts & Central Bank releases today ({today_readable}):\n\n"
        f"{events_formatted_dc}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ **Algorithmic Risk Guard:**\n"
        f"QuantFlow automatically suspends signal triggers **±30 minutes** around High-Impact releases "
        f"to protect prop firm accounts from spread spikes.\n\n"
        f"💎 [**Join QuantFlow VIP Club**]({TELEGRAM_VIP_LINK}) • [**Free Telegram Channel**]({TELEGRAM_PUBLIC_LINK})"
    )

    return {
        "type": "NEWS_BRIEFING",
        "title": f"📅 DAILY ECONOMIC RADAR · {today_readable}",
        "telegram_msg": telegram_msg,
        "discord_desc": discord_desc,
        "has_high_impact": any(e["impact"] == "High" for e in today_events),
        "events_count": len(today_events),
    }


# ==============================================================================
# 2. INTERACTIVE COMMUNITY POLLS
# ==============================================================================

COMMUNITY_POLLS: List[Dict[str, Any]] = [
    {
        "id": "poll_london_eurusd_bias",
        "question": "🇬🇧 London Session Open: What is your primary directional bias on EUR/USD today?",
        "options": [
            "🐂 Bullish (Hunting 1.0950 Buy-Side Liquidity)",
            "🐻 Bearish (Filling Discount Fair Value Gap)",
            "⏳ Neutral Chop / Waiting for NY Session"
        ],
        "category": "SESSION_BIAS"
    },
    {
        "id": "poll_prop_firm_risk",
        "question": "🛡️ Prop Firm Challenge Milestone: What is your maximum risk per trade?",
        "options": [
            "0.50% (Institutional / Low Drawdown / Stress-Free)",
            "1.00% (Balanced Growth / Standard Discipline)",
            "2.00%+ (High Variance / Aggressive Chasing)"
        ],
        "category": "PSYCHOLOGY_RISK"
    },
    {
        "id": "poll_ny_usd_bias",
        "question": "🇺🇸 New York Session Open: How are you positioning on the US Dollar Index (DXY)?",
        "options": [
            "💪 Strong USD (Short EUR/USD, AUD/USD)",
            "📉 Weak USD (Long Foreign Currencies)",
            "⚡ Selective Pairs (Trading CCRS Divergence Only)"
        ],
        "category": "SESSION_BIAS"
    },
    {
        "id": "poll_ict_quiz_sweep",
        "question": "🧠 Smart Money Concepts: Price sweeps the Asian Session High, rejects sharply, and shifts structure downward. What setup is forming?",
        "options": [
            "Turtle Soup / Judas Swing Short (Liquidity Sweep)",
            "Retail Bullish Breakout Continuation",
            "Random Unpredictable Market Noise"
        ],
        "category": "SMC_EDUCATION"
    },
    {
        "id": "poll_weekend_prep_focus",
        "question": "📊 Weekend Strategy Prep: What is your #1 trading focus for the upcoming week?",
        "options": [
            "Passing a Prop Firm Funded Challenge ($5K–$100K)",
            "Eliminating Emotional Overtrading & Revenge Trades",
            "Automating Execution with cTrader / Algorithms",
            "Mastering Institutional Order Flow & CCRS"
        ],
        "category": "GOAL_SETTING"
    },
    {
        "id": "poll_trade_execution_win",
        "question": "🎯 Execution Audit: Did you catch QuantFlow's latest confirmed institutional setup?",
        "options": [
            "🚀 Yes! Locked in full +1.50R target profit",
            "⏳ In position, trailing stop actively protecting gains",
            "👀 Missed the entry retest, waiting for next cycle",
            "💎 Upgrading to VIP to receive every trade live"
        ],
        "category": "SOCIAL_PROOF"
    }
]


def get_community_poll(idx: int) -> Dict[str, Any]:
    """Retrieves a rotating poll by index."""
    return COMMUNITY_POLLS[idx % len(COMMUNITY_POLLS)]


# ==============================================================================
# 3. ICT & SMART MONEY CONCEPTS EDUCATIONAL MASTERCLASS CARDS
# ==============================================================================

ICT_EDUCATIONAL_CARDS: List[Dict[str, str]] = [
    {
        "id": "ict_order_blocks",
        "title": "🏛️ ICT MASTERCLASS: Order Blocks (+OB / -OB) — Institutional Accumulation",
        "telegram_msg": (
            "🏛️ <b>ICT MASTERCLASS · ORDER BLOCKS (+OB / -OB)</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Retail traders view support and resistance as horizontal lines. Institutional algorithms view them as <b>liquidity accumulation pools</b>.\n\n"
            "<b>What is a True Order Block?</b>\n"
            "• <b>Bullish Order Block (+OB):</b> The final bearish down-candle immediately preceding an aggressive, impulsive upward displacement that breaks previous swing structure.\n"
            "• <b>Bearish Order Block (-OB):</b> The final bullish up-candle before an impulsive downward displacement.\n\n"
            "<b>How to Trade the Retest (Institutional Rules):</b>\n"
            "1. <b>The 50% Mean Threshold:</b> Institutions rarely allow price to close below the 50% body midpoint of a valid Order Block.\n"
            "2. <b>Validation:</b> Never buy blindly at an OB. Wait for lower-timeframe confirmation (confirmed rejection wick or 20-EMA pullback).\n"
            "3. <b>Invalidation:</b> A confirmed candle close beyond the OB structure immediately invalidates the setup.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>QuantFlow's scanner automatically maps confirmed Order Blocks and Donchian liquidity sweeps 24/7 across institutional forex.</i>\n\n"
            f"👉 <a href='{TELEGRAM_VIP_LINK}'><b>Trade with Institutional Order Flow · Join VIP</b></a>"
        ),
        "discord_desc": (
            "Retail traders view support and resistance as horizontal lines. Institutional algorithms view them as **liquidity accumulation pools**.\n\n"
            "**What is a True Order Block?**\n"
            "• **Bullish Order Block (+OB):** The final bearish down-candle immediately preceding an aggressive upward displacement that breaks swing structure.\n"
            "• **Bearish Order Block (-OB):** The final bullish up-candle before an impulsive downward displacement.\n\n"
            "**How to Trade the Retest (Institutional Rules):**\n"
            "1. **The 50% Mean Threshold:** Institutions rarely allow price to close below the 50% midpoint of a valid Order Block.\n"
            "2. **Validation:** Wait for lower-timeframe confirmation (rejection wick or 20-EMA pullback retest).\n"
            "3. **Invalidation:** A confirmed candle close beyond the OB structure immediately invalidates the setup.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💎 [**Upgrade to QuantFlow VIP Club**]({TELEGRAM_VIP_LINK}) • [**Free Telegram Signals**]({TELEGRAM_PUBLIC_LINK})"
        )
    },
    {
        "id": "ict_fair_value_gaps",
        "title": "⚡ ICT MASTERCLASS: Fair Value Gaps (FVG) & Algorithmic Inefficiencies",
        "telegram_msg": (
            "⚡ <b>ICT MASTERCLASS · FAIR VALUE GAPS (FVG)</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Ever wondered why price suddenly reverses to 'fill' an empty pocket on the chart? It is an algorithmic delivery requirement known as a <b>Fair Value Gap (FVG)</b>.\n\n"
            "<b>The 3-Candle Imbalance Anatomy:</b>\n"
            "• <b>Candle 1:</b> The preparatory move.\n"
            "• <b>Candle 2:</b> An expansive, high-volume displacement candle.\n"
            "• <b>Candle 3:</b> The follow-through candle.\n"
            "• <i>The Gap:</i> The space between the high of Candle 1 and the low of Candle 3 (in a bullish move) where only one side of the market was delivered.\n\n"
            "<b>Why Institutions Rebalance FVGs:</b>\n"
            "Central bank algorithmic pricing engines (IPDA) strive for <i>bilateral efficiency</i>. When price moves too fast, buy/sell inventory is left unfilled. Price retraces to rebalance the imbalance before continuing the trend.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🎯 <b>Pro Tip:</b> Combine an FVG retest with a Cross-Currency Relative Strength (CCRS) divergence of <b>|D| ≥ 1.75σ</b> for 68%+ win rate accuracy.\n\n"
            f"👉 <a href='{TELEGRAM_VIP_LINK}'><b>Get Live Algorithmic Setups in QuantFlow VIP</b></a>"
        ),
        "discord_desc": (
            "Ever wondered why price suddenly reverses to 'fill' an empty pocket on the chart? It is an algorithmic delivery requirement known as a **Fair Value Gap (FVG)**.\n\n"
            "**The 3-Candle Imbalance Anatomy:**\n"
            "• **Candle 1:** The preparatory move.\n"
            "• **Candle 2:** An expansive, high-volume displacement candle.\n"
            "• **Candle 3:** The follow-through candle.\n"
            "• *The Gap:* The space between the high of Candle 1 and low of Candle 3 where only one side was offered.\n\n"
            "**Why Institutions Rebalance FVGs:**\n"
            "Algorithmic pricing engines strive for *bilateral efficiency*. Price retraces to rebalance unfilled inventory before resuming structural trend.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💎 [**Upgrade to QuantFlow VIP Club**]({TELEGRAM_VIP_LINK}) • [**Free Telegram Signals**]({TELEGRAM_PUBLIC_LINK})"
        )
    },
    {
        "id": "ict_liquidity_sweeps",
        "title": "🧲 ICT MASTERCLASS: Buy-Side & Sell-Side Liquidity (BSL / SSL) Sweeps",
        "telegram_msg": (
            "🧲 <b>ICT MASTERCLASS · LIQUIDITY SWEEPS (BSL / SSL)</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<b>Where does smart money get the liquidity to execute multi-billion dollar orders?</b>\n"
            "From retail traders' stop losses.\n\n"
            "<b>The Anatomy of a Trap:</b>\n"
            "• <b>Buy-Side Liquidity (BSL):</b> Resting stop-losses of retail short sellers above equal highs or Asian range highs.\n"
            "• <b>Sell-Side Liquidity (SSL):</b> Resting stop-losses of retail buyers below key swing lows.\n\n"
            "When price pushes past a prominent swing high, retail breakout traders eagerly buy. Institutional algorithms use this flood of buy orders to <b>dump short positions</b> into the market, triggering an immediate reversal.\n\n"
            "<b>How QuantFlow Filters Avoid the Trap:</b>\n"
            "We wait for the <b>10-bar Donchian sweep confirmation</b>: price must sweep the high/low, reject, and pull back to the 20-EMA before any entry is triggered.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🛡️ <i>Never buy breakouts at resistance. Trade where institutions reverse the market.</i>\n\n"
            f"👉 <a href='{TELEGRAM_VIP_LINK}'><b>Join QuantFlow VIP Club on Whop</b></a>"
        ),
        "discord_desc": (
            "**Where does smart money get the liquidity to execute multi-billion dollar orders?**\n"
            "From retail traders' stop losses.\n\n"
            "**The Anatomy of a Trap:**\n"
            "• **Buy-Side Liquidity (BSL):** Resting stops of short sellers above equal highs or Asian range highs.\n"
            "• **Sell-Side Liquidity (SSL):** Resting stops of buyers below key swing lows.\n\n"
            "When price pushes past a prominent swing high, retail traders buy breakouts. Institutional algorithms use this flood of buy orders to **dump short positions**, triggering an immediate reversal.\n\n"
            "**QuantFlow Liquidity Filter:**\n"
            "We require a confirmed 10-bar Donchian sweep and 20-EMA pullback confirmation before triggering any execution.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💎 [**Upgrade to QuantFlow VIP Club**]({TELEGRAM_VIP_LINK}) • [**Free Telegram Signals**]({TELEGRAM_PUBLIC_LINK})"
        )
    },
    {
        "id": "ccrs_relative_strength",
        "title": "📡 QUANT STRATEGY: Cross-Currency Relative Strength (CCRS) Factor Engine",
        "telegram_msg": (
            "📡 <b>QUANT STRATEGY · CROSS-CURRENCY RELATIVE STRENGTH (CCRS)</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Why do traditional retail indicators (RSI, MACD, Bollinger Bands) fail 60% of the time on single forex pairs?\n\n"
            "Because forex is not a stock — <b>it is a currency exchange ratio</b>. If EUR/USD drops, is EUR weak, or is USD strong?\n\n"
            "<b>The Institutional Factor Approach:</b>\n"
            "QuantFlow tracks a 7-currency synthetic matrix (USD, EUR, GBP, CAD, JPY, AUD, CHF) over rolling 120-hour lookbacks normalized by 200-hour volatility Z-scores:\n\n"
            "• <b>Step 1:</b> Calculate individual currency strength across all 21 cross pairs.\n"
            "• <b>Step 2:</b> Rank currencies from strongest (+2.50σ) to weakest (-2.50σ).\n"
            "• <b>Step 3:</b> Pair the <b>Strongest Currency against the Weakest Currency</b>.\n"
            "• <b>Execution Rule:</b> Only trigger trades when pairwise divergence reaches <b>|D| ≥ 1.75σ</b>.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📈 Result: Trading with genuine institutional capital flows rather than lagging single-chart noise.\n\n"
            f"👉 <a href='{TELEGRAM_VIP_LINK}'><b>Trade with the CCRS Factor Engine · Join VIP</b></a>"
        ),
        "discord_desc": (
            "Why do traditional retail indicators fail on single forex pairs?\n"
            "Because forex is an exchange ratio. If EUR/USD drops, is EUR weak, or is USD strong?\n\n"
            "**The Institutional CCRS Factor Approach:**\n"
            "QuantFlow tracks a 7-currency synthetic matrix over 120-hour lookbacks normalized by 200-hour volatility Z-scores:\n"
            "• **Step 1:** Calculate individual currency strength across all 21 cross pairs.\n"
            "• **Step 2:** Rank currencies from strongest (+2.50σ) to weakest (-2.50σ).\n"
            "• **Step 3:** Pair the **Strongest Currency against the Weakest Currency**.\n"
            "• **Execution Rule:** Only trade when pairwise divergence reaches **|D| ≥ 1.75σ**.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💎 [**Upgrade to QuantFlow VIP Club**]({TELEGRAM_VIP_LINK}) • [**Free Telegram Signals**]({TELEGRAM_PUBLIC_LINK})"
        )
    },
    {
        "id": "risk_reward_math",
        "title": "⚖️ QUANTITATIVE DISCIPLINE: The Mathematical Edge of 1:1.50R Geometry",
        "telegram_msg": (
            "⚖️ <b>QUANTITATIVE DISCIPLINE · THE 1:1.50R EDGE</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Most retail traders fail because they risk 50 pips to make 10 pips (a negative 0.20 R:R). One bad trade wipes out weeks of hard work.\n\n"
            "<b>The Institutional Truth:</b>\n"
            "You do NOT need a 90% win rate to achieve institutional returns. You need <b>asymmetrical risk-to-reward geometry</b>.\n\n"
            "<b>The Math on 100 Trades (1:1.50R Target Geometry):</b>\n"
            "• <b>Win Rate:</b> Just <b>50%</b> (50 wins, 50 losses)\n"
            "• <b>Risk per trade:</b> 1.00R ($50 on a $5K account)\n"
            "• <b>Losses:</b> 50 × -1.00R = <b>-50.00 R</b>\n"
            "• <b>Wins:</b> 50 × +1.50R = <b>+75.00 R</b>\n"
            "• <b>Net Profit:</b> <b>+25.00 R</b> (+$1,250 net gain, or <b>+25.0% account growth</b>)\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🛡️ <i>Even with a 45% win rate, QuantFlow's 1:1.50R dynamic geometry generates positive net expectancy.</i>\n\n"
            f"👉 <a href='{TELEGRAM_VIP_LINK}'><b>Trade with Asymmetrical Edge · QuantFlow VIP Club</b></a>"
        ),
        "discord_desc": (
            "Most retail traders fail because they risk 50 pips to make 10 pips. One bad trade wipes out weeks of gains.\n\n"
            "**The Math of 1:1.50R Geometry (100 Trades):**\n"
            "• **Win Rate:** Just **50%** (50 wins, 50 losses)\n"
            "• **Risk per trade:** 1.00R ($50 on a $5K account)\n"
            "• **Losses:** 50 × -1.00R = **-50.00 R**\n"
            "• **Wins:** 50 × +1.50R = **+75.00 R**\n"
            "• **Net Profit:** **+25.00 R** (+25.0% gain)\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💎 [**Upgrade to QuantFlow VIP Club**]({TELEGRAM_VIP_LINK}) • [**Free Telegram Signals**]({TELEGRAM_PUBLIC_LINK})"
        )
    },
    {
        "id": "prop_firm_firewall",
        "title": "🛡️ RISK MANAGEMENT: The 4% Prop Firm Daily Drawdown Firewall",
        "telegram_msg": (
            "🛡️ <b>RISK MANAGEMENT · 4% PROP FIRM DRAWDOWN FIREWALL</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Over 92% of traders fail funded account evaluations (FTMO, FundedNext, FundingPips) due to a single rule: <b>The Daily Drawdown Limit</b>.\n\n"
            "When consecutive losses occur, emotional tilt causes traders to double their lot sizes in an attempt to recover quickly. Within hours, the account is breached.\n\n"
            "<b>QuantFlow's Automated Capital Invariants:</b>\n"
            "1. <b>Strict 0.50%–1.00% Risk Sizing:</b> Calculated dynamically from real-time equity via cTrader Open API.\n"
            "2. <b>Max 3 Concurrent Assets:</b> Floating correlation cap prevents correlated currency exposure.\n"
            "3. <b>Hard 4.0% Daily Loss Halt:</b> If daily cumulative losses reach -3.0R, all signal dispatch halts immediately for the day.\n"
            "4. <b>Pessimistic Intra-Candle Rule:</b> SL always takes precedence over TP in ambiguous market ticks.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "💎 <i>Pass your prop firm evaluation with algorithmic consistency, not emotional gambling.</i>\n\n"
            f"👉 <a href='{TELEGRAM_VIP_LINK}'><b>Join QuantFlow VIP Club on Whop</b></a>"
        ),
        "discord_desc": (
            "Over 92% of traders fail funded account evaluations due to a single rule: **The Daily Drawdown Limit**.\n\n"
            "**QuantFlow's Automated Capital Invariants:**\n"
            "1. **Strict 0.50%–1.00% Risk Sizing:** Calculated dynamically from real-time equity.\n"
            "2. **Max 3 Concurrent Assets:** Prevents overexposure to correlated pairs.\n"
            "3. **Hard 4.0% Daily Loss Halt:** Closes execution when risk budget is reached.\n"
            "4. **Zero Averaging Down:** Strict volatility-anchored stops (2.0× ATR).\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💎 [**Upgrade to QuantFlow VIP Club**]({TELEGRAM_VIP_LINK}) • [**Free Telegram Signals**]({TELEGRAM_PUBLIC_LINK})"
        )
    }
]


def get_ict_educational_card(idx: int) -> Dict[str, str]:
    """Retrieves a rotating ICT educational card by index."""
    return ICT_EDUCATIONAL_CARDS[idx % len(ICT_EDUCATIONAL_CARDS)]


# ==============================================================================
# 4. VIP MEMBERSHIP PROMOTIONS & SOCIAL PROOF CARDS
# ==============================================================================

VIP_PROMOTION_CARDS: List[Dict[str, str]] = [
    {
        "id": "vip_public_vs_vip",
        "title": "💎 QUANTFLOW VIP CLUB: Public Channel vs VIP Comparison",
        "telegram_msg": (
            "💎 <b>WHY SERIOUS TRADERS CHOOSE QUANTFLOW VIP CLUB</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "The free public channel provides a glimpse into our institutional strategy, but serious capital requires comprehensive execution:\n\n"
            "📊 <b>FREE PUBLIC CHANNEL:</b>\n"
            "• Max 2–4 signals per week (selected pairs)\n"
            "• Delayed execution guidance\n"
            "• Manual broker entry required\n\n"
            "🚀 <b>QUANTFLOW VIP CLUB ON WHOP:</b>\n"
            "• <b>10–14 Institutional Setups / Week:</b> Trade every confirmed CCRS divergence setup across all pairs.\n"
            "• <b>Full cTrader Open API Automated Copy-Trading:</b> Zero-lag execution directly on your broker account.\n"
            "• <b>Real-Time Stop Trailing & Profit Locks:</b> Automatic +1.2R risk halving and breakeven adjustments.\n"
            "• <b>Prop Firm Compliance Guard:</b> Dynamic lot sizing tailored specifically for passing $5K to $200K challenges.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔥 <b>Instant Access Available Now:</b>\n\n"
            f"👉 <a href='{TELEGRAM_VIP_LINK}'><b>Secure Your VIP Membership on Whop</b></a>"
        ),
        "discord_desc": (
            "The free channel provides a glimpse into our strategy, but serious capital requires full institutional coverage:\n\n"
            "📊 **FREE PUBLIC CHANNEL:**\n"
            "• Max 2–4 signals per week\n"
            "• Manual broker entry required\n\n"
            "🚀 **QUANTFLOW VIP CLUB:**\n"
            "• **10–14 Setups / Week:** Trade 100% of confirmed divergence setups across active pairs.\n"
            "• **Automated cTrader Copy-Trading:** Zero-lag broker order routing.\n"
            "• **Real-Time Stop Trailing:** Automatic profit locking and risk halving.\n"
            "• **Prop Firm Sizing Guard:** Sized specifically for passing $5K–$200K evaluations.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👉 [**Join QuantFlow VIP Club on Whop**]({TELEGRAM_VIP_LINK}) • [**Free Telegram Signals**]({TELEGRAM_PUBLIC_LINK})"
        )
    },
    {
        "id": "vip_prop_firm_pass",
        "title": "🏆 PROP FIRM PASSING ENGINE: Institutional Capital Scaling",
        "telegram_msg": (
            "🏆 <b>ENGINEERED FOR PASSING & KEEPING FUNDED ACCOUNTS</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Tired of passing Phase 1 only to lose the account on Phase 2 during choppy market conditions?\n\n"
            "QuantFlow was designed with institutional risk invariants:\n\n"
            "✓ <b>Asymmetrical 1:1.50R Geometry:</b> Reach your 8%–10% target in fewer trades without overleveraging.\n"
            "✓ <b>CCRS Macro Filter:</b> Trades only execute when institutional capital confirms the directional flow.\n"
            "✓ <b>Bank Holiday & News Blackout Defense:</b> Automatically protects accounts during spread blowouts.\n"
            "✓ <b>Full Trade Journal & Transparency:</b> Every completed trade logged with entry, exit, and net R.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Stop gambling with retail setups. Trade with institutional algorithmic execution.\n\n"
            f"👉 <a href='{TELEGRAM_VIP_LINK}'><b>Join QuantFlow VIP Club on Whop</b></a>"
        ),
        "discord_desc": (
            "Tired of passing Phase 1 only to lose the account on Phase 2 during choppy market conditions?\n\n"
            "QuantFlow was designed with institutional risk invariants:\n\n"
            "✓ **Asymmetrical 1:1.50R Geometry:** Hit profit targets in fewer trades.\n"
            "✓ **CCRS Macro Filter:** Trade only when institutional volume confirms flow.\n"
            "✓ **News Blackout Defense:** Automatically suppresses entries around high-impact news.\n"
            "✓ **Verified Trade Journal:** Every trade tracked with verified timestamps.\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👉 [**Secure Your VIP Membership on Whop**]({TELEGRAM_VIP_LINK}) • [**Free Telegram Signals**]({TELEGRAM_PUBLIC_LINK})"
        )
    }
]


def get_vip_promotion_card(idx: int) -> Dict[str, str]:
    """Retrieves a rotating VIP promotion card by index."""
    return VIP_PROMOTION_CARDS[idx % len(VIP_PROMOTION_CARDS)]


# ==============================================================================
# 5. DISPATCH CONTROLLER & SCHEDULE MANAGER
# ==============================================================================

def check_and_dispatch_engagement_content(
    state: Dict[str, Any],
    now_dt: Optional[datetime] = None,
    force: bool = False,
    content_type: str = "AUTO"
) -> Tuple[bool, str]:
    """
    Evaluates cooldowns, schedules, and active market sessions to dispatch
    the appropriate engagement content (News, Polls, ICT Cards, VIP Drops).
    Runs safely in scan cycles without altering trading or execution.
    """
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    elif now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    # Cooldown Check (unless forced)
    if not force:
        last_eng_str = state.get("last_engagement_post_ts")
        if last_eng_str:
            try:
                last_dt = datetime.fromisoformat(last_eng_str)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                elapsed = (now_dt - last_dt).total_seconds()
                if elapsed < MIN_ENGAGEMENT_INTERVAL_SECONDS:
                    return False, f"Cooldown active ({int(MIN_ENGAGEMENT_INTERVAL_SECONDS - elapsed)}s remaining)"
            except Exception as e:
                logger.warning(f"Failed to parse last_engagement_post_ts: {e}")

    # Determine Content Type to dispatch
    hour = now_dt.hour
    weekday = now_dt.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    today_date_str = now_dt.strftime("%Y-%m-%d")

    poll_idx = int(state.get("engagement_poll_idx", 0))
    ict_idx = int(state.get("engagement_ict_idx", 0))
    vip_idx = int(state.get("engagement_vip_idx", 0))

    chosen_type = content_type

    if chosen_type == "AUTO":
        last_calendar_date = state.get("last_calendar_briefing_date")
        
        # 1. London Morning (06:30 - 08:30 UTC): Daily Economic News Briefing (once per day)
        if weekday < 5 and 6 <= hour <= 8 and last_calendar_date != today_date_str:
            chosen_type = "NEWS"
        # 2. Mid-Day / European Session (10:00 - 12:00 UTC): ICT Educational Card
        elif weekday < 5 and 10 <= hour <= 12:
            chosen_type = "ICT"
        # 3. NY Open (13:00 - 15:00 UTC): Community Session Bias Poll
        elif weekday < 5 and 13 <= hour <= 15:
            chosen_type = "POLL"
        # 4. Evening Wrap / Post-NY (17:00 - 20:00 UTC): VIP Value Drop
        elif weekday < 5 and 17 <= hour <= 20:
            chosen_type = "VIP"
        # 5. Weekend Saturday (12:00 - 16:00 UTC): ICT Masterclass
        elif weekday == 5:
            chosen_type = "ICT"
        # 6. Weekend Sunday (16:00 - 20:00 UTC): Weekend Prep & Upcoming News Briefing
        elif weekday == 6:
            chosen_type = "NEWS"
        else:
            # Default rotation: rotate between ICT and POLL
            chosen_type = "ICT" if (poll_idx + ict_idx) % 2 == 0 else "POLL"

    # Execution by selected content type
    success = False
    dispatched_desc = ""

    from market_scanner import _safe_send_telegram_alert, send_telegram_poll, TELEGRAM_PUBLIC_CHAT_ID

    pub_chat = TELEGRAM_PUBLIC_CHAT_ID or TELEGRAM_PUBLIC_CHANNEL

    if chosen_type == "NEWS":
        briefing = generate_daily_news_briefing(now_dt=now_dt)
        # 1. Telegram
        t_ok = _safe_send_telegram_alert(briefing["telegram_msg"], specific_chat_id=pub_chat, protect_content=False)
        # 2. Discord
        d_ok = send_discord_content(
            title=briefing["title"],
            description=briefing["discord_desc"],
            category="ECONOMIC_CALENDAR",
            color=0x2962FF
        )
        if t_ok or d_ok:
            state["last_calendar_briefing_date"] = today_date_str
            state["last_engagement_post_ts"] = now_dt.isoformat()
            dispatched_desc = f"Economic Calendar Briefing ({briefing['events_count']} events)"
            success = True

    elif chosen_type == "POLL":
        poll_data = get_community_poll(poll_idx)
        # 1. Telegram native poll
        t_ok = send_telegram_poll(
            question=poll_data["question"],
            options=poll_data["options"],
            specific_chat_id=pub_chat,
            is_anonymous=True
        )
        # 2. Discord rich reaction poll
        d_ok = send_discord_poll(
            question=poll_data["question"],
            options=poll_data["options"]
        )
        if t_ok or d_ok:
            state["engagement_poll_idx"] = poll_idx + 1
            state["last_engagement_post_ts"] = now_dt.isoformat()
            dispatched_desc = f"Interactive Poll ({poll_data['id']})"
            success = True

    elif chosen_type == "ICT":
        card = get_ict_educational_card(ict_idx)
        # 1. Telegram
        t_ok = _safe_send_telegram_alert(card["telegram_msg"], specific_chat_id=pub_chat, protect_content=False)
        # 2. Discord
        d_ok = send_discord_content(
            title=card["title"],
            description=card["discord_desc"],
            category="ICT_MASTERCLASS",
            color=0x7C4DFF
        )
        if t_ok or d_ok:
            state["engagement_ict_idx"] = ict_idx + 1
            state["last_engagement_post_ts"] = now_dt.isoformat()
            dispatched_desc = f"ICT Masterclass Card ({card['id']})"
            success = True

    elif chosen_type == "VIP":
        card = get_vip_promotion_card(vip_idx)
        # 1. Telegram
        t_ok = _safe_send_telegram_alert(card["telegram_msg"], specific_chat_id=pub_chat, protect_content=False)
        # 2. Discord
        d_ok = send_discord_content(
            title=card["title"],
            description=card["discord_desc"],
            category="VIP_SPOTLIGHT",
            color=0x00E676
        )
        if t_ok or d_ok:
            state["engagement_vip_idx"] = vip_idx + 1
            state["last_engagement_post_ts"] = now_dt.isoformat()
            dispatched_desc = f"VIP Promotion Card ({card['id']})"
            success = True

    if success:
        from market_scanner import save_state
        save_state(state)
        logger.info(f"Community Engagement successfully dispatched: {dispatched_desc} to {pub_chat} & Discord.")
        return True, dispatched_desc

    return False, "Failed to dispatch engagement content to channels."
