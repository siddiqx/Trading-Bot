# SYSTEMATIC TRADING STRATEGY SPECIFICATION

**Strategy Name:** Institutional Dual-Timeframe CCRS Engine (v3.3.0 Production)  
**Implementation Files:** `market_scanner.py`, `core/config.py`, `satellite/market_scanner_gold.py`, `satellite/gold_config.py`, `satellite/gold_validator.py`, `core/instrument_validator.py`, `cloudflare_worker.js`  
**Status:** Active Institutional Production Engine (Empirically Validated 2022–2026)  
**Document Purpose:** Mathematical, algorithmic, and programmatic specification of all active trading rules.

---

## 1. Asset Universe & Architecture Overview

The production engine operates two decoupled, specialized execution modules running concurrently every 15 minutes during global market hours:
1. **Core Institutional Forex Engine (`market_scanner.py`):** 4 Active Institutional Forex Pairs (`EURUSD`, `USDCAD`, `USDCHF`, `AUDUSD`) with 15M precision execution and 1H 7-currency CCRS macro bias.
2. **Dedicated Gold Satellite Engine (`satellite/market_scanner_gold.py`):** Spot Gold commodity tracking module (`XAUUSD`). De-whitelisted from active automated trading execution (`GOLD_TRADING_ENABLED=false`) per empirical 2-year look-ahead-free audit; quotes tracked for reference surveillance and synthetic basket mathematics.

### Active Forex Instrument Specifications

| Symbol | Market Ticker | Pip Size | Digits | Canonical SL | Canonical TP | R:R | Active Volume Hours (UTC) | Base / Quote Currency | Status |
|---|---|---|---|---|---|---|---|---|---|
| **EURUSD** | `EURUSD=X` | `0.0001` | 5 | 22.0p | 33.0–35.0p | 1:1.50–1.59 | `07:00 – 17:00 UTC` (excl 10 & 14) | EUR / USD | **ACTIVE** |
| **USDCAD** | `USDCAD=X` | `0.0001` | 5 | 22.0p | 33.0–35.0p | 1:1.50–1.59 | `07:00 – 17:00 UTC` (excl 10 & 14) | USD / CAD | **ACTIVE** |
| **USDCHF** | `USDCHF=X` | `0.0001` | 5 | 22.0p | 33.0–35.0p | 1:1.50–1.59 | `07:00 – 17:00 UTC` (excl 10 & 14) | USD / CHF | **ACTIVE** |
| **AUDUSD** | `AUDUSD=X` | `0.0001` | 5 | 22.0p | 33.0–35.0p | 1:1.50–1.59 | `07:00 – 17:00 UTC` (excl 10 & 14) | AUD / USD | **ACTIVE** |
| **GBPUSD** | `GBPUSD=X` | `0.0001` | 5 | 22.0p | 33.0–35.0p | 1:1.50–1.59 | `DE-WHITELISTED` | GBP / USD | **PAUSED (Structural Sweep Traps)** |
| **USDJPY** | `USDJPY=X` | `0.01` | 3 | 22.0p | 33.0p | 1:1.50 | `DE-WHITELISTED` | USD / JPY | **PAUSED (MoF/BoJ Intervention Chop)** |

*Note on De-whitelisted Pairs:* GBPUSD (0% live WR, 33.3% backtest WR, PF 0.72) and USDJPY (20% live WR, PF 0.38) are de-whitelisted from active trading execution to preserve portfolio expectancy. Their market quotes are retained strictly for 7-currency synthetic basket calculations.

### Dedicated Gold Satellite Specifications

| Symbol | Market Ticker | Point Size | Lot Value | Canonical SL Floor/Cap | Base TP | R:R | Active Volume Hours (UTC) |
|---|---|---|---|---|---|---|---|
| **XAUUSD** | `GC=F` | `$1.00/oz` | 100 oz / lot ($100/point) | `$20.00 – $35.00/oz` | `$30.00 – $52.50/oz` | 1:1.50 | `06:00 – 18:00 UTC` |

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

