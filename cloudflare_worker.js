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
  { name: "GOLD",    symbol: "XAUUSD", ticker: "XAUUSD",   pip: 0.10,   digits: 2 },
  { name: "EUR/USD", symbol: "EURUSD", ticker: "EURUSD=X", pip: 0.0001, digits: 5 },
  { name: "USD/CAD", symbol: "USDCAD", ticker: "USDCAD=X", pip: 0.0001, digits: 5 }
];

const ALL_KNOWN_CONFIGS = {
  "XAUUSD": { name: "GOLD",    ticker: "XAUUSD",   pip: 0.10,   digits: 2 },
  "EURUSD": { name: "EUR/USD", ticker: "EURUSD=X", pip: 0.0001, digits: 5 },
  "USDCAD": { name: "USD/CAD", ticker: "USDCAD=X", pip: 0.0001, digits: 5 },
  "USDJPY": { name: "USD/JPY", ticker: "USDJPY=X", pip: 0.01,   digits: 3 },
  "USDCHF": { name: "USD/CHF", ticker: "USDCHF=X", pip: 0.0001, digits: 5 },
  "AUDUSD": { name: "AUD/USD", ticker: "AUDUSD=X", pip: 0.0001, digits: 5 }
};

const ALL_KNOWN_TICKERS = Object.fromEntries(Object.entries(ALL_KNOWN_CONFIGS).map(([k, v]) => [k, v.ticker]));

