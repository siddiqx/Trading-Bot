"""Tests for Telegram message formatting and command handling."""

import pytest
from app.services.telegram import TelegramService


def test_telegram_message_formatting_long():
    service = TelegramService(bot_token="mock_token", chat_id="123456")
    signal_data = {
        "symbol": "EURUSD",
        "direction": "LONG",
        "strategy": "Adaptive Trend-Momentum Breakout",
        "signal_score": 82.0,
        "timeframe": "60",
        "htf_regime": "BULLISH",
        "adx": 28.4,
        "roc": 0.31,
        "breakout_length": 20,
        "entry": 1.17240,
        "stop_loss": 1.17070,
        "take_profit": 1.17580,
        "risk_reward": 2.0,
        "atr": 0.00097,
        "signal_time": "2026-03-09 14:00 UTC",
        "strategy_version": "1.0.0",
        "environment": "LIVE",
    }
    msg = service.format_signal_message(signal_data)

    assert "🟢 <b>EURUSD LONG" in msg
    assert "Signal Quality:</b> 82/100" in msg
    assert "• 4H Trend: <code>BULLISH</code>" in msg
    assert "• 1H ADX(14): <code>28.40</code>" in msg
    assert "• Momentum ROC: <code>+0.31%</code>" in msg
    assert "• Ideal Entry: <code>1.17240</code>" in msg
    assert "• Stop Loss: <code>1.17070</code>" in msg
    assert "• Take Profit: <code>1.17580</code>" in msg
    assert "• Risk/Reward: <code>1:2.0</code>" in msg
    assert "GUARANTEED" not in msg
    assert "SAFE TRADE" not in msg


def test_telegram_message_formatting_test_env():
    service = TelegramService(bot_token="mock_token", chat_id="123456")
    signal_data = {
        "symbol": "USDJPY",
        "direction": "SHORT",
        "signal_score": 75,
        "entry": 150.25,
        "stop_loss": 150.65,
        "take_profit": 149.45,
        "adx": 24.0,
        "roc": -0.2,
        "atr": 0.22,
        "environment": "TEST",
    }
    msg = service.format_signal_message(signal_data)
    assert "TEST SIGNAL" in msg
    assert "🔴 <b>USDJPY SHORT" in msg


def test_telegram_message_formatting_intraday_mtf():
    service = TelegramService(bot_token="mock_token", chat_id="123456")
    signal_data = {
        "symbol": "EURUSD",
        "direction": "SHORT",
        "strategy": "Adaptive Intraday MTF Strategy",
        "signal_score": 85.0,
        "timeframe": "5",
        "htf_regime": "BEARISH",
        "intermediate_regime": "BEARISH",
        "entry_type": "PULLBACK_CONTINUATION",
        "suggested_lots": 0.45,
        "risk_percent": 1.0,
        "adx": 22.4,
        "roc": -0.15,
        "breakout_length": 20,
        "entry": 1.13720,
        "stop_loss": 1.13840,
        "take_profit": 1.13540,
        "risk_reward": 1.5,
        "atr": 0.00065,
        "candle_body_ratio": 0.82,
        "signal_time": "2026-09-26 22:50 UTC",
        "strategy_version": "1.0.0",
        "environment": "LIVE",
    }
    msg = service.format_signal_message(signal_data)
    assert "🔴 <b>EURUSD SHORT" in msg
    assert "MULTI-TIMEFRAME ANALYSIS" in msg
    assert "1H (60m Anchor)" in msg
    assert "Sizing (1.0% Risk): <b>0.45 Lots</b>" in msg


def test_telegram_message_formatting_order_block_fib():
    service = TelegramService(bot_token="mock_token", chat_id="123456")
    signal_data = {
        "symbol": "EURUSD",
        "direction": "LONG",
        "strategy": "Adaptive Trend-Momentum Breakout",
        "signal_score": 92.0,
        "timeframe": "60",
        "htf_regime": "BULLISH",
        "entry_type": "ORDER_BLOCK_FIB_CONFLUENCE",
        "order_block_high": 1.08480,
        "order_block_low": 1.08280,
        "fib_50": 1.08420,
        "fib_618": 1.08350,
        "fib_ext_tp": 1.08950,
        "suggested_lots": 0.50,
        "risk_percent": 1.0,
        "adx": 28.5,
        "rsi": 64.5,
        "roc": 0.35,
        "breakout_length": 48,
        "entry": 1.08420,
        "stop_loss": 1.08250,
        "take_profit": 1.08950,
        "risk_reward": 2.2,
        "atr": 0.00115,
        "signal_time": "2026-09-27 00:00 UTC",
        "strategy_version": "1.0.0",
        "environment": "LIVE",
    }
    msg = service.format_signal_message(signal_data)
    assert "🟢 <b>EURUSD LONG (1H Signal)" in msg
    assert "ORDER BLOCK & FIBONACCI TARGETS" in msg
    assert "• Origin Order Block (OB): <code>1.08280 – 1.08480</code>" in msg
    assert "• Fib OTE (50% – 61.8%): <code>1.08350 – 1.08420</code>" in msg
    assert "• Fib Extension TP Target: <code>1.08950</code>" in msg
    assert "• Ideal Entry: <code>1.08420</code>" in msg
    assert "• Stop Loss: <code>1.08250</code>" in msg
    assert "• Take Profit: <code>1.08950</code>" in msg
    assert "• Risk/Reward: <code>1:2.2</code>" in msg
    assert "Sizing (1.0% Risk): <b>0.50 Lots</b>" in msg



