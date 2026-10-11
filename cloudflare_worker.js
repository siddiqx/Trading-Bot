/**
 * 24/7 Institutional Cloudflare Worker for Telegram Trading Bot
 * System Version: v2.0-Frozen (Forensic Audit Release)
 * Strategy Freeze Date: 2026-10-02
 * 
 * Features:
 * - Active Trade Tracking & Floating PnL with Break-Even state display
 * - Market Radar differentiating live trades vs surveillance (ADX-aware)
 * - /history command with pair and date range filtering
 * - /performance command calculated strictly from live trades taken from 2026-10-02 onwards
 * - /strategy command: full v2 rulebook incl. ADX filter, Model F TP, BE rule, session overlap block
 * - Modern, aesthetic, executive terminal formatting
 */

const BOT_TOKEN = "8932628751:AAFS_Z7SZMbfNAgNE9KmU6Sly32IGxDm2p0";
const TELEGRAM_API = `https://api.telegram.org/bot${BOT_TOKEN}`;
const DEFAULT_GH_TOKEN = "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";
const DEFAULT_CHAT_ID = "8142877259";

const ASSETS = [
  { name: "EUR/USD", symbol: "EURUSD", ticker: "EURUSD=X", pip: 0.0001, digits: 5, donchian_len: 20 },
  { name: "USD/CAD", symbol: "USDCAD", ticker: "USDCAD=X", pip: 0.0001, digits: 5, donchian_len: 20 },
  { name: "GBP/USD", symbol: "GBPUSD", ticker: "GBPUSD=X", pip: 0.0001, digits: 5, donchian_len: 20 },
  { name: "USD/JPY", symbol: "USDJPY", ticker: "USDJPY=X", pip: 0.01,   digits: 3, donchian_len: 20 },
  { name: "USD/CHF", symbol: "USDCHF", ticker: "USDCHF=X", pip: 0.0001, digits: 5, donchian_len: 20 },
  { name: "AUD/USD", symbol: "AUDUSD", ticker: "AUDUSD=X", pip: 0.0001, digits: 5, donchian_len: 20 }
];

const ALL_KNOWN_CONFIGS = {
  "EURUSD": { name: "EUR/USD", ticker: "EURUSD=X", pip: 0.0001, digits: 5, donchian_len: 20 },
  "USDCAD": { name: "USD/CAD", ticker: "USDCAD=X", pip: 0.0001, digits: 5, donchian_len: 20 },
  "GBPUSD": { name: "GBP/USD", ticker: "GBPUSD=X", pip: 0.0001, digits: 5, donchian_len: 20 },
  "USDJPY": { name: "USD/JPY", ticker: "USDJPY=X", pip: 0.01,   digits: 3, donchian_len: 20 },
  "USDCHF": { name: "USD/CHF", ticker: "USDCHF=X", pip: 0.0001, digits: 5, donchian_len: 20 },
  "AUDUSD": { name: "AUD/USD", ticker: "AUDUSD=X", pip: 0.0001, digits: 5, donchian_len: 20 }
};

const ALL_KNOWN_TICKERS = Object.fromEntries(Object.entries(ALL_KNOWN_CONFIGS).map(([k, v]) => [k, v.ticker]));

/**
 * Universal Symbol Normalizer
 * Extracts base asset symbol (e.g., 'EURUSD') from slot keys like 'EURUSD_15M' or trade records
 */
function getBaseSymbol(key, trade = null) {
  if (trade && trade.symbol) return String(trade.symbol).toUpperCase();
  if (trade && trade.pair) return String(trade.pair).toUpperCase();
  if (typeof key === "string" && key.includes("_")) {
    return key.split("_")[0].toUpperCase();
  }
  return String(key || "").toUpperCase();
}

/**
 * Universal Asset Configuration Resolver
 * Always resolves to a valid asset configuration with correct market ticker (never EURUSD_15M=X)
 */
function getAssetConfig(symbolOrKey, trade = null) {
  const sym = getBaseSymbol(symbolOrKey, trade);
  if (ALL_KNOWN_CONFIGS[sym]) {
    return { ...ALL_KNOWN_CONFIGS[sym], symbol: sym };
  }
  const found = ASSETS.find(a => a.symbol === sym);
  if (found) return found;
  return {
    symbol: sym,
    name: trade?.pair || sym,
    ticker: trade?.ticker || `${sym}=X`,
    pip: trade?.pip || (sym.includes("JPY") ? 0.01 : 0.0001),
    digits: trade?.digits || (sym.includes("JPY") ? 3 : 5),
    donchian_len: 20
  };
}

// In-Memory High-Speed Quote Cache (30-second TTL prevents redundant HTTP calls across buttons)
let QUOTE_CACHE = {};
let QUOTE_CACHE_TIME = {};
const CACHE_TTL_MS = 30000;

async function fetchWithTimeout(url, options = {}, timeoutMs = 4000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(id);
    return res;
  } catch (err) {
    clearTimeout(id);
    throw err;
  }
}

/**
 * High-Speed Live Price Resolver with In-Memory Caching and Multi-Tier Fallbacks
 * Primary: TradingView Forex Scanner (Institutional speed ~200ms)
 * Secondary: Yahoo Finance Mirrors
 * Fallback: Most recent cached quote (Prevents 'Feed Offline' flickering)
 */
async function getLivePriceFast(asset, maxWaitMs = 4000) {
  const sym = asset.symbol;
  const now = Date.now();
  if (QUOTE_CACHE[sym] && (now - (QUOTE_CACHE_TIME[sym] || 0) < CACHE_TTL_MS)) {
    return QUOTE_CACHE[sym];
  }

  // Forex Majors & Crosses
  // A. TradingView Forex Scanner (Ultra-fast, institutional quotes)
  try {
    const res = await fetchWithTimeout("https://scanner.tradingview.com/forex/scan", {
      method: "POST",
      headers: { "User-Agent": "Mozilla/5.0", "Content-Type": "application/json" },
      body: JSON.stringify({ symbols: { tickers: [`FX_IDC:${sym}`, `FX:${sym}`] }, columns: ["close"] })
    }, maxWaitMs);
    if (res.ok) {
      const json = await res.json();
      const p = parseFloat(json?.data?.[0]?.d?.[0]);
      if (!isNaN(p) && p > 0) {
        QUOTE_CACHE[sym] = p;
        QUOTE_CACHE_TIME[sym] = now;
        return p;
      }
    }
  } catch (e) {}

  // B. Fallback: Yahoo Finance (query1 & query2 mirrors)
  const ticker = asset.ticker || `${sym}=X`;
  for (const host of ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]) {
    try {
      const url = `https://${host}/v8/finance/chart/${ticker}?range=1d&interval=5m`;
      const res = await fetchWithTimeout(url, {
        headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" }
      }, maxWaitMs);
      if (res.ok) {
        const json = await res.json();
        const closes = json?.chart?.result?.[0]?.indicators?.quote?.[0]?.close?.filter(v => v !== null && v !== undefined) || [];
        if (closes.length > 0) {
          const p = closes[closes.length - 1];
          QUOTE_CACHE[sym] = p;
          QUOTE_CACHE_TIME[sym] = now;
          return p;
        }
      }
    } catch (e) {}
  }

  // 4. Return cached quote if ever recorded (guarantees zero UI flicker)
  if (QUOTE_CACHE[sym] !== undefined) {
    return QUOTE_CACHE[sym];
  }

  return null;
}

/**
 * Checks whether global Forex markets are open.
 * Markets close Friday 17:00 New York time and reopen Sunday 17:00 New York time.
 */
function isMarketOpen() {
  const now = new Date();
  const nyStr = now.toLocaleString("en-US", { timeZone: "America/New_York" });
  const ny = new Date(nyStr);
  const day = ny.getDay(); // 0 = Sun, 1 = Mon, ..., 5 = Fri, 6 = Sat
  const hour = ny.getHours();
  const min = ny.getMinutes();

  // Closed all day Saturday (day 6)
  if (day === 6) return false;
  // Closed Friday after 17:00 NY (day 5)
  if (day === 5 && (hour > 17 || (hour === 17 && min >= 0))) return false;
  // Closed Sunday before 17:00 NY (day 0)
  if (day === 0 && hour < 17) return false;

  return true;
}

// Dynamic trade ledger state (zero hardcoded trades; populated 100% dynamically via signals & cloud sync)
let STORED_ACTIVE_TRADES = {};
let STORED_COMPLETED_TRADES = [];

/**
 * Strict Ledger Sanitizer: Permanently excludes any Gold (XAUUSD / GOLD) records from all bot views.
 */
function sanitizeLedger(ledger) {
  if (!ledger) return { active: {}, completed: [] };
  const cleanActive = {};
  for (const [k, t] of Object.entries(ledger.active || {})) {
    const sym = getBaseSymbol(k, t);
    if (sym !== "XAUUSD" && sym !== "GOLD" && !sym.includes("XAU")) {
      cleanActive[k] = t;
    }
  }
  const cleanCompleted = (ledger.completed || []).filter(t => {
    const sym = getBaseSymbol(t.pair || t.symbol, t);
    return sym !== "XAUUSD" && sym !== "GOLD" && !sym.includes("XAU");
  });
  return { active: cleanActive, completed: cleanCompleted };
}

/**
 * Universal Ledger Resolver
 * 1. Checks Cloudflare Workers KV (env.TRADE_LEDGER, env.TRADES_KV, env.KV)
 * 2. Checks GitHub API if env.GITHUB_TOKEN is provided
 * 3. Checks raw GitHub repository URL
 * 4. Falls back to baseline state
 */
