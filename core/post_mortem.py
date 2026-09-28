"""
Institutional Post-Mortem Diagnostic & Volume-Partitioned Pattern Engine
Tracks, categorizes, and logs winning and losing trade patterns across 100-trade volumes.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("post_mortem")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "patterns"
VOLUMES_DATA_DIR = DATA_DIR / "volumes"
JOURNALS_DIR = BASE_DIR / "journals"
VOLUMES_JOURNAL_DIR = JOURNALS_DIR / "volumes"

VOLUME_SIZE = 100  # Number of trades per volume


def get_volume_for_trade(global_trade_no: int) -> Tuple[int, int, str]:
    """
    Computes volume number (1-indexed), trade number within that volume (1-indexed), and volume id.
    Example:
      trade 1   -> (1, 1, "VOL_01")
      trade 100 -> (1, 100, "VOL_01")
      trade 101 -> (2, 1, "VOL_02")
    """
    if global_trade_no < 1:
        global_trade_no = 1
    volume_no = ((global_trade_no - 1) // VOLUME_SIZE) + 1
    volume_trade_no = ((global_trade_no - 1) % VOLUME_SIZE) + 1
    vol_id = f"VOL_{volume_no:02d}"
    return volume_no, volume_trade_no, vol_id


def determine_trading_session(utc_timestamp_str: str) -> str:
    """Classifies UTC timestamp into Forex session."""
    try:
        dt = datetime.fromisoformat(utc_timestamp_str.replace("Z", "+00:00"))
        hour = dt.hour
        # Forex Sessions (UTC):
        # Asian / Tokyo: 00:00 - 08:00
        # London: 07:00 - 16:00
        # London / NY Overlap: 12:00 - 16:00
        # New York: 12:00 - 21:00
        # Late NY / Rollover: 21:00 - 00:00
        if 12 <= hour < 16:
            return "London/New York Overlap"
        elif 7 <= hour < 12:
            return "London Session"
        elif 16 <= hour < 21:
            return "New York Afternoon"
        elif 0 <= hour < 7:
            return "Asian/Tokyo Session"
        else:
            return "Late NY / Pacific Rollover"
    except Exception:
        return "Standard Market Hours"


def calculate_excursion(
    trade: Dict[str, Any],
    df_bars: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Calculates Maximum Favorable Excursion (MFE) and Maximum Adverse Excursion (MAE).
    MFE: The peak floating profit reached during the life of the position.
    MAE: The deepest floating drawdown experienced during the life of the position.
    """
    entry = float(trade.get("entry", 0.0))
    sl = float(trade.get("stop_loss", 0.0))
    tp = float(trade.get("take_profit", 0.0))
    pip = float(trade.get("pip", 0.0001))
    is_long = (trade.get("direction", "").upper() == "LONG")
    risk_pips = abs(entry - sl) / pip if pip > 0 else 1.0

    mfe_pips = 0.0
    mae_pips = 0.0

    if df_bars is not None and hasattr(df_bars, "itertuples") and not df_bars.empty:
        for row in df_bars.itertuples():
            b_high = float(row.high)
            b_low = float(row.low)

            if is_long:
                favorable = (b_high - entry) / pip
                adverse = (b_low - entry) / pip
            else:
                favorable = (entry - b_low) / pip
                adverse = (entry - b_high) / pip

            if favorable > mfe_pips:
                mfe_pips = favorable
            if adverse < mae_pips:
                mae_pips = adverse
    else:
        # Fallback approximation based on realized outcome
        realized_pips = float(trade.get("realized_pips", 0.0))
        if trade.get("outcome") == "WIN":
            mfe_pips = realized_pips
            mae_pips = -0.2 * abs(realized_pips)
        else:
            mfe_pips = max(0.0, 0.25 * abs(realized_pips))
            mae_pips = realized_pips

    target_pips = abs(tp - entry) / pip if pip > 0 else 1.0
    tp_pct_reached = min(100.0, max(0.0, (mfe_pips / target_pips) * 100)) if target_pips > 0 else 0.0
    mfe_r = mfe_pips / risk_pips if risk_pips > 0 else 0.0
    mae_r = mae_pips / risk_pips if risk_pips > 0 else 0.0

    return {
        "mfe_pips": round(mfe_pips, 1),
        "mfe_r": round(mfe_r, 2),
        "mae_pips": round(mae_pips, 1),
        "mae_r": round(mae_r, 2),
        "tp_distance_pct_reached": round(tp_pct_reached, 1)
    }


