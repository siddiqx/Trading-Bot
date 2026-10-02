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

### #6 · EURUSD (1H) — 🛑 LOSS (-1.00R)

- **Global Sequence**: Trade `#6`
- **Direction**: `LONG` | **Outcome**: `LOSS` (`-10.0 pips` / `-0.17R`)
- **Execution Range**: Entry ` 1.136 ` ➔ Exit ` 1.135 `
- **Targets**: Stop Loss ` 1.13 ` | Take Profit ` 1.146 `
- **Holding Time**: `86.59 hours` (87 bars)
- **Window**: `2026-09-27 10:00:00 UTC` ➔ `2026-10-01 00:35:33 UTC`

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

