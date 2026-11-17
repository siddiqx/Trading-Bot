# ANTIGRAVITY WORKSPACE RULES & PROJECT RUNTIME INSTRUCTIONS

> **Scope:** This rulebook governs all Antigravity AI coding assistant sessions operating within `trading-bot`. It communicates the persistent memory hierarchy, engineering guidelines, financial safety invariants, and development workflows.

---

## 1. Project Identity & High-Level Architecture

This repository contains an institutional-grade, systematic algorithmic trading bot, trade journal, and execution gateway for Forex and Commodity markets.

* **Primary 24/7 Engine:** Dual cloud scanners executed every 15 minutes during market hours via GitHub Actions (`.github/workflows/scanner.yml`):
  1. *Forex Scanner (`market_scanner.py`):* 15M precision execution anchored to 1H 7-currency CCRS macro flow.
  2. *Gold Satellite (`satellite/market_scanner_gold.py`):* 1H commodity execution anchored to CCRS USD factor.
* **Edge Gateway & Telegram Cockpit:** Cloudflare Global Edge V8 Worker (`cloudflare_worker.js`) synchronizing active/completed trade ledgers in KV and serving Telegram slash commands (`/radar`, `/prices`, `/history`, `/performance`, `/strategy`, `/status`, `/active`).
* **Active Universe:** 5 Active Institutional Forex Pairs (`EURUSD`, `USDCAD`, `GBPUSD`, `USDCHF`, `AUDUSD`) + Isolated Gold Commodity Satellite (`XAUUSD`).
  - *Note:* `USDJPY` is de-whitelisted from active trading due to negative statistical expectancy in the 2026 BoJ/MoF currency intervention regime (20% live win rate, PF 0.38). USDJPY quotes are retained strictly for 7-currency synthetic basket calculations.
* **Strategy Engine:** Institutional Dual-Timeframe CCRS Engine (v3.3.0). Evaluates 1H rolling 200-hour volatility-normalized Z-scores over 120-hour lookbacks ($|D| \ge 1.75\sigma$ for Forex pairwise spread, $|Z_{\text{USD}}| \ge 1.25\sigma$ for Gold single factor). Precision entries triggered on confirmed 20-EMA pullback retests and 10-bar Donchian liquidity sweeps.
* **Exits & Trailing:** Volatility-anchored stops ($2.0\times$ 14-period ATR; 20.0–25.0 pips for Forex, $20–$35/oz for Gold) and $1:1.50$ Take Profit target with Volatility Cushion trailing (+1.20R halving, +1.50R profit lock, +2.00R runner).
* **Automated Broker Execution:** cTrader Open API Protobuf TLS client (`core/ctrader_executor.py`) with dynamic multi-tier position sizing, automatic SL/TP trailing synchronization, and orphaned position reconciliation.
* **Secondary / Legacy Framework:** FastAPI webhook service (`app/`) with SQLite database (`forex_signals.db`) for TradingView alert ingestion (isolated from active cloud runner).

---

## 2. Memory Hierarchy (Source of Truth)

To prevent context bloat and contradictory instructions across sessions, maintain information in this strict order:

1. **Level 1 — Global User Rules (`~/.gemini/config/`):** General engineering skepticism, correctness over speed, financial safety, verified facts over assumptions.
2. **Level 2 — Repository Instructions (This File — `GEMINI.md` / `AGENTS.md`):** Project identity, non-negotiable financial invariants, development workflow, strategy change controls.
3. **Level 3 — Project Context (`docs/PROJECT_CONTEXT.md`):** Durable architecture map, verified configuration, critical file paths, execution commands, and current development status.
4. **Level 4 — Deep Reference Documentation (`docs/`):**
   - System Audit: [`docs/PROJECT_AUDIT.md`](docs/PROJECT_AUDIT.md)
   - Strategy Rulebook: [`docs/TRADING_STRATEGY_SPEC.md`](docs/TRADING_STRATEGY_SPEC.md)
   - Backtesting Framework: [`docs/BACKTESTING_METHODOLOGY.md`](docs/BACKTESTING_METHODOLOGY.md)
   - Defect & Security Log: [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)
   - Development Roadmap: [`docs/DEVELOPMENT_ROADMAP.md`](docs/DEVELOPMENT_ROADMAP.md)
   - Position Sizing Guide: [`docs/LOT_SIZE_GUIDE.md`](docs/LOT_SIZE_GUIDE.md)

---

## 3. Non-Negotiable Financial Safety Invariants

Until explicitly authorized in writing by the user:
* **Zero Live Financial Transactions:** Never place live real-money trades, enable live broker order submission, or manipulate real trading balances. Real-money broker routing remains protected behind `ENABLE_CTRADER_EXECUTION=false` by default.
* **Offline Research & Paper Execution:** Rely strictly on historical data, local mocks, live forward paper trading, and dry-run execution.
* **Zero Secret Exposure:** Never commit, print, echo, or log API keys, broker passwords, Telegram bot tokens, or GitHub personal access tokens.
* **No Unilateral Strategy Alterations:** Never modify entry conditions, exit thresholds, stop-loss formulas, indicators, pair schedules, or risk percentages without documented justification, regression testing, and explicit user consent.

---

## 4. Quantitative & Engineering Principles

* **Inspect Before Modifying:** Always inspect affected modules, trace dependencies, check existing test coverage, and inspect the Git working tree before proposing changes.
* **Preserve Working Architecture:** Treat the existing repository as authoritative. Never initiate unnecessary framework migrations, complete rewrites, or replacement bots.
* **No Fabricated Performance:** Never invent win rates, backtest results, drawdowns, profit factors, or execution logs. If empirical data is unavailable, state the limitation explicitly.
* **Look-Ahead Prevention:** Ensure indicators and decision logic strictly use completed candle bars (`close_time <= now`). Never peek forward into future bars.
* **Pessimistic Intra-Candle Assumption:** When a candle touches both Stop Loss and Take Profit thresholds, Stop Loss must take absolute precedence.

---

## 5. Development Workflow for Future Sessions

For every coding task:
1. **Context Initialization:** Read [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) and examine the affected source files.
2. **Minimum Safe Change:** Formulate the smallest, cleanest, self-contained change that resolves the issue without introducing regressions.
3. **Pre-Change Alignment:** Explain the proposed modification, its architectural consequences, affected files, and validation plan.
4. **Validation:** Execute relevant automated unit tests (`pytest`). All 159 tests must pass with zero regressions.
5. **Documentation Synchronization:** If code changes alter the strategy, configuration, architecture, or issue status, immediately update the corresponding document in `docs/`.

---

## 6. Key Commands Quick Reference

```bash
# Run complete test suite (159 unit tests)
pytest

# Execute manual Forex market scan cycle
python market_scanner.py

# Execute manual Gold Satellite scan cycle
python satellite/market_scanner_gold.py

# Run scanners in local 24/7 background loops
python market_scanner.py --loop
python satellite/market_scanner_gold.py --loop

# Send sample developer test alerts to Telegram
python market_scanner.py --test
python satellite/market_scanner_gold.py --test

# Run canonical look-ahead-free backtest (70/30 split)
python scripts/run_canonical_backtest.py --markdown

# Run out-of-sample forward validation tracker
python scripts/forward_test_tracker.py --markdown

# Run $5,000 prop firm challenge simulation
python scripts/simulate_prop_firm_5k.py
```
