# Professional Forex Live Signal Bot
### Adaptive Trend-Momentum Breakout Architecture: TradingView (Pine Script v6) → FastAPI Webhook → Telegram

---

> **CRITICAL DISCLAIMER & RISK PRINCIPLES**
> This software is an **engineering research system** designed for **live forward-testing and signal tracking**. It is **SIGNAL-ONLY** in Version 1 and does not execute broker trades. 
> Trading foreign exchange (Forex) on margin carries high risk and may not be suitable for all investors. High leverage can work against you as well as for you. Past backtest performance is **never a guarantee of future live performance**. This system contains **no martingale, no grid recovery, no averaging down, and no revenge trading mechanics**.

---

## 1. System Architecture

```
FOREX MARKET (1H / 4H Data Feeds)
       │
       ▼
TRADINGVIEW (Pine Script v6 Engine)
  • 4H EMA 200 Regime Filter (strictly closed bars)
  • 1H ADX(14) Trend Strength Filter
  • 1H ROC(20) Momentum Filter
  • 1H 20-bar Donchian Breakout (strictly previous completed bars)
  • 1H ATR(14) Volatility & Risk Sizing
       │
       ▼
REALTIME CONFIRMED SIGNAL (barstate.isconfirmed == true)
       │
       ▼
TRADINGVIEW WEBHOOK (HTTPS POST JSON Alert)
       │
       ▼
FASTAPI SERVER (Uvicorn Async Webhook Worker)
  ├── 1. SHARED SECRET AUTHENTICATION (Constant-time HMAC check)
  ├── 2. PAYLOAD SCHEMA VALIDATION (Pydantic models & price geometry)
  ├── 3. DUPLICATE IDEMPOTENCY ENGINE (Deduplication against SQLite)
  ├── 4. STRATEGY REGIME & SESSION FILTERS
  └── 5. SQLALCHEMY RELATIONAL STORAGE (forex_signals.db)
       │
       ▼
ASYNC TELEGRAM SERVICE (HTML Formatted Alerts & Bot Commands)
       │
       ▼
USER'S TELEGRAM (Mobile / Desktop Client)
```

---

## 2. Core Strategy: Adaptive 1H Anchor Breakout with Order Block & Fibonacci Strategy

The strategy combines institutional Smart Money Concepts (SMC) with multi-timeframe trend momentum:

