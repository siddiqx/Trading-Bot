# 24/7 Institutional Algorithmic Signal Engine & Trade Journal

![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue?logo=python)
![Cloudflare Workers](https://img.shields.io/badge/Cloudflare_Workers-Edge_Serverless-orange?logo=cloudflare)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Automated_24%2F7_Cron-black?logo=githubactions)
![Telegram Bot API](https://img.shields.io/badge/Telegram_Bot-Interactive_Terminal-2CA5E0?logo=telegram)
![License](https://img.shields.io/badge/License-Proprietary-red)
![System Version](https://img.shields.io/badge/System-v2.0--Frozen-blueviolet)
![Forward Testing](https://img.shields.io/badge/Forward_Testing-2026--10--02-emerald)
![Test Suite](https://img.shields.io/badge/Tests-41%20Passing-brightgreen)

An institutional-grade, **100% free, 24/7 automated algorithmic trading system** optimised for the **Core Alpha Triad**: Spot Gold (`XAUUSD`), `EURUSD`, and `USDCAD`.

The engine runs entirely in the cloud with **zero hardware dependency** (runs 24/7 with your local PC powered off) and **zero paid subscriptions** (eliminates TradingView Premium, paid VPS, and external server costs).

> 🏛️ **Executive Whitepaper & Architecture Specifications:**
> - 📖 **[Institutional Whitepaper (GitHub Markdown View)](docs/Institutional_Trading_Engine_Whitepaper.md)** *(Instant rich rendering on GitHub)*
> - 🌐 **[Interactive Web Whitepaper (HTML)](docs/Institutional_Trading_Engine_Whitepaper.html)** *(Full interactive web presentation & print-to-PDF)*
> - 📑 **[Architecture Whitepaper (PDF)](docs/Institutional_Trading_Engine_Whitepaper.pdf)** *(Downloadable publication vector PDF)*

---

## 1. System Architecture

```
                    ┌────────────────────────────────────────────────────────┐
                    │            24/7 SERVERLESS CLOUD ARCHITECTURE           │
                    └────────────────────────────────────────────────────────┘

    ┌──────────────────────────┐                   ┌──────────────────────────┐
    │  GitHub Actions (Cloud)  │                   │ Cloudflare Global Edge   │
    │  Scheduled Cron (*/15m)  │                   │ Serverless Worker Relay  │
    └─────────────┬────────────┘                   └─────────────┬────────────┘
                  │                                              │
                  ▼                                              │
    ┌──────────────────────────┐                                 │
    │  Market Scanner Engine   │                                 │
    │  (market_scanner.py)     │                                 │
    │  • Yahoo Finance Feed    │                                 │
    │  • Core Alpha Triad      │                                 │
    │  • ADX Regime Filter     │                                 │
    │  • ICT Liquidity Targeting│                                │
    │  • Break-Even at +1.0R   │                                │
    │  • London/NY Overlap Block│                               │
    │  • 24h EMA Invalidation  │                                 │
    │  • Origin Order Block SL │                                 │
    │  • Pending Order Expiry  │                                 │
    └─────────────┬────────────┘                                 │
                  │                                              │
                  ├─────────────────── Sync Trades ──────────────┤
                  │                   (POST /sync_trades)        │
                  │                                              │
                  ▼                                              ▼
    ┌──────────────────────────┐                   ┌──────────────────────────┐
    │ Telegram Bot Push Alerts │                   │ Telegram Webhook Router  │
    │ • New Confirmed Breakout │                   │ • /radar   • /history    │
    │ • Break-Even Activation  │                   │ • /prices  • /performance│
    │ • Order Filled / Expired │                   │ • /status  • /strategy   │
    │ • TP / SL / Invalidation │                   │                          │
    └─────────────┬────────────┘                   └─────────────┬────────────┘
                  │                                              │
                  ▼                                              ▼
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                      User Mobile & Desktop Client                       │
    │                 Institutional Interactive Terminal UI                   │
    └─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Quantitative Strategy: Structural Breakout & ICT Liquidity Engine (v2.0-Frozen)

The strategy is a systematic, non-discretionary momentum model designed to capture sustained market displacements while eliminating false breakout traps, regime chop, and lingering consolidation. The ruleset is **frozen** following a forensic audit of 235 historical trades — no further modifications until out-of-sample forward validation completes.

### Entry Confluence Rulebook

| Strategy Dimension | Bullish Execution (LONG) | Bearish Execution (SHORT) |
| :--- | :--- | :--- |
| **Asset Universe** | `XAUUSD`, `EURUSD`, `USDCAD` (Core Alpha Triad) | `XAUUSD`, `EURUSD`, `USDCAD` (Core Alpha Triad) |
| **Breakout Trigger** | Confirmed close above Donchian High (10-bar Gold / **15-bar Forex**) | Confirmed close below Donchian Low (10-bar Gold / **15-bar Forex**) |
| **Trend Alignment** | `Close > EMA 50` & `EMA 20 > EMA 50` | `Close < EMA 50` & `EMA 20 < EMA 50` |
| **Velocity Vector** | EMA 20 Slope strictly positive (`EMA20 > EMA20[2]`) | EMA 20 Slope strictly negative (`EMA20 < EMA20[2]`) |
| **HTF Alignment** | 15M setups require 1H EMA20 > EMA50; 1H setups require Daily EMA20 > EMA50 | 15M setups require 1H EMA20 < EMA50; 1H setups require Daily EMA20 < EMA50 |
| **RSI Momentum Filter** | `40.0 ≤ RSI(14) ≤ 80.0` (Optimised Momentum Zone) | `20.0 ≤ RSI(14) ≤ 60.0` (Optimised Momentum Zone) |
| **ADX Regime Filter** | **ADX < 20.0 OR ADX ≥ 30.0 ONLY** — ADX 20–30 hard-blocked (−0.09R expectancy) | **ADX < 20.0 OR ADX ≥ 30.0 ONLY** — ADX 20–30 hard-blocked |
| **Candle Body Guard** | 15M: breakout candle must be >55% solid body (no wick-rejection entries) | 15M: breakout candle must be >55% solid body |
| **Session Filter** | London & NY liquidity hours (05:00–21:00 UTC). **London/NY Overlap 12:00–16:00 UTC hard-blocked** (33.3% WR, −0.218R) | Same session rules |
| **Origin Order Block** | Lowest price of the last down-candle before displacement | Highest price of the last up-candle before displacement |
| **Stop Loss Formula** | `Entry − max(MinSL, min(MaxSL, Entry − (OB_Low − 0.5×ATR)))` | `Entry + max(MinSL, min(MaxSL, (OB_High + 0.5×ATR) − Entry))` |
| **Take Profit Target** | **ICT Buy-Side Liquidity (BSL):** Nearest un-swept 5-bar fractal swing high (1.5R–2.5R). Setup **rejected** if no structural pool qualifies. | **ICT Sell-Side Liquidity (SSL):** Nearest un-swept 5-bar fractal swing low (1.5R–2.5R). Setup rejected if no structural pool qualifies. |
| **Wide SL Penalty** | Forex SL > 30 pips: −5 signal score points (ranking penalty, not filter) | Same |
| **Break-Even Rule** | **SL advanced to Entry + 1 pip once floating profit reaches +1.0R** | **SL advanced to Entry − 1 pip once floating profit reaches +1.0R** |
| **Intraday Time-Stop** | 20-EMA Invalidation: early exit if held ≥ 24h (or ≥ 12h for 15M) & closes opposite 20-EMA | Same |
| **Pending Order Watchdog** | Auto-cancels unfilled limit orders after 2h (15M) / 4h (1H) | Same |
| **Single-Trade Lock** | Strictly **1 position per pair**; duplicate signals blocked | Same |

---

## 3. Forensic Audit Results & Verified Performance (v2 — October 2026)

### Forensic Audit: V1 vs V2 System Comparison (235 Historical Trades)

| Performance Metric | V1 Baseline (All Filters Off) | V2 Full Universe | V2 Production Core (EURUSD, USDCAD, XAUUSD) |
| :--- | :---: | :---: | :---: |
| **Total Trades** | 235 | 111 | **44** |
| **Win Rate** | 46.4% | 54.9% | **70.5%** |
| **Gross Expectancy** | +0.111R | +0.562R | **+0.978R** |
| **Net Expectancy (post-cost)** | **−0.008R (break-even)** | +0.443R | **+0.859R** |
| **Profit Factor** | 1.24 | 2.42 | **4.91** |
| **Max Drawdown** | 15.96R | 6.25R | **2.00R** |
| **Max Consecutive Losses** | 5 | 6 | **2** |
| **BE Exits (Capital Saved)** | 0 | 6 | **2** |

### Primary Performance Drivers (V1 → V2)

| Improvement | Net R Contribution |
| :--- | :---: |
| **Model F Structural TP** (5-bar fractal BSL/SSL vs fixed 1.75R) | **+59.54R** on wins |
| **London/NY Overlap Block** (12–16 UTC) | **+13.05R** saved |
| **ADX 20–30 Filter** (blocked 87 losing-regime trades) | **+8.72R** saved |
| **Break-Even at +1.0R** (6 large-MFE trades converted from loss → 0R) | **+5.96R** saved |

### Asset-Level Performance

| Symbol | V2 Trades | V2 Win Rate | V2 Expectancy | V2 PF | Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **USDCAD** | 18 | 83.3% | +1.280R | 8.68 | ✅ Core universe |
| **EURUSD** | 23 | 60.9% | +0.761R | 3.50 | ✅ Core universe |
| **XAUUSD** | 3 | 66.7% | +0.833R | 3.50 | ✅ Core universe |
| GBPUSD | 21 | 42.9% | +0.226R | 1.43 | ❌ Excluded (marginal) |
| USDJPY | 24 | 45.8% | +0.334R | 1.73 | ❌ Excluded (BoJ risk) |
| USDCHF | 22 | 45.5% | +0.301R | 1.60 | ❌ Excluded (EURUSD corr.) |

---

## 4. Interactive Telegram Terminal Commands

The Telegram Bot acts as an institutional mobile cockpit. All messages use clean indices and compact 18-character dividers (`━━━━━━━━━━━━━━━━━━`) engineered for mobile screens:

| Command | Action & Output Description |
| :--- | :--- |
| `/radar` | **Live Market Radar:** Shows floating PnL, Entry, SL, TP, Break-Even status for active trades; breakout proximity & ADX regime for surveillance pairs. |
| `/prices` | **Market Quotes:** Displays clean, real-time spot prices across the Core Alpha Triad (`XAUUSD`, `EURUSD`, `USDCAD`). |
| `/history` | **Trade Journal Ledger:** Filterable record of active and closed trades. Supports syntax like `/history EURUSD 7d`. |
| `/performance` | **Forward Performance Metrics:** Calculates Win Rate, Expectancy, Pips, R, and Profit Factor strictly from live forward executions from 2026-10-02 onwards. |
| `/strategy` | **System Specifications:** Full quantitative rulebook including ADX filter, Donchian, EMA, RSI, ICT BSL/SSL, Break-Even, session rules, and Order Block formulas. |
| `/status` | **Engine Architecture Health:** Cloud edge uptime, active locked positions, ADX regime status, and serverless connection state. |

---

## 5. Repository File Structure

```
c:\trading-bot\
├── .github/
│   └── workflows/
│       └── scanner.yml              # GitHub Actions 24/7 cron runner (every 15 min)
├── app/                             # Core FastAPI webhook and routing service
├── core/                            # Post-mortem trade diagnostic engine
├── data/                            # Persistent pattern journals and volume benchmarks
├── docs/
│   ├── Institutional_Trading_Engine_Whitepaper.md   # Executive Architecture Whitepaper
│   ├── Institutional_Trading_Engine_Whitepaper.html # Interactive HTML Whitepaper
│   └── Institutional_Trading_Engine_Whitepaper.pdf  # Publication-grade vector PDF
├── journals/                        # Post-mortem trade journals (Volumes 1–100)
├── pinescript/
│   ├── adaptive_trend_momentum_indicator.pine       # TradingView v6 Indicator + Alerts
│   └── adaptive_trend_momentum_breakout.pine        # TradingView v6 Strategy Backtest
├── scripts/
│   ├── forward_test_tracker.py                      # Out-of-sample forward validation tracker
│   ├── audit_last_month_solutions.py                # Exit optimization benchmark
│   ├── audit_last_month_trades_deep.py              # MFE/MAE duration trade audit
│   ├── generate_whitepaper_pdf.py                   # ReportLab publication PDF generator
│   ├── simulate_prop_firm_5k.py                     # $5k prop firm challenge simulation
│   └── simulate_prop_firm_phases.py                 # Multi-phase prop firm evaluation
├── tests/
│   ├── test_market_scanner.py                       # Market scanner unit tests (41 passing)
│   ├── test_post_mortem.py                          # Diagnostic test cases
│   └── test_telegram.py                             # Telegram alert unit tests
├── cloudflare_worker.js             # 24/7 Edge gateway, Telegram webhook & command router
├── market_scanner.py                # Standalone Python scanner & trade lifecycle monitor
├── trade_records.json               # Permanent live forward trade ledger
├── requirements.txt                 # Production Python dependencies
├── pytest.ini                       # Test runner configuration
└── README.md                        # Comprehensive project documentation
```

---

## 6. Deployment & Operations

### 1. Cloudflare Worker Edge (Interactive Telegram Bot)
1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com) ➔ **Workers & Pages**.
2. Select your Worker (`tradingview-telegram-relay`).
3. Paste the contents of `cloudflare_worker.js` and click **Deploy**.
4. Set Telegram Webhook:
   ```bash
   curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook" \
        -H "Content-Type: application/json" \
        -d '{"url": "https://<YOUR_WORKER_URL>/"}'
   ```

### 2. GitHub Actions Cloud Scanner (24/7 Surveillance)
1. Ensure the repo has secrets configured in **Settings ➔ Secrets and variables ➔ Actions**:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
2. The workflow in `.github/workflows/scanner.yml` runs automatically every 15 minutes during market hours (`*/15 5-21 * * 1-5`).

> **Scheduling Note:** GitHub Actions has typical runner queue delays of 1–4 minutes. The freshness guard allows 12 minutes on 15M signals and 30 minutes on 1H signals, accommodating these delays. Only extreme runner congestion (>12 min delay) can cause a 15M signal to be silently skipped.

### 3. Local Development & Testing
```bash
# Clone and setup virtual environment
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\Activate.ps1 on Windows

# Install dependencies
pip install -r requirements.txt

# Run full test suite (41 unit tests)
pytest

# Execute manual market scan cycle
python market_scanner.py

# Run in continuous 24/7 loop (local alternative to GitHub Actions)
python market_scanner.py --loop

# Check out-of-sample forward validation metrics
python scripts/forward_test_tracker.py --markdown
```

---

## 7. Forward Validation Protocol

The strategy ruleset is **frozen** from 2026-10-02. All new live trades after this date feed the out-of-sample forward validation tracker.

Run the tracker at any time:
```bash
python scripts/forward_test_tracker.py          # Terminal summary
python scripts/forward_test_tracker.py --markdown  # Markdown table
python scripts/forward_test_tracker.py --json   # JSON for dashboards
```

| Metric | v1 Baseline | v2 Target |
| :--- | :---: | :---: |
| Win Rate | 46.4% | ≥ 50% |
| Expectancy | +0.111R | ≥ +0.20R |
| Profit Factor | 1.24 | ≥ 1.40 |
| Max Drawdown | 15.96R | < 12.0R |
| Net Expectancy (post-cost) | −0.008R | > 0.00R |

> ⚠️ **Rule**: No strategy parameters, filters, or thresholds will be modified until the out-of-sample forward sample reaches N ≥ 50 trades. Modifying rules based on individual live trades constitutes iterative curve-fitting.

---

## 8. Institutional Whitepaper

A venture-capital grade publication whitepaper detailing the mathematical formulas, architectural specifications, and execution invariants is available in:
📄 [`docs/Institutional_Trading_Engine_Whitepaper.pdf`](docs/Institutional_Trading_Engine_Whitepaper.pdf)