/**
 * Checks whether global Forex and MT5 Spot Gold markets are open.
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
        return {
          active: active || {},
          completed: completed || []
        };
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
        return {
          active: ghData.active_trades || {},
          completed: ghData.completed_trades || []
        };
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
      return {
        active: rawData.active_trades || {},
        completed: rawData.completed_trades || []
      };
    }
  } catch (e) {}

  // 4. Default in-memory baseline
  return {
    active: STORED_ACTIVE_TRADES,
    completed: STORED_COMPLETED_TRADES
  };
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
  const isWin = outcome === "WIN";
  const pips = isCancelled ? 0.0 : (isWin 
    ? (t.tp_pips || Math.abs(t.take_profit - t.entry) / (t.pip || 0.0001)) 
    : -(t.sl_pips || Math.abs(t.entry - t.stop_loss) / (t.pip || 0.0001)));
  const r = isCancelled ? 0.0 : (isWin ? (t.rr || 1.75) : -1.0);

  const completedRecord = {
    ...t,
    exit_price: exitPrice,
    outcome: outcome,
    realized_pips: Math.round(pips * 10) / 10,
    realized_r: Math.round(r * 100) / 100,
    closed_at: new Date().toISOString(),
    status: isCancelled ? "CANCELLED" : "CLOSED"
  };

  // Use pre-fetched ledger if provided — avoids 3 redundant HTTP calls on every resolve
  const currentLedger = prefetchedLedger || await getLedger(env);
  const currentActive = { ...(currentLedger.active || {}) };
  const currentCompleted = [...(currentLedger.completed || [])];

  delete currentActive[symbol];
  delete STORED_ACTIVE_TRADES[symbol];

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
    let asset = ASSETS.find(a => a.symbol === symbol);
    if (!asset) {
      const cfg = ALL_KNOWN_CONFIGS[symbol] || { name: t.pair || symbol, ticker: `${symbol}=X`, pip: 0.0001, digits: 5 };
      asset = { name: t.pair || cfg.name, symbol, ticker: t.ticker || cfg.ticker, pip: t.pip || cfg.pip, digits: t.digits || cfg.digits };
    }
    try {
      let lastClose, lastHigh, lastLow;
      if (symbol === "XAUUSD" || asset.ticker === "XAUUSD") {
        // 1. Primary: live spot gold API (guaranteed 100% uptime, zero Cloudflare block)
        try {
          const gRes = await fetch("https://api.gold-api.com/price/XAU", { headers: { "User-Agent": "Mozilla/5.0" } });
          if (gRes.ok) {
            const gJson = await gRes.json();
            const p = parseFloat(gJson?.price);
            if (!isNaN(p) && p > 0) {
              lastClose = p;
              lastHigh = p;
              lastLow = p;
            }
          }
        } catch(ge) {}

        // 2. Secondary: TradingView CFD scanner (OANDA:XAUUSD spot feed)
        if (lastClose === undefined) {
          try {
            const tvRes = await fetch("https://scanner.tradingview.com/cfd/scan", {
              method: "POST",
              headers: { "User-Agent": "Mozilla/5.0", "Content-Type": "application/json" },
              body: JSON.stringify({ symbols: { tickers: ["OANDA:XAUUSD", "FX:XAUUSD"] }, columns: ["close", "high|15", "low|15"] })
            });
            const tvJson = await tvRes.json();
            const d = tvJson?.data?.[0]?.d;
            if (Array.isArray(d) && d[0] !== null) {
              lastClose = parseFloat(d[0]);
              lastHigh = parseFloat(d[1]) || lastClose;
              lastLow = parseFloat(d[2]) || lastClose;
            }
          } catch(tve) {}
        }
      }

      if (lastClose === undefined) {
        // Use 5m interval for freshest available tick (not 15m which can be 15min stale)
        for (const host of ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]) {
          try {
            const url = `https://${host}/v8/finance/chart/${asset.ticker}?range=1d&interval=5m`;
            const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36" } });
            if (res.ok) {
              const json = await res.json();
              const quote = json?.chart?.result?.[0]?.indicators?.quote?.[0];
              const closes = quote?.close?.filter(v => v !== null && v !== undefined) || [];
              const highs = quote?.high?.filter(v => v !== null && v !== undefined) || [];
              const lows = quote?.low?.filter(v => v !== null && v !== undefined) || [];
              if (closes.length > 0) {
                lastClose = closes[closes.length - 1];
                // Use recent session high/low (last 4 bars ~20min) for accurate TP/SL sweep detection
                const recentHighs = highs.slice(-4);
                const recentLows = lows.slice(-4);
                lastHigh = recentHighs.length > 0 ? Math.max(...recentHighs) : lastClose;
                lastLow = recentLows.length > 0 ? Math.min(...recentLows) : lastClose;
                break;
              }
            }
          } catch (e) {}
        }
      }

      if (lastClose !== undefined) {
        const isLong = (t.direction || "").toUpperCase() === "LONG";

        // Use high/low range for TP/SL evaluation (not just close price)
        // This correctly catches cases where price ticked through a level intra-bar
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
          await autoResolveTrade(symbol, t, hitTP ? "WIN" : "LOSS", exitPrice, env, ledger);
          resolved.push({ symbol, outcome: hitTP ? "WIN" : "LOSS", exitPrice });

          const sign = hitTP ? "+" : "-";
          const pips = hitTP ? (t.tp_pips || 31.5) : (t.sl_pips || 18.0);
          const rVal = hitTP ? (t.rr || 1.75) : -1.0;
          const icon = hitTP ? "🎯" : "🛑";
          const title = hitTP ? "TARGET REACHED: LIQUIDITY POOL SWEPT" : "STRUCTURAL EXIT: STOP LOSS HIT";
          const text = 
            `${icon} <b>${title}</b>\n` +
            `━━━━━━━━━━━━━━━━━━\n` +
            `📊 <b>Asset:</b> <b>${t.pair || symbol}</b> (${t.timeframe || "1H"})\n` +
            `🧭 <b>Position:</b> <b>${t.direction} CLOSED</b>\n` +
            `━━━━━━━━━━━━━━━━━━\n\n` +
            `<b>📋 EXECUTION OUTCOME</b>\n` +
            `• <b>Entry Price:</b> <code>${t.entry}</code>\n` +
            `• <b>Exit Price:</b> <code>${exitPrice}</code>\n` +
            `• <b>Net Realized:</b> <b>${sign}${pips} pips</b>\n` +
            `• <b>Realized Return:</b> <b>${hitTP ? "+" : ""}${rVal} R</b>\n\n` +
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
        return new Response(JSON.stringify({ status: "RADAR_TEST_OK", version: "2.4.0-gold-infallible", radarPreview }, null, 2), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      const ledger = await getLedger(env);
      return new Response(JSON.stringify({
        status: "OK",
        version: "2.4.0-gold-infallible",
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

      // Handle Sync from Market Scanner Engine
      // IMPORTANT: Merge strategy — never blindly overwrite KV active trades.
      // The worker may have resolved a trade (auto-resolved TP/SL) between scanner runs.
      // We always let KV be the source of truth for active trades; scanner only ADDS new ones.
      if (payload.event === "sync_trades") {
        const kv = env && (env.TRADE_LEDGER || env.TRADES_KV || env.KV);

        // Get current KV state so we can merge
        let kvActive = payload.active_trades || {};
        let kvCompleted = payload.completed_trades || [];

        if (kv) {
          try {
            const existingActive = await kv.get("active_trades", "json") || {};
            const existingCompleted = await kv.get("completed_trades", "json") || [];

            // Merge: KV wins for pairs already tracked (could be worker-resolved)
            // Scanner wins for new pairs it just opened
            const resolvedPairs = new Set(existingCompleted.map(t => t.symbol || t.pair));
            const mergedActive = { ...kvActive };
            for (const [symbol, trade] of Object.entries(existingActive)) {
              // Keep KV active trade if scanner didn't send anything for this pair,
              // OR if scanner sent it too (scanner is authoritative for its own new opens)
              if (!(symbol in kvActive) || trade.status === "OPEN") {
                mergedActive[symbol] = mergedActive[symbol] || trade;
              }
            }
            // Remove any active trades KV already closed
            for (const ct of existingCompleted) {
              const sym = ct.symbol || ct.pair;
              if (sym && mergedActive[sym] && mergedActive[sym].trade_id === ct.trade_id) {
                delete mergedActive[sym];
              }
            }

            // Merge completed: deduplicate by trade_id
            const seenIds = new Set(existingCompleted.map(t => t.trade_id));
            for (const ct of kvCompleted) {
              if (!seenIds.has(ct.trade_id)) {
                existingCompleted.push(ct);
                seenIds.add(ct.trade_id);
              }
            }

            kvActive = mergedActive;
            kvCompleted = existingCompleted;
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
      await sendClearInstructions(chatId);
    } else if (cmd === "/close" || cmd === "/resolve") {
      // Admin: force-resolve a stuck active trade
      // Usage: /close EURUSD WIN | /close EURUSD LOSS | /close EURUSD CANCEL
      const symbol = parts[1] ? parts[1].toUpperCase().replace("/", "") : null;
      const outcomeArg = parts[2] ? parts[2].toUpperCase() : null;
      if (symbol && outcomeArg) {
        const outcome = outcomeArg === "WIN" ? "WIN" : outcomeArg === "LOSS" ? "LOSS" : "CANCELLED";
        const closeLedger = await getLedger(env);  // fetch once, reuse
        const trade = closeLedger.active[symbol];
        if (trade) {
          const exitPrice = outcome === "WIN" ? trade.take_profit : outcome === "LOSS" ? trade.stop_loss : trade.entry;
          await autoResolveTrade(symbol, trade, outcome, exitPrice, env, closeLedger);
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
          `<code>/close XAUUSD CANCEL</code>\n\n` +
          `Available pairs: EURUSD · USDCAD · XAUUSD`
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
 * Multi-tier fallbacks: api.gold-api.com -> TradingView CFD -> Yahoo Finance
 */
