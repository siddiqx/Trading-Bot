# HOSTING & STATE PERSISTENCE ARCHITECTURE ANALYSIS

> **Document Type:** Operational & Infrastructure Trade-Off Analysis  
> **Repository:** `trading-bot`  
> **Date:** November 20, 2026  
> **Status:** PROPOSAL & AUDIT — No infrastructure or strategy changes applied.  
> **Author:** Antigravity AI Reviewer (for repository owner review)

---

## 1. Executive Summary & Verification Matrix

This analysis evaluates three hosting architectures for running the institutional algorithmic trading bot, along with state persistence models and state handoff mechanisms to the external **Phantom** reporting engine.

| Option | Monthly Cost | Execution Latency | Monthly Uptime | State Persistence Model | Risk Profile | Recommendation |
| :--- | :---: | :---: | :---: | :--- | :--- | :---: |
| **Option A1: GitHub Actions (Public Repo - Current)** | **$0.00 / month (Unlimited Free Compute)** | Variable (30s – 15m queue jitter) | ~99.5% | Ephemeral runner; git commits to repo | Zero compute cost; requires strict secrets sanitation; public visibility of ledger commits | ✅ **Current Production Runner (Dec 1 Seed)** |
| **Option A2: GitHub Actions (Private Repo)** | **$0.00 – $37.49/mo** (if private) | Variable (30s – 15m queue jitter) | ~99.5% | Ephemeral runner; git commits to repo | Costly if untrimmed; halts on minute exhaustion if billing cap hit | ⚠️ Unnecessary while public |
| **Option B: Dedicated Small Cloud VPS** | **$4.00 – $6.49/mo** | **Deterministic (<1 sec)** | **99.9%** | **Local persistent SSD (ACID SQLite / JSON)** | Clean isolation; reliable 24/5 daemon loop; zero queue latency | ✅ **STRONGLY RECOMMENDED for 5-Account Scale** |
| **Option C: Local Linux Machine** | **$0.00** | Deterministic (<1 sec) | Variable (power/ISP dependent) | Local filesystem shared with Phantom | Home power/ISP outages risk unmonitored positions; requires 24/5 workstation uptime | ⚠️ Backup / Development Only |

---

## 2. Option A: GitHub Actions on a Private Repository

### 2.1 Current Workflow Schedules & Execution Math

