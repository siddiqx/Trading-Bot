# KNOWN ISSUES & DEFECT LOG

This document tracks verified defects, architectural discrepancies, and security vulnerabilities identified during the code audit of October 28, 2026, along with their remediation status.

---

### ISSUE-SEC-01: Hardcoded Telegram Bot Token and Chat ID in Source Code

* **Severity:** **Critical** (Security Vulnerability)
* **Status:** **REMEDIATED IN CODE (2026-10-28)** — Pending manual token revocation via @BotFather.
* **Affected Files:** `market_scanner.py` (lines 38–46), `cloudflare_worker.js` (lines 15–35, 1899–1940)
* **Root Cause:** Plaintext default fallback strings were committed to git to allow zero-config execution.
* **Remediation Implemented:**
  - Removed all hardcoded token and chat ID string fallbacks from `market_scanner.py` and `cloudflare_worker.js`.
  - In `market_scanner.py`, `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are ingested strictly from environment variables or `.env`. Missing credentials log a clear error and abort outbound network dispatches with an explicit configuration error rather than silently failing or using defaults. Running `market_scanner.py --test` without credentials exits cleanly with an error message and status code 1.
  - In `cloudflare_worker.js`, added `getBotToken(env)`, `getTelegramApi(env)`, and `getTelegramChatId(env)` helpers that dynamically resolve credentials from Cloudflare Worker secret bindings (`env.TELEGRAM_BOT_TOKEN`, `env.TELEGRAM_CHAT_ID`).
  - Created `.env.example` with sanitized placeholders.
  - Updated `.gitignore` to ignore `.env`, `.env.*`, and `.env*.local` while explicitly tracking `!.env.example`.
* **Required Manual User Action:**
  1. Open Telegram and message `@BotFather`.
  2. Send `/revoke` and select the trading bot to invalidate the exposed token.
  3. Send `/token` to generate a new bot token.
  4. Update the GitHub Repository Secret `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
  5. Update the Cloudflare Worker encrypted secret binding via `wrangler secret put TELEGRAM_BOT_TOKEN` and `wrangler secret put TELEGRAM_CHAT_ID`.

---

### ISSUE-SEC-02: Hardcoded GitHub Personal Access Token in Cloudflare Worker

* **Severity:** **Critical** (Security Vulnerability)
* **Status:** **REMEDIATED IN CODE (2026-10-28)** — Pending manual token revocation in GitHub Account Settings.
* **Affected Files:** `cloudflare_worker.js` (lines 18, 240, 375)
* **Root Cause:** A personal access token (`DEFAULT_GH_TOKEN = "gho_..."`) was embedded directly in the JavaScript source to enable automated GitHub Actions workflow dispatches.
* **Remediation Implemented:**
  - Removed hardcoded fallback token `DEFAULT_GH_TOKEN`.
  - `triggerGitHubScanner(env)` and `getLedger(env)` now check strictly for `env.GITHUB_TOKEN` or `env.GH_TOKEN` passed via Cloudflare Worker encrypted environment bindings.
  - If the token is absent, workflow dispatches log a clear warning and skip securely without failing or exposing credentials.
* **Required Manual User Action:**
  1. Go to GitHub Settings -> Developer Settings -> Personal Access Tokens (Tokens classic or Fine-grained).
  2. Locate the exposed token and click **Revoke** / **Delete**.
  3. Generate a new fine-grained Personal Access Token scoped strictly to the `Trading-Bot` repository with `Actions: Read and write` permission.
  4. Bind the new token in Cloudflare Workers using `wrangler secret put GITHUB_TOKEN`.

---

### ISSUE-RISK-01: Inaccurate Position Sizing on Non-USD Quote Currency Pairs

