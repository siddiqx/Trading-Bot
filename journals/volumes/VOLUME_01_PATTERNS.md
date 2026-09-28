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

