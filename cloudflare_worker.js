/**
 * 24/7 Institutional Cloudflare Worker for Telegram Trading Bot
 * Zero-fluff, professional market surveillance and signal execution.
 */

const BOT_TOKEN = "8932628751:AAFS_Z7SZMbfNAgNE9KmU6Sly32IGxDm2p0";
const TELEGRAM_API = `https://api.telegram.org/bot${BOT_TOKEN}`;

const ASSETS = [
  { name: "EUR/USD", ticker: "EURUSD=X", pip: 0.0001, digits: 4 },
  { name: "USD/JPY", ticker: "USDJPY=X", pip: 0.01,   digits: 2 },
  { name: "USD/CAD", ticker: "USDCAD=X", pip: 0.0001, digits: 4 },
  { name: "USD/CHF", ticker: "USDCHF=X", pip: 0.0001, digits: 4 },
  { name: "AUD/USD", ticker: "AUDUSD=X", pip: 0.0001, digits: 4 },
  { name: "GOLD",    ticker: "GC=F",     pip: 0.10,   digits: 2 }
];

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Gateway Operational", { status: 200 });
    }

    try {
      const rawText = await request.text();
      let payload = {};
      try {
        payload = JSON.parse(rawText);
      } catch (e) {
        payload = { text: rawText };
      }

      // Handle Telegram User Updates (Messages & Button Clicks)
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

/**
 * Routes Telegram user interactions
 */
async function handleTelegramUpdate(update) {
  // Inline Keyboard Button Callback
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
    else if (action === "cmd_status") await sendStatusMessage(chatId);
    else if (action === "cmd_strategy") await sendStrategyMessage(chatId);
    else if (action === "cmd_menu") await sendMenuMessage(chatId);

    return new Response("OK", { status: 200 });
  }

  // Text Commands
  if (update.message && update.message.text) {
    const chatId = update.message.chat.id;
    const text = update.message.text.trim().toLowerCase();

    if (text.startsWith("/radar") || text.startsWith("/scan") || text.startsWith("/tracking")) {
      await sendRadarMessage(chatId);
    } else if (text.startsWith("/prices") || text.startsWith("/quotes")) {
      await sendPricesMessage(chatId);
    } else if (text.startsWith("/status")) {
      await sendStatusMessage(chatId);
    } else if (text.startsWith("/strategy")) {
      await sendStrategyMessage(chatId);
    } else {
      await sendMenuMessage(chatId);
    }
    return new Response("OK", { status: 200 });
  }

  return new Response("Ignored", { status: 200 });
}

/**
 * /radar - Real-time pair tracking, proximity, and structural regime
 */
async function sendRadarMessage(chatId) {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";
  
  // Fetch market data in parallel
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

        if (closes.length < 25) {
          return `• <b>${asset.name}:</b> <i>Data Feed Synchronizing</i>`;
        }

        const price = closes[closes.length - 1];
        const prevHighs = highs.slice(-22, -1);
        const prevLows = lows.slice(-22, -1);
        const donchHigh = Math.max(...prevHighs);
        const donchLow = Math.min(...prevLows);

        const distHigh = (donchHigh - price) / asset.pip;
        const distLow = (price - donchLow) / asset.pip;

        // RSI(14)
        let gains = 0, losses = 0;
        for (let i = closes.length - 14; i < closes.length; i++) {
          const diff = closes[i] - closes[i - 1];
          if (diff >= 0) gains += diff;
          else losses += Math.abs(diff);
        }
        const rs = (gains / 14) / ((losses / 14) || 1e-9);
        const rsi = 100 - (100 / (1 + rs));

        // Structural Status Classification
        let status = "";
        let detail = "";

        if (rsi > 75) {
          status = "⚠️ Overbought Guard";
          detail = `RSI ${rsi.toFixed(1)}`;
        } else if (rsi < 25) {
          status = "⚠️ Oversold Guard";
          detail = `RSI ${rsi.toFixed(1)}`;
        } else if (distHigh <= 8.0) {
          status = "🔥 Imminent Breakout";
          detail = `${distHigh.toFixed(1)}p to High`;
        } else if (distLow <= 8.0) {
          status = "🔥 Imminent Breakdown";
          detail = `${distLow.toFixed(1)}p to Low`;
        } else if (distHigh <= 18.0) {
          status = "👀 Approaching Resistance";
          detail = `${distHigh.toFixed(1)}p to High`;
        } else if (distLow <= 18.0) {
          status = "👀 Approaching Support";
          detail = `${distLow.toFixed(1)}p to Low`;
        } else {
          status = "⏸ Range Consolidation";
          detail = `±${Math.min(distHigh, distLow).toFixed(1)}p in Band`;
        }

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
        { text: "📊 Market Quotes", callback_data: "cmd_prices" }
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
    ASSETS.map(async (asset) => {
      try {
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${asset.ticker}?range=1d&interval=15m`;
        const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
        const json = await res.json();
        const quote = json?.chart?.result?.[0]?.indicators?.quote?.[0];
        const closes = quote?.close?.filter(v => v !== null && v !== undefined) || [];
        if (closes.length > 0) {
          const p = closes[closes.length - 1];
          return `• <b>${asset.name}:</b> <code>${p.toFixed(asset.digits)}</code>`;
        }
        return `• <b>${asset.name}:</b> <i>Market Closed</i>`;
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
  const text = 
    `🟢 <b>SYSTEM STATUS</b>\n` +
    `<b>──────────────────────────</b>\n` +
    `• <b>Engine State:</b> 🟢 <b>ONLINE & MONITORING</b>\n` +
    `• <b>Host:</b> Cloudflare Global Edge & GitHub Cloud\n` +
    `• <b>Coverage:</b> 6 Instruments (15M / 1H Intervals)\n` +
    `• <b>Schedule:</b> Automated 15-Minute Scan Cycle\n` +
    `• <b>Hardware Dependency:</b> Zero (Runs with PC off)\n` +
    `• <b>Timestamp:</b> <code>${utcNow}</code>`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "📡 Market Radar", callback_data: "cmd_radar" },
        { text: "🎯 Strategy Rules", callback_data: "cmd_strategy" }
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
    `• <b>Trend Alignment:</b> EMA 20 > EMA 50 (Long) / EMA 20 < EMA 50 (Short)\n` +
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
  const text = 
    `🏛 <b>INSTITUTIONAL SIGNAL ENGINE</b>\n` +
    `<b>──────────────────────────</b>\n` +
    `Automated 24/7 Market Surveillance\n` +
    `EUR/USD • USD/JPY • USD/CAD • USD/CHF • AUD/USD • GOLD\n\n` +
    `Select an option below:`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: "📡 Market Radar", callback_data: "cmd_radar" },
        { text: "📊 Market Quotes", callback_data: "cmd_prices" }
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
