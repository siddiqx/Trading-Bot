"""
Quantitative Trade Chart Generator (v3.3.0)
Generates authentic TradingView Mobile-styled candlestick charts
matching real iPhone / TradingView app screenshots with custom
Monochrome / Deep Blue institutional candles, Long/Short position boxes,
and full UI shell (floating drawing toolbar, right-axis badges, and bottom app bar).
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
    bars_to_display: int = 58,
    projection_bars: int = 18
) -> Optional[bytes]:
    """
    Renders an authentic, 1:1 TradingView Mobile app chart screenshot
    anchored to real market data with zero red/green cliche colors.

    Aesthetic:
      - Clean White TradingView Light Theme (#FFFFFF) with subtle grid (#F0F3FA)
      - Institutional Monochrome & Royal Blue Candlesticks:
          • Bullish: Hollow white body with sharp dark outline (#131722)
          • Bearish: Solid Royal Blue / Navy body (#2962FF / #1855D1)
      - TradingView Position Tool:
          • Target Zone: Translucent Sky Blue box (#90CAF9 / #2962FF, alpha=0.45)
          • Stop Loss Zone: Solid Soft Slate Grey box (#D1D4DC, alpha=0.75)
          • Diagonal dotted trajectory line
      - TradingView Right Price Axis Badges:
          • Stop Loss: High-contrast Dark Badge
          • Entry: Soft Grey Badge
          • Take Profit: TradingView Royal Blue Badge
          • Live Price: Black Badge with candle countdown timer
      - TradingView Mobile UI Frame:
          • Top iOS status bar & instrument header
          • Floating dark drawing toolbar (#1E222D)
          • Bottom TradingView navigation bar & symbol pill
    """
    if df is None or df.empty or len(df) < 5:
        logger.warning("generate_trade_chart: Insufficient candle data provided.")
        return None

    try:
        pair = sig.get("pair", "EURUSD").upper()
        display_pair = f"{pair[:3]}/{pair[3:]}" if len(pair) == 6 else pair
        is_long = sig.get("direction", "LONG").upper() == "LONG"
        timeframe = str(sig.get("timeframe", "15M")).upper()
        tf_lower = timeframe.lower()

        entry = float(sig.get("entry", df.iloc[-1]["close"]))
        sl = float(sig.get("stop_loss", entry * (0.998 if is_long else 1.002)))
        tp = float(sig.get("take_profit", entry * (1.003 if is_long else 0.997)))

        # Precision decimals (3 for JPY, 5 for Forex, 2 for Gold)
        is_jpy = "JPY" in pair
        is_gold = "XAU" in pair or "GOLD" in pair
        digits = 3 if is_jpy else (2 if is_gold else 5)

        # Slice recent historical candles
        plot_df = df.iloc[-bars_to_display:].copy()
        n = len(plot_df)
        cur_px = float(plot_df.iloc[-1]["close"])
        first_px = float(plot_df.iloc[0]["open"])
        net_change = cur_px - first_px
        net_change_pct = (net_change / (first_px + 1e-9)) * 100.0
        change_sign = "+" if net_change >= 0 else ""

        # Mobile aspect ratio (1170 x 2400 iPhone ratio -> 5.8 x 12.0 inches @ 150 DPI)
        fig = plt.figure(figsize=(5.8, 12.0), dpi=150, facecolor="#FFFFFF")
        
        # Main chart axis [left, bottom, width, height]
        ax = fig.add_axes([0.02, 0.055, 0.81, 0.87], facecolor="#FFFFFF")

        x = np.arange(n)
        candle_w = 0.58
        wick_w = 0.09

        # Filter up and down candles
        up_mask = plot_df["close"] >= plot_df["open"]
        down_mask = plot_df["close"] < plot_df["open"]

        up_df = plot_df[up_mask]
        down_df = plot_df[down_mask]

        # 1. Bullish Candles: White / Hollow body with sharp dark outline (#131722)
        if not up_df.empty:
            up_x = [plot_df.index.get_loc(idx) for idx in up_df.index]
            ax.bar(up_x, up_df["close"] - up_df["open"], candle_w, bottom=up_df["open"],
                   color="#FFFFFF", edgecolor="#131722", linewidth=0.8, zorder=4)
            ax.bar(up_x, up_df["high"] - up_df["close"], wick_w, bottom=up_df["close"],
                   color="#131722", edgecolor="#131722", linewidth=0.8, zorder=4)
            ax.bar(up_x, up_df["low"] - up_df["open"], wick_w, bottom=up_df["open"],
                   color="#131722", edgecolor="#131722", linewidth=0.8, zorder=4)

        # 2. Bearish Candles: Solid Royal Blue (#2962FF) with dark borders
        if not down_df.empty:
            down_x = [plot_df.index.get_loc(idx) for idx in down_df.index]
            ax.bar(down_x, down_df["close"] - down_df["open"], candle_w, bottom=down_df["open"],
                   color="#2962FF", edgecolor="#131722", linewidth=0.8, zorder=4)
            ax.bar(down_x, down_df["high"] - down_df["open"], wick_w, bottom=down_df["open"],
                   color="#131722", edgecolor="#131722", linewidth=0.8, zorder=4)
            ax.bar(down_x, down_df["low"] - down_df["close"], wick_w, bottom=down_df["close"],
                   color="#131722", edgecolor="#131722", linewidth=0.8, zorder=4)

        # Position Tool Box Geometry
        # When trade_status == 'OPEN', project into future bars
        # When trade_status == 'TP_HIT', box starts at trigger candle and extends through resolution
        if trade_status == "TP_HIT":
            box_width = min(26, n // 2)
            box_start = max(0, n - box_width - 2)
            box_end = box_start + box_width
        else:
            box_start = n - 2
            box_width = projection_bars
            box_end = box_start + box_width

        # Shaded Boxes matching user TradingView mobile photo:
        # Grey = Stop Loss zone (#D1D4DC), Sky Blue = Target zone (#90CAF9)
        if is_long:
            tp_box = patches.Rectangle(
                (box_start, entry), box_width, tp - entry,
                linewidth=0.8, edgecolor="#2962FF", facecolor="#90CAF9", alpha=0.50, zorder=2
            )
            sl_box = patches.Rectangle(
                (box_start, sl), box_width, entry - sl,
                linewidth=0.8, edgecolor="#131722", facecolor="#D1D4DC", alpha=0.75, zorder=2
            )
        else:
            sl_box = patches.Rectangle(
                (box_start, entry), box_width, sl - entry,
                linewidth=0.8, edgecolor="#131722", facecolor="#D1D4DC", alpha=0.75, zorder=2
            )
            tp_box = patches.Rectangle(
                (box_start, tp), box_width, entry - tp,
                linewidth=0.8, edgecolor="#2962FF", facecolor="#90CAF9", alpha=0.50, zorder=2
            )

        ax.add_patch(sl_box)
        ax.add_patch(tp_box)

        # Dotted diagonal projection trajectory
        ax.plot([box_start, box_end], [entry, tp], color="#787B86", linestyle="--", linewidth=1.0, zorder=3)

        # Horizontal level lines
        ax.hlines(entry, box_start, box_end, colors="#131722", linestyles="-", linewidth=1.0, zorder=5)
        ax.hlines(sl, box_start, box_end, colors="#131722", linestyles="-", linewidth=1.2, zorder=5)
        ax.hlines(tp, box_start, box_end, colors="#2962FF", linestyles="-", linewidth=1.2, zorder=5)

        # Live market horizontal crosshair line
        ax.axhline(cur_px, color="#131722", linestyle=":", linewidth=0.8, alpha=0.85, zorder=4)

        # Format Axes
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        ax.tick_params(colors="#131722", labelsize=8.5, length=3, direction="out")
        ax.grid(True, color="#F0F3FA", linestyle="-", linewidth=0.8)

        # TradingView Right Axis Badges (Exact Replica of TradingView Badges)
        # 1. Stop Loss Badge (Black badge with white text)
        ax.text(1.012, sl, f" {sl:.{digits}f} ", transform=ax.get_yaxis_transform(),
                color="#FFFFFF", backgroundcolor="#131722", fontsize=7.5, weight="bold", va="center")

        # 2. Entry Level Badge (Grey badge)
        ax.text(1.012, entry, f" {entry:.{digits}f} ", transform=ax.get_yaxis_transform(),
                color="#FFFFFF", backgroundcolor="#787B86", fontsize=7.5, va="center")

        # 3. Take Profit Badge (TradingView Blue badge)
        ax.text(1.012, tp, f" {tp:.{digits}f} ", transform=ax.get_yaxis_transform(),
                color="#FFFFFF", backgroundcolor="#2962FF", fontsize=7.5, weight="bold", va="center")

        # 4. Current Live Price Badge (Black badge with countdown timer)
        ax.text(1.012, cur_px, f" {cur_px:.{digits}f} \n 02:13 ", transform=ax.get_yaxis_transform(),
                color="#FFFFFF", backgroundcolor="#000000", fontsize=7.0, weight="bold", va="center")

        # Bottom X-Axis Time Ticks
        step = max(1, n // 5)
        tick_locs = list(range(0, n, step))
        if plot_df.index is not None and hasattr(plot_df.index[0], "strftime"):
            tick_labels = [plot_df.index[i].strftime("%H:%M") for i in tick_locs]
            ax.set_xticks(tick_locs)
            ax.set_xticklabels(tick_labels, color="#787B86", fontsize=8)
        else:
            ax.set_xticks([])

        # Top iOS & TradingView Status Header
        now_time = datetime.now(timezone.utc).strftime("%H:%M")
        fig.text(0.05, 0.975, now_time, fontsize=10.5, weight="bold", color="#000000")
        fig.text(0.50, 0.975, "TradingView", fontsize=9.5, weight="bold", color="#000000", ha="center")
        fig.text(0.95, 0.975, "91%", fontsize=9.0, color="#000000", ha="right")

        # Instrument & Price Line
        fig.text(0.05, 0.948, f"● {display_pair} · {tf_lower}", fontsize=11, weight="bold", color="#000000")
        fig.text(0.05, 0.930, f"{cur_px:.{digits}f}  {change_sign}{net_change:.{digits}f} ({change_sign}{net_change_pct:.2f}%)",
                 fontsize=8.5, color="#787B86")

        # TradingView Top Floating Drawing Toolbar (Dark rounded bar)
        tb_box = patches.FancyBboxPatch(
            (0.32, 0.938), 0.62, 0.030, transform=fig.transFigure,
            boxstyle="round,pad=0.004", facecolor="#1E222D", edgecolor="#2A2E39", zorder=10
        )
        fig.patches.append(tb_box)
        fig.text(0.63, 0.953, "▢   ╱   ⊣⊢   ☰   [✕]   ▼", color="#FFFFFF", fontsize=8.0, ha="center", va="center", zorder=11)

        # TradingView Bottom Navigation Shell
        fig.text(0.05, 0.020, "17", fontsize=13, weight="bold", color="#000000")
        bottom_pill = patches.FancyBboxPatch(
            (0.18, 0.012), 0.38, 0.024, transform=fig.transFigure,
            boxstyle="round,pad=0.005", facecolor="#F0F3FA", edgecolor="#E0E3EB", zorder=10
        )
        fig.patches.append(bottom_pill)
        fig.text(0.37, 0.024, f"{pair}   {tf_lower}", fontsize=8.0, weight="bold", color="#131722", ha="center", va="center", zorder=11)
        fig.text(0.85, 0.020, "⚡", fontsize=11, color="#787B86", ha="center")

        # Limits & Bounds
        ax.set_xlim(-1, max(n + 3, box_end + 3))
        min_p = min(plot_df["low"].min(), sl, tp)
        max_p = max(plot_df["high"].max(), sl, tp)
        padding = (max_p - min_p) * 0.08
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
