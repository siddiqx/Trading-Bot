"""
AI Content & Educational Post Generator (Powered by OpenRouter)
==============================================================
Generates authentic, high-authority Forex and Prop Firm content for Twitter/X
and Reddit when there are no active trades open in the systematic engine.

Topics covered:
  • Smart Money Concepts (ICT): Liquidity Sweeps, BSL/SSL, MSS, Fair Value Gaps
  • Prop Firm Mathematical Edge: 0.5% risk rule, asymmetric R:R, drawdown survival
  • Macro Currency Relative Strength (CCRS): 7-currency basket flow vs single-pair traps
  • Institutional Execution: Session Killzones (London/NY), avoiding retail stop hunts
"""

import os
import sys
import json
import random
import logging
import urllib.request
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("AIContentGenerator")
logger.setLevel(logging.INFO)

OPENROUTER_API_KEY = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_CHANNEL_URL = "https://t.me/ccrs_forex_signals"

# Priority list of models (fast free models first, then standard)
MODELS_TO_TRY = [
    "nvidia/nemotron-3.5-lightning:free",
    "liquid/lfm-3-1.7b:free",
    "baidu/ernie-5.5-flash-preview:free",
    "meta-llama/llama-3.3-70b-instruct",
    "deepseek/deepseek-chat"
]

TOPICS = [
    {
        "category": "ICT / Smart Money Concepts",
        "theme": "Why Retail Support/Resistance Gets Swept Before Real Moves",
        "key_concept": "Buy-Side Liquidity (BSL) & Sell-Side Liquidity (SSL) stop-runs by institutional algorithms",
        "pair": "EURUSD"
    },
    {
        "category": "Prop Firm Mathematics",
        "theme": "The Real Math of Passing Prop Challenges: Why 0.50% Risk Beats 2% Risk",
        "key_concept": "Geometric drawdown protection and asymmetric 1:1.50R minimum expectancy",
        "pair": "USDCAD"
    },
    {
        "category": "Macro Currency Relative Strength",
        "theme": "Why Single-Pair Technical Indicators Lie: Cross-Currency Relative Strength (CCRS)",
        "key_concept": "Measuring rolling 200-hour Z-score divergence across 7 major currencies to identify true institutional capital flow",
        "pair": "USDCHF"
    },
    {
        "category": "Session Killzones",
        "theme": "How the London Open Judas Swing Engineers Retail Liquidity",
        "key_concept": "False breakout past Asian session range to trigger retail breakout stops before real institutional trend displacement",
        "pair": "AUDUSD"
    },
    {
        "category": "Order Block Mechanics",
        "theme": "The Anatomy of High-Probability Order Blocks (+OB/-OB)",
        "key_concept": "Identifying genuine institutional order blocks with confirmed 15M displacement and Fair Value Gaps (FVG) vs retail fakeouts",
        "pair": "EURUSD"
    }
]


