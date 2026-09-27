#!/usr/bin/env python3
"""
Session Range Breakout v1 - ONE engine for backtest, shadow and live trading.

WHY THIS REPLACES THE SWEEP/MSS SCRIPT
The previous script traded ICT/SMC concepts (liquidity sweep -> displacement -> MSS -> OTE
retrace). Even sympathetic writeups of that concept say plainly: the behaviour (stop hunts at
obvious levels) is real, but no peer-reviewed study validates the specific ICT rules or win
rates - it's a plausible story, not a documented mechanism. It also needed four timeframes and
a dozen parameters, which is a lot of surface area to accidentally overfit.

This strategy is a much older, simpler idea with more of a track record: the low-liquidity Asian
session compresses into a range; when the more liquid London/NY session arrives, price often
breaks that range and continues. A widely-read multi-year study of "opening range breakout" on
other liquid markets found a real edge that did NOT come from a high win rate - it came from
cutting losers fast at the other side of the range and letting winners run. That's the shape this
script targets: aim for roughly a coin-flip win rate with a payoff skewed by the R-multiple, not
an 80% win rate. There is no FX-specific peer-reviewed study behind this exact rule set either -
treat this as a materially more defensible hypothesis to test, not a proven edge.

WHAT'S THE SAME AS BEFORE (because it already proved itself)
  * Event-driven, closed-bar-only engine - can't see a bar before it closes.
  * A random-walk self-test + causality check that must pass before you trust any backtest.
  * Realistic costs (spread/commission/slippage), one-trade-per-symbol-per-day, portfolio caps
    (max concurrent, max same-USD-side, daily loss limit).
  * In/out-of-sample split, cost-stress test, parameter sensitivity, filter ablation.
  * A live runner with a demo-only guard, kill file, drawdown/daily-loss halts.

THE SIGNAL, IN PLAIN WORDS
  1. Build a range from the Asian session (default 00:00-07:00 UTC) using H1 bars.
  2. Skip the day if that range is too tight (noise) or too wide (already trended out) relative
     to the pair's own recent average daily range, or if yesterday's volatility was unusually low.
  3. Skip a direction that fights a clear D1 trend (old technical-analysis idea, unrelated to ICT).
  4. Arm a buy-stop above the range high and a sell-stop below the range low, both with a small
     buffer so a 1-pip poke doesn't count as a breakout. Whichever triggers first (on M15 bars,
     before an entry cutoff hour) is the trade; the other side is cancelled.
  5. Stop-loss at the opposite side of the range. Once price is `breakeven_at_r` in profit, the
     stop moves to entry (cut losers fast). Target is `tp_r` x the risk, or flatten by a fixed
     session/Friday cutoff or a max holding time (let winners run, but not forever).

Usage
  python session_breakout_v1.py selftest
  python session_breakout_v1.py backtest [--start 2022-01-01 --end 2026-09-15 --cache]
  python session_breakout_v1.py sensitivity [--cache]
  python session_breakout_v1.py shadow            # live data, logs signals, places NO orders
  python session_breakout_v1.py live              # places orders; demo account only unless --allow-real

Nothing here is investment advice, and no backtest - however carefully built - guarantees live
profitability. Run shadow mode and demo trading before risking real money.
"""
from __future__ import annotations

import argparse
import math
import os
import pickle
import sys
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:  # backtest logic and selftest still run without MT5
    mt5 = None

UTC = timezone.utc


