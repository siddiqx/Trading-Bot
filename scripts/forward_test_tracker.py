#!/usr/bin/env python3
"""
Forward-Test Out-of-Sample Validation Tracker
============================================
Compares the frozen New System (v2.0-Frozen) against the Old Baseline (v1.0 Baseline)
across the exact forensic validation metrics table.

Tracking Focus:
  1. Side-by-side performance metrics (WR, Expectancy, PF, Max DD, MFE, MAE, Costs).
  2. Granular MFE tracking on every losing trade to evaluate the +1.0R Break-Even mechanism:
     - Are large-MFE losers (>1.0R) successfully converted to BE / 0.0R?
     - Are eventual winners being prematurely cut off by the BE threshold?
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

# Ensure clean UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Root directory of the trading bot
ROOT_DIR = Path(__file__).resolve().parent.parent
TRADE_RECORDS_FILE = ROOT_DIR / "trade_records.json"
HISTORICAL_SIM_FILE = ROOT_DIR / "data" / "audit_summary_metrics.json"

# Strategy freeze timestamp: all trades opened on or after this timestamp belong to the New System
FREEZE_TIMESTAMP = "2026-10-02T10:35:00Z"

# Benchmark Old Baseline Metrics (computed across 235 historical trades, v1.0)
OLD_BASELINE = {
    "system_name": "Old Baseline (v1.0 Hybrid)",
    "trades": 235,
    "wins": 109,
    "losses": 126,
    "be_exits": 0,
    "win_rate_pct": 46.38,
    "avg_win_r": 1.216,
    "avg_loss_r": -0.845,
    "expectancy_r": 0.111,
    "profit_factor": 1.24,
    "max_dd_r": 15.96,
    "avg_mfe_r": 1.04,
    "median_mfe_win": 1.78,
    "median_mfe_loss": 0.38,
    "avg_mae_r": -0.80,
    "plus1_before_minus1_pct": 45.96,
    "tp_reached_pct": 26.38,
    "be_triggered": 0,
    "be_triggered_pct": 0.0,
    "be_exits_pct": 0.0,
    "avg_tp_distance_r": 1.75,
    "est_cost_per_trade_r": 0.119,
    "net_expectancy_r": -0.008,
}


def load_trade_records(file_path: Path = TRADE_RECORDS_FILE) -> Dict[str, Any]:
    """Loads trade records from JSON file."""
    if not file_path.exists():
        return {"completed_trades": [], "active_trades": {}}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading trade records from {file_path}: {e}", file=sys.stderr)
        return {"completed_trades": [], "active_trades": {}}


def parse_timestamp(ts_str: Optional[str]) -> Optional[datetime]:
    """Parses ISO timestamp string into UTC datetime object."""
    if not ts_str:
        return None
    try:
        clean_str = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def calculate_metrics(trades: List[Dict[str, Any]], cost_per_trade_r: float = 0.10) -> Dict[str, Any]:
    """
    Computes rigorous systematic trading metrics from a list of completed trade records.
    """
    if not trades:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "be_exits": 0,
            "win_rate_pct": 0.0,
            "avg_win_r": 0.0,
            "avg_loss_r": 0.0,
            "expectancy_r": 0.0,
            "profit_factor": 0.0,
            "max_dd_r": 0.0,
            "avg_mfe_r": 0.0,
            "median_mfe_win": 0.0,
            "median_mfe_loss": 0.0,
            "avg_mae_r": 0.0,
            "plus1_before_minus1_pct": 0.0,
            "tp_reached_pct": 0.0,
            "be_triggered": 0,
            "be_triggered_pct": 0.0,
            "be_exits_pct": 0.0,
            "avg_tp_distance_r": 0.0,
            "est_cost_per_trade_r": cost_per_trade_r,
            "net_expectancy_r": -cost_per_trade_r,
        }

    n = len(trades)
    wins = [t for t in trades if t.get("outcome") == "WIN"]
    losses = [t for t in trades if t.get("outcome") == "LOSS"]
    be_trades = [t for t in trades if t.get("outcome") in ("BREAK_EVEN", "BE")]

    n_wins = len(wins)
    n_losses = len(losses)
    n_be = len(be_trades)

    # Win rate: standard definition is wins / total trades
    win_rate_pct = (n_wins / n * 100.0) if n > 0 else 0.0

    # R metrics
    win_r_list = [t.get("realized_r", 0.0) for t in wins]
    loss_r_list = [t.get("realized_r", 0.0) for t in losses]
    all_r_list = [t.get("realized_r", 0.0) for t in trades]

    avg_win_r = (sum(win_r_list) / n_wins) if n_wins > 0 else 0.0
    avg_loss_r = (sum(loss_r_list) / n_losses) if n_losses > 0 else 0.0
    expectancy_r = sum(all_r_list) / n if n > 0 else 0.0

    total_win_r = sum(win_r_list)
    total_loss_r = abs(sum(loss_r_list))
    profit_factor = (total_win_r / total_loss_r) if total_loss_r > 0 else (999.0 if total_win_r > 0 else 0.0)

    # Max Drawdown in R
    cum_r = 0.0
    peak_r = 0.0
    max_dd_r = 0.0
    for r in all_r_list:
        cum_r += r
        if cum_r > peak_r:
            peak_r = cum_r
        dd = peak_r - cum_r
        if dd > max_dd_r:
            max_dd_r = dd

    # Excursion (MFE / MAE)
    mfe_list = [t.get("mfe_r", t.get("realized_r", 0.0)) for t in trades]
    mae_list = [t.get("mae_r", -1.0 if t.get("outcome") == "LOSS" else 0.0) for t in trades]
    avg_mfe_r = (sum(mfe_list) / n) if n > 0 else 0.0
    avg_mae_r = (sum(mae_list) / n) if n > 0 else 0.0

    win_mfe_list = [t.get("mfe_r", t.get("realized_r", 0.0)) for t in wins]
    loss_mfe_list = [t.get("mfe_r", 0.0) for t in losses]

    import statistics
    median_mfe_win = statistics.median(win_mfe_list) if win_mfe_list else 0.0
    median_mfe_loss = statistics.median(loss_mfe_list) if loss_mfe_list else 0.0

    # Path milestones
    plus1_count = sum(1 for t in trades if t.get("mfe_r", 0.0) >= 1.0 or t.get("hit_100r") or t.get("be_active"))
    plus1_pct = (plus1_count / n * 100.0) if n > 0 else 0.0

    tp_count = sum(1 for t in trades if t.get("outcome") == "WIN" or t.get("hit_175r") or t.get("hit_tp"))
    tp_pct = (tp_count / n * 100.0) if n > 0 else 0.0

    be_triggered_count = sum(1 for t in trades if t.get("be_active") or t.get("outcome") in ("BREAK_EVEN", "BE"))
    be_triggered_pct = (be_triggered_count / n * 100.0) if n > 0 else 0.0
    be_exits_pct = (n_be / n * 100.0) if n > 0 else 0.0

    # Target distance
    tp_dist_list = [t.get("target_rr", t.get("rr", 1.75)) for t in trades]
    avg_tp_distance_r = (sum(tp_dist_list) / n) if n > 0 else 1.75

    net_expectancy_r = expectancy_r - cost_per_trade_r

    return {
        "trades": n,
        "wins": n_wins,
        "losses": n_losses,
        "be_exits": n_be,
        "win_rate_pct": round(win_rate_pct, 2),
        "avg_win_r": round(avg_win_r, 3),
        "avg_loss_r": round(avg_loss_r, 3),
        "expectancy_r": round(expectancy_r, 3),
        "profit_factor": round(profit_factor, 2),
        "max_dd_r": round(max_dd_r, 2),
        "avg_mfe_r": round(avg_mfe_r, 2),
        "median_mfe_win": round(median_mfe_win, 2),
        "median_mfe_loss": round(median_mfe_loss, 2),
        "avg_mae_r": round(avg_mae_r, 2),
        "plus1_before_minus1_pct": round(plus1_pct, 2),
        "tp_reached_pct": round(tp_pct, 2),
        "be_triggered": be_triggered_count,
        "be_triggered_pct": round(be_triggered_pct, 2),
        "be_exits_pct": round(be_exits_pct, 2),
        "avg_tp_distance_r": round(avg_tp_distance_r, 2),
        "est_cost_per_trade_r": round(cost_per_trade_r, 3),
        "net_expectancy_r": round(net_expectancy_r, 3),
    }


def analyze_losing_mfe(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Performs critical loss MFE analysis to evaluate the +1.0R Break-Even mechanism.
    Categorizes losses by Maximum Favorable Excursion (MFE):
      - Large MFE (>= 1.0R): Leakage where price reached target zone but ended in loss.
      - Moderate MFE (0.50R - 0.99R): Directional follow-through before reversal.
      - Small MFE (0.25R - 0.49R): Timing whipsaw.
      - Immediate Failure (< 0.25R): Order block failed immediately.
    """
    losses = [t for t in trades if t.get("outcome") == "LOSS"]
    be_exits = [t for t in trades if t.get("outcome") in ("BREAK_EVEN", "BE")]

    large_mfe_losses = []     # MFE >= 1.0R
    moderate_mfe_losses = []  # 0.50R <= MFE < 1.0R
    timing_whipsaws = []      # 0.25R <= MFE < 0.50R
    immediate_failures = []   # MFE < 0.25R

    for t in losses:
        mfe = t.get("mfe_r", 0.0)
        rec = {
            "trade_id": t.get("trade_id", "N/A"),
            "pair": t.get("pair") or t.get("symbol", "N/A"),
            "timeframe": t.get("timeframe", "N/A"),
            "direction": t.get("direction", "N/A"),
            "opened_at": t.get("opened_at", "N/A"),
            "mfe_r": round(mfe, 2),
            "mfe_pips": t.get("mfe_pips", 0.0),
            "realized_r": round(t.get("realized_r", -1.0), 2),
            "realized_pips": t.get("realized_pips", 0.0),
            "exit_reason": t.get("exit_reason", "SL_HIT"),
        }
        if mfe >= 1.0:
            large_mfe_losses.append(rec)
        elif mfe >= 0.50:
            moderate_mfe_losses.append(rec)
        elif mfe >= 0.25:
            timing_whipsaws.append(rec)
        else:
            immediate_failures.append(rec)

    # Analyze Break-Even trades
    be_analysis = []
    for t in be_exits:
        be_analysis.append({
            "trade_id": t.get("trade_id", "N/A"),
            "pair": t.get("pair") or t.get("symbol", "N/A"),
            "timeframe": t.get("timeframe", "N/A"),
            "direction": t.get("direction", "N/A"),
            "opened_at": t.get("opened_at", "N/A"),
            "mfe_r": round(t.get("mfe_r", 1.0), 2),
            "mfe_pips": t.get("mfe_pips", 0.0),
            "realized_r": round(t.get("realized_r", 0.0), 2),
            "capital_saved_r": 1.0,  # Prevented a -1.0R loss
        })

    return {
        "total_losses": len(losses),
        "total_be_exits": len(be_exits),
        "large_mfe_losses_count": len(large_mfe_losses),      # LEAKAGE
        "moderate_mfe_losses_count": len(moderate_mfe_losses),
        "timing_whipsaws_count": len(timing_whipsaws),
        "immediate_failures_count": len(immediate_failures),
        "large_mfe_losses": large_mfe_losses,
        "be_records": be_analysis,
    }