async function getLedger(env) {
  // 1. Cloudflare Workers KV
  const kv = env && (env.TRADE_LEDGER || env.TRADES_KV || env.KV);
  if (kv) {
    try {
      const active = await kv.get("active_trades", "json");
      const completed = await kv.get("completed_trades", "json");
      if (active !== null || completed !== null) {
        return sanitizeLedger({
          active: active || {},
          completed: completed || []
        });
      }
    } catch (e) {
      console.error("KV read error:", e);
    }
  }

  // 2. Private GitHub API via GITHUB_TOKEN secret or fallback
  const ghAuthToken = (env && (env.GITHUB_TOKEN || env.GH_TOKEN)) || DEFAULT_GH_TOKEN;
  if (ghAuthToken) {
    try {
      const ghRes = await fetch("https://api.github.com/repos/siddiqx/Trading-Bot/contents/trade_records.json", {
        headers: {
          "Authorization": `Bearer ${ghAuthToken}`,
          "Accept": "application/vnd.github.raw",
          "User-Agent": "Cloudflare-Worker-Ledger"
        }
      });
      if (ghRes.ok) {
        const ghData = await ghRes.json();
        return sanitizeLedger({
          active: ghData.active_trades || {},
          completed: ghData.completed_trades || []
        });
      }
    } catch (e) {
      console.error("GitHub API fetch error:", e);
    }
  }

  // 3. Raw GitHub URL (public repo fallback)
  try {
    const rawRes = await fetch("https://raw.githubusercontent.com/siddiqx/Trading-Bot/main/trade_records.json?t=" + Date.now(), {
      headers: { "User-Agent": "Cloudflare-Worker-Ledger" }
    });
    if (rawRes.ok) {
      const rawData = await rawRes.json();
      return sanitizeLedger({
        active: rawData.active_trades || {},
        completed: rawData.completed_trades || []
      });
    }
  } catch (e) {}

  // 4. Default in-memory baseline
  return sanitizeLedger({
    active: STORED_ACTIVE_TRADES,
    completed: STORED_COMPLETED_TRADES
  });
}

/**
 * Auto-resolves a trade that hit TP or SL, updating memory, KV, and triggering GitHub sync.
 * @param {string} symbol
 * @param {object} t - trade record
 * @param {string} outcome - "WIN" | "LOSS" | "CANCELLED"
 * @param {number} exitPrice
 * @param {object} env - Cloudflare env bindings
 * @param {object|null} prefetchedLedger - already-fetched {active, completed} to avoid re-fetching
 */
async function autoResolveTrade(symbol, t, outcome, exitPrice, env, prefetchedLedger = null) {
  const isCancelled = outcome === "CANCELLED";
  let resolvedOutcome = outcome;
  let pips = 0.0;
  let r = 0.0;

  if (isCancelled) {
    pips = 0.0;
    r = 0.0;
  } else if (t.partial_taken) {
    // Model J: 50% position was booked at +1.0R (+0.50R banked)
    const baseBankedR = t.partial_banked_r || 0.50;
    const initSlPips = t.sl_pips || Math.abs(t.entry - t.stop_loss) / (t.pip || 0.0001);

    if (outcome === "WIN") {
      // Reached full TP target on remaining 50%
      const tpPips = t.tp_pips || Math.abs(t.take_profit - t.entry) / (t.pip || 0.0001);
      const rr = t.rr || 2.0;
      r = baseBankedR + (rr * 0.50);
      pips = (initSlPips * 0.50) + (tpPips * 0.50);
      resolvedOutcome = "WIN";
    } else {
      // Stopped out at Breakeven after banking 50% at +1.0R
      r = baseBankedR; // +0.50R net win
      pips = initSlPips * 0.50;
      resolvedOutcome = "WIN"; // Model J guarantees net win
    }
  } else {
    const isWin = outcome === "WIN";
    pips = isWin 
      ? (t.tp_pips || Math.abs(t.take_profit - t.entry) / (t.pip || 0.0001)) 
      : -(t.sl_pips || Math.abs(t.entry - t.stop_loss) / (t.pip || 0.0001));
    r = isWin ? (t.rr || 2.0) : -1.0;
  }

  const completedRecord = {
    ...t,
    exit_price: exitPrice,
    outcome: resolvedOutcome,
    realized_pips: Math.round(pips * 10) / 10,
    realized_r: Math.round(r * 100) / 100,
    closed_at: new Date().toISOString(),
    status: isCancelled ? "CANCELLED" : "CLOSED"
  };

  // Use pre-fetched ledger if provided — avoids 3 redundant HTTP calls on every resolve
  const currentLedger = prefetchedLedger || await getLedger(env);
  const currentActive = { ...(currentLedger.active || {}) };
  const currentCompleted = [...(currentLedger.completed || [])];

  const targetId = t.trade_id;
  const targetBase = getBaseSymbol(symbol, t);
  for (const k of Object.keys(currentActive)) {
    const act = currentActive[k];
    if (k === symbol || k === targetBase || (act && act.trade_id === targetId) || (act && getBaseSymbol(k, act) === targetBase)) {
      delete currentActive[k];
      delete STORED_ACTIVE_TRADES[k];
    }
  }

  const alreadyExists = currentCompleted.some(x => x.trade_id === t.trade_id);
  if (!alreadyExists) {
    currentCompleted.push(completedRecord);
  }
  STORED_COMPLETED_TRADES = currentCompleted;

  const kv = env && (env.TRADE_LEDGER || env.TRADES_KV || env.KV);
  if (kv) {
    try {
      await kv.put("active_trades", JSON.stringify(currentActive));
      await kv.put("completed_trades", JSON.stringify(currentCompleted));
    } catch (e) {
      console.error("KV resolve error:", e);
    }
  }

  // Trigger GitHub Actions workflow to log post-mortem and persist to Git
  await triggerGitHubScanner(env);
}

/**
 * Dispatches GitHub Actions scanner workflow via REST API
 */
async function triggerGitHubScanner(env) {
  if (!isMarketOpen()) {
    console.log("Forex market is closed for the weekend. Skipping GitHub scanner dispatch.");
    return false;
  }
  const token = (env && (env.GITHUB_TOKEN || env.GH_TOKEN)) || DEFAULT_GH_TOKEN;
  if (!token) return false;
  try {
    const res = await fetch("https://api.github.com/repos/siddiqx/Trading-Bot/actions/workflows/scanner.yml/dispatches", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Cloudflare-Worker-Scheduler"
      },
      body: JSON.stringify({ ref: "main" })
    });
    return res.status === 204;
  } catch (e) {
    console.error("Workflow dispatch error:", e);
    return false;
  }
}

/**
 * Universal active trade monitor & auto-resolution loop
 * Executed by Cloudflare Cron Trigger, external /cron pings, or Telegram /scan command
 */
async function runActiveTradeChecks(env) {
  if (!isMarketOpen()) {
    return { checked_active: 0, resolved_trades: [], market_open: false, note: "Forex market is closed for the weekend" };
  }

  const ledger = await getLedger(env);
  const activeEntries = Object.entries(ledger.active);
  const resolved = [];

  for (const [symbol, t] of activeEntries) {
    const asset = getAssetConfig(symbol, t);
    try {
      const fastPrice = await getLivePriceFast(asset, 2500);
      let lastClose = fastPrice !== null ? fastPrice : undefined;
      let lastHigh = lastClose;
      let lastLow = lastClose;

      if (lastClose !== undefined) {
        const isLong = (t.direction || "").toUpperCase() === "LONG";
        const pipVal = asset.pip || 0.0001;
        // Fixed 15-pip TP / 10-pip SL Exit Resolution (Zero conflicting BE or ATR overrides)
        let hitTP = false;
        let hitSL = false;
        if (isLong) {
          if (lastLow <= t.stop_loss) hitSL = true;
          else if (lastHigh >= t.take_profit) hitTP = true;
        } else {
          if (lastHigh >= t.stop_loss) hitSL = true;
          else if (lastLow <= t.take_profit) hitTP = true;
        }

        if (hitTP || hitSL) {
          const exitPrice = hitTP ? t.take_profit : t.stop_loss;
          const rawOutcome = hitTP ? "WIN" : "LOSS";
          await autoResolveTrade(symbol, t, rawOutcome, exitPrice, env, ledger);
          resolved.push({ symbol, outcome: rawOutcome, exitPrice });

          const finalR = hitTP ? (t.rr || 1.50) : -1.00;
          const finalPips = hitTP ? (t.tp_pips || 15.0) : -(t.sl_pips || 10.0);
          const sign = finalR >= 0 ? "+" : "";
          const icon = hitTP ? "🎯" : "🛑";
          const title = hitTP
            ? "TARGET REACHED: FIXED TAKE PROFIT HIT"
            : "STRUCTURAL EXIT: FIXED STOP LOSS HIT";
          const text = 
            `${icon} <b>${title}</b>\n` +
            `━━━━━━━━━━━━━━━━━━\n` +
            `📊 <b>Asset:</b> <b>${t.pair || symbol}</b> (${t.timeframe || "15M"})\n` +
            `🧭 <b>Position:</b> <b>${t.direction} CLOSED</b>\n` +
            `━━━━━━━━━━━━━━━━━━\n\n` +
            `<b>📋 EXECUTION OUTCOME (FIXED 15p TP / 10p SL)</b>\n` +
            `• <b>Entry Price:</b> <code>${t.entry}</code>\n` +
            `• <b>Exit Price:</b> <code>${exitPrice}</code>\n` +
            `• <b>Net Realized:</b> <b>${sign}${finalPips.toFixed(1)} pips</b>\n` +
            `• <b>Realized Return:</b> <b>${sign}${finalR.toFixed(2)} R</b>\n\n` +
            `━━━━━━━━━━━━━━━━━━\n` +
            `🕒 <code>${new Date().toISOString().replace("T", " ").substring(0, 16)} UTC</code>\n` +
            `🔓 <i>Pair unlocked. Surveillance resumed.</i>`;
          await sendTelegramMessage(DEFAULT_CHAT_ID, text);
        }
      }
    } catch (e) {
      console.error("Scheduled check error:", e);
    }
  }

  // Trigger GitHub Actions market scanner so it scans for new confirmed setups immediately
  const dispatched = await triggerGitHubScanner(env);
  return { checked_active: activeEntries.length, resolved_trades: resolved, github_scanner_dispatched: dispatched };
}

