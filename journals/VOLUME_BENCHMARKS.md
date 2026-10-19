# Cross-Volume Strategy Benchmarks

Comparative analytics evaluating performance across sequential 100-trade volumes to measure strategy improvements.

- **Global Trades Evaluated**: `4`
- **Global Win Rate**: `9.5%` (2 Wins / 19 Losses)
- **Active Volume**: `VOL_01`

### 📈 Comparative Volume Benchmark Table

| Volume | Range | Completed | Win Rate | Net Pips | Net R | Profit Factor | Avg Loss MFE | Top Failure Mode | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Volume 01** | #1 – #100 | `21/100` | **9.5%** | `-219.8p` | `-16.48R` | `0.18` | `+3.0p` | `STRUCTURAL_INVALIDATION` | `IN_PROGRESS` |

---

### 🔍 Continuous Refinement Protocol
1. **Volume 1 (Baseline)**: Trades #1 to #100 establish institutional forward benchmarks with zero curve-fitting.
2. **Volume Transition Protocol**: Upon completing each 100-trade volume, the distribution of loss causes and MFE is analyzed to calibrate parameters (e.g. wick-ratio filtering, dynamic trailing stop triggers).
3. **Version Benchmarking**: Successive volumes must demonstrate progressive improvement in Profit Factor and Loss MFE reduction.
