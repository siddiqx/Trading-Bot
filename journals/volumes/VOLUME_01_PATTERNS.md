# Trade Pattern Journal · Volume 01

> **Volume Capacity**: Trades 1 to 100
> **Purpose**: Systematic post-mortem documentation to analyze failure modes, win factors, and optimize execution rules across 100-trade blocks.

---

### #1 · EURUSD (1H) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#1`
- **Direction**: `SHORT` | **Outcome**: `LOSS` (`-18.7 pips` / `-1.0R`)
- **Execution Range**: Entry ` 1.13662 ` ➔ Exit ` 1.13849 `
- **Targets**: Stop Loss ` 1.13849 ` | Take Profit ` 1.13335 `
- **Holding Time**: `2.47 hours` (2 bars)
- **Window**: `2026-09-28 14:26:26 UTC` ➔ `2026-09-28 16:54:22 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+4.7 pips` | Reached `+0.25R` (14.3% of TP) |
| **Max Adverse Excursion (MAE)** | `-18.7 pips` | Deepest drawdown `-1.0R` |
| **Session** | `London/New York Overlap` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BEARISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `STRUCTURAL_INVALIDATION`
> **Analysis**: Order block level was invalidated by institutional flow after 1 bar(s). Stop-loss executed disciplined capital preservation.
>
> **Actionable Takeaway**: Trade adhered strictly to risk geometry. Invalidation was clean and preserved capital.

---

### #2 · USD/CHF (1H) — 🎯 WIN (+1.75R)

- **Global Sequence**: Trade `#2`
- **Direction**: `LONG` | **Outcome**: `WIN` (`+31.5 pips` / `1.75R`)
- **Execution Range**: Entry ` 0.83031 ` ➔ Exit ` 0.83346 `
- **Targets**: Stop Loss ` 0.82851 ` | Take Profit ` 0.83346 `
- **Holding Time**: `25.14 hours` (25 bars)
- **Window**: `2026-09-28 06:00:00 UTC` ➔ `2026-09-29 07:08:28 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+36.4 pips` | Reached `+2.02R` (100.0% of TP) |
| **Max Adverse Excursion (MAE)** | `-6.7 pips` | Deepest drawdown `-0.37R` |
| **Session** | `Asian/Tokyo Session` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BULLISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `HIGH_VELOCITY_BREAKOUT`
> **Analysis**: Take-profit hit within 1 bar(s). High momentum impulse confirmed structural breakout conviction.
>
> **Actionable Takeaway**: Validates the 20-period Donchian channel breakout trigger.

---

### #3 · EURUSD (1H) — 🎯 WIN (+1.75R)

- **Global Sequence**: Trade `#3`
- **Direction**: `SHORT` | **Outcome**: `WIN` (`+34.6 pips` / `1.75R`)
- **Execution Range**: Entry ` 1.13533 ` ➔ Exit ` 1.13187 `
- **Targets**: Stop Loss ` 1.13731 ` | Take Profit ` 1.13187 `
- **Holding Time**: `11.99 hours` (12 bars)
- **Window**: `2026-09-29 08:00:00 UTC` ➔ `2026-09-29 19:59:34 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+36.0 pips` | Reached `+1.82R` (100.0% of TP) |
| **Max Adverse Excursion (MAE)** | `-7.8 pips` | Deepest drawdown `-0.39R` |
| **Session** | `London Session` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BEARISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `HIGH_VELOCITY_BREAKOUT`
> **Analysis**: Take-profit hit within 1 bar(s). High momentum impulse confirmed structural breakout conviction.
>
> **Actionable Takeaway**: Validates the 20-period Donchian channel breakout trigger.

---