def query_openrouter(messages: List[Dict[str, str]], max_tokens: int = 800) -> Optional[str]:
    """Queries OpenRouter with automatic model fallback."""
    if not OPENROUTER_API_KEY:
        return None
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return None

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/siddiqx/Trading-Bot",
        "X-Title": "QuantFlow Contents Bot"
    }

    for model in MODELS_TO_TRY:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7
        }
        try:
            req = urllib.request.Request(
                OPENROUTER_API_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices:
                    raw_content = choices[0].get("message", {}).get("content")
                    if raw_content and isinstance(raw_content, str):
                        content = raw_content.strip()
                        if content:
                            return content
        except Exception as e:
            logger.warning(f"OpenRouter query error with {model}: {e}")
            continue

    return None


def generate_ai_twitter_educational_thread(topic_idx: Optional[int] = None) -> Dict[str, Any]:
    """
    Generates a high-engagement 3-tweet educational FinTwit thread using AI.
    Falls back to institutional knowledge base if offline.
    """
    topic_data = TOPICS[topic_idx % len(TOPICS)] if topic_idx is not None else random.choice(TOPICS)
    pair = topic_data["pair"]

    system_prompt = (
        "You are an experienced, full-time currency trader who shares real market insights with peers. "
        "Write a punchy, highly engaging 3-tweet educational thread for Twitter/FinTwit. "
        "Strict rules:\n"
        "1. Write conversationally like a real human trader talking to other traders. Zero robot-speak, zero academic math jargon (no sigma, z-score, regression, or algorithms).\n"
        "2. Tweet 1: Hook the reader with a common trap or relatable observation about ${pair} liquidity. Keep under 240 chars.\n"
        "3. Tweet 2: Simple 3-step breakdown of how the move actually plays out (liquidity sweep, 15M structure shift, 20-EMA tap). Keep under 260 chars.\n"
        "4. Tweet 3: Risk rule (0.50% risk, 1:1.50R target), an engaging question to prompt replies, and clean tags with link. Keep under 270 chars.\n"
        "Format output strictly as JSON with keys 'tweet_1', 'tweet_2', 'tweet_3'."
    )
    user_prompt = f"Topic: {topic_data['theme']}\nCore concept: {topic_data['key_concept']}\nAsset focus: ${pair}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    ai_output = query_openrouter(messages, max_tokens=600)
    if ai_output:
        try:
            clean_json = ai_output
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()
            parsed = json.loads(clean_json)
            if "tweet_1" in parsed and "tweet_2" in parsed and "tweet_3" in parsed:
                return {
                    "tweets": [parsed["tweet_1"], parsed["tweet_2"], parsed["tweet_3"]],
                    "topic": topic_data["theme"],
                    "pair": pair
                }
        except Exception:
            pass

    # Built-in Institutional Knowledge Base Fallback
    t1 = (
        f"🧵 1/3 An uncomfortable truth about trading ${pair}:\n\n"
        f"Most traders treat support and resistance as hard walls. In reality, they are giant liquidity pools where resting retail stop-losses sit.\n\n"
        f"When you buy an obvious support bounce, your stop is often the exact fuel institutions need to fill their positions."
    )
    t2 = (
        f"2/3 How the setup actually unfolds:\n\n"
        f"1. Consolidation builds stop orders above and below session levels.\n"
        f"2. A quick spike sweeps through the high/low, trapping breakout traders.\n"
        f"3. Structure shifts cleanly on the 15M chart, retesting the 20-EMA for entry."
    )
    t3 = (
        f"3/3 How we trade it:\n\n"
        f"• Wait for the trap to spring first — never chase the initial breakout.\n"
        f"• Keep risk fixed at 0.50% per trade with a 1:1.50R minimum target.\n\n"
        f"Have you ever been stopped out right before the market ran in your direction? Let me know below 👇\n\n"
        f"Free daily trade surveillance & insights: {DEFAULT_CHANNEL_URL}\n"
        f"#{pair} #Forex #Trading #PriceAction #PropFirm"
    )
    return {
        "tweets": [t1, t2, t3],
        "topic": topic_data["theme"],
        "pair": pair
    }


def generate_ai_reddit_educational_post(topic_idx: Optional[int] = None, target_subreddit: str = "r/Forex") -> Dict[str, str]:
    """
    Generates an in-depth, high-effort Reddit educational breakdown for r/Forex or r/PropFirm.
    """
    topic_data = TOPICS[topic_idx % len(TOPICS)] if topic_idx is not None else random.choice(TOPICS)
    pair = topic_data["pair"]

    system_prompt = (
        "You are an experienced, funded prop firm currency trader writing a peer-to-peer educational post for r/Forex or r/PropFirm. "
        "Strict rules:\n"
        "1. Speak conversationally and authentically, like a seasoned trader talking to fellow traders. Zero robotic jargon, zero academic math equations, zero sales pitches.\n"
        "2. Structure cleanly: Relatable Introduction, The Retail Trap vs Market Reality, Step-by-Step Price Action Guide (Liquidity Sweeps & 20-EMA Retests), Prop Risk Rules (0.50% risk per trade, 1:1.50R target), and an engaging open-ended question at the end to spark community discussion.\n"
        "3. Output strictly as JSON with keys 'title' and 'body' (in clean markdown format)."
    )
    user_prompt = f"Topic: {topic_data['theme']}\nCore concept: {topic_data['key_concept']}\nSubreddit: {target_subreddit}\nAsset: {pair}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    ai_output = query_openrouter(messages, max_tokens=1200)
    if ai_output:
        try:
            clean_json = ai_output
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()
            parsed = json.loads(clean_json)
            if "title" in parsed and "body" in parsed:
                return {
                    "title": parsed["title"],
                    "body": parsed["body"],
                    "subreddit": target_subreddit,
                    "pair": pair
                }
        except Exception:
            pass

    # Built-in Institutional Knowledge Base Fallback
    title = f"Why retail support/resistance gets swept before big moves on {pair} (And how to stop getting trapped)"
    body = (
        f"Most traders start their journey drawing support and resistance lines, only to watch price aggressively spike through their level, stop them out by a couple of pips, and then immediately reverse straight toward their original target.\n\n"
        f"If that has happened to you, it is not bad luck — it is simply how market liquidity operates.\n\n"
        f"The Retail Trap vs Market Reality\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Retail textbooks teach traders to buy support and sell resistance with tight stops just outside the range.\n\n"
        f"Large liquidity providers and institutional participants cannot enter sizable positions without counterpart liquidity. "
        f"Resting retail stop-loss orders provide the exact volume required for absorption:\n\n"
        f"• Buy-Side Liquidity: Retail buy stops and breakout orders sitting above equal swing highs.\n"
        f"• Sell-Side Liquidity: Retail sell stops sitting below prominent swing lows.\n\n"
        f"The 3-Step Execution Framework\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Instead of buying the first touch of a level, here is how we approach the market systematically:\n\n"
        f"1. Patience for the Sweep: Allow price to aggressively pierce the session high or low. Never try to front-run the breakout.\n"
        f"2. Confirmed Market Structure Shift: Wait for a decisive 15-minute candle to displace back inside the range, confirming institutional participation.\n"
        f"3. Retest of Equilibrium: Look for an entry on the pullback into the 20-period EMA, offering a clean, tight invalidation level.\n\n"
        f"Risk Rules That Keep You Funded\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"No strategy wins 100% of the time, and you don't need it to. Prop firm survival comes down to two rules:\n\n"
        f"• Risk 0.50% per trade: A 4-trade losing streak is only a 2% drawdown, leaving 80% of your maximum allowable drawdown completely safe.\n"
        f"• Minimum 1:1.50R Target: Even with a 45% win rate, positive risk-to-reward ensures long-term compounding.\n\n"
        f"Question for the community: How do you handle fakeouts around key levels? Do you wait for a candle close or enter on limit orders? Curious to hear different perspectives below!"
    )
    return {
        "title": title,
        "body": body,
        "subreddit": target_subreddit,
        "pair": pair
    }
