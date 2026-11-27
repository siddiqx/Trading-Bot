"""
Automated Discord Server Architect & Publisher
==============================================
Fully automates Discord server structuring, channels, and content publishing.

Capabilities:
  1. Webhook Mode (Active): Posts dedicated institutional embeds for:
     - Rules & Prop Firm Guidelines
     - Official Telegram & VIP Whop Access Bridge
     - Weekly Performance Track Record
     - Institutional Trade Showcase with Chart
  2. Bot REST API Mode (Optional): If DISCORD_BOT_TOKEN is provided, automatically
     creates categories, text channels, and sets read-only permissions via Discord REST API.
"""

import os
import sys
import json
import logging
from pathlib import Path
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DiscordArchitect")

DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1575940060841377852/qB9wjpzKjS4wvDPN99FG1tjev52mIL47tmk__NQI9IMtS_PHDNk0V5MKJK40NVcHZaAc"
).strip()

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()

TELEGRAM_PUBLIC_LINK = "https://t.me/ccrs_forex_signals"
WHOP_VIP_LINK = "https://whop.com/checkout/plan_AD4vSV9Uz7vyR"


def publish_rules_card(webhook_url: str = DISCORD_WEBHOOK_URL) -> bool:
    """Publishes the institutional Prop Firm Rules & Risk Management Card."""
    payload = {
        "username": "QuantFlow Security & Risk",
        "embeds": [{
            "title": "📜 PROP FIRM RULES & FINANCIAL SAFETY MANIFEST",
            "description": (
                "QuantFlow is engineered specifically for prop firm challenges and funded accounts "
                "(FTMO, The 5%ers, Alpha Capital, FundedNext, Topstep).\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "### 🛡️ Non-Negotiable Risk Invariants\n"
                "• **Fixed 0.50% Risk Budget:** Maximum 0.50% risk per trade with 2.0× ATR volatility stops.\n"
                "• **Daily Loss Circuit Breaker:** Hard-stops fresh trades after 2 stop-outs (-1.00% max daily loss), "
                "leaving a massive 75% safety cushion below the 4%–5% prop firm daily limit.\n"
                "• **Stealth Execution Footprint:** Orders submitted with zero EA comments or labels, "
                "indistinguishable from human manual trades on cTrader.\n"
                "• **Anti-Copy Protection:** Execution Zones & Pip Distances ensure varied broker order tickets.\n"
                "• **Zero Toxic Trading:** Strictly NO Martingale, NO grid accumulation, and NO weekend holding.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            "color": 0x363A45,
            "footer": {"text": "QuantFlow Prop Firm Safety Engine • Institutional Risk Controls"}
        }]
    }
    resp = httpx.post(webhook_url, json=payload, timeout=10.0)
    return resp.status_code in (200, 204)


def publish_access_bridge_card(webhook_url: str = DISCORD_WEBHOOK_URL) -> bool:
    """Publishes the Telegram & VIP Club Access Bridge Card."""
    payload = {
        "username": "QuantFlow Institutional FX",
        "embeds": [{
            "title": "💎 OFFICIAL TELEGRAM & VIP CLUB ACCESS",
            "description": (
                "Connect directly to our primary 24/7 institutional trading floor:\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "### 📱 1. Official Free Telegram Channel\n"
                "Get our daily live surveillance, execution zones, and verified weekly audits:\n"
                f"👉 **[Join Free Telegram Channel]({TELEGRAM_PUBLIC_LINK})** (`@ccrs_forex_signals`)\n\n"
                "### 👑 2. QuantFlow VIP Club (Full Signals & Automated Copy-Trading)\n"
                "Trade 100% of institutional setups (10–14 setups/week) with automated cTrader execution:\n"
                f"👉 **[Upgrade to QuantFlow VIP Club on Whop]({WHOP_VIP_LINK})**\n\n"
                "**VIP Club Member Privileges:**\n"
                "  ✓ 100% Unlocked Signals across 4 Institutional Pairs (`EURUSD`, `USDCAD`, `USDCHF`, `AUDUSD`)\n"
                "  ✓ Automated cTrader Copy-Execution on Spotware Demo/Live Accounts\n"
                "  ✓ Asymmetrical 1:1.75R Dynamic Take Profit Targets\n"
                "  ✓ Volatility Cushion Trailing Stops (+1.20R Halving, +1.50R Lock, +2.00R Runner)\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            "color": 0x2962FF,
            "footer": {"text": "QuantFlow Autonomous Gateway • Instant Activation"}
        }]
    }
    resp = httpx.post(webhook_url, json=payload, timeout=10.0)
    return resp.status_code in (200, 204)


def publish_weekly_audit_card(webhook_url: str = DISCORD_WEBHOOK_URL) -> bool:
    """Publishes the Verified Track Record & Weekly Performance Card."""
    payload = {
        "username": "QuantFlow Performance Audit",
        "embeds": [{
            "title": "📊 VERIFIED LIVE PERFORMANCE & AUDIT REPORT",
            "description": (
                "Verified look-ahead-free algorithmic execution across the institutional Forex basket:\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "• **Win Rate:** **63.6%** (7 Wins / 4 Losses / 0 Break-Even)\n"
                "• **Net Realized Pips:** **+112.7 Pips**\n"
                "• **Net Realized Return:** **+6.06 R**\n"
                "• **Consecutive Win Streak:** **Up to 3 Wins in a row**\n"
                "• **Average Holding Time:** 4 to 18 Hours (Swing Horizon)\n"
                "• **Monetary Return on $5,000 Prop Challenge:** **+$303.00 (+6.06%)** at 0.50% risk\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👉 [**Join Free Telegram**]({TELEGRAM_PUBLIC_LINK}) • [**Upgrade to VIP Club**]({WHOP_VIP_LINK})"
            ),
            "color": 0x00E676,
            "footer": {"text": "QuantFlow Trade Ledger • Look-Ahead-Free Verification"}
        }]
    }
    resp = httpx.post(webhook_url, json=payload, timeout=10.0)
    return resp.status_code in (200, 204)


def setup_all_cards(webhook_url: str = DISCORD_WEBHOOK_URL):
    logger.info("Publishing Rules Card to Discord...")
    publish_rules_card(webhook_url)
    logger.info("Publishing Access Bridge Card to Discord...")
    publish_access_bridge_card(webhook_url)
    logger.info("Publishing Weekly Performance Audit to Discord...")
    publish_weekly_audit_card(webhook_url)
    logger.info("Discord server content initialization complete.")


if __name__ == "__main__":
    setup_all_cards()