### #4 · USDCAD (1H) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#4`
- **Direction**: `LONG` | **Outcome**: `LOSS` (`-18.3 pips` / `-1.0R`)
- **Execution Range**: Entry ` 1.41813 ` ➔ Exit ` 1.4163 `
- **Targets**: Stop Loss ` 1.4163 ` | Take Profit ` 1.42133 `
- **Holding Time**: `38.02 hours` (38 bars)
- **Window**: `2026-09-29 01:40:03 UTC` ➔ `2026-09-30 15:41:15 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+21.8 pips` | Reached `+1.19R` (68.1% of TP) |
| **Max Adverse Excursion (MAE)** | `-30.3 pips` | Deepest drawdown `-1.66R` |
| **Session** | `Asian/Tokyo Session` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BULLISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `PREMATURE_REVERSAL`
> **Analysis**: Position reached +21.8 pips (+1.19R / 68.1% of TP) before aggressive counter-trend reversal hit stop-loss.
>
> **Actionable Takeaway**: Incorporate a Breakeven Protection rule once position reaches +0.8R or 50% TP distance.

---

### #5 · USDJPY (1H) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#5`
- **Direction**: `SHORT` | **Outcome**: `LOSS` (`-65.0 pips` / `-1.0R`)
- **Execution Range**: Entry ` 156.746 ` ➔ Exit ` 157.396 `
- **Targets**: Stop Loss ` 157.396 ` | Take Profit ` 155.609 `
- **Holding Time**: `21.95 hours` (22 bars)
- **Window**: `2026-09-30 02:00:00 UTC` ➔ `2026-09-30 23:56:42 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+37.6 pips` | Reached `+0.58R` (33.1% of TP) |
| **Max Adverse Excursion (MAE)** | `-83.9 pips` | Deepest drawdown `-1.29R` |
| **Session** | `Asian/Tokyo Session` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BEARISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `LOW_LIQUIDITY_CHOP`
> **Analysis**: Signal triggered during Asian/Tokyo Session. Lower institutional volume led to whipsaw without sustainable directional continuation.
>
> **Actionable Takeaway**: Restrict or weight signal scoring lower during off-peak liquidity windows.

---

### #6 · XAUUSD (15M) — 🛑 LOSS (-0.35R)

- **Global Sequence**: Trade `#6`
- **Direction**: `SHORT` | **Outcome**: `LOSS` (`-112.0 pips` / `-0.35R`)
- **Execution Range**: Entry ` 4187.9 ` ➔ Exit ` 4199.1 `
- **Targets**: Stop Loss ` 4220.28 ` | Take Profit ` 4131.23 `
- **Holding Time**: `14.4 hours` (58 bars)
- **Window**: `2026-09-30 15:30:00 UTC` ➔ `2026-10-01 05:54:18 UTC`
- **Exit Reason**: `EMA20_INVALIDATION`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+402.5 pips` | Reached `+1.24R` (71.0% of TP) |
| **Max Adverse Excursion (MAE)** | `-86.8 pips` | Deepest drawdown `-0.27R` |
| **Session** | `London/New York Overlap` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BEARISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `PREMATURE_REVERSAL`
> **Analysis**: Position moved aggressively in favor (+402.5 pips / +1.24R) before multi-session counter-trend retracement triggered dynamic EMA20 invalidation.
>
> **Actionable Takeaway**: Model H Break-Even protection rule locks in risk-free status once +1.0R is achieved.

---

### #7 · EURUSD (15M) — 🎯 WIN (+1.75R)

- **Global Sequence**: Trade `#7`
- **Direction**: `SHORT` | **Outcome**: `WIN` (`+44.7 pips` / `+1.75R`)
- **Execution Range**: Entry ` 1.12778 ` ➔ Exit ` 1.12330 `
- **Targets**: Stop Loss ` 1.13033 ` | Take Profit ` 1.12330 `
- **Holding Time**: `0.83 hours` (3 bars)
- **Window**: `2026-10-01 14:45:00 UTC` ➔ `2026-10-01 15:35:00 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+53.2 pips` | Reached `+2.09R` (118.7% of TP) |
| **Max Adverse Excursion (MAE)** | `-11.4 pips` | Deepest drawdown `-0.45R` |
| **Session** | `London/New York Overlap` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BEARISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `CLEAN_MOMENTUM_EXPANSION`
> **Analysis**: Clean displacement bar triggered rapid 3-bar expansion directly to target with minimal drawdown.
>
> **Actionable Takeaway**: Validates 15M breakout trigger when accompanied by solid candle body displacement.