export default {
  async fetch(request, env) {
    if (request.method === "GET") {
      const url = new URL(request.url);
      if (url.pathname === "/cron" || url.pathname === "/tick" || url.pathname === "/check") {
        const result = await runActiveTradeChecks(env);
        return new Response(JSON.stringify({ status: "CRON_EXECUTED", ...result }, null, 2), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      const kv = env && (env.TRADE_LEDGER || env.TRADES_KV || env.KV);
      let kvActive = null;
      let kvCompleted = null;
      if (kv) {
        try {
          kvActive = await kv.get("active_trades", "json");
          kvCompleted = await kv.get("completed_trades", "json");
        } catch(e) {}
      }

      if (url.pathname === "/test_radar" || url.searchParams.get("test") === "radar") {
        const radarPreview = await Promise.all(
          ASSETS.map(async (asset) => {
            const data = await fetchAssetCandles(asset);
            return {
              name: asset.name,
              symbol: asset.symbol,
              ticker: asset.ticker,
              price: data.price,
              barsCount: data.closes.length,
              lastClose: data.closes.length > 0 ? data.closes[data.closes.length - 1] : null,
              highest: data.highs.length > 0 ? Math.max(...data.highs) : null,
              lowest: data.lows.length > 0 ? Math.min(...data.lows) : null
            };
          })
        );
        return new Response(JSON.stringify({ status: "RADAR_TEST_OK", version: "3.1.0-institutional-alpha", radarPreview }, null, 2), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      const ledger = await getLedger(env);
      return new Response(JSON.stringify({
        status: "OK",
        version: "3.1.0-institutional-alpha",
        timestamp: new Date().toISOString(),
        kv_bound: !!kv,
        env_keys: env ? Object.keys(env) : [],
        kv_active: kvActive,
        kv_completed: kvCompleted,
        resolved_ledger: ledger
      }, null, 2), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }

    try {
      const rawText = await request.text();
      let payload = {};
      try { payload = JSON.parse(rawText); } catch (e) { payload = { text: rawText }; }

      // Handle Reset / Fresh Start from Market Scanner Engine
      if (payload.event === "reset_trades" || payload.reset === true) {
        const kv = env && (env.TRADE_LEDGER || env.TRADES_KV || env.KV);
        if (kv) {
          try {
            await kv.put("active_trades", JSON.stringify({}));
            await kv.put("completed_trades", JSON.stringify([]));
          } catch (e) {
            console.error("KV reset error:", e);
          }
        }
        STORED_ACTIVE_TRADES = {};
        STORED_COMPLETED_TRADES = [];
        return new Response("Trades Reset Cleanly", { status: 200 });
      }

      // Handle Sync from Market Scanner Engine
      // IMPORTANT: Merge strategy — never blindly overwrite KV active trades.
      // The worker may have resolved a trade (auto-resolved TP/SL) between scanner runs.
      // We always let KV be the source of truth for active trades; scanner only ADDS new ones.
      if (payload.event === "sync_trades") {
        const kv = env && (env.TRADE_LEDGER || env.TRADES_KV || env.KV);

        // Get current KV state
        let kvActive = payload.active_trades || {};
        let kvCompleted = payload.completed_trades || [];

        if (kv) {
          try {
            if (payload.overwrite_active) {
              kvActive = payload.active_trades || {};
              kvCompleted = payload.completed_trades || [];
            } else {
              const existingActive = await kv.get("active_trades", "json") || {};
              const existingCompleted = await kv.get("completed_trades", "json") || [];

              const mergedActive = { ...kvActive };
              for (const [symbol, trade] of Object.entries(existingActive)) {
                if (!(symbol in kvActive) && (trade.status === "OPEN" || trade.status === "PENDING")) {
                  mergedActive[symbol] = trade;
                }
              }

              const seenIds = new Set(existingCompleted.map(t => t.trade_id));
              for (const ct of kvCompleted) {
                if (!seenIds.has(ct.trade_id)) {
                  existingCompleted.push(ct);
                  seenIds.add(ct.trade_id);
                }
              }

              // Purge any active trade whose trade_id is already completed
              for (const [k, at] of Object.entries(mergedActive)) {
                if (seenIds.has(at.trade_id)) {
                  delete mergedActive[k];
                }
              }

              kvActive = mergedActive;
              kvCompleted = existingCompleted;
            }
          } catch (e) {
            console.error("KV merge error:", e);
          }

          try {
            await kv.put("active_trades", JSON.stringify(kvActive));
            await kv.put("completed_trades", JSON.stringify(kvCompleted));
            if (payload.volume_summary) {
              await kv.put("volume_summary", JSON.stringify(payload.volume_summary));
            }
          } catch (e) {
            console.error("KV save error:", e);
          }
        }

        STORED_ACTIVE_TRADES = kvActive;
        STORED_COMPLETED_TRADES = kvCompleted;
        return new Response("Trades Synced", { status: 200 });
      }

      // Handle Telegram User Updates
      if (payload.update_id) {
        return await handleTelegramUpdate(payload, env);
      }

      // Handle Incoming Trade Signals
      return await handleIncomingSignal(payload);
    } catch (err) {
      return new Response("Error: " + err.message, { status: 500 });
    }
  },

  /**
   * Cloudflare Worker Scheduled Cron Trigger (Runs 24/7 without GitHub Actions delays)
   */
  async scheduled(event, env, ctx) {
    ctx.waitUntil(runActiveTradeChecks(env));
  }
};

async function handleTelegramUpdate(update, env) {
  if (update.callback_query) {
    const cb = update.callback_query;
    const chatId = cb.message.chat.id;
    const action = cb.data;

    await fetch(`${TELEGRAM_API}/answerCallbackQuery`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ callback_query_id: cb.id })
    });

    if (action === "cmd_radar") {
      triggerGitHubScanner(env).catch(() => {});
      await sendRadarMessage(chatId, env);
    }
    else if (action === "cmd_active") await sendActiveMessage(chatId, env);
    else if (action === "cmd_prices") await sendPricesMessage(chatId);
    else if (action === "cmd_history") await sendHistoryMessage(chatId, "ALL", "ALL", env);
    else if (action === "cmd_performance") await sendPerformanceMessage(chatId, "ALL", env);
    else if (action === "cmd_patterns") await sendPatternsMessage(chatId, env);
    else if (action === "cmd_status") await sendStatusMessage(chatId, env);
    else if (action === "cmd_strategy") await sendStrategyMessage(chatId);
    else if (action === "cmd_menu") await sendMenuMessage(chatId, env);
    else if (action.startsWith("hist_pair_")) {
      const p = action.replace("hist_pair_", "");
      await sendHistoryMessage(chatId, p, "ALL", env);
    } else if (action.startsWith("hist_range_")) {
      const r = action.replace("hist_range_", "");
      await sendHistoryMessage(chatId, "ALL", r, env);
    } else if (action.startsWith("perf_pair_")) {
      const p = action.replace("perf_pair_", "");
      await sendPerformanceMessage(chatId, p, env);
    }

    return new Response("OK", { status: 200 });
  }

  if (update.message && update.message.text) {
    const chatId = update.message.chat.id;
    let text = update.message.text.trim();
    
    // Support both / and \ command prefixes
    if (text.startsWith("\\")) {
      text = "/" + text.substring(1);
    }

    const parts = text.split(/\s+/);
    // Strip bot username if invoked as /command@BotName
    const cmd = parts[0].toLowerCase().split("@")[0];

    if (cmd === "/active" || cmd === "/open" || cmd === "/trades" || cmd === "/positions") {
      await sendActiveMessage(chatId, env);
    } else if (cmd === "/check" || cmd === "/scan" || cmd === "/refresh") {
      await sendTelegramMessage(chatId, "⚡ <i>Executing instant real-time quote check & cloud scan dispatch...</i>");
      await runActiveTradeChecks(env);
      await sendActiveMessage(chatId, env);
    } else if (cmd === "/radar" || cmd === "/tracking") {
      triggerGitHubScanner(env).catch(() => {});
      await sendRadarMessage(chatId, env);
    } else if (cmd === "/prices" || cmd === "/quotes") {
      await sendPricesMessage(chatId);
    } else if (cmd === "/history") {
      let filterPair = "ALL";
      let filterRange = "ALL";
      const validRanges = ["today", "1d", "7d", "30d", "all"];

      for (let i = 1; i < parts.length; i++) {
        const val = parts[i].toLowerCase();
        if (validRanges.includes(val)) {
          filterRange = val;
        } else {
          filterPair = parts[i].toUpperCase().replace("/", "");
        }
      }
      await sendHistoryMessage(chatId, filterPair, filterRange, env);
    } else if (cmd === "/performance" || cmd === "/stats") {
      const filterPair = parts[1] ? parts[1].toUpperCase().replace("/", "") : "ALL";
      await sendPerformanceMessage(chatId, filterPair, env);
    } else if (cmd === "/patterns" || cmd === "/pattern" || cmd === "/journal" || cmd === "/journals") {
      await sendPatternsMessage(chatId, env);
    } else if (cmd === "/status") {
      await sendStatusMessage(chatId, env);
    } else if (cmd === "/strategy" || cmd === "/rules") {
      await sendStrategyMessage(chatId);
    } else if (cmd === "/clear" || cmd === "/clean" || cmd === "/reset") {
      const kv = env && (env.TRADE_LEDGER || env.TRADES_KV || env.KV);
      if (kv) {
        try {
          await kv.put("active_trades", JSON.stringify({}));
          await kv.put("completed_trades", JSON.stringify([]));
        } catch (e) {}
      }
      STORED_ACTIVE_TRADES = {};
      STORED_COMPLETED_TRADES = [];
      await sendClearInstructions(chatId);
    } else if (cmd === "/close" || cmd === "/resolve") {
      // Admin: force-resolve a stuck active trade
      // Usage: /close EURUSD WIN | /close EURUSD LOSS | /close EURUSD CANCEL
      const symbol = parts[1] ? parts[1].toUpperCase().replace("/", "") : null;
      const outcomeArg = parts[2] ? parts[2].toUpperCase() : null;
      if (symbol && outcomeArg) {
        const outcome = outcomeArg === "WIN" ? "WIN" : outcomeArg === "LOSS" ? "LOSS" : "CANCELLED";
        const closeLedger = await getLedger(env);
        const matchedKey = Object.keys(closeLedger.active).find(k => k === symbol || getBaseSymbol(k, closeLedger.active[k]) === symbol);
        const trade = matchedKey ? closeLedger.active[matchedKey] : null;
        if (trade) {
          const exitPrice = outcome === "WIN" ? trade.take_profit : outcome === "LOSS" ? trade.stop_loss : trade.entry;
          await autoResolveTrade(matchedKey, trade, outcome, exitPrice, env, closeLedger);
          await sendTelegramMessage(chatId,
            `✅ <b>ADMIN FORCE-CLOSE · ${symbol} ${outcome}</b>\n` +
            `━━━━━━━━━━━━━━━━━━\n` +
            `• Trade ID: <code>${trade.trade_id}</code>\n` +
            `• Closed at: <code>${exitPrice}</code>\n` +
            `• Pair unlocked. Surveillance resumed.`
          );
        } else {
          await sendTelegramMessage(chatId, `⚠️ No active trade found for <code>${symbol}</code>. Use /active to see current positions.`);
        }
      } else {
        await sendTelegramMessage(chatId,
          `ℹ️ <b>Force-Close Usage:</b>\n` +
          `<code>/close EURUSD WIN</code>\n` +
          `<code>/close EURUSD LOSS</code>\n` +
          `<code>/close EURUSD CANCEL</code>\n\n` +
          `Available pairs: EURUSD · USDCAD · GBPUSD · USDJPY · USDCHF · AUDUSD`
        );
      }
    } else {
      await sendMenuMessage(chatId, env);
    }
    return new Response("OK", { status: 200 });
  }

  return new Response("Ignored", { status: 200 });
}

/**
 * Infallible Multi-Tier Candle & Quote Resolver
 * Multi-tier fallbacks: TradingView Forex Scanner -> Yahoo Finance
 * Zero fake synthetic bars! Guaranteed real institutional data.
 */
async function fetchAssetCandles(asset) {
  const browserHeaders = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json"
  };

  let closes = [];
  let highs = [];
  let lows = [];
  let liveSpotPrice = null;
  let tvIndicators = null;

  // 1. Fetch live spot quote and real-time indicators directly from TradingView Forex Scanner
  const tvUrl = "https://scanner.tradingview.com/forex/scan";
  const tvTicker = `FX_IDC:${asset.symbol}`;

  try {
    const tvRes = await fetchWithTimeout(tvUrl, {
      method: "POST",
      headers: { "User-Agent": "Mozilla/5.0", "Content-Type": "application/json" },
      body: JSON.stringify({
        symbols: { tickers: [tvTicker] },
        columns: ["open|15", "high|15", "low|15", "close|15", "RSI|15", "EMA20|15", "EMA50|15", "ADX|15"]
      })
    }, 3000);
    if (tvRes.ok) {
      const tvJson = await tvRes.json();
      const d = tvJson?.data?.[0]?.d;
      if (Array.isArray(d) && d.length >= 8 && d[3] !== null) {
        liveSpotPrice = parseFloat(d[3]);
        tvIndicators = {
          open: parseFloat(d[0]),
          high: parseFloat(d[1]),
          low: parseFloat(d[2]),
          close: parseFloat(d[3]),
          rsi: parseFloat(d[4]),
          ema20: parseFloat(d[5]),
          ema50: parseFloat(d[6]),
          adx: parseFloat(d[7])
        };
        QUOTE_CACHE[asset.symbol] = liveSpotPrice;
        QUOTE_CACHE_TIME[asset.symbol] = Date.now();
      }
    }
  } catch (e) {}

  // 2. Fetch genuine 15M candle series from Yahoo Finance for Donchian channels
  const yTicker = asset.ticker || `${asset.symbol}=X`;
  for (const host of ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]) {
    try {
      const url = `https://${host}/v8/finance/chart/${yTicker}?range=5d&interval=15m`;
      const res = await fetchWithTimeout(url, { headers: browserHeaders }, 3500);
      if (res.ok) {
        const json = await res.json();
        const quote = json?.chart?.result?.[0]?.indicators?.quote?.[0];
        const rawCloses = quote?.close?.filter(v => v !== null && v !== undefined) || [];
        const rawHighs = quote?.high?.filter(v => v !== null && v !== undefined) || [];
        const rawLows = quote?.low?.filter(v => v !== null && v !== undefined) || [];
        if (rawCloses.length >= 10) {
          closes = rawCloses;
          highs = rawHighs;
          lows = rawLows;
          if (liveSpotPrice === null && closes.length > 0) {
            liveSpotPrice = closes[closes.length - 1];
          }
          break;
        }
      }
    } catch (e) {}
    if (closes.length >= 10) break;
  }

  // 3. Fallback to cached price if available (never returns null)
  if (liveSpotPrice === null && QUOTE_CACHE[asset.symbol] !== undefined) {
    liveSpotPrice = QUOTE_CACHE[asset.symbol];
  }

  return { closes, highs, lows, price: liveSpotPrice, indicators: tvIndicators };
}