# ============================================================================ CONFIG
@dataclass(frozen=True)
class Cfg:
    pairs: tuple = ("USDJPY", "EURUSD", "GBPUSD", "USDCHF", "AUDUSD", "USDCAD")
    start: str = "2022-01-01"          # fixed dates => reproducible results; widen this, not just pairs
    end: str = "2026-09-15"

    # --- session range (UTC broker/server hours - check your broker's server-time offset)
    range_start_hour: int = 0          # Asian session start
    range_end_hour: int = 7            # range closes here; breakout watch begins immediately after
    entry_cutoff_hour: int = 12        # stop arming new breakouts after this hour (avoid late chases)
    session_flat_hour: int = 20        # force-close any open position / drop stale arming by this hour
    friday_flat_hour: int = 20

    # --- range quality, as a FRACTION of the pair's own trailing 20-day average daily range
    # (fractions instead of raw pips so one config works across JPY and non-JPY pairs)
    min_range_frac: float = 0.15       # below this, the "range" is just noise
    max_range_frac: float = 0.65       # above this, the day already used up its typical range
    breakout_buffer_frac: float = 0.05
    sl_buffer_frac: float = 0.05

    # --- trade management: cut losers fast, let winners run (this is what the ORB research
    # attributes the edge to, more than the win rate)
    breakeven_at_r: float = 1.0        # move stop to entry once price is this many R in profit
    tp_r: float = 3.0
    max_hold_hours: int = 10

    # --- regime filters (kept from the prior script: HTF alignment showed the clearest signal
    # in your last ablation; the volatility filter also looked like it was pulling weight)
    htf_filter: bool = True
    htf_trend_days: int = 10
    htf_neutral_band: float = 0.10
    atr_percentile_filter: bool = True
    atr_percentile_lookback: int = 60
    atr_percentile_min: float = 0.20

    # --- hygiene
    max_spread_to_risk: float = 0.15
    blackout_windows: tuple = ((0, 12, 14), (1, 12, 14), (2, 12, 14), (3, 12, 14), (4, 12, 14))
                                        # (weekday0=Mon, hour_start, hour_end) UTC: a blunt Mon-Fri
                                        # 12:00-14:00 UTC guard, since most high-impact USD data
                                        # (NFP, CPI, retail sales, GDP) lands at 12:30 or 13:30 UTC.
                                        # Replace with real event times for anything more precise.

    # --- costs (cost_mult scales all of them: 0 = gross, 2 = stress test)
    min_spread_pips: float = 0.2
    slippage_pips: float = 0.3
    commission_pips: float = 0.7       # round turn, pip-equivalent (~$7/lot on majors)
    cost_mult: float = 1.0

    # --- portfolio rules
    max_concurrent: int = 3
    max_same_usd_side: int = 2
    daily_loss_limit_r: float = 3.0

    # --- live only
    risk_pct: float = 0.25             # % of equity risked per trade
    live_daily_loss_pct: float = 1.0
    live_max_dd_pct: float = 6.0
    poll_seconds: int = 20             # how often the live loop polls MT5 for BE-move/flat checks
    magic: int = 515151
    kill_file: str = "STOP.txt"


def dt(t) -> datetime:
    return datetime.fromtimestamp(t, tz=UTC)


def specs(symbol: str):
    if mt5 is not None:
        try:
            info = mt5.symbol_info(symbol)
        except Exception:
            info = None
        if info is not None:
            pip = info.point * 10 if info.digits in (3, 5) else info.point
            return pip, info.point
    pip = 0.01 if symbol.endswith("JPY") else 0.0001
    return pip, pip / 10


def usd_side(symbol: str, side: int) -> int:
    if symbol.startswith("USD"):
        return side
    if symbol.endswith("USD"):
        return -side
    return 0


def bars_of(df: pd.DataFrame):
    sp = df["spread"] if "spread" in df else pd.Series(0.0, index=df.index)
    return list(zip(df["time"].astype("int64").tolist(), df["open"].tolist(), df["high"].tolist(),
                    df["low"].tolist(), df["close"].tolist(), df["tick_volume"].astype(float).tolist(),
                    sp.astype(float).tolist()))


def build_daily_ctx(d1: pd.DataFrame, cfg: Cfg) -> dict:
    """date -> {trend, atr_pct, avg_rng}, using only bars strictly before that date (causal).
    trend: +1/-1/0, from the D1 close vs `htf_trend_days` ago, scaled by the recent daily range.
    atr_pct: percentile rank (0..1) of yesterday's daily range within its own trailing history.
    avg_rng: trailing 20-day average daily range, used to size the session range as a fraction.
    Weekend stub bars are dropped, so Monday's 'previous day' is Friday."""
    d = d1.sort_values("time").reset_index(drop=True)
    ts = pd.to_datetime(d["time"], unit="s")
    d = d[ts.dt.weekday < 5].reset_index(drop=True)
    dates = pd.to_datetime(d["time"], unit="s").dt.date.tolist()
    hi, lo, cl = d["high"].to_numpy(), d["low"].to_numpy(), d["close"].to_numpy()
    rng = hi - lo
    ctx = {}
    for i in range(1, len(d)):
        trend, atr_pct, avg_rng = 0, 1.0, float("nan")
        if i - 1 >= 20:
            avg_rng = float(rng[i - 21:i - 1].mean())
        if i > cfg.htf_trend_days and avg_rng == avg_rng and avg_rng > 0:
            move = cl[i - 1] - cl[i - 1 - cfg.htf_trend_days]
            slope = move / (cfg.htf_trend_days * avg_rng)
            trend = 1 if slope > cfg.htf_neutral_band else (-1 if slope < -cfg.htf_neutral_band else 0)
        lb = cfg.atr_percentile_lookback
        if i - 1 >= lb:
            hist = rng[i - 1 - lb:i - 1]
            atr_pct = float((hist < rng[i - 1]).mean())
        ctx[dates[i]] = {"trend": trend, "atr_pct": atr_pct, "avg_rng": avg_rng}
    return ctx


# ============================================================================ ENGINE
@dataclass
class Signal:
    symbol: str
    side: int             # +1 long, -1 short
    t: int                # epoch of the triggering M15 bar's OPEN
    trigger: float         # raw (no-cost) stop-order price
    sl: float               # raw stop-loss price


