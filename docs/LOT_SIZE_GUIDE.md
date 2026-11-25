# Quantitative Position Sizing & Lot Size Allocation Architecture

> **Authoritative Specification & Runtime Guide**  
> Governs: Standalone Market Scanner (`market_scanner.py`), Gold Satellite Engine (`satellite/market_scanner_gold.py`), cTrader Automated Execution Engine (`core/ctrader_executor.py`), and Instrument Validator (`core/instrument_validator.py`).

---

## 1. Executive Summary & Core Mathematical Principles

The trading engine utilizes **Dynamic Volatility-Anchored Position Sizing** governed by three non-negotiable financial safety invariants:

1. **Strict Capital Preservation:** Monetary risk per trade is strictly capped by the risk budget:
   $$\text{Budget}_{\text{USD}} = \text{Account Equity} \times \left(\frac{\text{Risk \%}}{100}\right)$$
2. **Quote-to-USD Currency Alignment:** Standard lot pip values vary significantly across quote currencies. Position sizing converts pip values into USD in real time:
   $$\text{Pip Value}_{\text{USD}} = \begin{cases} 
   \$10.00 & \text{Direct USD Quote (EURUSD, GBPUSD, AUDUSD)} \\
   \frac{10.00}{\text{Exchange Rate}} & \text{USD Base Pairs (USDCAD, USDCHF)} \\
   \frac{1,000}{\text{USDJPY Rate}} & \text{USDJPY (JYP Quote Currency)}
   \end{cases}$$
3. **Conservative Lot-Step Flooring:** Raw lots are floored to the nearest `0.01` lot increment (`math.floor(raw_lots / 0.01) * 0.01`). Rounding never rounds up, guaranteeing monetary risk never exceeds the configured dollar budget.
4. **Zero-Budget Breach Guard:** If the minimum permitted broker lot (`0.01` lot) would exceed `1.50x` of the dollar risk budget, the trade is safely rejected.

---

## 2. Prop Firm & Funded Account Allocation ($5,000 to $100,000)

Prop firm challenges (FTMO, FundedNext, Alpha Capital, The5ers) enforce strict Daily Drawdown caps (typically 4% to 5%) and Total Drawdown caps (8% to 10%).

### 2.1 Standard Prop Firm Sizing: 1.00% Risk per Trade
*Optimal for challenge phases (8% to 10% target in 5 to 7 net winning trades).*

| Account Equity | Risk Budget (1.0%) | EURUSD, GBPUSD, AUDUSD | USDCAD (Rate ~1.424) | USDJPY (Rate ~158.9) | USDCHF (Rate ~0.825) | XAUUSD Gold (25pt SL) | Take Profit (+35p / +37.5pt) | Account Gain per Win |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$5,000** | **$50.00** | 0.22 lots ($48.40) | 0.32 lots ($49.44) | 0.36 lots ($49.84) | 0.18 lots ($48.00) | 0.02 lots ($50.00) | **+$77.00 to +$79.30** | **+1.58%** |
| **$10,000** | **$100.00** | 0.45 lots ($99.00) | 0.64 lots ($98.88) | 0.72 lots ($99.69) | 0.37 lots ($98.67) | 0.04 lots ($100.00) | **+$157.30 to +$158.60** | **+1.58%** |
| **$25,000** | **$250.00** | **1.13 lots** ($248.60) | **1.61 lots** ($248.75) | **1.80 lots** ($249.21) | **0.93 lots** ($248.00) | **0.10 lots** ($250.00) | **+$395.50 to +$396.50** | **+1.58%** |
| **$50,000** | **$500.00** | 2.27 lots ($499.40) | 3.23 lots ($499.05) | 3.61 lots ($499.81) | 1.87 lots ($498.67) | 0.20 lots ($500.00) | **+$793.95 to +$795.15** | **+1.59%** |
| **$100,000** | **$1,000.00** | 4.54 lots ($998.80) | 6.47 lots ($999.65) | 7.22 lots ($999.62) | 3.75 lots ($1,000.0) | 0.40 lots ($1,000.00) | **+$1,589.00 to +$1,590.35** | **+1.59%** |

---

### 2.2 Conservative Funded Account Sizing: 0.50% Risk per Trade
*Recommended for Stage 2 / Funded live accounts prioritizing zero breach over speed.*