def format_comparison_table(old: Dict[str, Any], new: Dict[str, Any]) -> str:
    """Formats side-by-side comparison table between Old System and New System."""
    lines = []
    lines.append("=" * 76)
    lines.append(f"{'SYSTEM VALIDATION MATRIX: OLD BASELINE vs NEW OUT-OF-SAMPLE':^76}")
    lines.append("=" * 76)
    lines.append(f"{'Metric':<28} | {'Old Baseline (v1.0)':<21} | {'New System (v2.0-Frozen)':<21}")
    lines.append("-" * 28 + "-+-" + "-" * 21 + "-+-" + "-" * 21)

    def row(label: str, old_val: Any, new_val: Any) -> str:
        return f"{label:<28} | {str(old_val):<21} | {str(new_val):<21}"

    lines.append(row("Trades Evaluated", old["trades"], new["trades"]))
    lines.append(row("Win Rate", f"{old['win_rate_pct']:.1f}%", f"{new['win_rate_pct']:.1f}%" if new["trades"] > 0 else "Pending"))
    lines.append(row("Avg Win R", f"{old['avg_win_r']:+.2f}R", f"{new['avg_win_r']:+.2f}R" if new["wins"] > 0 else "Pending"))
    lines.append(row("Avg Loss R", f"{old['avg_loss_r']:+.2f}R", f"{new['avg_loss_r']:+.2f}R" if new["losses"] > 0 else "Pending"))
    lines.append(row("Expectancy", f"{old['expectancy_r']:+.3f}R", f"{new['expectancy_r']:+.3f}R" if new["trades"] > 0 else "Pending"))
    lines.append(row("Profit Factor", f"{old['profit_factor']:.2f}", f"{new['profit_factor']:.2f}" if new["trades"] > 0 else "Pending"))
    lines.append(row("Max Drawdown", f"{old['max_dd_r']:.2f}R", f"{new['max_dd_r']:.2f}R" if new["trades"] > 0 else "Pending"))
    lines.append(row("Average MFE", f"{old['avg_mfe_r']:.2f}R", f"{new['avg_mfe_r']:.2f}R" if new["trades"] > 0 else "Pending"))
    lines.append(row("Average MAE", f"{old['avg_mae_r']:.2f}R", f"{new['avg_mae_r']:.2f}R" if new["trades"] > 0 else "Pending"))
    lines.append(row("+1R before -1R", f"{old['plus1_before_minus1_pct']:.1f}%", f"{new['plus1_before_minus1_pct']:.1f}%" if new["trades"] > 0 else "Pending"))
    lines.append(row("TP Reached Rate", f"{old['tp_reached_pct']:.1f}%", f"{new['tp_reached_pct']:.1f}%" if new["trades"] > 0 else "Pending"))
    lines.append(row("BE Triggered Count", f"{old['be_triggered']} ({old['be_triggered_pct']:.1f}%)", f"{new['be_triggered']} ({new['be_triggered_pct']:.1f}%)" if new["trades"] > 0 else "Pending"))
    lines.append(row("BE Exits Count", f"{old['be_exits']} ({old['be_exits_pct']:.1f}%)", f"{new['be_exits']} ({new['be_exits_pct']:.1f}%)" if new["trades"] > 0 else "Pending"))
    lines.append(row("Structural TP Target", f"{old['avg_tp_distance_r']:.2f}R (Hybrid)", f"{new['avg_tp_distance_r']:.2f}R (Dynamic BSL/SSL)" if new["trades"] > 0 else "Model F (1.5-2.5R)"))
    lines.append(row("Friction / Costs per Trade", f"{old['est_cost_per_trade_r']:.3f}R", f"{new['est_cost_per_trade_r']:.3f}R"))
    lines.append(row("Net Expectancy (Post-Cost)", f"{old['net_expectancy_r']:+.3f}R", f"{new['net_expectancy_r']:+.3f}R" if new["trades"] > 0 else "Pending"))
    lines.append("=" * 76)
    return "\n".join(lines)


