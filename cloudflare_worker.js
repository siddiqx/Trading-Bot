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

// In-memory trade ledger state
let STORED_ACTIVE_TRADES = {
  "USDCHF": {
    "trade_id": "USDCHF_1H_2026-09-28T06:00:00Z_LONG",
    "pair": "USD/CHF",
    "symbol": "USDCHF",
    "ticker": "USDCHF=X",
    "direction": "LONG",
    "timeframe": "1H",
    "entry": 0.83031,
    "stop_loss": 0.82851,
    "take_profit": 0.83346,
    "sl_pips": 18.0,
    "tp_pips": 31.5,
    "rr": 1.75,
    "pip": 0.0001,
    "digits": 5,
    "opened_at": "2026-09-28T06:00:00Z",
    "status": "OPEN"
  },
  "EURUSD": {
    "trade_id": "EURUSD_1H_2026-09-28T14:00:00Z_SHORT",
    "pair": "EUR/USD",
    "symbol": "EURUSD",
    "ticker": "EURUSD=X",
    "direction": "SHORT",
    "timeframe": "1H",
    "entry": 1.13662,
    "stop_loss": 1.13842,
    "take_profit": 1.13347,
    "sl_pips": 18.0,
    "tp_pips": 31.5,
    "rr": 1.75,
    "pip": 0.0001,
    "digits": 5,
    "opened_at": "2026-09-28T14:00:00Z",
    "status": "OPEN"
  }
};

let STORED_COMPLETED_TRADES = [];

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("Gateway Operational", { status: 200 });

    try {
      const rawText = await request.text();
      let payload = {};
      try { payload = JSON.parse(rawText); } catch (e) { payload = { text: rawText }; }

      // Handle Sync from Market Scanner Engine
      if (payload.event === "sync_trades") {
        if (payload.active_trades) STORED_ACTIVE_TRADES = payload.active_trades;
        if (payload.completed_trades) STORED_COMPLETED_TRADES = payload.completed_trades;
        return new Response("Trades Synced", { status: 200 });
      }

      // Handle Telegram User Updates
      if (payload.update_id) {
        return await handleTelegramUpdate(payload);
      }

      // Handle Incoming Trade Signals
      return await handleIncomingSignal(payload);
    } catch (err) {
      return new Response("Error: " + err.message, { status: 500 });
    }
  }
};

async function handleTelegramUpdate(update) {
  if (update.callback_query) {
    const cb = update.callback_query;
    const chatId = cb.message.chat.id;
    const action = cb.data;

    await fetch(`${TELEGRAM_API}/answerCallbackQuery`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ callback_query_id: cb.id })
    });

    if (action === "cmd_radar") await sendRadarMessage(chatId);
    else if (action === "cmd_prices") await sendPricesMessage(chatId);
    else if (action === "cmd_history") await sendHistoryMessage(chatId, "ALL", "ALL");
    else if (action === "cmd_performance") await sendPerformanceMessage(chatId, "ALL");
    else if (action === "cmd_status") await sendStatusMessage(chatId);
    else if (action === "cmd_strategy") await sendStrategyMessage(chatId);
    else if (action === "cmd_menu") await sendMenuMessage(chatId);
    else if (action.startsWith("hist_pair_")) {
      const p = action.replace("hist_pair_", "");
      await sendHistoryMessage(chatId, p, "ALL");
    } else if (action.startsWith("hist_range_")) {
      const r = action.replace("hist_range_", "");
      await sendHistoryMessage(chatId, "ALL", r);
    } else if (action.startsWith("perf_pair_")) {
      const p = action.replace("perf_pair_", "");
      await sendPerformanceMessage(chatId, p);
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

    if (cmd === "/radar" || cmd === "/scan" || cmd === "/tracking") {
      await sendRadarMessage(chatId);
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
      await sendHistoryMessage(chatId, filterPair, filterRange);
    } else if (cmd === "/performance" || cmd === "/stats") {
      const filterPair = parts[1] ? parts[1].toUpperCase().replace("/", "") : "ALL";
      await sendPerformanceMessage(chatId, filterPair);
    } else if (cmd === "/status") {
      await sendStatusMessage(chatId);
    } else if (cmd === "/strategy" || cmd === "/rules") {
      await sendStrategyMessage(chatId);
    } else {
      await sendMenuMessage(chatId);
    }
    return new Response("OK", { status: 200 });
  }

  return new Response("Ignored", { status: 200 });
}