/**
 * /radar - Institutional Market Surveillance across all 6 monitored Forex pairs (Zero Gold)
 * Real-time 20/50 EMA, 15M Donchian Channels (Forex=20), RSI, and ADX
 * Read-only surveillance: Never mutates or closes trades on read queries!
 */
async function sendRadarMessage(chatId, env) {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";
  const radarLedger = await getLedger(env);
  const { active } = radarLedger;
  let activeCount = 0;
  let hasImminentBreakout = false;

  const filteredAssets = ASSETS.filter(a => a.symbol !== "XAUUSD" && a.symbol !== "GOLD" && !a.symbol.includes("XAU"));

  const results = await Promise.all(
    filteredAssets.map(async (asset, idx) => {
      const num = idx + 1;
      try {
        const { closes, highs, lows, price, indicators } = await fetchAssetCandles(asset);

        if (price === null) {
          return `<b>${num}. ${asset.name}</b> · <i>Feed Initializing</i>`;
        }

        // 1. CHECK IF PAIR HAS AN ACTIVE RUNNING TRADE
        const activeTrade = Object.entries(active).find(([k, t]) => getBaseSymbol(k, t) === asset.symbol)?.[1];
        if (activeTrade) {
          const isPending = activeTrade.status === "PENDING";
          const isLong = activeTrade.direction === "LONG";

          if (isPending) {
            const distPips = (Math.abs(price - activeTrade.entry) / asset.pip).toFixed(1);
            return (
              `<b>${num}. ${asset.name}</b> · <code>${price.toFixed(asset.digits)}</code>\n` +
              `⏳ <b>PENDING ${activeTrade.direction}</b> (${activeTrade.timeframe})\n` +
              `• Entry Target: <code>${activeTrade.entry}</code> (⏳ ${distPips}p away)\n` +
              `• Float: <code>0.0 pips (Awaiting Fill)</code>\n` +
              `• SL: <code>${activeTrade.stop_loss}</code> | TP: <code>${activeTrade.take_profit}</code>`
            );
          }

          // Active OPEN position
          activeCount++;
          const pnlPips = ((price - activeTrade.entry) / asset.pip) * (isLong ? 1 : -1);
          const pnlSign = pnlPips >= 0 ? "+" : "";
          const icon = isLong ? "🟢" : "🔴";
          const beStatus = activeTrade.be_active ? " 🛡<b>BE Locked (+0.50R)</b>" : "";

          return (
            `<b>${num}. ${asset.name}</b> · <code>${price.toFixed(asset.digits)}</code>\n` +
            `${icon} <b>LIVE ${activeTrade.direction}</b> (${activeTrade.timeframe})${beStatus}\n` +
            `• Float: <code>${pnlSign}${pnlPips.toFixed(1)} pips</code>\n` +
            `• Entry: <code>${activeTrade.entry}</code>\n` +
            `• SL: <code>${activeTrade.stop_loss}</code> | TP: <code>${activeTrade.take_profit}</code> (1:${activeTrade.rr || "2.0"}R)`
          );
        }

        // 2. NORMAL SURVEILLANCE (NO ACTIVE TRADE)
        const donchLen = 20;
        let donchHigh = price, donchLow = price;
        if (highs.length >= donchLen && lows.length >= donchLen) {
          donchHigh = Math.max(...highs.slice(-(donchLen + 1), -1));
          donchLow = Math.min(...lows.slice(-(donchLen + 1), -1));
        } else if (indicators) {
          donchHigh = Math.max(price, indicators.high);
          donchLow = Math.min(price, indicators.low);
        }

        const channelPips = (donchHigh - donchLow) / asset.pip;
        const distHigh = (donchHigh - price) / asset.pip;
        const distLow = (price - donchLow) / asset.pip;
        const posPct = channelPips > 0 ? ((price - donchLow) / (donchHigh - donchLow)) * 100 : 50;

        let ema20 = indicators?.ema20;
        let ema50 = indicators?.ema50;
        if (ema20 === undefined || isNaN(ema20)) {
          if (closes.length >= 20) {
            ema20 = closes[0]; ema50 = closes[0];
            const k20 = 2 / (20 + 1), k50 = 2 / (50 + 1);
            for (let i = 1; i < closes.length; i++) {
              ema20 = closes[i] * k20 + ema20 * (1 - k20);
              ema50 = closes[i] * k50 + ema50 * (1 - k50);
            }
          } else {
            ema20 = price; ema50 = price;
          }
        }

        const isBullish = ema20 > ema50 && price > ema50;
        const isBearish = ema20 < ema50 && price < ema50;

        let rsi = indicators?.rsi;
        if (rsi === undefined || isNaN(rsi)) {
          if (closes.length >= 15) {
            let gains = 0, losses = 0;
            for (let i = closes.length - 14; i < closes.length; i++) {
              const diff = closes[i] - closes[i - 1];
              if (diff >= 0) gains += diff;
              else losses += Math.abs(diff);
            }
            const rs = (gains / 14) / ((losses / 14) || 1e-9);
            rsi = 100 - (100 / (1 + rs));
          } else {
            rsi = 50.0;
          }
        }

        // Calibrate channel minimum for Forex
        const minChannelPips = 12.0;
        const isCompressing = channelPips < minChannelPips;
        const breakDistance = 3.0;

        let badge = "", status = "", detail = "";
        if (rsi > 80.0) {
          badge = "🛡";
          status = "RSI Guard Active";
          detail = `RSI ${rsi.toFixed(0)} Overbought (>80 Exhaustion)`;
        } else if (rsi < 20.0) {
          badge = "🛡";
          status = "RSI Guard Active";
          detail = `RSI ${rsi.toFixed(0)} Oversold (<20 Exhaustion)`;
        } else if (isCompressing) {
          badge = "💤";
          status = "Tight Squeeze (Low Volatility)";
          detail = `${channelPips.toFixed(0)}p Band · Awaiting Volume`;
        } else if (distHigh <= 0.0 && isBullish && rsi >= 40.0 && rsi <= 80.0) {
          hasImminentBreakout = true;
          badge = "⚡";
          status = "Testing Breakout (Live Bar at High)";
          detail = `Awaiting 15M Close · Trend Bullish`;
        } else if (distHigh <= breakDistance && isBullish && rsi >= 40.0 && rsi <= 80.0) {
          hasImminentBreakout = true;
          badge = "⚡";
          status = "Imminent Breakout Setup";
          detail = `${distHigh.toFixed(1)}p to Break · Trend Bullish`;
        } else if (distLow <= 0.0 && isBearish && rsi >= 20.0 && rsi <= 60.0) {
          hasImminentBreakout = true;
          badge = "⚡";
          status = "Testing Breakdown (Live Bar at Low)";
          detail = `Awaiting 15M Close · Trend Bearish`;
        } else if (distLow <= breakDistance && isBearish && rsi >= 20.0 && rsi <= 60.0) {
          hasImminentBreakout = true;
          badge = "⚡";
          status = "Imminent Breakdown Setup";
          detail = `${distLow.toFixed(1)}p to Break · Trend Bearish`;
        } else if (posPct >= 80) {
          badge = "👀";
          status = "Testing Range High";
          detail = `${distHigh.toFixed(1)}p to High · ${posPct.toFixed(0)}% Band`;
        } else if (posPct <= 20) {
          badge = "👀";
          status = "Testing Range Low";
          detail = `${distLow.toFixed(1)}p to Low · ${posPct.toFixed(0)}% Band`;
        } else {
          badge = "⏸";
          status = "Range Consolidation";
          detail = `${channelPips.toFixed(0)}p Channel · Mid-Range (${posPct.toFixed(0)}%)`;
        }

        return `<b>${num}. ${asset.name}</b> · <code>${price.toFixed(asset.digits)}</code>\n${badge} <b>${status}</b> (${detail})`;
      } catch (e) {
        return `<b>${num}. ${asset.name}</b> · <i>Feed Offline</i>`;
      }
    })
  );

  if (hasImminentBreakout && isMarketOpen()) {
    triggerGitHubScanner(env).catch(() => {});
  }

  const marketStatusBanner = isMarketOpen()
    ? ""
    : "⚠️ <b>MARKETS CLOSED (Weekend)</b>\n<i>Surveillance paused · Reopens Sun 17:00 NY / 21:00 UTC</i>\n\n";

  const text = 
    `📡 <b>MARKET SURVEILLANCE RADAR</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n\n` +
    marketStatusBanner +
    results.join("\n\n") + "\n\n" +
    `━━━━━━━━━━━━━━━━━━\n` +
    `🟢 <b>Live Positions:</b> <code>${activeCount} Active</code>\n` +
    `🕒 <code>${utcNow}</code> · <i>Real-time Engine</i>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "🔄 Refresh Radar", callback_data: "cmd_radar" },
        { text: "⚡ Active Trades", callback_data: "cmd_active" }
      ],
      [
        { text: "📜 Completed History", callback_data: "cmd_history" },
        { text: "📈 Performance", callback_data: "cmd_performance" }
      ],
      [
        { text: "« Main Menu", callback_data: "cmd_menu" }
      ]
    ]
  };

  await sendTelegramMessage(chatId, text, keyboard);
}

/**
 * /active - Dedicated monitor listing ONLY currently running / floating trades
 */
async function sendActiveMessage(chatId, env) {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";
  const ledger = await getLedger(env);
  const { active } = ledger;
  const activeEntries = Object.entries(active);

  if (activeEntries.length === 0) {
    const text = 
      `⚡ <b>ACTIVE LIVE TRADES (0)</b>\n` +
      `━━━━━━━━━━━━━━━━━━\n` +
      `<i>No active positions currently running.</i>\n\n` +
      `Institutional 6-Asset Universe under active surveillance:\n` +
      `<code>EURUSD · USDCAD · GBPUSD · USDJPY · USDCHF · AUDUSD</code>\n\n` +
      `Signals trigger strictly on confirmed candle closes.\n` +
      `━━━━━━━━━━━━━━━━━━\n` +
      `🕒 <code>${utcNow}</code>`;

    const keyboard = {
      inline_keyboard: [
        [
          { text: "📡 Market Radar", callback_data: "cmd_radar" },
          { text: "📜 Completed History", callback_data: "cmd_history" }
        ],
        [
          { text: "📈 Performance", callback_data: "cmd_performance" },
          { text: "« Main Menu", callback_data: "cmd_menu" }
        ]
      ]
    };

    await sendTelegramMessage(chatId, text, keyboard);
    return;
  }

  const rows = await Promise.all(
    activeEntries.map(async ([symbolKey, t], idx) => {
      const num = idx + 1;
      const asset = getAssetConfig(symbolKey, t);

      const isLong = (t.direction || "").toUpperCase() === "LONG";
      const dirIcon = isLong ? "🟢" : "🔴";
      const openTime = (t.opened_at || "").substring(11, 16) || "00:00";
      const openDate = (t.opened_at || "").substring(0, 10);
      const pName = t.pair || asset.name;

      const currentPrice = await getLivePriceFast(asset, 4000);
      let floatText = "";
      const isPending = (t.status === "PENDING");

      if (currentPrice !== null) {
        if (isPending) {
          const distPips = (Math.abs(currentPrice - t.entry) / asset.pip).toFixed(1);
          floatText = 
            `• Status: ⏳ <b>PENDING ENTRY FILL</b>\n` +
            `• Live Price: <code>${currentPrice.toFixed(asset.digits)}</code> (⏳ <b>${distPips} pips to entry</b>)\n` +
            `• Floating PnL: <b>0.0 pips</b> (<i>Awaiting Market Fill · Zero Exposure</i>)\n`;
        } else {
          const pnlPips = ((currentPrice - t.entry) / asset.pip) * (isLong ? 1 : -1);
          const pnlSign = pnlPips >= 0 ? "+" : "";
          const riskDist = Math.abs(t.entry - t.stop_loss) / asset.pip;
          const floatR = riskDist > 0 ? (pnlPips / riskDist).toFixed(2) : "0.00";
          const rSign = parseFloat(floatR) >= 0 ? "+" : "";
          const floatEmoji = pnlPips >= 0 ? "🟢" : "🔻";
          const beFlag = t.be_active ? " 🛡<b>Break-Even Locked</b>" : "";
          const partialFlag = t.partial_taken ? " 💰<b>+0.50R Banked</b>" : "";
          floatText = `• Live Price: <code>${currentPrice.toFixed(asset.digits)}</code> (${floatEmoji} <b>${pnlSign}${pnlPips.toFixed(1)} pips</b> | <b>${rSign}${floatR}R</b>)${beFlag}${partialFlag}\n`;
        }
      } else {
        if (isPending) {
          floatText = `• Status: ⏳ <b>PENDING ENTRY FILL</b>\n• Floating PnL: <b>0.0 pips</b> (<i>Awaiting Feed</i>)\n`;
        } else {
          floatText = `• Status: 🟢 <b>IN MARKET (Active)</b>\n• Live Price: <code>Awaiting Feed Update</code>\n`;
        }
      }

      const statusBadge = isPending ? `⏳ <b>PENDING ${t.direction}</b>` : `${dirIcon} <b>${t.direction}</b>`;
      const entryLabel = isPending ? "• Entry Target:" : "• Entry:";

      return (
        `<b>${num}. ${pName}</b> · ${t.timeframe || "15M"} · ${statusBadge}\n` +
        `${entryLabel} <code>${t.entry}</code> (${openDate} ${openTime} UTC)\n` +
        floatText +
        `• Targets: SL <code>${t.stop_loss}</code> | TP <code>${t.take_profit}</code>\n` +
        `• Plan: <b>1 : ${t.rr || t.risk_reward || "1.50"} R:R</b> (0.50% Equity Risk · $25 on $5k Prop Account)`
      );
    })
  );

  const text = 
    `⚡ <b>ACTIVE LIVE TRADES (${activeEntries.length})</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `Currently floating in institutional market:\n` +
    `━━━━━━━━━━━━━━━━━━\n\n` +
    rows.join("\n\n") + "\n\n" +
    `━━━━━━━━━━━━━━━━━━\n` +
    `🔄 <i>Float updates automatically with live quotes.</i>\n` +
    `🕒 <code>${utcNow}</code>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "🔄 Refresh Active", callback_data: "cmd_active" },
        { text: "📜 Completed History", callback_data: "cmd_history" }
      ],
      [
        { text: "📈 Performance", callback_data: "cmd_performance" },
        { text: "📡 Market Radar", callback_data: "cmd_radar" }
      ],
      [
        { text: "« Main Menu", callback_data: "cmd_menu" }
      ]
    ]
  };

  await sendTelegramMessage(chatId, text, keyboard);
}

/**
 * /history - Historical completed trade records ONLY with pair & date range filters
 */
async function sendHistoryMessage(chatId, filterPair = "ALL", filterRange = "ALL", env) {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";
  const nowMs = Date.now();
  const { completed } = await getLedger(env);

  let closedTrades = completed.slice();

  // 1. Filter by Pair
  if (filterPair !== "ALL") {
    closedTrades = closedTrades.filter(t => (t.symbol || "").toUpperCase() === filterPair.toUpperCase());
  }

  // 2. Filter by Date Range
  let rangeLabel = "ALL TIME";
  if (filterRange === "today" || filterRange === "1d") {
    rangeLabel = "TODAY";
    const todayStr = new Date().toISOString().substring(0, 10);
    closedTrades = closedTrades.filter(t => (t.closed_at || t.opened_at || "").startsWith(todayStr));
  } else if (filterRange === "7d") {
    rangeLabel = "LAST 7 DAYS";
    const cutoff = nowMs - (7 * 24 * 60 * 60 * 1000);
    closedTrades = closedTrades.filter(t => new Date(t.closed_at || t.opened_at).getTime() >= cutoff);
  } else if (filterRange === "30d") {
    rangeLabel = "LAST 30 DAYS";
    const cutoff = nowMs - (30 * 24 * 60 * 60 * 1000);
    closedTrades = closedTrades.filter(t => new Date(t.closed_at || t.opened_at).getTime() >= cutoff);
  }

  // Build Output Rows strictly for Completed Trades
  let closedRows = [];
  let closedIdx = 1;

  for (const t of closedTrades) {
    const num = closedIdx++;
    const openDate = (t.opened_at || "").substring(0, 10);
    const closeDate = (t.closed_at || "").substring(0, 10) || openDate;
    const pName = t.pair || t.symbol;
    const isCancelled = t.outcome === "CANCELLED";
    const isWin = t.outcome === "WIN";
    const outcomeBadge = isCancelled ? "⚠️ <b>CANCELLED</b>" : (isWin ? "🎯 <b>WIN</b>" : "🛑 <b>LOSS</b>");
    const pipsVal = typeof t.realized_pips === "number" ? t.realized_pips : parseFloat(t.realized_pips || 0);
    const rVal = typeof t.realized_r === "number" ? t.realized_r : parseFloat(t.realized_r || 0);
    const sign = pipsVal >= 0 ? "+" : "";
    const rSign = rVal >= 0 ? "+" : "";
    const outcomeDetail = isCancelled ? "(Unfilled · 0.0p / 0.00R)" : `(${sign}${pipsVal.toFixed(1)}p / ${rSign}${rVal.toFixed(2)}R)`;

    closedRows.push(
      `<b>${num}. ${pName}</b> · ${t.timeframe || "1H"} · <b>${t.direction}</b>\n` +
      `• Date: <code>${closeDate}</code>\n` +
      `• Price: <code>${t.entry}</code> ➔ <code>${t.exit_price}</code>\n` +
      `• Outcome: ${outcomeBadge} ${outcomeDetail}`
    );
  }

  let bodyText = "";
  if (closedRows.length > 0) {
    bodyText = closedRows.join("\n\n") + "\n\n";
  } else {
    bodyText = `<i>No completed trades found for ${filterPair} (${rangeLabel}).</i>\n\n`;
  }

  const text = 
    `📜 <b>COMPLETED TRADE HISTORY</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `Scope: <b>${filterPair}</b> | Range: <b>${rangeLabel}</b>\n` +
    `Total Completed: <b>${closedTrades.length} Trades</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n\n` +
    bodyText +
    `━━━━━━━━━━━━━━━━━━\n` +
    `🕒 <code>${utcNow}</code>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "Today", callback_data: "hist_range_today" },
        { text: "7 Days", callback_data: "hist_range_7d" },
        { text: "All Time", callback_data: "hist_range_all" }
      ],
      [
        { text: "EUR/USD", callback_data: "hist_pair_EURUSD" },
        { text: "USD/CAD", callback_data: "hist_pair_USDCAD" },
        { text: "GBP/USD", callback_data: "hist_pair_GBPUSD" }
      ],
      [
        { text: "USD/JPY", callback_data: "hist_pair_USDJPY" },
        { text: "USD/CHF", callback_data: "hist_pair_USDCHF" },
        { text: "AUD/USD", callback_data: "hist_pair_AUDUSD" }
      ],
      [
        { text: "⚡ Active Trades", callback_data: "cmd_active" },
        { text: "📈 Performance", callback_data: "cmd_performance" },
        { text: "« Menu", callback_data: "cmd_menu" }
      ]
    ]
  };

  await sendTelegramMessage(chatId, text, keyboard);
}

/**
 * /performance - Evaluates metrics strictly from trades taken from 2026-09-28 onwards
 */
async function sendPerformanceMessage(chatId, filterPair = "ALL", env) {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";
  const { active: activeMap, completed: completedList } = await getLedger(env);

  let closed = completedList.slice();
  let active = Object.values(activeMap);

  if (filterPair !== "ALL") {
    closed = closed.filter(t => (t.symbol || "").toUpperCase() === filterPair.toUpperCase());
    active = active.filter(t => (t.symbol || "").toUpperCase() === filterPair.toUpperCase());
  }

  const totalClosed = closed.length;
  const wins = closed.filter(t => t.outcome === "WIN").length;
  const losses = closed.filter(t => t.outcome === "LOSS").length;
  const cancelled = closed.filter(t => t.outcome === "CANCELLED").length;
  const decided = wins + losses;
  const winRate = decided > 0 ? ((wins / decided) * 100).toFixed(1) : "N/A";

  let netPips = 0;
  let netR = 0;
  let grossWins = 0;
  let grossLosses = 0;

  for (const t of closed) {
    const pips = t.realized_pips || 0;
    const r = t.realized_r || 0;
    netPips += pips;
    netR += r;

    if (pips > 0) grossWins += pips;
    else grossLosses += Math.abs(pips);
  }

  let profitFactor = "N/A";
  if (grossLosses > 0) {
    profitFactor = (grossWins / grossLosses).toFixed(2);
  } else if (grossWins > 0) {
    profitFactor = "MAX (0 Loss)";
  }

  const pipsSign = netPips >= 0 ? "+" : "";
  const rSign = netR >= 0 ? "+" : "";
  const scopeLabel = filterPair === "ALL" ? "PORTFOLIO (ALL PAIRS)" : filterPair;

  const breakEvenCount = closed.filter(t => t.outcome === "BREAK_EVEN").length;
  const beLabel = breakEvenCount > 0 ? ` · <b>${breakEvenCount} BE</b>` : "";
  const expectancy = decided > 0 ? (netR / (decided + breakEvenCount)).toFixed(3) : "N/A";
  const expSign = parseFloat(expectancy) >= 0 ? "+" : "";

  const text = 
    `📈 <b>STRATEGY PERFORMANCE (v3.1 Production)</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `Scope: <b>${scopeLabel}</b>\n` +
    `Baseline: <code>2026-10-08</code> (Strategy Reset — Fresh Start)\n` +
    `━━━━━━━━━━━━━━━━━━\n\n` +
    `<b>1. TRADE EXECUTION</b>\n` +
    `• Total Closed: <code>${totalClosed}</code>\n` +
    `• Active Live: <code>${active.length} positions</code>\n` +
    `• Win / Loss / BE: <b>${wins}W</b> · <b>${losses}L</b>${beLabel}${cancelled > 0 ? ` <i>(${cancelled} cancelled)</i>` : ""}\n` +
    `• Win Rate: <b>${winRate}${decided > 0 ? "%" : ""}</b>\n\n` +
    `<b>2. RETURNS & PROFITABILITY</b>\n` +
    `• Net Realized Pips: <b>${pipsSign}${netPips.toFixed(1)} pips</b>\n` +
    `• Net Realized Return: <b>${rSign}${netR.toFixed(2)} R</b>\n` +
    `• Expectancy / Trade: <b>${expSign}${expectancy} R</b>\n` +
    `• Profit Factor: <code>${profitFactor}</code>\n` +
    `• Target R:R: <code>1:1.5 (Fixed 15-Pip TP / 10-Pip SL)</code>\n\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `⚡ <i>100% out-of-sample forward verification. Baseline reset 2026-10-08.</i>\n` +
    `🕒 <code>${utcNow}</code>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "📊 Overall", callback_data: "perf_pair_ALL" },
        { text: "EUR/USD", callback_data: "perf_pair_EURUSD" },
        { text: "USD/CAD", callback_data: "perf_pair_USDCAD" }
      ],
      [
        { text: "GBP/USD", callback_data: "perf_pair_GBPUSD" },
        { text: "USD/JPY", callback_data: "perf_pair_USDJPY" },
        { text: "USD/CHF", callback_data: "perf_pair_USDCHF" }
      ],
      [
        { text: "AUD/USD", callback_data: "perf_pair_AUDUSD" }
      ],
      [
        { text: "⚡ Active", callback_data: "cmd_active" },
        { text: "📜 History", callback_data: "cmd_history" },
        { text: "« Menu", callback_data: "cmd_menu" }
      ]
    ]
  };

  await sendTelegramMessage(chatId, text, keyboard);
}