* **Severity:** **High** (Financial Risk / Calculation Defect)
* **Status:** **REMEDIATED IN CODE (2026-10-28)** — Tested and verified in `tests/test_position_sizing.py`.
* **Affected Files:** `core/instrument_validator.py` (lines 214–248), `market_scanner.py` (signal generation and alert formatter)
* **Root Cause:** `calculate_position_size()` assumed every instrument had a fixed pip value of $10.00 USD per standard lot, which is only valid for direct USD quote pairs (`EURUSD`, `GBPUSD`, `AUDUSD`). For USD base pairs (`USDCAD`, `USDJPY`, `USDCHF`), the quote currency pip value was never converted into account currency (USD), creating pricing errors exceeding 40%.
* **Remediation Implemented:**
  - Implemented `calculate_pip_value_usd(symbol, exchange_rate, contract_size)` in `core/instrument_validator.py`:
    - Direct Quote pairs (`XXX/USD`): Pip value is fixed at $10.00 USD per standard lot ($0.0001 \times 100,000$).
    - Indirect Quote pairs (`USD/XXX`): Pip value converts Quote currency to USD via $\frac{\text{pip\_size} \times \text{contract\_size}}{\text{exchange\_rate}}$ (e.g. $10.0 / 1.4190 \approx \$7.05$ for `USDCAD`, $1,000.0 / 155.0 \approx \$6.45$ for `USDJPY`, $10.0 / 0.8800 \approx \$11.36$ for `USDCHF`).
    - Validates exchange rates: strictly raises `ValueError` if `exchange_rate` is missing ($\le 0$ or None) on non-USD quote pairs.
    - Strictly rejects Gold (`XAUUSD`) and non-forex pairs with `ValueError`.
  - Implemented conservative lot-step flooring:
    - $\text{floored\_lots} = \lfloor \frac{\text{raw\_lots}}{\text{lot\_step}} \rfloor \times \text{lot\_step}$.
    - Guarantees that rounded lot sizes never exceed the monetary dollar risk budget.
    - Clamps to `min_lot` (0.01) and `max_lot` (100.0).
  - Implemented `calculate_monetary_risk(lots, sl_pips, symbol, exchange_rate)` to compute the exact realized dollar risk after lot-step truncation.
  - Connected `market_scanner.py` signal generators (`scan_pair_timeframe`) to compute `calc_lots` and `calc_risk_usd` dynamically at signal time and embed them in signal payloads.
  - Updated `format_alert_message()` to display the exact calculated risk in Telegram alerts:
    `• Suggested Risk: $49.61 / trade (1.00% on $5,000 Account · 0.44 Lots)` with backward-compatible fallback for mock test payloads.
* **Validation & Test Coverage:**
  - Created comprehensive test suite `tests/test_position_sizing.py` covering:
    - `EURUSD`, `GBPUSD`, `AUDUSD` ($10.00 USD pip value).
    - `USDCAD`, `USDJPY`, `USDCHF` exchange rate quote conversions.
    - Zero and negative stop-loss distances (`ValueError`).
    - Missing, zero, and negative exchange rates on indirect pairs (`ValueError`).
    - Gold symbols (`XAUUSD`, `GOLD`, `PAXG`) and unsupported symbols (`ValueError`).
    - Minimum lot enforcement (0.01 lot minimum).
    - Monetary risk budget invariant across arbitrary equity and SL levels.

---

### ISSUE-STRAT-01: Discrepancy Between Stated 15/10 Pips and Implemented Liquidity Exits

