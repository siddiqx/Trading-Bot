# ANTIGRAVITY WORKSPACE RULES & PROJECT RUNTIME INSTRUCTIONS

> **Scope:** This rulebook governs all Antigravity AI coding assistant sessions operating within `d:\02_Projects\trading-bot`. It communicates the persistent memory hierarchy, engineering guidelines, financial safety invariants, and development workflows.

---

## 1. Project Identity & High-Level Architecture

This repository contains an institutional-grade, systematic algorithmic trading bot and trade journal for Forex markets.

* **Primary 24/7 Engine:** Standalone Python market scanner (`market_scanner.py`) executed every 15 minutes during Forex market hours via GitHub Actions (`.github/workflows/scanner.yml`).
* **Edge Gateway & Telegram Cockpit:** Cloudflare Global Edge V8 Worker (`cloudflare_worker.js`) synchronizing active/completed trade ledgers in KV and serving Telegram slash commands (`/radar`, `/prices`, `/history`, `/performance`, `/strategy`, `/status`, `/active`).
* **Active Universe:** 6 standard institutional Forex pairs (`EURUSD`, `USDCAD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD`). **Gold (`XAUUSD`) and all commodity/crypto derivatives are strictly excluded.**
* **Strategy Engine:** Structural Donchian Breakout combined with ICT Killzone Liquidity Sweeps (Asian High/Low & 10-bar fractal reclaim) and Two-Phase Pullback Rejections. Dynamic liquidity-anchored TP/SL bounded between 15.0 and 25.0 pips (Pure Binary 1:1.50 R:R execution).
* **Secondary / Legacy Framework:** FastAPI webhook service (`app/`) with SQLite database (`forex_signals.db`) for TradingView alert ingestion.

---

## 2. Memory Hierarchy (Source of Truth)

To prevent context bloat and contradictory instructions across sessions, maintain information in this strict order:

1. **Level 1 — Global User Rules (`~/.gemini/config/`):** General engineering skepticism, correctness over speed, financial safety, verified facts over assumptions.
2. **Level 2 — Repository Instructions (This File — `GEMINI.md`):** Project identity, non-negotiable financial invariants, development workflow, strategy change controls.
3. **Level 3 — Project Context (`docs/PROJECT_CONTEXT.md`):** Durable architecture map, verified configuration, critical file paths, execution commands, and current development status.
4. **Level 4 — Deep Reference Documentation (`docs/`):**
   - System Audit: [`docs/PROJECT_AUDIT.md`](docs/PROJECT_AUDIT.md)
   - Strategy Rulebook: [`docs/TRADING_STRATEGY_SPEC.md`](docs/TRADING_STRATEGY_SPEC.md)
   - Backtesting Framework: [`docs/BACKTESTING_METHODOLOGY.md`](docs/BACKTESTING_METHODOLOGY.md)
   - Defect & Security Log: [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)
   - Development Roadmap: [`docs/DEVELOPMENT_ROADMAP.md`](docs/DEVELOPMENT_ROADMAP.md)

---

## 3. Non-Negotiable Financial Safety Invariants

Until explicitly authorized in writing by the user:
* **Zero Live Financial Transactions:** Never place live trades, enable live broker order submission, or manipulate real trading balances.
* **Offline Research by Default:** Rely strictly on historical data, local mocks, paper trading, and dry-run execution.
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
4. **Validation:** Execute relevant automated unit tests (`tests/test_market_scanner.py`, `tests/test_post_mortem.py`, `tests/test_telegram.py`).
5. **Documentation Synchronization:** If code changes alter the strategy, configuration, architecture, or issue status, immediately update the corresponding document in `docs/`.

---

## 6. Key Commands Quick Reference

```bash
# Run complete test suite (49 unit tests)
pytest

# Execute manual market scan cycle
python market_scanner.py

# Run scanner in local 24/7 background loop
python market_scanner.py --loop

# Send sample developer test alert to Telegram
python market_scanner.py --test

# Run out-of-sample forward validation tracker
python scripts/forward_test_tracker.py --markdown

# Run $5,000 prop firm challenge simulation
python scripts/simulate_prop_firm_5k.py
```