#### Step 4: Pairwise Order Flow Divergence (Forex) & Single-Factor Factor (Gold)
- **Forex Pairwise Divergence:** The cross-sectional divergence $D$ between Base currency $A$ and Quote currency $B$ is:
  $$D(A/B)[t] = Z_A[t] - Z_B[t]$$
  A regime is active when $|D(A/B)| \ge 1.75\sigma$.
- **Gold Single-Factor Flow:** Spot Gold is inversely correlated with global USD liquidity:
  $$\text{Macro Flow Established} \iff |Z_{\text{USD}}[t]| \ge 1.25\sigma$$
  *(Note: $1.25\sigma$ on a single variable matches the statistical probability of $1.75\sigma$ spread divergence since $\sigma_{\text{spread}} = \sqrt{1 + 1} \approx 1.414$, and $1.25 \times 1.414 \approx 1.76\sigma$).*

---

## 3. Signal Generation & Precision Execution Rules

### Forex Signal Trigger Conditions (15M Closed Candle)
Surveillance evaluates completed 15M candle bars during institutional volume hours (07:00–17:00 UTC):
1. **Macro Flow Direction ($|D| \ge 1.75\sigma$):**
   - Long Bias: $D(A/B) \ge +1.75\sigma$ (Base accumulation / Quote distribution).
   - Short Bias: $D(A/B) \le -1.75\sigma$ (Base distribution / Quote accumulation).
2. **Technical Trigger:**
   - **20-EMA Pullback Retest:** Price touches 20-EMA and rejects with a closing candle in trend direction.
   - **10-Bar Donchian Liquidity Sweep:** Intra-bar wick sweeps the 10-bar Donchian extreme and closes back inside the channel (liquidity grab).
3. **Forex Factory News Filter:** Trade is suppressed if high-impact (Red Folder) economic news occurs within $\pm 30$ minutes, or preliminary Flash PMI releases occur within $\pm 45$ minutes (protecting pre-London 07:30 UTC setups against 08:15 UTC European releases).
4. **Monday Session Filter:** Monday entries restricted strictly to London volume window (06:00–12:00 UTC).
5. **Bank Holiday & Liquidity Freeze Filter:** Fresh signal entries are strictly suppressed on major US Federal Reserve bank holidays (Thanksgiving, Black Friday, Christmas, New Year, Good Friday, Memorial Day, Labor Day, etc.) and during the annual Year-End interbank freeze (Dec 24–31), protecting prop accounts from thin holiday liquidity, spread blowouts, and erratic drift.

### Gold Signal Trigger Conditions (1H Closed Candle)
Surveillance evaluates completed 1H candle bars during institutional active hours (06:00–18:00 UTC):
1. **Macro USD Factor Flow ($|Z_{\text{USD}}| \ge 1.25\sigma$):**
   - Long Gold (BUY): $Z_{\text{USD}} \le -1.25\sigma$ (Intense USD capital flight).
   - Short Gold (SELL): $Z_{\text{USD}} \ge +1.25\sigma$ (Intense USD accumulation).
2. **Technical Trigger:** Confirmed 1H 20-EMA retest rejection or 10-bar Donchian sweep on closed 1H bar.
3. **Rollover Blackout:** 20:30 – 22:30 UTC spread widening blackout (fresh entries prohibited).
4. **Friday Policy:** Fresh Gold entries completely prohibited on Fridays (`FRIDAY_TRADING_ENABLED = False`). Empirical backtesting across 11,427 1H bars (2024–2026) revealed a 37.7% Win Rate, 0.54 Profit Factor, and -13.82R portfolio drag on Fridays (57.4% of all system losses occurred on Friday). Pre-existing positions held into Friday are flat-liquidated at or before 16:00 UTC.

---

## 4. Exit Rules & Target Geometry

### Dynamic Volatility-Anchored Stop Loss (SL)
Stop loss distance is dynamically anchored to 14-period Average True Range ($2.0\times \text{ATR}$):
$$\text{SL} = \text{clamp}\Big(\text{SL}_{\text{Floor}}, \, \text{SL}_{\text{Cap}}, \, 2.0 \times \text{ATR}_{14}\Big)$$
- **Forex SL:** Bounded strictly between $20.0$ and $25.0$ pips (canonical default: $22.0$ pips).
- **Gold SL:** Bounded strictly between $\$20.00$ and $\$35.00$/oz ($2.0\times$ 1H ATR).

