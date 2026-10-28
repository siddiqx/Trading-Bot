# PRIORITIZED DEVELOPMENT ROADMAP & ACCEPTANCE CRITERIA

This roadmap outlines the recommended engineering improvements for the trading bot project, strictly prioritized by financial safety, correctness, backtesting validity, reliability, and maintainability.

> [!IMPORTANT]
> In accordance with Operating Rule 1 and Rule 6, no material code refactoring or strategy parameter modifications will be executed until explicitly authorized.

---

## Phase 1: Critical Financial Safety & Security Defects

### Task SEC-1: Rotate and Remove Plaintext Secrets from Source Code
* **Priority:** Critical (P0)
* **Scope:** `market_scanner.py`, `cloudflare_worker.js`, `.github/workflows/scanner.yml`
* **Objective:** Revoke exposed credentials and enforce strict environment variable injection.
* **Acceptance Criteria:**
  1. Telegram Bot Token is revoked and re-issued by `@BotFather`.
  2. GitHub Personal Access Token in `cloudflare_worker.js` is deleted and replaced with a restricted Cloudflare Worker secret.
  3. Default string fallbacks in `market_scanner.py` and `cloudflare_worker.js` are removed; application raises an explicit `RuntimeError` if required secrets are missing.
  4. Repository history is sanitized or credentials confirmed rotated.

### Task RISK-1: Correct Multi-Currency Position Sizing Mathematics
* **Priority:** Critical (P0)
* **Scope:** `core/instrument_validator.py`, `market_scanner.py`
* **Objective:** Ensure 1.0% risk on a $5,000 account corresponds to exactly $50.00 monetary loss at the stop-loss level across all pairs.
* **Acceptance Criteria:**
  1. Pip value formula dynamically incorporates the quote currency exchange rate for `USDJPY`, `USDCAD`, and `USDCHF`.
  2. For a $50 risk budget on `USDCAD` with a 16-pip SL, calculated lot size correctly reflects CAD/USD exchange rate conversion.
  3. Signal alert messages dynamically display the calculated lot size rather than hardcoded 0.25 lots.
  4. Unit test suite validates lot sizing across all six configured pairs.

---

## Phase 2: Quantitative Strategy Specification & Alignment

### Task STRAT-1: Reconcile Conflicting Exit Rules (Fixed 15/10p vs. Dynamic 15–25p)
* **Priority:** High (P1)
* **Scope:** `market_scanner.py`, `core/instrument_validator.py`, `app/config.py`
* **Objective:** Establish unambiguous consensus on whether the bot executes the rigid 15-pip TP / 10-pip SL model or the dynamic 15–25 pip liquidity-anchored model.
* **Acceptance Criteria:**
  1. Specification choice confirmed with user.
  2. `market_scanner.py`, `app/config.py`, and `instrument_validator.py` reflect the exact agreed-upon exit geometry.
  3. All automated tests in `test_market_scanner.py` assert against the unified exit model.

### Task STRAT-2: Deprecate Legacy Pine Script Gold Configurations
* **Priority:** High (P1)
* **Scope:** `pinescript/adaptive_trend_momentum_breakout.pine`, `pinescript/adaptive_trend_momentum_indicator.pine`
* **Objective:** Synchronize Pine Script indicators with the current 6-pair Forex-only ruleset.
* **Acceptance Criteria:**
  1. Gold logic removed from TradingView indicators.
  2. Account size, risk percentage, and exit parameters in Pine scripts mirror the Python production engine.

---

## Phase 3: Backtesting Validity & Data Integrity

### Task TEST-1: Eliminate Look-Ahead Bias in Historical Liquidity Targeting
* **Priority:** High (P1)
* **Scope:** `scripts/simulate_prop_firm_5k.py`, `scripts/audit_last_month_solutions.py`
* **Objective:** Ensure historical backtesting logic cannot peek forward into future bars when identifying liquidity targets.
* **Acceptance Criteria:**
  1. Forward-window search constrained to bars strictly prior to the trade decision index ($k + 12 \le \text{current\_idx}$).
  2. Backtest results recalculated and documented without future data leakage.

### Task DATA-1: Construct 6-Month Clean Institutional Forex Dataset
* **Priority:** High (P1)
* **Scope:** `data/`, `scripts/`
* **Objective:** Acquire or assemble a clean, documented 6-month historical dataset for all six Forex pairs covering 15M and 1H timeframes.
* **Acceptance Criteria:**
  1. Data includes verified open, high, low, close, and volume with UTC timestamps.
  2. Zero look-ahead bias and verified absence of missing trading hours.
  3. Stored in a reproducible format (e.g. Parquet or CSV) with data provenance documented.

---

## Phase 4: Execution Reliability & Architecture Clean-Up

### Task ARCH-1: Consolidate Dual Architectures
* **Priority:** Medium (P2)
* **Scope:** `app/` vs. `market_scanner.py`
* **Objective:** Resolve architectural ambiguity by declaring `market_scanner.py` + Cloudflare Worker as canonical, and cleanly archiving legacy FastAPI webhook code.
* **Acceptance Criteria:**
  1. Architecture decision confirmed.
  2. Unused legacy endpoints marked deprecated or safely archived without breaking imports.
  3. Unified documentation detailing the single canonical execution flow.

### Task REL-1: Harden GitHub Actions State Synchronization
* **Priority:** Medium (P2)
* **Scope:** `.github/workflows/scanner.yml`, `market_scanner.py`
* **Objective:** Prevent state race conditions during automated Git rebase and commit of `trade_records.json`.
* **Acceptance Criteria:**
  1. Git commit step incorporates exponential backoff retry on push conflicts.
  2. Cloudflare Worker KV acts as the primary distributed state store, with GitHub acting strictly as an archival mirror.

---

## Phase 5: Testing & Automation Enhancements

### Task TEST-2: Local Test Environment Diagnostics & CI Hardening
* **Priority:** Medium (P2)
* **Scope:** `tests/`, `.github/workflows/scanner.yml`
* **Objective:** Diagnose and resolve local Windows environment execution issues (`0xC0000142`) and ensure test suite runs cleanly in automated CI on every commit.
* **Acceptance Criteria:**
  1. GitHub Actions workflow runs `pytest` automatically on PR and push.
  2. All 49 unit tests pass in CI.