class Engine:
    """Pure signal logic on CLOSED bars only - no cost model, no fills. Feed it H1 bars, then
    M15 bars, in true close-time order (see run_symbol for exactly why the tie-break matters)."""

    def __init__(self, symbol, cfg: Cfg, daily_ctx):
        self.symbol, self.cfg, self.ctx = symbol, cfg, daily_ctx
        self.day = None
        self.range_hi = self.range_lo = None
        self.armed = False
        self.long_trigger = self.short_trigger = None
        self.sl_long = self.sl_short = None
        self.log = []

    def on_h1(self, bar):
        t, o, h, l, c, v, _ = bar
        d = dt(t)
        day = d.date()
        if day != self.day:
            self.day, self.range_hi, self.range_lo, self.armed = day, None, None, False
            self.long_trigger = self.short_trigger = None
        cfg = self.cfg
        if cfg.range_start_hour <= d.hour < cfg.range_end_hour:
            self.range_hi = h if self.range_hi is None else max(self.range_hi, h)
            self.range_lo = l if self.range_lo is None else min(self.range_lo, l)
            if d.hour == cfg.range_end_hour - 1:      # last bar of the range just closed -> arm
                self._arm(day)

    def _arm(self, day):
        cfg, ctx = self.cfg, self.ctx.get(day)
        if ctx is None or self.range_hi is None or self.range_lo is None:
            return
        avg_rng = ctx["avg_rng"]
        if not (avg_rng == avg_rng) or avg_rng <= 0:      # NaN-safe: not enough D1 history yet
            return
        width = self.range_hi - self.range_lo
        if width <= 0 or not (cfg.min_range_frac <= width / avg_rng <= cfg.max_range_frac):
            return
        if cfg.atr_percentile_filter and ctx["atr_pct"] < cfg.atr_percentile_min:
            return
        trend = ctx["trend"]
        long_ok = not (cfg.htf_filter and trend == -1)
        short_ok = not (cfg.htf_filter and trend == 1)
        if not long_ok and not short_ok:
            return
        buf, slbuf = avg_rng * cfg.breakout_buffer_frac, avg_rng * cfg.sl_buffer_frac
        self.long_trigger = (self.range_hi + buf) if long_ok else None
        self.short_trigger = (self.range_lo - buf) if short_ok else None
        self.sl_long, self.sl_short = self.range_lo - slbuf, self.range_hi + slbuf
        self.armed = True

    def on_m15(self, bar) -> Optional[Signal]:
        if not self.armed:
            return None
        t, o, h, l, c, v, _ = bar
        d = dt(t)
        if d.hour >= self.cfg.entry_cutoff_hour:
            self.armed = False
            self.long_trigger = self.short_trigger = None
            return None
        hit_long = self.long_trigger is not None and h >= self.long_trigger
        hit_short = self.short_trigger is not None and l <= self.short_trigger
        if not hit_long and not hit_short:
            return None
        self.armed = False
        if hit_long and hit_short:                        # one bar spans both triggers: pick the
            hit_long = abs(o - self.long_trigger) <= abs(o - self.short_trigger)  # side nearer the open
            hit_short = not hit_long
        sig = Signal(self.symbol, 1 if hit_long else -1, t,
                    self.long_trigger if hit_long else self.short_trigger,
                    self.sl_long if hit_long else self.sl_short)
        self.long_trigger = self.short_trigger = None
        self.log.append(sig)
        return sig


