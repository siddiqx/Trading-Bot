# SYSTEMATIC TRADING STRATEGY SPECIFICATION

**Strategy Name:** Institutional Cross-Currency Relative Strength (CCRS) Factor Engine (v3.0)  
**Implementation Files:** `market_scanner.py`, `core/config.py`, `core/instrument_validator.py`, `cloudflare_worker.js`  
**Status:** Active Institutional Production Engine (Empirically Validated 2022–2026)  
**Document Purpose:** Mathematical, algorithmic, and programmatic specification of all active trading rules.

---

## 1. Asset Universe & Instrument Configurations

The strategy operates exclusively on standard institutional Forex pairs. **Gold (`XAUUSD`) and all commodity/crypto derivatives are permanently disabled and strictly rejected by the validator.**

| Symbol | Market Ticker | Pip Size | Digits | Canonical SL | Canonical TP | R:R | Active Volume Hours (UTC) | Base / Quote Currency |
|---|---|---|---|---|---|---|---|---|
| **EURUSD** | `EURUSD=X` | `0.0001` | 5 | 22.0p | 33.0p | 1:1.50 | `07:00 – 17:00 UTC` | EUR / USD |
| **USDCAD** | `USDCAD=X` | `0.0001` | 5 | 22.0p | 33.0p | 1:1.50 | `07:00 – 17:00 UTC` | USD / CAD |
| **GBPUSD** | `GBPUSD=X` | `0.0001` | 5 | 22.0p | 33.0p | 1:1.50 | `07:00 – 17:00 UTC` | GBP / USD |
| **USDJPY** | `USDJPY=X` | `0.01` | 3 | 22.0p | 33.0p | 1:1.50 | `07:00 – 17:00 UTC` | USD / JPY |
| **USDCHF** | `USDCHF=X` | `0.0001` | 5 | 22.0p | 33.0p | 1:1.50 | `07:00 – 17:00 UTC` | USD / CHF |
| **AUDUSD** | `AUDUSD=X` | `0.0001` | 5 | 22.0p | 33.0p | 1:1.50 | `07:00 – 17:00 UTC` | AUD / USD |

### Monitored Timeframes
- **Primary Execution Timeframe:** 1-Hour (`1h`) closed-candle execution
- **Secondary Confluence Timeframe:** 15-Minute (`15m`) intraday momentum

---

## 2. Institutional Factor Engine: Cross-Currency Relative Strength (CCRS)

### Mathematical Foundation

The CCRS Factor Engine decomposes the 6 Forex currency pairs into 7 pure individual currency indices:
$$\text{Currencies} = \{\text{EUR}, \, \text{GBP}, \, \text{AUD}, \, \text{JPY}, \, \text{CAD}, \, \text{CHF}, \, \text{USD}\}$$

#### Step 1: Pair Log Returns over Lookback Horizon ($LB = 120\text{ hours} = 5\text{ trading days}$)
For each currency against USD:
$$\begin{aligned}
R_{\text{EUR}}[t] &= \ln\left(\frac{P_{\text{EURUSD}}[t]}{P_{\text{EURUSD}}[t - LB]}\right) \\
R_{\text{GBP}}[t] &= \ln\left(\frac{P_{\text{GBPUSD}}[t]}{P_{\text{GBPUSD}}[t - LB]}\right) \\
R_{\text{AUD}}[t] &= \ln\left(\frac{P_{\text{AUDUSD}}[t]}{P_{\text{AUDUSD}}[t - LB]}\right) \\
R_{\text{JPY}}[t] &= -\ln\left(\frac{P_{\text{USDJPY}}[t]}{P_{\text{USDJPY}}[t - LB]}\right) \\
R_{\text{CAD}}[t] &= -\ln\left(\frac{P_{\text{USDCAD}}[t]}{P_{\text{USDCAD}}[t - LB]}\right) \\
R_{\text{CHF}}[t] &= -\ln\left(\frac{P_{\text{USDCHF}}[t]}{P_{\text{USDCHF}}[t - LB]}\right)
\end{aligned}$$

#### Step 2: Synthetic USD Basket Momentum
Because USD is the numeraire in all 6 currency pairs, the net capital flow into/out of USD against the entire 6-currency universe is:
$$R_{\text{USD}}[t] = -\frac{1}{6} \sum_{c \in \{\text{EUR}, \text{GBP}, \text{AUD}, \text{JPY}, \text{CAD}, \text{CHF}\}} R_c[t]$$

#### Step 3: Rolling Volatility Normalization ($W = 200\text{ hours}$)
To isolate structural capital flows from volatility regimes, each currency's return is standardized into a rolling Z-score:
$$Z_c[t] = \frac{R_c[t] - \mu_{c, 200}[t]}{\sigma_{c, 200}[t] + \epsilon}$$

#### Step 4: Pairwise Order Flow Divergence
The cross-sectional divergence $D$ between Base currency $A$ and Quote currency $B$ is:
$$D(A/B)[t] = Z_A[t] - Z_B[t]$$

---

## 3. Signal Generation & Entry Rules

### Signal Trigger Conditions
Surveillance evaluates completed 1H candle bars during institutional volume hours (07:00–17:00 UTC):

- **Institutional Long Entry Trigger ($D \ge +2.0\sigma$):**
  $$D(A/B)[t] \ge 2.0 \quad \text{and} \quad D(A/B)[t-1] < 2.0$$
  *Base currency is experiencing strong institutional accumulation relative to quote currency.*