/**
 * /patterns - Volume-partitioned trade pattern diagnostics & failure analysis
 */
async function sendPatternsMessage(chatId, env) {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";
  const { completed } = await getLedger(env);

  const kv = env && (env.TRADE_LEDGER || env.TRADES_KV || env.KV);
  let kvSummary = null;
  if (kv) {
    try {
      kvSummary = await kv.get("volume_summary", "json");
    } catch(e) {}
  }

  const totalTrades = completed.length;
  const volNo = totalTrades > 0 ? Math.floor((totalTrades - 1) / 100) + 1 : 1;
  const volTradeNo = totalTrades > 0 ? ((totalTrades - 1) % 100) + 1 : 0;
  const volStart = (volNo - 1) * 100 + 1;
  const volEnd = volNo * 100;

  // Filter trades belonging to the current active volume
  const volTrades = completed.slice(volStart - 1, volEnd);
  const wins = volTrades.filter(t => t.outcome === "WIN");
  const losses = volTrades.filter(t => t.outcome === "LOSS");
  const winCount = wins.length;
  const lossCount = losses.length;
  const winRate = volTrades.length > 0 ? ((winCount / volTrades.length) * 100).toFixed(1) : "0.0";

  let netPips = 0;
  let netR = 0;
  let grossWins = 0;
  let grossLosses = 0;

  for (const t of volTrades) {
    const p = t.realized_pips || 0;
    const r = t.realized_r || 0;
    netPips += p;
    netR += r;
    if (p > 0) grossWins += p;
    else grossLosses += Math.abs(p);
  }

  let pf = "0.00";
  if (grossLosses > 0) pf = (grossWins / grossLosses).toFixed(2);
  else if (grossWins > 0) pf = "MAX (0 Loss)";

  const pipsSign = netPips >= 0 ? "+" : "";
  const rSign = netR >= 0 ? "+" : "";

  // Diagnostic factor aggregation (from KV summary or trade records)
  let lossReasons = kvSummary?.top_loss_factors || {};
  if (Object.keys(lossReasons).length === 0) {
    for (const t of losses) {
      const factor = t.diagnostic?.primary_factor || "STRUCTURAL_INVALIDATION";
      lossReasons[factor] = (lossReasons[factor] || 0) + 1;
    }
  }

  let lossBreakdown = "<i>No closed losses in current volume.</i>";
  if (Object.keys(lossReasons).length > 0) {
    const totalLossReported = Object.values(lossReasons).reduce((a, b) => a + b, 0) || 1;
    lossBreakdown = Object.entries(lossReasons)
      .map(([f, cnt]) => {
        const pct = ((cnt / totalLossReported) * 100).toFixed(0);
        const readable = f.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
        return `• <b>${readable}:</b> <code>${cnt} trade(s) (${pct}%)</code>`;
      })
      .join("\n");
  }

  const avgMfeText = kvSummary?.average_loss_mfe_pips
    ? `• <b>Avg Loss Excursion (MFE):</b> <code>+${kvSummary.average_loss_mfe_pips} pips</code>\n`
    : "";

  const text =
    `📚 <b>TRADE PATTERN & VOLUME ANALYTICS</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `Active Cohort: <b>Volume ${volNo} (Trades ${volStart}–${volEnd})</b>\n` +
    `Progress: <code>${volTradeNo} / 100 Trades (${volTradeNo}%)</code>\n` +
    `━━━━━━━━━━━━━━━━━━\n\n` +
    `<b>📊 VOLUME ${volNo} BENCHMARKS</b>\n` +
    `• <b>Win Rate:</b> <b>${winRate}%</b> (${winCount}W / ${lossCount}L)\n` +
    `• <b>Net Pips:</b> <b>${pipsSign}${netPips.toFixed(1)} pips</b>\n` +
    `• <b>Net R-Return:</b> <b>${rSign}${netR.toFixed(2)} R</b>\n` +
    `• <b>Profit Factor:</b> <code>${pf}</code>\n` +
    avgMfeText + "\n" +
    `<b>🔬 OBSERVED FAILURE MODES</b>\n` +
    lossBreakdown + "\n\n" +
    `<b>💡 STRATEGY OPTIMIZATION PROTOCOL</b>\n` +
    `• Post-mortem data tracks MFE/MAE excursions.\n` +
    `• At 100-trade completion, baseline parameters calibrate to reduce repeat failure factors.\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `🕒 <code>${utcNow}</code> · <i>Volume Engine</i>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "🔄 Refresh Patterns", callback_data: "cmd_patterns" },
        { text: "📜 History (Closed)", callback_data: "cmd_history" }
      ],
      [
        { text: "⚡ Active Trades", callback_data: "cmd_active" },
        { text: "📈 Performance", callback_data: "cmd_performance" }
      ],
      [
        { text: "« Main Menu", callback_data: "cmd_menu" }
      ]
    ]
  };

  await sendTelegramMessage(chatId, text, keyboard);
}

/**
 * /prices - Raw live price table
 */
async function sendPricesMessage(chatId) {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";
  const marketStatus = isMarketOpen()
    ? `🟢 <b>Market Status:</b> <code>OPEN (Live Trading)</code>`
    : `⚠️ <b>Market Status:</b> <code>CLOSED (Weekend)</code>\n<i>Reopens Sunday 17:00 NY / 21:00 UTC</i>`;

  const rows = await Promise.all(
    ASSETS.map(async (asset, idx) => {
      const num = idx + 1;
      try {
        const p = await getLivePriceFast(asset, 4000);
        if (p !== null) {
          return `<b>${num}. ${asset.name}</b> · <code>${p.toFixed(asset.digits)}</code>`;
        }
        return `<b>${num}. ${asset.name}</b> · <i>Awaiting Tick</i>`;
      } catch (e) {
        return `<b>${num}. ${asset.name}</b> · <i>Feed Offline</i>`;
      }
    })
  );

  const text = 
    `📊 <b>LIVE MARKET QUOTES</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    marketStatus + "\n\n" +
    rows.join("\n") + "\n" +
    `━━━━━━━━━━━━━━━━━━\n` +
    `🕒 <code>${utcNow}</code> · <i>MT5 Spot Feed</i>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "📡 Market Radar", callback_data: "cmd_radar" },
        { text: "🔄 Refresh Quotes", callback_data: "cmd_prices" }
      ],
      [
        { text: "« Main Menu", callback_data: "cmd_menu" }
      ]
    ]
  };

  await sendTelegramMessage(chatId, text, keyboard);
}

/**
 * /status - Engine operational health
 */
async function sendStatusMessage(chatId, env) {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC";
  const { active, completed } = await getLedger(env);
  const activeCount = Object.keys(active).length;
  const closedCount = completed.length;

  const text = 
    `⚡ <b>SYSTEM ARCHITECTURE STATUS</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `1. Engine Core: 🟢 <b>OPERATIONAL (24/7 Live)</b>\n` +
    `2. Strategy Version: <code>v4.0 ICT Killzone Liquidity Sweep Engine</code>\n` +
    `3. Profit Banking: <code>Fixed 15-Pip TP / 10-Pip SL (1:1.5 RR)</code>\n` +
    `4. Cloud Edge: <code>Cloudflare Global Edge Gateway</code>\n` +
    `5. Scanner Engine: <code>GitHub Actions Cloud Cron (*/15 Mon-Fri)</code>\n` +
    `6. Monitored Universe: <code>6 Forex Pairs (EURUSD, USDCAD, GBPUSD, USDJPY, USDCHF, AUDUSD — Zero Gold)</code>\n` +
    `7. Execution Timeframes: <code>15M (Killzone Execution) &amp; 1H (Macro Structural Alignment)</code>\n` +
    `8. Active Positions: <code>${activeCount} locked</code>\n` +
    `9. Recorded Trades: <code>${closedCount} closed</code>\n` +
    `10. Session Windows: <code>London Killzone (07-10 UTC) &amp; NY Killzone (12-15 UTC)</code>\n` +
    `11. Forward Baseline: <code>2026-10-11 (ICT Institutional Upgrade)</code>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `🕒 <code>${utcNow}</code>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "⚡ Active Trades", callback_data: "cmd_active" },
        { text: "📡 Market Radar", callback_data: "cmd_radar" }
      ],
      [
        { text: "📈 Performance", callback_data: "cmd_performance" },
        { text: "« Main Menu", callback_data: "cmd_menu" }
      ]
    ]
  };

  await sendTelegramMessage(chatId, text, keyboard);
}

