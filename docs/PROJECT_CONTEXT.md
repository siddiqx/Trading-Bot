# PROJECT CONTEXT & AGENT RUNTIME DIRECTIVE

**Project Purpose:** Production-oriented systematic Forex algorithmic trading signal engine and trade journal.  
**Operating Environment:** Python 3.11+, Cloudflare Workers (V8), GitHub Actions 24/7 cron surveillance.  
**Repository Working Directory:** `d:\02_Projects\trading-bot`  
**Git Branch:** `main`

---

## 1. Core Architecture Overview

The system operates primarily via a **24/7 Serverless Cloud Architecture**:
1. **Surveillance Runner (`market_scanner.py`):** Runs every 15 minutes during Forex market hours via GitHub Actions (`.github/workflows/scanner.yml`). Connects to Yahoo Finance, calculates indicators on closed bars, identifies institutional ICT Liquidity Sweeps and Pullback Rejections across 6 Forex pairs, monitors active positions, and sends Telegram alerts.
2. **Edge Gateway & Router (`cloudflare_worker.js`):** Hosted on Cloudflare Workers (`tradingview-telegram-relay.siddiqsiddiq00012.workers.dev`). Maintains active and completed trade state in Cloudflare KV, routes Telegram commands (`/radar`, `/prices`, `/history`, `/performance`, `/strategy`, `/status`), and ensures 24/7 Telegram responsiveness.
3. **Trade Ledger & Diagnostics:** State stored in `trade_records.json` and synchronized with Cloudflare KV. `core/post_mortem.py` logs trade excursions (MFE/MAE) and failure classifications to `data/patterns/` and `journals/`.
4. **Secondary / Legacy Framework (`app/`):** FastAPI webhook service with SQLite database (`forex_signals.db`) designed to receive TradingView alert webhooks. Currently disconnected from the active 24/7 market scanner pipeline.

---

## 2. Actual Implemented Strategy (Canonical Alignment Verified)

| Parameter | Canonical Specification | Code Reality (`core/config.py`, `market_scanner.py`, `cloudflare_worker.js`) |
|---|---|---|
| **Strategy Identity** | Institutional Dual-Timeframe CCRS Engine (v3.3.0) | Cross-Currency Relative Strength (CCRS) Factor Engine with Volatility-Cushioned Trailing and Real-Time Economic News Filtering. Decouples Macro Order Flow Bias (1H CCRS) from Precision Execution Timing (15M Retest / Sweep). Decomposes 6 Forex pairs into 7 pure currency strength indices, calculates rolling 200h volatility-normalized Z-scores over 120-hour lookbacks, and trades active macro flow regimes (\|D\| ≥ 1.75σ) on 15M confirmed pullbacks and fractal sweeps. Verified 6-month performance: +1,096.8 net pips, 1.26 Profit Factor, and 2.0% max daily drawdown. |
| **Asset Universe** | 6 Institutional Forex Pairs (Zero Gold) | **6 Forex Pairs:** `EURUSD`, `USDCAD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD`. Gold (`XAUUSD`) and all commodities/crypto are strictly excluded. |
| **Timeframes** | Dual-Timeframe (1H Macro + 15M Execution) | 1H closed-candle CCRS Macro Flow calculation; 15M closed-candle precision execution every 15 minutes via GitHub Actions. |
| **Active Volume Hours** | Institutional Volume Hours (07:00–17:00 UTC) | Strictly institutional London & NY overlap volume hours. Daily rollover spread spike window (22:00 UTC) and weekends strictly bypassed. |
| **Take Profit & Trailing** | Volatility Cushion Runner (1:1.50 to 1:2.00 R:R) | Base 33.0p TP (+1.50R). Volatility Cushion: Tier 1 @ +1.20R (+26.4p) halves risk by moving SL to -10.0p (retains 36p breathing buffer); Tier 2 @ +1.50R (+33.0p) locks in +11.0p (+0.50R profit) and extends runner TP to +44.0p (+2.00R). |
| **Stop Loss** | Volatility-Anchored Dynamic ATR Stop | Dynamic 2.0× 14-period 1H ATR stop loss bounded strictly between 20.0 and 25.0 pips (suppresses retail spread friction while respecting intraday ADR). Canonical baseline: 22.0 pips. |
| **News Filter** | Automated Forex Factory High-Impact Filter | Real-time economic calendar feed (`core/news_filter.py`). Automatically suppresses fresh entries 30 minutes before and after Red Folder news releases. |
| **Risk per Trade** | 0.50% ($25 on $5,000 reference) | Calibrated prop firm risk sizing. Max daily drawdown capped at ~2.0% ($100), ensuring immunity from 4.0% daily DD limits. |
| **Daily Circuit Breaker** | Prop firm capital preservation | Halts if today's loss $\le -2.00\text{R}$ or if $\ge 2$ stop-outs occur today (1.0% max daily loss ceiling). |
| **Correlated Exposure** | Risk limit | Max 3 simultaneous unprotected trades; max 2 in same net USD direction. |
| **Post-Loss Lockout** | Churn prevention | 60-minute mandatory lockout for an instrument after a stop-loss. |

---

## 3. Important File Reference Map

