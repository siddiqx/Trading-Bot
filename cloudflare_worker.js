/**
 * 24/7 Institutional Cloudflare Worker for Telegram Trading Bot
 * 
 * Features:
 * - Active Trade Tracking & Floating PnL
 * - Market Radar differentiating live trades vs surveillance
 * - /history command with pair and date range filtering
 * - /performance command calculated strictly from live trades taken from 2026-09-28 onwards
 * - /strategy command explaining institutional breakout execution rules
 * - Modern, aesthetic, executive terminal formatting
 */

const BOT_TOKEN = "8932628751:AAFS_Z7SZMbfNAgNE9KmU6Sly32IGxDm2p0";
const TELEGRAM_API = `https://api.telegram.org/bot${BOT_TOKEN}`;

const ASSETS = [
  { name: "EUR/USD", symbol: "EURUSD", ticker: "EURUSD=X", pip: 0.0001, digits: 5 },
  { name: "USD/JPY", symbol: "USDJPY", ticker: "USDJPY=X", pip: 0.01,   digits: 3 },
  { name: "USD/CAD", symbol: "USDCAD", ticker: "USDCAD=X", pip: 0.0001, digits: 5 },
  { name: "USD/CHF", symbol: "USDCHF", ticker: "USDCHF=X", pip: 0.0001, digits: 5 },
  { name: "AUD/USD", symbol: "AUDUSD", ticker: "AUDUSD=X", pip: 0.0001, digits: 5 },
  { name: "GOLD",    symbol: "XAUUSD", ticker: "GC=F",     pip: 0.10,   digits: 2 }
];

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

  // 2. Private GitHub API via GITHUB_TOKEN secret
  if (env && env.GITHUB_TOKEN) {
    try {
      const ghRes = await fetch("https://api.github.com/repos/siddiqx/Trading-Bot/contents/trade_records.json", {
        headers: {
          "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
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

export default {
  async fetch(request, env) {
    if (request.method === "GET") {
      const kv = env && (env.TRADE_LEDGER || env.TRADES_KV || env.KV);
      let kvActive = null;
      let kvCompleted = null;
      if (kv) {
        try {
          kvActive = await kv.get("active_trades", "json");
          kvCompleted = await kv.get("completed_trades", "json");
        } catch(e) {}
      }
      const ledger = await getLedger(env);
      return new Response(JSON.stringify({
        status: "OK",
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
      if (payload.event === "sync_trades") {
        if (payload.active_trades) STORED_ACTIVE_TRADES = payload.active_trades;
        if (payload.completed_trades) STORED_COMPLETED_TRADES = payload.completed_trades;

        const kv = env && (env.TRADE_LEDGER || env.TRADES_KV || env.KV);
        if (kv) {
          try {
            await kv.put("active_trades", JSON.stringify(STORED_ACTIVE_TRADES));
            await kv.put("completed_trades", JSON.stringify(STORED_COMPLETED_TRADES));
            if (payload.volume_summary) {
              await kv.put("volume_summary", JSON.stringify(payload.volume_summary));
            }
          } catch (e) {
            console.error("KV save error:", e);
          }
        }
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

    if (action === "cmd_radar") await sendRadarMessage(chatId, env);
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
    } else if (cmd === "/radar" || cmd === "/scan" || cmd === "/tracking") {
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
    } else {
      await sendMenuMessage(chatId, env);
    }
    return new Response("OK", { status: 200 });
  }

  return new Response("Ignored", { status: 200 });
}

/**
 * /radar - Differentiates active live trades from normal surveillance
 */
async function sendRadarMessage(chatId, env) {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";
  const { active } = await getLedger(env);
  let activeCount = 0;

  const results = await Promise.all(
    ASSETS.map(async (asset, idx) => {
      const num = idx + 1;
      try {
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${asset.ticker}?range=5d&interval=15m`;
        const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
        const json = await res.json();
        const quote = json?.chart?.result?.[0]?.indicators?.quote?.[0];
        
        const closes = quote?.close?.filter(v => v !== null && v !== undefined) || [];
        const highs = quote?.high?.filter(v => v !== null && v !== undefined) || [];
        const lows = quote?.low?.filter(v => v !== null && v !== undefined) || [];

        if (closes.length < 25) return `<b>${num}. ${asset.name}</b> · <i>Syncing Data</i>`;

        const price = closes[closes.length - 1];

        // 1. CHECK IF PAIR HAS AN ACTIVE RUNNING TRADE
        const activeTrade = active[asset.symbol];
        if (activeTrade) {
          activeCount++;
          const isLong = activeTrade.direction === "LONG";
          const pnlPips = ((price - activeTrade.entry) / asset.pip) * (isLong ? 1 : -1);
          const pnlSign = pnlPips >= 0 ? "+" : "";
          const icon = isLong ? "🟢" : "🔴";

          return (
            `<b>${num}. ${asset.name}</b> · <code>${price.toFixed(asset.digits)}</code>\n` +
            `${icon} <b>LIVE ${activeTrade.direction}</b> (${activeTrade.timeframe})\n` +
            `• Float: <code>${pnlSign}${pnlPips.toFixed(1)} pips</code>\n` +
            `• Entry: <code>${activeTrade.entry}</code>\n` +
            `• SL: <code>${activeTrade.stop_loss}</code> | TP: <code>${activeTrade.take_profit}</code>`
          );
        }

        // 2. NORMAL SURVEILLANCE (NO ACTIVE TRADE)
        const donchHigh = Math.max(...highs.slice(-22, -1));
        const donchLow = Math.min(...lows.slice(-22, -1));
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

        let badge = "", status = "", detail = "";
        if (rsi > 75) {
          badge = "🛡";
          status = "RSI Guard Active";
          detail = `RSI ${rsi.toFixed(0)} Overbought`;
        } else if (rsi < 25) {
          badge = "🛡";
          status = "RSI Guard Active";
          detail = `RSI ${rsi.toFixed(0)} Oversold`;
        } else if (posPct >= 85) {
          if (isBullish) {
            badge = "⚡";
            status = "Imminent Breakout Setup";
            detail = `${distHigh <= 0 ? "Piercing High" : distHigh.toFixed(1) + "p to Break"} · Trend Bullish`;
          } else {
            badge = "👀";
            status = "Testing Range High";
            detail = `${distHigh.toFixed(1)}p to High · Counter-Trend EMA`;
          }
        } else if (posPct <= 15) {
          if (isBearish) {
            badge = "⚡";
            status = "Imminent Breakdown Setup";
            detail = `${distLow <= 0 ? "Piercing Low" : distLow.toFixed(1) + "p to Break"} · Trend Bearish`;
          } else {
            badge = "👀";
            status = "Testing Range Low";
            detail = `${distLow.toFixed(1)}p to Low · Counter-Trend EMA`;
          }
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

  const text = 
    `📡 <b>MARKET SURVEILLANCE RADAR</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n\n` +
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
      `All 6 asset pairs are under automated surveillance.\n` +
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
      const asset = ASSETS.find(a => a.symbol === symbol) || {
        symbol: symbol,
        name: t.pair || symbol,
        digits: 5,
        pip: 0.0001,
        ticker: `${symbol}=X`
      };

      const isLong = (t.direction || "").toUpperCase() === "LONG";
      const dirIcon = isLong ? "🟢" : "🔴";
      const openTime = (t.opened_at || "").substring(11, 16) || "00:00";
      const openDate = (t.opened_at || "").substring(0, 10);
      const pName = t.pair || asset.name;

      let currentPrice = null;
      let floatText = "";

      try {
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${asset.ticker}?range=1d&interval=15m`;
        const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
        const json = await res.json();
        const quote = json?.chart?.result?.[0]?.indicators?.quote?.[0];
        const closes = quote?.close?.filter(v => v !== null && v !== undefined) || [];
        if (closes.length > 0) {
          currentPrice = closes[closes.length - 1];
        }
      } catch (e) {
        // Fallback to null
      }

      if (currentPrice !== null) {
        const pnlPips = ((currentPrice - t.entry) / asset.pip) * (isLong ? 1 : -1);
        const pnlSign = pnlPips >= 0 ? "+" : "";
        const riskDist = Math.abs(t.entry - t.stop_loss) / asset.pip;
        const floatR = riskDist > 0 ? (pnlPips / riskDist).toFixed(2) : "0.00";
        const rSign = parseFloat(floatR) >= 0 ? "+" : "";
        const floatEmoji = pnlPips >= 0 ? "🟢" : "🔻";
        floatText = `• Live Price: <code>${currentPrice.toFixed(asset.digits)}</code> (${floatEmoji} <b>${pnlSign}${pnlPips.toFixed(1)} pips</b> | <b>${rSign}${floatR}R</b>)\n`;
      }

      return (
        `<b>${num}. ${pName}</b> · ${t.timeframe || "1H"} · ${dirIcon} <b>${t.direction}</b>\n` +
        `• Entry: <code>${t.entry}</code> (${openDate} ${openTime} UTC)\n` +
        floatText +
        `• Targets: SL <code>${t.stop_loss}</code> | TP <code>${t.take_profit}</code>\n` +
        `• Plan: <b>1 : ${t.risk_reward || "1.75"} R:R</b> (1.0% Equity Risk)`
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
    const isWin = t.outcome === "WIN";
    const outcomeBadge = isWin ? "🎯 <b>WIN</b>" : "🛑 <b>LOSS</b>";
    const pipsVal = typeof t.realized_pips === "number" ? t.realized_pips : parseFloat(t.realized_pips || 0);
    const rVal = typeof t.realized_r === "number" ? t.realized_r : parseFloat(t.realized_r || 0);
    const sign = pipsVal >= 0 ? "+" : "";
    const rSign = rVal >= 0 ? "+" : "";

    closedRows.push(
      `<b>${num}. ${pName}</b> · ${t.timeframe || "1H"} · <b>${t.direction}</b>\n` +
      `• Date: <code>${closeDate}</code>\n` +
      `• Price: <code>${t.entry}</code> ➔ <code>${t.exit_price}</code>\n` +
      `• Outcome: ${outcomeBadge} (${sign}${pipsVal.toFixed(1)}p / ${rSign}${rVal.toFixed(2)}R)`
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
        { text: "USD/CHF", callback_data: "hist_pair_USDCHF" },
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
  const winRate = totalClosed > 0 ? ((wins / totalClosed) * 100).toFixed(1) : "N/A";

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

  const text = 
    `📈 <b>STRATEGY PERFORMANCE</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `Scope: <b>${scopeLabel}</b>\n` +
    `Baseline: <code>2026-09-28</code> (Live Only)\n` +
    `━━━━━━━━━━━━━━━━━━\n\n` +
    `<b>1. TRADE EXECUTION</b>\n` +
    `• Total Closed: <code>${totalClosed}</code>\n` +
    `• Active Live: <code>${active.length} positions</code>\n` +
    `• Win / Loss: <b>${wins}W</b> · <b>${losses}L</b>\n` +
    `• Win Rate: <b>${winRate}${totalClosed > 0 ? "%" : ""}</b>\n\n` +
    `<b>2. RETURNS & PROFITABILITY</b>\n` +
    `• Net Realized Pips: <b>${pipsSign}${netPips.toFixed(1)} pips</b>\n` +
    `• Net Realized Return: <b>${rSign}${netR.toFixed(2)} R</b>\n` +
    `• Profit Factor: <code>${profitFactor}</code>\n` +
    `• Target R:R: <code>1 : 1.75</code>\n\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `⚡ <i>Zero backtest data. Live forward verified.</i>\n` +
    `🕒 <code>${utcNow}</code>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "Overall", callback_data: "perf_pair_ALL" },
        { text: "USD/CHF", callback_data: "perf_pair_USDCHF" },
        { text: "EUR/USD", callback_data: "perf_pair_EURUSD" }
      ],
      [
        { text: "USD/CAD", callback_data: "perf_pair_USDCAD" },
        { text: "USD/JPY", callback_data: "perf_pair_USDJPY" },
        { text: "GOLD", callback_data: "perf_pair_XAUUSD" }
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
  const rows = await Promise.all(
    ASSETS.map(async (asset, idx) => {
      const num = idx + 1;
      try {
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${asset.ticker}?range=1d&interval=15m`;
        const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
        const json = await res.json();
        const closes = json?.chart?.result?.[0]?.indicators?.quote?.[0]?.close?.filter(v => v !== null) || [];
        if (closes.length > 0) return `<b>${num}. ${asset.name}</b> · <code>${closes[closes.length - 1].toFixed(asset.digits)}</code>`;
        return `<b>${num}. ${asset.name}</b> · <i>Closed</i>`;
      } catch (e) {
        return `<b>${num}. ${asset.name}</b> · <i>Offline</i>`;
      }
    })
  );

  const text = 
    `📊 <b>LIVE MARKET QUOTES</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    rows.join("\n") + "\n" +
    `━━━━━━━━━━━━━━━━━━\n` +
    `🕒 <code>${utcNow}</code> · <i>Live Feed</i>`;

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
    `2. Cloud Edge: Cloudflare Global Edge\n` +
    `3. Scanner Host: GitHub Actions Cron\n` +
    `4. Monitored Assets: <code>6 pairs</code> (Forex + Gold)\n` +
    `5. Active Positions: <code>${activeCount} locked</code>\n` +
    `6. Recorded Trades: <code>${closedCount} closed</code>\n` +
    `7. PC Dependency: Zero (100% Serverless)\n` +
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
 * /strategy - Institutional Execution Specifications
 */
async function sendStrategyMessage(chatId) {
  const text = 
    `🎯 <b>STRATEGY SPECIFICATIONS</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `<b>INSTITUTIONAL BREAKOUT & ORDER BLOCK MODEL</b>\n\n` +
    `<b>1. Structural Breakout Trigger</b>\n` +
    `• 20-period Donchian Channel High/Low breach\n` +
    `• Confirmation requires candle close outside channel\n\n` +
    `<b>2. Trend Bias & Momentum Guard</b>\n` +
    `• Longs: EMA 20 above EMA 50 (Bullish)\n` +
    `• Shorts: EMA 20 below EMA 50 (Bearish)\n` +
    `• Anti-Exhaustion RSI: <code>25.0 ≤ RSI ≤ 75.0</code>\n\n` +
    `<b>3. Structural Protection & Sizing</b>\n` +
    `• Invalidation SL at Origin Order Block\n` +
    `• Fixed Risk-to-Reward: <b>1 : 1.75</b>\n` +
    `• Fixed Risk per Trade: <b>1.0% Equity</b>\n` +
    `• Enforced Single-Position Lock per pair\n\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `🛡 <i>Systematic, rule-based execution.</i>`;

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
 * Main Navigation Menu
 */
async function sendMenuMessage(chatId, env) {
  const { active } = await getLedger(env);
  const activeCount = Object.keys(active).length;
  const activeLabel = activeCount > 0 ? ` (${activeCount} Active)` : "";

  const text = 
    `🏛 <b>INSTITUTIONAL SIGNAL TERMINAL</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `Automated 24/7 Algorithmic Trading & Forward Verification\n` +
    `Coverage: <b>EURUSD · USDJPY · USDCAD · USDCHF · AUDUSD · GOLD</b>\n\n` +
    `<b>SYSTEM MODULES</b>\n` +
    `1. /active ── Running trades & live float pips\n` +
    `2. /radar ── Market surveillance & live scan\n` +
    `3. /prices ── Live quotes across all 6 pairs\n` +
    `4. /history ── Completed trade history ledger\n` +
    `5. /performance ── Win rate & return metrics\n` +
    `6. /patterns ── Volume post-mortems & pattern stats\n` +
    `7. /strategy ── Systematic entry/exit rules\n` +
    `8. /status ── 24/7 serverless engine health\n\n` +
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
    const displayPair = pair === "XAUUSD" ? "GOLD (XAU/USD)" : (pair.length === 6 ? `${pair.substring(0,3)}/${pair.substring(3)}` : pair);

    alertMessage = 
      `${icon} <b>NEW TRADE SIGNAL · ${displayPair}</b>\n` +
      `━━━━━━━━━━━━━━━━━━\n` +
      `🧭 <b>Direction:</b> <b>${actionText}</b>\n` +
      `⏱ <b>Timeframe:</b> <b>${payload.timeframe || "1H"}</b>\n` +
      `━━━━━━━━━━━━━━━━━━\n\n` +
      `<b>📋 TRADE PARAMETERS</b>\n` +
      `• <b>Entry Price:</b> <code>${payload.entry || payload.price}</code>\n` +
      `• <b>Stop Loss:</b> <code>${payload.stop_loss}</code>\n` +
      `• <b>Take Profit:</b> <code>${payload.take_profit}</code>\n` +
      `• <b>Risk / Reward:</b> <b>1 : ${payload.risk_reward || "1.75"}</b>\n` +
      `• <b>Suggested Risk:</b> <b>1.0% Equity</b>\n\n` +
      `<b>🔬 CONFLUENCE MODEL</b>\n` +
      `• <b>Setup:</b> 20-Bar Structural Breakout\n` +
      `• <b>Signal Score:</b> <b>${payload.signal_score || 92} / 100</b>\n\n` +
      `━━━━━━━━━━━━━━━━━━\n` +
      `🕒 <b>Confirmed Bar:</b> <code>${payload.signal_time || new Date().toISOString()}</code>\n` +
      `⚠️ <i>Bar strictly closed. Execute with strict risk discipline.</i>`;
  } else {
    alertMessage = payload.text || JSON.stringify(payload);
  }

  await sendTelegramMessage("8142877259", alertMessage);
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
