"""
Quantitative Trade Chart Generator (v3.3.0)
Generates high-resolution, institutional TradingView charts with Smart Money Concepts (SMC/ICT)
overlays: Order Blocks (OB), Liquidity Sweeps (BSL/SSL), Market Structure Shifts (MSS),
20-EMA Dynamic Equilibrium curve, and the authentic Long/Short Position Tool.
"""

import io
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import matplotlib
matplotlib.use("Agg")  # Headless non-interactive backend
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logger = logging.getLogger("ChartGenerator")


def generate_trade_chart(
    df: pd.DataFrame,
    sig: Dict[str, Any],
    trade_status: str = "OPEN",
    bars_to_display: int = 60,
    projection_bars: int = 20
) -> Optional[bytes]:
    """
    Renders an institutional-grade TradingView chart with full ICT / Smart Money Concepts overlays.

    Visual Specifications:
      - Clean Institutional Dark Theme (#131722) canvas with subtle grid (#2A2E39).
      - Modern Royal Blue & Dark Slate Candlesticks (Zero classic red/green):
          • Bullish Candles: Modern Royal Blue (#2962FF).
          • Bearish Candles: Dark Slate / Charcoal (#363A45) with silver outline (#787B86).
      - ICT / SMC Technical Overlays:
          • Order Block (OB): Semi-transparent shaded box with 50% equilibrium dotted line.
          • Liquidity Sweep: Swing level marked with 'x' (SSL for Long, BSL for Short).
          • Market Structure Shift (MSS): Breakout pivot line with direction arrow.
          • 20-EMA Dynamic Equilibrium curve (#FF9800).
      - TradingView Long / Short Position Tool:
          • Target Zone: Translucent Royal Blue (#2962FF, alpha=0.22).
          • Stop Loss Zone: Translucent Slate Grey (#787B86, alpha=0.20).
          • Dotted diagonal projection trajectory.
      - Right Price Axis Flags:
          • Take Profit: Solid Royal Blue badge (#2962FF).
          • Entry Level: Solid Off-White badge (#D1D4DC).
          • Stop Loss: Solid Slate Grey badge (#787B86).
          • Market Price: Solid Dark Badge (#363A45) with crosshair.
      - Top-Left Header:
          • Symbol & Timeframe: "{PAIR} • {TF}" (Clean, bold institutional font).
          • Sub-header: "QuantFlow Institutional Analysis • ICT Smart Money Engine".
          • Indicators Legend: SMC [ICT] (Order Block, Liquidity Sweep, MSS) & 20-EMA.
    """
    if df is None or df.empty or len(df) < 5:
        logger.warning("generate_trade_chart: Insufficient candle data provided.")
        return None

    try:
        raw_pair = sig.get("pair", "EURUSD").upper()
        display_pair = f"{raw_pair[:3]}/{raw_pair[3:]}" if len(raw_pair) == 6 else raw_pair
        is_long = sig.get("direction", "LONG").upper() == "LONG"
        timeframe_raw = str(sig.get("timeframe", "15M")).strip().upper()
        if timeframe_raw.endswith("M") or timeframe_raw.endswith("H") or timeframe_raw.endswith("D"):
            tf_display = timeframe_raw
        else:
            tf_display = f"{timeframe_raw}M"

        entry = float(sig.get("entry", df.iloc[-1]["close"]))
        sl = float(sig.get("stop_loss", entry * (0.998 if is_long else 1.002)))
        tp = float(sig.get("take_profit", entry * (1.003 if is_long else 0.997)))
        rr_val = float(sig.get("risk_reward") or sig.get("rr") or (abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 1.75))

        # Precision decimals (3 for JPY, 5 for Forex, 2 for Gold)
        is_jpy = "JPY" in raw_pair
        is_gold = "XAU" in raw_pair or "GOLD" in raw_pair
        digits = 3 if is_jpy else (2 if is_gold else 5)

        # Slice recent historical candles
        plot_df = df.iloc[-bars_to_display:].copy()
        n = len(plot_df)
        cur_px = float(plot_df.iloc[-1]["close"])

        # Calculate 20-EMA if not present
        if "ema20" not in plot_df.columns:
            plot_df["ema20"] = plot_df["close"].ewm(span=20, adjust=False).mean()

        # Canvas Setup (13.0 x 7.2 inches @ 150 DPI)
        fig = plt.figure(figsize=(13.0, 7.2), dpi=150, facecolor="#131722")
        ax = fig.add_axes([0.035, 0.07, 0.865, 0.85], facecolor="#131722")

        x = np.arange(n)
        w_candle = 0.62
        w_wick = 0.08

        # Candlestick colors
        up_color = "#2962FF"       # Royal Blue
        down_color = "#363A45"     # Dark Slate / Charcoal

        up_mask = plot_df["close"] >= plot_df["open"]
        down_mask = plot_df["close"] < plot_df["open"]

        up_df = plot_df[up_mask]
        down_df = plot_df[down_mask]

        # Draw Bullish Candles
        if not up_df.empty:
            up_x = [plot_df.index.get_loc(i) for i in up_df.index]
            ax.bar(up_x, up_df["close"] - up_df["open"], w_candle, bottom=up_df["open"],
                   color=up_color, edgecolor=up_color, linewidth=0.6, zorder=3)
            ax.bar(up_x, up_df["high"] - up_df["close"], w_wick, bottom=up_df["close"],
                   color=up_color, edgecolor=up_color, linewidth=0.6, zorder=3)
            ax.bar(up_x, up_df["low"] - up_df["open"], w_wick, bottom=up_df["open"],
                   color=up_color, edgecolor=up_color, linewidth=0.6, zorder=3)

        # Draw Bearish Candles
        if not down_df.empty:
            down_x = [plot_df.index.get_loc(i) for i in down_df.index]
            ax.bar(down_x, down_df["close"] - down_df["open"], w_candle, bottom=down_df["open"],
                   color=down_color, edgecolor="#787B86", linewidth=0.6, zorder=3)
            ax.bar(down_x, down_df["high"] - down_df["open"], w_wick, bottom=down_df["open"],
                   color="#787B86", edgecolor="#787B86", linewidth=0.6, zorder=3)
            ax.bar(down_x, down_df["low"] - down_df["close"], w_wick, bottom=down_df["close"],
                   color="#787B86", edgecolor="#787B86", linewidth=0.6, zorder=3)

        # Draw 20-EMA Trendline
        ax.plot(x, plot_df["ema20"], color="#FF9800", linewidth=1.3, alpha=0.85, zorder=4)

        # ==============================================================================
        # ICT / SMART MONEY CONCEPTS (SMC) OVERLAYS (Liquidity Zones & Sweeps)
        # ==============================================================================
        sweep_level = None
        search_window = plot_df.iloc[max(0, n - 26):max(1, n - 3)]

        if is_long:
            # 1. Bullish Order Block / Demand Liquidity Zone: Lowest down-candle prior to impulse
            down_candles = search_window[search_window["close"] <= search_window["open"]]
            if not down_candles.empty:
                ob_bar_idx = down_candles["low"].idxmin()
                ob_idx = plot_df.index.get_loc(ob_bar_idx)
            else:
                ob_idx = max(0, n - 14)

            ob_bar = plot_df.iloc[ob_idx]
            ob_top = max(ob_bar["open"], ob_bar["close"])
            ob_bottom = ob_bar["low"]
            ob_len = (n - ob_idx) + 8

            ob_rect = patches.Rectangle(
                (ob_idx - 0.5, ob_bottom), ob_len, max(ob_top - ob_bottom, 0.0001),
                linewidth=0.9, edgecolor="#00E676", facecolor="#00E676", alpha=0.14, zorder=2
            )
            ax.add_patch(ob_rect)
            ax.hlines((ob_top + ob_bottom) / 2, ob_idx - 0.5, ob_idx + ob_len,
                      colors="#00E676", linestyles=":", linewidth=0.8, alpha=0.6, zorder=3)
            ax.text(ob_idx + 0.8, ob_top, f"+OB / Demand ({tf_display.lower()})", color="#00E676", fontsize=7.5, weight="bold", va="bottom")

            # 2. Sell-Side Liquidity (SSL) Sweep
            if not search_window.empty:
                sweep_level = search_window["low"].min()
                sweep_bar_idx = search_window["low"].idxmin()
                sweep_x = plot_df.index.get_loc(sweep_bar_idx)
                ax.hlines(sweep_level, sweep_x - 3, min(n + 6, sweep_x + 18), colors="#FF5252", linestyles="--", linewidth=0.9, zorder=3)
                ax.plot(sweep_x, sweep_level, "x", color="#FF5252", markersize=6, markeredgewidth=1.5, zorder=5)
                ax.text(sweep_x + 3, sweep_level - (0.00015 if not is_jpy else 0.015),
                        "Liquidity Sweep (SSL)", color="#FF5252", fontsize=7.5, weight="bold", va="top")

                # 3. Market Structure Shift (MSS ▴)
                pre_sweep = search_window.loc[:sweep_bar_idx]
                mss_bar_idx = pre_sweep["high"].idxmax() if len(pre_sweep) >= 2 else search_window["high"].idxmax()
                mss_level = float(search_window.loc[mss_bar_idx, "high"])
                mss_x = plot_df.index.get_loc(mss_bar_idx)
                ax.hlines(mss_level, mss_x, min(n + 6, mss_x + 14), colors="#00E5FF", linestyles=":", linewidth=1.1, zorder=4)
                ax.text(min(n + 3, mss_x + 13), mss_level + (0.00010 if not is_jpy else 0.010),
                        "MSS ▴", color="#00E5FF", fontsize=7.5, weight="bold", va="bottom", ha="right")

        else:
            # 1. Bearish Order Block / Supply Liquidity Zone: Highest up-candle prior to sell-off
            up_candles = search_window[search_window["close"] >= search_window["open"]]
            if not up_candles.empty:
                ob_bar_idx = up_candles["high"].idxmax()
                ob_idx = plot_df.index.get_loc(ob_bar_idx)
            else:
                ob_idx = max(0, n - 14)

            ob_bar = plot_df.iloc[ob_idx]
            ob_top = ob_bar["high"]
            ob_bottom = min(ob_bar["open"], ob_bar["close"])
            ob_len = (n - ob_idx) + 8

            ob_rect = patches.Rectangle(
                (ob_idx - 0.5, ob_bottom), ob_len, max(ob_top - ob_bottom, 0.0001),
                linewidth=0.9, edgecolor="#FF5252", facecolor="#FF5252", alpha=0.14, zorder=2
            )
            ax.add_patch(ob_rect)
            ax.hlines((ob_top + ob_bottom) / 2, ob_idx - 0.5, ob_idx + ob_len,
                      colors="#FF5252", linestyles=":", linewidth=0.8, alpha=0.6, zorder=3)
            ax.text(ob_idx + 0.8, ob_bottom, f"-OB / Supply ({tf_display.lower()})", color="#FF5252", fontsize=7.5, weight="bold", va="top")

            # 2. Buy-Side Liquidity (BSL) Sweep
            if not search_window.empty:
                sweep_level = search_window["high"].max()
                sweep_bar_idx = search_window["high"].idxmax()
                sweep_x = plot_df.index.get_loc(sweep_bar_idx)
                ax.hlines(sweep_level, sweep_x - 3, min(n + 6, sweep_x + 18), colors="#FF5252", linestyles="--", linewidth=0.9, zorder=3)
                ax.plot(sweep_x, sweep_level, "x", color="#FF5252", markersize=6, markeredgewidth=1.5, zorder=5)
                ax.text(sweep_x + 3, sweep_level + (0.00015 if not is_jpy else 0.015),
                        "Liquidity Sweep (BSL)", color="#FF5252", fontsize=7.5, weight="bold", va="bottom")

                # 3. Market Structure Shift (MSS ▾)
                pre_sweep = search_window.loc[:sweep_bar_idx]
                mss_bar_idx = pre_sweep["low"].idxmin() if len(pre_sweep) >= 2 else search_window["low"].idxmin()
                mss_level = float(search_window.loc[mss_bar_idx, "low"])
                mss_x = plot_df.index.get_loc(mss_bar_idx)
                ax.hlines(mss_level, mss_x, min(n + 6, mss_x + 14), colors="#FF9800", linestyles=":", linewidth=1.1, zorder=4)
                ax.text(min(n + 3, mss_x + 13), mss_level - (0.00010 if not is_jpy else 0.010),
                        "MSS ▾", color="#FF9800", fontsize=7.5, weight="bold", va="top", ha="right")

        # ==============================================================================
        # TradingView Long / Short Position Tool Geometry OR Market Outlook Zones
        # ==============================================================================
        is_running = trade_status.upper() in ("HALFWAY", "RUNNING")
        is_tp_hit = trade_status.upper() in ("TP_HIT", "RESOLVED", "WIN")
        is_outlook = trade_status.upper() in ("OUTLOOK", "TREND", "MACRO")

        if is_outlook:
            # 1. 50-SMA Trendline Curve
            if "sma50" not in plot_df.columns:
                plot_df["sma50"] = plot_df["close"].rolling(min(30, n), min_periods=5).mean()
            ax.plot(x, plot_df["sma50"], color="#00E5FF", linewidth=1.1, linestyle="--", alpha=0.75, zorder=4)

            # 2. Major Supply / Overhead Resistance Zone
            res_px = float(plot_df["high"].tail(35).max())
            res_rect = patches.Rectangle(
                (0, res_px - 0.0006), n + 12, 0.0006,
                linewidth=0.9, edgecolor="#FF5252", facecolor="#FF5252", alpha=0.15, zorder=2
            )
            ax.add_patch(res_rect)
            ax.hlines(res_px, 0, n + 10, colors="#FF5252", linestyles="-", linewidth=1.1, zorder=4)
            ax.text(n - 2, res_px + (0.00010 if not is_jpy else 0.010),
                    "Major Supply / Key Resistance", color="#FF5252", fontsize=7.5, weight="bold", ha="right", va="bottom")

            # 3. Major Demand / Underlying Support Zone
            sup_px = float(plot_df["low"].tail(35).min())
            sup_rect = patches.Rectangle(
                (0, sup_px), n + 12, 0.0006,
                linewidth=0.9, edgecolor="#00E676", facecolor="#00E676", alpha=0.15, zorder=2
            )
            ax.add_patch(sup_rect)
            ax.hlines(sup_px, 0, n + 10, colors="#00E676", linestyles="-", linewidth=1.1, zorder=4)
            ax.text(n - 2, sup_px - (0.00010 if not is_jpy else 0.010),
                    "Major Demand / Key Support", color="#00E676", fontsize=7.5, weight="bold", ha="right", va="top")

            # 4. Market Price crosshair
            ax.axhline(cur_px, color="#787B86", linestyle=":", linewidth=0.7, alpha=0.6, zorder=4)

            # 5. Outlook Info Pill
            trend_dir = "Bullish" if cur_px >= float(plot_df["ema20"].iloc[-1]) else "Bearish"
            pill_text = (
                f"Market Trend Outlook ({tf_display})\n"
                f"Trend Structure: {trend_dir} Flow\n"
                f"Game Plan: Awaiting Key Zone Reaction"
            )
            ax.text(n - 16, cur_px, pill_text, color="#FFFFFF", fontsize=8.0, weight="bold",
                    va="center", ha="left", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.35", facecolor="#1E222D", edgecolor="#00E5FF", alpha=0.85, linewidth=0.8))

            # 6. Right Axis Badges for Outlook
            ax.yaxis.tick_right()
            ax.yaxis.set_label_position("right")
            ax.tick_params(colors="#787B86", labelsize=9, length=4)
            ax.grid(True, color="#2A2E39", linestyle="-", linewidth=0.5, alpha=0.5)

            ax.text(1.008, res_px, f" {res_px:.{digits}f} ", transform=ax.get_yaxis_transform(),
                    color="#FFFFFF", backgroundcolor="#FF5252", fontsize=8.5, weight="bold", va="center")
            ax.text(1.008, sup_px, f" {sup_px:.{digits}f} ", transform=ax.get_yaxis_transform(),
                    color="#131722", backgroundcolor="#00E676", fontsize=8.5, weight="bold", va="center")
            ax.text(1.008, cur_px, f" {cur_px:.{digits}f} ", transform=ax.get_yaxis_transform(),
                    color="#FFFFFF", backgroundcolor="#363A45", fontsize=8.5, weight="bold", va="center")

            # Timeline
            step = max(1, n // 6)
            tick_locs = list(range(0, n, step))
            time_series = plot_df.index if isinstance(plot_df.index, pd.DatetimeIndex) else None
            if time_series is not None and len(time_series) == n:
                tick_labels = [time_series[i].strftime("%d %b %H:%M") for i in tick_locs]
                ax.set_xticks(tick_locs)
                ax.set_xticklabels(tick_labels, color="#787B86", fontsize=8.5)
            else:
                ax.set_xticks([])

            # Header
            fig.text(0.038, 0.955, f"{display_pair}  •  {tf_display}", fontsize=14, weight="bold", color="#FFFFFF")
            fig.text(0.038, 0.925, "Higher-Timeframe Trend Structure • 20-EMA & 50-SMA • Major Zones", fontsize=8.2, color="#787B86")
            fig.text(0.890, 0.955, "QuantFlow Institutional Analysis", fontsize=9.5, color="#787B86", ha="right")

            ax.set_xlim(-1, n + 8)
            min_p = min(plot_df["low"].min(), sup_px)
            max_p = max(plot_df["high"].max(), res_px)
            padding = (max_p - min_p) * 0.10
            ax.set_ylim(min_p - padding, max_p + padding)

            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor(), edgecolor="none")
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()

        if is_tp_hit:
            box_width = min(22, max(6, n // 2))
            box_start = max(0, n - box_width)
            box_end = n - 1
        elif is_running:
            elapsed_bars = min(14, max(4, n // 3))
            box_start = max(0, n - elapsed_bars)
            box_width = (n - box_start) + projection_bars
            box_end = box_start + box_width
        else:
            box_start = n - 2
            box_width = projection_bars
            box_end = box_start + box_width

        # Shaded Boxes (Royal Blue for Target, Slate Grey for Stop Loss)
        if is_long:
            tp_box = patches.Rectangle(
                (box_start, entry), box_width, tp - entry,
                linewidth=1.0, edgecolor="#2962FF", facecolor="#2962FF", alpha=0.22, zorder=2
            )
            sl_box = patches.Rectangle(
                (box_start, sl), box_width, entry - sl,
                linewidth=1.0, edgecolor="#787B86", facecolor="#787B86", alpha=0.20, zorder=2
            )
        else:
            sl_box = patches.Rectangle(
                (box_start, entry), box_width, sl - entry,
                linewidth=1.0, edgecolor="#787B86", facecolor="#787B86", alpha=0.20, zorder=2
            )
            tp_box = patches.Rectangle(
                (box_start, tp), box_width, entry - tp,
                linewidth=1.0, edgecolor="#2962FF", facecolor="#2962FF", alpha=0.22, zorder=2
            )

        ax.add_patch(tp_box)
        ax.add_patch(sl_box)

        # Diagonal dotted trajectory lines (Authentic TradingView Projection)
        if is_running:
            # Traversed path from entry to current price
            ax.plot([box_start, n - 1], [entry, cur_px], color="#2962FF", linestyle=":", linewidth=1.2, alpha=0.85, zorder=3)
            # Remaining path to TP
            ax.plot([n - 1, box_end], [cur_px, tp], color="#2962FF", linestyle=":", linewidth=0.9, alpha=0.60, zorder=3)
        else:
            ax.plot([box_start, box_end], [entry, tp], color="#2962FF", linestyle=":", linewidth=1.2, alpha=0.80, zorder=3)

        # Horizontal level lines
        ax.hlines(entry, box_start, box_end, colors="#D1D4DC", linestyles="--", linewidth=1.0, zorder=5)
        ax.hlines(tp, box_start, box_end, colors="#2962FF", linestyles="-", linewidth=1.2, zorder=5)
        ax.hlines(sl, box_start, box_end, colors="#787B86", linestyles="-", linewidth=1.2, zorder=5)

        # Target Draw on Liquidity (DOL) annotation on Take Profit level
        tp_target_name = "Target: Buy-Side Liquidity (BSL)" if is_long else "Target: Sell-Side Liquidity (SSL)"
        ax.text(box_start + 0.8, tp + (0.00012 if is_long else -0.00012) if not is_jpy else tp + (0.012 if is_long else -0.012),
                tp_target_name, color="#2962FF", fontsize=7.5, weight="bold",
                va="bottom" if is_long else "top", zorder=6)

        # Invalidation annotation on Stop Loss level
        ax.text(box_start + 0.8, sl - (0.00012 if is_long else -0.00012) if not is_jpy else sl - (0.012 if is_long else -0.012),
                "Invalidation (SL)", color="#787B86", fontsize=7.0, weight="bold",
                va="top" if is_long else "bottom", zorder=6)

        # Current market price crosshair line
        ax.axhline(cur_px, color="#787B86", linestyle=":", linewidth=0.7, alpha=0.6, zorder=4)

        # TradingView Box Info Pill (Open PnL / Take Profit Status)
        pip_mult = 100 if is_jpy else 10000
        target_badge = "BSL Target" if is_long else "SSL Target"
        if is_running:
            pnl_pips = (cur_px - entry) * pip_mult if is_long else (entry - cur_px) * pip_mult
            sl_pips_val = float(sig.get("sl_pips", 20.0))
            r_val = pnl_pips / sl_pips_val if sl_pips_val > 0 else 0.0
            pill_text = f"{target_badge} • Open PnL: {pnl_pips:+.1f} pips (+{r_val:.2f}R)\nRisk/reward ratio: {rr_val:.2f}"
            pill_x = box_start + 1.2
            pill_y = entry + (tp - entry) * 0.25
            ax.text(pill_x, pill_y, pill_text, color="#FFFFFF", fontsize=8.0, weight="bold",
                    va="center", ha="left", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.35", facecolor="#1E222D", edgecolor="#2962FF", alpha=0.80, linewidth=0.8))
        elif is_tp_hit:
            tp_pips_val = float(sig.get("tp_pips", 35.0))
            pill_text = f"{target_badge} Swept: +{tp_pips_val:.1f} pips (+{rr_val:.2f}R)\nStatus: Target Reached"
            pill_x = box_start + 1.2
            pill_y = entry + (tp - entry) * 0.50
            ax.text(pill_x, pill_y, pill_text, color="#FFFFFF", fontsize=8.0, weight="bold",
                    va="center", ha="left", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.35", facecolor="#1E222D", edgecolor="#00E676", alpha=0.85, linewidth=0.8))
        else:
            tp_pips_val = float(sig.get("tp_pips", 35.0))
            pill_text = f"{target_badge}: +{tp_pips_val:.1f} pips (+{rr_val:.2f}R)\nRisk/reward ratio: {rr_val:.2f}"
            pill_x = box_start + 1.2
            pill_y = entry + (tp - entry) * 0.35
            ax.text(pill_x, pill_y, pill_text, color="#FFFFFF", fontsize=8.0, weight="bold",
                    va="center", ha="left", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.35", facecolor="#1E222D", edgecolor="#2962FF", alpha=0.80, linewidth=0.8))

        # Right Price Axis Formatting
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        ax.tick_params(colors="#787B86", labelsize=9, length=4)
        ax.grid(True, color="#2A2E39", linestyle="-", linewidth=0.5, alpha=0.5)

        # Right Axis Badges (Authentic TradingView Price Badges)
        cur_px_bg = "#2962FF" if (is_running or is_tp_hit) else "#363A45"
        ax.text(1.008, tp, f" {tp:.{digits}f} ", transform=ax.get_yaxis_transform(),
                color="#FFFFFF", backgroundcolor="#2962FF", fontsize=8.5, weight="bold", va="center")
        ax.text(1.008, entry, f" {entry:.{digits}f} ", transform=ax.get_yaxis_transform(),
                color="#131722", backgroundcolor="#D1D4DC", fontsize=8.5, weight="bold", va="center")
        ax.text(1.008, sl, f" {sl:.{digits}f} ", transform=ax.get_yaxis_transform(),
                color="#FFFFFF", backgroundcolor="#787B86", fontsize=8.5, weight="bold", va="center")
        ax.text(1.008, cur_px, f" {cur_px:.{digits}f} ", transform=ax.get_yaxis_transform(),
                color="#FFFFFF", backgroundcolor=cur_px_bg, fontsize=8.5, weight="bold", va="center")

        # Bottom X-Axis Time Ticks (Authentic TradingView Timeline)
        step = max(1, n // 6)
        tick_locs = list(range(0, n, step))
        time_series = None
        if "time" in plot_df.columns:
            time_series = pd.to_datetime(plot_df["time"])
        elif isinstance(plot_df.index, pd.DatetimeIndex):
            time_series = plot_df.index
        elif hasattr(plot_df.index[0], "strftime"):
            time_series = plot_df.index

        if time_series is not None and len(time_series) == n:
            tick_labels = [
                time_series.iloc[i].strftime("%d %b %H:%M") if hasattr(time_series, "iloc") else time_series[i].strftime("%d %b %H:%M")
                for i in tick_locs
            ]
            ax.set_xticks(tick_locs)
            ax.set_xticklabels(tick_labels, color="#787B86", fontsize=8.5)
        else:
            ax.set_xticks([])

        # ==============================================================================
        # Professional Institutional Header (TradingView Style)
        # ==============================================================================
        # Top-Left: Clean pair name and timeframe (e.g. "EUR/USD  •  15M")
        fig.text(0.038, 0.955, f"{display_pair}  •  {tf_display}", fontsize=14, weight="bold", color="#FFFFFF")
        fig.text(0.038, 0.925, "ICT SMC Precision Execution • 20-EMA • Liquidity Sweeps • MSS", fontsize=8.2, color="#787B86")

        # Top-Right: Institutional branding aligned to right margin (zero overlap)
        fig.text(0.890, 0.955, "QuantFlow Institutional Analysis", fontsize=9.5, color="#787B86", ha="right")

        # Set axis limits with clean padding
        right_padding = 4 if is_tp_hit else (8 if is_running else 12)
        ax.set_xlim(-1, max(n + 2, box_end + right_padding))
        price_candidates = [plot_df["low"].min(), plot_df["high"].max(), sl, tp]
        if sweep_level is not None:
            price_candidates.append(sweep_level)
        min_p = min(price_candidates)
        max_p = max(price_candidates)
        padding = (max_p - min_p) * 0.09
        ax.set_ylim(min_p - padding, max_p + padding)

        # Render to in-memory byte buffer
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        logger.error(f"generate_trade_chart failed: {e}", exc_info=True)
        try:
            plt.close("all")
        except Exception:
            pass
        return None