* **Authoritative Config:** `core/config.py` (Single source of truth for universe, exits, risk budgets, transaction costs, and portfolio rules)
* **Production Scanner:** `market_scanner.py` (Main scanning engine and trade lifecycle monitor)
* **Cloudflare Edge Relay:** `cloudflare_worker.js` (Telegram webhook router & KV sync)
* **Instrument Validator & Sizing:** `core/instrument_validator.py` (Symbol eligibility, pip values, multi-currency position sizing)
* **Post-Mortem Diagnostics:** `core/post_mortem.py` (MFE/MAE tracking & pattern classification)
* **Canonical Backtest Engine:** `scripts/run_canonical_backtest.py` (Look-ahead-free, transaction-friction-modeled 70/30 backtesting engine)
* **Prop Firm Simulation:** `scripts/simulate_prop_firm_5k.py` ($5,000 challenge tracker driven by canonical backtest engine)
* **Trade Ledger:** `trade_records.json` (Atomic live forward trade state)
* **Volume Journal:** `journals/VOLUME_BENCHMARKS.md`, `data/patterns/volume_index.json`
* **Test Suites:** `tests/test_canonical_strategy.py`, `tests/test_position_sizing.py`, `tests/test_market_scanner.py`, `tests/test_post_mortem.py`, `tests/test_telegram.py`
* **Cron Runner:** `.github/workflows/scanner.yml` (Runs `*/15 5-21 * * 1-5`)
* **Legacy Webhook Service:** `app/main.py`, `app/config.py`, `app/api/webhook.py`
* **TradingView Strategies:** `pinescript/adaptive_trend_momentum_breakout.pine`

---

## 4. Key Execution & Developer Commands

```bash
# Activate virtual environment
# Windows: .venv\Scripts\Activate.ps1 | Linux: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run complete automated unit test suite
pytest

# Execute a single market scan cycle manually
python market_scanner.py

# Run scanner in continuous local background loop (60s poll)
python market_scanner.py --loop

# Dispatch sample developer test alert to Telegram
python market_scanner.py --test

# Run canonical look-ahead-free backtest with institutional costs (70/30 split)
python scripts/run_canonical_backtest.py --markdown

# Run historical prop firm challenge simulation ($5,000 account)
python scripts/simulate_prop_firm_5k.py
```

---

## 5. Non-Negotiable Financial Safety Invariants

Until explicitly authorized by the user:
1. **Zero Live Orders:** Never place live trades, enable live broker APIs, or alter live account balances.
2. **Zero Credential Exposure:** Never print, log, or commit API keys, bot tokens, passwords, or personal access tokens.
3. **No Unilateral Strategy Alterations:** Never change entry rules, exit thresholds, indicators, stop-loss formulas, or pair whitelists without explicit consent and documented rationale.
4. **No Fabricated Performance:** Never invent backtest results, win rates, trade counts, or drawdowns. Report only empirical facts with documented evidence.

---

## 6. Recent Remediation & Next Recommended Task

### Completed Remediation (October 28, 2026)
- **ISS-SEC-01 & ISS-SEC-02 (Credential Security):** Cleansed plaintext Telegram token, chat ID, and GitHub PAT fallbacks from `market_scanner.py` and `cloudflare_worker.js`. Mandated environment variables and encrypted secret bindings. Created `.env.example` and updated `.gitignore`.
- **ISS-RISK-01 (Multi-Currency Position Sizing):** Implemented `calculate_pip_value_usd()`, updated `calculate_position_size()`, and `calculate_monetary_risk()` in `core/instrument_validator.py`. Connected `market_scanner.py` signal generation and alert formatter. Added exhaustive unit tests in `tests/test_position_sizing.py`.
- **ISS-STRAT-01 (Strategy Exit Alignment & Single Source of Truth):** Created `core/config.py` establishing canonical 15.0p TP and 10.0p SL (1:1.50 R:R), $5,000 equity, 1% risk ($50), and 6 Forex pairs (zero Gold). Aligned `market_scanner.py`, `core/instrument_validator.py`, `app/config.py`, and `cloudflare_worker.js`. Enforced budget protection: trades are safely skipped if min permitted lot (0.01) would breach dollar budget.
- **ISS-BACKTEST-01 (Look-Ahead Elimination & Realistic Backtest):** Implemented `scripts/run_canonical_backtest.py` strictly evaluating historical decisions at closed bar $t \le \text{current\_idx}$, modeling spread, commission, and slippage, enforcing portfolio risk rules, and reporting In-Sample (70%) vs Out-of-Sample (30%) performance. Refactored `scripts/simulate_prop_firm_5k.py`.
- **ISS-OPS-01 (Signal Delivery Restoration & Quantitative Analysis):** Diagnosed missing Telegram signal root cause (stripped fallback tokens required GitHub Repository Secrets). Added workflow pre-flight secrets check and step summaries. Reconstructed dataset: 24 live forward trades and 303 archival trades. Investigated Friday behavior (refuted Friday exclusion; shown to degrade OOS performance). Evaluated exit variants A through D across 3,794 setups, proving Variant D (Structure + ATR Buffer) reduces drawdown by 91% compared to rigid 10p stops.

### Next Recommended Tasks
1. **GitHub Secret Injection:** User sets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in repository secrets, and enables Read/Write workflow permissions.
2. **Strategy Evolution (Variant D):** Transition canonical stop model from rigid 10-pip stop to structure-anchored stop with ATR buffer (Variant D) to eliminate high friction and noise stop-outs.