def classify_trade_diagnostics(
    trade: Dict[str, Any],
    excursion: Dict[str, Any],
    market_regime: Dict[str, Any]
) -> Dict[str, str]:
    """
    Institutional Rule-Based Diagnostic Classifier:
    Determines the primary mechanical reason why a trade succeeded or failed.
    """
    outcome = trade.get("outcome", "LOSS").upper()
    is_win = (outcome == "WIN")
    mfe_r = excursion.get("mfe_r", 0.0)
    mae_r = excursion.get("mae_r", 0.0)
    tp_pct = excursion.get("tp_distance_pct_reached", 0.0)
    session = market_regime.get("trading_session", "")
    rsi_entry = market_regime.get("rsi_at_entry", 50.0)
    wick_ratio = market_regime.get("breakout_candle_wick_ratio", 0.25)
    duration_bars = trade.get("duration_bars", 1)

    if not is_win:
        # LOSS DIAGNOSTICS
        if tp_pct >= 45.0 or mfe_r >= 0.75:
            return {
                "primary_factor": "PREMATURE_REVERSAL",
                "summary": (
                    f"Position reached +{excursion.get('mfe_pips')} pips (+{mfe_r}R / {tp_pct}% of TP) "
                    "before aggressive counter-trend reversal hit stop-loss."
                ),
                "actionable_insight": (
                    "Incorporate a Breakeven Protection rule once position reaches +0.8R or 50% TP distance."
                )
            }
        elif wick_ratio >= 0.35:
            return {
                "primary_factor": "LIQUIDITY_GRAB_REVERSAL",
                "summary": (
                    f"Breakout candle breached Donchian structure but exhibited high wick rejection "
                    f"({round(wick_ratio * 100)}% shadow). Market absorbed orders and reversed rapidly."
                ),
                "actionable_insight": (
                    "Apply a candle body-to-wick filter (>65% solid body) to prevent entering on rejection wicks."
                )
            }
        elif (trade.get("direction") == "LONG" and rsi_entry >= 68.0) or (trade.get("direction") == "SHORT" and rsi_entry <= 32.0):
            return {
                "primary_factor": "MOMENTUM_EXHAUSTION",
                "summary": (
                    f"Entry occurred with extended RSI ({rsi_entry}). Momentum exhausted immediately "
                    "following breakout bar."
                ),
                "actionable_insight": (
                    "Tighten RSI entry bands from 25–75 to 35–65 to avoid entering at extreme oscillator exhaustions."
                )
            }
        elif "Asian" in session or "Rollover" in session:
            return {
                "primary_factor": "LOW_LIQUIDITY_CHOP",
                "summary": (
                    f"Signal triggered during {session}. Lower institutional volume led to whipsaw "
                    "without sustainable directional continuation."
                ),
                "actionable_insight": (
                    "Restrict or weight signal scoring lower during off-peak liquidity windows."
                )
            }
        else:
            return {
                "primary_factor": "STRUCTURAL_INVALIDATION",
                "summary": (
                    f"Order block level was invalidated by institutional flow after {duration_bars} bar(s). "
                    "Stop-loss executed disciplined capital preservation."
                ),
                "actionable_insight": (
                    "Trade adhered strictly to risk geometry. Invalidation was clean and preserved capital."
                )
            }
    else:
        # WIN DIAGNOSTICS
        if abs(mae_r) <= 0.25:
            return {
                "primary_factor": "CLEAN_MOMENTUM_EXPANSION",
                "summary": (
                    f"Flawless directional expansion with negligible adverse drawdown ({abs(mae_r)}R). "
                    "Institutional order flow propelled price directly to target."
                ),
                "actionable_insight": (
                    "Prime candidate setup for runner scaling or full 1.75R capture."
                )
            }
        elif duration_bars <= 3:
            return {
                "primary_factor": "HIGH_VELOCITY_BREAKOUT",
                "summary": (
                    f"Take-profit hit within {duration_bars} bar(s). High momentum impulse confirmed "
                    "structural breakout conviction."
                ),
                "actionable_insight": (
                    "Validates the 20-period Donchian channel breakout trigger."
                )
            }
        else:
            return {
                "primary_factor": "SUSTAINED_TREND_WAVE",
                "summary": (
                    f"Position navigated natural pullbacks and respected EMA structural support/resistance "
                    f"over {duration_bars} bar(s) to achieve full TP."
                ),
                "actionable_insight": (
                    "Validates patient holding rules and 1:1.75 Risk-to-Reward geometry."
                )
            }


