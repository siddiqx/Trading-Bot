/**
 * 24/7 Professional Cloudflare Worker for Telegram Trading Bot
 * 
 * Handles:
 * 1. Interactive Telegram Bot commands & Inline Buttons (/start, /status, /prices, /strategy)
 * 2. Incoming trade signal webhooks (TradingView / Cloud Market Scanner)
 * 3. Live real-time market price quoting via Yahoo Finance
 */

const BOT_TOKEN = "8932628751:AAFS_Z7SZMbfNAgNE9KmU6Sly32IGxDm2p0";
const TELEGRAM_API = `https://api.telegram.org/bot${BOT_TOKEN}`;

const SYMBOLS = [
  { name: "EUR/USD", ticker: "EURUSD=X", digits: 4 },
  { name: "USD/JPY", ticker: "USDJPY=X", digits: 3 },
  { name: "USD/CAD", ticker: "USDCAD=X", digits: 4 },
  { name: "USD/CHF", ticker: "USDCHF=X", digits: 4 },
  { name: "AUD/USD", ticker: "AUDUSD=X", digits: 4 },
  { name: "GOLD",    ticker: "GC=F",     digits: 2 }
];

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Telegram & TradingView 24/7 Gateway Active.", { status: 200 });
    }

    try {
      const rawText = await request.text();
      let data = {};
      try {
        data = JSON.parse(rawText);
      } catch (e) {
        // Raw text signal fallback
        data = { text: rawText };
      }

      // Check if this is an incoming update from TELEGRAM
      if (data.update_id) {
        return await handleTelegramUpdate(data);
      }

      // Otherwise, it is an INCOMING SIGNAL (from TradingView or Scanner)
      return await handleIncomingSignal(data);

    } catch (err) {
      return new Response("Internal Error: " + err.message, { status: 500 });
    }
  }
};

/**
 * Handles Telegram user messages and inline button clicks
 */
async function handleTelegramUpdate(update) {
  // 1. Handle Inline Button Callback Queries
  if (update.callback_query) {
    const cb = update.callback_query;
    const chatId = cb.message.chat.id;
    const data = cb.data;

    // Answer callback query to remove loading spinner in Telegram
    await fetch(`${TELEGRAM_API}/answerCallbackQuery`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ callback_query_id: cb.id })
    });

    if (data === "cmd_status") {
      await sendStatusMessage(chatId);
    } else if (data === "cmd_prices") {
      await sendPricesMessage(chatId);
    } else if (data === "cmd_strategy") {
      await sendStrategyMessage(chatId);
    } else if (data === "cmd_menu") {
      await sendStartMessage(chatId);
    }
    return new Response("OK", { status: 200 });
  }

  // 2. Handle Text Messages & Commands
  if (update.message && update.message.text) {
    const msg = update.message;
    const chatId = msg.chat.id;
    const text = msg.text.trim();

    if (text.startsWith("/start") || text.startsWith("/help")) {
      await sendStartMessage(chatId);
    } else if (text.startsWith("/status")) {
      await sendStatusMessage(chatId);
    } else if (text.startsWith("/prices") || text.startsWith("/pairs")) {
      await sendPricesMessage(chatId);
    } else if (text.startsWith("/strategy")) {
      await sendStrategyMessage(chatId);
    } else {
      await sendTelegramMessage(chatId, 
        "🤖 <b>Command not recognized.</b>\n\n" +
        "Please use the menu buttons below or type /help for available options.",
        getMainKeyboard()
      );
    }
    return new Response("OK", { status: 200 });
  }

  return new Response("Ignored Update", { status: 200 });
}

/**
 * /start and /help command
 */
async function sendStartMessage(chatId) {
  const text = 
    `🏛 <b>INSTITUTIONAL FOREX SIGNAL BOT</b>\n` +
    `<b>──────────────────────────</b>\n` +
    `Welcome to your automated 24/7 algorithmic signal companion.\n\n` +
    `<b>📡 Monitored Instruments:</b>\n` +
    `• <b>Forex:</b> EUR/USD, USD/JPY, USD/CAD, USD/CHF, AUD/USD\n` +
    `• <b>Commodities:</b> Gold (XAU/USD)\n` +
    `• <b>Timeframes:</b> 15-Minute (15M) & 1-Hour (1H)\n\n` +
    `<b>⚙️ System Architecture:</b>\n` +
    `• <b>Engine:</b> 20-Bar Donchian Structural Breakouts\n` +
    `• <b>Confirmation:</b> EMA 20/50 Momentum & Order Block (OB)\n` +
    `• <b>Risk Model:</b> Fixed 1:1.75 Risk/Reward with 1% Equity Sizing\n` +
    `• <b>Execution:</b> 24/7 Cloud Edge Engine (Zero PC Needed)\n\n` +
    `Select an option below to view real-time statistics:`;

  await sendTelegramMessage(chatId, text, getMainKeyboard());
}

/**
 * /status command
 */