---

### #8 · EURUSD (1H) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#8`
- **Direction**: `LONG` | **Outcome**: `LOSS` (`-10.0 pips` / `-0.17R`)
- **Execution Range**: Entry ` 1.136 ` ➔ Exit ` 1.135 `
- **Targets**: Stop Loss ` 1.13 ` | Take Profit ` 1.146 `
- **Holding Time**: `120.48 hours` (120 bars)
- **Window**: `2026-09-27 10:00:00 UTC` ➔ `2026-10-02 10:28:52 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+5.0 pips` | Reached `+0.08R` (5.0% of TP) |
| **Max Adverse Excursion (MAE)** | `-20.0 pips` | Deepest drawdown `-0.33R` |
| **Session** | `London Session` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BULLISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `STRUCTURAL_INVALIDATION`
> **Analysis**: Order block level was invalidated by institutional flow after 1 bar(s). Stop-loss executed disciplined capital preservation.
>
> **Actionable Takeaway**: Trade adhered strictly to risk geometry. Invalidation was clean and preserved capital.

---

### #7 · XAUUSD (15M) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#7`
- **Direction**: `SHORT` | **Outcome**: `LOSS` (`-112.0 pips` / `-0.35R`)
- **Execution Range**: Entry ` 4187.9 ` ➔ Exit ` 4199.10009765625 `
- **Targets**: Stop Loss ` 4220.28 ` | Take Profit ` 4131.23 `
- **Holding Time**: `14.4 hours` (58 bars)
- **Window**: `2026-09-30 15:30:00 UTC` ➔ `2026-10-01 05:54:18 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+185.0 pips` | Reached `+0.57R` (32.6% of TP) |
| **Max Adverse Excursion (MAE)** | `-349.0 pips` | Deepest drawdown `-1.08R` |
| **Session** | `London/New York Overlap` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BEARISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `STRUCTURAL_INVALIDATION`
> **Analysis**: Order block level was invalidated by institutional flow after 1 bar(s). Stop-loss executed disciplined capital preservation.
>
> **Actionable Takeaway**: Trade adhered strictly to risk geometry. Invalidation was clean and preserved capital.

---

### #8 · XAUUSD (15M) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#8`
- **Direction**: `LONG` | **Outcome**: `LOSS` (`-211.7 pips` / `-1.0R`)
- **Execution Range**: Entry ` 4181.5 ` ➔ Exit ` 4160.33 `
- **Targets**: Stop Loss ` 4160.33 ` | Take Profit ` 4226.9 `
- **Holding Time**: `6.77 hours` (27 bars)
- **Window**: `2026-10-01 17:30:00 UTC` ➔ `2026-10-02 00:16:18 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+14.0 pips` | Reached `+0.07R` (3.1% of TP) |
| **Max Adverse Excursion (MAE)** | `-223.0 pips` | Deepest drawdown `-1.05R` |
| **Session** | `New York Afternoon` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BULLISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `STRUCTURAL_INVALIDATION`
> **Analysis**: Order block level was invalidated by institutional flow after 1 bar(s). Stop-loss executed disciplined capital preservation.
>
> **Actionable Takeaway**: Trade adhered strictly to risk geometry. Invalidation was clean and preserved capital.

---