def ensure_directories():
    """Ensures all necessary pattern and volume directories exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VOLUMES_DATA_DIR.mkdir(parents=True, exist_ok=True)
    JOURNALS_DIR.mkdir(parents=True, exist_ok=True)
    VOLUMES_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)


def load_volume_index() -> Dict[str, Any]:
    """Loads or initializes the volume tracker index."""
    ensure_directories()
    index_file = DATA_DIR / "volume_index.json"
    if index_file.exists():
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    default_index = {
        "current_volume_no": 1,
        "current_volume_id": "VOL_01",
        "total_global_trades": 0,
        "total_wins": 0,
        "total_losses": 0,
        "global_win_rate_pct": 0.0,
        "volumes": {
            "VOL_01": {
                "volume_no": 1,
                "label": "Volume 1 (Trades 1–100)",
                "trade_count": 0,
                "wins": 0,
                "losses": 0,
                "win_rate_pct": 0.0,
                "status": "IN_PROGRESS"
            }
        }
    }
    save_volume_index(default_index)
    return default_index


def save_volume_index(index: Dict[str, Any]):
    """Persists volume index to disk."""
    ensure_directories()
    index_file = DATA_DIR / "volume_index.json"
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def record_trade_post_mortem(
    trade: Dict[str, Any],
    df_bars: Optional[Any] = None,
    custom_regime: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Main Entrypoint:
    Enriches a closed trade with MFE/MAE excursions, regime context, and causal diagnostics.
    Assigns volume tracking and saves to volume-segregated datasets and markdown journals.
    """
    ensure_directories()
    vol_index = load_volume_index()

    # Determine global trade number
    existing_global = vol_index.get("total_global_trades", 0)
    global_trade_no = existing_global + 1

    vol_no, vol_trade_no, vol_id = get_volume_for_trade(global_trade_no)
    vol_folder = VOLUMES_DATA_DIR / f"vol_{vol_no:02d}"
    vol_folder.mkdir(parents=True, exist_ok=True)

    # 1. Calculate Excursion (MFE / MAE)
    excursion = calculate_excursion(trade, df_bars)

    # 2. Derive Market Regime
    open_time = trade.get("opened_at", datetime.now(timezone.utc).isoformat())
    session = determine_trading_session(open_time)

    # Calculate holding duration
    closed_time = trade.get("closed_at", datetime.now(timezone.utc).isoformat())
    duration_hours = 1.0
    duration_bars = 1
    try:
        t_open = datetime.fromisoformat(open_time.replace("Z", "+00:00"))
        t_close = datetime.fromisoformat(closed_time.replace("Z", "+00:00"))
        diff_sec = (t_close - t_open).total_seconds()
        duration_hours = round(max(0.1, diff_sec / 3600.0), 2)
        duration_bars = max(1, int(round(duration_hours)))
    except Exception:
        pass

    market_regime = {
        "trading_session": session,
        "rsi_at_entry": trade.get("rsi", 50.0),
        "atr_14": trade.get("atr", 0.0015),
        "volatility_regime": "NORMAL",
        "ema_alignment": "BULLISH_EXPANDING" if trade.get("direction") == "LONG" else "BEARISH_EXPANDING",
        "breakout_candle_wick_ratio": 0.28
    }
    if custom_regime:
        market_regime.update(custom_regime)

    # 3. Classify Diagnostics
    diagnostic = classify_trade_diagnostics(trade, excursion, market_regime)

    # 4. Construct Full Enriched Record
    enriched_record = {
        "tracking": {
            "global_trade_no": global_trade_no,
            "volume_no": vol_no,
            "volume_trade_no": vol_trade_no,
            "volume_id": vol_id,
            "volume_label": f"Volume {vol_no} (Trades {(vol_no-1)*VOLUME_SIZE + 1}–{vol_no*VOLUME_SIZE})"
        },
        "trade_id": trade.get("trade_id", f"{trade.get('symbol')}_{global_trade_no}"),
        "pair": trade.get("pair") or trade.get("symbol"),
        "symbol": trade.get("symbol"),
        "timeframe": trade.get("timeframe", "1H"),
        "direction": trade.get("direction", "LONG"),
        "entry_price": float(trade.get("entry", 0.0)),
        "exit_price": float(trade.get("exit_price", 0.0)),
        "stop_loss": float(trade.get("stop_loss", 0.0)),
        "take_profit": float(trade.get("take_profit", 0.0)),
        "opened_at": open_time,
        "closed_at": closed_time,
        "duration_hours": duration_hours,
        "duration_bars": duration_bars,
        "outcome": trade.get("outcome", "LOSS"),
        "realized_pips": float(trade.get("realized_pips", 0.0)),
        "realized_r": float(trade.get("realized_r", 0.0)),
        "excursion_metrics": excursion,
        "market_regime": market_regime,
        "diagnostic": diagnostic
    }

    is_win = (enriched_record["outcome"] == "WIN")

    # 5. Save into Volume-Segregated JSON Files
    target_vol_file = vol_folder / ("winning_trades.json" if is_win else "losing_trades.json")
    vol_trades = []
    if target_vol_file.exists():
        try:
            with open(target_vol_file, "r", encoding="utf-8") as f:
                vol_trades = json.load(f)
        except Exception:
            vol_trades = []
    vol_trades.append(enriched_record)
    with open(target_vol_file, "w", encoding="utf-8") as f:
        json.dump(vol_trades, f, indent=2)

    # 6. Save into Master Cumulative JSON Files
    master_file = DATA_DIR / ("master_winning_trades.json" if is_win else "master_losing_trades.json")
    master_trades = []
    if master_file.exists():
        try:
            with open(master_file, "r", encoding="utf-8") as f:
                master_trades = json.load(f)
        except Exception:
            master_trades = []
    master_trades.append(enriched_record)
    with open(master_file, "w", encoding="utf-8") as f:
        json.dump(master_trades, f, indent=2)

    # 7. Update Volume Summary & Index
    update_volume_summary(vol_no, vol_id, enriched_record)

    # 8. Append Narrative Case Study into Markdown Journals
    append_markdown_journal(enriched_record)
    update_benchmarks_markdown()

    logger.info(
        f"==> Post-Mortem Saved: Global #{global_trade_no} ({vol_id} #{vol_trade_no}) | "
        f"{enriched_record['pair']} {enriched_record['outcome']} | Factor: {diagnostic['primary_factor']}"
    )

    return enriched_record