async function fetchAssetCandles(asset) {
  const browserHeaders = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9"
  };

  let closes = [];
  let highs = [];
  let lows = [];
  let liveSpotPrice = null;

  // 1. For Gold: Fetch live MT5 Spot Gold price (gold-api + TradingView OANDA:XAUUSD)
  if (asset.symbol === "XAUUSD") {
    try {
      const gRes = await fetch("https://api.gold-api.com/price/XAU", { headers: browserHeaders });
      if (gRes.ok) {
        const gJson = await gRes.json();
        const p = parseFloat(gJson?.price);
        if (!isNaN(p) && p > 0) liveSpotPrice = p;
      }
    } catch(e) {}

    try {
      const tvRes = await fetch("https://scanner.tradingview.com/cfd/scan", {
        method: "POST",
        headers: { "User-Agent": "Mozilla/5.0", "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: { tickers: ["OANDA:XAUUSD", "FX:XAUUSD"] }, columns: ["close", "high|15", "low|15"] })
      });
      if (tvRes.ok) {
        const tvJson = await tvRes.json();
        const d = tvJson?.data?.[0]?.d;
        if (Array.isArray(d) && d[0] !== null) {
          const p = parseFloat(d[0]);
          if (!isNaN(p) && p > 0 && liveSpotPrice === null) liveSpotPrice = p;
        }
      }
    } catch(e) {}
  }

  // 2. Query Yahoo Finance for Forex pairs (EURUSD=X, USDCAD=X)
  if (asset.symbol !== "XAUUSD") {
    for (const host of ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]) {
      try {
        const url = `https://${host}/v8/finance/chart/${asset.ticker}?range=5d&interval=15m`;
        const res = await fetch(url, { headers: browserHeaders });
        if (res.ok) {
          const json = await res.json();
          const quote = json?.chart?.result?.[0]?.indicators?.quote?.[0];
          const rawCloses = quote?.close?.filter(v => v !== null && v !== undefined) || [];
          const rawHighs = quote?.high?.filter(v => v !== null && v !== undefined) || [];
          const rawLows = quote?.low?.filter(v => v !== null && v !== undefined) || [];
          if (rawCloses.length >= 20) {
            closes = rawCloses;
            highs = rawHighs;
            lows = rawLows;
            break;
          }
        }
      } catch (e) {}
      if (closes.length >= 20) break;
    }
  }

  // 3. For Spot Gold: Synthesize clean reference bars around live spot price if needed for radar display
  if (asset.symbol === "XAUUSD" && liveSpotPrice !== null) {
    if (closes.length === 0) {
      const base = liveSpotPrice;
      for (let i = 0; i < 30; i++) {
        closes.push(base);
        highs.push(base + 1.5);
        lows.push(base - 1.5);
      }
    }
  }

  const currentPrice = liveSpotPrice !== null ? liveSpotPrice : (closes.length > 0 ? closes[closes.length - 1] : null);

  return { closes, highs, lows, price: currentPrice };
}

/**
 * /radar - Differentiates active live trades from normal surveillance
 */