| Account Equity | Risk Budget (0.50%) | EURUSD, GBPUSD, AUDUSD | USDCAD (Rate ~1.424) | USDJPY (Rate ~158.9) | USDCHF (Rate ~0.825) | XAUUSD Gold (25pt SL) | Take Profit (+35p / +37.5pt) | Account Gain per Win |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$5,000** | **$25.00** | 0.11 lots ($24.20) | 0.16 lots ($24.72) | 0.18 lots ($24.92) | 0.09 lots ($24.00) | 0.01 lots ($25.00) | **+$38.50 to +$39.65** | **+0.79%** |
| **$10,000** | **$50.00** | 0.22 lots ($48.40) | 0.32 lots ($49.44) | 0.36 lots ($49.84) | 0.18 lots ($48.00) | 0.02 lots ($50.00) | **+$77.00 to +$79.30** | **+0.79%** |
| **$25,000** | **$125.00** | **0.56 lots** ($123.20) | **0.80 lots** ($123.60) | **0.90 lots** ($124.61) | **0.46 lots** ($122.67) | **0.05 lots** ($125.00) | **+$196.00 to +$198.24** | **+0.79%** |
| **$50,000** | **$250.00** | 1.13 lots ($248.60) | 1.61 lots ($248.75) | 1.80 lots ($249.21) | 0.93 lots ($248.00) | 0.10 lots ($250.00) | **+$395.50 to +$396.48** | **+0.79%** |
| **$100,000** | **$500.00** | 2.27 lots ($499.40) | 3.23 lots ($499.05) | 3.61 lots ($499.81) | 1.87 lots ($498.67) | 0.20 lots ($500.00) | **+$794.50 to +$795.15** | **+0.79%** |

---

## 3. Retail & Micro Accounts ($100 to $1,000 USD)

Standard ECN brokers enforce a minimum order volume of **0.01 lots** (1 micro-lot = 1,000 units for Forex, 1 Troy Ounce for Gold).

### 3.1 Mathematical Constraints for Small Accounts
- **EURUSD 0.01 lot = $0.10 per pip.** With a 22-pip stop, the minimum loss is **$2.20**.
- **Gold 0.01 lot = $1.00 per point.** With a 25-point stop, the minimum loss is **$25.00**.

| Account Equity | Intended Risk % | Dollar Budget | Forex 0.01 Lot Risk | Forex Action | Gold 0.01 Lot Risk | Gold Action | Recommendation |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$100** | 1.0% | $1.00 | $2.20 (2.2%) | ⚠️ Rejected by Guard | $25.00 (25.0%) | 🚫 Rejected by Guard | Use Cent Account (10,000 USC) |
| **$100** | 2.5% | $2.50 | $2.20 (2.2%) | ✅ Traded (0.01 lot) | $25.00 (25.0%) | 🚫 Rejected by Guard | Forex only (Micro-lot) |
| **$200** | 1.5% | $3.00 | $2.20 (1.1%) | ✅ Traded (0.01 lot) | $25.00 (12.5%) | 🚫 Rejected by Guard | Forex only |
| **$500** | 1.0% | $5.00 | $4.40 (0.88%) | ✅ Traded (0.02 lot) | $25.00 (5.0%) | ⚠️ High Risk (0.01 lot) | Forex recommended |
| **$1,000** | 1.0% | $10.00 | $8.80 (0.88%) | ✅ Traded (0.04 lot) | $25.00 (2.5%) | ⚠️ Permitted at 2.5% risk | Full universe unlocked |

> [!IMPORTANT]
> **Cent Account Solution for Sub-$500 Accounts:**
> For personal accounts between $100 and $500, depositing into a **Cent Account** (where $100 = 10,000 USC) enables 0.01 cent-lots ($0.001/pip), perfectly aligning institutional 1.0% risk budgeting ($1.00 risk) without budget breach rejections.

---

## 4. Commodity Geometry: Gold (XAUUSD) Contract Math

| Specification | Standard Institutional Lot (1.0) | Broker Micro-Lot (0.01) |
| :--- | :--- | :--- |
| **Contract Size** | 100 Troy Ounces | 1.0 Troy Ounce |
| **Value per $1.00 move** | **$100.00 USD** | **$1.00 USD** |
| **Dynamic ATR Stop (25 pts)** | **$2,500.00 loss** | **$25.00 loss** |
| **Target Exit (+37.5 pts / 1.5R)** | **+$3,750.00 profit** | **+$37.50 profit** |
| **Round-Turn Total Friction** | $36.00 / lot ($0.36/oz) | $0.36 / micro-lot |

---

## 5. cTrader Execution Engine Dynamic Alignment

The cTrader executor (`core/ctrader_executor.py`) enforces dynamic equity and risk budget synchronization.

### 5.1 Runtime Resolution Workflow
1. When `execute_ctrader_order(sig)` is called, it inspects live broker equity directly via `get_ctrader_account_equity()`.
2. Sizing resolution priority:
   - **Priority 1 (Authoritative):** Live broker equity queried over TLS from cTrader Open API (`ProtoOATraderRes` balance + floating P&L).
   - **Priority 2:** Explicit `ACCOUNT_EQUITY` environment variable if configured.
   - **Priority 3:** Signal equity embedded at scan time by `market_scanner.py`.
   - **Priority 4:** Default reference equity ($5,000 USD).