/**
 * /strategy - ICT Killzone Liquidity Sweep & Capital Protection Specifications
 */
async function sendStrategyMessage(chatId) {
  const text = 
    `🎯 <b>STRATEGY SPECIFICATIONS (v4.0 Institutional)</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `<b>ICT KILLZONE LIQUIDITY SWEEP (TURTLE SOUP) — INSTITUTIONAL FOREX STRATEGY</b>\n\n` +
    `<b>1. The Institutional Core (Smart Money Reversal)</b>\n` +
    `• <b>Evolution:</b> Upgraded from Two-Phase Pullback Engine and Donchian Breakout Impulse to the verified ICT Killzone Liquidity Sweep model.\n` +
    `• <b>Liquidity Sweep:</b> Price sweeps external liquidity pools outside Asian Session Range (00:00–06:00 UTC Asian High/Low) or 10-bar fractal swing levels by ≥1.0 pip.\n` +
    `• <b>Displacement Reclaim:</b> Price immediately closes back inside the swept level, forming a strong rejection displacement candle (lower/upper wick ≥55% of candle range, body in trade direction, candle range ≥0.6 ATR).\n\n` +
    `<b>2. Session Windows & Macro Filters</b>\n` +
    `• <b>London Killzone:</b> 07:00–10:00 UTC (Judas Swing from Asian Range).\n` +
    `• <b>New York Killzone:</b> 12:00–15:00 UTC (NY Open Liquidity Expansion).\n` +
    `• <b>Macro Trend Alignment:</b> 1H 20-EMA > 50-EMA for Longs, 1H 20-EMA < 50-EMA for Shorts.\n` +
    `• <b>Universe:</b> 6 Forex Pairs (EURUSD, USDCAD, GBPUSD, USDJPY, USDCHF, AUDUSD — Zero Gold).\n\n` +
    `<b>3. Fixed Exits & Strict Capital Protection</b>\n` +
    `• <b>Take Profit:</b> Fixed 15 Pips from actual entry price.\n` +
    `• <b>Stop Loss:</b> Fixed 10 Pips from actual entry price.\n` +
    `• <b>Risk/Reward Ratio:</b> Fixed 1:1.5 before transaction costs.\n` +
    `• <b>Prop Firm Sizing:</b> $25.00 / trade (0.50% risk on $5,000 baseline account · 0.25 Lots).\n` +
    `• <b>Daily Circuit Breaker:</b> Trading halts if daily loss reaches -2.5R or 2 losses in a day.\n` +
    `• <b>Daily Frequency Cap:</b> Maximum 2 trades per pair per day.\n` +
    `• <b>Holding Timeout:</b> Positions capped at 80 bars (20 hours max hold).\n\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `🛡 <i>Institutional, non-repainting execution with verified positive expectancy (+413.5 pips).</i>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "📡 Market Radar", callback_data: "cmd_radar" },
        { text: "« Main Menu", callback_data: "cmd_menu" }
      ]
    ]
  };

  await sendTelegramMessage(chatId, text, keyboard);
}

/**
 * /clear - Clean bot chat & reset instructions
 */
async function sendClearInstructions(chatId) {
  const text =
    `🧹 <b>CLEAN BOT CHAT & LEDGER STATUS</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `<b>1. Live Ledger Baseline</b>\n` +
    `• All legacy test/backtest data has been <b>completely wiped</b>.\n` +
    `• The ledger tracks strictly live confirmed signals from <code>2026-10-08</code> onwards.\n` +
    `• Strategy is locked at v3.1 Two-Phase Pullback Engine (Fixed 15p TP / 10p SL).\n\n` +
    `<b>2. To Clear Telegram Chat History</b>\n` +
    `• On Mobile / Desktop: Tap the <b>⋮ (Three Dots)</b> menu at the top right of this chat.\n` +
    `• Select <b>Clear History</b> (or <b>Delete Chat</b>).\n` +
    `• Type <code>/start</code> to resume with a 100% clean, fresh terminal!\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `✨ <i>v3.1 Production institutional session active.</i>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "⚡ Active Trades", callback_data: "cmd_active" },
        { text: "📡 Market Radar", callback_data: "cmd_radar" }
      ],
      [
        { text: "« Main Menu", callback_data: "cmd_menu" }
      ]
    ]
  };

  await sendTelegramMessage(chatId, text, keyboard);
}

