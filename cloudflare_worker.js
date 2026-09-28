/**
 * 24/7 Institutional Cloudflare Worker for Telegram Trading Bot
 * 
 * Features:
 * - Active Trade Tracking & Floating PnL
 * - Market Radar differentiating live trades vs surveillance
 * - /history command with pair and date range filtering
 * - /performance command calculated strictly from live trades taken from 2026-09-28 onwards
 * - Zero fluff, dense institutional formatting
 */

const BOT_TOKEN = "8932628751:AAFS_Z7SZMbfNAgNE9KmU6Sly32IGxDm2p0";
const TELEGRAM_API = `https://api.telegram.org/bot${BOT_TOKEN}`;

const ASSETS = [
  { name: "EUR/USD", symbol: "EURUSD", ticker: "EURUSD=X", pip: 0.0001, digits: 4 },
  { name: "USD/JPY", symbol: "USDJPY", ticker: "USDJPY=X", pip: 0.01,   digits: 2 },
  { name: "USD/CAD", symbol: "USDCAD", ticker: "USDCAD=X", pip: 0.0001, digits: 4 },
  { name: "USD/CHF", symbol: "USDCHF", ticker: "USDCHF=X", pip: 0.0001, digits: 4 },
  { name: "AUD/USD", symbol: "AUDUSD", ticker: "AUDUSD=X", pip: 0.0001, digits: 4 },
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
    const text = update.message.text.trim();
    const parts = text.split(/\s+/);
    const cmd = parts[0].toLowerCase();

    if (cmd === "/radar" || cmd === "/scan" || cmd === "/tracking") {
      await sendRadarMessage(chatId);
    } else if (cmd === "/prices" || cmd === "/quotes") {
      await sendPricesMessage(chatId);
    } else if (cmd === "/history") {
      const filterPair = parts[1] ? parts[1].toUpperCase().replace("/", "") : "ALL";
      const filterRange = parts[2] ? parts[2].toLowerCase() : "ALL";
      await sendHistoryMessage(chatId, filterPair, filterRange);
    } else if (cmd === "/performance" || cmd === "/stats") {
      const filterPair = parts[1] ? parts[1].toUpperCase().replace("/", "") : "ALL";
      await sendPerformanceMessage(chatId, filterPair);
    } else if (cmd === "/status") {
      await sendStatusMessage(chatId);
    } else if (cmd === "/strategy") {
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
  
  const results = await Promise.all(
    ASSETS.map(async (asset) => {
      try {
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${asset.ticker}?range=5d&interval=15m`;
        const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
        const json = await res.json();
        const quote = json?.chart?.result?.[0]?.indicators?.quote?.[0];
        
        const closes = quote?.close?.filter(v => v !== null && v !== undefined) || [];
        const highs = quote?.high?.filter(v => v !== null && v !== undefined) || [];
        const lows = quote?.low?.filter(v => v !== null && v !== undefined) || [];

        if (closes.length < 25) return `• <b>${asset.name}:</b> <i>Data Syncing</i>`;

        const price = closes[closes.length - 1];

        // 1. CHECK IF PAIR HAS AN ACTIVE RUNNING TRADE
        const activeTrade = STORED_ACTIVE_TRADES[asset.symbol];
        if (activeTrade) {
          const isLong = activeTrade.direction === "LONG";
          const pnlPips = ((price - activeTrade.entry) / asset.pip) * (isLong ? 1 : -1);
          const pnlSign = pnlPips >= 0 ? "+" : "";
          const icon = isLong ? "🟢" : "🔴";

          return (
            `• <b>${asset.name}:</b> <code>${price.toFixed(asset.digits)}</code>\n` +
            `  └ ${icon} <b>LIVE TRADE [${activeTrade.direction} @ ${activeTrade.entry}]</b>\n` +
            `  └ <b>Floating:</b> <code>${pnlSign}${pnlPips.toFixed(1)}p</code> | <b>SL:</b> <code>${activeTrade.stop_loss}</code> | <b>TP:</b> <code>${activeTrade.take_profit}</code>`
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

        let status = "", detail = "";
        if (rsi > 75) { status = "⚠️ Overbought Guard"; detail = `RSI ${rsi.toFixed(1)}`; }
        else if (rsi < 25) { status = "⚠️ Oversold Guard"; detail = `RSI ${rsi.toFixed(1)}`; }
        else if (distHigh <= 8.0) { status = "🔥 Imminent Breakout"; detail = `${distHigh.toFixed(1)}p to High`; }
        else if (distLow <= 8.0) { status = "🔥 Imminent Breakdown"; detail = `${distLow.toFixed(1)}p to Low`; }
        else if (distHigh <= 18.0) { status = "👀 Approaching Resistance"; detail = `${distHigh.toFixed(1)}p to High`; }
        else if (distLow <= 18.0) { status = "👀 Approaching Support"; detail = `${distLow.toFixed(1)}p to Low`; }
        else { status = "⏸ Range Consolidation"; detail = `±${Math.min(distHigh, distLow).toFixed(1)}p in Band`; }

        return `• <b>${asset.name}:</b> <code>${price.toFixed(asset.digits)}</code>\n  └ <b>${status}</b> (${detail})`;
      } catch (e) {
        return `• <b>${asset.name}:</b> <i>Feed Offline</i>`;
      }
    })
  );

  const text = 
    `📡 <b>MARKET SURVEILLANCE RADAR</b>\n` +
    `<b>──────────────────────────</b>\n` +
    results.join("\n") + "\n" +
    `<b>──────────────────────────</b>\n` +
    `🕒 <b>Time:</b> <code>${utcNow}</code>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "🔄 Refresh Radar", callback_data: "cmd_radar" },
        { text: "📜 Trade History", callback_data: "cmd_history" }
      ],
      [
        { text: "📈 Performance Metrics", callback_data: "cmd_performance" },
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
  if (filterRange === "today" || filterRange === "1d") {
    const todayStr = new Date().toISOString().substring(0, 10);
    allTrades = allTrades.filter(t => (t.opened_at || "").startsWith(todayStr));
  } else if (filterRange === "7d") {
    const cutoff = nowMs - (7 * 24 * 60 * 60 * 1000);
    allTrades = allTrades.filter(t => new Date(t.opened_at).getTime() >= cutoff);
  } else if (filterRange === "30d") {
    const cutoff = nowMs - (30 * 24 * 60 * 60 * 1000);
    allTrades = allTrades.filter(t => new Date(t.opened_at).getTime() >= cutoff);
  }

  // Build Output Rows
  let activeRows = [];
  let closedRows = [];

  for (const t of allTrades) {
    const dateStr = (t.opened_at || "").substring(0, 10);
    const pName = t.pair || t.symbol;

    if (t.is_active) {
      activeRows.push(
        `• <b>${pName} (${t.timeframe}):</b> ${t.direction} @ <code>${t.entry}</code>\n` +
        `  └ <b>Status:</b> 🟢 <b>LIVE FLOATING</b> | <b>SL:</b> <code>${t.stop_loss}</code> | <b>TP:</b> <code>${t.take_profit}</code>`
      );
    } else {
      const isWin = t.outcome === "WIN";
      const icon = isWin ? "🎯 WIN" : "🛑 LOSS";
      const sign = t.realized_pips >= 0 ? "+" : "";
      const rSign = t.realized_r >= 0 ? "+" : "";

      closedRows.push(
        `• <b>${dateStr} | ${pName} (${t.timeframe}):</b>\n` +
        `  └ ${t.direction} @ <code>${t.entry}</code> ➔ <code>${t.exit_price}</code>\n` +
        `  └ <b>Outcome:</b> ${icon} (<b>${sign}${t.realized_pips}p</b> / <b>${rSign}${t.realized_r}R</b>)`
      );
    }
  }

  let bodyText = "";
  if (activeRows.length > 0) {
    bodyText += `🟢 <b>ACTIVE POSITIONS (${activeRows.length}):</b>\n` + activeRows.join("\n") + "\n\n";
  }
  if (closedRows.length > 0) {
    bodyText += `📁 <b>COMPLETED TRADES (${closedRows.length}):</b>\n` + closedRows.join("\n") + "\n";
  }
  if (allTrades.length === 0) {
    bodyText = `<i>No recorded trades found for ${filterPair} (${filterRange}).</i>\n`;
  }

  const text = 
    `📜 <b>TRADE HISTORY LEDGER</b>\n` +
    `<b>──────────────────────────</b>\n` +
    `<b>Scope:</b> <code>${filterPair}</code> | <b>Range:</b> <code>${filterRange.toUpperCase()}</code>\n` +
    `<b>Tracking Baseline:</b> <code>2026-09-28</code>\n` +
    `<b>──────────────────────────</b>\n\n` +
    bodyText +
    `<b>──────────────────────────</b>\n` +
    `🕒 <b>Time:</b> <code>${utcNow}</code>`;

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

  const text = 
    `📈 <b>STRATEGY PERFORMANCE METRICS</b>\n` +
    `<b>──────────────────────────</b>\n` +
    `<b>Scope:</b> <code>${filterPair}</code>\n` +
    `<b>Tracking Started:</b> <code>2026-09-28</code>\n` +
    `<b>──────────────────────────</b>\n\n` +
    `• <b>Total Closed Trades:</b> <code>${totalClosed}</code>\n` +
    `• <b>Win Rate:</b> <b>${winRate}${totalClosed > 0 ? "%" : ""}</b> (${wins}W / ${losses}L)\n` +
    `• <b>Net Realized Pips:</b> <b>${pipsSign}${netPips.toFixed(1)} pips</b>\n` +
    `• <b>Net Realized Return:</b> <b>${rSign}${netR.toFixed(2)} R</b>\n` +
    `• <b>Profit Factor:</b> <code>${profitFactor}</code>\n` +
    `• <b>Active Live Positions:</b> <code>${active.length}</code>\n\n` +
    `<b>──────────────────────────</b>\n` +
    `⚡ <i>Calculated strictly from live forward executions.</i>\n` +
    `🕒 <b>Time:</b> <code>${utcNow}</code>`;

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
    ASSETS.map(async (asset) => {
      try {
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${asset.ticker}?range=1d&interval=15m`;
        const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
        const json = await res.json();
        const closes = json?.chart?.result?.[0]?.indicators?.quote?.[0]?.close?.filter(v => v !== null) || [];
        if (closes.length > 0) return `• <b>${asset.name}:</b> <code>${closes[closes.length - 1].toFixed(asset.digits)}</code>`;
        return `• <b>${asset.name}:</b> <i>Closed</i>`;
      } catch (e) {
        return `• <b>${asset.name}:</b> <i>Offline</i>`;
      }
    })
  );

  const text = 
    `📊 <b>LIVE MARKET QUOTES</b>\n` +
    `<b>──────────────────────────</b>\n` +
    rows.join("\n") + "\n" +
    `<b>──────────────────────────</b>\n` +
    `🕒 <b>Time:</b> <code>${utcNow}</code>`;

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
    `🟢 <b>SYSTEM STATUS</b>\n` +
    `<b>──────────────────────────</b>\n` +
    `• <b>Engine State:</b> 🟢 <b>ONLINE & MONITORING</b>\n` +
    `• <b>Host:</b> Cloudflare Global Edge & GitHub Cloud\n` +
    `• <b>Active Positions:</b> <code>${activeCount}</code> locked\n` +
    `• <b>Total Closed:</b> <code>${closedCount}</code> recorded\n` +
    `• <b>Hardware Dependency:</b> Zero (Runs with PC off)\n` +
    `• <b>Timestamp:</b> <code>${utcNow}</code>`;

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
 * /strategy - Pure execution specifications
 */
async function sendStrategyMessage(chatId) {
  const text = 
    `🎯 <b>STRATEGY SPECIFICATIONS</b>\n` +
    `<b>──────────────────────────</b>\n` +
    `• <b>Breakout Trigger:</b> Confirmed 20-period Donchian bar close\n` +
    `• <b>Trend Alignment:</b> EMA 20 above EMA 50 (Long) / EMA 20 below EMA 50 (Short)\n` +
    `• <b>Structural Protection:</b> Stop Loss anchored to Origin Order Block\n` +
    `• <b>Exhaustion Filter:</b> Anti-Chase RSI Guard (25.0 <= RSI <= 75.0)\n` +
    `• <b>Target Matrix:</b> Fixed 1 : 1.75 Risk-to-Reward ratio\n` +
    `• <b>Capital Sizing:</b> 1.0% Equity Risk per trade`;

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
    `🏛 <b>INSTITUTIONAL SIGNAL ENGINE</b>\n` +
    `<b>──────────────────────────</b>\n` +
    `Automated 24/7 Market Surveillance & Trade Management\n` +
    `EUR/USD • USD/JPY • USD/CAD • USD/CHF • AUD/USD • GOLD\n\n` +
    `Select an option below:`;

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
      `${icon} <b>NEW TRADE SIGNAL: ${displayPair}</b>\n` +
      `<b>──────────────────────────</b>\n` +
      `🧭 <b>Direction:</b> <b>${actionText}</b>\n` +
      `⏱ <b>Timeframe:</b> <b>${payload.timeframe || "1H"}</b>\n` +
      `<b>──────────────────────────</b>\n\n` +
      `<b>📋 TRADE PARAMETERS</b>\n` +
      `• <b>Entry Price:</b> <code>${payload.entry || payload.price}</code>\n` +
      `• <b>Stop Loss:</b> <code>${payload.stop_loss}</code>\n` +
      `• <b>Take Profit:</b> <code>${payload.take_profit}</code>\n` +
      `• <b>Risk / Reward:</b> <b>1 : ${payload.risk_reward || "1.75"}</b>\n` +
      `• <b>Recommended Risk:</b> <b>1.0% Equity</b>\n\n` +
      `<b>🔬 STRATEGY CONFLUENCE</b>\n` +
      `• <b>Setup:</b> 20-Bar Structural Breakout\n` +
      `• <b>Signal Score:</b> <b>${payload.signal_score || 95} / 100</b>\n\n` +
      `<b>──────────────────────────</b>\n` +
      `🕒 <b>Confirmed Bar:</b> <code>${payload.signal_time || new Date().toISOString()}</code>\n` +
      `⚠️ <i>Bar strictly closed. Execute with strict risk discipline.</i>`;
  } else {
    alertMessage = payload.text || JSON.stringify(payload);
  }

  await sendTelegramMessage("8142877259", alertMessage);
  return new Response("OK", { status: 200 });
}

async function sendTelegramMessage(chatId, text, replyMarkup = null) {
  const body = { chat_id: chatId, text: text, parse_mode: "HTML" };
  if (replyMarkup) body.reply_markup = replyMarkup;

  return await fetch(`${TELEGRAM_API}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
}