### #9 · XAUUSD (15M) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#9`
- **Direction**: `LONG` | **Outcome**: `LOSS` (`-129.2 pips` / `-1.0R`)
- **Execution Range**: Entry ` 4192.4 ` ➔ Exit ` 4179.48 `
- **Targets**: Stop Loss ` 4179.48 ` | Take Profit ` 4215.01 `
- **Holding Time**: `0.52 hours` (2 bars)
- **Window**: `2026-10-02 06:15:00 UTC` ➔ `2026-10-02 06:46:26 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+0.0 pips` | Reached `+0.0R` (0.0% of TP) |
| **Max Adverse Excursion (MAE)** | `-134.0 pips` | Deepest drawdown `-1.04R` |
| **Session** | `Asian/Tokyo Session` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BULLISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `LOW_LIQUIDITY_CHOP`
> **Analysis**: Signal triggered during Asian/Tokyo Session. Lower institutional volume led to whipsaw without sustainable directional continuation.
>
> **Actionable Takeaway**: Restrict or weight signal scoring lower during off-peak liquidity windows.

---

### #10 · USDCAD (15M) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#10`
- **Direction**: `SHORT` | **Outcome**: `LOSS` (`-0.3 pips` / `-0.02R`)
- **Execution Range**: Entry ` 1.42258 ` ➔ Exit ` 1.4226100444793701 `
- **Targets**: Stop Loss ` 1.42438 ` | Take Profit ` 1.4191 `
- **Holding Time**: `12.03 hours` (48 bars)
- **Window**: `2026-10-01 19:45:00 UTC` ➔ `2026-10-02 07:46:30 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+20.8 pips` | Reached `+1.16R` (59.8% of TP) |
| **Max Adverse Excursion (MAE)** | `-9.7 pips` | Deepest drawdown `-0.54R` |
| **Session** | `New York Afternoon` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BEARISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `PREMATURE_REVERSAL`
> **Analysis**: Position reached +20.8 pips (+1.16R / 59.8% of TP) before aggressive counter-trend reversal hit stop-loss.
>
> **Actionable Takeaway**: Incorporate a Breakeven Protection rule once position reaches +0.8R or 50% TP distance.

---

### #11 · USDCAD (15M) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#11`
- **Direction**: `LONG` | **Outcome**: `LOSS` (`-18.0 pips` / `-1.0R`)
- **Execution Range**: Entry ` 1.4239 ` ➔ Exit ` 1.4221 `
- **Targets**: Stop Loss ` 1.4221 ` | Take Profit ` 1.42705 `
- **Holding Time**: `1.28 hours` (5 bars)
- **Window**: `2026-10-02 11:15:00 UTC` ➔ `2026-10-02 12:31:38 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+7.0 pips` | Reached `+0.39R` (22.2% of TP) |
| **Max Adverse Excursion (MAE)** | `-38.9 pips` | Deepest drawdown `-2.16R` |
| **Session** | `London Session` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BULLISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `STRUCTURAL_INVALIDATION`
> **Analysis**: Order block level was invalidated by institutional flow after 1 bar(s). Stop-loss executed disciplined capital preservation.
>
> **Actionable Takeaway**: Trade adhered strictly to risk geometry. Invalidation was clean and preserved capital.

---

### #12 · XAUUSD (15M) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#12`
- **Direction**: `LONG` | **Outcome**: `LOSS` (`-350.0 pips` / `-1.0R`)
- **Execution Range**: Entry ` 4210.2 ` ➔ Exit ` 4175.2 `
- **Targets**: Stop Loss ` 4175.2 ` | Take Profit ` 4271.45 `
- **Holding Time**: `1.78 hours` (7 bars)
- **Window**: `2026-10-02 12:45:00 UTC` ➔ `2026-10-02 14:31:39 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+20.0 pips` | Reached `+0.06R` (3.3% of TP) |
| **Max Adverse Excursion (MAE)** | `-462.0 pips` | Deepest drawdown `-1.32R` |
| **Session** | `London/New York Overlap` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BULLISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `STRUCTURAL_INVALIDATION`
> **Analysis**: Order block level was invalidated by institutional flow after 1 bar(s). Stop-loss executed disciplined capital preservation.
>
> **Actionable Takeaway**: Trade adhered strictly to risk geometry. Invalidation was clean and preserved capital.