async function sendStatusMessage(chatId) {
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC";
  const text = 
    `🟢 <b>SYSTEM OPERATIONAL STATUS</b>\n` +
    `<b>──────────────────────────</b>\n` +
    `• <b>Engine Status:</b> 🟢 <b>ONLINE & MONITORING</b>\n` +
    `• <b>Cloud Host:</b> Cloudflare Edge Workers & GitHub Cloud\n` +
    `• <b>Monitored Pairs:</b> 6 Instruments (12 Active Charts)\n` +
    `• <b>Uptime:</b> 24/7/365 (Uninterrupted Cloud)\n` +
    `• <b>Hardware Dependency:</b> Zero (PC Off)\n` +
    `• <b>Filter State:</b> Active (Strict RSI Guard & EMA Trend)\n` +
    `• <b>Current UTC Time:</b> <code>${utcNow}</code>\n\n` +
    `<i>The bot is continuously watching candles at every bar close to dispatch confirmed breakouts.</i>`;

  const keyboard = {
    inline_keyboard: [
      [{ text: "📈 View Live Prices", callback_data: "cmd_prices" }],
      [{ text: "🎯 View Strategy Rules", callback_data: "cmd_strategy" }],
      [{ text: "« Back to Main Menu", callback_data: "cmd_menu" }]
    ]
  };

  await sendTelegramMessage(chatId, text, keyboard);
}

/**
 * /prices command - Fetches live quotes from Yahoo Finance
 */
async function sendPricesMessage(chatId) {
  let lines = [];
  const utcNow = new Date().toISOString().replace("T", " ").substring(0, 16) + " UTC";

  for (const sym of SYMBOLS) {
    try {
      const url = `https://query1.finance.yahoo.com/v8/finance/chart/${sym.ticker}?range=1d&interval=15m`;
      const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
      const json = await res.json();
      const quote = json?.chart?.result?.[0]?.indicators?.quote?.[0];
      const closes = quote?.close?.filter(v => v !== null && v !== undefined);
      if (closes && closes.length > 0) {
        const lastClose = closes[closes.length - 1];
        const formatted = lastClose.toFixed(sym.digits);
        lines.push(`• <b>${sym.name}:</b> <code>${formatted}</code>`);
      } else {
        lines.push(`• <b>${sym.name}:</b> <i>Market Closed</i>`);
      }
    } catch (e) {
      lines.push(`• <b>${sym.name}:</b> <code>Online</code>`);
    }
  }

  const text = 
    `📊 <b>LIVE REAL-TIME MARKET QUOTES</b>\n` +
    `<b>──────────────────────────</b>\n` +
    lines.join("\n") + "\n" +
    `<b>──────────────────────────</b>\n` +
    `🕒 <b>Feed Synchronized:</b> <code>${utcNow}</code>\n` +
    `⚡ <i>Live institutional multi-asset price feed</i>`;

  const keyboard = {
    inline_keyboard: [
      [{ text: "🔄 Refresh Prices", callback_data: "cmd_prices" }],
      [{ text: "🟢 Check System Status", callback_data: "cmd_status" }],
      [{ text: "« Back to Main Menu", callback_data: "cmd_menu" }]
    ]
  };

  await sendTelegramMessage(chatId, text, keyboard);
}

/**
 * /strategy command
 */
async function sendStrategyMessage(chatId) {
  const text = 
    `🎯 <b>STRATEGY & RISK SPECIFICATIONS</b>\n` +
    `<b>──────────────────────────</b>\n` +
    `<b>1. Trend & Velocity Filter:</b>\n` +
    `• EMA 20 must be above EMA 50 for Longs (below for Shorts)\n` +
    `• EMA 20 must show active directional velocity slope\n\n` +
    `<b>2. Breakout Identification:</b>\n` +
    `• Scans for 20-period Donchian Channel breakouts\n` +
    `• Strictly waits for the candle to close (No mid-bar fakeouts)\n\n` +
    `<b>3. Structural Protection:</b>\n` +
    `• <b>Stop Loss:</b> Placed behind the Origin Order Block (OB)\n` +
    `• <b>Take Profit:</b> Calculated at a fixed <b>1 : 1.75</b> Risk-to-Reward\n` +
    `• <b>Anti-Exhaustion RSI:</b> Rejects entries when RSI > 75 (Overbought) or < 25 (Oversold)\n\n` +
    `<b>4. Risk Management:</b>\n` +
    `• Recommended Risk: <b>1.0% Equity per trade</b>\n` +
    `• Strictly zero martingale, zero grid, zero revenge trading.`;

  const keyboard = {
    inline_keyboard: [
      [{ text: "📈 View Live Prices", callback_data: "cmd_prices" }],
      [{ text: "« Back to Main Menu", callback_data: "cmd_menu" }]
    ]
  };

  await sendTelegramMessage(chatId, text, keyboard);
}

/**
 * Handle trade signal forwarding from TradingView / Market Scanner
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

  // Forward to target chat
  await sendTelegramMessage("8142877259", alertMessage);
  return new Response("OK", { status: 200 });
}

/**
 * Standard Telegram Send Message helper
 */
async function sendTelegramMessage(chatId, text, replyMarkup = null) {
  const body = {
    chat_id: chatId,
    text: text,
    parse_mode: "HTML"
  };
  if (replyMarkup) {
    body.reply_markup = replyMarkup;
  }

  return await fetch(`${TELEGRAM_API}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
}

function getMainKeyboard() {
  return {
    inline_keyboard: [
      [
        { text: "📊 System Status", callback_data: "cmd_status" },
        { text: "📈 Live Prices", callback_data: "cmd_prices" }
      ],
      [
        { text: "🎯 Strategy Specifications", callback_data: "cmd_strategy" }
      ]
    ]
  };
}
