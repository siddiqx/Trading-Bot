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
        "id": "gold_liquidity_sweep",
        "category": "Commodity / Gold ICT Concepts",
        "theme": "How Institutional Liquidity Sweeps Really Work on Gold ($XAUUSD)",
        "key_concept": "$20-$40 Gold volatility sweeps past Asian session highs/lows before NY trend displacement",
        "pair": "XAUUSD",
        "tweets": [
            (
                "🧵 1/3 Why 90% of retail traders lose trading Gold ($XAUUSD):\n\n"
                "Gold doesn't respect retail trendlines.\n"
                "Institutions engineer massive $25-$40 liquidity spikes past session highs just to absorb resting orders.\n\n"
                "Here is how smart money trades Gold 🧵👇"
            ),
            (
                "2/3 The Anatomy of the Gold Sweep:\n\n"
                "1. Asian Range: Gold chops inside a tight $15 range.\n"
                "2. The Judas Spike: London open violently spikes through the high to grab stops.\n"
                "3. The Reclaim: A 15M candle displaces back below the 20-EMA with volume."
            ),
            (
                "3/3 Gold Risk Rule:\n\n"
                "Never chase the spike on $XAUUSD.\n"
                "• Fixed 0.50% risk per trade\n"
                "• Stop behind sweep wick ($25 wide)\n"
                "• 1:1.50R target\n\n"
                "Did Gold trap you today or did you catch the sweep? Share below 👇\n\n"
                "Live setups: https://t.me/ccrs_forex_signals\n"
                "#XAUUSD #GOLD"
            )
        ],
        "reddit_title": "Why retail support/resistance gets destroyed on Gold (XAUUSD) — And how to trade liquidity sweeps",
        "reddit_body": (
            "Gold (XAU/USD) is without question the most popular asset in modern retail trading, but it is also the fastest account-killer for undisciplined traders.\n\n"
            "Retail traders draw horizontal lines at round numbers ($2,650, $2,700), place a tight $3-$5 stop loss, and watch in frustration as an aggressive candle spikes through their stop by $15 before reversing in their intended direction.\n\n"
            "Here is why Gold behaves this way, and how we systematically trade institutional liquidity sweeps on XAU/USD.\n\n"
            "The Anatomy of Gold Liquidity Engineering\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Because Gold is traded globally around the clock with extreme institutional volume, large liquidity providers cannot fill positions inside tight consolidation.\n\n"
            "• Asian Session Build-up: Between 00:00 and 07:00 UTC, Gold typically consolidates in a $15-$25 range. Breakout traders place buy stops above the high and sell stops below the low.\n"
            "• The London/NY Judas Sweep: At the session open, algorithmic market makers engineer a rapid $20-$35 impulse move past the Asian range, absorbing retail stops at premium/discount prices.\n"
            "• The 15M Displacement: Once liquidity is absorbed, price prints an impulsive displacement candle that reclaims the 20-period EMA.\n\n"
            "How to Trade the Setup\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. Never buy the breakout of session highs or sell the breakout of session lows.\n"
            "2. Wait for the sweep wick to complete and look for a confirmed 15M Market Structure Shift (MSS).\n"
            "3. Enter on the pullback into the 20-EMA dynamic equilibrium, placing your stop loss safely protected behind the sweep extreme ($20-$30 ATR buffer).\n"
            "4. Target the opposing session liquidity pool for a minimum 1:1.50R return.\n\n"
            "Risk Management on Gold (Non-Negotiable)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1 standard lot on Gold controls 100 troy ounces. A $20 move against a 1.0 lot is -$2,000. Never use static lot sizing on Gold. "
            "Always calculate lot size so total dollar risk equals exactly 0.50% of your account balance.\n\n"
            "Question for the community: How do you handle Gold's aggressive volatility? Do you trade the London open, the New York open, or wait for the daily close?"
        )
    },
    {
        "id": "gold_news_cpi_nfp",
        "category": "Commodity / Gold Macro Flow",
        "theme": "Trading Gold ($XAUUSD) Around CPI & US News Spikes (Without Gambling)",
        "key_concept": "How news spikes engineer two-way liquidity pools on Gold and why waiting for 15M structure shift avoids slippage",
        "pair": "XAUUSD",
        "tweets": [
            (
                "🧵 1/3 The biggest mistake traders make on Gold ($XAUUSD) during high-impact news:\n\n"
                "Trying to gamble the CPI or NFP candle.\n"
                "Institutions use the initial 1-minute spike to wipe out retail stops on BOTH sides of the market.\n\n"
                "Here is how patient traders exploit it 🧵👇"
            ),
            (
                "2/3 The Post-News Execution Rule:\n\n"
                "1. The 2-Way Sweep: News runs Buy stops first, then Sell stops.\n"
                "2. Let Dust Settle: Wait 15 minutes for real institutional order flow.\n"
                "3. The Reclaim: Enter only on confirmed 20-EMA rejection with displacement."
            ),
            (
                "3/3 Gold News Rule:\n\n"
                "Spreads widen violently during US data.\n"
                "• Never trade the initial spike\n"
                "• Fixed 0.50% account risk\n"
                "• 1:1.50R target\n\n"
                "Do you trade Gold during news or wait for close? Share below 👇\n\n"
                "Alerts: https://t.me/ccrs_forex_signals\n"
                "#XAUUSD #GOLD"
            )
        ],
        "reddit_title": "Why gambling US CPI / NFP news on Gold (XAUUSD) is a trap — And the 15-minute patience rule",
        "reddit_body": (
            "Every month during US CPI or Non-Farm Payrolls (NFP), trading forums and Telegram channels are flooded with screenshots of blown Gold accounts. "
            "Traders try to guess the release number, enter market orders seconds before the data drops, and suffer massive spread widening and slippage.\n\n"
            "Here is an institutional perspective on how news really impacts Gold liquidity, and how professional traders trade the aftermath.\n\n"
            "The Mechanics of News Volatility\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "When high-impact news drops, interbank liquidity providers immediately pull their limit orders to protect their books. "
            "With thin liquidity, even modest order flow causes extreme price slippage of $10 to $20 within seconds.\n\n"
            "1. The Stop-Run Phase: The initial candle almost always spikes in one direction to run stops, before whipping back in the opposite direction to trap breakout orders.\n"
            "2. The Absorption Phase: Once retail stops on both sides are cleared, institutions begin accumulating positions at true institutional discount/premium levels.\n\n"
            "The 15-Minute Patience Rule\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• Step 1: Hands off the keyboard for the first 15 minutes post-release. Let spreads normalize from $2.00+ back to standard $0.20-$0.35.\n"
            "• Step 2: Observe which liquidity boundary was swept. Did price run the prior day's high or low?\n"
            "• Step 3: Wait for a confirmed 15M candle close that displaces back toward the 20-period EMA.\n"
            "• Step 4: Enter on the retest of the rejection wick, anchoring stop loss behind the news spike high/low with fixed 0.50% risk.\n\n"
            "Question for the community: Do you keep positions open through CPI/NFP or do you completely flat your book before high-impact US news?"
        )
    },
    {
        "id": "gold_prop_contract_sizing",
        "category": "Prop Firm Mathematics",
        "theme": "Why Gold ($XAUUSD) Blows Prop Firm Challenges: The 100oz Contract Reality",
        "key_concept": "Contract size math, $1 point value, why oversized lot sizes cause instant challenge failure",
        "pair": "XAUUSD",
        "tweets": [
            (
                "🧵 1/3 Why Gold ($XAUUSD) blows more prop firm accounts than any Forex pair:\n\n"
                "Contract sizing. 1 standard lot on Gold controls 100 troy ounces.\n"
                "A simple $20 move against a 1.0 lot is an instant $2,000 loss (40% of a $5k prop challenge).\n\n"
                "Here is the math that keeps you funded 🧵👇"
            ),
            (
                "2/3 Sizing Formula for Gold:\n\n"
                "1. Risk Budget: Fixed 0.50% ($25 on $5k, $500 on $100k).\n"
                "2. Dynamic Stop: Gold ATR requires a $20 to $30 stop buffer.\n"
                "3. Micro-Lots: Sizing must scale down to 0.01-0.02 lots. Never trade fixed 1.0 lots on Gold."
            ),
            (
                "3/3 Prop Firm Rule:\n\n"
                "Consistency is about risk geometry, not guessing.\n"
                "• Scale lots to dollar risk\n"
                "• Target 1:1.50R minimum\n"
                "• Never average down\n\n"
                "What lot size do you use on Gold? Share below 👇\n\n"
                "Live alerts: https://t.me/ccrs_forex_signals\n"
                "#XAUUSD #PropFirm"
            )
        ],
        "reddit_title": "The math behind why Gold (XAUUSD) destroys prop firm challenges: 100oz contract sizing guide",
        "reddit_body": (
            "Most traders fail prop firm challenges on Gold not because of their entry strategy, but because they treat Gold like a standard Forex pair (EUR/USD, GBP/USD).\n\n"
            "Let's break down the exact mathematics of Gold contract specifications and how to size your positions to guarantee you never violate maximum drawdown limits.\n\n"
            "Contract Geometry: Forex vs Gold\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• On EUR/USD: 1 standard lot = 100,000 units. A 1-pip move = $10.00.\n"
            "• On Gold (XAU/USD): 1 standard lot = 100 Troy Ounces. A $1.00 move in Gold price = $100.00 per standard lot.\n\n"
            "Because Gold routinely moves $25.00 to $40.00 in a single trading session, an open position of 1.0 lot carries $2,500 to $4,000 of intraday fluctuation.\n"
            "On a $5,000 challenge account with a $500 max daily loss limit, a 1.0 lot on Gold can blow the account in under 3 minutes.\n\n"
            "The Prop Firm Gold Formula\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "To risk exactly 0.50% ($25 on $5k, $500 on $100k) with a standard $25 volatility stop:\n"
            "• Lot Size = (Account Balance * 0.005) / (Stop Distance in Dollars * 100)\n"
            "• On a $5,000 account: ($25.00) / ($25.00 * 100) = 0.01 Lots.\n"
            "• On a $100,000 account: ($500.00) / ($25.00 * 100) = 0.20 Lots.\n\n"
            "If you trade more than 0.01-0.02 lots on a $5k account or more than 0.20 lots on a $100k account, you are overleveraged for Gold's volatility.\n\n"
            "Question for the community: What is your strict max lot size when trading Gold on prop firm accounts? Do you calculate risk per trade or trade fixed lots?"
        )
    },
    {
        "id": "ict_liquidity_sweep",
        "category": "ICT / Smart Money Concepts",
        "theme": "Why Retail Support/Resistance Gets Swept Before Real Moves",
        "key_concept": "Buy-Side Liquidity (BSL) & Sell-Side Liquidity (SSL) stop-runs by institutional algorithms",
        "pair": "EURUSD",
        "tweets": [
            (
                "🧵 1/3 Most retail traders lose on $EURUSD not because their bias is wrong, "
                "but because they enter at obvious support.\n\n"
                "Smart money sees support as a pool of resting retail stops to harvest for liquidity.\n\n"
                "Here is how to stop getting trapped 🧵👇"
            ),
            (
                "2/3 The Anatomy of the Sweep:\n\n"
                "1. Range Buildup: Price chops, baiting stops outside the range.\n"
                "2. The Stop Hunt: An aggressive spike punches through to absorb orders.\n"
                "3. The Reclaim: A strong 15M candle closes back inside, tapping the 20-EMA."
            ),
            (
                "3/3 The Prop Trader Rule:\n\n"
                "Never chase the spike. Wait for the trap to spring first.\n"
                "• Fixed 0.50% risk per trade\n"
                "• 1:1.50R target\n\n"
                "Did London fake you out today or did you catch the reclaim? Let's discuss 👇\n\n"
                "Live alerts: https://t.me/ccrs_forex_signals\n"
                "#EURUSD #Forex"
            )
        ],
        "reddit_title": "Why retail support/resistance gets swept before big moves on EURUSD (And how to stop getting trapped)",
        "reddit_body": (
            "Most traders start their journey drawing support and resistance lines, only to watch price aggressively spike through their level, stop them out by a couple of pips, and then immediately reverse straight toward their original target.\n\n"
            "If that has happened to you, it is not bad luck — it is simply how market liquidity operates.\n\n"
            "The Retail Trap vs Market Reality\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Retail textbooks teach traders to buy support and sell resistance with tight stops just outside the range.\n\n"
            "Large liquidity providers and institutional participants cannot enter sizable positions without counterpart liquidity. "
            "Resting retail stop-loss orders provide the exact volume required for absorption:\n\n"
            "• Buy-Side Liquidity (BSL): Retail buy stops and breakout orders sitting above equal swing highs.\n"
            "• Sell-Side Liquidity (SSL): Retail sell stops sitting below prominent swing lows.\n\n"
            "The 3-Step Execution Framework\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Instead of buying the first touch of a level, here is how we approach the market systematically:\n\n"
            "1. Patience for the Sweep: Allow price to aggressively pierce the session high or low. Never try to front-run the breakout.\n"
            "2. Confirmed Market Structure Shift: Wait for a decisive 15-minute candle to displace back inside the range, confirming institutional participation.\n"
            "3. Retest of Equilibrium: Look for an entry on the pullback into the 20-period EMA, offering a clean, tight invalidation level.\n\n"
            "Risk Rules That Keep You Funded\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "No strategy wins 100% of the time, and you don't need it to. Prop firm survival comes down to two rules:\n\n"
            "• Risk 0.50% per trade: A 4-trade losing streak is only a 2% drawdown, leaving 80% of your maximum allowable drawdown completely safe.\n"
            "• Minimum 1:1.50R Target: Even with a 45% win rate, positive risk-to-reward ensures long-term compounding.\n\n"
            "Question for the community: How do you handle fakeouts around key levels? Do you wait for a candle close or enter on limit orders? Curious to hear different perspectives below!"
        )
    },
    {
        "id": "prop_firm_risk_math",
        "category": "Prop Firm Mathematics",
        "theme": "The Real Math of Passing Prop Challenges: Why 0.50% Risk Beats 2% Risk",
        "key_concept": "Geometric drawdown protection and asymmetric 1:1.50R minimum expectancy",
        "pair": "USDCAD",
        "tweets": [
            (
                "🧵 1/3 Why 95% of traders fail prop firm challenges on $USDCAD:\n\n"
                "It's almost never the strategy. It's risk geometry.\n"
                "At 2% risk, a normal 4-loss streak wipes out 80% of your max drawdown buffer. Tilt takes over.\n\n"
                "Here is the math that keeps you funded 🧵👇"
            ),
            (
                "2/3 The Math of Asymmetry:\n\n"
                "1. The 0.50% Safety Net: A 4-trade loss streak is only 2.0% drawdown, leaving 80% of your buffer safe.\n"
                "2. The 1:1.50R Target: Even with a modest 45% win rate, positive expectancy compounds equity consistently without stress."
            ),
            (
                "3/3 Prop Firm Rule:\n\n"
                "Survive drawdown clusters — don't swing for home runs.\n"
                "• Max 0.50% risk\n"
                "• Stops behind sweep wicks\n\n"
                "What risk % do you use on funded accounts? Share below 👇\n\n"
                "Live setups: https://t.me/ccrs_forex_signals\n"
                "#USDCAD #PropFirm #FTMO"
            )
        ],
        "reddit_title": "The exact math of why 0.50% risk beats 2.0% risk on prop firm challenges (USDCAD case study)",
        "reddit_body": (
            "Most traders who fail prop firm challenges believe they just need a higher win-rate strategy. "
            "In reality, the number one killer of funded accounts is poor risk geometry.\n\n"
            "Let's look at why risking 0.50% per trade makes passing statistical certainty over time, while 2.0% risk guarantees failure.\n\n"
            "The Drawdown Trap\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "On a standard $100k account with a 10% maximum trailing drawdown, your actual capital isn't $100k — it's $10k.\n\n"
            "• At 2.0% risk ($2,000 per trade), a completely normal statistical streak of 4 consecutive losses wipes out $8,000 (80% of your entire drawdown buffer).\n"
            "• At 0.50% risk ($500 per trade), the same 4-loss streak is only a $2,000 drawdown, leaving $8,000 (80%) of your buffer fully intact.\n\n"
            "The Power of Asymmetric R:R (1:1.50R)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "With a 1:1.50R minimum target:\n"
            "• 10 trades: 5 wins (+7.5R), 5 losses (-2.5R) = Net +5.0R (+2.5% gain).\n"
            "• You don't need a 70% win rate. You only need discipline to cut losers fast and let winners hit opposing liquidity.\n\n"
            "Actionable Rules for Funded Traders\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. Cap risk at 0.50% per trade.\n"
            "2. Anchor stop-losses behind session liquidity sweep wicks.\n"
            "3. Take partials at +1.2R and trail to breakeven.\n\n"
            "Question for the community: What is your strict max risk per trade on funded accounts? Have you ever had to dial down your risk to survive a bad week?"
        )
    },
    {
        "id": "macro_ccrs_divergence",
        "category": "Macro Currency Relative Strength",
        "theme": "Why Single-Pair Technical Indicators Lie: Cross-Currency Relative Strength (CCRS)",
        "key_concept": "Measuring rolling 200-hour Z-score divergence across 7 major currencies to identify true institutional capital flow",
        "pair": "USDCHF",
        "tweets": [
            (
                "🧵 1/3 Ever wonder why RSI gives an 'oversold' signal on $USDCHF, but price keeps dumping anyway?\n\n"
                "Single-pair indicators only look at 1 chart. They are blind to where global capital is actually flowing across currency baskets.\n\n"
                "Here is why relative strength matters 🧵👇"
            ),
            (
                "2/3 The Multi-Currency Matrix:\n\n"
                "1. Currency Baskets: The US Dollar trades against 6 peers at once.\n"
                "2. True Divergence: When USD strengthens across all peers while CHF lags, that is institutional flow — not a fake oscillator divergence.\n"
                "Trade flow, not oscillators."
            ),
            (
                "3/3 How We Execute:\n\n"
                "We wait for currency divergence to confirm, then use 15M sweeps for entries.\n"
                "• 0.50% disciplined risk\n"
                "• 1:1.50R target\n\n"
                "Do you trade single pairs or currency strength? Let's discuss 👇\n\n"
                "Alerts: https://t.me/ccrs_forex_signals\n"
                "#USDCHF #Forex"
            )
        ],
        "reddit_title": "Why single-pair indicators (RSI/MACD) fail: The power of 7-currency relative strength on USDCHF",
        "reddit_body": (
            "How many times have you bought an 'oversold' RSI or MACD divergence on a single currency pair, only for price to blow straight through your stop?\n\n"
            "Single-pair technical indicators are fundamentally lagging because currencies do not trade in a vacuum. A currency pair is simply a ratio between two sovereign economies.\n\n"
            "The Flaw of Single-Pair Indicators\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "When you look at USD/CHF on a 1-hour chart, an oscillator can stay 'overbought' for days if global capital is systematically fleeing into the US Dollar across all asset classes.\n\n"
            "If the US Dollar is gaining relative strength against EUR, GBP, JPY, and CAD, buying CHF because an intraday oscillator says 'oversold' is stepping directly in front of an institutional freight train.\n\n"
            "The Macro Relative Strength Approach\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. Synthetic Currency Baskets: Measure the relative strength of each individual currency against its global peers.\n"
            "2. Trade True Flow: Only pair the strongest currency against the weakest currency.\n"
            "3. Timing on 15M: Once macro direction is confirmed, use lower-timeframe liquidity sweeps and 20-EMA retests for precision entry.\n\n"
            "Question for the community: Do you monitor multi-currency strength (like DXY or currency indexes) before taking setups on individual pairs, or do you stick to single-chart price action?"
        )
    },
    {
        "id": "session_killzones_judas",
        "category": "Session Killzones",
        "theme": "How the London Open Judas Swing Engineers Retail Liquidity",
        "key_concept": "False breakout past Asian session range to trigger retail breakout stops before real institutional trend displacement",
        "pair": "AUDUSD",
        "tweets": [
            (
                "🧵 1/3 The London Open Judas Swing on $AUDUSD blows more retail accounts than almost any intraday pattern.\n\n"
                "Between 07:00-08:30 UTC, an aggressive false spike engineers liquidity right before the real session trend begins.\n\n"
                "Here is how to recognize it 🧵👇"
            ),
            (
                "2/3 The Anatomy of the Fakeout:\n\n"
                "1. Asian Range Trap: Liquidity builds stops above Asian highs & lows.\n"
                "2. The Judas Spike: London open pierces the high to trap breakout buyers.\n"
                "3. Market Structure Shift: Price displaces back down through the 20-EMA."
            ),
            (
                "3/3 The Execution Rule:\n\n"
                "Never trade the initial breakout.\n"
                "• Let Asian stops sweep first\n"
                "• Enter on 15M pullback to 20-EMA\n"
                "• Fixed 0.50% risk | 1:1.50R target\n\n"
                "Did London trap you today or did you wait? Let's discuss 👇\n\n"
                "Alerts: https://t.me/ccrs_forex_signals\n"
                "#AUDUSD #Forex"
            )
        ],
        "reddit_title": "How the London Open 'Judas Swing' engineers liquidity on AUDUSD (And how to trade it)",
        "reddit_body": (
            "If you trade the European morning session, you have likely experienced this: The London session opens at 07:00-08:00 UTC, "
            "price aggressively breaks above the overnight range, you enter a breakout long, and within 15 minutes a massive rejection wick forms, "
            "stopping you out as the market dumps for the rest of the day.\n\n"
            "This classic pattern is known in institutional Smart Money Concepts as the 'Judas Swing'. Here is how it works.\n\n"
            "Why the False Breakout Exists\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "During the quiet Asian session, price typically consolidates inside a well-defined 25-40 pip range. "
            "Retail breakout traders place buy stops above the Asian high and sell stops below the Asian low.\n\n"
            "Large institutions preparing to sell the day's trend need buy liquidity to fill their short orders. "
            "By pushing price just 5-10 pips above the Asian high at the London open, they trigger those buy stops, filling their short positions at premium prices.\n\n"
            "How to Trade the Judas Reversal\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. Mark the Asian Range: Draw the highest high and lowest low between 00:00 and 07:00 UTC.\n"
            "2. Wait for the Sweep: Watch price spike beyond the range without chasing.\n"
            "3. Confirm Displacement: Wait for a 15M candle to close back inside the Asian range with an impulsive body.\n"
            "4. Enter the Retest: Enter on the pullback to the 20-EMA, placing stops behind the sweep wick and targeting the opposing Asian range low.\n\n"
            "Question for the community: Do you trade session opens actively or do you prefer to wait until 1-2 hours after London/NY opens before placing trades?"
        )
    },
    {
        "id": "order_block_mechanics",
        "category": "Order Block Mechanics",
        "theme": "The Anatomy of High-Probability Order Blocks (+OB/-OB)",
        "key_concept": "Identifying genuine institutional order blocks with confirmed 15M displacement and Fair Value Gaps (FVG) vs retail fakeouts",
        "pair": "EURUSD",
        "tweets": [
            (
                "🧵 1/3 Most traders mark every opposite candle on $EURUSD as an 'order block', "
                "then wonder why price slices right through them.\n\n"
                "Real institutional order blocks have strict criteria. Without displacement, it's just retail chop.\n\n"
                "Here is how to spot the real ones 🧵👇"
            ),
            (
                "2/3 The 3 Criteria of a High-Win-Rate OB:\n\n"
                "1. Prior Sweep: Price must sweep a key high/low before forming the block.\n"
                "2. Impulsive Displacement: Must create an imbalance / Fair Value Gap.\n"
                "3. Structure Shift: Confirms institutions defended the level with volume."
            ),
            (
                "3/3 How to Trade It:\n\n"
                "Wait for price to pull back to the order block in confluence with 20-EMA.\n"
                "• Stops behind sweep wick\n"
                "• 0.50% risk | 1:1.50R target\n\n"
                "How do you filter order blocks? Share below 👇\n\n"
                "Live setups: https://t.me/ccrs_forex_signals\n"
                "#EURUSD #ICT #Trading"
            )
        ],
        "reddit_title": "The 3 rules that separate genuine institutional order blocks from retail noise on EURUSD",
        "reddit_body": (
            "Order Blocks (OB) have become one of the most popular concepts in modern technical trading. "
            "However, many traders make the mistake of marking every last opposing candle before an expansion as an order block, "
            "resulting in a chart cluttered with rectangles that get blown through repeatedly.\n\n"
            "Here are the 3 strict filters we use to identify genuine institutional order blocks with high win-rate expectancy.\n\n"
            "1. The Preceding Liquidity Sweep (No Sweep = No Trade)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Institutions do not accumulate positions in the middle of a range. A valid order block must form immediately after a liquidity sweep of a key high (Buy-Side Liquidity) or low (Sell-Side Liquidity).\n\n"
            "2. Impulsive Displacement & Fair Value Gap (FVG)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "The candle leaving the order block cannot be hesitant or small. It must print an impulsive displacement candle that leaves an imbalance / Fair Value Gap. This confirms institutional market orders overwhelmed opposing limit orders.\n\n"
            "3. Confluence with Dynamic Moving Averages (20-EMA)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "When price pulls back to mitigate the order block, we look for confluence with the 20-period dynamic EMA. If the order block holds and prints a rejection wick, we enter with our stop safely protected behind the structural swing.\n\n"
            "Question for the community: How do you personally identify order blocks? Do you refine them down to the 5M/1M chart or do you stick to higher timeframes?"
        )
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


def generate_ai_twitter_educational_thread(topic_idx: Optional[int] = None, pair: Optional[str] = None) -> Dict[str, Any]:
    """
    Generates a high-engagement, viral-grade 3-tweet educational FinTwit thread using AI.
    Every tweet is structured, multi-line, full-bodied (220-275 chars), and provides real trading value.
    Falls back to curated institutional knowledge base if offline or low quality.
    Supports filtering by asset (e.g. 'XAUUSD' / Gold).
    """
    if pair:
        from core.marketing.contents_bot import normalize_asset_symbol
        norm_pair = normalize_asset_symbol(pair)
        matching = [t for t in TOPICS if t["pair"].upper() == norm_pair]
        if matching:
            topic_data = matching[topic_idx % len(matching)] if topic_idx is not None else random.choice(matching)
        else:
            topic_data = TOPICS[topic_idx % len(TOPICS)] if topic_idx is not None else random.choice(TOPICS)
    else:
        topic_data = TOPICS[topic_idx % len(TOPICS)] if topic_idx is not None else random.choice(TOPICS)

    pair = topic_data["pair"]

    system_prompt = (
        f"You are an elite, highly followed currency and prop firm trader on Twitter/FinTwit.\n"
        f"Write an authoritative, high-impression 3-tweet educational thread about trading ${pair}.\n"
        f"CRITICAL FORMATTING & LENGTH RULES:\n"
        f"1. Every tweet MUST be substantial, full-bodied, and multi-line (between 220 and 275 characters with paragraph breaks and bullet points). "
        f"NEVER write shallow 1-line or 1-sentence tweets — FinTwit readers demand depth, narrative context, and actionable substance.\n"
        f"2. Tone: Conversational, experienced, and peer-to-peer. Zero robotic math formulas, zero guru hype.\n"
        f"3. Tweet 1 (The Hook): A compelling narrative hook about why retail traders get trapped on ${pair}. End with 'Here is the breakdown 🧵👇'.\n"
        f"4. Tweet 2 (The Mechanics): A clear, step-by-step price action breakdown with clean numbered points (1. The Range, 2. The Stop Hunt, 3. The Reclaim at 20-EMA).\n"
        f"5. Tweet 3 (Risk & Engagement): Prop firm risk rules (strict 0.50% risk, 1:1.50R target), an engaging open-ended question to spark discussion, cashtags (#{pair} #Forex #Trading #PriceAction), and the EXACT link: {DEFAULT_CHANNEL_URL} (never use placeholder links).\n"
        f"Output strictly valid JSON with keys 'tweet_1', 'tweet_2', 'tweet_3'."
    )
    user_prompt = f"Topic: {topic_data['theme']}\nCore concept: {topic_data['key_concept']}\nAsset focus: ${pair}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    ai_output = query_openrouter(messages, max_tokens=1000)
    if ai_output:
        try:
            clean_json = ai_output
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()
            parsed = json.loads(clean_json)
            if "tweet_1" in parsed and "tweet_2" in parsed and "tweet_3" in parsed:
                t1 = str(parsed["tweet_1"]).strip()
                t2 = str(parsed["tweet_2"]).strip()
                t3 = str(parsed["tweet_3"]).strip()

                # Clean any placeholder URLs if model hallucinated
                for ph in ["https://link.to/your/forex/resource", "http://link.to", "link.to", "your/link"]:
                    if ph in t3:
                        t3 = t3.replace(ph, DEFAULT_CHANNEL_URL)

                # Quality gate: Reject lazy 1-liners (must be rich, multi-sentence tweets)
                if len(t1) >= 160 and len(t2) >= 160 and len(t3) >= 160:
                    return {
                        "tweets": [t1, t2, t3],
                        "topic": topic_data["theme"],
                        "pair": pair
                    }
        except Exception:
            pass

    # Built-in Institutional Knowledge Base (Guaranteed high-impression depth)
    curated_tweets = topic_data.get("tweets")
    if not curated_tweets or len(curated_tweets) != 3:
        curated_tweets = [
            (
                f"🧵 1/3 Most retail traders lose on ${pair} not because their bias is wrong, "
                f"but because they enter at obvious support/resistance.\n\n"
                f"Smart money doesn't view support as a wall. They view it as a pool of resting retail stop-losses ready to be harvested.\n\n"
                f"Here is how to stop getting caught 🧵👇"
            ),
            (
                f"2/3 The Anatomy of the Sweep:\n\n"
                f"1. Range Buildup: Price consolidates, baiting breakout traders to place stops outside the range.\n"
                f"2. The Stop Hunt: An aggressive spike punches through the level to absorb liquidity.\n"
                f"3. The Reclaim: A decisive 15M candle closes back inside the range, tapping the 20-EMA."
            ),
            (
                f"3/3 The Prop Trader Rule:\n\n"
                f"Never chase the initial spike. Wait for the trap to spring first.\n"
                f"• Fixed 0.50% risk per execution\n"
                f"• Minimum 1:1.50R asymmetric target\n"
                f"• Capital stays protected\n\n"
                f"Did the session open fake you out today or did you catch the reclaim? Let's discuss below 👇\n\n"
                f"Free daily trade breakdowns: {DEFAULT_CHANNEL_URL}\n"
                f"#{pair} #Forex #PriceAction #PropFirm"
            )
        ]

    return {
        "tweets": curated_tweets,
        "topic": topic_data["theme"],
        "pair": pair
    }


def generate_ai_reddit_educational_post(
    topic_idx: Optional[int] = None,
    target_subreddit: str = "r/Forex",
    pair: Optional[str] = None
) -> Dict[str, str]:
    """
    Generates an in-depth, high-effort Reddit educational breakdown for r/Forex or r/PropFirm.
    Supports filtering by asset (e.g. 'XAUUSD' / Gold).
    """
    if pair:
        from core.marketing.contents_bot import normalize_asset_symbol
        norm_pair = normalize_asset_symbol(pair)
        matching = [t for t in TOPICS if t["pair"].upper() == norm_pair]
        if matching:
            topic_data = matching[topic_idx % len(matching)] if topic_idx is not None else random.choice(matching)
        else:
            topic_data = TOPICS[topic_idx % len(TOPICS)] if topic_idx is not None else random.choice(TOPICS)
    else:
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

    ai_output = query_openrouter(messages, max_tokens=1500)
    if ai_output:
        try:
            clean_json = ai_output
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0].strip()
            parsed = json.loads(clean_json)
            if "title" in parsed and "body" in parsed:
                body_str = str(parsed["body"]).strip()
                # Quality gate: Must be a detailed multi-paragraph breakdown (at least 500 chars)
                if len(body_str) >= 500:
                    return {
                        "title": parsed["title"],
                        "body": body_str,
                        "subreddit": target_subreddit,
                        "pair": pair
                    }
        except Exception:
            pass

    # Built-in Institutional Knowledge Base Fallback
    curated_title = topic_data.get("reddit_title") or f"Why retail support/resistance gets swept before big moves on {pair}"
    curated_body = topic_data.get("reddit_body") or (
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
        "title": curated_title,
        "body": curated_body,
        "subreddit": target_subreddit,
        "pair": pair
    }