def format_loss_mfe_table(loss_diag: Dict[str, Any]) -> str:
    """Formats loss MFE distribution and +1.0R BE protection efficiency."""
    lines = []
    lines.append("\n" + "=" * 76)
    lines.append(f"{'CRITICAL +1.0R BREAK-EVEN MECHANISM EVALUATION (LOSS MFE AUDIT)':^76}")
    lines.append("=" * 76)

    total_losses = loss_diag["total_losses"]
    total_be = loss_diag["total_be_exits"]

    lines.append(f"Total Completed Losses: {total_losses} | Total Break-Even Exits: {total_be}")
    lines.append("-" * 76)
    lines.append(f"1. Immediate Failures (MFE < 0.25R):        {loss_diag['immediate_failures_count']:>3} trades (Normal structural stop-outs)")
    lines.append(f"2. Timing Whipsaws (0.25R <= MFE < 0.50R):     {loss_diag['timing_whipsaws_count']:>3} trades (Early pullback sweep)")
    lines.append(f"3. Moderate Excursions (0.50R <= MFE < 1.0R):  {loss_diag['moderate_mfe_losses_count']:>3} trades (Reversed before +1R BE)")
    lines.append(f"4. Leakage Losses (MFE >= 1.0R):               {loss_diag['large_mfe_losses_count']:>3} trades (CRITICAL: should be 0 with BE active!)")
    lines.append("-" * 76)

    if loss_diag["large_mfe_losses"]:
        lines.append("⚠️  ALERT: Detected trades that reached >= +1.0R but still closed as LOSS:")
        for t in loss_diag["large_mfe_losses"]:
            lines.append(f"   • {t['trade_id']}: MFE = +{t['mfe_r']}R ({t['mfe_pips']} pips) -> Closed at {t['realized_r']}R")
    else:
        lines.append("✅  Zero leakage: No trade reaching +1.0R reversed into a full stop loss.")

    if loss_diag["be_records"]:
        lines.append("\n🛡️  Break-Even Capital Protection Records:")
        for b in loss_diag["be_records"]:
            lines.append(f"   • {b['trade_id']}: Peaked at +{b['mfe_r']}R -> Reversal protected at BE (+{b['realized_r']}R). Saved: +{b['capital_saved_r']:.1f}R capital.")
    lines.append("=" * 76)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Forward-Test Out-of-Sample Performance Tracker")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--markdown", action="store_true", help="Output results formatted in Markdown")
    parser.add_argument("--all-trades", action="store_true", help="Include all completed live trades regardless of timestamp")
    args = parser.parse_args()

    records = load_trade_records()
    completed = records.get("completed_trades", [])

    freeze_dt = parse_timestamp(FREEZE_TIMESTAMP)

    new_system_trades = []
    old_system_live_trades = []

    for t in completed:
        open_dt = parse_timestamp(t.get("opened_at"))
        if not args.all_trades and freeze_dt and open_dt and open_dt < freeze_dt:
            old_system_live_trades.append(t)
        else:
            new_system_trades.append(t)

    # Compute metrics for New System
    new_metrics = calculate_metrics(new_system_trades)
    new_loss_diag = analyze_losing_mfe(new_system_trades)

    if args.json:
        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strategy_freeze_time": FREEZE_TIMESTAMP,
            "old_baseline": OLD_BASELINE,
            "new_system_forward_test": {
                "metrics": new_metrics,
                "loss_mfe_analysis": new_loss_diag,
                "trades": new_system_trades,
            }
        }
        print(json.dumps(output, indent=2))
        return

    if args.markdown:
        md = []
        md.append("## Forward-Test Out-of-Sample Validation Tracker\n")
        md.append(f"*Frozen Baseline Established*: `{FREEZE_TIMESTAMP}`\n")
        md.append("| Metric | Old Baseline (v1.0) | New System (v2.0-Frozen) |")
        md.append("| :--- | :--- | :--- |")
        md.append(f"| **Trades Evaluated** | {OLD_BASELINE['trades']} | {new_metrics['trades']} |")
        md.append(f"| **Win Rate** | {OLD_BASELINE['win_rate_pct']:.1f}% | {new_metrics['win_rate_pct']:.1f}% |")
        md.append(f"| **Avg Win R** | {OLD_BASELINE['avg_win_r']:+.2f}R | {new_metrics['avg_win_r']:+.2f}R |")
        md.append(f"| **Avg Loss R** | {OLD_BASELINE['avg_loss_r']:+.2f}R | {new_metrics['avg_loss_r']:+.2f}R |")
        md.append(f"| **Expectancy** | {OLD_BASELINE['expectancy_r']:+.3f}R | {new_metrics['expectancy_r']:+.3f}R |")
        md.append(f"| **Profit Factor** | {OLD_BASELINE['profit_factor']:.2f} | {new_metrics['profit_factor']:.2f} |")
        md.append(f"| **Max Drawdown** | {OLD_BASELINE['max_dd_r']:.2f}R | {new_metrics['max_dd_r']:.2f}R |")
        md.append(f"| **Average MFE** | {OLD_BASELINE['avg_mfe_r']:.2f}R | {new_metrics['avg_mfe_r']:.2f}R |")
        md.append(f"| **Average MAE** | {OLD_BASELINE['avg_mae_r']:.2f}R | {new_metrics['avg_mae_r']:.2f}R |")
        md.append(f"| **+1R before -1R** | {OLD_BASELINE['plus1_before_minus1_pct']:.1f}% | {new_metrics['plus1_before_minus1_pct']:.1f}% |")
        md.append(f"| **TP Reached Rate** | {OLD_BASELINE['tp_reached_pct']:.1f}% | {new_metrics['tp_reached_pct']:.1f}% |")
        md.append(f"| **BE Triggered** | {OLD_BASELINE['be_triggered']} | {new_metrics['be_triggered']} |")
        md.append(f"| **BE Exits** | {OLD_BASELINE['be_exits']} | {new_metrics['be_exits']} |")
        md.append(f"| **Structural TP Distance** | {OLD_BASELINE['avg_tp_distance_r']:.2f}R | {new_metrics['avg_tp_distance_r']:.2f}R |")
        md.append(f"| **Costs / Trade** | {OLD_BASELINE['est_cost_per_trade_r']:.3f}R | {new_metrics['est_cost_per_trade_r']:.3f}R |")
        md.append(f"| **Net Expectancy** | {OLD_BASELINE['net_expectancy_r']:+.3f}R | {new_metrics['net_expectancy_r']:+.3f}R |")
        print("\n".join(md))
        return

    # Default formatted table output
    print(format_comparison_table(OLD_BASELINE, new_metrics))
    print(format_loss_mfe_table(new_loss_diag))


if __name__ == "__main__":
    main()
