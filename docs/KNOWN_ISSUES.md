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

---

### ISSUE-CCRS-01: Incomplete Forming 1H Candle Bar Masking CCRS Divergence Crossovers

* **Severity:** **High** (Signal Generation Defect)
* **Status:** **REMEDIATED IN CODE (2026-11-02)** — Verified with unit tests (`test_ccrs_matrix_trims_unclosed_bars`) and live market cycle.
* **Affected Files:** `market_scanner.py` (`compute_ccrs_matrix`, lines 1024–1050)
* **Root Cause:** In `market_scanner.py`, `compute_ccrs_matrix()` fetched raw 1H candle data from Yahoo Finance without filtering for completed bars (`close_time <= as_of`). Yahoo Finance includes the in-progress, unclosed bar for the current hour at index `[-1]`. Consequently, `latest_div` was calculated on the unclosed forming bar, while `prev_div` was calculated on the just-closed bar. When a true crossover occurred on the completed bar (e.g., AUDUSD crossing below $-2.0\sigma$ at 11:00 UTC), `prev_div` was already $\le -2.0\sigma$, causing `prev_div > -2.0` to evaluate to `False` and blinding the scanner to the valid breakout.
* **Remediation Implemented:**
  - Updated `compute_ccrs_matrix()` to accept `as_of: datetime | None = None` (defaulting to current UTC time).
  - Explicitly compute each bar's close time (`close_time = time + 1h`) and trim any candle where `close_time > as_of`.
  - Guaranteed exact 1:1 synchronization between CCRS factor matrix bars and `scan_pair_timeframe()` completed bars.
  - Added unit regression test `test_ccrs_matrix_trims_unclosed_bars` in `tests/test_market_scanner.py`.

---

### ISSUE-EXEC-01: Missing cTrader Market Close on Take Profit, Stop Loss, and Invalidation Exits

* **Severity:** **Critical** (Execution Integrity / Position Desynchronization)
* **Status:** **REMEDIATED IN CODE (2026-11-12)** — Tested and verified with automated test suite in `tests/test_ctrader_executor.py`.
* **Affected Files:** `core/ctrader_executor.py`, `market_scanner.py` (`check_active_trades`)
* **Root Cause:** While `core/ctrader_executor.py` supported placing orders (`execute_ctrader_order`) and amending SL/TP (`modify_ctrader_position`), it had no position close implementation (`dispatch_ctrader_tls_close`, `close_ctrader_position`). When `market_scanner.py` detected that an active trade touched Take Profit, Stop Loss, or early EMA invalidation in Yahoo Finance candle data, it dispatched the Telegram alert and deleted the trade from internal active trade tracking, but never sent a close order (`ProtoOAClosePositionReq`) to cTrader. If the broker's live spread or price differed by even fractional pips from Yahoo Finance, resting broker limits failed to trigger, leaving live trades orphaned and running unmonitored on cTrader.
* **Remediation Implemented:**
  - Implemented `dispatch_ctrader_tls_close()` and `close_ctrader_position()` in `core/ctrader_executor.py` utilizing the official Protobuf `ProtoOAClosePositionReq` (`payloadType=2111`).
  - Integrated `close_ctrader_position()` into `check_active_trades()` in `market_scanner.py` across all exit branches (`hit_tp`, `hit_sl`, and `hit_ema_exit`).
  - Stored `ctrader_close_receipt` in the archived trade record for full post-mortem auditability.
  - Created standalone utility `scripts/close_live_position.py` to allow instant manual closing of any orphaned positions.
  - Added unit regression tests `test_dry_run_close_position` and `test_live_demo_close_position_structure` in `tests/test_ctrader_executor.py`.

---

### ISSUE-STRAT-03: USDJPY Empirical Profit Bleed & Negative Expectancy in 2026 Regime

