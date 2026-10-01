# 24/7 Institutional Algorithmic Signal Engine & Trade Journal

![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue?logo=python)
![Cloudflare Workers](https://img.shields.io/badge/Cloudflare_Workers-Edge_Serverless-orange?logo=cloudflare)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Automated_24%2F7_Cron-black?logo=githubactions)
![Telegram Bot API](https://img.shields.io/badge/Telegram_Bot-Interactive_Terminal-2CA5E0?logo=telegram)
![License](https://img.shields.io/badge/License-Proprietary-red)
![Forward Testing](https://img.shields.io/badge/Forward_Testing-2026--09--28-emerald)
![Test Suite](https://img.shields.io/badge/Tests-41%20Passing-brightgreen)

An institutional-grade, **100% free, 24/7 automated algorithmic trading system** optimized for the **Core Alpha Triad**: Spot Gold (`XAUUSD`), `EURUSD`, and `USDCAD`.

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
    │  • ICT Liquidity Targeting│                                │
    │  • London/NY Session Guard│                                │
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
    │ • Order Filled / Expired │                   │ • /prices  • /performance│
    │ • TP / SL / Invalidation │                   │ • /status  • /strategy   │
    └─────────────┬────────────┘                   └─────────────┬────────────┘
                  │                                              │
                  ▼                                              ▼
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                      User Mobile & Desktop Client                       │
    │                 Institutional Interactive Terminal UI                   │
    └─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Quantitative Strategy: Structural Breakout & ICT Liquidity Engine

The strategy is a systematic, non-discretionary momentum model designed to capture sustained market displacements while eliminating false breakout traps and lingering consolidation:

| Strategy Dimension | Bullish Execution (LONG) | Bearish Execution (SHORT) |
| :--- | :--- | :--- |
| **Asset Universe** | `XAUUSD`, `EURUSD`, `USDCAD` (Core Alpha Triad) | `XAUUSD`, `EURUSD`, `USDCAD` (Core Alpha Triad) |
| **Breakout Trigger** | Confirmed close above Donchian High (10-bar Gold, 15-bar Forex) | Confirmed close below Donchian Low (10-bar Gold, 15-bar Forex) |
| **Trend Alignment** | `Close > EMA 50` & `EMA 20 > EMA 50` | `Close < EMA 50` & `EMA 20 < EMA 50` |
| **Velocity Vector** | EMA 20 Slope strictly positive (`EMA20 > EMA20[2]`) | EMA 20 Slope strictly negative (`EMA20 < EMA20[2]`) |
| **RSI Momentum Filter** | `40.0 ≤ RSI(14) ≤ 80.0` (Optimized Momentum Zone) | `20.0 ≤ RSI(14) ≤ 60.0` (Optimized Momentum Zone) |
| **Session Filter** | Frankfurt, London & NY liquidity hours (`05:00 to 21:00 UTC`) | Frankfurt, London & NY liquidity hours (`05:00 to 21:00 UTC`) |
| **Origin Order Block** | Lowest price of the last down-candle before displacement | Highest price of the last up-candle before displacement |
| **Stop Loss Formula** | `Entry - max(MinSL, min(MaxSL, Entry - (OB_Low - 0.5*ATR)))` | `Entry + max(MinSL, min(MaxSL, (OB_High + 0.5*ATR) - Entry))` |
| **Take Profit Target** | **ICT Buy-Side Liquidity (BSL):** Prior swing high pullback pools (1.0R to 2.5R) | **ICT Sell-Side Liquidity (SSL):** Prior swing low pullback pools (1.0R to 2.5R) |
| **Intraday Time-Stop** | **20-EMA Invalidation:** Closes early if held ≥ 24h (or 12h for 15M) and closes below 20-EMA | **20-EMA Invalidation:** Closes early if held ≥ 24h (or 12h for 15M) and closes above 20-EMA |
| **Pending Order Watchdog** | Auto-cancels unfilled limit orders after 2 hours (15M) or 4 hours (1H) | Auto-cancels unfilled limit orders after 2 hours (15M) or 4 hours (1H) |
| **Single-Trade Lock** | Strictly **1 position per pair**; duplicate signals blocked | Strictly **1 position per pair**; duplicate signals blocked |

---

## 3. Verified Performance & Prop Firm Benchmarks

### Last Month Audit (Optimized High-Frequency Model)
- **Total Trades Taken:** 35 (+30% trade frequency boost, ~1.2 trades/day)
- **Win Rate:** **57.1%** (20W / 15L)
- **Net Return:** **+13.39 R** (+13.39% on 1.0% risk)
- **Max Overall Drawdown:** **1.69%** (Well within the 7.0% prop firm threshold)
- **Max Daily Loss:** **1.14%** (Well within the 3.0% daily limit)
- **Profit Factor:** **2.23**

### 2-Year Historical Portfolio Backtest (2024 – 2026)
- **Total Trades:** 869 (+26% more trades, 36 trades/month across triad)
- **Win Rate:** **43.4%**
- **Net Realized Return:** **+88.61 R** (+80% profit increase over previous baseline)
- **Max Portfolio Drawdown:** **4.82%** (at 0.50% risk per trade; 9.64% at 1.0% risk)
- **Profit Factor:** **1.23**
- **Average Holding Time:** 21.4 hours

### $5,000 Prop Firm Challenge Simulation
- **Daily Loss Limit (3.0% = $150):** 100% Passed (Max daily drop observed was 1.14%).
- **Overall Max Drawdown (7.0% = $350):** 100% Passed (Peak drawdown observed was 3.52%).
- **Phase 1 Target (+8.0% = +$400):** **Passed at Trade #15 in ~2.5 weeks**.
- **Net Payout (80% profit split):** **$434.00** generated on funded capital in 30 days.

---

## 4. Interactive Telegram Terminal Commands

The Telegram Bot acts as an institutional mobile cockpit. All messages use clean indices and compact 18-character dividers (`━━━━━━━━━━━━━━━━━━`) engineered for mobile screens:

| Command | Action & Output Description |
| :--- | :--- |
| `/radar` | **Live Market Radar:** Shows floating PnL, Entry, SL, and TP for active trades; displays breakout proximity and RSI guard status for surveillance pairs. |
| `/prices` | **Market Quotes:** Displays clean, real-time spot prices across the Core Alpha Triad (`XAUUSD`, `EURUSD`, `USDCAD`). |
| `/history` | **Trade Journal Ledger:** Filterable record of active and closed trades. Supports syntax like `/history EURUSD 7d`. |
| `/performance` | **Forward Performance Metrics:** Calculates Win Rate %, Realized Pips, Realized R, and Profit Factor strictly from live forward executions. |
| `/strategy` | **System Specifications:** Full quantitative rulebook including Donchian, EMA, RSI sweet-spot, ICT BSL/SSL, and Order Block formulas. |
| `/status` | **Engine Architecture Health:** Cloud edge uptime, active locked positions, and serverless connection state. |

---

## 5. Repository File Structure

```
c:\trading-bot\
├── .github/
│   └── workflows/
│       └── scanner.yml           # GitHub Actions 24/7 cron runner (every 15 min)
├── app/                          # Core FastAPI webhook and routing service
├── core/                         # Post-mortem trade diagnostic engine
├── data/                         # Persistent pattern journals and volume benchmarks
├── docs/
│   ├── Institutional_Trading_Engine_Whitepaper.md   # Executive Architecture Whitepaper
│   ├── Institutional_Trading_Engine_Whitepaper.html # Interactive HTML Whitepaper
│   └── Institutional_Trading_Engine_Whitepaper.pdf  # Publication-grade vector PDF
├── journals/                     # Post-mortem trade journals (Volumes 1-100)
├── pinescript/
│   ├── adaptive_trend_momentum_indicator.pine       # TradingView v6 Indicator + Alerts
│   └── adaptive_trend_momentum_breakout.pine        # TradingView v6 Strategy Backtest
├── scripts/
│   ├── audit_last_month_solutions.py                # Exit optimization benchmark
│   ├── audit_last_month_trades_deep.py              # MFE/MAE duration trade audit
│   ├── generate_whitepaper_pdf.py                   # ReportLab publication PDF generator
│   ├── simulate_prop_firm_5k.py                     # $5k prop firm challenge simulation
│   ├── simulate_prop_firm_phases.py                 # Multi-phase prop firm evaluation
│   └── simulate_prop_firm_timeline.py               # 2-year timeline payout simulator
├── tests/
│   ├── test_market_scanner.py                       # Market scanner unit tests
│   ├── test_post_mortem.py                          # Diagnostic test cases
│   └── test_telegram.py                             # Telegram alert unit tests
├── cloudflare_worker.js          # 24/7 Edge gateway, Telegram webhook & command router
├── market_scanner.py             # Standalone Python scanner & trade lifecycle monitor
├── trade_records.json            # Permanent live forward trade ledger
├── requirements.txt              # Production Python dependencies
├── pytest.ini                    # Test runner configuration
└── README.md                     # Comprehensive project documentation
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
2. The workflow in `.github/workflows/scanner.yml` runs automatically every 15 minutes during market hours (`*/15 * * * 1-5`).

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
```

---

## 7. Institutional Whitepaper

A venture-capital grade publication whitepaper detailing the mathematical formulas, architectural specifications, and execution invariants is available in:
📄 [`docs/Institutional_Trading_Engine_Whitepaper.pdf`](docs/Institutional_Trading_Engine_Whitepaper.pdf)