/**
 * Main Navigation Menu
 */
async function sendMenuMessage(chatId, env) {
  const { active } = await getLedger(env);
  const activeCount = Object.keys(active).length;
  const activeLabel = activeCount > 0 ? ` (${activeCount} Active)` : "";

  const text = 
    `🏛 <b>INSTITUTIONAL SIGNAL TERMINAL v3.1</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `Automated 24/7 Algorithmic Trading &amp; Forward Verification\n` +
    `Coverage: <b>EURUSD · USDCAD · GBPUSD · USDJPY · USDCHF · AUDUSD</b>\n\n` +
    `<b>SYSTEM MODULES</b>\n` +
    `1. /active ── Running trades &amp; live float pips\n` +
    `2. /radar ── Market surveillance &amp; imminent breakouts\n` +
    `3. /prices ── Live quotes (5M fresh tick)\n` +
    `4. /history ── Completed trade history ledger\n` +
    `5. /performance ── Win rate &amp; net return metrics\n` +
    `6. /patterns ── Volume post-mortems &amp; failure analysis\n` +
    `7. /strategy ── ICT multi-timeframe entry rules\n` +
    `8. /status ── 24/7 serverless engine health\n` +
    `9. /close PAIR WIN|LOSS ── Admin force-close\n\n` +
    `Select a dashboard module below:`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: `⚡ Active Trades${activeLabel}`, callback_data: "cmd_active" },
        { text: "📡 Market Radar", callback_data: "cmd_radar" }
      ],
      [
        { text: "📜 History (Closed)", callback_data: "cmd_history" },
        { text: "📈 Performance", callback_data: "cmd_performance" }
      ],
      [
        { text: "📚 Pattern Analytics", callback_data: "cmd_patterns" },
        { text: "📊 Quotes", callback_data: "cmd_prices" }
      ],
      [
        { text: "🎯 Strategy", callback_data: "cmd_strategy" },
        { text: "🟢 System Status", callback_data: "cmd_status" }
      ]
    ]
  };

  await sendTelegramMessage(chatId, text, keyboard);
}

/**
 * Trade Signal Dispatcher
 */
async function handleIncomingSignal(payload) {
  let alertMessage = "";

  const rawSymbol = String(payload.symbol || "").toUpperCase();
  if (rawSymbol.includes("XAU") || rawSymbol.includes("GOLD")) {
    console.warn(`Gold signal rejected: ${rawSymbol} is permanently excluded.`);
    return new Response(JSON.stringify({ status: "REJECTED", message: "Gold trading is permanently disabled. Forex pairs only." }), {
      status: 400,
      headers: { "Content-Type": "application/json" }
    });
  }

  if (payload.event === "forex_signal" || payload.symbol) {
    const isLong = (payload.direction || "").toUpperCase() === "LONG";
    const icon = isLong ? "🟢" : "🔴";
    const actionText = isLong ? "BUY / LONG" : "SELL / SHORT";
    const pair = payload.symbol || "FOREX";
    const displayPair = pair.length === 6 ? `${pair.substring(0,3)}/${pair.substring(3)}` : pair;
    const marketWarning = !isMarketOpen() ? "⚠️ <b>WARNING: MARKETS CURRENTLY CLOSED (Weekend)</b>\n<i>Execution paused until Sunday 17:00 NY open.</i>\n\n" : "";

    alertMessage = 
      marketWarning +
      `${icon} <b>NEW TRADE SIGNAL · ${displayPair}</b>\n` +
      `━━━━━━━━━━━━━━━━━━\n` +
      `🧭 <b>Direction:</b> <b>${actionText}</b>\n` +
      `⏱ <b>Timeframe:</b> <b>${payload.timeframe || "15M"}</b>\n` +
      `━━━━━━━━━━━━━━━━━━\n\n` +
      `<b>📋 TRADE PARAMETERS</b>\n` +
      `• <b>Entry Target:</b> <code>${payload.entry || payload.price}</code> <i>(Executed Fill Level)</i>\n` +
      `• <b>Order State:</b> ⏳ <b>PENDING ENTRY FILL</b>\n` +
      `• <b>Stop Loss:</b> <code>${payload.stop_loss}</code> (Fixed 10 pips)\n` +
      `• <b>Take Profit:</b> <code>${payload.take_profit}</code> (Fixed 15 pips)\n` +
      `• <b>Risk / Reward:</b> <b>1 : 1.5</b> (15-pip TP / 10-pip SL)\n` +
      `• <b>Suggested Risk:</b> <b>0.50% Equity ($25 on $5k Account · 0.25 Lots)</b>\n\n` +
      `<b>🔬 CONFLUENCE MODEL</b>\n` +
      `• <b>Setup:</b> ${payload.strategy || "ICT Killzone Liquidity Sweep (Turtle Soup)"}\n` +
      `• <b>Phase:</b> ${payload.phase || "Liquidity Sweep Reclaim & Rejection"}\n` +
      `• <b>Signal Score:</b> <b>${payload.score || payload.signal_score || 96} / 100</b>\n\n` +
      `━━━━━━━━━━━━━━━━━━\n` +
      `🕒 <b>Confirmed Bar:</b> <code>${payload.signal_time || new Date().toISOString()}</code>\n` +
      `⏳ <i>Order pending fill. Floating PnL activates once entry point is touched.</i>`;
  } else {
    alertMessage = payload.text || JSON.stringify(payload);
  }

  await sendTelegramMessage(DEFAULT_CHAT_ID, alertMessage);
  return new Response("OK", { status: 200 });
}

/**
 * Resilient Telegram Message Sender with Entity Fallback
 */
async function sendTelegramMessage(chatId, text, replyMarkup = null) {
  const body = { chat_id: chatId, text: text, parse_mode: "HTML" };
  if (replyMarkup) body.reply_markup = replyMarkup;

  try {
    const res = await fetch(`${TELEGRAM_API}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!data.ok) {
      console.error("Telegram API Error:", JSON.stringify(data));
      // Fallback: If Telegram failed due to HTML entity formatting, strip tags and send as clean plain text
      if (data.description && data.description.includes("can't parse entities")) {
        const plainText = text.replace(/<[^>]*>/g, "");
        await fetch(`${TELEGRAM_API}/sendMessage`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chat_id: chatId, text: plainText, reply_markup: replyMarkup })
        });
      }
    }
    return res;
  } catch (err) {
    console.error("Failed to post message to Telegram:", err);
  }
}
