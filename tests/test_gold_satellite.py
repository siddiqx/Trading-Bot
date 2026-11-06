"""Comprehensive Unit Test Suite for the Isolated Gold Satellite Engine.

Tests:
1. Gold Commodity Contract Math ($100/point per lot) and Position Sizing.
2. Conservative Lot-Step Flooring and Zero-Budget Breaching.
3. Rollover Blackout Window (20:30 - 22:30 UTC).
4. Friday 16:00 UTC Weekend Cutoff Protection.
5. Cross-Engine Correlation Interlock (Enforces Max 2 net USD exposure).
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path

from satellite.gold_config import (
    POINT_VALUE_PER_LOT,
    MIN_LOT,
    LOT_STEP,
    MAX_CONCURRENT_USD_EXPOSURE,
)
from satellite.gold_validator import (
    calculate_gold_position_size,
    is_rollover_blackout_active,
    is_friday_weekend_cutoff,
    check_correlation_interlock,
    get_gold_usd_bias,
)


class TestGoldPositionSizing:
    """Verifies commodity contract specifications and sizing safety."""

    def test_standard_sizing(self):
        # $5,000 equity, 0.5% risk ($25.00 budget), 25.0 point stop
        # Cost per lot = 25.0 * 100 = $2,500. Raw lots = 25 / 2500 = 0.01
        lots, risk_usd = calculate_gold_position_size(
            account_equity=5000.0,
            risk_pct=0.50,
            sl_points=25.0
        )
        assert lots == 0.01
        assert risk_usd == 25.00

    def test_larger_account_sizing(self):
        # $20,000 equity, 1.0% risk ($200.00 budget), 20.0 point stop
        # Cost per lot = 20.0 * 100 = $2,000. Raw lots = 200 / 2000 = 0.10
        lots, risk_usd = calculate_gold_position_size(
            account_equity=20000.0,
            risk_pct=1.0,
            sl_points=20.0
        )
        assert lots == 0.10
        assert risk_usd == 200.00

    def test_lot_flooring_precision(self):
        # Raw lots = 0.0278 -> floored to 0.02
        lots, risk_usd = calculate_gold_position_size(
            account_equity=5000.0,
            risk_pct=1.0, # $50 budget
            sl_points=18.0 # cost per lot = $1,800. Raw = 50 / 1800 = 0.02777...
        )
        assert lots == 0.02
        assert risk_usd == pytest.approx(36.00)

    def test_zero_budget_breach_rejection(self):
        # Very small account ($1,000) with 0.5% risk ($5 budget) and 30 point stop.
        # Min lot (0.01) risks 0.01 * 100 * 30 = $30.00.
        # $30.00 is 6.0x the $5 budget (exceeds 1.5x ceiling) -> should safely return 0.0
        lots, risk_usd = calculate_gold_position_size(
            account_equity=1000.0,
            risk_pct=0.50,
            sl_points=30.0
        )
        assert lots == 0.0
        assert risk_usd == 0.0

    def test_invalid_arguments_raise_error(self):
        with pytest.raises(ValueError):
            calculate_gold_position_size(account_equity=-5000.0, risk_pct=0.50, sl_points=25.0)
        with pytest.raises(ValueError):
            calculate_gold_position_size(account_equity=5000.0, risk_pct=-0.50, sl_points=25.0)
        with pytest.raises(ValueError):
            calculate_gold_position_size(account_equity=5000.0, risk_pct=0.50, sl_points=0.0)


class TestRolloverBlackout:
    """Verifies that trading is suppressed during the illiquid 20:30 - 22:30 UTC rollover window."""

    def test_inside_blackout(self):
        t1 = datetime(2026, 11, 5, 20, 30, tzinfo=timezone.utc)
        t2 = datetime(2026, 11, 5, 21, 15, tzinfo=timezone.utc)
        t3 = datetime(2026, 11, 5, 22, 30, tzinfo=timezone.utc)
        assert is_rollover_blackout_active(t1) is True
        assert is_rollover_blackout_active(t2) is True
        assert is_rollover_blackout_active(t3) is True

    def test_outside_blackout(self):
        t1 = datetime(2026, 11, 5, 20, 29, tzinfo=timezone.utc)
        t2 = datetime(2026, 11, 5, 22, 31, tzinfo=timezone.utc)
        t3 = datetime(2026, 11, 5, 14, 0, tzinfo=timezone.utc)
        assert is_rollover_blackout_active(t1) is False
        assert is_rollover_blackout_active(t2) is False
        assert is_rollover_blackout_active(t3) is False


class TestWeekendCutoff:
    """Verifies that Gold positions are flat before the weekend to avoid Sunday gaps."""

    def test_friday_after_cutoff(self):
        # 2026-11-06 is Friday
        fri_late = datetime(2026, 11, 6, 16, 30, tzinfo=timezone.utc)
        assert is_friday_weekend_cutoff(fri_late) is True

    def test_friday_before_cutoff(self):
        fri_early = datetime(2026, 11, 6, 14, 0, tzinfo=timezone.utc)
        assert is_friday_weekend_cutoff(fri_early) is False

    def test_saturday_and_sunday(self):
        sat = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
        sun_early = datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc)
        sun_open = datetime(2026, 11, 8, 22, 0, tzinfo=timezone.utc)
        assert is_friday_weekend_cutoff(sat) is True
        assert is_friday_weekend_cutoff(sun_early) is True
        assert is_friday_weekend_cutoff(sun_open) is False


class TestCorrelationInterlock:
    """Verifies that the cross-engine interlock prevents exceeding Max 2 net USD exposure."""

    def test_gold_usd_bias_mapping(self):
        assert get_gold_usd_bias("LONG") == -1   # Buy Gold / Sell USD = Short USD
        assert get_gold_usd_bias("BUY") == -1
        assert get_gold_usd_bias("SHORT") == 1   # Sell Gold / Buy USD = Long USD
        assert get_gold_usd_bias("SELL") == 1
        with pytest.raises(ValueError):
            get_gold_usd_bias("FLAT")

    def test_interlock_approved_when_no_active_forex(self, tmp_path):
        ledger = tmp_path / "trade_records.json"
        ledger.write_text(json.dumps({"active_trades": {}}), encoding="utf-8")

        approved, msg, count = check_correlation_interlock("LONG", forex_records_path=ledger)
        assert approved is True
        assert count == 0

    def test_interlock_rejected_when_two_same_bias_exist(self, tmp_path):
        # Setup Forex ledger with 2 Short USD trades:
        # Long EURUSD (Short USD = -1)
        # Short USDCAD (Short USD = -1)
        ledger = tmp_path / "trade_records.json"
        mock_active = {
            "T1": {"symbol": "EURUSD", "direction": "LONG"},
            "T2": {"symbol": "USDCAD", "direction": "SHORT"},
        }
        ledger.write_text(json.dumps({"active_trades": mock_active}), encoding="utf-8")

        # Prospective LONG Gold is ALSO Short USD (-1) -> must be REJECTED!
        approved, msg, count = check_correlation_interlock("LONG", forex_records_path=ledger)
        assert approved is False
        assert count == 2
        assert "Correlation Interlock REJECTED" in msg

        # Prospective SHORT Gold is Long USD (+1) -> must be APPROVED!
        approved, msg, count = check_correlation_interlock("SHORT", forex_records_path=ledger)
        assert approved is True
        assert count == 0
        assert "Correlation Interlock APPROVED" in msg

    def test_interlock_approved_when_one_same_bias_exists(self, tmp_path):
        # 1 Short USD trade open
        ledger = tmp_path / "trade_records.json"
        mock_active = {
            "T1": {"symbol": "EURUSD", "direction": "LONG"},
            "T2": {"symbol": "USDJPY", "direction": "LONG"}, # Long USD
        }
        ledger.write_text(json.dumps({"active_trades": mock_active}), encoding="utf-8")

        # LONG Gold is Short USD -> 1 active exists, max is 2 -> APPROVED
        approved, msg, count = check_correlation_interlock("LONG", forex_records_path=ledger)
        assert approved is True
        assert count == 1

    def test_interlock_handles_broker_prefixes(self, tmp_path):
        ledger = tmp_path / "trade_records.json"
        mock_active = {
            "T1": {"symbol": "OANDA:EUR_USD", "direction": "BUY"},
            "T2": {"symbol": "FX:USDCAD=X", "direction": "SELL"},
        }
        ledger.write_text(json.dumps({"active_trades": mock_active}), encoding="utf-8")

        # Both are Short USD (-1) -> Long Gold must be rejected
        approved, msg, count = check_correlation_interlock("LONG", forex_records_path=ledger)
        assert approved is False
        assert count == 2


class TestGoldActiveTradeLifecycle:
    """Verifies that active Gold trade exits correctly compute friction and PnL."""

    def test_weekend_flat_exit_sets_friction(self, monkeypatch, tmp_path):
        from satellite.market_scanner_gold import check_active_gold_trades
        import pandas as pd

        # Mock Friday 17:00 UTC
        fri_1700 = datetime(2026, 11, 6, 17, 0, tzinfo=timezone.utc)
        records = {
            "active_trades": {
                "GOLD_001": {
                    "symbol": "XAUUSD",
                    "direction": "LONG",
                    "entry_price": 4100.0,
                    "current_sl_price": 4075.0,
                    "current_tp_price": 4137.5,
                    "init_sl_points": 25.0,
                    "lots": 0.01,
                    "monetary_risk_usd": 25.0,
                    "entry_time": "2026-11-06T14:00:00+00:00",
                }
            },
            "completed_trades": [],
            "daily_losses": {}
        }
        cur_bar = pd.Series({"open": 4110.0, "high": 4115.0, "low": 4108.0, "close": 4112.0})

        # Monkeypatch is_friday_weekend_cutoff to return True
        monkeypatch.setattr("satellite.market_scanner_gold.is_friday_weekend_cutoff", lambda dt: True)
        monkeypatch.setattr("satellite.market_scanner_gold.send_telegram_alert", lambda txt: True)

        check_active_gold_trades(records, cur_bar, records_path=tmp_path / "mock_gold_records.json")

        assert len(records["active_trades"]) == 0
        assert len(records["completed_trades"]) == 1
        closed = records["completed_trades"][0]
        assert closed["reason"] == "WEEKEND_FLAT"
        assert "friction" in closed
        assert closed["friction"] == pytest.approx(0.36) # 0.01 lot = 1 oz * $0.36 = $0.36
        assert closed["net_pnl"] == pytest.approx(12.0 - 0.36) # ($4112 - $4100) * 1 oz - 0.36 = $11.64

    def test_post_loss_cooldown_active_and_expired(self):
        from satellite.market_scanner_gold import check_gold_loss_cooldown

        # No completed trades -> cooldown False
        assert check_gold_loss_cooldown({"completed_trades": []}) == (False, 0.0)

        # Recent winning trade -> cooldown False
        win_records = {
            "completed_trades": [{
                "net_pnl": 35.0,
                "exit_time": datetime.now(timezone.utc).isoformat()
            }]
        }
        assert check_gold_loss_cooldown(win_records) == (False, 0.0)

        # Recent loss trade (5 minutes ago) -> cooldown True
        recent_loss_records = {
            "completed_trades": [{
                "net_pnl": -25.0,
                "exit_time": datetime.now(timezone.utc).isoformat()
            }]
        }
        in_cd, rem = check_gold_loss_cooldown(recent_loss_records, cooldown_minutes=60.0)
        assert in_cd is True
        assert 58.0 <= rem <= 60.0

        # Old loss trade (120 minutes ago) -> cooldown False
        from datetime import timedelta
        old_loss_records = {
            "completed_trades": [{
                "net_pnl": -25.0,
                "exit_time": (datetime.now(timezone.utc) - timedelta(minutes=120)).isoformat()
            }]
        }
        in_cd_old, rem_old = check_gold_loss_cooldown(old_loss_records, cooldown_minutes=60.0)
        assert in_cd_old is False
        assert rem_old == 0.0