# ============================================================================ SIMULATOR
class Sim:
    """Broker stand-in for backtests. Chart bars are BID prices:
    long  : stop-fills at (raw trigger + spread) i.e. the ask; SL/TP trigger on bid.
    short : stop-fills at the raw trigger (bid); SL/TP trigger on ask (bid + spread).
    Entry-bar SL is checked like any other bar (a stop order can immediately reverse)."""

    def __init__(self, symbol, cfg: Cfg, pip, point):
        self.symbol, self.cfg, self.pip, self.point = symbol, cfg, pip, point
        self.pos: Optional[dict] = None
        self.trades = []

    def _spread(self, sp):
        return self.cfg.cost_mult * max(sp * self.point, self.cfg.min_spread_pips * self.pip)

    def on_m15(self, bar, sig: Optional[Signal]):
        t, o, h, l, c, v, sp = bar
        s = self._spread(sp)
        slip = self.cfg.cost_mult * self.cfg.slippage_pips * self.pip
        if self.pos is None and sig is not None:
            # A stop order that triggers intra-bar can't be assumed to fill at the pristine
            # threshold if the bar's OWN close ended up further past it - that would silently
            # credit the rest of the bar's favorable move as "free" post-entry profit, when it's
            # really part of the same triggering event. Price at the worst of trigger/open/close.
            if sig.side > 0:
                raw = max(sig.trigger, o, c)
                entry = raw + s + slip
            else:
                raw = min(sig.trigger, o, c)
                entry = raw - slip
            risk = (entry - sig.sl) if sig.side > 0 else (sig.sl - entry)
            if risk > 0 and s / risk <= self.cfg.max_spread_to_risk:
                tp = entry + self.cfg.tp_r * risk if sig.side > 0 else entry - self.cfg.tp_r * risk
                self.pos = dict(side=sig.side, entry=entry, cur_sl=sig.sl, tp=tp, risk=risk,
                                be_moved=False, t_entry=t)
        if self.pos is not None:
            self._manage(bar, s)

    def _manage(self, bar, s):
        t, o, h, l, c, v, _ = bar
        pos, cfg = self.pos, self.cfg
        slip = cfg.cost_mult * cfg.slippage_pips * self.pip
        d = dt(t)
        friday = d.weekday() == 4 and d.hour >= cfg.friday_flat_hour
        timed_out = (t - pos["t_entry"]) >= cfg.max_hold_hours * 3600
        session_flat = d.hour >= cfg.session_flat_hour
        px = outcome = None
        if pos["side"] > 0:
            if l <= pos["cur_sl"]:
                raw = min(pos["cur_sl"], o, c)
                px, outcome = raw - slip, ("be_stop" if pos["be_moved"] else "sl")
            elif h >= pos["tp"]:
                px, outcome = pos["tp"], "tp"
            elif not pos["be_moved"] and h - pos["entry"] >= cfg.breakeven_at_r * pos["risk"]:
                pos["cur_sl"], pos["be_moved"] = pos["entry"], True
        else:
            if h + s >= pos["cur_sl"]:
                raw = max(pos["cur_sl"], o + s, c + s)
                px, outcome = raw + slip, ("be_stop" if pos["be_moved"] else "sl")
            elif l + s <= pos["tp"]:
                px, outcome = pos["tp"], "tp"
            elif not pos["be_moved"] and pos["entry"] - l >= cfg.breakeven_at_r * pos["risk"]:
                pos["cur_sl"], pos["be_moved"] = pos["entry"], True
        if px is None and (friday or timed_out or session_flat):
            outcome = "friday_flat" if friday else ("timeout" if timed_out else "session_flat")
            px = (c - slip) if pos["side"] > 0 else (c + s + slip)
        if px is None:
            return
        gross = (px - pos["entry"]) if pos["side"] > 0 else (pos["entry"] - px)
        comm = cfg.cost_mult * cfg.commission_pips * self.pip
        self.trades.append(dict(symbol=self.symbol, side=pos["side"], t_entry=pos["t_entry"], t_exit=t,
                                entry=pos["entry"], exit=px, sl=pos["cur_sl"], tp=pos["tp"], outcome=outcome,
                                r=(gross - comm) / pos["risk"], risk_pips=pos["risk"] / self.pip))
        self.pos = None


def run_symbol(symbol, data, cfg: Cfg):
    pip, point = specs(symbol)
    eng = Engine(symbol, cfg, build_daily_ctx(data["D1"], cfg))
    sim = Sim(symbol, cfg, pip, point)
    h1, m15 = bars_of(data["H1"]), bars_of(data["M15"])
    t = np.concatenate([np.array([b[0] for b in h1]) + 3600, np.array([b[0] for b in m15]) + 900])
    # tie-break: at an identical close time, M15 is processed BEFORE H1. The M15 bar that closes at
    # exactly range_end_hour:00 is part of the SAME window used to build the range (it opened before
    # range_end_hour), so it must be evaluated while still un-armed - otherwise a level would be
    # checked against the very bar that helped define it.
    prio = np.concatenate([np.ones(len(h1)), np.zeros(len(m15))])
    idx = np.concatenate([np.arange(len(h1)), np.arange(len(m15))])
    order = np.lexsort((prio, t))
    for p, i in zip(prio[order].tolist(), idx[order].tolist()):
        if p == 1:
            eng.on_h1(h1[i])
        else:
            sig = eng.on_m15(m15[i])
            sim.on_m15(m15[i], sig)
    return sim.trades, eng.log


def apply_portfolio_rules(trades, cfg: Cfg):
    kept = []
    for tr in sorted(trades, key=lambda x: x["t_entry"]):
        t, recent = tr["t_entry"], kept[-200:]
        open_ = [k for k in recent if k["t_exit"] > t]
        if len(open_) >= cfg.max_concurrent:
            continue
        u = usd_side(tr["symbol"], tr["side"])
        if u and sum(1 for k in open_ if usd_side(k["symbol"], k["side"]) == u) >= cfg.max_same_usd_side:
            continue
        day = dt(t).date()
        if sum(k["r"] for k in recent if k["t_exit"] <= t and dt(k["t_exit"]).date() == day) <= -cfg.daily_loss_limit_r:
            continue
        kept.append(tr)
    return kept