3. **Capital Defense Hard Clamp:** Before TLS order submission, the executor calculates the exact dollar risk of `lots` given `sl_pips` and current exchange rate. If `monetary_risk > target_budget * 1.05`, the order is clamped down to the exact risk budget. If clamped risk still exceeds the ceiling, the trade is rejected with `REJECTED_RISK_BUDGET_BREACH`, guaranteeing zero oversized lot execution.

### 5.2 How to Switch Account Tiers in 10 Seconds

#### Option A: Local / VPS Execution (`.env`)
Update your `.env` file with your target account equity and risk percentage:
```bash
# For a $5,000 Prop Firm Challenge (Default):
ACCOUNT_EQUITY=5000.0
RISK_PCT=1.00  # $50.00 risk per trade (or 0.50 for $25.00)
ENABLE_CTRADER_EXECUTION=true

# For a $25,000 Funded Account with 1.0% Risk ($250 per trade):
# ACCOUNT_EQUITY=25000.0
# RISK_PCT=1.00

# For a $100,000 Funded Account with 0.50% Conservative Risk ($500 per trade):
# ACCOUNT_EQUITY=100000.0
# RISK_PCT=0.50
```

#### Option B: GitHub Actions 24/7 Cloud Scanner
Navigate to **GitHub Repository $\rightarrow$ Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions** and configure:
* `ACCOUNT_EQUITY`: `5000.0`
* `RISK_PCT`: `1.00`

---

## 6. Rank 3 Phase-Asymmetric Dynamic Sizing Architecture (Production Default)

To maximize evaluation speed while prioritizing funded capital survival, the bot implements **Rank 3 Phase-Asymmetric Dynamic Drawdown Sizing** in `core/config.py` (`resolve_effective_risk_pct`) and `core/ctrader_executor.py`.

### 6.1 Drawdown Tier Matrix

$$\text{Drawdown \%} = \frac{\text{Live Equity} - \text{Initial Balance}}{\text{Initial Balance}} \times 100$$

| Account Stage | Current Drawdown Range | Effective Risk % | $5,000 Risk Budget | Win Payout (+1.59R) | Strategic Rationale |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`EVALUATION`** | **DD $\ge -1.50\%$** (Profit or mild DD) | **`1.25%`** | **$62.50** | **+$99.38** | Fast-tracks Step 1 (8–10% target in ~5–6 net wins) and Step 2 (5% in ~3 net wins). |
| **`EVALUATION`** | **$-1.50\% > \text{DD} \ge -4.00\%$** (Moderate DD) | **`0.75%`** | **$37.50** | **+$59.63** | Preserves buffer below 5.0% max daily loss ceiling. |
| **`EVALUATION`** | **$\text{DD} < -4.00\%$** (Near Max DD) | **`0.40%`** | **$20.00** | **+$31.80** | Crash guard: requires 15 consecutive stop-outs to breach 10.0% max limit. |
| **`FUNDED`** | **DD $\ge -3.00\%$** (Buffer zone) | **`0.75%`** | **$37.50** | **+$59.63** | Balanced risk maximizing monthly payout expectancy while ensuring long-term funded survival. |
| **`FUNDED`** | **$\text{DD} < -3.00\%$** (Defense zone) | **`0.50%`** | **$25.00** | **+$39.75** | Maximum safety dampener protecting funded account status. |

### 6.2 Sizing Configuration Parameters

```bash
# In .env or GitHub Actions Secrets:
RISK_MODE=dynamic_rank3       # "dynamic_rank3" (default) or "flat" (fallback to fixed RISK_PCT)
ACCOUNT_STAGE=EVALUATION      # "EVALUATION" (1.25%/0.75%/0.40%) or "FUNDED" (0.75%/0.50%)
INITIAL_BALANCE=5000.0        # Initial starting account tier (auto-inferred from live equity if omitted)
```

### 6.3 Dynamic Broker Pre-Flight Recalculation
Before any market order is transmitted to Spotware cTrader Open API over TLS:
1. `_dispatch_order_over_socket()` queries current live equity directly from broker.
2. `resolve_effective_risk_pct()` dynamically computes the exact risk percentage for the current drawdown tier.
3. Lots are dynamically recalculated:
   $$\text{Lots} = \text{floor}\left( \frac{\text{Live Equity} \times \text{Risk \%}}{\text{SL Pips} \times \text{Pip Value USD} \times 0.01} \right) \times 0.01$$
4. Capital Defense Hard Clamp verifies `monetary_risk <= target_budget * 1.05`. If compliant, the order is dispatched immediately.