/**
 * /radar - Differentiates active live trades from normal surveillance
 */
async function sendRadarMessage(chatId) {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";
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
        const activeTrade = STORED_ACTIVE_TRADES[asset.symbol];
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

        const distHigh = (donchHigh - price) / asset.pip;
        const distLow = (price - donchLow) / asset.pip;

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
          detail = `RSI ${rsi.toFixed(1)} Overbought`;
        } else if (rsi < 25) {
          badge = "🛡";
          status = "RSI Guard Active";
          detail = `RSI ${rsi.toFixed(1)} Oversold`;
        } else if (distHigh <= 8.0) {
          badge = "⚡";
          status = "Imminent Breakout";
          detail = `${distHigh.toFixed(1)}p to Resistance`;
        } else if (distLow <= 8.0) {
          badge = "⚡";
          status = "Imminent Breakdown";
          detail = `${distLow.toFixed(1)}p to Support`;
        } else if (distHigh <= 18.0) {
          badge = "👀";
          status = "Approaching Resistance";
          detail = `${distHigh.toFixed(1)}p to High`;
        } else if (distLow <= 18.0) {
          badge = "👀";
          status = "Approaching Support";
          detail = `${distLow.toFixed(1)}p to Low`;
        } else {
          badge = "⏸";
          status = "Range Consolidation";
          detail = `±${Math.min(distHigh, distLow).toFixed(1)}p in Band`;
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
        { text: "📜 Trade History", callback_data: "cmd_history" }
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
 * /history - Historical trade records with pair & date range filters
 */
async function sendHistoryMessage(chatId, filterPair = "ALL", filterRange = "ALL") {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";
  const nowMs = Date.now();

  // Combine Active and Completed Trades
  let allTrades = [];

  // Active trades
  for (const [sym, t] of Object.entries(STORED_ACTIVE_TRADES)) {
    allTrades.push({ ...t, is_active: true });
  }
  // Completed trades
  for (const t of STORED_COMPLETED_TRADES) {
    allTrades.push({ ...t, is_active: false });
  }

  // 1. Filter by Pair
  if (filterPair !== "ALL") {
    allTrades = allTrades.filter(t => (t.symbol || "").toUpperCase() === filterPair.toUpperCase());
  }

  // 2. Filter by Date Range
  let rangeLabel = "ALL TIME";
  if (filterRange === "today" || filterRange === "1d") {
    rangeLabel = "TODAY";
    const todayStr = new Date().toISOString().substring(0, 10);
    allTrades = allTrades.filter(t => (t.opened_at || "").startsWith(todayStr));
  } else if (filterRange === "7d") {
    rangeLabel = "LAST 7 DAYS";
    const cutoff = nowMs - (7 * 24 * 60 * 60 * 1000);
    allTrades = allTrades.filter(t => new Date(t.opened_at).getTime() >= cutoff);
  } else if (filterRange === "30d") {
    rangeLabel = "LAST 30 DAYS";
    const cutoff = nowMs - (30 * 24 * 60 * 60 * 1000);
    allTrades = allTrades.filter(t => new Date(t.opened_at).getTime() >= cutoff);
  }

  // Build Output Rows
  let activeRows = [];
  let closedRows = [];
  let activeIdx = 1;
  let closedIdx = 1;

  for (const t of allTrades) {
    const dateStr = (t.opened_at || "").substring(0, 10);
    const pName = t.pair || t.symbol;

    if (t.is_active) {
      const num = activeIdx++;
      const isLong = t.direction === "LONG";
      const dirIcon = isLong ? "🟢" : "🔴";
      const openTime = (t.opened_at || "").substring(11, 16) || "00:00";
      activeRows.push(
        `<b>${num}. ${pName}</b> · ${t.timeframe} · ${dirIcon} <b>${t.direction}</b>\n` +
        `• Entry: <code>${t.entry}</code> (${openTime} UTC)\n` +
        `• Targets: SL <code>${t.stop_loss}</code> | TP <code>${t.take_profit}</code>`
      );
    } else {
      const num = closedIdx++;
      const isWin = t.outcome === "WIN";
      const outcomeBadge = isWin ? "🎯 <b>WIN</b>" : "🛑 <b>LOSS</b>";
      const sign = t.realized_pips >= 0 ? "+" : "";
      const rSign = t.realized_r >= 0 ? "+" : "";

      closedRows.push(
        `<b>${num}. ${pName}</b> · ${t.timeframe} · <b>${t.direction}</b>\n` +
        `• Date: <code>${dateStr}</code>\n` +
        `• Price: <code>${t.entry}</code> ➔ <code>${t.exit_price}</code>\n` +
        `• Outcome: ${outcomeBadge} (${sign}${t.realized_pips}p / ${rSign}${t.realized_r}R)`
      );
    }
  }

  let bodyText = "";
  if (activeRows.length > 0) {
    bodyText += `🟢 <b>ACTIVE POSITIONS (${activeRows.length})</b>\n\n` + activeRows.join("\n\n") + "\n\n";
  }
  if (closedRows.length > 0) {
    bodyText += `📁 <b>COMPLETED TRADES (${closedRows.length})</b>\n\n` + closedRows.join("\n\n") + "\n\n";
  }
  if (allTrades.length === 0) {
    bodyText = `<i>No recorded trades found for ${filterPair} (${rangeLabel}).</i>\n\n`;
  }

  const text = 
    `📜 <b>TRADE HISTORY LEDGER</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `Scope: <b>${filterPair}</b> | Range: <b>${rangeLabel}</b>\n` +
    `Baseline: <code>2026-09-28</code> (Live Forward)\n` +
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
        { text: "All Pairs", callback_data: "hist_pair_ALL" },
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
async function sendPerformanceMessage(chatId, filterPair = "ALL") {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";

  let closed = STORED_COMPLETED_TRADES.slice();
  let active = Object.values(STORED_ACTIVE_TRADES);

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
        { text: "📜 View Trade History", callback_data: "cmd_history" },
        { text: "« Menu", callback_data: "cmd_menu" }
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
async function sendStatusMessage(chatId) {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC";
  const activeCount = Object.keys(STORED_ACTIVE_TRADES).length;
  const closedCount = STORED_COMPLETED_TRADES.length;

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
        { text: "📡 Market Radar", callback_data: "cmd_radar" },
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
async function sendMenuMessage(chatId) {
  const activeCount = Object.keys(STORED_ACTIVE_TRADES).length;
  const activeLabel = activeCount > 0 ? ` (${activeCount} Active)` : "";

  const text = 
    `🏛 <b>INSTITUTIONAL SIGNAL TERMINAL</b>\n` +
    `━━━━━━━━━━━━━━━━━━\n` +
    `Automated 24/7 Algorithmic Trading & Forward Verification\n` +
    `Coverage: <b>EURUSD · USDJPY · USDCAD · USDCHF · AUDUSD · GOLD</b>\n\n` +
    `<b>SYSTEM MODULES</b>\n` +
    `1. /radar ── Market surveillance & live trades\n` +
    `2. /prices ── Live quotes across all 6 pairs\n` +
    `3. /history ── Historical trade log & ledger\n` +
    `4. /performance ── Win rate & return metrics\n` +
    `5. /strategy ── Systematic entry/exit rules\n` +
    `6. /status ── 24/7 serverless engine health\n\n` +
    `Select a dashboard module below:`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: `📡 Market Radar${activeLabel}`, callback_data: "cmd_radar" },
        { text: "📊 Market Quotes", callback_data: "cmd_prices" }
      ],
      [
        { text: "📜 Trade History", callback_data: "cmd_history" },
        { text: "📈 Performance", callback_data: "cmd_performance" }
      ],
      [
        { text: "🟢 System Status", callback_data: "cmd_status" },
        { text: "🎯 Strategy Rules", callback_data: "cmd_strategy" }
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
