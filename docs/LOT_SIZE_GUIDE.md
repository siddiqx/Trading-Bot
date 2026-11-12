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
1. When `execute_ctrader_order(sig)` is called, it inspects `sig["suggested_lots"]`.
2. It cross-checks `ACCOUNT_EQUITY` and `RISK_PCT` from runtime environment variables.
3. If `sig` was generated using a mismatched reference equity (e.g., $5,000 default when the live account is $25,000), `core/ctrader_executor.py` automatically recalculates the exact lot size before TLS dispatch, preventing under-sized low-profit executions.

### 5.2 How to Switch Account Tiers in 10 Seconds

#### Option A: Local / VPS Execution (`.env`)
Update your `.env` file with your target account equity and risk percentage:
```bash
# For a $25,000 Funded Account with 1.0% Risk ($250 per trade):
ACCOUNT_EQUITY=25000
RISK_PCT=1.00
ENABLE_CTRADER_EXECUTION=true

# For a $100,000 Funded Account with 0.50% Conservative Risk:
# ACCOUNT_EQUITY=100000
# RISK_PCT=0.50
```

#### Option B: GitHub Actions 24/7 Cloud Scanner
Navigate to **GitHub Repository $\rightarrow$ Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions** and configure:
* `ACCOUNT_EQUITY`: `25000`
* `RISK_PCT`: `1.00`