### Architectural Workflow:
1. **1-Hour Anchor Breakout (Candle #1 Crossover)**:
   - Scans for structural 48-hour (2 full days) Donchian breakouts aligned with **Daily (D1) 50 EMA** and **1H 200 EMA**.
   - Employs **Strict Position Lock**: exactly ONE trade signal per move, eliminating overlapping or repeated arrows.
2. **Origin Order Block (OB) Identification**:
   - **Bullish (+OB)**: The last bearish candle (down-close) prior to the 1H breakout displacement.
   - **Bearish (-OB)**: The last bullish candle (up-close) prior to the 1H breakdown displacement.
   - Automatically plots the institutional Order Block box (`[OB_Low, OB_High]`) directly on TradingView charts.
3. **Fibonacci Retracement Grid (Optimal Trade Entry - OTE)**:
   - Measures the impulse swing from Order Block extreme to Breakout Extreme.
   - Computes:
     - **Fib 50.0% Equilibrium**: Separates premium from discount.
     - **Fib 61.8% Golden Pocket & 70.5% ICT OTE**: High-probability confluence entry zone.
4. **Confluence Entry Corridor**:
   - `Optimal Entry Range: min(OB_Low, Fib 61.8%) – min(OB_High, Fib 50.0%)` for Longs.
   - `Ideal Retest Entry`: The confluence price where the Order Block boundary meets the 50%/61.8% discount area.
5. **Structural Exit Strategy**:
   - **Stop Loss (SL)**: Strictly invalidates the Order Block (`OB_Low - 0.15 ATR` for Longs; `OB_High + 0.15 ATR` for Shorts). If the Order Block is violated, institutional support is broken.
   - **Take Profit (TP)**: Institutional Fibonacci Extension:
     - **Target 1**: `-0.272 Extension` (Conservative swing target).
     - **Target 2**: `-0.618 Extension` (Expansion runner).
6. **Dynamic 1% Position Sizing**:
   - True 1% equity risk calculated from the surgical distance between the Confluence Entry and the Order Block Stop Loss.

| Strategy Component | Bullish (LONG) | Bearish (SHORT) |
| :--- | :--- | :--- |
| **Daily (D1) Macro Filter** | D1 Close > D1 EMA 50 | D1 Close < D1 EMA 50 |
| **1H Trend Filter** | 1H Close > EMA 200 & EMA 20 > EMA 50 | 1H Close < EMA 200 & EMA 20 < EMA 50 |
| **Momentum Filter** | ADX >= 20, Rising ADX (`ADX > ADX[1]`) | ADX >= 20, Rising ADX (`ADX > ADX[1]`) |
| **RSI Velocity Sweet-Spot** | 55.0 <= RSI <= 75.0 | 25.0 <= RSI <= 45.0 |
| **Origin Order Block** | Last bearish candle before impulse | Last bullish candle before impulse |
| **Retest Entry Corridor** | `[OB_Low / Fib 61.8%, OB_High / Fib 50%]` | `[OB_Low / Fib 50%, OB_High / Fib 61.8%]` |
| **Structural Invalidation (SL)** | `OB_Low - (0.15 * ATR)` | `OB_High + (0.15 * ATR)` |
| **Take Profit Target (TP)** | Fibonacci -0.272 / -0.618 Extension | Fibonacci -0.272 / -0.618 Extension |
| **Execution Window** | London / NY Overlap: `07:00 - 17:00 UTC` | London / NY Overlap: `07:00 - 17:00 UTC` |

---

## 3. Signal Quality Score (0–100)

Every trade setup generates an objective, deterministic heuristic score:
- **HTF Trend Alignment (25 pts):** Strong alignment with 4H EMA 200 and positive/negative slope.
- **ADX Trend Strength (15 pts):** Graded from weak (`ADX >= 18`) to strong (`ADX >= 25`).
- **Momentum ROC (15 pts):** Graded on magnitude and direction of 20-period Rate of Change.
- **Breakout Clearance (20 pts):** Measures distance cleared beyond the 20-period Donchian boundary.
- **Volatility Health (10 pts):** Ensures ATR is not collapsed or parabolically blown out.
- **Session Timing (5 pts):** Active during London / New York high-liquidity overlap.
- **Execution Quality Baseline (10 pts):** Baseline spread-to-volatility check.

*Note: The Signal Quality Score is an engineering heuristic, NOT a probability of winning.*

## 4. 24/7 Standalone Cloud Market Scanner (Zero PC / 100% Free Mode)

For automated 24/7 signal monitoring without keeping your computer running and without paying for a TradingView subscription:

```
LIVE MARKET (Yahoo Finance API)
       │
       ▼ (Every 15 min via GitHub Actions / Cloud Cron)
MARKET SCANNER (market_scanner.py)
   • Pairs: EURUSD, USDJPY, USDCAD, USDCHF, AUDUSD, XAUUSD
   • Timeframes: 15M & 1H
   • Strategies: Donchian 20, EMA 20/50 Slope, RSI 14, Order Blocks
       │
       ▼ (Confirmed Breakout)
TELEGRAM BOT API ──► YOUR PHONE
```

### Automation & Deployment
The system includes [`.github/workflows/scanner.yml`](file:///.github/workflows/scanner.yml) which executes automatically on GitHub's free runners every 15 minutes during Forex market hours (Monday through Friday).
- **Manual Scan**: Run `python market_scanner.py`
- **Background Daemon**: Run `python market_scanner.py --loop`
- **Test Alert**: Run `python market_scanner.py --test`

---

## 5. Local Installation & Setup (Windows PowerShell)

Open **PowerShell** in `C:\trading-bot` and execute:

```powershell
# 1. Activate Virtual Environment
.venv\Scripts\Activate.ps1

# 2. Verify / Install Dependencies
pip install -r requirements.txt

# 3. Copy Environment Configuration
Copy-Item .env.example .env

# 4. Run Pytest Suite to Verify System Integrity
pytest
```

---

## 5. Running the FastAPI Server

Launch the production-grade Uvicorn server:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Health Check Verification
In a second PowerShell window, verify the health endpoint:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
```
Expected output:
```json
{
  "status": "ok",
  "service": "forex-signal-bot",
  "version": "1.0.0"
}
```

---

## 6. End-to-End Automated Local Testing

We have provided a turnkey testing script: [`test_local_webhook.ps1`](file:///c:/trading-bot/test_local_webhook.ps1).

Run it in PowerShell:
```powershell
.\test_local_webhook.ps1
```

This script automatically:
1. Pings `GET /health`
2. Dispatches a simulated `TEST` signal (`EURUSD LONG`) with complete trade geometry
3. Tests duplicate protection by attempting to resend the exact same signal
4. Queries `GET /webhook/stats` to verify SQLite signal recording
5. Queries `GET /webhook/last` to view the saved database record

---

## 7. Connecting to Telegram

### Setup Bot Credentials
1. Open Telegram and search for `@BotFather`.
2. Type `/newbot` and follow instructions to get your **Bot Token** (e.g. `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).
3. Send a message to your bot or invite it to your channel/group.
4. Get your **Chat ID** (you can use `@userinfobot` or check `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`).
5. Open your `.env` file and set:
   ```env
   TELEGRAM_BOT_TOKEN="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
   TELEGRAM_CHAT_ID="YOUR_CHAT_OR_CHANNEL_ID"
   ```

### Bot Interactive Commands
The Telegram bot supports the following commands:
- `/start` or `/help` - Displays bot capabilities and available commands.
- `/status` - Server health, database status, last signal timestamp.
- `/last` - Detailed breakdown of the most recent recorded signal.
- `/stats` - Total signals, long vs. short distribution, pair breakdowns.
- `/strategy` - Full parameter and logic summary of the strategy.

---

## 8. Exposing FastAPI to TradingView via Cloudflare Tunnel

TradingView requires a publicly reachable **HTTPS** endpoint to deliver webhooks.

### Quick Setup using Cloudflare `cloudflared`:
1. Download Cloudflare Tunnel client:
   ```powershell
   winget install Cloudflare.cloudflared
   ```
2. With your FastAPI server running on port 8000, start an ephemeral tunnel:
   ```powershell
   cloudflared tunnel --url http://localhost:8000
   ```
3. Cloudflare will output a public HTTPS URL like:
   `https://random-assigned-name.trycloudflare.com`
4. Your TradingView Webhook URL is:
   `https://random-assigned-name.trycloudflare.com/webhook/tradingview`

*(Note: Keep the PowerShell tunnel window open while forward-testing).*

---

## 9. TradingView Alert Setup

1. Open **TradingView** and navigate to your Forex chart (e.g. `EURUSD`, `1H`).
2. Open the **Pine Editor** at the bottom, paste the code from [`pinescript/adaptive_trend_momentum_breakout.pine`](file:///c:/trading-bot/pinescript/adaptive_trend_momentum_breakout.pine), and click **Add to chart**.
3. In Strategy Settings (Gear icon):
   - Set `Webhook Secret Key` matching your `.env` `WEBHOOK_SECRET`.
   - Set `Environment` to `LIVE` (or `TEST` for initial verification).
4. Click **Alert** (Clock icon with plus) on TradingView:
   - **Condition:** Select `Adaptive Trend-Momentum Breakout [Confirmed Bar Signal]`
   - **Trigger:** `Any alert() function call` or `Order fills and alert() function calls`
   - **Webhook URL:** Check the box and paste `https://your-public-url.com/webhook/tradingview`
   - **Message:** Leave blank or enter `{{strategy.order.alert_message}}` (The Pine Script code dynamically formats the alert JSON).
5. Click **Create**.

---

## 10. Database Schema & Forward-Testing Tracking

The SQLite database (`forex_signals.db`) records every signal with full forward-testing fields:

| Column | Type | Purpose |
| :--- | :--- | :--- |
| `signal_id` | String (Unique) | Idempotency key to block duplicate network deliveries |
| `received_at` | DateTime (UTC) | Server receipt timestamp |
| `signal_time` | String | Candlestick close timestamp from TradingView |
| `symbol` | String | Normalized pair (e.g. `EURUSD`, `USDJPY`) |
| `direction` | String | `LONG` or `SHORT` |
| `entry`, `stop_loss`, `take_profit` | Float | Calculated trade boundaries |
| `risk_reward` | Float | Planned risk/reward ratio (e.g. `2.0`) |
| `signal_score` | Float | Heuristic score (0-100) |
| `adx`, `atr`, `roc` | Float | Exact indicator readings at signal close |
| `htf_regime` | String | `BULLISH` or `BEARISH` |
| `outcome` | String | Forward-test outcome (`PENDING`, `WIN`, `LOSS`, `BREAKEVEN`) |
| `r_multiple` | Float | Realized return in terms of risk R |
| `maximum_favorable_excursion` | Float | Maximum price movement in favor of trade (MFE) |
| `maximum_adverse_excursion` | Float | Maximum price drawdown against trade (MAE) |

---

## 11. Production Linux VPS Deployment

For 24/7 continuous operation on a Linux VPS (Ubuntu / Debian):

### 1. Clone & Set Up Virtualenv
```bash
git clone <repo-url> /opt/trading-bot
cd /opt/trading-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env # configure tokens and production secret
```

### 2. Configure Systemd Service
Create `/etc/systemd/system/forex-bot.service`:
```ini
[Unit]
Description=Forex Live Signal Bot FastAPI Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/trading-bot
EnvironmentFile=/opt/trading-bot/.env
ExecStart=/opt/trading-bot/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 3. Start & Enable Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now forex-bot
sudo systemctl status forex-bot
```

### 4. Nginx Reverse Proxy with Let's Encrypt SSL
```nginx
server {
    server_name signals.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Obtain free SSL certificate:
```bash
sudo certbot --nginx -d signals.yourdomain.com
```

---

## 12. Forward-Testing Methodology

A core tenet of this system is: **Never fabricate profitability or claim edge without statistical proof.**

Do not draw conclusions from 10 or 20 signals. Collect a statistically valid sample of **100+ live forward-tested signals** across multiple market regimes and analyze:
- **Sample Distribution:** Win Rate % across Longs vs. Shorts.
- **Expectancy:** $E = (P_{\text{win}} \times R_{\text{win}}) - (P_{\text{loss}} \times R_{\text{loss}})$.
- **Excursion Profiles:** MFE / MAE analysis to determine whether the 1.75 ATR stop distance is breathing adequately or being cut off prematurely.
- **Regime Stability:** Performance when 4H EMA slope is steep vs. shallow.
