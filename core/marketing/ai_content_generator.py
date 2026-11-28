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
        "You are an institutional algorithmic currency trader and quantitative analyst. "
        "Write a punchy, ultra-valuable 3-tweet educational thread for Twitter/FinTwit. "
        "Strict rules:\n"
        "1. NO generic guru motivational fluff. Deep, authentic technical mechanics only.\n"
        "2. Tweet 1: Hook about the topic with a counter-intuitive truth. Under 240 chars.\n"
        "3. Tweet 2: Step-by-step institutional breakdown or mechanics. Under 260 chars.\n"
        "4. Tweet 3: Practical actionable takeaway for prop firm / serious traders, cashtags (#EURUSD #ICT #Forex), and a clean link.\n"
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
        f"🧵 1/3 The uncomfortable truth about ${pair} liquidity sweeps:\n\n"
        f"Retail traders view support and resistance as barriers. Institutional algorithms view them as liquidity pools containing resting stop-loss orders.\n\n"
        f"If you buy obvious support, your stop is the exact fuel smart money needs to enter."
    )
    t2 = (
        f"2/3 The Institutional Mechanics:\n\n"
        f"1. Consolidation builds retail buy/sell stops outside the range.\n"
        f"2. London/NY Open: Aggressive Judas sweep runs stops at Buy-Side Liquidity (BSL).\n"
        f"3. 15M Market Structure Shift (MSS) + tap into -Order Block confirms true direction."
    )
    t3 = (
        f"3/3 Systematic Edge for Prop Traders:\n\n"
        f"• Wait for the sweep to confirm FIRST — never anticipate.\n"
        f"• Risk max 0.50% per execution with 2.0x ATR stops.\n"
        f"• Target opposing liquidity at 1:1.50R minimum.\n\n"
        f"Follow institutional macro flows free in our surveillance cockpit:\n"
        f"👉 {DEFAULT_CHANNEL_URL}\n\n"
        f"#{pair} #ICT #SmartMoneyConcepts #Forex #PropFirm"
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
        "You are an experienced quantitative currency trader who has passed multiple institutional prop firm challenges. "
        "Write an authoritative, highly educational Reddit post for r/Forex or r/PropFirm. "
        "Strict rules:\n"
        "1. NO promotional spam. Zero guru claims. Pure value, mathematical edge, and institutional mechanics.\n"
        "2. Include detailed sections: Introduction, The Institutional Reality, Technical Mechanics (SMC/ICT), Risk Management Rules, and Key Takeaway.\n"
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
    title = f"[Deep Dive] {topic_data['theme']}: An Institutional Perspective on {pair}"
    body = (
        f"## Introduction\n\n"
        f"Most retail traders focus entirely on static indicators (RSI, MACD, generic Bollinger Bands) "
        f"on single currency pairs without understanding the underlying mechanics of institutional order flow.\n\n"
        f"In this breakdown, we examine **{topic_data['theme']}**, breaking down how interbank algorithms "
        f"engineer liquidity and how quantitative traders exploit this with asymmetric risk management.\n\n"
        f"---\n\n"
        f"### 1. The Institutional Reality vs Retail Belief\n"
        f"Retail technical analysis teaches traders to buy support and sell resistance with tight stops just beyond the level. "
        f"Large liquidity providers and institutional funds cannot enter sizable positions without counterpart liquidity. "
        f"Resting retail stop-loss orders provide the exact volume required for absorption.\n\n"
        f"* **Buy-Side Liquidity (BSL):** Retail buy stops and breakout orders sitting above equal swing highs.\n"
        f"* **Sell-Side Liquidity (SSL):** Retail sell stops sitting below prominent swing lows.\n\n"
        f"### 2. Smart Money Concepts (ICT) Execution Framework\n"
        f"To avoid being trapped during liquidity engineering:\n"
        f"1. **Patience for the Sweep:** Allow price to aggressively pierce the swing high/low. Do not trade the initial breakout.\n"
        f"2. **Confirmed Market Structure Shift (MSS):** Wait for an impulsive candle close breaking counter-structure with displacement.\n"
        f"3. **Equilibrium Mitigation:** Enter on the retest of the confirmed Order Block or Fair Value Gap confluence with the 20-EMA.\n\n"
        f"### 3. Prop Firm Compliance & Mathematical Edge\n"
        f"* **Risk Budget:** Never risk more than 0.50% to 0.75% per execution. A 5-loss streak at 0.50% is only 2.5% drawdown, leaving 75% of your prop drawdown buffer intact.\n"
        f"* **Asymmetric Geometry:** Anchor your Take Profit to opposing unmitigated liquidity at a **minimum 1:1.50R target**.\n"
        f"* **Stealth Execution:** Trade with market orders at true spread to minimize broker slippage footprint.\n\n"
        f"---\n\n"
        f"### Key Takeaway for Systematic Traders\n"
        f"Consistency is not about predicting every tick. It is about understanding where market liquidity resides, "
        f"waiting for institutional participation to confirm, and executing with uncompromising mathematical risk control.\n\n"
        f"*What are your rules for identifying genuine liquidity sweeps vs trend continuations? Let's discuss below.*"
    )
    return {
        "title": title,
        "body": body,
        "subreddit": target_subreddit,
        "pair": pair
    }