def evaluate(data_by_symbol, cfg: Cfg):
    trades = []
    for sym, data in data_by_symbol.items():
        trades += run_symbol(sym, data, cfg)[0]
    t0 = int(datetime.fromisoformat(cfg.start).replace(tzinfo=UTC).timestamp())
    trades = [x for x in trades if x["t_entry"] >= t0]
    return pd.DataFrame(apply_portfolio_rules(trades, cfg))


# ============================================================================ REPORTING
def summarize(df, title):
    print(f"\n=== {title} ===")
    if df is None or df.empty:
        print("no trades")
        return None
    r = df["r"].to_numpy()
    n = len(r)
    wins, loss = r[r > 0], r[r <= 0]
    pf = wins.sum() / abs(loss.sum()) if loss.sum() < 0 else float("inf")
    eq = np.cumsum(r)
    dd = float((np.maximum.accumulate(eq) - eq).max())
    streak = cur = 0
    for x in r:
        cur = cur + 1 if x <= 0 else 0
        streak = max(streak, cur)
    rng = np.random.default_rng(0)
    lo, hi = np.percentile([rng.choice(r, n).mean() for _ in range(2000)], [2.5, 97.5])
    print(f"trades {n} | win% {100 * len(wins) / n:.1f} | avg win {wins.mean() if len(wins) else 0:.2f}R "
          f"| avg loss {loss.mean() if len(loss) else 0:.2f}R")
    print(f"expectancy {r.mean():+.3f}R (95% CI {lo:+.3f}..{hi:+.3f}) | total {r.sum():+.1f}R "
          f"| PF {pf:.2f} | max DD {dd:.1f}R | longest loss streak {streak}")
    print("outcomes:", df["outcome"].value_counts().to_dict())
    return float(r.mean()), float(lo), float(hi)


def report(df):
    summarize(df, "ALL TRADES (net of costs)")
    if df.empty:
        return
    print("\nPer symbol (R):")
    print(df.groupby("symbol")["r"].agg(["count", "sum", "mean"]).round(2))
    m = pd.to_datetime(df["t_exit"], unit="s").dt.to_period("M")
    tab = df.groupby(m)["r"].agg(["count", "sum", "mean"]).round(2)
    print("\nPer month (R):")
    print(tab)
    print(f"months positive: {(tab['sum'] > 0).sum()}/{len(tab)}")
    d = df.sort_values("t_entry")
    k = int(len(d) * 0.7)
    summarize(d.iloc[:k], "first 70% of trades (in-sample: tune ONLY here, if at all)")
    summarize(d.iloc[k:], "last 30% of trades (out-of-sample: look, never tune)")


def sensitivity(data, cfg):
    base = evaluate(data, cfg)
    print(f"\nbase: n={len(base)} expectancy={base['r'].mean() if len(base) else float('nan'):+.3f} "
          f"total={base['r'].sum() if len(base) else 0:+.1f}R")
    knobs = ["min_range_frac", "max_range_frac", "breakout_buffer_frac", "sl_buffer_frac",
             "breakeven_at_r", "tp_r", "atr_percentile_min"]
    print(f"{'param':20s}{'x0.8':>26s}{'x1.2':>26s}")
    for k in knobs:
        cells = []
        for mult in (0.8, 1.2):
            df = evaluate(data, replace(cfg, **{k: getattr(cfg, k) * mult}))
            cells.append(f"n={len(df):4d} E={df['r'].mean() if len(df) else float('nan'):+.3f} "
                         f"T={df['r'].sum() if len(df) else 0:+7.1f}")
        print(f"{k:20s}{cells[0]:>26s}{cells[1]:>26s}")
    print("\nWant a plateau, not a peak: if a small nudge flips the sign of expectancy, that's noise, not edge.")


# ============================================================================ DATA
def tf_const(name):
    return {"D1": mt5.TIMEFRAME_D1, "H1": mt5.TIMEFRAME_H1, "M15": mt5.TIMEFRAME_M15}[name]


def mt5_connect():
    if mt5 is None:
        sys.exit("MetaTrader5 package not available (Windows only: pip install MetaTrader5).")
    if not mt5.initialize():
        sys.exit(f"MT5 init failed: {mt5.last_error()}")


def fetch_range(symbol, tf, start, end, chunk_days):
    frames, cur, failed = [], start, 0
    while cur < end:
        nxt = min(cur + timedelta(days=chunk_days), end)
        r = mt5.copy_rates_range(symbol, tf_const(tf), cur, nxt)
        if r is not None and len(r):
            frames.append(pd.DataFrame(r))
        else:
            failed += 1
        cur = nxt
    if failed:
        print(f"    [{symbol} {tf}] {failed} empty chunk(s)")
    if not frames:
        return None
    return pd.concat(frames).drop_duplicates("time").sort_values("time").reset_index(drop=True)


