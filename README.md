# 24/7 Institutional Algorithmic Signal Engine & Trade Journal

![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue?logo=python)
![Cloudflare Workers](https://img.shields.io/badge/Cloudflare_Workers-Edge_Serverless-orange?logo=cloudflare)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Automated_24%2F7_Cron-black?logo=githubactions)
![Telegram Bot API](https://img.shields.io/badge/Telegram_Bot-Interactive_Terminal-2CA5E0?logo=telegram)
![cTrader Open API](https://img.shields.io/badge/cTrader-Automated_Execution-green?logo=tradingview)
![License](https://img.shields.io/badge/License-Proprietary-red)
![System Version](https://img.shields.io/badge/System-v3.3.0--Production-success)
![Test Suite](https://img.shields.io/badge/Tests-159%20Passing-brightgreen)

An institutional-grade, **24/7 autonomous systematic algorithmic trading bot, trade journal, and execution gateway** engineered for institutional Forex markets and Spot Gold commodity trading.

The engine operates serverless in the cloud with **zero hardware dependency** (runs 24/7 without requiring a home computer or paid VPS) and **zero paid SaaS subscriptions** (eliminates TradingView Premium subscriptions and third-party signal relays).

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
    │ Dual Production Engines  │                                 │
    │ 1. Forex Scanner (15M)   │                                 │
    │    market_scanner.py     │                                 │
    │    • 5 Institutional FX  │                                 │
    │    • 1H 7-Currency CCRS  │                                 │
    │    • Forex Factory News  │                                 │
    │                          │                                 │
    │ 2. Gold Satellite (1H)   │                                 │
    │    market_scanner_gold.py│                                 │
    │    • Spot Gold (XAUUSD)  │                                 │
    │    • CCRS USD Factor     │                                 │
    │    • Dynamic ATR Stops   │                                 │
    │    • Correlation Interlock                                 │
    └─────────────┬────────────┘                                 │
                  │                                              │
                  ├─────────────────── Sync Ledgers ─────────────┤
                  │                   (POST /sync_trades)        │
                  │                                              │
                  ▼                                              ▼
    ┌──────────────────────────┐                   ┌──────────────────────────┐
    │  Outbound Notifications  │                   │ Telegram Webhook Router  │
    │  • Telegram Push Alerts  │                   │ • /radar   • /history    │
    │  • cTrader Open API      │                   │ • /prices  • /performance│
    │    Automated Execution   │                   │ • /status  • /strategy   │
    │    (TLS Protobuf Client) │                   │ • /active                │
    └─────────────┬────────────┘                   └─────────────┬────────────┘
                  │                                              │
                  ▼                                              ▼
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                      Institutional Trader Cockpit                       │
    │           Real-Time Signals, Risk Management & Trade Ledger             │
    └─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Quantitative Strategy Engine (v3.3.0 Production)

The system deploys a decoupled, multi-asset quantitative strategy that separates **Macro Order Flow Regime Identification (1H)** from **Precision Execution Timing (15M & 1H)**.

### A. Core Institutional Forex Engine (`market_scanner.py`)
* **Monitored Universe (5 Active Pairs):** `EURUSD`, `USDCAD`, `GBPUSD`, `USDCHF`, `AUDUSD`.
* **USDJPY De-whitelisted:** Paused due to empirical 2026 negative expectancy (20% live win rate, PF 0.38) caused by Ministry of Finance / Bank of Japan intervention whipsaws. USDJPY quotes are retained solely for synthetic currency basket mathematics.
* **Macro Factor Model (1H CCRS):** Decomposes 6 major Forex pairs into 7 pure currency strength indices (`EUR`, `GBP`, `AUD`, `JPY`, `CAD`, `CHF`, `USD`). Normalizes 120-hour returns across a 200-hour rolling volatility window into Z-scores. Trades active macro momentum regimes where pairwise spread divergence $|D| \ge 1.75\sigma$.
* **Precision Execution (15M):** Evaluates completed 15M candle bars for 20-EMA pullback rejections and 10-bar Donchian / fractal liquidity sweeps aligned with the 1H macro bias.
* **Dynamic Exits:** Stop Loss dynamically anchored to 14-period ATR ($20.0 - 25.0$ pips, canonical $22.0$ pips). Take Profit fixed at $1:1.50$ Risk-to-Reward ratio ($30.0 - 37.5$ pips, canonical $33.0 - 35.0$ pips).
* **Volatility Cushion Trailing:**
  - **Tier 1 (+1.20R):** Halves risk by advancing SL to $-0.50$R of entry.
  - **Tier 2 (+1.50R):** Locks in $+0.50$R guaranteed profit and extends runner target to $+2.00$R.

### B. Dedicated Gold Satellite Engine (`satellite/market_scanner_gold.py`)
* **Asset:** Spot Gold (`XAUUSD` / front-month futures `GC=F`).
* **Contract Geometry:** 1 Standard Lot = 100 Troy Ounces ($1.00 move in Gold price = $100.00 USD per standard lot). Minimum trade = 0.01 lot (1 Troy Ounce = $1.00/point).
* **Macro Factor (1H CCRS Single-Factor):** Computes isolated USD basket factor $Z_{\text{USD}}$. Macro flow is established when $|Z_{\text{USD}}| \ge 1.25\sigma$ (statistically calibrated to match the $1.75\sigma$ pairwise Forex threshold: $1.25 \times \sqrt{2} \approx 1.76\sigma$).
  - $Z_{\text{USD}} \le -1.25\sigma$ $\implies$ Institutional USD Weakness $\implies$ **Long Gold (BUY)**.
  - $Z_{\text{USD}} \ge +1.25\sigma$ $\implies$ Institutional USD Strength $\implies$ **Short Gold (SELL)**.
* **Precision Triggers (1H):** Confirmed 1H 20-EMA retest rejection or 10-bar Donchian liquidity sweep on closed 1H bars.
* **Dynamic Volatility Stops:** $2.0\times$ 14-period 1H ATR stop bounded strictly between $\$20.00$ and $\$35.00$/oz ($1:1.50$ base TP at $\$30.00 - \$52.50$/oz).

---

## 3. Institutional Risk Management & Prop Firm Controls

The system was engineered from the ground up to comply with institutional prop firm challenge rules (FTMO, FundedNext, Alpha Capital, 5%ers):

| Risk Control | Implementation | Purpose |
| :--- | :--- | :--- |
| **Dynamic Lot Sizing** | `core/instrument_validator.py` & `satellite/gold_validator.py` | Automatically computes exact position size so monetary risk never exceeds budget (e.g. 0.50% = $25 on $5k, 1.00% = $250 on $25k). Conservative lot flooring prevents over-budget rounding. |
| **USD Correlation Interlock** | `MAX_CONCURRENT_USD_EXPOSURE = 2` | Strictly limits simultaneous net USD exposure to 2 positions across **both** Forex and Gold ledgers, preventing multi-pair news cascade wipeouts. |
| **Forex Factory News Filter** | `core/news_filter.py` | Automatically suppresses fresh entries 30 minutes before and after high-impact (Red Folder) economic events. |
| **Daily Loss Circuit Breaker** | `DAILY_LOSS_CIRCUIT_BREAKER = 2` | Halts fresh entries for the day if 2 stop-outs occur or daily loss exceeds $-2.00$R, guaranteeing immunity from prop firm 4–5% daily drawdown limits. |
| **Rollover Blackout** | 20:30 – 22:30 UTC (Gold) & 21:00 – 23:00 UTC (Forex) | Halts entries during illiquid interbank rollover when spreads widen drastically. |
| **Friday Weekend Cutoff** | 12:00 UTC (Forex) & 16:00 UTC (Gold) | Blocks fresh entries ahead of the weekend and exits remaining open Gold positions flat to eliminate 48-hour gap risk. |
| **Monday London Window** | 06:00 – 12:00 UTC strictly | Prohibits entries during erratic Asian opens and low-volume NY afternoon drift. |
| **Post-Loss Cooldown** | 60 Minutes | Enforces mandatory 1-hour timeout following a stop-out to prevent revenge trading. |

---

## 4. Interactive Telegram Terminal

The Telegram bot functions as a 24/7 mobile cockpit powered by the Cloudflare Worker edge router:

| Command | Action & Output Description |
| :--- | :--- |
| `/radar` | **Live Market Radar:** Shows floating PnL, Entry, SL, TP, and trailing stage for all active positions, plus CCRS macro regimes across the universe. |
| `/prices` | **Institutional Quotes:** Real-time spot prices across EURUSD, USDCAD, GBPUSD, USDCHF, AUDUSD, and XAUUSD. |
| `/history` | **Trade Journal Ledger:** Filterable record of active and closed trades. |
| `/performance` | **Forward Performance Metrics:** Calculates Win Rate, Expectancy, Pips, R-multiples, and Profit Factor from verified live forward trades. |
| `/strategy` | **System Specifications:** Complete active quantitative rulebook and parameter matrix. |
| `/status` | **System Health Monitor:** Edge uptime, active trade count, circuit breaker status, and broker connection state. |
| `/active` | **Immediate Active Trade Status:** Summary of currently floating positions with entry, SL, TP, and R-multiple excursion. |

---

## 5. Repository File Structure

```
trading-bot/
├── .github/
│   └── workflows/
│       └── scanner.yml              # GitHub Actions 24/7 cron runner (every 15 min)
├── app/                             # Secondary / Legacy FastAPI webhook service
├── core/                            # Core quantitative & execution modules
│   ├── config.py                    # Authoritative Forex configuration & single source of truth
│   ├── ctrader_executor.py          # cTrader Open API TLS Protobuf execution engine
│   ├── instrument_validator.py      # Multi-currency pip math & position sizing
│   ├── news_filter.py               # Forex Factory real-time economic calendar filter
│   └── post_mortem.py               # Trade excursion diagnostics (MFE/MAE tracking)
├── data/                            # Historical data, patterns, and trade ledgers
│   ├── gold_trade_records.json      # Gold Satellite active & historical trade ledger
│   └── patterns/                    # Trade volume benchmarks and pattern journals
├── docs/                            # Deep institutional documentation & strategy specs
│   ├── BACKTESTING_METHODOLOGY.md   # Rigorous look-ahead-free backtest framework
│   ├── DEVELOPMENT_ROADMAP.md       # Development history and milestone tracking
│   ├── KNOWN_ISSUES.md              # Complete forensic defect log & remediation history
│   ├── LOT_SIZE_GUIDE.md            # Account sizing table ($100 to $100,000 accounts)
│   ├── PROJECT_AUDIT.md             # System audit & codebase verification
│   ├── PROJECT_CONTEXT.md           # Authoritative agent context & architecture map
│   └── TRADING_STRATEGY_SPEC.md     # Mathematical & algorithmic strategy rulebook
├── satellite/                       # Dedicated Isolated Gold Satellite Engine
│   ├── gold_config.py               # Authoritative Gold contract & exit configuration
│   ├── gold_validator.py            # Gold position sizing & correlation interlock
│   └── market_scanner_gold.py       # Standalone 24/7 Gold scanning & trailing engine
├── scripts/                         # Research, backtesting & simulation scripts
│   ├── forward_test_tracker.py      # Out-of-sample forward validation tracker
│   ├── run_canonical_backtest.py    # Walk-forward 70/30 backtest engine
│   └── simulate_prop_firm_5k.py     # Prop firm challenge Monte Carlo simulation
├── tests/                           # Complete automated unit test suite (159 tests)
│   ├── test_canonical_strategy.py   # CCRS factor matrix & regime tests
│   ├── test_ctrader_executor.py     # cTrader Protobuf message & TLS client tests
│   ├── test_gold_satellite.py       # Gold contract geometry, sizing & interlock tests
│   ├── test_instrument_validator.py # Multi-currency pip value & lot sizing tests
│   ├── test_market_scanner.py       # Forex scanner cycle & signal tests
│   ├── test_news_filter.py          # Economic calendar parsing & blackout tests
│   └── test_position_sizing.py      # Prop firm budget & risk ceiling tests
├── cloudflare_worker.js             # Global Edge V8 Worker & Telegram webhook router
├── market_scanner.py                # Standalone 24/7 Forex Market Scanner Engine
├── trade_records.json               # Atomic live Forex trade ledger & journal
├── requirements.txt                 # Production Python dependencies
└── README.md                        # Primary project documentation
```

---

## 6. Deployment & Operations

### A. 24/7 Cloud Automated Execution (GitHub Actions)
The bot executes autonomously every 15 minutes during Forex market hours via `.github/workflows/scanner.yml`.

To deploy:
1. Fork or clone this repository to your GitHub account.
2. In your GitHub repository, navigate to **Settings ➔ Secrets and variables ➔ Actions**.
3. Add the following secrets:
   - `TELEGRAM_BOT_TOKEN`: Your Telegram Bot API token from `@BotFather`.
   - `TELEGRAM_CHAT_ID`: Your private Telegram Chat ID.
   - `CTRADER_ENV`: `demo` or `live` (Optional, defaults to `demo`).
   - `CTRADER_CLIENT_ID`: cTrader Open API Client ID (Optional).
   - `CTRADER_CLIENT_SECRET`: cTrader Open API Client Secret (Optional).
   - `CTRADER_ACCESS_TOKEN`: cTrader User Access Token (Optional).
   - `CTRADER_ACCOUNT_ID`: cTrader Account ID (Optional).
   - `ENABLE_CTRADER_EXECUTION`: `true` to enable automated broker execution (defaults to `false` for paper trading).
4. In **Settings ➔ Actions ➔ General ➔ Workflow permissions**, select **"Read and write permissions"** so the scanner can automatically persist trade records to `trade_records.json`.

### B. Interactive Telegram Edge Cockpit (Cloudflare Workers)
1. In the [Cloudflare Dashboard](https://dash.cloudflare.com), create a new Worker named `tradingview-telegram-relay`.
2. Paste the contents of `cloudflare_worker.js` and click **Deploy**.
3. Bind a KV Namespace named `TRADE_LEDGER` to the Worker.
4. Set your Telegram webhook:
   ```bash
   curl -X POST "https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/setWebhook" \
        -H "Content-Type: application/json" \
        -d '{"url": "https://<YOUR_WORKER_SUBDOMAIN>.workers.dev/"}'
   ```

### C. Local CLI Commands
```bash
# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1

# Run complete automated test suite (159 unit tests)
pytest

# Execute a single Forex market scan cycle
python market_scanner.py

# Execute a single Gold Satellite scan cycle
python satellite/market_scanner_gold.py

# Run continuous 24/7 background loops locally
python market_scanner.py --loop
python satellite/market_scanner_gold.py --loop

# Send sample verification test alerts to Telegram
python market_scanner.py --test
python satellite/market_scanner_gold.py --test

# Run canonical look-ahead-free backtest (70/30 In-Sample/Out-of-Sample)
python scripts/run_canonical_backtest.py --markdown

# Check live forward validation performance metrics
python scripts/forward_test_tracker.py --markdown
```

---

## 7. Production Readiness & System Verification

| Verification Dimension | Status | Evidence / Metric |
| :--- | :---: | :--- |
| **Unit Test Coverage** | **100% PASS** | **159 automated unit tests** passing with zero regressions across all core components. |
| **Cloud Surveillance** | **OPERATIONAL** | GitHub Actions 24/7 runner executing cycles every 15 minutes during global market hours. |
| **Signal Dispatch** | **OPERATIONAL** | Real-time HTML alerts delivered to Telegram with entry, SL, TP, lot size, and confluence metrics. |
| **Edge Synchronization** | **OPERATIONAL** | Atomic two-way synchronization between Python scanner ledgers and Cloudflare Worker KV. |
| **Financial Safety** | **ENFORCED** | Conservative lot flooring, zero budget breaching, look-ahead prevention, pessimistic intra-candle resolution, and default dry-run broker execution. |
| **Broker Execution** | **STAGE-GATED** | Full cTrader Open API Protobuf client implemented, tested, and ready for live order submission upon credential injection. |

---

## 8. Financial Safety Invariants

Until explicitly authorized in writing:
1. **Zero Live Financial Transactions:** Never place live trades, enable live broker order submission, or manipulate real trading balances.
2. **Offline Research & Paper Execution:** Rely strictly on historical market data, local mocks, forward paper trading, and dry-run execution.
3. **Zero Secret Exposure:** Never commit, print, echo, or log API keys, broker passwords, Telegram tokens, or personal access tokens.
4. **Pessimistic Intra-Candle Assumption:** When a candle touches both Stop Loss and Take Profit thresholds, Stop Loss takes absolute precedence.
