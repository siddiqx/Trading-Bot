# INSTITUTIONAL PROP FIRM PRODUCTION & ANTI-BAN GUIDE

> **Target Audience:** Traders deploying the Institutional Dual-Timeframe CCRS Trading Bot (v3.3.0) on Proprietary Trading Firm evaluation challenges and funded accounts (FTMO, FundedNext, Alpha Capital, The 5%ers, Topstep, etc.).
> **Scope:** Comprehensive audit of prop firm ban triggers, copy-trading detection mechanisms, automated defensive shields, and recommended risk settings.

---

## 1. Executive Summary: Why Prop Firms Ban Accounts

Proprietary trading firms employ advanced risk surveillance systems (such as *RiskOps*, *OneZero*, and *BridgeEngine*) to monitor trader activity. Risk desks automatically flag and disqualify accounts based on 9 specific violations:

1. **Commercial Copy Trading / Group Trading Flags:** Multiple unrelated accounts executing identical trades at the exact same second with the same ticket comment or EA magic numbers.
2. **News Trading Violations:** Executing trades within 2 to 5 minutes before or after high-impact macroeconomic events (NFP, CPI, FOMC).
3. **Weekend Gap Violations:** Holding open positions past Friday close into Sunday open on standard challenge accounts.
4. **Daily Drawdown Breach:** Losing 4.0% to 5.0% of starting balance or equity in a single UTC day.
5. **Maximum Drawdown Breach:** Accumulating 8.0% to 10.0% overall trailing or static loss.
6. **Latency Arbitrage & Tick Scalping:** Opening and closing trades in under 30 to 60 seconds.
7. **Grid / Martingale / Toxic Flow:** Doubling position size on losing trades or opening uncontrolled multi-lot grids.
8. **Rollover Spread Traps:** Executing during the 21:00–23:00 UTC interbank rollover when spreads widen 500% to 1000%.
9. **IP Hopping & Proxy Flagging:** Accessing accounts through commercial VPN data-center proxies flagged by broker fraud filters.

---

## 2. The 9 Prop Firm Ban Vectors & Bot Defense Matrix

| Prop Firm Ban Vector | Risk Desk Detection Mechanism | Bot Automatic Defensive Shield | Code Implementation |
| :--- | :--- | :--- | :--- |
| **1. Copy Trading Detection** | Inspects order ticket `comment` and `label` for public EA signatures or shared text. | **Stealth Order Mode:** Submits clean orders with zero comments or labels by default. Completely indistinguishable from human manual trades on cTrader Web/Mobile. Custom stealth comment is optional (`CTRADER_ORDER_COMMENT`). | `core/ctrader_executor.py` |
| **2. News Trading Bans** | Scans trade open/close timestamps against economic calendar release times. | **Automated News Blackout:** Real-time Forex Factory calendar feed automatically halts fresh Forex and Gold entries within $\pm 30$ minutes of high-impact (Red Folder) releases. | `core/news_filter.py`, `market_scanner.py`, `satellite/market_scanner_gold.py` |
| **3. Weekend Holding Rule** | Flags positions held after Friday market close. | **Friday Hard Cutoffs:** Forex fresh entries halt at 12:00 UTC Friday (`FRIDAY_ENTRY_CUTOFF_HOUR_UTC = 12`). Gold fresh entries halt at 16:00 UTC, and any open Gold positions are automatically closed flat before the weekend. | `core/config.py`, `satellite/gold_config.py`, `satellite/market_scanner_gold.py` |
| **4. Daily Loss Limit Breach** | Calculates peak daily equity drop against 4.0%–5.0% limit. | **Daily Loss Circuit Breaker:** Hard-stops all fresh trading for the day if 2 stop-outs occur or daily loss reaches $-2.00$R. At 0.50% risk, max daily loss is capped at **$-1.00\%$** (leaving 75% safety buffer from 4% limit). | `core/config.py`, `satellite/gold_config.py` |
| **5. Max Overall Drawdown** | Trailing equity breach against 8.0%–10.0% ceiling. | **Dynamic Lot Sizing & Correlation Interlock:** Strict lot flooring prevents budget over-allocation. Max concurrent USD exposure capped at 2 positions across both Forex and Gold ledgers. Max portfolio floating risk is $1.0\% - 2.0\%$. | `core/instrument_validator.py`, `satellite/gold_validator.py` |
| **6. Latency Arbitrage / Scalping** | Flags trades held for under 30–60 seconds. | **Institutional Swing Horizon:** Operates exclusively on completed 15M (Forex) and 1H (Gold) bars. Average holding duration is 4 to 18 hours (max 48 hours). Zero high-frequency or tick scalping. | `market_scanner.py`, `satellite/market_scanner_gold.py` |
| **7. Martingale / Grid Rules** | Flags progressive lot sizing or grid accumulation during drawdowns. | **Zero Martingale Architecture:** Exactly 1 trade per pair and maximum 1 trade on Gold. Fixed risk budget calculated strictly before order placement. Zero averaging down. | `core/instrument_validator.py` |
| **8. Rollover Spread Blowouts** | Extreme spreads during 21:00–23:00 UTC cause slippage and immediate stop-out. | **Automated Rollover Blackout:** Fresh entries are strictly suppressed between 20:30 and 22:30 UTC for Gold and 21:00 to 23:00 UTC for Forex. | `satellite/gold_validator.py`, `market_scanner.py` |
| **9. Monday Asian Chop** | Low liquidity and false breakouts during Monday market open. | **Monday London Window:** Entries on Mondays are restricted strictly to the London volume window (06:00–12:00 UTC), eliminating Monday Asian chop and NY afternoon drift. | `core/config.py`, `satellite/gold_config.py` |