def load_symbol(symbol, cfg: Cfg):
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"cannot select {symbol}")
    s = datetime.fromisoformat(cfg.start).replace(tzinfo=UTC)
    e = datetime.fromisoformat(cfg.end).replace(tzinfo=UTC)
    out = {}
    for tf, chunk, pad in [("D1", 3650, 40), ("H1", 365, 3), ("M15", 180, 2)]:
        df = fetch_range(symbol, tf, s - timedelta(days=pad), e, chunk)
        if df is None:
            raise RuntimeError(f"{symbol}: no {tf} data for this range")
        out[tf] = df
    print(f"  {symbol}: " + " ".join(f"{k}:{len(v)}" for k, v in out.items()))
    return out


def load_all(cfg: Cfg, use_cache=False):
    cache = "data_cache_orb.pkl"
    key = (cfg.pairs, cfg.start, cfg.end)
    if use_cache and os.path.exists(cache):
        with open(cache, "rb") as f:
            k, data = pickle.load(f)
        if k == key:
            return data
    mt5_connect()
    data = {p: load_symbol(p, cfg) for p in cfg.pairs}
    mt5.shutdown()
    if use_cache:
        with open(cache, "wb") as f:
            pickle.dump((key, data), f)
    return data


def synthetic_data(symbol, cfg: Cfg, days=400, seed=7):
    """Driftless M15 random walk, resampled up to H1/D1. A sound backtester must NOT find an
    edge here."""
    rng = np.random.default_rng(seed + sum(map(ord, symbol)))
    pip, _ = specs(symbol)
    idx = pd.date_range("2022-01-03", periods=days * 96, freq="15min")
    idx = idx[idx.weekday < 5]
    n = len(idx)
    ret = rng.normal(0, 2.0 * pip * math.sqrt(15 / 3), n)
    close = (150.0 if symbol.endswith("JPY") else 1.1) + np.cumsum(ret)
    open_ = np.concatenate([[close[0] - ret[0]], close[:-1]])
    wick = np.abs(rng.normal(0, 1.0 * pip, (2, n)))
    base = pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + wick[0],
                         "low": np.minimum(open_, close) - wick[1], "close": close,
                         "tick_volume": rng.integers(40, 200, n), "spread": 12.0}, index=idx)

    def to_epoch(ix):
        return ix.values.astype("datetime64[s]").astype("int64")

    def agg(rule):
        g = base.resample(rule, label="left", closed="left")
        out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                            "close": g["close"].last(), "tick_volume": g["tick_volume"].sum(),
                            "spread": g["spread"].mean()}).dropna()
        out["time"] = to_epoch(out.index)
        return out.reset_index(drop=True)

    m15 = base.copy()
    m15["time"] = to_epoch(m15.index)
    return {"D1": agg("1D"), "H1": agg("60min"), "M15": m15.reset_index(drop=True)}


# ============================================================================ COMMANDS (offline)
def cmd_backtest(cfg: Cfg, use_cache):
    data = load_all(cfg, use_cache)
    print(f"\nBacktest {cfg.start} .. {cfg.end}  pairs={cfg.pairs}")
    df = evaluate(data, cfg)
    report(df)
    if not df.empty:
        df.assign(t_entry=pd.to_datetime(df["t_entry"], unit="s"), t_exit=pd.to_datetime(df["t_exit"], unit="s")) \
            .to_csv("backtest_orb_trades.csv", index=False)
    for mult, label in ((0.0, "GROSS (no costs)"), (2.0, "STRESS (costs x2)")):
        summarize(evaluate(data, replace(cfg, cost_mult=mult)), label)
    print("\n--- What each filter is doing on THIS data (baseline above = all filters as configured) ---")
    for name in ("htf_filter", "atr_percentile_filter"):
        summarize(evaluate(data, replace(cfg, **{name: False})), f"same run with {name} DISABLED")
    print("\nSaved backtest_orb_trades.csv. Real edge = positive expectancy net of costs, a CI that "
          "mostly clears zero, survives x2 costs, and holds in the out-of-sample slice.")


