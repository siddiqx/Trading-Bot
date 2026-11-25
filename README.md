# 24/7 Institutional Forex Algorithmic Trading Engine

![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue?logo=python)
![Cloudflare Workers](https://img.shields.io/badge/Cloudflare_Workers-Edge_Serverless-orange?logo=cloudflare)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Automated_24%2F7_Cron-black?logo=githubactions)
![Telegram Bot API](https://img.shields.io/badge/Telegram_Bot-Interactive_Terminal-2CA5E0?logo=telegram)
![cTrader Open API](https://img.shields.io/badge/cTrader-Automated_Execution-green?logo=tradingview)
![License](https://img.shields.io/badge/License-Proprietary-red)
![System Version](https://img.shields.io/badge/System-v3.3.0--Production-success)
![Test Suite](https://img.shields.io/badge/Tests-216%20Passing-brightgreen)

An institutional-grade, **24/7 autonomous systematic algorithmic trading bot, trade journal, and execution gateway** engineered for Forex markets.

The engine operates fully serverless in the cloud with **zero hardware dependency** (runs 24/7 via GitHub Actions and Cloudflare Global Edge) and **zero paid SaaS subscriptions**.

---

## 1. System Architecture

```
                    ┌────────────────────────────────────────────────────────┐
                    │            24/7 SERVERLESS CLOUD ARCHITECTURE          │
                    └────────────────────────────────────────────────────────┘

     ┌──────────────────────────┐                   ┌──────────────────────────┐
     │  GitHub Actions (Cloud)  │                   │ Cloudflare Global Edge   │
     │  Scheduled Cron (*/15m)  │                   │ Serverless Worker Relay  │
     └─────────────┬────────────┘                   └─────────────┬────────────┘
                   │                                              │
                   ▼                                              │
     ┌──────────────────────────┐                                 │
     │  Forex Market Scanner    │                                 │
     │  `market_scanner.py`     │                                 │
     │  • Macro Regime Engine   │                                 │
     │  • 15M Precision Signals │                                 │
     │  • Economic News Filter  │                                 │
     │  • Position Reconciler   │                                 │
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

## 2. Core Capabilities

* **Automated 24/7 Cloud Surveillance:** Autonomous market surveillance runs on closed candle bars every 15 minutes during global market hours.
* **Macro Regime & Execution Decoupling:** Combines higher-timeframe macro flow analysis with lower-timeframe precision execution timing.
* **Direct Broker Execution:** Native TLS Open API Protobuf client for cTrader with atomic server-side Stop Loss and Take Profit protection.
* **Multi-Account Auto-Discovery:** Seamlessly discovers and concurrently executes across linked challenge and funded accounts in parallel.
* **Phase-Aware Risk Architecture:** Dynamically adjusts risk exposure based on account phase (Evaluation vs Funded) and live equity drawdown tiers.
* **Capital Defense Guardrails:** Live broker equity tracking, floating drawdown limits, correlated exposure limits, news event blackouts, and weekend auto-close protection.
* **Mobile Telegram Terminal:** Real-time push notifications, live market radar, interactive trade history, and remote commands.

---

## 3. Interactive Telegram Cockpit

The Telegram terminal provides mobile surveillance and trade management via the Cloudflare Edge Worker:

| Command | Action & Telemetry |
| :--- | :--- |
| `/radar` | **Live Market Radar:** Real-time tracking of open trades, floating PnL, trailing status, and market regimes. |
| `/prices` | **Institutional Quotes:** Live spot price quotes across monitored pairs. |
| `/history` | **Trade History Ledger:** Completed trade records with quick toggle buttons (`Recent`, `Today`, `7 Days`, `All Time`) and pair filters. |
| `/performance` | **Performance Metrics:** Real-time Win Rate, Profit Factor, realized R-multiples, and trade statistics. |
| `/status` | **System Health Monitor:** Scanner heartbeat, broker connection status, and circuit breaker telemetry. |
| `/active` | **Active Positions:** Detailed breakdown of currently open positions and excursions. |

---

## 4. Repository Structure

```
trading-bot/
├── .github/workflows/
│   └── scanner.yml              # GitHub Actions 24/7 automated runner
├── core/                        # Core quantitative, risk & execution modules
│   ├── config.py                # System configuration & risk rules
│   ├── ctrader_executor.py      # cTrader Open API TLS Protobuf engine
│   ├── instrument_validator.py  # Pip math & position sizing engine
│   ├── news_filter.py           # Real-time economic calendar filter
│   └── post_mortem.py           # Trade diagnostics & excursion analytics
├── cloudflare_worker.js         # Cloudflare Edge Worker & Telegram router
├── market_scanner.py            # 24/7 Market Scanner & position reconciler
├── trade_records.json           # Live trade ledger & execution state
├── scripts/                     # Account validation & diagnostic utilities
│   ├── check_ctrader_account.py # Broker permissions & account inspector
│   ├── demo_live_equity.py      # Live equity & drawdown diagnostic
│   └── forward_test_tracker.py  # Forward validation performance tracker
├── tests/                       # Automated unit test suite (216 tests)
└── README.md                    # System documentation
```

---

## 5. Operations & Quickstart

### A. 24/7 Cloud Automated Execution (GitHub Actions)
The scanner runs autonomously during market hours via `.github/workflows/scanner.yml`.

Configure the following secrets in **GitHub Repository ➔ Settings ➔ Secrets and variables ➔ Actions**:
* `TELEGRAM_BOT_TOKEN`: Telegram Bot token from `@BotFather`.
* `TELEGRAM_CHAT_ID`: Authorized Telegram Chat ID.
* `ENABLE_CTRADER_EXECUTION`: Set `true` to enable automated broker execution (defaults to `false` for paper trading).
* `CTRADER_ENV`: `demo` or `live`.
* `CTRADER_CLIENT_ID`, `CTRADER_CLIENT_SECRET`, `CTRADER_ACCESS_TOKEN`: cTrader Open API credentials.
* `CTRADER_ACCOUNT_IDS`: Set `auto` to auto-discover all active challenge accounts.
* `RISK_MODE`: `dynamic_rank3` (phase-asymmetric risk) or `flat`.
* `ACCOUNT_STAGE`: `EVALUATION` or `FUNDED`.

### B. Telegram Edge Router (Cloudflare Workers)
1. Deploy `cloudflare_worker.js` to Cloudflare Workers.
2. Bind a KV Namespace named `TRADE_LEDGER`.
3. Set your Telegram webhook:
   ```bash
   curl -X POST "https://api.telegram.org/bot<YOUR_TELEGRAM_BOT_TOKEN>/setWebhook" \
        -H "Content-Type: application/json" \
        -d '{"url": "https://<YOUR_WORKER_SUBDOMAIN>.workers.dev/"}'
   ```

### C. Local CLI Commands
```bash
# Activate virtual environment
source .venv_linux/bin/activate  # On Windows: .venv\Scripts\Activate.ps1

# Run complete test suite (216 unit tests)
pytest

# Verify broker connection, token scopes & account permissions
python scripts/check_ctrader_account.py

# Run a single manual scan cycle
python market_scanner.py

# Run scanner in continuous local background loop
python market_scanner.py --loop

# Send a test alert to Telegram
python market_scanner.py --test
```

---

## 6. Verification & Quality Assurance

| Verification Dimension | Status | Evidence / Metric |
| :--- | :---: | :--- |
| **Unit Test Coverage** | **100% PASS** | **216 automated unit tests** passing with zero regressions across all modules. |
| **Cloud Surveillance** | **OPERATIONAL** | GitHub Actions scheduled execution running every 15 minutes during market hours. |
| **Edge Synchronization** | **OPERATIONAL** | Real-time atomic ledger synchronization between Python engine and Cloudflare KV. |
| **Broker Security** | **ENFORCED** | Process-level test interlocks, strict risk clamping, atomic server SL/TP, and timeout fill reconciliation. |

---

## 7. Safety Invariants

* **Guarded Broker Execution:** Real-money execution remains strictly disabled (`ENABLE_CTRADER_EXECUTION=false`) until explicitly authorized.
* **Credential Protection:** Secrets, access tokens, and passwords are never logged, printed, or committed to source control.
* **Pessimistic Intra-Candle Assumption:** When a candle touches both Stop Loss and Take Profit levels, Stop Loss takes precedence.
