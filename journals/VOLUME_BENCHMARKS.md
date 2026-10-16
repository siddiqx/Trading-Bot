# Cross-Volume Strategy Benchmarks

Comparative analytics evaluating performance across sequential 100-trade volumes to measure strategy improvements.

- **Global Trades Evaluated**: `2`
- **Global Win Rate**: `10.5%` (2 Wins / 17 Losses)
- **Active Volume**: `VOL_01`

### 📈 Comparative Volume Benchmark Table

| Volume | Range | Completed | Win Rate | Net Pips | Net R | Profit Factor | Avg Loss MFE | Top Failure Mode | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Volume 01** | #1 – #100 | `19/100` | **10.5%** | `-187.7p` | `-14.48R` | `0.21` | `+3.0p` | `UNKNOWN` | `IN_PROGRESS` |

---

### 🔍 Continuous Refinement Protocol
1. **Volume 1 (Baseline)**: Trades #1 to #100 establish institutional forward benchmarks with zero curve-fitting.
2. **Volume Transition Protocol**: Upon completing each 100-trade volume, the distribution of loss causes and MFE is analyzed to calibrate parameters (e.g. wick-ratio filtering, dynamic trailing stop triggers).
3. **Version Benchmarking**: Successive volumes must demonstrate progressive improvement in Profit Factor and Loss MFE reduction.