def test_telegram_command_responses():
    service = TelegramService(bot_token="mock_token", chat_id="123456")

    help_reply = service.generate_command_response("/help")
    assert "Available Commands" in help_reply

    strat_reply = service.generate_command_response("/strategy")
    assert "INSTITUTIONAL STRATEGY SPECIFICATION" in strat_reply
    assert "ICT KILLZONE LIQUIDITY SWEEP" in strat_reply

    stats_reply = service.generate_command_response(
        "/stats",
        stats={
            "total_signals": 10,
            "long_signals": 6,
            "short_signals": 4,
            "live_signals": 8,
            "signals_by_pair": {"EURUSD": 6, "GBPUSD": 4},
        },
    )
    assert "Total Signals Recorded:</b> 10" in stats_reply
    assert "EURUSD: 6" in stats_reply

    active_reply = service.generate_command_response("/active")
    assert "ACTIVE LIVE TRADES" in active_reply

    status_reply = service.generate_command_response("/status")
    assert "SYSTEM OPERATIONAL STATUS" in status_reply
    assert "INFRASTRUCTURE &amp; HEALTH" in status_reply

    perf_reply = service.generate_command_response("/performance")
    assert "STRATEGY PERFORMANCE" in perf_reply
    assert "Fixed 15-Pip TP / 10-Pip SL" in perf_reply

    hist_reply = service.generate_command_response("/history")
    assert "COMPLETED TRADE HISTORY" in hist_reply


@pytest.mark.asyncio
async def test_telegram_supervisor_close_and_cancel_payloads(monkeypatch, tmp_path):
    """Verify scripts.run_telegram_bot close and cancel commands handle active trades and empty states."""
    import scripts.run_telegram_bot as rtb

    # 1. Test when no active trades exist
    empty_records = {"tracking_started": "2026-10-15", "active_trades": {}, "completed_trades": []}
    monkeypatch.setattr(rtb, "load_trade_records", lambda: empty_records)

    close_msg, _ = await rtb.get_close_payload()
    assert "No Active Trades to Close" in close_msg

    cancel_msg, _ = await rtb.get_cancel_payload()
    assert "No Active Trades to Cancel" in cancel_msg

    # 2. Test when active trade exists and is closed manually
    active_records = {
        "tracking_started": "2026-10-15",
        "active_trades": {
            "EURUSD": {
                "trade_id": "TEST_EURUSD_01",
                "pair": "EUR/USD",
                "symbol": "EURUSD",
                "direction": "LONG",
                "entry": 1.08000,
                "stop_loss": 1.07780,
                "take_profit": 1.08330,
                "sl_pips": 22.0,
                "tp_pips": 33.0,
                "pip": 0.0001,
                "digits": 5,
                "status": "OPEN",
                "ctrader_position_id": 999123
            }
        },
        "completed_trades": []
    }
    saved_records = []
    closed_pos = []

    async def mock_live_price(asset, timeout):
        return 1.08110

    monkeypatch.setattr(rtb, "load_trade_records", lambda: dict(active_records))
    monkeypatch.setattr(rtb, "save_trade_records", lambda rec: saved_records.append(rec))
    monkeypatch.setattr(rtb, "get_live_price", mock_live_price)
    monkeypatch.setattr("core.ctrader_executor.close_ctrader_position", lambda position_id, pair=None: closed_pos.append(position_id))

    close_text, _ = await rtb.get_close_payload("EURUSD")
    assert "MANUAL TRADE CLOSE" in close_text
    assert "EURUSD" in close_text
    assert "+11.0 pips" in close_text
    assert "+0.50 R" in close_text
    assert len(saved_records) == 1
    assert len(saved_records[0]["completed_trades"]) == 1
    assert saved_records[0]["completed_trades"][0]["outcome"] == "MANUAL_CLOSE"
    assert 999123 in closed_pos

    # 3. Test when active trade is cancelled (zero PnL)
    cancel_active = {
        "tracking_started": "2026-10-15",
        "active_trades": {
            "USDCAD": {
                "trade_id": "TEST_USDCAD_01",
                "pair": "USD/CAD",
                "symbol": "USDCAD",
                "direction": "SHORT",
                "entry": 1.38500,
                "stop_loss": 1.38720,
                "take_profit": 1.38170,
                "sl_pips": 22.0,
                "tp_pips": 33.0,
                "status": "PENDING",
                "ctrader_position_id": 999456
            }
        },
        "completed_trades": []
    }
    saved_records.clear()
    closed_pos.clear()
    monkeypatch.setattr(rtb, "load_trade_records", lambda: dict(cancel_active))
    cancel_text, _ = await rtb.get_cancel_payload("USDCAD")
    assert "TRADE CANCELLED" in cancel_text
    assert "USDCAD" in cancel_text
    assert "0.0 pips / 0.00 R (PnL Excluded)" in cancel_text
    assert len(saved_records) == 1
    assert saved_records[0]["completed_trades"][0]["outcome"] == "CANCELLED"
    assert saved_records[0]["completed_trades"][0]["realized_pips"] == 0.0
    assert 999456 in closed_pos