---

### #13 · EURUSD (1H) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#13`
- **Direction**: `SHORT` | **Outcome**: `LOSS` (`-12.7 pips` / `-0.33R`)
- **Execution Range**: Entry ` 1.12689 ` ➔ Exit ` 1.1281588077545166 `
- **Targets**: Stop Loss ` 1.13076 ` | Take Profit ` 1.12011 `
- **Holding Time**: `24.03 hours` (24 bars)
- **Window**: `2026-10-01 15:00:00 UTC` ➔ `2026-10-02 15:01:35 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+49.3 pips` | Reached `+1.27R` (72.8% of TP) |
| **Max Adverse Excursion (MAE)** | `-19.1 pips` | Deepest drawdown `-0.49R` |
| **Session** | `London/New York Overlap` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BEARISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `PREMATURE_REVERSAL`
> **Analysis**: Position reached +49.3 pips (+1.27R / 72.8% of TP) before aggressive counter-trend reversal hit stop-loss.
>
> **Actionable Takeaway**: Incorporate a Breakeven Protection rule once position reaches +0.8R or 50% TP distance.

---

### #14 · XAUUSD (1H) — 🎯 WIN (+1.75R)

- **Global Sequence**: Trade `#14`
- **Direction**: `LONG` | **Outcome**: `WIN` (`+50.5 pips` / `0.5R`)
- **Execution Range**: Entry ` 2650.0 ` ➔ Exit ` 2650.1 `
- **Targets**: Stop Loss ` 2650.1 ` | Take Profit ` 2667.5 `
- **Holding Time**: `159.71 hours` (160 bars)
- **Window**: `2026-09-28 10:00:00 UTC` ➔ `2026-10-05 01:42:48 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+150.0 pips` | Reached `+150.0R` (85.7% of TP) |
| **Max Adverse Excursion (MAE)** | `-20.0 pips` | Deepest drawdown `-20.0R` |
| **Session** | `London Session` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BULLISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `HIGH_VELOCITY_BREAKOUT`
> **Analysis**: Take-profit hit within 1 bar(s). High momentum impulse confirmed structural breakout conviction.
>
> **Actionable Takeaway**: Validates the 20-period Donchian channel breakout trigger.

---

### #15 · USDCAD (15M) — 🎯 WIN (+1.75R)

- **Global Sequence**: Trade `#15`
- **Direction**: `LONG` | **Outcome**: `WIN` (`+31.9 pips` / `0.97R`)
- **Execution Range**: Entry ` 1.42463 ` ➔ Exit ` 1.4277000427246094 `
- **Targets**: Stop Loss ` 1.42473 ` | Take Profit ` 1.4304 `
- **Holding Time**: `71.28 hours` (285 bars)
- **Window**: `2026-10-02 15:15:00 UTC` ➔ `2026-10-05 14:31:42 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+47.3 pips` | Reached `+47.3R` (82.0% of TP) |
| **Max Adverse Excursion (MAE)** | `-12.3 pips` | Deepest drawdown `-12.3R` |
| **Session** | `London/New York Overlap` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BULLISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `HIGH_VELOCITY_BREAKOUT`
> **Analysis**: Take-profit hit within 1 bar(s). High momentum impulse confirmed structural breakout conviction.
>
> **Actionable Takeaway**: Validates the 20-period Donchian channel breakout trigger.

---

