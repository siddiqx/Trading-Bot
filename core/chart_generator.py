"""
Quantitative Trade Chart Generator (v3.3.0)
Generates clean, institutional TradingView-styled candlestick charts
matching TradingView's official desktop export format.
Features modern Royal Blue & Dark Slate candlesticks (zero classic red/green),
the Long/Short Position Tool, 20-EMA curve, and right-axis price flags.
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
    Renders a high-resolution, institutional TradingView chart export.

    Visual Specifications:
      - TradingView Dark Theme (#131722) canvas with subtle grid (#2A2E39).
      - Modern Institutional Palette (Zero classic red/green):
          • Bullish Candles: Modern Royal Blue (#2962FF).
          • Bearish Candles: Dark Slate / Charcoal (#363A45) with crisp silver outline (#787B86).
      - 20-EMA dynamic equilibrium curve (#FF9800).
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
          • Symbol & Timeframe: "{PAIR} · {TF} · FX_IDC"
          • Live OHLC Bar Data: "O ... H ... L ... C ..."
          • Indicator Title: "EMA 20 close 0"
    """
    if df is None or df.empty or len(df) < 5:
        logger.warning("generate_trade_chart: Insufficient candle data provided.")
        return None

    try:
        pair = sig.get("pair", "EURUSD").upper()
        is_long = sig.get("direction", "LONG").upper() == "LONG"
        timeframe = str(sig.get("timeframe", "15M")).upper().replace("M", "")

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

        # Calculate 20-EMA if not pre-computed
        if "ema20" not in plot_df.columns:
            plot_df["ema20"] = plot_df["close"].ewm(span=20, adjust=False).mean()

        # Clean 16:9 Desktop TradingView Export Aspect Ratio (13.0 x 7.2 in @ 150 DPI)
        fig = plt.figure(figsize=(13.0, 7.2), dpi=150, facecolor="#131722")
        ax = fig.add_axes([0.04, 0.08, 0.86, 0.84], facecolor="#131722")

        x = np.arange(n)
        w_candle = 0.62
        w_wick = 0.08

        # Color palette: Modern Institutional Royal Blue & Dark Slate
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
        ax.plot(x, plot_df["ema20"], color="#FF9800", linewidth=1.4, alpha=0.9, zorder=4)

        # TradingView Long / Short Position Tool Geometry
        if trade_status == "TP_HIT":
            box_width = min(24, n // 2)
            box_start = max(0, n - box_width - 2)
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

        # Diagonal dotted trajectory line
        ax.plot([box_start, box_end], [entry, tp], color="#2962FF", linestyle=":", linewidth=1.2, alpha=0.8, zorder=3)

        # Horizontal level lines
        ax.hlines(entry, box_start, box_end, colors="#D1D4DC", linestyles="--", linewidth=1.0, zorder=5)
        ax.hlines(tp, box_start, box_end, colors="#2962FF", linestyles="-", linewidth=1.2, zorder=5)
        ax.hlines(sl, box_start, box_end, colors="#787B86", linestyles="-", linewidth=1.2, zorder=5)

        # Current market price crosshair line
        ax.axhline(cur_px, color="#787B86", linestyle=":", linewidth=0.7, alpha=0.6, zorder=4)

        # Right Price Axis Formatting
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        ax.tick_params(colors="#787B86", labelsize=9, length=4)
        ax.grid(True, color="#2A2E39", linestyle="-", linewidth=0.5, alpha=0.6)

        # Right Axis Badges (Authentic TradingView Price Badges)
        ax.text(1.008, tp, f" {tp:.{digits}f} ", transform=ax.get_yaxis_transform(),
                color="#FFFFFF", backgroundcolor="#2962FF", fontsize=8.5, weight="bold", va="center")
        ax.text(1.008, entry, f" {entry:.{digits}f} ", transform=ax.get_yaxis_transform(),
                color="#131722", backgroundcolor="#D1D4DC", fontsize=8.5, weight="bold", va="center")
        ax.text(1.008, sl, f" {sl:.{digits}f} ", transform=ax.get_yaxis_transform(),
                color="#FFFFFF", backgroundcolor="#787B86", fontsize=8.5, weight="bold", va="center")
        ax.text(1.008, cur_px, f" {cur_px:.{digits}f} ", transform=ax.get_yaxis_transform(),
                color="#FFFFFF", backgroundcolor="#363A45", fontsize=8.5, weight="bold", va="center")

        # Bottom X-Axis Time Ticks
        step = max(1, n // 7)
        tick_locs = list(range(0, n, step))
        if plot_df.index is not None and hasattr(plot_df.index[0], "strftime"):
            tick_labels = [plot_df.index[i].strftime("%d %b %H:%M") for i in tick_locs]
            ax.set_xticks(tick_locs)
            ax.set_xticklabels(tick_labels, color="#787B86", fontsize=8.5)
        else:
            ax.set_xticks([])

        # Top-Left TradingView Header (Clean & Institutional)
        last_bar = plot_df.iloc[-1]
        o, h, l, c = last_bar["open"], last_bar["high"], last_bar["low"], last_bar["close"]
        ohlc_line = f"O {o:.{digits}f}   H {h:.{digits}f}   L {l:.{digits}f}   C {c:.{digits}f}"

        fig.text(0.045, 0.955, f"{pair} · {timeframe} · FX_IDC", fontsize=13, weight="bold", color="#D1D4DC")
        fig.text(0.045, 0.932, ohlc_line, fontsize=9.5, color="#787B86", fontfamily="monospace")
        fig.text(0.045, 0.910, "EMA 20 close 0", fontsize=9.0, color="#FF9800")

        # Set axis limits with clean padding
        ax.set_xlim(-1, max(n + 3, box_end + 12))
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