---

## 3. Account Size & Recommended Risk Budget Calibration

Prop firm challenge phases require passing profit targets (typically 8%–10% in Phase 1, 5% in Phase 2) while never violating daily (4%–5%) or max (8%–10%) drawdowns.

### Recommended Risk Settings by Account Size:

| Account Equity | Challenge Phase Risk | Funded Account Risk | Monetary Risk / Trade | Max Daily Loss Cap (2 Losses) | Safety Buffer from 5% Daily Limit |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **$5,000** | **0.50%** | 0.25%–0.50% | **$25.00** | **$50.00 (1.00%)** | **4.00% ($200 buffer)** |
| **$10,000** | **0.50%** | 0.25%–0.50% | **$50.00** | **$100.00 (1.00%)** | **4.00% ($400 buffer)** |
| **$25,000** | **0.50%**–1.00% | 0.50% | **$125.00**–$250 | **$250.00 (1.00%)** | **4.00% ($1,000 buffer)** |
| **$50,000** | **0.50%** | 0.25%–0.50% | **$250.00** | **$500.00 (1.00%)** | **4.00% ($2,000 buffer)** |
| **$100,000** | **0.50%** | 0.25%–0.50% | **$500.00** | **$1,000.00 (1.00%)** | **4.00% ($4,000 buffer)** |
| **$200,000** | **0.50%** | 0.25% | **$1,000.00** | **$2,000.00 (1.00%)** | **4.00% ($8,000 buffer)** |

> [!TIP]
> **Golden Rule for Prop Firms:** Keep `RISK_PCT=0.50` on all evaluation challenges. At 0.50% risk with our $1:1.50$ Risk-to-Reward ratio, each winning trade yields $+0.75\%$ account growth, while 2 consecutive stop-outs cost only $-1.00\%$, guaranteeing you will **never** trigger a daily drawdown violation.

---

## 4. Step-by-Step Prop Account Onboarding Checklist

Follow these exact steps to connect your real prop firm account without risking bans:

### Step 1: Obtain cTrader Open API Credentials
1. Log in to your broker's cTrader web or desktop terminal.
2. Verify your account number (`ctidTraderAccountId`) at the top left.
3. Visit the [Spotware Open API Portal](https://openapi.ctrader.com/apps/).
4. Create an Application (e.g. named `PersonalTrader` or any custom name) to obtain:
   - `Client ID`
   - `Client Secret`
5. Click **"Get Token"** or authorize your trading account to generate an `Access Token`.

### Step 2: Inject Credentials into GitHub Repository Secrets
In your GitHub repository, go to **Settings ➔ Secrets and variables ➔ Actions** and set:

| Secret Name | Value Example | Description |
| :--- | :--- | :--- |
| `ENABLE_CTRADER_EXECUTION` | `true` | Enables real order transmission to your cTrader broker. |
| `CTRADER_ENV` | `demo` or `live` | Use `demo` for evaluation challenges; `live` for funded stage. |
| `CTRADER_CLIENT_ID` | `1234_abcdef...` | Your cTrader Open API Client ID. |
| `CTRADER_CLIENT_SECRET` | `secret_...` | Your cTrader Open API Client Secret. |
| `CTRADER_ACCESS_TOKEN` | `token_...` | Your cTrader User Access Token. |
| `CTRADER_ACCOUNT_ID` | `87654321` | Your numeric cTrader Trading Account ID. |
| `ACCOUNT_EQUITY` | `5000.0` | Your exact account balance / equity. |
| `RISK_PCT` | `0.50` | Recommended 0.50% for challenges. |
| `CTRADER_ORDER_COMMENT` | *(Leave Empty)* | Submits clean orders with zero tags (looks manual). |

### Step 3: Verify Pre-Flight Surveillance
1. In GitHub Actions, click **"24/7 Cloud Market Scanner"** ➔ **"Run workflow"**.
2. Inspect the run logs to ensure:
   - Secrets validated: `cTrader credentials and Access Token verified present in GitHub Secrets.`
   - Market scan completes with clean exit codes.
   - Initial signals and alerts appear on Telegram.

---

## 5. Summary Verification
With these protections active, your real prop account is immune to common automated ban mechanisms:
- **Zero EA comment footprint** (stealth manual appearance).
- **Zero news trading violations** (automatic $\pm 30$ min blackout).
- **Zero weekend gap violations** (automatic Friday exits).
- **Zero daily loss violations** (hardcoded 2-stop-out circuit breaker).
- **Zero copy-trade clustering** (individual account parameters and decoupled factor models).