def update_volume_summary(vol_no: int, vol_id: str, latest_record: Dict[str, Any]):
    """Calculates and updates aggregate metrics for the given volume."""
    vol_folder = VOLUMES_DATA_DIR / f"vol_{vol_no:02d}"
    wins_file = vol_folder / "winning_trades.json"
    losses_file = vol_folder / "losing_trades.json"

    wins = []
    losses = []
    if wins_file.exists():
        try:
            with open(wins_file, "r", encoding="utf-8") as f:
                wins = json.load(f)
        except Exception:
            pass
    if losses_file.exists():
        try:
            with open(losses_file, "r", encoding="utf-8") as f:
                losses = json.load(f)
        except Exception:
            pass

    total = len(wins) + len(losses)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = round((win_count / total * 100), 1) if total > 0 else 0.0

    net_pips = sum(t.get("realized_pips", 0.0) for t in wins + losses)
    net_r = sum(t.get("realized_r", 0.0) for t in wins + losses)

    gross_win_pips = sum(t.get("realized_pips", 0.0) for t in wins)
    gross_loss_pips = abs(sum(t.get("realized_pips", 0.0) for t in losses))
    pf = round(gross_win_pips / gross_loss_pips, 2) if gross_loss_pips > 0 else (99.0 if gross_win_pips > 0 else 0.0)

    # Frequency of failure reasons
    loss_factors = {}
    for l in losses:
        factor = l.get("diagnostic", {}).get("primary_factor", "UNKNOWN")
        loss_factors[factor] = loss_factors.get(factor, 0) + 1

    # Frequency of win reasons
    win_factors = {}
    for w in wins:
        factor = w.get("diagnostic", {}).get("primary_factor", "UNKNOWN")
        win_factors[factor] = win_factors.get(factor, 0) + 1

    avg_loss_mfe_pips = 0.0
    if losses:
        avg_loss_mfe_pips = round(sum(l.get("excursion_metrics", {}).get("mfe_pips", 0.0) for l in losses) / len(losses), 1)

    summary = {
        "volume_no": vol_no,
        "volume_id": vol_id,
        "trade_count": total,
        "capacity": VOLUME_SIZE,
        "status": "COMPLETED" if total >= VOLUME_SIZE else "IN_PROGRESS",
        "wins": win_count,
        "losses": loss_count,
        "win_rate_pct": win_rate,
        "net_pips": round(net_pips, 1),
        "net_r": round(net_r, 2),
        "profit_factor": pf,
        "average_loss_mfe_pips": avg_loss_mfe_pips,
        "top_loss_factors": loss_factors,
        "top_win_factors": win_factors,
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    summary_file = vol_folder / "volume_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Update index
    vol_index = load_volume_index()
    vol_index["total_global_trades"] = latest_record["tracking"]["global_trade_no"]
    vol_index["current_volume_no"] = vol_no
    vol_index["current_volume_id"] = vol_id
    vol_index.setdefault("volumes", {})[vol_id] = {
        "volume_no": vol_no,
        "label": f"Volume {vol_no} (Trades {(vol_no-1)*VOLUME_SIZE + 1}–{vol_no*VOLUME_SIZE})",
        "trade_count": total,
        "wins": win_count,
        "losses": loss_count,
        "win_rate_pct": win_rate,
        "status": summary["status"]
    }

    # Calculate global win rate
    all_wins = sum(v.get("wins", 0) for v in vol_index["volumes"].values())
    all_losses = sum(v.get("losses", 0) for v in vol_index["volumes"].values())
    all_trades = all_wins + all_losses
    vol_index["total_wins"] = all_wins
    vol_index["total_losses"] = all_losses
    vol_index["global_win_rate_pct"] = round((all_wins / all_trades * 100), 1) if all_trades > 0 else 0.0

    save_volume_index(vol_index)


def append_markdown_journal(record: Dict[str, Any]):
    """Appends clean, professional Markdown case study into the volume journal."""
    vol_no = record["tracking"]["volume_no"]
    journal_path = VOLUMES_JOURNAL_DIR / f"VOLUME_{vol_no:02d}_PATTERNS.md"

    is_win = (record["outcome"] == "WIN")
    badge = "🎯 WIN (+1.75R)" if is_win else "🛑 LOSS (-1.00R)"
    sign = "+" if record["realized_pips"] >= 0 else ""
    ex = record["excursion_metrics"]
    diag = record["diagnostic"]
    regime = record["market_regime"]
    open_str = record["opened_at"].replace("T", " ").replace("Z", " UTC")
    close_str = record["closed_at"].replace("T", " ").replace("Z", " UTC")

    # If file doesn't exist, create header
    if not journal_path.exists():
        header = (
            f"# Trade Pattern Journal · Volume {vol_no:02d}\n\n"
            f"> **Volume Capacity**: Trades {(vol_no-1)*VOLUME_SIZE + 1} to {vol_no*VOLUME_SIZE}\n"
            f"> **Purpose**: Systematic post-mortem documentation to analyze failure modes, win factors, "
            f"and optimize execution rules across 100-trade blocks.\n\n"
            f"---\n\n"
        )
        with open(journal_path, "w", encoding="utf-8") as f:
            f.write(header)

    entry_md = (
        f"### #{record['tracking']['volume_trade_no']} · {record['pair']} ({record['timeframe']}) — {badge}\n\n"
        f"- **Global Sequence**: Trade `#{record['tracking']['global_trade_no']}`\n"
        f"- **Direction**: `{record['direction']}` | **Outcome**: `{record['outcome']}` (`{sign}{record['realized_pips']} pips` / `{record['realized_r']}R`)\n"
        f"- **Execution Range**: Entry ` {record['entry_price']} ` ➔ Exit ` {record['exit_price']} `\n"
        f"- **Targets**: Stop Loss ` {record['stop_loss']} ` | Take Profit ` {record['take_profit']} `\n"
        f"- **Holding Time**: `{record['duration_hours']} hours` ({record['duration_bars']} bars)\n"
        f"- **Window**: `{open_str}` ➔ `{close_str}`\n\n"
        f"#### 📊 Excursion & Market Regime\n"
        f"| Metric | Value | Detail |\n"
        f"| :--- | :--- | :--- |\n"
        f"| **Max Favorable Excursion (MFE)** | `+{ex['mfe_pips']} pips` | Reached `+{ex['mfe_r']}R` ({ex['tp_distance_pct_reached']}% of TP) |\n"
        f"| **Max Adverse Excursion (MAE)** | `{ex['mae_pips']} pips` | Deepest drawdown `{ex['mae_r']}R` |\n"
        f"| **Session** | `{regime['trading_session']}` | Institutional Market Timing |\n"
        f"| **Entry RSI (14)** | `{regime['rsi_at_entry']}` | Momentum Baseline |\n"
        f"| **EMA Alignment** | `{regime['ema_alignment']}` | Structural Trend Bias |\n\n"
        f"#### 🔬 Post-Mortem Diagnosis: `{diag['primary_factor']}`\n"
        f"> **Analysis**: {diag['summary']}\n>\n"
        f"> **Actionable Takeaway**: {diag['actionable_insight']}\n\n"
        f"---\n\n"
    )

    with open(journal_path, "a", encoding="utf-8") as f:
        f.write(entry_md)


def update_benchmarks_markdown():
    """Generates and updates the master comparative benchmarks Markdown table."""
    vol_index = load_volume_index()
    benchmarks_path = JOURNALS_DIR / "VOLUME_BENCHMARKS.md"

    table_rows = []
    for vol_id, v in vol_index.get("volumes", {}).items():
        vol_no = v.get("volume_no", 1)
        summary_file = VOLUMES_DATA_DIR / f"vol_{vol_no:02d}" / "volume_summary.json"
        net_pips = "0.0"
        net_r = "0.00"
        pf = "N/A"
        avg_loss_mfe = "N/A"
        top_factor = "N/A"

        if summary_file.exists():
            try:
                with open(summary_file, "r", encoding="utf-8") as f:
                    s = json.load(f)
                    net_pips = f"{'+' if s.get('net_pips', 0) >= 0 else ''}{s.get('net_pips', 0.0)}p"
                    net_r = f"{'+' if s.get('net_r', 0) >= 0 else ''}{s.get('net_r', 0.00)}R"
                    pf = str(s.get("profit_factor", "N/A"))
                    avg_loss_mfe = f"+{s.get('average_loss_mfe_pips', 0.0)}p"
                    losses_f = s.get("top_loss_factors", {})
                    if losses_f:
                        top_factor = max(losses_f.items(), key=lambda x: x[1])[0]
            except Exception:
                pass

        table_rows.append(
            f"| **Volume {vol_no:02d}** | #{ (vol_no-1)*VOLUME_SIZE + 1 } – #{ vol_no*VOLUME_SIZE } | "
            f"`{v.get('trade_count', 0)}/{VOLUME_SIZE}` | **{v.get('win_rate_pct', 0.0)}%** | "
            f"`{net_pips}` | `{net_r}` | `{pf}` | `{avg_loss_mfe}` | `{top_factor}` | `{v.get('status')}` |"
        )

    content = (
        f"# Cross-Volume Strategy Benchmarks\n\n"
        f"Comparative analytics evaluating performance across sequential 100-trade volumes to measure strategy improvements.\n\n"
        f"- **Global Trades Evaluated**: `{vol_index.get('total_global_trades', 0)}`\n"
        f"- **Global Win Rate**: `{vol_index.get('global_win_rate_pct', 0.0)}%` ({vol_index.get('total_wins', 0)} Wins / {vol_index.get('total_losses', 0)} Losses)\n"
        f"- **Active Volume**: `{vol_index.get('current_volume_id', 'VOL_01')}`\n\n"
        f"### 📈 Comparative Volume Benchmark Table\n\n"
        f"| Volume | Range | Completed | Win Rate | Net Pips | Net R | Profit Factor | Avg Loss MFE | Top Failure Mode | Status |\n"
        f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
        + "\n".join(table_rows) + "\n\n"
        f"---\n\n"
        f"### 🔍 Continuous Refinement Protocol\n"
        f"1. **Volume 1 (Baseline)**: Trades #1 to #100 establish institutional forward benchmarks with zero curve-fitting.\n"
        f"2. **Volume Transition Protocol**: Upon completing each 100-trade volume, the distribution of loss causes and MFE is analyzed to calibrate parameters (e.g. wick-ratio filtering, dynamic trailing stop triggers).\n"
        f"3. **Version Benchmarking**: Successive volumes must demonstrate progressive improvement in Profit Factor and Loss MFE reduction.\n"
    )

    with open(benchmarks_path, "w", encoding="utf-8") as f:
        f.write(content)
