# BACKTESTING METHODOLOGY & QUANTITATIVE VALIDATION FRAMEWORK

**Document Version:** 1.0.0  
**Scope:** Historical Simulation Integrity, Data Cleansing, Execution Assumptions, and Out-of-Sample Validation Standards

---

## 1. Historical Market Data Sources & Integrity

The trading bot repository currently contains two distinct market data streams for research and live scanning:

### A. Live Feed (Yahoo Finance REST API)
* **Endpoint:** `https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range}&interval={interval}`
* **Coverage:** Real-time 5-minute, 15-minute, and 1-hour OHLCV candles covering the most recent 7 days.
* **Cleaning Protocol:**
  - Missing ticks and null prices (`open`, `high`, `low`, `close`) are dropped via `df.dropna()`.
  - UTC timestamp normalization: Unix epochs converted to timezone-aware UTC datetime.
  - Sorting: Guaranteed chronological order (`df.sort_values('time')`).
  - Bar Close Calculation: In Yahoo Finance, the candle timestamp corresponds to the **bar open**. The scanner explicitly calculates `df['close_time'] = df['time'] + pd.Timedelta(minutes=15)` and verifies that `close_time <= now_utc` to ensure bars are closed before signal evaluation.

### B. Historical Backtest Cache (`archives/portfolio_8pairs_cache.pkl`)
* **File Format:** Serialized Python binary pickle (5.48 MB).
* **Contents:** Dictionary of DataFrames keyed by symbol (`EURUSD`, `USDCAD`, `GBPUSD`, `USDJPY`, `USDCHF`, `AUDUSD`, `NZDUSD`, `XAUUSD`).
* **Integrity Audit:**
  - Provenance: Unspecified external export. Timestamps and tick volumes are unverified against institutional broker tick data.
  - Coverage: Extends over approximately 1 to 2 years of 1-hour candle data.
  - Limitation: Not versioned in Git (tracked in `.gitignore` under `*.pkl`), making backtest reproducibility non-deterministic across fresh clones unless the archive is present.

---

## 2. Temporal Correctness & Look-Ahead Bias Auditing

A backtest is invalid if calculations access information that was not available at the execution decision point.

### Audited Invariants in Code
1. **Indicator Lag Invariance (PASSED in `market_scanner.py`):**
   Donchian channel channels strictly use `high.shift(1).rolling(N).max()`. The current candle's high/low is not included in the breakout channel boundary.
2. **Fractal Swing Centering (PASSED in `market_scanner.py`):**
   ICT 10-bar swing highs/lows use `rolling(15, center=True).max().shift(8)`. Shifting by 8 bars ensures that the center bar of a 15-bar window is only confirmed 8 bars after it occurred.
3. **Look-Ahead Flaw in Research Script (DEFECT in `scripts/simulate_prop_firm_5k.py`):**
   In `scripts/simulate_prop_firm_5k.py` (lines 18–20):
   ```python
   forward_window = min(n, k + 12)
   pullback_depth = highs[k] - float(np.min(lows[k:forward_window]))
   ```
   When filtering historical swing highs, the function peeks 12 bars into the future (`k:forward_window`) to determine whether a pullback occurred before accepting the level as a valid target. This constitutes **future-data leakage** in that specific simulation script.

---

## 3. Execution Realism & Order Modelling

### Bid / Ask Spread Modelling
* **Market Orders:** In reality, long market orders execute at the Ask price, while short market orders execute at the Bid price.
* **Scanner Realism:** `market_scanner.py` implements a **1.0-pip retail spread clearance buffer** on Take Profit orders:
  - Long Take Profit requires $\text{High} \ge \text{TP} + 1.0\text{ pip}$.
  - Short Take Profit requires $\text{Low} \le \text{TP} - 1.0\text{ pip}$.
  This prevents false-positive win declarations on bars that merely touched the target bid price without clearing the broker's spread.
* **Backtest Scripts:** Ad-hoc scripts (`simulate_prop_firm_5k.py`) do not deduct spread, overstating win rates by approximately 3–6%.

### Intra-Candle Stop-Loss vs. Take-Profit Collision
When backtesting on OHLC data, if a single candle's range encompasses both the Stop Loss and the Take Profit prices, it is impossible to know with certainty which level was touched first without tick or 1-minute data.

* **Audit Finding:** `market_scanner.py` (lines 569, 604, 622) and `simulate_prop_firm_5k.py` (line 146) both implement **pessimistic execution priority**:
  ```python
  if hit_tp and hit_sl:
      hit_tp = False  # Stop Loss takes absolute precedence
  ```
  This is a sound, conservative engineering decision that avoids inflating strategy performance.

### Slippage & Latency
* The backtest scripts assume zero execution slippage.
* In live market execution during high-impact news (e.g. US CPI, NFP), slippage on market orders and stop losses can widen by 2 to 10 pips.

---

## 4. Accounting & Performance Metric Definitions

System metrics must be computed strictly and consistently:

### 1. R-Multiple ($R$)
Realized trade return normalized by the initial risk distance:
$$\text{Realized } R = \frac{\text{Exit Price} - \text{Entry Price}}{\text{Entry Price} - \text{Stop Loss}} \quad (\text{for Longs})$$
$$\text{Realized } R = \frac{\text{Entry Price} - \text{Exit Price}}{\text{Stop Loss} - \text{Entry Price}} \quad (\text{for Shorts})$$

### 2. Expectancy per Trade ($\mathbb{E}[R]$)
$$\mathbb{E}[R] = (W \times \bar{R}_W) - (L \times \bar{R}_L)$$
Where $W$ is the win rate, $\bar{R}_W$ is the average winning trade return in R, $L = 1 - W$ is the loss rate, and $\bar{R}_L$ is the average loss in R.

### 3. Maximum Drawdown (MDD)
Calculated from peak equity to subsequent trough:
$$\text{MDD}_t = \max_{\tau \in [0, t]} (\text{Equity}_\tau) - \text{Equity}_t$$

### 4. Maximum Favorable Excursion (MFE) & Maximum Adverse Excursion (MAE)
* **MFE:** The highest floating profit in pips reached during the trade duration.
* **MAE:** The deepest floating drawdown in pips experienced during the trade duration.

---

## 5. Forward-Testing Validation Protocol

To guard against curve-fitting and selection bias, the system follows a **Frozen Forward-Test Protocol**:

1. **Rulebook Freeze:** Strategy rules were frozen on **2026-10-02** (commit `9184be7`). No indicator parameters, timeframe inputs, or thresholds may be modified until out-of-sample forward testing accumulates at least $N \ge 50$ live trades.
2. **Atomic Trade Logging:** Every trade alert generated in production is recorded atomically in `trade_records.json` and mirrored in Cloudflare Worker KV.
3. **Volume Partitioning (100-Trade Volumes):** Trades are partitioned into sequential volumes of 100 trades (`data/patterns/volumes/`). Post-mortem diagnostics analyze loss factors (`STRUCTURAL_INVALIDATION`, `PREMATURE_REVERSAL`, `MOMENTUM_EXHAUSTION`) across each completed volume to detect regime decay before revising parameters.

---

## 6. Offline Backtest Reproduction Instructions

To reproduce the historical simulation in a clean Python 3.11/3.12 environment:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Verify archive file exists
# Expected location: archives/portfolio_8pairs_cache.pkl (5.48 MB)

# 3. Run $5,000 prop firm challenge simulation
python scripts/simulate_prop_firm_5k.py

# 4. Run multi-phase progression simulation
python scripts/simulate_prop_firm_phases.py

# 5. Run forward validation tracker
python scripts/forward_test_tracker.py --markdown
```
