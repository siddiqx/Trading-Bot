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
| **Strategy Identity** | Asian Night Statistical Mean-Reversion Scalper (v2.0) | Primary Alpha Engine: Fades extreme $\pm 2.0\sigma$ Bollinger Band deviations with RSI exhaustion during Asian/Late NY liquidity hours (21:00–05:00 UTC, skipping 22:00 rollover). Empirical: 65.13% WR over 2,776 trades, +319.73R net, +38.0R avg/6-month window across 4.8 years. |
| **Asset Universe** | 6 Institutional Forex Pairs (Zero Gold) | **6 Forex Pairs:** `EURUSD`, `USDCAD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD`. Gold (`XAUUSD`) and all commodities/crypto are strictly excluded. |
| **Timeframes** | 15M (Intraday) & 1H (Macro) | 15M execution, 1H/Daily HTF trend alignment, 5M precision trigger. |
| **Take Profit** | Dynamic Equilibrium Mean (20-EMA) | Dynamically anchored at the 20-period EMA (minimum 5.0 pips). |
| **Stop Loss** | Bounded Structural Stop | Anchored beyond local swing low/high + 1.0 ATR buffer (bounded strictly between 8.0 and 25.0 pips). |
| **Max Hold Duration** | Session Capital Protection | 16 bars (4 hours) timeout exit at market close before European volatility. |
| **Risk per Trade** | 1.0% ($50 on $5,000) | Dynamically calculated multi-currency position sizing with quote-to-USD conversion and lot flooring (`core/instrument_validator.py`). Trades safely skipped (returns `0.0` lots) if min lot exceeds risk budget. |
| **Daily Circuit Breaker** | Prop firm capital preservation | Halts if today's loss $\le -2.50\text{R}$ or if $\ge 3$ stop-outs occur today. |
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