### #16 · EURUSD (15M) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#16`
- **Direction**: `SHORT` | **Outcome**: `LOSS` (`-16.0 pips` / `-1.0R`)
- **Execution Range**: Entry ` 1.1207 ` ➔ Exit ` 1.1223 `
- **Targets**: Stop Loss ` 1.1223 ` | Take Profit ` 1.11744 `
- **Holding Time**: `4.29 hours` (17 bars)
- **Window**: `2026-10-05 16:30:00 UTC` ➔ `2026-10-05 20:47:15 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+6.3 pips` | Reached `+0.39R` (19.3% of TP) |
| **Max Adverse Excursion (MAE)** | `-17.6 pips` | Deepest drawdown `-1.1R` |
| **Session** | `New York Afternoon` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BEARISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `STRUCTURAL_INVALIDATION`
> **Analysis**: Order block level was invalidated by institutional flow after 1 bar(s). Stop-loss executed disciplined capital preservation.
>
> **Actionable Takeaway**: Trade adhered strictly to risk geometry. Invalidation was clean and preserved capital.

---

### #17 · GBPUSD (15M) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#17`
- **Direction**: `SHORT` | **Outcome**: `LOSS` (`-22.8 pips` / `-1.0R`)
- **Execution Range**: Entry ` 1.32083 ` ➔ Exit ` 1.32311 `
- **Targets**: Stop Loss ` 1.32311 ` | Take Profit ` 1.31684 `
- **Holding Time**: `9.52 hours` (38 bars)
- **Window**: `2026-10-05 16:15:00 UTC` ➔ `2026-10-06 01:46:16 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+2.4 pips` | Reached `+0.11R` (6.1% of TP) |
| **Max Adverse Excursion (MAE)** | `-23.6 pips` | Deepest drawdown `-1.03R` |
| **Session** | `New York Afternoon` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BEARISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `STRUCTURAL_INVALIDATION`
> **Analysis**: Order block level was invalidated by institutional flow after 1 bar(s). Stop-loss executed disciplined capital preservation.
>
> **Actionable Takeaway**: Trade adhered strictly to risk geometry. Invalidation was clean and preserved capital.

---

### #18 · XAUUSD (15M) — 🎯 WIN (+1.75R)

- **Global Sequence**: Trade `#18`
- **Direction**: `SHORT` | **Outcome**: `WIN` (`+183.8 pips` / `1.38R`)
- **Execution Range**: Entry ` 4130.7 ` ➔ Exit ` 4107.29 `
- **Targets**: Stop Loss ` 4130.6 ` | Take Profit ` 4107.29 `
- **Holding Time**: `0.77 hours` (3 bars)
- **Window**: `2026-10-06 02:00:00 UTC` ➔ `2026-10-06 02:46:18 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+271.8 pips` | Reached `+271.85R` (100.0% of TP) |
| **Max Adverse Excursion (MAE)** | `-9.3 pips` | Deepest drawdown `-9.3R` |
| **Session** | `Asian/Tokyo Session` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BEARISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `HIGH_VELOCITY_BREAKOUT`
> **Analysis**: Take-profit hit within 1 bar(s). High momentum impulse confirmed structural breakout conviction.
>
> **Actionable Takeaway**: Validates the 20-period Donchian channel breakout trigger.

---

### #19 · USDCAD (1H) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#19`
- **Direction**: `LONG` | **Outcome**: `LOSS` (`-19.8 pips` / `-1.0R`)
- **Execution Range**: Entry ` 1.42696 ` ➔ Exit ` 1.42498 `
- **Targets**: Stop Loss ` 1.42498 ` | Take Profit ` 1.43043 `
- **Holding Time**: `2.76 hours` (3 bars)
- **Window**: `2026-10-06 09:00:00 UTC` ➔ `2026-10-06 11:45:47 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+8.1 pips` | Reached `+0.41R` (23.3% of TP) |
| **Max Adverse Excursion (MAE)** | `-29.6 pips` | Deepest drawdown `-1.49R` |
| **Session** | `London Session` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BULLISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `STRUCTURAL_INVALIDATION`
> **Analysis**: Order block level was invalidated by institutional flow after 1 bar(s). Stop-loss executed disciplined capital preservation.
>
> **Actionable Takeaway**: Trade adhered strictly to risk geometry. Invalidation was clean and preserved capital.