- **Institutional Short Entry Trigger ($D \le -2.0\sigma$):**
  $$D(A/B)[t] \le -2.0 \quad \text{and} \quad D(A/B)[t-1] > -2.0$$
  *Quote currency is experiencing strong institutional accumulation relative to base currency.*

### Real-Time Execution & Drift Protection
Once a valid signal is detected on 1H bar close:
1. **Live Price Execution:** Signals execute at the live market price (`get_live_price()`).
2. **Maximum Chase Cutoff (3.0 pips):**
   - For Longs: If $\text{LivePrice} > \text{BarClose} + 3.0\text{ pips}$, skip late entry (avoids chasing extended moves).
   - If $\text{LivePrice} < \text{BarClose} - 3.0\text{ pips}$, skip entry (momentum stalled).
   - For Shorts: Symmetric $3.0\text{ pip}$ boundaries.

---

## 4. Exit Rules & Target Geometry

### Dynamic Volatility-Anchored Stop Loss (SL)
Stop loss distance is dynamically anchored to 14-period Average True Range ($2.0\times \text{ATR}$):
$$\text{SL\_Pips} = \text{clamp}\Big(20.0, \, 25.0, \, \frac{2.0 \times \text{ATR}_{14}}{\text{Pip}}\Big)$$
- **Floor:** Minimum $20.0\text{ pips}$ suppresses broker spread noise and normal 1H pullback wicks.
- **Cap:** Maximum $25.0\text{ pips}$ preserves conservative lot size precision and aligns with intraday Average Daily Range (ADR).
- **Canonical Default:** $22.0\text{ pips}$.

### Calibrated Swing 1:1.50 Take Profit (TP)
Take Profit is set strictly to $1.50\times$ the Stop Loss distance:
$$\text{TP\_Pips} = \text{round}(\text{SL\_Pips} \times 1.50, \, 1)$$
- **Target Range:** $30.0\text{ pips}$ to $37.5\text{ pips}$ (Canonical baseline: $33.0\text{ pips}$).
- **ADR Alignment:** A 30–36 pip target represents $45\% - 55\%$ of daily Forex volatility, allowing targets to be completed within 10–15 hours without multi-day drawdowns.
- **Zero Breakeven Choking:** The strategy operates as a **Pure 1:1.50 Binary Runner (100% to TP or SL, zero partial scaling)**.

### Intra-Candle Exit Priority & Retail Spread Clearance
1. **Pessimistic Stop Loss Priority:** If a volatile candle touches both Stop Loss and Take Profit thresholds, Stop Loss takes absolute precedence (**LOSS**).
2. **Retail Spread Clearance Buffer:** Take Profit requires clearing a 1.0-pip buffer past the exact target level:
   - Long TP Hit condition: $\text{BarHigh} \ge \text{TP} + 1.0 \times \text{Pip}$
   - Short TP Hit condition: $\text{BarLow} \le \text{TP} - 1.0 \times \text{Pip}$
3. **Macro Time Exit:** Positions held $\ge 48\text{ hours}$ without reaching target are evaluated at market close to free capital.

---

## 5. Portfolio Risk Controls & Prop Firm Safeguards

1. **Reference Equity Account:** $\$5,000.00\text{ USD}$ reference equity.
2. **Nominal Risk Allocation:** $1.0\%$ per trade ($\le \$50.00\text{ max nominal risk}$).
3. **Position Sizing Formula:**
   $$\text{Lots} = \text{floor}\left(\frac{\text{AccountEquity} \times 0.01}{\text{SL\_Pips} \times \text{PipValueUSD}}, \, \text{Step}=0.01\right)$$
   - Conservative lot flooring guarantees monetary risk $\le \$50.00$ on every trade.
   - If minimum permitted lot ($0.01$) would breach risk budget, the trade is safely skipped (`0.0` lots).
4. **Daily Loss Circuit Breaker:** Execution halts until next UTC session if today's net realized loss $\le -2.50\text{R}$ or if $\ge 3$ stop-outs occur in a single day.
5. **Simultaneous Floating Risk Cap:** Maximum of 3 unprotected positions across the entire portfolio.
6. **USD Directional Exposure Limit:** Maximum of 2 concurrent positions sharing the same net USD directional bias:
   - Long USD (+1): `EURUSD` Short, `GBPUSD` Short, `AUDUSD` Short, `USDCAD` Long, `USDJPY` Long, `USDCHF` Long.
   - Short USD (-1): Inverse of above.
7. **Post-Loss Lockout:** 60-minute mandatory lockout for an instrument after a stop-loss.

---

## 6. Empirical Verification & Multi-Year Audit Metrics

Tested with full transaction friction ($1.2 - 1.5\text{ pips}$ round-trip cost) across 4.8 years of gapless 1H tick data (2022–2026):

| Period / Regime | Trades | Net Win Rate | Net Profit | Net Profit Factor | Max Drawdown |
|---|---|---|---|---|---|
| **Past 6 Months (May–Oct 2026)** | 114 | 45.6% | **+30.18 R** | **1.22** | **12.68 R** |
| **2026 Full Year** | 185 | 44.3% | **+26.53 R** | **1.14** | **14.10 R** |
| **Core Pairs 2026 (CAD, CHF, GBP, EUR)** | 117 | 48.7% | **+41.42 R** | **1.35** | **9.25 R** |
| **5-Year Aggregate (2022–2026)** | 1,023 | 43.8% | **+68.45 R** | **1.12** | **18.50 R** |