def cmd_selftest(cfg: Cfg):
    cfg = replace(cfg, start="2022-01-01")
    data = {p: synthetic_data(p, cfg) for p in cfg.pairs}
    print("Self-test on driftless random-walk data (no real edge exists here)")
    net = summarize(evaluate(data, cfg), "random walk, NET of costs")
    gross = summarize(evaluate(data, replace(cfg, cost_mult=0.0)), "random walk, GROSS")
    ok = True
    if gross and gross[1] > 0:
        ok = False
        print("FAIL: significantly profitable gross on random data -> look-ahead or simulator bug")
    if net and net[0] > 0.05:
        ok = False
        print("FAIL: net expectancy clearly positive on random data")
    sym = cfg.pairs[0]
    d = data[sym]
    cut = int(np.median(d["H1"]["time"]) // 3600 * 3600)
    part = {"D1": d["D1"][d["D1"]["time"] <= cut], "H1": d["H1"][d["H1"]["time"] + 3600 <= cut],
            "M15": d["M15"][d["M15"]["time"] + 900 <= cut]}
    full_sigs = [x for x in run_symbol(sym, d, cfg)[1] if x.t <= cut]
    part_sigs = run_symbol(sym, part, cfg)[1]
    same = full_sigs == part_sigs
    print(f"\nCausality check ({sym}): signals before the cut are identical with and without future "
          f"data: {'PASS' if same else 'FAIL'} ({len(full_sigs)} signals)")
    ok &= same
    print("\nSELFTEST", "PASSED" if ok else "FAILED")
    return ok


# ============================================================================ LIVE / SHADOW
def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with open("live_log.txt", "a") as f:
        f.write(line + "\n")


def side_of(t):
    return 1 if t in (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_BUY_LIMIT) else -1


def mine(items, cfg):
    return [x for x in (items or []) if x.magic == cfg.magic]


def lots_for(info, risk_money, dist):
    per_lot = dist / info.trade_tick_size * info.trade_tick_value
    if per_lot <= 0:
        return 0.0
    step = info.volume_step
    lots = math.floor(risk_money / per_lot / step + 1e-9) * step
    if lots < info.volume_min:
        return 0.0
    return round(min(lots, info.volume_max), max(0, round(-math.log10(step))))


def halted(cfg, st):
    if os.path.exists(cfg.kill_file):
        return "kill file present"
    acc = mt5.account_info()
    st["peak"] = max(st.get("peak", acc.equity), acc.equity)
    if acc.equity <= st["peak"] * (1 - cfg.live_max_dd_pct / 100):
        return f"drawdown >= {cfg.live_max_dd_pct}% from peak equity"
    now = datetime.now(UTC)
    deals = mt5.history_deals_get(now - timedelta(hours=27), now + timedelta(hours=3)) or []
    pnl = sum(d.profit + d.commission + d.swap + getattr(d, "fee", 0.0) for d in mine(deals, cfg))
    if pnl <= -cfg.live_daily_loss_pct / 100 * acc.equity:
        return f"rolling-24h loss limit hit ({pnl:.2f})"
    return None


def exposure_ok(cfg, sym, side):
    items = mine(mt5.orders_get(), cfg) + mine(mt5.positions_get(), cfg)
    if len(items) >= cfg.max_concurrent:
        return False
    u = usd_side(sym, side)
    return not (u and sum(1 for x in items if usd_side(x.symbol, side_of(x.type)) == u) >= cfg.max_same_usd_side)


def in_blackout(cfg, t):
    d = dt(t)
    return any(d.weekday() == wd and h0 <= d.hour < h1 for wd, h0, h1 in cfg.blackout_windows)


def place_straddle(cfg, symbol, eng: Engine, st):
    """Called once, right when the H1 range closes and the engine arms. Places the actual
    buy-stop/sell-stop bracket orders at the broker with SL/TP attached."""
    if not eng.armed:
        return
    why = halted(cfg, st)
    if why:
        return log(f"{symbol}: range armed but trading halted: {why}")
    if in_blackout(cfg, time.time()):
        return log(f"{symbol}: range armed but inside a news blackout window - skipping this session")
    info, tick = mt5.symbol_info(symbol), mt5.symbol_info_tick(symbol)
    spread = tick.ask - tick.bid
    equity = mt5.account_info().equity
    for side, trigger, sl in ((1, eng.long_trigger, eng.sl_long), (-1, eng.short_trigger, eng.sl_short)):
        if trigger is None:
            continue
        price = trigger + spread if side > 0 else trigger
        dist = abs(price - sl)
        min_dist = info.trade_stops_level * info.point
        if spread / dist > cfg.max_spread_to_risk or dist < min_dist:
            log(f"{symbol}: {'buy' if side>0 else 'sell'}-stop skipped, spread/stop-level guard")
            continue
        if not exposure_ok(cfg, symbol, side):
            log(f"{symbol}: {'buy' if side>0 else 'sell'}-stop skipped, exposure limits")
            continue
        lots = lots_for(info, equity * cfg.risk_pct / 100, dist)
        if lots <= 0:
            log(f"{symbol}: {'buy' if side>0 else 'sell'}-stop skipped, min lot exceeds risk budget")
            continue
        tp = price + cfg.tp_r * dist if side > 0 else price - cfg.tp_r * dist
        req = {"action": mt5.TRADE_ACTION_PENDING, "symbol": symbol, "volume": lots,
               "type": mt5.ORDER_TYPE_BUY_STOP if side > 0 else mt5.ORDER_TYPE_SELL_STOP,
               "price": round(price, info.digits), "sl": round(sl, info.digits), "tp": round(tp, info.digits),
               "magic": cfg.magic, "comment": "orb_v1", "type_time": mt5.ORDER_TIME_DAY,
               "type_filling": mt5.ORDER_FILLING_RETURN}
        res = mt5.order_send(req)
        ok = res is not None and res.retcode == mt5.TRADE_RETCODE_DONE
        log(("PLACED: " if ok else f"ORDER FAILED ({getattr(res, 'retcode', None)} "
             f"{getattr(res, 'comment', mt5.last_error())}): ") +
            f"{symbol} {'BUY' if side > 0 else 'SELL'} STOP {price:.{info.digits}f} sl {sl:.{info.digits}f} "
            f"tp {tp:.{info.digits}f} lots {lots}")


def cancel_unfilled(cfg, symbol):
    for o in mine(mt5.orders_get(symbol=symbol), cfg):
        mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
        log(f"{symbol}: cancelled unfilled order {o.ticket} (entry window closed)")


def manage_position(cfg, symbol, p, be_moved: dict):
    """Poll-based breakeven move (MT5 has no native 'move SL to entry at +1R' order type) plus
    a session/Friday/max-hold flatten."""
    tick, buy = mt5.symbol_info_tick(symbol), p.type == mt5.POSITION_TYPE_BUY
    info = mt5.symbol_info(symbol)
    risk = abs(p.price_open - p.sl) if p.sl else 0
    now = tick.time
    d = dt(now)
    flat = (d.hour >= cfg.session_flat_hour or (d.weekday() == 4 and d.hour >= cfg.friday_flat_hour) or
            (now - p.time) >= cfg.max_hold_hours * 3600)
    if flat:
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": p.volume,
               "type": mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY, "position": p.ticket,
               "price": tick.bid if buy else tick.ask, "deviation": 20, "magic": cfg.magic,
               "comment": "orb_v1 flat", "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
        res = mt5.order_send(req)
        log(f"{symbol}: flatten position {p.ticket} -> {getattr(res, 'retcode', None)}")
        be_moved.pop(p.ticket, None)
        return
    if risk <= 0 or be_moved.get(p.ticket):
        return
    profit = (tick.bid - p.price_open) if buy else (p.price_open - tick.ask)
    if profit >= cfg.breakeven_at_r * risk:
        req = {"action": mt5.TRADE_ACTION_SLTP, "symbol": symbol, "position": p.ticket,
               "sl": round(p.price_open, info.digits), "tp": p.tp}
        res = mt5.order_send(req)
        if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
            be_moved[p.ticket] = True
            log(f"{symbol}: moved SL to breakeven on position {p.ticket}")


def run_live(cfg: Cfg, place: bool, allow_real: bool):
    mt5_connect()
    acc = mt5.account_info()
    if place and acc.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO and not allow_real:
        sys.exit("Refusing to place orders on a non-demo account. Use --allow-real only after weeks "
                 "of demo/shadow results.")
    log(f"start: mode={'LIVE ORDERS' if place else 'SHADOW'} account={acc.login} equity={acc.equity}")
    st, engines, last_h1, be_moved = {}, {}, {}, {}
    for sym in cfg.pairs:
        mt5.symbol_select(sym, True)
        d1 = pd.DataFrame(mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 60))
        engines[sym] = Engine(sym, cfg, build_daily_ctx(d1, cfg))
        last_h1[sym] = 0
    while True:
        try:
            for sym in cfg.pairs:
                eng, tick = engines[sym], mt5.symbol_info_tick(sym)
                d1 = pd.DataFrame(mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 60))
                eng.ctx = build_daily_ctx(d1, cfg)
                r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 40)
                new_h1 = [b for b in bars_of(pd.DataFrame(r)) if b[0] > last_h1[sym] and b[0] + 3600 <= tick.time]
                was_armed = eng.armed
                for b in new_h1:
                    last_h1[sym] = b[0]
                    eng.on_h1(b)
                if eng.armed and not was_armed and place is not None:  # just transitioned to armed
                    place_straddle(cfg, sym, eng, st)
                if not eng.armed and was_armed:
                    cancel_unfilled(cfg, sym)
                for p in mine(mt5.positions_get(symbol=sym), cfg):
                    manage_position(cfg, sym, p, be_moved)
        except Exception:
            log("loop error:\n" + traceback.format_exc())
            if mt5.terminal_info() is None:
                mt5.initialize()
        time.sleep(cfg.poll_seconds)


# ============================================================================ MAIN
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["selftest", "backtest", "sensitivity", "shadow", "live"])
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--cache", action="store_true")
    ap.add_argument("--allow-real", action="store_true")
    ap.add_argument("--risk-pct", type=float)
    a = ap.parse_args()
    over = {k: v for k, v in (("start", a.start), ("end", a.end), ("risk_pct", a.risk_pct)) if v}
    cfg = replace(Cfg(), **over)
    if a.mode == "selftest":
        sys.exit(0 if cmd_selftest(cfg) else 1)
    elif a.mode == "backtest":
        cmd_backtest(cfg, a.cache)
    elif a.mode == "sensitivity":
        sensitivity(load_all(cfg, a.cache), cfg)
    else:
        run_live(cfg, place=(a.mode == "live"), allow_real=a.allow_real)


if __name__ == "__main__":
    main()