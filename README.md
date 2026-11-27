# QuantFlow Institutional FX & VIP Engine (v3.3.0)

![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue?logo=python)
![Cloudflare Workers](https://img.shields.io/badge/Cloudflare_Workers-Edge_Serverless-orange?logo=cloudflare)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-Automated_24%2F7_Cron-black?logo=githubactions)
![Telegram Bot API](https://img.shields.io/badge/Telegram_Bot-Interactive_Terminal-2CA5E0?logo=telegram)
![cTrader Open API](https://img.shields.io/badge/cTrader-Automated_Execution-green?logo=tradingview)
![License](https://img.shields.io/badge/License-Proprietary-red)
![System Version](https://img.shields.io/badge/System-v3.3.0--Production-success)
![Test Suite](https://img.shields.io/badge/Tests-239%20Passing-brightgreen)

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
     │  • Public Channel Signals│                   │ • /radar   • /history    │
     │  • VIP Execution Feed    │                   │ • /prices  • /performance│
     │  • cTrader Open API      │                   │ • /status  • /strategy   │
     │    Automated Execution   │                   │ • /active                │
     │    (TLS Protobuf Client) │                   │                          │
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
* **Macro Regime & Execution Decoupling:** Combines higher-timeframe 7-currency relative strength (CCRS) macro flow analysis ($|D| \ge 1.75\sigma$) with lower-timeframe 15M precision execution timing (20-EMA retests & Donchian liquidity sweeps).
* **Direct Broker Execution:** Native TLS Open API Protobuf client for cTrader with atomic server-side Stop Loss and Take Profit protection.
* **Multi-Account Auto-Discovery:** Seamlessly discovers and concurrently executes across linked challenge and funded accounts in parallel with independent dynamic lot sizing.
* **Capital Defense Hard Clamp:** Strict monetary risk validation prevents any order from exceeding target risk budgets, protecting prop firm accounts from drawdown violations.
* **Commercial Monetization Engine:** Built-in dual-channel funnel (`QuantFlow Institutional FX` public channel and `QuantFlow VIP Club` execution feed) with anti-forwarding DRM, quota gating, locked teasers, and Whop billing synchronization.
* **Mobile Telegram Terminal:** Real-time push notifications, live market radar, interactive trade history, and remote commands.

---

## 3. Commercial Funnel & Telegram Architecture

The platform includes an automated two-tier signal distribution engine:

1. **Public Channel (`QuantFlow Institutional FX` - `@ccrs_forex_signals`):**
   * Delivers weekly verified performance journals, milestone celebrations, and up to 4 free sample trades per week.
   * Automatically switches to high-converting **Locked VIP Teasers** once the weekly quota is reached, withholding exact Entry and SL levels.
   * Educational market insights broadcast on a 72-hour cooldown.

2. **VIP Channel (`QuantFlow VIP Club`):**
   * Receives 100% of confirmed execution signals in real time.
   * Clean, jargon-free trade formatting (direct Entry, Stop Loss, Take Profit, and Risk/Reward).
   * Real-time Fill, Breakeven, and Trailing Stop-Loss adjustments.
   * DRM Content Protection (`protect_content=True`) blocks message forwarding and unauthorized leaks.
   * Access managed automatically via Whop memberships.

---

## 4. Interactive Telegram Cockpit

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

## 5. Repository Structure

```
trading-bot/
├── .github/workflows/
│   └── scanner.yml              # GitHub Actions 24/7 automated runner
├── core/                        # Core quantitative, risk & execution modules
│   ├── config.py                # System configuration & risk rules
│   ├── ctrader_executor.py      # cTrader Open API TLS Protobuf engine
│   ├── instrument_validator.py  # Pip math & position sizing engine
│   ├── news_filter.py           # Real-time economic calendar filter
│   ├── holiday_filter.py        # Institutional bank holiday filter
│   └── post_mortem.py           # Trade diagnostics & excursion analytics
├── satellite/                   # Isolated commodity engines
│   ├── market_scanner_gold.py   # Gold satellite scanner (de-whitelisted by default)
│   ├── gold_config.py           # Commodity specifications
│   └── gold_validator.py        # Commodity risk sizing & session filters
├── cloudflare_worker.js         # Cloudflare Edge Worker & Telegram router
├── market_scanner.py            # 24/7 Market Scanner & position reconciler
├── trade_records.json           # Live trade ledger & execution state
├── scripts/                     # Account validation & diagnostic utilities
│   ├── check_ctrader_account.py # Broker permissions & account inspector
│   ├── run_canonical_backtest.py# 70/30 out-of-sample backtest engine
│   └── forward_test_tracker.py  # Forward validation performance tracker
├── tests/                       # Automated unit test suite (239 tests)
└── README.md                    # System documentation
```

---

## 6. Operations & Quickstart

### A. 24/7 Cloud Automated Execution (GitHub Actions)
The scanner runs autonomously during market hours via `.github/workflows/scanner.yml`.

Configure the following secrets in **GitHub Repository ➔ Settings ➔ Secrets and variables ➔ Actions**:
* `TELEGRAM_BOT_TOKEN`: Telegram Bot token from `@BotFather`.
* `TELEGRAM_CHAT_ID`: Authorized Telegram Admin Chat ID.
* `TELEGRAM_PUBLIC_CHAT_ID`: Public channel username (e.g. `@ccrs_forex_signals`).
* `TELEGRAM_VIP_CHAT_ID`: Private VIP channel ID (e.g. `-1005701371238`).
* `TELEGRAM_VIP_INVITE_LINK`: Official Whop checkout URL.
* `ENABLE_CTRADER_EXECUTION`: Set `true` to enable automated broker execution (defaults to `false` for paper trading).
* `CTRADER_ENV`: `demo` or `live`.
* `CTRADER_CLIENT_ID`, `CTRADER_CLIENT_SECRET`, `CTRADER_ACCESS_TOKEN`: cTrader Open API credentials.
* `CTRADER_ACCOUNT_IDS`: Set `auto` to auto-discover all active challenge accounts.
* `RISK_MODE`: `dynamic_rank3` (phase-asymmetric risk) or `flat`.
* `ACCOUNT_STAGE`: `EVALUATION` or `FUNDED`.

### B. Telegram Edge Router (Cloudflare Workers)
1. Deploy `cloudflare_worker.js` to Cloudflare Workers via `wrangler deploy`.
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

# Run complete test suite (239 unit tests)
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

## 7. Verification & Quality Assurance

| Verification Dimension | Status | Evidence / Metric |
| :--- | :---: | :--- |
| **Unit Test Coverage** | **100% PASS** | **239 automated unit tests** passing with zero regressions across all modules. |
| **Cloud Surveillance** | **OPERATIONAL** | GitHub Actions scheduled execution running every 15 minutes during market hours. |
| **Edge Synchronization** | **OPERATIONAL** | Real-time atomic ledger synchronization between Python engine and Cloudflare KV. |
| **Broker Security** | **ENFORCED** | Process-level test interlocks, strict Capital Defense Hard Clamp, atomic server SL/TP, and timeout fill reconciliation. |
| **Secrets & Privacy** | **VERIFIED** | Zero hardcoded API keys or tokens in git tracked files. Strict environment variable isolation. |

---

## 8. Financial Safety Invariants

* **Guarded Broker Execution:** Real-money execution remains strictly protected behind `ENABLE_CTRADER_EXECUTION=false` by default.
* **Credential Protection:** Secrets, access tokens, and passwords are never logged, printed, or committed to source control.
* **Pessimistic Intra-Candle Assumption:** When a candle touches both Stop Loss and Take Profit levels, Stop Loss takes absolute precedence.
* **Look-Ahead Prevention:** All indicators and signal decisions evaluate strictly on closed candle bars (`close_time <= now`).