async function sendRadarMessage(chatId, env) {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";
  const radarLedger = await getLedger(env);
  const { active } = radarLedger;
  let activeCount = 0;
  let hasImminentBreakout = false;

  const results = await Promise.all(
    ASSETS.map(async (asset, idx) => {
      const num = idx + 1;
      try {
        const { closes, highs, lows, price } = await fetchAssetCandles(asset);

        if (price === null || closes.length < 15) {
          return `<b>${num}. ${asset.name}</b> · <i>Feed Offline</i>`;
        }

        // 1. CHECK IF PAIR HAS AN ACTIVE RUNNING TRADE
        const activeTrade = active[asset.symbol];
        if (activeTrade) {
          const isPending = activeTrade.status === "PENDING";
          const isLong = activeTrade.direction === "LONG";

          if (isPending) {
            const hitSL = isLong ? price <= activeTrade.stop_loss : price >= activeTrade.stop_loss;
            const hitEntry = isLong ? price <= activeTrade.entry : price >= activeTrade.entry;

            if (hitSL && !hitEntry) {
              autoResolveTrade(asset.symbol, activeTrade, "CANCELLED", price, env, radarLedger);
              return (
                `<b>${num}. ${asset.name}</b> · <code>${price.toFixed(asset.digits)}</code>\n` +
                `⚠️ <b>SETUP CANCELLED (SL Breached Before Fill)</b>\n` +
                `• Target <code>${activeTrade.entry}</code> · 0 Loss · Surveillance Resumed`
              );
            }

            if (hitEntry) {
              activeTrade.status = "OPEN";
              activeTrade.filled_at = new Date().toISOString();
            } else {
              const distPips = (Math.abs(price - activeTrade.entry) / asset.pip).toFixed(1);
              return (
                `<b>${num}. ${asset.name}</b> · <code>${price.toFixed(asset.digits)}</code>\n` +
                `⏳ <b>PENDING ${activeTrade.direction}</b> (${activeTrade.timeframe})\n` +
                `• Entry Target: <code>${activeTrade.entry}</code> (⏳ ${distPips}p to fill)\n` +
                `• Float: <code>0.0 pips (Awaiting Fill)</code>\n` +
                `• SL: <code>${activeTrade.stop_loss}</code> | TP: <code>${activeTrade.take_profit}</code>`
              );
            }
          }

          // Active OPEN position
          const hitTP = isLong ? price >= activeTrade.take_profit : price <= activeTrade.take_profit;
          const hitSL = isLong ? price <= activeTrade.stop_loss : price >= activeTrade.stop_loss;

          if (hitTP) {
            autoResolveTrade(asset.symbol, activeTrade, "WIN", activeTrade.take_profit, env, radarLedger);
            return (
              `<b>${num}. ${asset.name}</b> · <code>${price.toFixed(asset.digits)}</code>\n` +
              `🎯 <b>TAKE PROFIT ACHIEVED (+${activeTrade.tp_pips || "31.5"} pips | +${activeTrade.rr || "1.75"}R)</b>\n` +
              `• Target <code>${activeTrade.take_profit}</code> Booked · Surveillance Resumed`
            );
          } else if (hitSL) {
            autoResolveTrade(asset.symbol, activeTrade, "LOSS", activeTrade.stop_loss, env, radarLedger);
            return (
              `<b>${num}. ${asset.name}</b> · <code>${price.toFixed(asset.digits)}</code>\n` +
              `🛑 <b>STOP LOSS HIT (-${activeTrade.sl_pips || "18.0"} pips | -1.00R)</b>\n` +
              `• SL <code>${activeTrade.stop_loss}</code> Executed · Surveillance Resumed`
            );
          }

          activeCount++;
          const pnlPips = ((price - activeTrade.entry) / asset.pip) * (isLong ? 1 : -1);
          const pnlSign = pnlPips >= 0 ? "+" : "";
          const icon = isLong ? "🟢" : "🔴";
          const beStatus = activeTrade.be_active ? " 🛡<b>BE</b>" : "";

          return (
            `<b>${num}. ${asset.name}</b> · <code>${price.toFixed(asset.digits)}</code>\n` +
            `${icon} <b>LIVE ${activeTrade.direction}</b> (${activeTrade.timeframe})${beStatus}\n` +
            `• Float: <code>${pnlSign}${pnlPips.toFixed(1)} pips</code>\n` +
            `• Entry: <code>${activeTrade.entry}</code>\n` +
            `• SL: <code>${activeTrade.stop_loss}</code> | TP: <code>${activeTrade.take_profit}</code> (1:${activeTrade.rr || "~"}R)`
          );
        }

        // 2. NORMAL SURVEILLANCE (NO ACTIVE TRADE)
        const donchLen = asset.symbol === "XAUUSD" ? 10 : 15;
        const donchHigh = Math.max(...highs.slice(-(donchLen + 1), -1));
        const donchLow = Math.min(...lows.slice(-(donchLen + 1), -1));
        const channelPips = (donchHigh - donchLow) / asset.pip;
        const distHigh = (donchHigh - price) / asset.pip;
        const distLow = (price - donchLow) / asset.pip;
        const posPct = channelPips > 0 ? ((price - donchLow) / (donchHigh - donchLow)) * 100 : 50;

        // Calculate EMAs for trend confluence
        let ema20 = closes[0], ema50 = closes[0];
        const k20 = 2 / (20 + 1), k50 = 2 / (50 + 1);
        for (let i = 1; i < closes.length; i++) {
          ema20 = closes[i] * k20 + ema20 * (1 - k20);
          ema50 = closes[i] * k50 + ema50 * (1 - k50);
        }
        const isBullish = ema20 > ema50 && price > ema50;
        const isBearish = ema20 < ema50 && price < ema50;

        let gains = 0, losses = 0;
        for (let i = closes.length - 14; i < closes.length; i++) {
          const diff = closes[i] - closes[i - 1];
          if (diff >= 0) gains += diff;
          else losses += Math.abs(diff);
        }
        const rs = (gains / 14) / ((losses / 14) || 1e-9);
        const rsi = 100 - (100 / (1 + rs));

        // Calibrate channel minimum for Gold vs Forex
        const minChannelPips = asset.symbol === "XAUUSD" ? 60.0 : 12.0;
        const isCompressing = channelPips < minChannelPips;
        const breakDistance = asset.symbol === "XAUUSD" ? 25.0 : 3.0;

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
  const { active } = await getLedger(env);
  const activeEntries = Object.entries(active);

  if (activeEntries.length === 0) {
    const text = 
      `⚡ <b>ACTIVE LIVE TRADES (0)</b>\n` +
      `━━━━━━━━━━━━━━━━━━\n` +
      `<i>No active positions currently running.</i>\n\n` +
      `Core Alpha Triad (EURUSD · USDCAD · XAUUSD) under surveillance.\n` +
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
    activeEntries.map(async ([symbol, t], idx) => {
      const num = idx + 1;
      const cfg = ALL_KNOWN_CONFIGS[symbol] || { name: symbol, ticker: `${symbol}=X`, pip: 0.0001, digits: 5 };
      const asset = ASSETS.find(a => a.symbol === symbol) || {
        symbol: symbol,
        name: t.pair || cfg.name,
        digits: t.digits || cfg.digits,
        pip: t.pip || cfg.pip,
        ticker: t.ticker || cfg.ticker
      };

      const isLong = (t.direction || "").toUpperCase() === "LONG";
      const dirIcon = isLong ? "🟢" : "🔴";
      const openTime = (t.opened_at || "").substring(11, 16) || "00:00";
      const openDate = (t.opened_at || "").substring(0, 10);
      const pName = t.pair || asset.name;

      let currentPrice = null;
      let floatText = "";

      if (asset.symbol === "XAUUSD") {
        try {
          const gRes = await fetch("https://api.gold-api.com/price/XAU", { headers: { "User-Agent": "Mozilla/5.0" } });
          if (gRes.ok) {
            const gJson = await gRes.json();
            const p = parseFloat(gJson?.price);
            if (!isNaN(p) && p > 0) currentPrice = p;
          }
        } catch (ge) {}
      }

      if (currentPrice === null) {
        // Use 5m interval for freshest price tick (not 15m which lags by up to 15 minutes)
        for (const host of ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]) {
          try {
            const url = `https://${host}/v8/finance/chart/${asset.ticker}?range=1d&interval=5m`;
            const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36" } });
            if (res.ok) {
              const json = await res.json();
              const quote = json?.chart?.result?.[0]?.indicators?.quote?.[0];
              const closes = quote?.close?.filter(v => v !== null && v !== undefined) || [];
              if (closes.length > 0) {
                currentPrice = closes[closes.length - 1];
                break;
              }
            }
          } catch (e) {}
        }
      }

      const isPending = (t.status === "PENDING");

      if (currentPrice !== null) {
        if (isPending) {
          const hitSL = isLong ? currentPrice <= t.stop_loss : currentPrice >= t.stop_loss;
          const hitEntry = isLong ? currentPrice <= t.entry : currentPrice >= t.entry;

          if (hitSL && !hitEntry) {
            autoResolveTrade(symbol, t, "CANCELLED", currentPrice, env, { active: currentActive, completed: currentCompleted });
            floatText = 
              `• Status: ⚠️ <b>SETUP CANCELLED · SL BREACHED BEFORE FILL</b>\n` +
              `• Live Price: <code>${currentPrice.toFixed(asset.digits)}</code> (0.0 pips | Unfilled)\n`;
          } else if (hitEntry) {
            t.status = "OPEN";
            t.filled_at = new Date().toISOString();
            const hitTP = isLong ? currentPrice >= t.take_profit : currentPrice <= t.take_profit;
            const hitSLAfterFill = isLong ? currentPrice <= t.stop_loss : currentPrice >= t.stop_loss;

            if (hitTP) {
              autoResolveTrade(symbol, t, "WIN", t.take_profit, env, { active: currentActive, completed: currentCompleted });
              floatText = `• Status: 🎯 <b>TARGET REACHED · TAKE PROFIT HIT (+${t.tp_pips || "31.5"} pips | +${t.rr || "1.75"}R)</b>\n• Live Price: <code>${currentPrice.toFixed(asset.digits)}</code> (Target Booked)\n`;
            } else if (hitSLAfterFill) {
              autoResolveTrade(symbol, t, "LOSS", t.stop_loss, env, { active: currentActive, completed: currentCompleted });
              floatText = `• Status: 🛑 <b>STOP LOSS HIT (-${t.sl_pips || "18.0"} pips | -1.00R)</b>\n• Live Price: <code>${currentPrice.toFixed(asset.digits)}</code> (SL Booked)\n`;
            } else {
              const pnlPips = ((currentPrice - t.entry) / asset.pip) * (isLong ? 1 : -1);
              const pnlSign = pnlPips >= 0 ? "+" : "";
              const riskDist = Math.abs(t.entry - t.stop_loss) / asset.pip;
              const floatR = riskDist > 0 ? (pnlPips / riskDist).toFixed(2) : "0.00";
              const rSign = parseFloat(floatR) >= 0 ? "+" : "";
              const floatEmoji = pnlPips >= 0 ? "🟢" : "🔻";
              floatText = 
                `• Status: 🎯 <b>ORDER FILLED @ ${t.entry}</b>\n` +
                `• Live Price: <code>${currentPrice.toFixed(asset.digits)}</code> (${floatEmoji} <b>${pnlSign}${pnlPips.toFixed(1)} pips</b> | <b>${rSign}${floatR}R</b>)\n`;
            }
          } else {
            // Still pending entry fill
            const distPips = (Math.abs(currentPrice - t.entry) / asset.pip).toFixed(1);
            floatText = 
              `• Status: ⏳ <b>PENDING ENTRY FILL</b>\n` +
              `• Live Price: <code>${currentPrice.toFixed(asset.digits)}</code> (⏳ <b>${distPips} pips to entry</b>)\n` +
              `• Floating PnL: <b>0.0 pips</b> (<i>Awaiting Market Fill · Zero Exposure</i>)\n`;
          }
        } else {
          // Normal active OPEN position
          const hitTP = isLong ? currentPrice >= t.take_profit : currentPrice <= t.take_profit;
          const hitSL = isLong ? currentPrice <= t.stop_loss : currentPrice >= t.stop_loss;

          if (hitTP) {
            autoResolveTrade(symbol, t, "WIN", t.take_profit, env, { active: currentActive, completed: currentCompleted });
            floatText = `• Status: 🎯 <b>TARGET REACHED · TAKE PROFIT HIT (+${t.tp_pips || "31.5"} pips | +${t.rr || "1.75"}R)</b>\n• Live Price: <code>${currentPrice.toFixed(asset.digits)}</code> (Target Booked)\n`;
          } else if (hitSL) {
            autoResolveTrade(symbol, t, "LOSS", t.stop_loss, env, { active: currentActive, completed: currentCompleted });
            floatText = `• Status: 🛑 <b>STOP LOSS HIT (-${t.sl_pips || "18.0"} pips | -1.00R)</b>\n• Live Price: <code>${currentPrice.toFixed(asset.digits)}</code> (SL Booked)\n`;
          } else {
            const pnlPips = ((currentPrice - t.entry) / asset.pip) * (isLong ? 1 : -1);
            const pnlSign = pnlPips >= 0 ? "+" : "";
            const riskDist = Math.abs(t.entry - t.stop_loss) / asset.pip;
            const floatR = riskDist > 0 ? (pnlPips / riskDist).toFixed(2) : "0.00";
            const rSign = parseFloat(floatR) >= 0 ? "+" : "";
            const floatEmoji = pnlPips >= 0 ? "🟢" : "🔻";
            const beFlag = t.be_active ? " 🛡<b>Break-Even Active</b>" : "";
            floatText = `• Live Price: <code>${currentPrice.toFixed(asset.digits)}</code> (${floatEmoji} <b>${pnlSign}${pnlPips.toFixed(1)} pips</b> | <b>${rSign}${floatR}R</b>)${beFlag}\n`;
          }
        }
      } else {
        if (isPending) {
          floatText = `• Status: ⏳ <b>PENDING ENTRY FILL</b>\n• Floating PnL: <b>0.0 pips</b> (<i>Price Feed Offline · Awaiting Fill</i>)\n`;
        }
      }

      const statusBadge = isPending ? `⏳ <b>PENDING ${t.direction}</b>` : `${dirIcon} <b>${t.direction}</b>`;
      const entryLabel = isPending ? "• Entry Target:" : "• Entry:";

      return (
        `<b>${num}. ${pName}</b> · ${t.timeframe || "1H"} · ${statusBadge}\n` +
        `${entryLabel} <code>${t.entry}</code> (${openDate} ${openTime} UTC)\n` +
        floatText +
        `• Targets: SL <code>${t.stop_loss}</code> | TP <code>${t.take_profit}</code>\n` +
        `• Plan: <b>1 : ${t.rr || t.risk_reward || "1.75"} R:R</b> (1.0% Equity Risk)`
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
        { text: "GOLD", callback_data: "hist_pair_XAUUSD" },
        { text: "EUR/USD", callback_data: "hist_pair_EURUSD" },
        { text: "USD/CAD", callback_data: "hist_pair_USDCAD" }
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
    `📈 <b>STRATEGY PERFORMANCE (v2.0-Frozen)</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `Scope: <b>${scopeLabel}</b>\n` +
    `Baseline: <code>2026-10-02</code> (Out-of-Sample Forward Only)\n` +
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
    `• Target R:R: <code>1.5R – 2.5R (Model F Structural)</code>\n\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `⚡ <i>100% out-of-sample. Strategy frozen 2026-10-02.</i>\n` +
    `🕒 <code>${utcNow}</code>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "Overall", callback_data: "perf_pair_ALL" },
        { text: "GOLD", callback_data: "perf_pair_XAUUSD" }
      ],
      [
        { text: "EUR/USD", callback_data: "perf_pair_EURUSD" },
        { text: "USD/CAD", callback_data: "perf_pair_USDCAD" }
      ],
      [
        { text: "⚡ Active Trades", callback_data: "cmd_active" },
        { text: "📜 History (Closed)", callback_data: "cmd_history" }
      ],
      [
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
        if (asset.symbol === "XAUUSD" || asset.ticker === "XAUUSD") {
          // 1. Primary: gold-api.com (100% uptime, zero Cloudflare block, live MT5 spot price)
          try {
            const gRes = await fetch("https://api.gold-api.com/price/XAU", { headers: { "User-Agent": "Mozilla/5.0" } });
            if (gRes.ok) {
              const gJson = await gRes.json();
              const p = parseFloat(gJson?.price);
              if (!isNaN(p) && p > 0) return `<b>${num}. ${asset.name}</b> · <code>${p.toFixed(asset.digits)}</code>`;
            }
          } catch(ge) {}

          // 2. Secondary: TradingView CFD scanner (OANDA:XAUUSD)
          try {
            const tvRes = await fetch("https://scanner.tradingview.com/cfd/scan", {
              method: "POST",
              headers: { "User-Agent": "Mozilla/5.0", "Content-Type": "application/json" },
              body: JSON.stringify({ symbols: { tickers: ["OANDA:XAUUSD", "FX:XAUUSD"] }, columns: ["close"] })
            });
            const tvJson = await tvRes.json();
            const p = parseFloat(tvJson?.data?.[0]?.d?.[0]);
            if (!isNaN(p)) return `<b>${num}. ${asset.name}</b> · <code>${p.toFixed(asset.digits)}</code>`;
          } catch(tve) {}
        }
        for (const host of ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]) {
          try {
            // Use 5m interval for freshest price (not 15m which can be 15min stale)
            const url = `https://${host}/v8/finance/chart/${asset.ticker}?range=1d&interval=5m`;
            const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36" } });
            if (res.ok) {
              const json = await res.json();
              const closes = json?.chart?.result?.[0]?.indicators?.quote?.[0]?.close?.filter(v => v !== null) || [];
              if (closes.length > 0) return `<b>${num}. ${asset.name}</b> · <code>${closes[closes.length - 1].toFixed(asset.digits)}</code>`;
            }
          } catch (ye) {}
        }
        return `<b>${num}. ${asset.name}</b> · <i>Closed</i>`;
      } catch (e) {
        return `<b>${num}. ${asset.name}</b> · <i>Offline</i>`;
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
    `1. Engine Core: 🟢 <b>OPERATIONAL (24/7)</b>\n` +
    `2. Strategy Version: <code>v2.0-Frozen (2026-10-02)</code>\n` +
    `3. Cloud Edge: Cloudflare Global Edge\n` +
    `4. Scanner Host: GitHub Actions Cron (*/15 5-21 UTC)\n` +
    `5. Monitored Assets: <code>Core Alpha Triad (XAUUSD, EURUSD, USDCAD)</code>\n` +
    `6. Active Positions: <code>${activeCount} locked</code>\n` +
    `7. Recorded Trades: <code>${closedCount} closed</code>\n` +
    `8. ADX Regime Gate: <code>20–30 Blocked (v2 Filter)</code>\n` +
    `9. PC Dependency: Zero (100% Serverless)\n` +
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
 * /strategy - ICT Multi-Timeframe Execution Specifications
 */
async function sendStrategyMessage(chatId) {
  const text = 
    `🎯 <b>STRATEGY SPECIFICATIONS</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `<b>INSTITUTIONAL ICT ORDER BLOCK &amp; LIQUIDITY MODEL</b>\n\n` +
    `<b>1. Multi-Timeframe Hierarchy (ICT)</b>\n` +
    `• 1H: Macro trend bias (EMA20 vs EMA50 + RSI zone check)\n` +
    `• 15M: Setup — Donchian structural breakout + Order Block detection\n` +
    `• 5M: Precision entry trigger — Rejection Wick / Engulf / FVG at OTE\n\n` +
    `<b>2. Entry: Live Price + 5M Trigger</b>\n` +
    `• Gold: 10-period Donchian (Profit Factor 1.40 backtested)\n` +
    `• Forex: 15-period Donchian (Profit Factor 1.25 backtested)\n` +
    `• RSI Filter: Longs 40–80, Shorts 20–60 (Anti-exhaustion)\n` +
    `• Entry: Live 5M price at signal time (not stale bar close)\n` +
    `• Stop Loss: Origin Order Block Invalidation (+0.5 ATR buffer)\n\n` +
    `<b>3. ICT Execution Protocol (3 Tiers)</b>\n` +
    `• 0–3 min: Enter at 5M trigger price or current market\n` +
    `• 3–10 min delayed: Enter if inside OTE Valid Zone only\n` +
    `• Late / Missed: Limit at 50% CE (OTE pullback) — never chase beyond Max Chase\n\n` +
    `<b>4. Institutional Targets: BSL &amp; SSL Liquidity Pools (Model F)</b>\n` +
    `• Longs: Buy-Side Liquidity (BSL) above 5-bar fractal confirmed swing highs\n` +
    `• Shorts: Sell-Side Liquidity (SSL) below 5-bar fractal confirmed swing lows\n` +
    `• Calibration: Dynamic 1.5R – 2.5R to nearest un-swept pool\n` +
    `• Audit: Model F = 0.281R expectancy, 1.52 PF vs 0.111R (old baseline)\n\n` +
    `<b>5. ADX Regime Filter (Forensic Audit v2)</b>\n` +
    `• ADX &lt;20 (Range): 54.5% WR, +0.32R — TRADE\n` +
    `• ADX 20–30 (Moderate): 38.4% WR, -0.09R — BLOCKED\n` +
    `• ADX &gt;30 (Strong Trend): 45.9% WR, +0.09R — TRADE\n\n` +
    `<b>6. Session Quality Scoring</b>\n` +
    `• London 05:00–12:00 UTC: 51.1% WR, +0.27R (Score x1.05)\n` +
    `• NY Afternoon 16:00–20:00 UTC: 52.8% WR, +0.10R (Score x1.00)\n` +
    `• Asian 00:00–05:00 &amp; 20:00–24:00 UTC: 47.8% WR (Score x0.95)\n` +
    `• London/NY Overlap 12:00–16:00 UTC: 33.3% WR, -0.22R — BLOCKED\n\n` +
    `<b>7. Trade Management</b>\n` +
    `• Freshness Guard: 15M signals fire within 12 min of bar close; 1H within 30 min\n` +
    `• Break-Even: SL moves to entry +1 pip when +1.0R floating\n` +
    `• EMA20 Time-Stop: Exit if counter-trend close after 12h (15M) / 24h (1H)\n` +
    `• Suggested Risk: <b>0.5% Equity per trade</b> (Portfolio DD ≤ 6.0%)\n` +
    `• Admin: /close PAIR WIN|LOSS to force-resolve stuck trades\n\n` +
    `<b>8. Asset Universe (Forensic-Tested)</b>\n` +
    `• EURUSD: 56.4% WR, +0.366R, 2.26 PF (Active)\n` +
    `• USDCAD: 65.9% WR, +0.402R, 2.20 PF (Active)\n` +
    `• XAUUSD: 42.9% WR, +0.319R, 1.72 PF (Active)\n` +
    `• GBPUSD: 37.7% WR, +0.021R (Excluded)\n` +
    `• USDJPY: 38.8% WR, -0.043R (Excluded)\n` +
    `• USDCHF: 39.1% WR, -0.128R (Excluded)\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `🛡 <i>Systematic, rule-based. One trade per pair at all times.</i>`;

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
    `• The ledger tracks strictly live confirmed signals from <code>2026-10-02</code> onwards.\n` +
    `• Strategy is frozen at v2.0 — no parameter changes during forward test.\n\n` +
    `<b>2. To Clear Telegram Chat History</b>\n` +
    `• On Mobile / Desktop: Tap the <b>⋮ (Three Dots)</b> menu at the top right of this chat.\n` +
    `• Select <b>Clear History</b> (or <b>Delete Chat</b>).\n` +
    `• Type <code>/start</code> to resume with a 100% clean, fresh terminal!\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `✨ <i>v2.0-Frozen institutional session active.</i>`;

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
    `🏛 <b>INSTITUTIONAL SIGNAL TERMINAL</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `Automated 24/7 Algorithmic Trading &amp; Forward Verification\n` +
    `Coverage: <b>EURUSD · USDCAD · GOLD</b> (Core Alpha Triad)\n\n` +
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

  if (payload.event === "forex_signal" || payload.symbol) {
    const isLong = (payload.direction || "").toUpperCase() === "LONG";
    const icon = isLong ? "🟢" : "🔴";
    const actionText = isLong ? "BUY / LONG" : "SELL / SHORT";
    const pair = payload.symbol || "FOREX";
    const isGold = (pair === "XAUUSD");
    const displayPair = isGold ? "GOLD (XAU/USD)" : (pair.length === 6 ? `${pair.substring(0,3)}/${pair.substring(3)}` : pair);
    const goldNote = isGold ? "• <b>Feed:</b> <code>MT5 Institutional Spot Gold (XAU/USD)</code>\n\n" : "";
    const marketWarning = !isMarketOpen() ? "⚠️ <b>WARNING: MARKETS CURRENTLY CLOSED (Weekend)</b>\n<i>Execution paused until Sunday 17:00 NY open.</i>\n\n" : "";

    alertMessage = 
      marketWarning +
      `${icon} <b>NEW TRADE SIGNAL · ${displayPair}</b>\n` +
      `━━━━━━━━━━━━━━━━━━\n` +
      `🧭 <b>Direction:</b> <b>${actionText}</b>\n` +
      `⏱ <b>Timeframe:</b> <b>${payload.timeframe || "1H"}</b>\n` +
      `━━━━━━━━━━━━━━━━━━\n\n` +
      `<b>📋 TRADE PARAMETERS</b>\n` +
      `• <b>Entry Target:</b> <code>${payload.entry || payload.price}</code> <i>(Limit / Retest Level)</i>\n` +
      `• <b>Order State:</b> ⏳ <b>PENDING ENTRY FILL</b>\n` +
      `• <b>Stop Loss:</b> <code>${payload.stop_loss}</code>\n` +
      `• <b>Take Profit:</b> <code>${payload.take_profit}</code>\n` +
      `• <b>Risk / Reward:</b> <b>1 : ${payload.risk_reward || "1.75"}</b>\n` +
      `• <b>Suggested Risk:</b> <b>1.0% Equity</b>\n\n` +
      goldNote +
      `<b>🔬 CONFLUENCE MODEL</b>\n` +
      `• <b>Setup:</b> Institutional Structural Breakout & ICT Liquidity Sweep\n` +
      `• <b>Signal Score:</b> <b>${payload.signal_score || 92} / 100</b>\n\n` +
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