* **Severity:** **High** (Specification Discrepancy)
* **Status:** **REMEDIATED IN CODE (2026-10-28)** — Single source of truth established in `core/config.py` and validated across test suite.
* **Affected Files:** `core/config.py` (New), `market_scanner.py`, `core/instrument_validator.py`, `app/config.py`, `cloudflare_worker.js`
* **Root Cause:** The codebase previously contained two conflicting exit models: a rigid 15p TP / 10p SL model in `app/config.py` and `instrument_validator.py`, and a dynamic 15–25p liquidity-anchored model in `market_scanner.py`.
* **Remediation Implemented:**
  - Established `core/config.py` as the authoritative single source of truth for all strategy parameters across the repository:
    - Active Universe: 6 institutional Forex pairs (`EURUSD`, `USDCAD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD`). Gold (`XAUUSD`) strictly excluded.
    - Exits: Fixed 15.0 pips Take Profit and 10.0 pips Stop Loss (Pure Binary 1:1.50 R:R).
    - Account & Risk: Reference account equity `$5,000.00 USD`, `1.0%` risk per trade, `$50.00 USD` maximum nominal risk budget before transaction costs.
  - Aligned `core/instrument_validator.py`: `PAIR_SCHEDULES`, `FIXED_TAKE_PROFIT_PIPS`, and `FIXED_STOP_LOSS_PIPS` import from `core.config`. Position sizing floors lots and safely returns `0.0` (skips the trade) when the minimum lot (0.01) would breach the dollar risk budget.
  - Aligned `market_scanner.py`: `calculate_liquidity_bounds_tp_sl()` returns canonical 15.0p TP and 10.0p SL. Signal generator rejects trades if `calc_lots <= 0.0`. Alert formatter reports stop distance (10.0p), target distance (15.0p), calculated lots, account equity ($5,000.00), risk budget ($50.00), and estimated monetary risk ($USD).
  - Aligned `cloudflare_worker.js`: Updated pair schedules and default TP (15.0p) / SL (10.0p).
  - Aligned `app/config.py`: Synchronized `TAKE_PROFIT_PIPS` (15.0) and `STOP_LOSS_PIPS` (10.0).
* **Validation & Test Coverage:**
  - Verified in `tests/test_canonical_strategy.py` and `tests/test_position_sizing.py`.

---

### ISSUE-BACKTEST-01: Look-Ahead Bias in Historical Liquidity Search Script

* **Severity:** **High** (Backtest Validity Defect)
* **Status:** **REMEDIATED IN CODE (2026-10-28)** — Canonical look-ahead-free backtesting engine implemented in `scripts/run_canonical_backtest.py`.
* **Affected Files:** `scripts/run_canonical_backtest.py` (New), `scripts/simulate_prop_firm_5k.py`
* **Root Cause:** Legacy `scripts/simulate_prop_firm_5k.py` included Gold (`XAUUSD`), searched up to 12 bars into the future of past swing pivots (`forward_window = min(n, k + 12)` peeking ahead of `current_idx`), and omitted realistic transaction costs.
* **Remediation Implemented:**
  - Implemented `scripts/run_canonical_backtest.py` providing an institutional-grade, look-ahead-free chronological backtesting engine:
    - Evaluates signals strictly at closed bar $t \le \text{current\_idx}$ without peeking into future candles.
    - Evaluates trade exits bar-by-bar strictly forward in time.
    - Pessimistic intra-candle resolution: if a candle touches both SL and TP, SL takes absolute precedence.
    - Modeled realistic institutional transaction friction (spread, commission, slippage) per pair.
    - Enforced portfolio risk constraints: max 3 concurrent unprotected positions, max 2 same USD bias, 60-min post-loss cooldown, daily loss circuit breaker (-2.5R or 3 losses).
    - Partitions data into 70% In-Sample and 30% Out-of-Sample intervals.
  - Refactored `scripts/simulate_prop_firm_5k.py` to evaluate the canonical simulation engine under standard 2-step prop firm rules ($5,000 balance, 3% daily limit, 7% max drawdown, 8% Phase 1 target, 5% Phase 2 target) without look-ahead bias and with Gold excluded.
* **Validation & Test Coverage:**
  - Tested in `tests/test_canonical_strategy.py`.

---

### ISSUE-ARCH-01: Dual Competing System Architectures

* **Severity:** **Medium** (Architecture / Maintainability Defect)
* **Status:** **OPEN**
* **Affected Files:** `app/` (FastAPI) vs. `market_scanner.py` (Standalone Scanner)
* **Evidence:** `app/` contains an entire web framework, database, models, and services that are bypassed by `market_scanner.py`.
* **Reproduction Steps:** Inspect application entry points in `app/main.py` and `market_scanner.py`.
* **Expected Behavior:** A single unified architecture where signal generation, validation, and storage follow a consistent pipeline.
* **Actual Behavior:** Two parallel architectures with diverging filter configurations and separate state stores.
* **Potential Impact:** High developer cognitive overhead, fragmented bug fixes, and configuration desynchronization.
* **Recommended Correction:** Establish one architecture as the canonical production system (e.g. `market_scanner.py` + Cloudflare Worker) and archive or deprecate the unused legacy paths.
* **Verification Procedure:** Verify all system tests pass against the canonical production pipeline.