---

### #20 · XAUUSD (15M) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#20`
- **Direction**: `LONG` | **Outcome**: `LOSS` (`-150.0 pips` / `-1.0R`)
- **Execution Range**: Entry ` 4170.8 ` ➔ Exit ` 4155.8 `
- **Targets**: Stop Loss ` 4155.8 ` | Take Profit ` 4200.8 `
- **Holding Time**: `4.57 hours` (18 bars)
- **Window**: `2026-10-06 20:00:00 UTC` ➔ `2026-10-07 00:34:01 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+0.0 pips` | Reached `+0.0R` (0.0% of TP) |
| **Max Adverse Excursion (MAE)** | `-150.7 pips` | Deepest drawdown `-1.0R` |
| **Session** | `New York Afternoon` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BULLISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `STRUCTURAL_INVALIDATION`
> **Analysis**: Order block level was invalidated by institutional flow after 1 bar(s). Stop-loss executed disciplined capital preservation.
>
> **Actionable Takeaway**: Trade adhered strictly to risk geometry. Invalidation was clean and preserved capital.

---

### #21 · GBPUSD (15M) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#21`
- **Direction**: `LONG` | **Outcome**: `LOSS` (`-18.7 pips` / `-1.0R`)
- **Execution Range**: Entry ` 1.32767 ` ➔ Exit ` 1.3258 `
- **Targets**: Stop Loss ` 1.3258 ` | Take Profit ` 1.3314 `
- **Holding Time**: `7.78 hours` (31 bars)
- **Window**: `2026-10-06 18:15:00 UTC` ➔ `2026-10-07 02:01:57 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+3.7 pips` | Reached `+0.2R` (9.9% of TP) |
| **Max Adverse Excursion (MAE)** | `-20.3 pips` | Deepest drawdown `-1.08R` |
| **Session** | `New York Afternoon` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BULLISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `STRUCTURAL_INVALIDATION`
> **Analysis**: Order block level was invalidated by institutional flow after 1 bar(s). Stop-loss executed disciplined capital preservation.
>
> **Actionable Takeaway**: Trade adhered strictly to risk geometry. Invalidation was clean and preserved capital.

---

### #22 · XAUUSD (15M) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#22`
- **Direction**: `SHORT` | **Outcome**: `BREAK_EVEN` (`+1.0 pips` / `0.0R`)
- **Execution Range**: Entry ` 4128.85 ` ➔ Exit ` 4128.75 `
- **Targets**: Stop Loss ` 4128.75 ` | Take Profit ` 4084.78 `
- **Holding Time**: `4.78 hours` (19 bars)
- **Window**: `2026-10-07 06:00:00 UTC` ➔ `2026-10-07 10:46:45 UTC`

#### 📊 Excursion & Market Regime
| Metric | Value | Detail |
| :--- | :--- | :--- |
| **Max Favorable Excursion (MFE)** | `+196.2 pips` | Reached `+196.2R` (44.5% of TP) |
| **Max Adverse Excursion (MAE)** | `-108.1 pips` | Deepest drawdown `-108.1R` |
| **Session** | `Asian/Tokyo Session` | Institutional Market Timing |
| **Entry RSI (14)** | `50.0` | Momentum Baseline |
| **EMA Alignment** | `BEARISH_EXPANDING` | Structural Trend Bias |

#### 🔬 Post-Mortem Diagnosis: `PREMATURE_REVERSAL`
> **Analysis**: Position reached +196.2 pips (+196.2R / 44.5% of TP) before aggressive counter-trend reversal hit stop-loss.
>
> **Actionable Takeaway**: Incorporate a Breakeven Protection rule once position reaches +0.8R or 50% TP distance.

---