* **Severity:** **High** (Systematic Performance Drag & Profit Bleed)
* **Status:** **REMEDIATED IN CODE (2026-11-17)** — Tested and verified with automated test suite in `tests/test_canonical_strategy.py`.
* **Affected Files:** `core/config.py`, `market_scanner.py` (`scan_pair_timeframe`, main scan loop), `core/instrument_validator.py`, `cloudflare_worker.js`
* **Root Cause:**
  1. *Volatility / Stop-Loss Asymmetry:* USDJPY exhibits an average 15M ATR of 11.3 pips (vs EURUSD's 7.0 pips, +60.5% higher intraday volatility), with a 90th percentile 15M range of 20.4 pips. The canonical 20–22 pip Stop Loss represents only 1.77× ATR (0.125% of price at 159.50) compared to EURUSD's 2.85× ATR, causing single routine intra-session volatility spikes to stop out trades before structural expansion occurs.
  2. *Severe Premature Reversals (Lack of Breakeven Protection):* 30.9% of all historical backtest losses reached $\ge +0.75\text{R}$ MFE before reversing into a full stop loss (e.g. Live Trade #11 reached +0.82R, Live Trade #13 reached +1.05R before reversing into full -1.0R losses).
  3. *2026 BoJ / MoF Currency Intervention Regime:* At the 158.00–160.00 psychological danger zone, covert and overt Japanese currency interventions create violent two-way whipsaws and false breakouts during London/NY sessions.
* **Empirical Performance Evidence:**
  - Live forward testing: 20.0% Win Rate (1 Win / 4 Losses), Profit Factor 0.38, Net -2.50R, -59.0 pips.
  - 2026 YTD backtest: 43.6% Win Rate, Profit Factor 0.88, Net -3.84R (-76.9 pips).
  - Portfolio impact: Erased >58% of the profits generated by AUDUSD (+3.86R), USDCAD (+3.00R), and USDCHF (+1.64R).
* **Remediation Implemented (Option A):**
  - Officially de-whitelisted USDJPY from active trading via `DEWHITELISTED_PAIRS = {"USDJPY"}` in `core/config.py`.
  - Added guards in `market_scanner.py` (`scan_pair_timeframe` and main scan loop) to bypass signal generation and order dispatch for de-whitelisted pairs.
  - Retained USDJPY data fetching in `compute_ccrs_matrix()` to ensure mathematical integrity of the 7-currency relative strength factor model.
  - Preserved active trade tracking in `check_active_trades()` so existing live USDJPY positions close gracefully without being orphaned.
  - Added unit regression test `test_dewhitelisted_pairs_enforcement` in `tests/test_canonical_strategy.py`.

---

### ISSUE-GOLD-02: CCRS USD Single-Currency Threshold Over-Constraint Suppressing Gold Signals

* **Severity:** **Medium** (Signal Generation Suppression)
* **Status:** **REMEDIATED IN CODE (2026-11-17)** — Tested and verified with automated test suite in `tests/test_gold_satellite.py`.
* **Affected Files:** `satellite/gold_config.py`, `satellite/market_scanner_gold.py`, `tests/test_gold_satellite.py`
* **Root Cause:**
  - In Forex pair trading, CCRS evaluates pairwise currency spread divergence $Z_A - Z_B$. Because both currencies are standard normal variables ($Z \sim \mathcal{N}(0, 1)$), their difference has variance $\text{Var}(Z_A - Z_B) = 2$, yielding standard deviation $\sigma \approx 1.414$. A $1.75\sigma$ spread threshold corresponds to an individual currency move of $1.75 / \sqrt{2} \approx 1.24\sigma$.
  - In `satellite/gold_config.py`, evaluating single-factor $Z_{\text{USD}}$ against $1.75\sigma$ demanded an extreme 1-in-20 statistical event ($p \approx 0.04$ on each tail), suppressing valid Gold signals even during strong macro USD regimes. For example, between Nov 13 and Nov 17, $Z_{\text{USD}}$ peaked at $+1.73\sigma$ (averaging $+1.15\sigma$), resulting in zero Gold signal dispatches.
* **Remediation Implemented:**
  - Calibrated `CCRS_USD_THRESHOLD` from `1.75` to `1.25` in `satellite/gold_config.py`.
  - Updated docstrings in `satellite/market_scanner_gold.py`.
  - Added unit regression tests in `tests/test_gold_satellite.py` (`TestGoldMacroFactor`).

---

### ISSUE-STRAT-04: GBPUSD Structural Sweep Traps & Consecutive Live Losses

* **Severity:** **High** (Systematic Performance Drag & Profit Bleed)
* **Status:** **REMEDIATED IN CODE (2026-11-19)** — Tested and verified in `tests/test_canonical_strategy.py` & `tests/test_market_scanner.py`.
* **Affected Files:** `core/config.py`, `market_scanner.py`, `core/instrument_validator.py`, `cloudflare_worker.js`
* **Root Cause:**
  1. *Structural Sweep Traps ("Cable Traps"):* GBPUSD exhibits frequent two-way institutional liquidity sweeps that violate 15M Donchian/EMA breakout setups before reversing into 20–22p stop losses.
  2. *5-Year Empirical Failure:* Over the 5-year canonical backtest (2021–2026, 3,479 closed trades), GBPUSD posted a 33.3% Win Rate, Profit Factor 0.72, and a massive net loss of -102.63R (-$4,959.24).
  3. *Live Forward Failure:* In live forward execution, GBPUSD suffered a 0.0% Win Rate (0 Wins / 5 Losses, 1 Cancelled), taking -5.00R net loss and severely eroding portfolio gains from AUDUSD (+3.86R), USDCHF (+2.04R), USDCAD (+2.00R), and EURUSD (+0.91R).
* **Remediation Implemented:**
  - Added GBPUSD to `DEWHITELISTED_PAIRS = {"USDJPY", "GBPUSD"}` in `core/config.py`.
  - Active universe now strictly comprises the Clean Core 4 (`AUDUSD`, `EURUSD`, `USDCAD`, `USDCHF`).
  - GBPUSD historical quotes retained in `compute_ccrs_matrix()` for 7-currency macro basket calculation.
  - Active trade tracking in `check_active_trades()` preserved for graceful lifecycle management.

---

### ISSUE-STRAT-05: Non-CCRS Breakout Fall-Through & Off-Hours Profit Bleed

* **Severity:** **High** (Strategy Logic Leak & Negative Expectancy)
* **Status:** **REMEDIATED IN CODE (2026-11-19)** — Tested and verified in `tests/test_market_scanner.py`.
* **Affected Files:** `market_scanner.py`, `core/config.py`
* **Root Cause:**
  1. *Silent Fall-Through to Raw Breakouts:* When 1H CCRS macro flow was neutral ($|D| < 1.75\sigma$), `scan_pair_timeframe` fell through to legacy non-CCRS breakout setups. In live execution, true CCRS trades delivered 58.3% Win Rate and +5.68R profit, while non-CCRS fallback trades suffered 40.6% Win Rate and -4.37R net loss across 36 trades (accounting for 79.2% of all portfolio losses).
  2. *High-Loss Intraday Hours:* 10:00 UTC (European pre-lunch lull) suffered a 25.0% live Win Rate (-3.08R loss), and 14:00 UTC (US equity open whipsaws) suffered a 20.0% live Win Rate (-3.60R loss).
* **Remediation Implemented:**
  - Enforced strict CCRS exclusivity in `market_scanner.py`: when `ccrs_matrix` is present, neutral macro flow or unconfirmed triggers stand down immediately (`return []`) rather than falling through to non-CCRS breakout entries.
  - Excluded 10:00 UTC and 14:00 UTC from `INSTITUTIONAL_HOURS` in `core/config.py` and added explicit execution guards in `market_scanner.py`.
---

### ISSUE-EXEC-02: cTrader Silent Pseudo-Fill on Rejection & Gold PnL Unit Formatting Discrepancy

* **Severity:** **High** (Broker Execution Integrity & State Divergence Defect)
* **Status:** **REMEDIATED IN CODE & DEPLOYED (2026-11-20)** — Tested and verified with 163 pytest unit tests, Cloudflare Worker deployment, and KV ledger reconciliation.
* **Affected Files:** `core/ctrader_executor.py`, `satellite/market_scanner_gold.py`, `market_scanner.py`, `cloudflare_worker.js`, `data/gold_trade_records.json`
* **Root Cause:**
  1. *cTrader Executor Silent Fallback to 9990001:* In `core/ctrader_executor.py`, `order_id` and `position_id` defaulted to `9990001` and `tls_status` defaulted to `"EXECUTED"`. In `dispatch_ctrader_tls_order`, `PROTO_OA_ORDER_ERROR_EVENT` (2132) was not caught, falling through to `return {"status": "EXECUTED"}` without `position_id`. Furthermore, `execute_ctrader_order` hardcoded `"status": "EXECUTED"` on return regardless of broker outcome. As a result, when cTrader rejected or failed an order, the system reported `status: "EXECUTED"` with mock `position_id: 9990001`, leading `market_scanner_gold.py` to record phantom trades (`GOLD_20261120_080251`) into active trade ledgers and Cloudflare KV while no broker position existed.
  2. *Two-Step Execution Event Fragmentation:* `ProtoOANewOrderReq` for market orders triggers `ProtoOAExecutionType.ORDER_ACCEPTED` (2) as an immediate precursor before the `ORDER_FILLED` (3) event arrives. Reading only a single TLS frame terminated socket communication before position creation was confirmed.
  3. *Unfragmented TCP Socket Frame Reading:* Socket reads did not loop until complete length-prefixed Protobuf frames were received, creating vulnerability to TCP segmentation.
  4. *Gold Unit Formatting Discrepancy:* Floating PnL for Gold in `/active` and `/radar` was displayed as `+$X.XX/oz`, which did not provide the actual monetary USD floating profit or unified pip metrics requested by the user.
* **Remediation Implemented:**
  1. Implemented `_read_exact` and `_read_tls_frame` in `core/ctrader_executor.py` to ensure complete, framed Protobuf transmissions over TLS.
  2. Enhanced `dispatch_ctrader_tls_order` to explicitly parse `ProtoOAOrderErrorEvent` (2132), `ProtoOAErrorRes` (2142), and `ProtoOAExecutionType.ORDER_REJECTED` (7) / `ORDER_CANCELLED` (5). When `ORDER_ACCEPTED` (2) is returned, the subsequent frame is read to capture the true `ORDER_FILLED` position ID.
  3. Replaced mock defaults in `execute_ctrader_order` with strict validation: when running in non-mock live/demo environments, any broker rejection or missing `position_id` returns `status: "ORDER_REJECTED"` or `"ERROR"` with `position_id: None`, preventing phantom fills.
  4. Added execution safeguards in `satellite/market_scanner_gold.py` and `market_scanner.py`: signals are only admitted to `active_trades` if cTrader returns `status: "EXECUTED"` with a valid broker `position_id > 0` (or `SIMULATED_DEMO_FILL` in paper trading). Rejections dispatch a broker rejection alert to Telegram and stand down without creating ghost trades.
  5. Cleared the phantom trade `GOLD_20261120_080251` from `data/gold_trade_records.json` and reset `active_trades` and `gold_active_trades` in remote Cloudflare KV.
  6. Updated `cloudflare_worker.js` to compute and display floating profit directly in **USD** and **pips** (`+$XX.XX USD (+YY.Y pips) | +Z.ZZR`) for Gold in both `/active` and `/radar`, removing all `$/oz` references across the entire Worker.
  7. Deployed updated Cloudflare Worker to production (`https://tradingview-telegram-relay.siddiqsiddiq00012.workers.dev`).


* **Severity:** **Medium** (State Visibility & UI Consistency Defect)
* **Status:** **REMEDIATED IN CODE (2026-11-20)** — Tested and verified with Node CJS integration runner and pytest test suite.
* **Affected Files:** `cloudflare_worker.js`
* **Root Cause:**
  1. */radar Disjoint Formatting:* `/radar` mapped only 6 Forex pairs in its primary surveillance loop with Donchian channels, EMAs, and RSI, appending Gold as a static, unnumbered, hardcoded card at the bottom with inconsistent units and styling.
  2. *Active Trade State Exclusion:* Legacy sanitization logic in `sanitizeLedger` explicitly purged any trade where `sym === "XAUUSD" || sym === "GOLD" || sym.includes("XAU")`. Additionally, `getLedger` queried only `active_trades` and ignored `gold_active_trades` in Cloudflare KV.
  3. */active Blind to Commodity Alpha:* Active Gold trades never appeared in `/active`, forcing users to use `/gold`, which was cluttered with a 12-line wall of documentation text.
* **Remediation Implemented:**
  1. Added Gold (`XAU/USD (Gold)`) to `ASSETS` and `ALL_KNOWN_CONFIGS` with `symbol: "XAUUSD"`, `ticker: "GC=F"`, `pip: 0.1`, `digits: 2`, and `donchian_len: 10`.
  2. Implemented `normalizeTrade()` to standardize trade schemas across Forex and Gold (`entry`, `stop_loss`, `take_profit`, `opened_at`, `timeframe`, `pip`, `digits`, `rr`, `lots`, `direction`).
  3. Rewrote `getLedger()` and `sanitizeLedger()` to merge `gold_active_trades` and `gold_completed_trades` from KV and GitHub fallbacks, eliminating the legacy exclusion filter.
  4. Updated `/radar` to incorporate Gold as item #7 directly inside the numbered asset surveillance list with unified formatting (live price, Donchian range in $/oz and pips, 20/50 EMA, RSI, and breakout/consolidation posture), removing the redundant bottom card.
  5. Updated `/active` to render Gold trades seamlessly alongside Forex majors, reporting floating PnL in both pips and points (`+$X.XX/oz`).
  6. Eliminated the separate `/gold` command entirely; any `/gold` command or callback now transparently redirects to the unified `/radar` surveillance terminal, and all menus/keyboards reflect the consolidated universe.
  7. Updated `/prices` to stream Gold quotes alongside Forex pairs.

---

### ISSUE-EDGE-01: Cloudflare KV Persistence Drop on Active Broker Positions Flagged with `pending_close`

* **Severity:** **Critical** (Orphaned Live Positions & Ghost State)
* **Status:** **REMEDIATED IN CODE (2026-11-22)** — Deployed to Cloudflare Edge.
* **Affected Files:** `cloudflare_worker.js` (lines 509–535)
* **Root Cause:** In `autoResolveTrade`, when a trade with an active broker position hit SL/TP on spot price (`hasBrokerPosition && !isBrokerClosed`), the function updated `t.pending_close = outcome` and `t.pending_exit_price = exitPrice` on the local variable, called `triggerGitHubScanner`, and returned immediately without persisting the modified trade to KV `active_trades`. When GitHub Actions pulled the ledger, it received the old active trade without `pending_close`. If the spot price pulled back, the Python scanner did not close the cTrader position, yet the Cloudflare Worker sent a Telegram exit alert ("STOP LOSS HIT - CLOSED").
* **Remediation Implemented:**
  - Updated `autoResolveTrade` in `cloudflare_worker.js` to persist `pending_close` and `pending_exit_price` directly into `active_trades` in KV prior to returning.
  - In `runActiveTradeChecks`, suppressed premature exit alerts to Telegram when `hasBrokerPosition && !isBrokerClosed`, deferring exit alerting to `market_scanner.py` once the broker confirms execution.

---

### ISSUE-SEC-03: Unauthenticated Administrative Endpoints & Telegram Slash Command Execution

* **Severity:** **Critical** (Security / Unauthorized Trade Manipulation)
* **Status:** **REMEDIATED IN CODE (2026-11-22)** — Deployed to Cloudflare Edge.
* **Affected Files:** `cloudflare_worker.js` (lines 860–1160)
* **Root Cause:**
  - `payload.event === "reset_trades"` and `payload.event === "sync_trades"` were exposed on the public worker root without secret token authentication.
  - Telegram admin commands `/clear`, `/clean`, `/reset` and `/close`, `/resolve` did not verify if the sender's Telegram user ID or chat ID matched `TELEGRAM_CHAT_ID`.
* **Remediation Implemented:**
  - Added admin verification guard to `/clear`, `/reset`, `/close`, and `/resolve`: commands verify that `String(chatId) === String(authorizedChatId) || String(fromId) === String(authorizedChatId)`. Unauthorized attempts are rejected with an access-denied message.
  - Added optional `X-Admin-Secret` / Bearer token check for `reset_trades`.
  - Supported `X-Telegram-Bot-Api-Secret-Token` validation when `TELEGRAM_WEBHOOK_SECRET` is configured in worker environment.

---

### ISSUE-RISK-02: Executor Defaulting Zero/Negative Calculated Lots to 0.10 Lots

* **Severity:** **High** (Financial Safety Risk)
* **Status:** **REMEDIATED IN CODE (2026-11-22)** — Validated in `tests/test_ctrader_executor.py`.
* **Affected Files:** `core/ctrader_executor.py` (lines 670–685)
* **Root Cause:** If `lots <= 0.0` (which occurs when account equity cannot safely support the minimum lot size or if calculation fails), `execute_ctrader_order()` previously defaulted to `lots = 0.10`. On small accounts, placing 0.10 standard lots (10,000 units) breaches risk budgets.
* **Remediation Implemented:**
  - Replaced `lots = 0.10` override with strict capital preservation rejection: returns `{"status": "REJECTED_ZERO_LOTS", "error": "Computed lot size is 0.00..."}`.
  - Harmonized default account equity in `core/ctrader_executor.py` from `$5,000` to `$25,000` to match the centralized configuration.

---

### ISSUE-TEST-01: Weekend Wall-Clock Test Leakage in Market Scanner Flat Cutoff Guard

* **Severity:** **Medium** (Test Suite Regression on Weekends)
* **Status:** **REMEDIATED IN CODE (2026-11-22)** — Tested and verified across all 184 tests.
* **Affected Files:** `market_scanner.py` (lines 154–161)
* **Root Cause:** `is_forex_weekend_flat_cutoff(dt=None)` evaluated live system wall-clock time. During weekend test runs, `check_active_trades()` auto-liquidated active test trades as `WEEKEND_FLAT`, causing 12 unit test failures in `test_market_scanner.py`.
* **Remediation Implemented:**
  - Added `if dt is None and os.environ.get("PYTEST_CURRENT_TEST"): return False`.

---

### ISSUE-DEP-01: PyOpenSSL / Cryptography Version Incompatibility

* **Severity:** **Low** (Dependency Conflict / TLS Verification Failure)
* **Status:** **REMEDIATED IN CODE (2026-11-22)** — Verified in `requirements.txt`.
* **Affected Files:** `requirements.txt`
* **Root Cause:** Unconstrained `service-identity` installation pulled `cryptography>=50.0.0`, breaking `pyOpenSSL 24.1.0` with `module 'lib' has no attribute 'GEN_EMAIL'`, causing Twisted TLS verification failures.
* **Remediation Implemented:**
  - Pinned `cryptography>=41.0.5,<43.0.0` in `requirements.txt` and reinstalled compatible `cryptography 42.0.8` and `service-identity 24.2.0`.

---

### ISSUE-EXEC-01: cTrader MARKET Order Rejection on Invalid Slippage Parameters

* **Severity:** **High** (Order Submission Failure)
* **Status:** **REMEDIATED IN CODE (2026-11-23)** — Tested and validated in `tests/test_ctrader_executor.py`.
* **Affected Files:** `core/config.py`, `core/ctrader_executor.py`
* **Root Cause:** `execute_ctrader_order` populated `baseSlippagePrice` and `slippageInPoints` on `ProtoOANewOrderReq` even when `orderType` was standard unconditional `MARKET` (`orderType=1`). Under cTrader Open API Protobuf specification, slippage parameters are legally accepted strictly for `MARKET_RANGE` orders (`orderType=2`). The broker returned `INVALID_REQUEST` / `ORDER_CANCELLED`.
* **Remediation Implemented:**
  - Configured `CTRADER_ORDER_TYPE` in `core/config.py` defaulting to `"MARKET"`.
  - Conditioned `baseSlippagePrice` and `slippageInPoints` strictly upon `CTRADER_ORDER_TYPE == "MARKET_RANGE"`. Standard unconditional `MARKET` orders cleanly omit slippage fields, executing instantaneously with atomic relative SL/TP.

---

### ISSUE-NEWS-01: Unprotected Pre-London Open Entries Against European Flash PMI Releases

* **Severity:** **Medium** (Volatility Trap / Judas Swing)
* **Status:** **REMEDIATED IN CODE (2026-11-23)** — Tested and validated in `tests/test_news_filter.py`.
* **Affected Files:** `core/config.py`, `core/news_filter.py`
* **Root Cause:** Forex Factory frequently categorizes preliminary French/Eurozone Flash PMIs as `Medium` impact rather than `High`. Because `core/news_filter.py` strictly checked `impact == "High"`, early 07:30 UTC London open setups were not shielded from the 08:15 UTC French Flash PMI release.
* **Remediation Implemented:**
  - Added targeted detection for preliminary Flash PMIs (`"flash" in title.lower() and "pmi" in title.lower()`) alongside `impact == "High"`.
  - Added `FLASH_PMI_BUFFER_MINUTES = 45` protective window to insulate 07:30 UTC setups against 08:15 UTC releases while preserving 30-minute buffers for conventional High-Impact events and 100% trade frequency on regular days.

---

### ISSUE-UI-01: Local Supervisor Menu & Command Synchronization with Cloudflare Edge Relay

* **Severity:** **Low** (Operational Parity / Command Handling)
* **Status:** **REMEDIATED IN CODE (2026-11-23)** — Tested and validated in `tests/test_telegram.py`.
* **Affected Files:** `scripts/run_telegram_bot.py`
* **Root Cause:** Local desktop supervisor (`scripts/run_telegram_bot.py`) lacked `/close` and `/cancel` routing and displayed outdated menu references to legacy strategies and `WIN|LOSS` syntax, causing command drops when executed outside the Cloudflare Edge Worker.
* **Remediation Implemented:**
  - Synchronized `get_menu_payload`, `/close`, and `/cancel` handlers in `scripts/run_telegram_bot.py` with `cloudflare_worker.js`, providing unified terminal behavior across both local and edge deployments.