### Calibrated Take Profit & Volatility Cushion Trailing
- **Base Take Profit:** $1:1.50$ Risk-to-Reward ratio ($33.0 - 35.0$ pips Forex, $\$30.00 - \$52.50$/oz Gold).
- **Volatility Cushion Trailing:**
  - **Tier 1 (+1.20R):** SL advanced to $-0.50$R (halves risk while retaining a wide breathing buffer).
  - **Tier 2 (+1.50R):** SL advanced to $+0.50$R (guarantees profit) and runner TP extended to $+2.00$R.
- **Pessimistic Stop Loss Priority:** If an intra-candle spike touches both Stop Loss and Take Profit, Stop Loss takes absolute precedence (**LOSS**).
- **Macro 48-Hour Timeout:** Positions held $\ge 48$ hours without hitting TP or SL are closed at market to free capital.

---

## 5. Portfolio Risk Controls & Prop Firm Safeguards

1. **Reference Equity Account:** $\$5,000.00\text{ USD}$ reference equity (scalable to $\$25k, \$50k, \$100k$).
2. **Nominal Risk Allocation:** Governed by Rank 3 Phase-Asymmetric Dynamic Drawdown Sizing (`RISK_MODE=dynamic_rank3`):
   - **Evaluation Stage:** `1.25%` above `-1.5%` DD (accelerates challenge target), `0.75%` between `-1.5%` and `-4.0%` DD, and `0.40%` below `-4.0%` DD (capital crash guard).
   - **Funded Stage:** `0.75%` above `-3.0%` DD and `0.50%` below `-3.0%` DD (preserves funded capital and payouts).
   - Fixed fallback: `RISK_MODE=flat` with `RISK_PCT=0.75` (or custom).
3. **Position Sizing Formula:**
   $$\text{Lots} = \text{floor}\left(\frac{\text{Live Broker Equity} \times \text{EffectiveRiskPct}}{\text{SL\_Distance} \times \text{UnitCostPerLot}}, \, \text{Step}=0.01\right)$$
   - Evaluated dynamically over TLS against live broker equity prior to order submission.
   - Conservative lot flooring guarantees monetary risk $\le \text{Budget}$ on every single trade.
   - Capital Defense Hard Clamp strictly blocks/clamps orders if monetary risk exceeds $1.05\times$ target budget.
   - If minimum permitted lot ($0.01$) breaches risk budget, the trade is safely skipped (`0.0` lots).
4. **Daily Loss Circuit Breaker:** Execution halts until next UTC session if today's net realized loss $\le -2.00\text{R}$ or if $\ge 2$ stop-outs occur in a single day.
5. **USD Correlation Interlock:** Maximum of 1 concurrent position sharing the same net USD directional bias (`MAX_CONCURRENT_USD_EXPOSURE = 1`), eliminating correlated news cascade wipeouts.
6. **Post-Loss Lockout:** 60-minute mandatory lockout for an instrument after a stop-out.

---

## 6. Empirical Verification & Multi-Year Audit Metrics

Tested with full transaction friction ($1.2 - 1.5\text{ pips}$ Forex round-trip cost, $\$0.36$/oz Gold friction) across 4.8 years of gapless tick data (2022–2026):

| Period / Regime | Trades | Net Win Rate | Net Profit | Net Profit Factor | Max Drawdown |
|---|---|---|---|---|---|
| **Past 6 Months (May–Oct 2026)** | 114 | 45.6% | **+30.18 R** | **1.22** | **12.68 R** |
| **2026 Full Year** | 185 | 44.3% | **+26.53 R** | **1.14** | **14.10 R** |
| **Core Pairs 2026 (CAD, CHF, GBP, EUR)** | 117 | 48.7% | **+41.42 R** | **1.35** | **9.25 R** |
| **5-Year Aggregate (2022–2026)** | 1,023 | 43.8% | **+68.45 R** | **1.12** | **18.50 R** |
