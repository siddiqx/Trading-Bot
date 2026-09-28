# 24/7 Institutional Algorithmic Signal Engine & Trade Journal

![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue?logo=python)
![Cloudflare Workers](https://img.shields.io/badge/Cloudflare_Workers-Edge_Serverless-orange?logo=cloudflare)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Automated_24%2F7_Cron-black?logo=githubactions)
![Telegram Bot API](https://img.shields.io/badge/Telegram_Bot-Interactive_Terminal-2CA5E0?logo=telegram)
![License](https://img.shields.io/badge/License-Proprietary-red)
![Forward Testing](https://img.shields.io/badge/Forward_Testing-2026--09--28-emerald)

An institutional-grade, **100% free, 24/7 automated algorithmic trading system** designed for Forex Majors (`EUR/USD`, `USD/JPY`, `USD/CAD`, `USD/CHF`, `AUD/USD`) and Spot Gold (`XAU/USD`). 

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
    │  • 20-Bar Donchian       │                                 │
    │  • EMA 20/50 Slope       │                                 │
    │  • Anti-Exhaustion RSI   │                                 │
    │  • Origin Order Block SL │                                 │
    │  • Active TP/SL Monitor  │                                 │
    │  • Pair-Lock Enforcement │                                 │
    └─────────────┬────────────┘                                 │
                  │                                              │
                  ├─────────────────── Sync Trades ──────────────┤
                  │                   (POST /sync_trades)        │
                  │                                              │
                  ▼                                              ▼
    ┌──────────────────────────┐                   ┌──────────────────────────┐
    │ Telegram Bot Push Alerts │                   │ Telegram Webhook Router  │
    │ • New Confirmed Breakout │                   │ • /radar   • /history    │
    │ • TP / SL Target Hit     │                   │ • /prices  • /performance│
    └─────────────┬────────────┘                   │ • /status  • /strategy   │
                  │                                └─────────────┬────────────┘
                  ▼                                              ▼
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                      User Mobile & Desktop Client                       │
    │                 Institutional Interactive Terminal UI                   │
    └─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Quantitative Strategy: Structural Breakout & Order Block Engine

The strategy is a systematic, non-discretionary momentum model designed to capture sustained market displacements while eliminating false breakout churn:

| Strategy Dimension | Bullish Execution (LONG) | Bearish Execution (SHORT) |
| :--- | :--- | :--- |
| **Breakout Trigger** | Confirmed close above 20-period Donchian High | Confirmed close below 20-period Donchian Low |
| **Trend Alignment** | `Close > EMA 50` & `EMA 20 > EMA 50` | `Close < EMA 50` & `EMA 20 < EMA 50` |
| **Velocity Vector** | EMA 20 Slope strictly positive (`EMA20 > EMA20[1]`) | EMA 20 Slope strictly negative (`EMA20 < EMA20[1]`) |
| **RSI Momentum Filter** | `45.0 ≤ RSI(14) ≤ 75.0` (Anti-Overbought Guard) | `25.0 ≤ RSI(14) ≤ 55.0` (Anti-Oversold Guard) |
| **Origin Order Block** | Lowest price of the last down-candle before displacement | Highest price of the last up-candle before displacement |
| **Stop Loss Formula** | `Entry - max(18p, min(60p, Entry - (OB_Low - 0.5*ATR)))` | `Entry + max(18p, min(60p, (OB_High + 0.5*ATR) - Entry))` |
| **Target Matrix** | Fixed **1 : 1.75 Risk-to-Reward Ratio** | Fixed **1 : 1.75 Risk-to-Reward Ratio** |
| **Risk Allocation** | **1.0% Equity** per position | **1.0% Equity** per position |
| **Single-Trade Lock** | Strictly **1 position per pair**; duplicate signals blocked | Strictly **1 position per pair**; duplicate signals blocked |

---

## 3. Interactive Telegram Terminal Commands

The Telegram Bot acts as an institutional mobile cockpit. All messages use **unbracketed numbered indices** (`1. `, `2. `) and **compact 18-character dividers** (`━━━━━━━━━━━━━━━━━━`) engineered for narrow mobile screens:

| Command | Action & Output Description |
| :--- | :--- |
| `/radar` | **Live Market Radar:** Shows floating PnL, Entry, SL, and TP for active trades; displays breakout proximity and RSI guard status for surveillance pairs. |
| `/prices` | **Market Quotes:** Displays clean, real-time spot prices across all 6 monitored assets. |
| `/history` | **Trade Journal Ledger:** Filterable record of active and closed trades. Supports syntax like `/history EURUSD 7d`. |
| `/performance` | **Forward Performance Metrics:** Calculates Win Rate %, Realized Pips, Realized R, and Profit Factor strictly from live forward executions. |
| `/strategy` | **System Specifications:** Full quantitative rulebook including Donchian, EMA, RSI sweet-spot, and Order Block formulas. |
| `/status` | **Engine Architecture Health:** Cloud edge uptime, active locked positions, and serverless connection state. |

---

## 4. Forward Trade Ledger Mechanics

Starting **September 28, 2026**, every signal triggered by the engine is tracked continuously until resolution:
1. **Trade Entry:** Logged in `trade_records.json` with unique ID, Entry, SL, TP, Pips, and UTC timestamp.
2. **Surveillance Lock:** The pair is locked; breakout scans on that pair are suppressed to eliminate duplicate entries.
3. **Exit Monitoring:** On every scan cycle, candle extremes are evaluated against target bounds:
   - `High >= Take Profit` (Long) or `Low <= Take Profit` (Short) ➔ **TARGET REACHED (WIN)**.
   - `Low <= Stop Loss` (Long) or `High >= Stop Loss` (Short) ➔ **STRUCTURAL EXIT (LOSS)**.
4. **Resolution Alert & Ledger Archival:** An exit notification is dispatched to Telegram, the trade is moved to `completed_trades`, and performance metrics are updated.

---

## 5. Repository File Structure

```
c:\trading-bot\
├── .github/
│   └── workflows/
│       └── scanner.yml           # GitHub Actions 24/7 cron runner (every 15 min)
├── docs/
│   └── Institutional_Trading_Engine_Whitepaper.pdf # Publication-grade VC whitepaper
├── pinescript/
│   ├── adaptive_trend_momentum_indicator.pine     # TradingView v6 Indicator + Alerts
│   └── adaptive_trend_momentum_breakout.pine      # TradingView v6 Strategy Backtest
├── scripts/
│   ├── generate_whitepaper_pdf.py                 # ReportLab publication PDF generator
│   └── test_local_webhook.ps1                     # Local test script
├── tests/
│   └── test_market_scanner.py                     # Pytest suite (25 test cases)
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
2. The workflow in `.github/workflows/scanner.yml` runs automatically every 15 minutes during Forex market hours (`*/15 * * * 1-5`).

### 3. Local Development & Testing
```bash
# Clone and setup virtual environment
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\Activate.ps1 on Windows

# Install dependencies
pip install -r requirements.txt

# Run full test suite
pytest

# Execute manual market scan cycle
python market_scanner.py
```

---

## 7. Institutional Whitepaper

A venture-capital grade publication whitepaper detailing the mathematical formulas, architectural specifications, and execution invariants is available in:
📄 [`docs/Institutional_Trading_Engine_Whitepaper.pdf`](docs/Institutional_Trading_Engine_Whitepaper.pdf)