---

### ISSUE-OPS-01: Silent Telegram Signal Delivery Drops Post-Credential Hardening

* **Severity:** **High** (Operational Reliability / Signal Delivery Defect)
* **Status:** **REMEDIATED IN CODE (2026-10-28)** — Workflow pre-flight check, diagnostic telemetry, and step summary reporting implemented. Awaiting user secret injection into GitHub Repository Secrets.
* **Affected Files:** `market_scanner.py` (lines 885–918, 2304–2440), `.github/workflows/scanner.yml` (lines 47–75)
* **Root Cause:** When plaintext Telegram credentials were excised during security remediation (`ISS-SEC-01`), any environment lacking `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` in its execution environment aborted network dispatch and dropped the alert. Because Cloudflare Edge Worker responded to Telegram slash commands (`/status`, `/radar`) using independent secrets in Cloudflare KV, it created the illusion that the bot was functioning normally while scheduled signal alerts were completely disabled.
* **Remediation Implemented:**
  - In `market_scanner.py`:
    - Fixed `send_telegram_alert()` return types: now returns explicit `bool` (`True` on HTTP 200, `False` on error, rate limit failure, or missing credentials).
    - Added structured diagnostic telemetry tracking cycle duration, slots scanned, signals generated, risk-guard rejections, and Telegram dispatch delivery rates.
    - Added `write_step_summary()` which outputs telemetry to execution logs and appends a markdown summary table to `$GITHUB_STEP_SUMMARY` in GitHub Actions.
  - In `.github/workflows/scanner.yml`:
    - Added a `Validate Telegram Secrets` pre-flight step that warns loudly in the GitHub Actions UI when secrets are missing.
    - Fixed shell quoting in the state restoration verification step.
    - Added a graceful warning fallback to `git push origin main` so workflow runs do not fail if repository write permissions are restricted.
* **Required Manual User Action:**
  1. Go to repository **Settings** -> **Secrets and variables** -> **Actions**.
  2. Add repository secrets: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
  3. Go to repository **Settings** -> **Actions** -> **General** -> **Workflow permissions** and select **Read and write permissions**.
  4. (For local execution) Populate `.env` from `.env.example`.

---

### ISSUE-OPS-02: GitHub Actions Peak-Minute Queue Throttling and Cron Dropping

* **Severity:** **High** (Operational Execution Continuity)
* **Status:** **REMEDIATED (2026-10-30)** — Dual offset schedule (`:02`, `:17`, `:32`, `:47` and redundant `:09`, `:24`, `:39`, `:54`) implemented in `.github/workflows/scanner.yml`. Cloudflare Worker `/cron` dual dispatch enabled.
* **Affected Files:** `.github/workflows/scanner.yml`, `cloudflare_worker.js`
* **Root Cause:** Standard `:00, :15, :30, :45` (`*/15`) cron intervals experience extreme queue saturation on GitHub Actions shared runners. For public repositories, GitHub deprioritizes or drops scheduled crons during peak load or following account billing holds. Furthermore, running exactly at `:00` risks querying Yahoo Finance before the previous 15M candle is finalized.
* **Remediation Implemented:**
  - Migrated `.github/workflows/scanner.yml` to primary offset schedule `2,17,32,47 * * * 1-5`: runs 120 seconds after candle close, ensuring candle consolidation and zero queue backlog.
  - Added redundant fallback schedule `9,24,39,54 * * * 1-5` providing 200% execution coverage. Because `market_scanner.py` tracks alerted bars in `state["alerted_signals"]`, backup runs are completely duplicate-free.
  - Enhanced Cloudflare Worker `/cron` endpoint to optionally dispatch GitHub Actions via repository dispatch when `env.GITHUB_TOKEN` is present.