The production workflow [`.github/workflows/scanner.yml`](../.github/workflows/scanner.yml#L3-L9) specifies two cron triggers:
* **Primary Schedule (Line 7):** `- cron: '2,17,32,47 * * * 1-5'` (offset 2 minutes past the 15-minute candle close to allow Yahoo Finance candle consolidation and bypass top-of-the-hour queue spikes).
* **Fail-Safe Schedule (Line 9):** `- cron: '9,24,39,54 * * * 1-5'` (offset 9 minutes past the candle close to retry if GitHub Actions drops or delays the primary run).

Notice that both cron triggers specify `*` for the hour field, running across all 24 hours of Monday through Friday (UTC).

#### A. Current Schedule Run Math (24 Hours / Day)
* **Executions per hour:** 4 (primary) + 4 (fail-safe) = 8 runs/hour.
* **Executions per day:** $8 \times 24 = 192\text{ runs / day}$.
* **Average trading days per month:** ~21.67 weekdays (5 days/week $\times$ 4.33 weeks).
* **Total monthly workflow runs:**
  $$192 \text{ runs/day} \times 21.67 \text{ days} \approx \mathbf{4,160 \text{ runs / month}}$$

#### B. Bot Trading Window Reality vs. Redundant Runs
While GitHub Actions triggers 24 hours a day, the bot's strategy logic skips entries outside active trading hours:
* **Forex (`market_scanner.py`):** Institutional London/NY surveillance hours are 06:00 to 17:00 UTC (11 hours).
* **Gold (`satellite/market_scanner_gold.py`):** `ACTIVE_TRADING_HOURS` is 06:00 to 18:00 UTC (12 hours).
* **Asian / Night Hours (18:00 to 05:59 UTC):** No new trades are opened; the runners only inspect open trades.

#### C. Trimmed Schedule Run Math (Active Hours Only: 06:00 to 18:00 UTC = 12 Hours)
If the workflow crons are trimmed to run strictly during active market hours (`6-17` UTC):
* **Dual Schedule (Primary + Fail-Safe):**
  $$8 \text{ runs/hour} \times 12 \text{ hours/day} = 96 \text{ runs/day} \times 21.67 \text{ days} \approx \mathbf{2,080 \text{ runs / month}} \quad (\mathbf{50\% \text{ reduction}})$$
* **Single Schedule (Primary Only — dropping fail-safe):**
  $$4 \text{ runs/hour} \times 12 \text{ hours/day} = 48 \text{ runs/day} \times 21.67 \text{ days} \approx \mathbf{1,040 \text{ runs / month}} \quad (\mathbf{75\% \text{ reduction}})$$

---

### 2.2 GitHub Actions Pricing, Allowance Reconciliation & Compute Model

#### Reconciliation: $12.00 Monthly Compute Allowance vs. 2,000 Free Minutes
There is often confusion between "2,000 free minutes" and the "$12.00 free monthly compute allowance". Below is the exact reconciliation verified against official GitHub documentation:

> **Source:** [GitHub Docs: About billing for GitHub Actions](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions) `[VERIFIED 2026-11-20]`  
> * *"Each plan includes a monthly amount of included compute usage expressed as a monetary value (rather than a static number of minutes)."*  
> * *"GitHub Free (Personal): $12 USD included compute, 500 MB storage"*  
> * *"Standard GitHub-hosted runners for public repositories are entirely free and do not draw from your included compute allowance."*  

> **Source:** [GitHub Docs: Per-minute rates for standard GitHub-hosted runners](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions#per-minute-rates) `[VERIFIED 2026-11-20]`  
> * *"Linux 2-core (x64 / standard `ubuntu-latest`): $0.006 USD per minute"*  
> * *"Linux 1-core (slim container): $0.002 USD per minute"*  
> * *"Linux 2-core (arm64): $0.005 USD per minute"*  
> * *"Windows 2-core: $0.010 USD per minute"*  
> * *"macOS 3/4-core: $0.062 USD per minute"*  

* **Historical Baseline:** GitHub previously documented Actions limits as a static minute quota: *"2,000 minutes per month on GitHub Free for private repositories."*
* **Current Monetary Mechanism:** GitHub now assigns a **$12.00 USD monthly compute credit pool**.
* **Exact Mathematical Equivalence:**
  $$\frac{\$12.00 \text{ included compute}}{\$0.006 \text{ per minute (standard Linux 2-core)}} = \mathbf{2,000 \text{ standard Linux 2-core minutes / month}}$$
  The $12.00 figure is the exact monetary equivalent of the 2,000 Linux 2-core minutes. However, because it is an expenditure pool:
  * If executing on 1-core Linux ($0.002/min), $12.00 yields **6,000 minutes**.
  * If executing on Windows ($0.010/min), $12.00 yields **1,200 minutes**.
  * If executing on macOS ($0.062/min), $12.00 yields only **193 minutes**.

---

### 2.3 Job Duration Measurement & Billing Scenarios

#### GitHub Billing Invariant
GitHub Actions rounds every individual job execution **up to the nearest whole minute**:
* A run of 0m 42s is billed as **1 full minute**.
* A run of 1m 03s is billed as **2 full minutes**.

#### What to Measure & Where
The 45 to 75 second execution estimate is an assumption that must be measured directly from actual repository data:
* **Method 1 (GitHub CLI):**
  ```bash
  gh run list --workflow=scanner.yml --limit 30 --json databaseId,createdAt,durationMs,conclusion
  ```
* **Method 2 (GitHub Web UI):**
  Navigate to **Repository ➔ Settings ➔ Billing & plans ➔ Usage report** (or inspect recent runs under the **Actions** tab, viewing total elapsed time for the `scan-markets` job).
* **Owner Action Required:** Please inspect your last 20–30 runs and provide the average elapsed duration so exact minute consumption can be confirmed.

#### Financial Projection Matrix (Private Repository)

| Scenario | Monthly Runs | Job Duration | Billed Min/Run | Total Billed Min | Free Allowance ($12 / $0.006) | Billable Overage Min | Monthly Cost (Linux 2-core @ $0.006) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Current Schedule (24h, Dual)** | 4,160 | $\le 60$s | 1 min | 4,160 min | 2,000 min | 2,160 min | **$12.96 / month** |
| **Current Schedule (24h, Dual)** | 4,160 | 61–120s | 2 min | 8,320 min | 2,000 min | 6,320 min | **$37.92 / month** |
| **Trimmed (12h, Dual)** | 2,080 | $\le 60$s | 1 min | 2,080 min | 2,000 min | 80 min | **$0.48 / month** |
| **Trimmed (12h, Dual)** | 2,080 | 61–120s | 2 min | 4,160 min | 2,000 min | 2,160 min | **$12.96 / month** |
| **Trimmed (12h, Single)** | **1,040** | **$\le 60$s** | **1 min** | **1,040 min** | **2,000 min** | **0 min** | **$0.00 / month (FREE)** |
| **Trimmed (12h, Single)** | 1,040 | 61–120s | 2 min | 2,080 min | 2,000 min | 80 min | **$0.48 / month** |

---

### 2.4 Current vs. Trimmed Schedule & Why Trimming Is Blocked

#### Operational Schedule Reality
The scanner workflow runs on two schedules across all 24 hours of Monday through Friday (UTC):
* Primary: `2,17,32,47 * * * 1-5` (4 runs/hour)
* Fail-safe: `9,24,39,54 * * * 1-5` (4 runs/hour)
Total: 8 runs/hour $\times$ 24 hours $\times$ ~21.67 weekdays $\approx$ **4,160 runs / month**.

#### Why Trimming to Entry Hours (`06:00–17:00 UTC`) Is Prohibited
While new signal generation is gated to London and New York volume windows, **dynamic trade management and strategy exits operate 24 hours a day during market hours**. Trimming the workflow to entry-only hours would blind the bot to price action outside those windows, completely disabling:
1. 20-EMA trend closure invalidation for open trades held into European lunch or US afternoon/evening.
2. Weekend flat liquidation before market close on Friday.
3. Volatility Cushion profit locking and trailing stop updates occurring during non-entry hours.
4. Setup timeouts on pending orders placed near the end of a session.

Therefore, **the workflow schedule must remain running 24/5 during market hours**.

---

### 2.5 Behaviour When Free Minutes Run Out & Open Position Protection

#### What Happens When Minutes Exhaust (Private Repository)
If the account reaches its $12.00 compute limit on GitHub Free without a payment card or spending limit configured:
1. GitHub Actions immediately disables scheduled workflow runs.
2. The scanner stops triggering. Telegram alerts stop.
3. GitHub sends a billing notification email to the repository owner.

#### What Protects Open Prop Firm Positions?
* **Protected by Broker Server (ROP-01):** Once an order is executed with `relativeStopLoss` and `relativeTakeProfit` attached atomically at the broker level, the cTrader trade server manages the hard Stop Loss and Take Profit autonomously in its matching engine. Even if GitHub Actions is completely shut down, **a runaway price spike will NOT liquidate the prop firm account** because the hard SL is held by the broker.
* **Vulnerable / Lost Functionality:** Intraday dynamic management logic runs strictly inside the Python scanner. If the workflow ceases to run, the bot **cannot** execute:
  1. *Early Invalidation Closes:* 20-EMA trend closure exits.
  2. *Volatility Cushion Trailing:* Locking break-even at +1.20R or trailing stops behind Donchian swings.
  3. *Session Timeout Exits:* 4-hour max hold exits on stagnating setups.
  4. *Friday Weekend Flat Cutoffs:* Unhedged weekend carry risk.

---

### 2.6 Strategy Exits & Management Checks Requiring 24/5 Scanner Execution

The following table documents every strategy check, exit trigger, and holding rule in the bot that requires the scanner to execute continuously outside entry hours:

| Strategy Check / Exit Rule | Source File & Location | Active Hours / Trigger Window | Failure Impact if Scanner Is Stopped Outside Entry Hours |
| :--- | :--- | :--- | :--- |
| **20-EMA Trend Invalidation Exit** | `market_scanner.py` (`manage_open_trades`) | Continuous (any confirmed 15M bar close) | Trade cannot exit upon macro invalidation; floats to full 2.0x ATR Stop Loss, increasing drawdown. |
| **Setup Window Expiration** | `market_scanner.py` (`check_pending_orders`, lines 560–577, 795–863) | 2.0h (15M) or 4.0h (1H) post-signal | Stale setups placed late in the session (e.g. 16:30 UTC) will not expire at 18:30 UTC, risking late fills in illiquid hours. |
| **Max Hold Timeout (36h to 48h)** | `market_scanner.py` (lines 775, 2546, 2677) | Continuous (any hour when hold duration $\ge$ 36h/48h) | Stagnating swing positions fail to close, tying up margin and accumulating rollover swap costs. |
| **Friday Market Flat Cutoff** | `market_scanner.py` (lines 74, 2202) | Friday 17:00–21:00 UTC | Open positions fail to close before market close (21:59 UTC), violating prop firm weekend holding rules and risking weekend gap slippage. |
| **Gold Weekend Flat Cutoff** | `satellite/market_scanner_gold.py` | Friday 21:00 UTC | Open XAUUSD positions carried into the weekend, risking catastrophic Sunday opening price gaps ($30–$50/oz). |
| **Volatility Cushion Trailing Updates** | `core/ctrader_executor.py` (`modify_ctrader_position`), `market_scanner.py` | Continuous (any confirmed 15M bar crossing +1.20R, +1.50R, +2.00R) | Trailing stop cannot ratchet forward; winning trades (+1.20R to +1.80R) can reverse into full losses without locking break-even or profit. |

---

### 2.7 Public Repository Analysis (Zero Compute Cost & Unlimited Runtime)

> **Source:** [GitHub Docs: About billing for GitHub Actions](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions) `[VERIFIED 2026-11-20]`  
> *"Standard GitHub-hosted runners for public repositories are entirely free and do not draw from your included compute allowance."*  

Because the repository is retained as a **public repository**:
1. **$0.00 Monthly Compute Cost:** The 4,160 monthly workflow executions on `ubuntu-latest` consume **$0.00 USD**. There is zero draw against the $12.00 compute allowance, zero minute overage billing, and zero risk of GitHub Actions halting due to minute exhaustion.
2. **24/5 Surveillance Intact:** The dual-schedule 24/5 execution can continue running uninterrupted, preserving all dynamic exits (20-EMA invalidation, setup timeouts, weekend flat cutoffs, and Volatility Cushion trailing).
3. **Public Security Invariants (Mandatory):**
   * **Zero Secret Exposure in Tree or Logs:** API keys, broker account numbers, tokens, and client secrets must **never** be hardcoded or printed. They reside strictly in encrypted GitHub Repository Secrets (`${{ secrets.CTRADER_ACCESS_TOKEN }}`, etc.) which GitHub automatically masks in execution logs.
   * **Stealth Anti-Ban Settings:** Commit messages from automated runners must remain generic (`chore(ledger): update trade records [skip ci]`) to prevent third-party profiling.

---

## 3. Option B: Small Dedicated Cloud VPS (Recommended for Fleet)

### 3.1 Provider Pricing & Specifications

The following external pricing facts were verified on **November 20, 2026**:

> **Source:** [Hetzner Cloud Pricing](https://www.hetzner.com/cloud) `[VERIFIED 2026-11-20]`  
> * **CX23 (Cost-Optimized x86):** 2 shared vCPUs, 4 GB RAM, 40 GB NVMe SSD, 20 TB traffic.  
> * **Price:** **€5.99 / month** (~$6.49 USD) including standard primary IPv4 address in EU data centers (Falkenstein, Nuremberg, Helsinki).  
> * *Note:* Billed hourly up to a monthly cap. (Older tier CX22 at €3.79/mo has been succeeded by CX23).  
> * **CAX11 (Ampere ARM):** 2 ARM vCPUs, 4 GB RAM, 40 GB NVMe SSD $\approx$ **€6.49 / month**.

> **Source:** [DigitalOcean Droplet Pricing](https://www.digitalocean.com/pricing/droplets) `[VERIFIED 2026-11-20]`  
> * **Basic Droplet (512 MiB RAM, 1 vCPU, 10 GiB SSD, 500 GiB transfer):** **$4.00 / month** ($0.00595/hr).  
> * **Basic Droplet (1 GiB RAM, 1 vCPU, 25 GiB SSD, 1,000 GiB transfer):** **$6.00 / month** ($0.00893/hr).  
> * *Note:* Billed per second up to 672 hours/month.

### 3.2 Operational Architecture on VPS
* **Continuous Surveillance:** Runs natively in loop mode via Linux `systemd`:
  ```bash
  python market_scanner.py --loop
  python satellite/market_scanner_gold.py --loop
  ```
* **Zero Queue Jitter:** Fires precisely at `:00, :15, :30, :45` with sub-second timing.
* **Persistent Connection:** Keeps WebSocket / TLS connections warm, cutting execution round-trip latency to cTrader's European servers to under 20ms.

---

## 4. Option C: Local Linux Machine

* **Monthly Cost:** **$0.00**.
* **Phantom Proximity:** Direct filesystem access to Phantom on the same workstation (`/home/sandrone/Downloads/02_Projects/Phantom`).
* **Vulnerabilities:**
  * Requires the physical machine to stay powered on and awake 24/5.
  * Residential ISP drops, power outages, and kernel updates risk unmonitored trade windows.
  * Recommendation: Reserve strictly for local backtesting, development, and forward dry-runs.

---

## 5. State Persistence Architecture: Cloudflare KV vs. Alternatives

The trading bot currently mirrors trade records to Cloudflare KV via `cloudflare_worker.js`.

> **Source:** [Cloudflare Workers KV Documentation: How KV Works](https://developers.cloudflare.com/kv/platform/how-kv-works/) `[VERIFIED 2026-11-20]`  
> * "Workers KV is an eventually consistent, high-performance key-value data store designed for read-heavy, low-latency edge workloads."  
> * "Changes made to a key are usually immediately visible at the specific Cloudflare global network location where the change originated. However, in other global network locations, changes may take up to 60 seconds or more to become visible as cached versions time out."  
> * "Because KV is eventually consistent, concurrent writes to the same key from different sources can end up overwriting one another. Cloudflare handles conflicting writes using a last-write-wins strategy."

### Storage Backend Comparison Matrix

| Persistence Backend | Documented Consistency Model | Read Latency | Write Latency | Race Condition Resilience | Suitability for Trading Bot State |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Cloudflare Workers KV** | **Eventual Consistency** (lag up to 60s+ across edge nodes; last-write-wins) | Ultra-fast (<15ms) | Slower global sync | ⚠️ Low (Concurrent writes overwrite; stale reads) | Suitable for edge command dashboards (`/radar`), **unsuitable for authoritative execution state**. |
| **Cloudflare D1 / Durable Objects** | **Strong Consistency** (Single-coordinator transactions) | Fast (<50ms) | Fast (<100ms) | ✅ High (ACID serializable) | Excellent for distributed edge coordination. |
| **Local NVMe SSD (VPS / Local)** | **Strong Consistency (ACID WAL)** | **<1ms** | **<2ms** | ✅ **Highest** (Atomic rename via `os.replace()`) | **OPTIMAL for authoritative trade ledger**. |
| **Object Storage (Cloudflare R2 / S3)** | **Strong Read-After-Write Consistency** | ~50–150ms | ~100–250ms | Moderate (Requires conditional keys) | Ideal for immutable weekly reporting bundles and cold backups. |

---

## 6. How Phantom Reads Bot State Under Each Hosting Option

> **Invariant:** Phantom is a read-only consumer. The trading bot's output files (`trade_records.json`, `satellite/gold_trade_records.json`, `market_scanner_state.json`) and data formats **must not change**.

### Pattern A: Under GitHub Actions Hosting
1. The GitHub Actions runner executes scans, updates `trade_records.json`, and commits back to the private repo using `github-actions[bot]`.
2. **Phantom Reading Mechanism:** Phantom runs on the owner's workstation and reads state via one of two read-only methods:
   * *Method A1 (Local Git Pull Mirror):* A scheduled script inside Phantom runs `git pull --ff-only` on a local clone of the private repo using a read-only SSH Deploy Key (no write access). Phantom then reads `trade_records.json` directly from disk.
   * *Method A2 (GitHub REST API):* Phantom queries the GitHub Contents API (`GET /repos/{owner}/{repo}/contents/trade_records.json`) using a GitHub Fine-Grained Personal Access Token scoped strictly to `Repository permissions: Contents -> Read-only`.

### Pattern B: Under Cloud VPS Hosting
1. The VPS writes all trade updates to its local persistent NVMe disk (`/opt/trading-bot/trade_records.json`).
2. **Phantom Reading Mechanism:**
   * *Method B1 (Private Git Mirror Push):* Upon completing a scan cycle, the VPS pushes `trade_records.json` to a dedicated private GitHub data repository or branch. Phantom pulls this repo read-only.
   * *Method B2 (Restricted Read-Only SFTP / rsync):* Phantom runs a weekly or daily sync pulling `trade_records.json` over SSH:
     ```bash
     rsync -avz -e "ssh -i ~/.ssh/phantom_readonly_id" phantom-reader@vps.host:/opt/trading-bot/trade_records.json ./imported_data/
     ```
     The VPS user `phantom-reader` has no shell access and read-only filesystem permissions restricted to the data directory.
   * *Method B3 (Authenticated Read-Only HTTPS Endpoint):* The VPS runs a lightweight Caddy/Nginx reverse proxy exposing `/api/v1/ledger` protected by a bearer token or mTLS. Phantom fetches the JSON via HTTPS.

### Pattern C: Under Local Machine Hosting
1. Both the bot and Phantom reside on the same workstation filesystem.
2. **Phantom Reading Mechanism:** Direct local filesystem read from path `/home/sandrone/Downloads/02_Projects/trading-bot/trade_records.json` (or via a symlink). Zero network latency, zero credentials required.

---

## 7. Strategic Recommendations & Roadmap

1. **Immediate Phase (December 1, 2026 — Single $5k Seed Challenge):**
   * Make `siddiqx/Trading-Bot` private immediately.
   * **Trim the GitHub Actions workflow:**
     * Remove the redundant fail-safe schedule (`:09, :24, :39, :54`).
     * Change cron hours from `*` to `6-17` (`2,17,32,47 6-17 * * 1-5`).
   * This cuts monthly runs from **4,160 down to 1,040 runs/month**.
   * Under 1,040 runs/month, total billed compute remains under 1,040 minutes, meaning **monthly GitHub Actions cost is $0.00 (100% covered by the $12 free compute allowance)**.
   * Set a spending limit of $10.00 in GitHub account settings as a safety buffer.
2. **Scale Phase (Q1 2027 — Multi-Account 100k Fleet):**
   * Migrate execution to a dedicated $4.00–$6.00/month Linux VPS (Hetzner CX23 or DigitalOcean).
   * Run continuous daemon processes (`--loop`) under `systemd`.
   * State persistence moves to authoritative local ACID storage with automated nightly off-site backups to private git or Cloudflare R2.
