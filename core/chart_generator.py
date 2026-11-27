"""
Quantitative Trade Chart Generator (v3.3.0)
Generates clean, institutional TradingView-styled candlestick charts
with Long/Short position boxes, 20-EMA dynamic equilibrium curves,
and high-resolution projection overlays for Telegram channel broadcasts.
"""

import io
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive headless backend
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logger = logging.getLogger("ChartGenerator")


def generate_trade_chart(
    df: pd.DataFrame,
    sig: Dict[str, Any],
    trade_status: str = "OPEN",
    bars_to_display: int = 55,
    projection_bars: int = 16
) -> Optional[bytes]:
    """
    Renders an institutional-grade TradingView-style chart with real market candles,
    20-EMA, and the Long/Short Position projection box.

    Args:
        df: DataFrame with datetime index and columns ['open', 'high', 'low', 'close']
        sig: Signal dictionary with ['pair', 'direction', 'entry', 'stop_loss', 'take_profit', 'sl_pips', 'tp_pips', 'rr']
        trade_status: 'OPEN' (entry signal) or 'TP_HIT' (take profit celebration)
        bars_to_display: Number of historical candles to show
        projection_bars: Width of the position tool box in candle bars

    Returns:
        PNG image bytes in memory, or None on error.
    """
    if df is None or df.empty or len(df) < 5:
        logger.warning("generate_trade_chart: Insufficient candle data provided.")
        return None

    try:
        pair = sig.get("pair", "FOREX")
        display_pair = f"{pair[:3]}/{pair[3:]}" if len(pair) == 6 else pair
        is_long = sig.get("direction", "LONG").upper() == "LONG"
        timeframe = str(sig.get("timeframe", "15M")).upper()

        entry = float(sig.get("entry", df.iloc[-1]["close"]))
        sl = float(sig.get("stop_loss", entry * (0.998 if is_long else 1.002)))
        tp = float(sig.get("take_profit", entry * (1.003 if is_long else 0.997)))
        sl_pips = float(sig.get("sl_pips", 20.0))
        tp_pips = float(sig.get("tp_pips", 35.0))
        rr_val = float(sig.get("rr", 1.75))

        # Precision formatting
        is_jpy = "JPY" in pair.upper()
        digits = 3 if is_jpy else 5

        # Take last N bars
        plot_df = df.iloc[-bars_to_display:].copy()
        n = len(plot_df)

        # 20-EMA calculation
        if "ema20" not in plot_df.columns:
            plot_df["ema20"] = plot_df["close"].ewm(span=20, adjust=False).mean()

        # Canvas Setup (TradingView Dark Palette)
        fig, ax = plt.subplots(figsize=(11.5, 6.2), dpi=150, facecolor="#131722")
        ax.set_facecolor("#131722")

        # Candlestick Geometry
        x = np.arange(n)
        candle_width = 0.58
        wick_width = 0.10

        up_mask = plot_df["close"] >= plot_df["open"]
        down_mask = plot_df["close"] < plot_df["open"]

        up_df = plot_df[up_mask]
        down_df = plot_df[down_mask]

        # Colors: TradingView Emerald (#089981) and Crimson (#F23645)
        up_color = "#089981"
        down_color = "#F23645"

        # Plot Bullish Candles
        if not up_df.empty:
            up_x = [plot_df.index.get_loc(idx) for idx in up_df.index]
            ax.bar(up_x, up_df["close"] - up_df["open"], candle_width, bottom=up_df["open"],
                   color=up_color, edgecolor=up_color, zorder=3)
            ax.bar(up_x, up_df["high"] - up_df["close"], wick_width, bottom=up_df["close"],
                   color=up_color, edgecolor=up_color, zorder=3)
            ax.bar(up_x, up_df["low"] - up_df["open"], wick_width, bottom=up_df["open"],
                   color=up_color, edgecolor=up_color, zorder=3)

        # Plot Bearish Candles
        if not down_df.empty:
            down_x = [plot_df.index.get_loc(idx) for idx in down_df.index]
            ax.bar(down_x, down_df["close"] - down_df["open"], candle_width, bottom=down_df["open"],
                   color=down_color, edgecolor=down_color, zorder=3)
            ax.bar(down_x, down_df["high"] - down_df["open"], wick_width, bottom=down_df["open"],
                   color=down_color, edgecolor=down_color, zorder=3)
            ax.bar(down_x, down_df["low"] - down_df["close"], wick_width, bottom=down_df["close"],
                   color=down_color, edgecolor=down_color, zorder=3)

        # Plot 20-EMA Dynamic Trendline
        ax.plot(x, plot_df["ema20"], color="#FF9800", linewidth=1.5, alpha=0.85, zorder=4)

        # Long / Short Position Tool Geometry (TradingView Style)
        box_start = n - 1
        box_end = box_start + projection_bars

        target_color = "#2962FF"   # TradingView Institutional Blue
        sl_color = "#787B86"       # Subtle Slate Grey

        if is_long:
            target_box = patches.Rectangle(
                (box_start, entry), projection_bars, tp - entry,
                linewidth=1.2, edgecolor=target_color, facecolor=target_color, alpha=0.25, zorder=2
            )
            sl_box = patches.Rectangle(
                (box_start, sl), projection_bars, entry - sl,
                linewidth=1.2, edgecolor=sl_color, facecolor=sl_color, alpha=0.22, zorder=2
            )
        else:
            target_box = patches.Rectangle(
                (box_start, tp), projection_bars, entry - tp,
                linewidth=1.2, edgecolor=target_color, facecolor=target_color, alpha=0.25, zorder=2
            )
            sl_box = patches.Rectangle(
                (box_start, entry), projection_bars, sl - entry,
                linewidth=1.2, edgecolor=sl_color, facecolor=sl_color, alpha=0.22, zorder=2
            )

        ax.add_patch(target_box)
        ax.add_patch(sl_box)

        # Horizontal Key Levels across Box
        ax.hlines(entry, box_start, box_end, colors="#FFFFFF", linestyles="--", linewidth=1.0, zorder=5)
        ax.hlines(tp, box_start, box_end, colors="#00E676", linestyles="-", linewidth=1.4, zorder=5)
        ax.hlines(sl, box_start, box_end, colors="#FF5252", linestyles="-", linewidth=1.4, zorder=5)

        # Diagonal Projection Trajectory
        ax.plot([box_start, box_end], [entry, tp], color=target_color, linestyle=":", linewidth=1.2, alpha=0.7, zorder=4)

        # Level Price Badges (Right Margins)
        ax.text(box_end + 0.6, tp, f" TP: {tp:.{digits}f} (+{tp_pips:.1f}p · +{rr_val:.2f}R)",
                color="#00E676", fontsize=8.5, va="center", weight="bold")
        ax.text(box_end + 0.6, entry, f" Entry: {entry:.{digits}f}",
                color="#FFFFFF", fontsize=8.5, va="center")
        ax.text(box_end + 0.6, sl, f" SL: {sl:.{digits}f} (-{sl_pips:.1f}p)",
                color="#FF5252", fontsize=8.5, va="center", weight="bold")

        # Format Right-Side Price Axis
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position("right")
        ax.tick_params(colors="#787B86", labelsize=8, length=4)
        ax.grid(True, color="#2A2E39", linestyle="--", linewidth=0.5, alpha=0.6)

        # Format Bottom Time Axis
        step = max(1, n // 6)
        tick_locs = list(range(0, n, step))
        if plot_df.index is not None and hasattr(plot_df.index[0], "strftime"):
            tick_labels = [plot_df.index[i].strftime("%H:%M") for i in tick_locs]
            ax.set_xticks(tick_locs)
            ax.set_xticklabels(tick_labels, color="#787B86", fontsize=8)
        else:
            ax.set_xticks([])

        # Header Titles & Status
        ax.text(0.02, 0.95, f"QuantFlow Institutional FX  |  {display_pair}  •  {timeframe}",
                transform=ax.transAxes, color="#FFFFFF", fontsize=12, weight="bold", va="top")

        if trade_status == "TP_HIT":
            status_text = f"[TAKE PROFIT RESOLVED] · +{rr_val:.2f}R PROFIT LOCKED"
            status_color = "#00E676"
        else:
            action_desc = "BUY / LONG SETUP" if is_long else "SELL / SHORT SETUP"
            status_text = f"{action_desc} · Risk/Reward 1:{rr_val:.2f} · 20-EMA Equilibrium Confluence"
            status_color = "#00E676" if is_long else "#FF5252"

        ax.text(0.02, 0.89, status_text, transform=ax.transAxes,
                color=status_color, fontsize=9.5, weight="bold", va="top")

        # Watermark
        ax.text(0.98, 0.03, "QuantFlow VIP Club · Systematic Alpha Engine", transform=ax.transAxes,
                color="#787B86", fontsize=7.5, ha="right", va="bottom", style="italic")

        # Axis Limits with Padding
        ax.set_xlim(-1, box_end + 14)
        min_price = min(plot_df["low"].min(), sl, tp)
        max_price = max(plot_df["high"].max(), sl, tp)
        padding = (max_price - min_price) * 0.10
        ax.set_ylim(min_price - padding, max_price + padding)

        plt.tight_layout()

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
