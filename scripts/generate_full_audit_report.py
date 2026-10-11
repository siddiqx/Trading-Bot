"""
Full Statistical Audit, Out-of-Sample Validation, and Prop-Firm Resampling Engine.
Produces complete audited metrics across all requested sections.
"""

import sys
import pickle
import math
import numpy as np
import pandas as pd
from datetime import datetime, timezone

def analyze_portfolio_metrics(df_trades, title="PORTFOLIO PERFORMANCE", account_equity=5000.0, risk_pct=0.01):
    if df_trades.empty:
        print(f"[{title}] No trades to analyze.")
        return {}

    n = len(df_trades)
    wins = df_trades[df_trades['outcome'] == 'WIN']
    losses = df_trades[df_trades['outcome'] == 'LOSS']

    n_win = len(wins)
    n_loss = len(losses)
    win_rate = (n_win / n) * 100.0 if n > 0 else 0.0
    loss_rate = (n_loss / n) * 100.0 if n > 0 else 0.0

    gross_profit_pips = wins['gross_pips'].sum()
    gross_loss_pips = abs(losses['gross_pips'].sum())
    total_costs_pips = df_trades['costs_pips'].sum()
    net_pips = df_trades['net_pips'].sum()

    avg_win_net = wins['net_pips'].mean() if n_win > 0 else 0.0
    avg_loss_net = abs(losses['net_pips'].mean()) if n_loss > 0 else 0.0
    profit_factor = (wins['net_pips'].sum() / abs(losses['net_pips'].sum())) if abs(losses['net_pips'].sum()) > 0 else 999.0

    net_expectancy_pips = df_trades['net_pips'].mean()
    net_expectancy_r = df_trades['realized_r'].mean()
    avg_costs_per_trade = df_trades['costs_pips'].mean()
    avg_spread = df_trades['spread_pips'].mean()

    # Consecutive wins / losses
    outcomes = (df_trades['outcome'] == 'WIN').astype(int).values
    max_consec_w = 0
    max_consec_l = 0
    curr_w = 0
    curr_l = 0
    for o in outcomes:
        if o == 1:
            curr_w += 1
            curr_l = 0
            if curr_w > max_consec_w:
                max_consec_w = curr_w
        else:
            curr_l += 1
            curr_w = 0
            if curr_l > max_consec_l:
                max_consec_l = curr_l

    # Average hold time in bars and hours
    avg_hold_bars = df_trades['hold_bars'].mean()
    avg_hold_hours = (avg_hold_bars * 15.0) / 60.0

    # Drawdown calculation in pips and in currency ($5,000 account)
    # Position sizing: dollar risk = account_equity * risk_pct
    # For a 10-pip stop: dollar_per_pip = dollar_risk / 10.0
    dollar_risk = account_equity * risk_pct
    dollar_per_pip = dollar_risk / 10.0

    df_trades = df_trades.copy()
    df_trades['pnl_usd'] = df_trades['net_pips'] * dollar_per_pip
    df_trades['cum_pnl_usd'] = df_trades['pnl_usd'].cumsum()
    df_trades['equity'] = account_equity + df_trades['cum_pnl_usd']
    df_trades['peak_equity'] = df_trades['equity'].cummax()
    df_trades['drawdown_usd'] = df_trades['peak_equity'] - df_trades['equity']
    df_trades['drawdown_pct'] = (df_trades['drawdown_usd'] / df_trades['peak_equity']) * 100.0

    max_dd_usd = df_trades['drawdown_usd'].max()
    max_dd_pct = df_trades['drawdown_pct'].max()

    # Pips drawdown
    df_trades['cum_net_pips'] = df_trades['net_pips'].cumsum()
    df_trades['peak_pips'] = df_trades['cum_net_pips'].cummax()
    max_dd_pips = (df_trades['peak_pips'] - df_trades['cum_net_pips']).max()

    # Daily aggregation for worst day / daily limit breaches
    df_trades['date'] = pd.to_datetime(df_trades['exit_time']).dt.date
    daily_pnl = df_trades.groupby('date')['pnl_usd'].sum()
    worst_day_usd = daily_pnl.min() if not daily_pnl.empty else 0.0
    daily_limit_5pct = account_equity * 0.05 # $250
    daily_breaches = (daily_pnl < -daily_limit_5pct).sum()

    # Weekly aggregation
    df_trades['week'] = pd.to_datetime(df_trades['exit_time']).dt.to_period('W')
    weekly_pnl = df_trades.groupby('week')['pnl_usd'].sum()
    worst_week_usd = weekly_pnl.min() if not weekly_pnl.empty else 0.0

    # Monthly aggregation
    df_trades['month'] = pd.to_datetime(df_trades['exit_time']).dt.to_period('M')
    monthly_pnl = df_trades.groupby('month')['pnl_usd'].sum()
    worst_month_usd = monthly_pnl.min() if not monthly_pnl.empty else 0.0

    # Ambiguity count
    ambiguous_count = len(df_trades[df_trades['exit_reason'] == 'SL_SAME_CANDLE_AMBIGUITY'])
    ambiguous_pct = (ambiguous_count / n) * 100.0 if n > 0 else 0.0

    # Statistical confidence interval for win rate (Wilson Score Interval 95%)
    z = 1.96
    p = n_win / n if n > 0 else 0
    denominator = 1 + z**2 / n
    centre_adjusted_probability = (p + z**2 / (2 * n)) / denominator
    adjusted_std_dev = math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denominator
    lower_bound = max(0.0, (centre_adjusted_probability - z * adjusted_std_dev) * 100.0)
    upper_bound = min(100.0, (centre_adjusted_probability + z * adjusted_std_dev) * 100.0)

    # Net expectancy confidence interval (Student's t 95%)
    t_crit = 1.96
    se_expectancy = df_trades['net_pips'].std() / math.sqrt(n) if n > 1 else 0
    exp_ci_lower = net_expectancy_pips - t_crit * se_expectancy
    exp_ci_upper = net_expectancy_pips + t_crit * se_expectancy

    res = {
        'total_trades': n,
        'wins': n_win,
        'losses': n_loss,
        'win_rate': win_rate,
        'loss_rate': loss_rate,
        'win_rate_ci_95': (lower_bound, upper_bound),
        'gross_profit_pips': gross_profit_pips,
        'gross_loss_pips': gross_loss_pips,
        'total_costs_pips': total_costs_pips,
        'net_pips': net_pips,
        'profit_factor': profit_factor,
        'net_expectancy_pips': net_expectancy_pips,
        'net_expectancy_r': net_expectancy_r,
        'expectancy_ci_95': (exp_ci_lower, exp_ci_upper),
        'avg_win_net': avg_win_net,
        'avg_loss_net': avg_loss_net,
        'avg_holding_hours': avg_hold_hours,
        'max_consec_wins': max_consec_w,
        'max_consec_losses': max_consec_l,
        'max_drawdown_pips': max_dd_pips,
        'max_drawdown_usd': max_dd_usd,
        'max_drawdown_pct': max_dd_pct,
        'ending_equity': df_trades['equity'].iloc[-1] if n > 0 else account_equity,
        'net_return_usd': df_trades['cum_pnl_usd'].iloc[-1] if n > 0 else 0.0,
        'net_return_pct': (df_trades['cum_pnl_usd'].iloc[-1] / account_equity * 100.0) if n > 0 else 0.0,
        'worst_day_usd': worst_day_usd,
        'worst_week_usd': worst_week_usd,
        'worst_month_usd': worst_month_usd,
        'daily_limit_breaches': daily_breaches,
        'overall_limit_breach': max_dd_usd >= (account_equity * 0.10),
        'avg_spread_pips': avg_spread,
        'avg_costs_per_trade': avg_costs_per_trade,
        'same_candle_ambiguity_trades': ambiguous_count,
        'same_candle_ambiguity_pct': ambiguous_pct,
        'monthly_pnl': monthly_pnl
    }
    return res


def run_monte_carlo(df_trades, num_simulations=1000, account_equity=5000.0, risk_pct=0.01):
    """
    Simulates 1,000 resampled trade sequences with replacement to test sequence risk,
    maximum drawdown distribution, and account ruin probability.
    """
    if df_trades.empty:
        return {}

    dollar_risk = account_equity * risk_pct
    dollar_per_pip = dollar_risk / 10.0
    trade_pnls = (df_trades['net_pips'] * dollar_per_pip).values
    n = len(trade_pnls)

    max_drawdowns = []
    ending_equities = []
    ruin_count_10pct = 0 # 10% overall drawdown limit ($500)
    daily_fail_count = 0

    np.random.seed(42)
    for _ in range(num_simulations):
        sampled_indices = np.random.choice(n, size=n, replace=True)
        resampled_pnl = trade_pnls[sampled_indices]
        curve = account_equity + np.cumsum(resampled_pnl)
        peaks = np.maximum.accumulate(curve)
        dds = peaks - curve
        max_dd = np.max(dds)
        max_drawdowns.append(max_dd)
        ending_equities.append(curve[-1])

        if max_dd >= (account_equity * 0.10): # $500 max limit
            ruin_count_10pct += 1

    return {
        'simulations': num_simulations,
        'p50_max_dd_usd': np.percentile(max_drawdowns, 50),
        'p95_max_dd_usd': np.percentile(max_drawdowns, 95),
        'p99_max_dd_usd': np.percentile(max_drawdowns, 99),
        'p50_ending_equity': np.percentile(ending_equities, 50),
        'p5_ending_equity': np.percentile(ending_equities, 5),
        'p95_ending_equity': np.percentile(ending_equities, 95),
        'account_failure_rate_10pct': (ruin_count_10pct / num_simulations) * 100.0
    }


def main():
    with open('scripts/six_month_trades_baseline.pkl', 'rb') as f:
        baseline_df = pickle.load(f)

    print("================================================================================")
    print("SECTION D: SIX-MONTH BASELINE PERFORMANCE AUDIT (OCT 1, 2025 - MAR 31, 2026)")
    print("================================================================================")
    b_metrics = analyze_portfolio_metrics(baseline_df, "BASELINE FIXED 15/10", account_equity=5000.0, risk_pct=0.01)

    print(f"Total Completed Trades: {b_metrics['total_trades']}")
    print(f"Win Rate: {b_metrics['win_rate']:.2f}% ({b_metrics['wins']}W / {b_metrics['losses']}L)")
    print(f"95% Confidence Interval for Win Rate: [{b_metrics['win_rate_ci_95'][0]:.2f}%, {b_metrics['win_rate_ci_95'][1]:.2f}%]")
    print(f"Gross Profit: +{b_metrics['gross_profit_pips']:.1f} pips | Gross Loss: -{b_metrics['gross_loss_pips']:.1f} pips")
    print(f"Total Transaction Costs: {b_metrics['total_costs_pips']:.1f} pips (Avg {b_metrics['avg_costs_per_trade']:.2f}p/trade)")
    print(f"Net Profit after Costs: {b_metrics['net_pips']:+.1f} pips")
    print(f"Profit Factor: {b_metrics['profit_factor']:.2f}")
    print(f"Net Expectancy per Trade: {b_metrics['net_expectancy_pips']:+.2f} pips ({b_metrics['net_expectancy_r']:+.3f} R)")
    print(f"95% Confidence Interval for Expectancy: [{b_metrics['expectancy_ci_95'][0]:+.2f}p, {b_metrics['expectancy_ci_95'][1]:+.2f}p]")
    print(f"Average Net Win: +{b_metrics['avg_win_net']:.2f} pips | Average Net Loss: -{b_metrics['avg_loss_net']:.2f} pips")
    print(f"Average Hold Time: {b_metrics['avg_holding_hours']:.1f} hours ({b_metrics['avg_holding_hours']*4:.0f} M15 bars)")
    print(f"Max Consecutive Wins: {b_metrics['max_consec_wins']} | Max Consecutive Losses: {b_metrics['max_consec_losses']}")
    print(f"Max Portfolio Drawdown: {b_metrics['max_drawdown_pips']:.1f} pips (${b_metrics['max_drawdown_usd']:.2f} / {b_metrics['max_drawdown_pct']:.2f}%)")
    print(f"Worst Day: ${b_metrics['worst_day_usd']:.2f} | Worst Week: ${b_metrics['worst_week_usd']:.2f} | Worst Month: ${b_metrics['worst_month_usd']:.2f}")
    print(f"Daily Drawdown Breaches (>5% / $250): {b_metrics['daily_limit_breaches']}")
    print(f"Overall Drawdown Breach (>10% / $500): {b_metrics['overall_limit_breach']}")
    print(f"Same-Candle Ambiguity Count: {b_metrics['same_candle_ambiguity_trades']} ({b_metrics['same_candle_ambiguity_pct']:.1f}% assumed loss)")

    print("\n--- MONTHLY PERFORMANCE (NET PROFIT IN USD ON $5,000 ACCOUNT AT 1.0% RISK) ---")
    for m, val in b_metrics['monthly_pnl'].items():
        print(f"  {str(m):<7}: ${val:+8.2f}")

    print("\n--- PERFORMANCE BY ELIGIBLE FOREX PAIR ---")
    for pair, grp in baseline_df.groupby('pair'):
        pm = analyze_portfolio_metrics(grp, pair, account_equity=5000.0, risk_pct=0.01)
        print(f"  {pair:<7}: {pm['total_trades']:3d} trades ({pm['wins']:2d}W/{pm['losses']:2d}L) | WR: {pm['win_rate']:5.1f}% | Net: {pm['net_pips']:+7.1f}p | PF: {pm['profit_factor']:4.2f} | Exp: {pm['net_expectancy_pips']:+5.2f}p | MaxDD: {pm['max_drawdown_pips']:5.1f}p")

    print("\n================================================================================")
    print("SECTION E: CHRONOLOGICAL OUT-OF-SAMPLE VALIDATION")
    print("================================================================================")
    # Split chronologically:
    # Total range: Oct 1, 2025 to Mar 31, 2026 (182 days)
    # 60% Development: Oct 1, 2025 to Jan 18, 2026
    # 20% Validation: Jan 19, 2026 to Feb 24, 2026
    # 20% Untouched Out-of-Sample: Feb 25, 2026 to Mar 31, 2026
    baseline_df['entry_time_dt'] = pd.to_datetime(baseline_df['entry_time'])
    t_start = baseline_df['entry_time_dt'].min()
    t_end = baseline_df['entry_time_dt'].max()
    t_span = (t_end - t_start)

    t_split1 = t_start + t_span * 0.60
    t_split2 = t_start + t_span * 0.80

    df_dev = baseline_df[baseline_df['entry_time_dt'] < t_split1].copy()
    df_val = baseline_df[(baseline_df['entry_time_dt'] >= t_split1) & (baseline_df['entry_time_dt'] < t_split2)].copy()
    df_oos = baseline_df[baseline_df['entry_time_dt'] >= t_split2].copy()

    m_dev = analyze_portfolio_metrics(df_dev, "DEV (60%)", 5000.0, 0.01)
    m_val = analyze_portfolio_metrics(df_val, "VAL (20%)", 5000.0, 0.01)
    m_oos = analyze_portfolio_metrics(df_oos, "UNTOUCHED OOS (20%)", 5000.0, 0.01)

    print(f"Development Period ({str(t_start)[:10]} to {str(t_split1)[:10]}):")
    print(f"  Trades: {m_dev['total_trades']} | WR: {m_dev['win_rate']:.1f}% | Net Pips: {m_dev['net_pips']:+.1f} | PF: {m_dev['profit_factor']:.2f} | Exp: {m_dev['net_expectancy_pips']:+.2f}p | MaxDD: {m_dev['max_drawdown_pips']:.1f}p")

    print(f"\nValidation Period ({str(t_split1)[:10]} to {str(t_split2)[:10]}):")
    print(f"  Trades: {m_val['total_trades']} | WR: {m_val['win_rate']:.1f}% | Net Pips: {m_val['net_pips']:+.1f} | PF: {m_val['profit_factor']:.2f} | Exp: {m_val['net_expectancy_pips']:+.2f}p | MaxDD: {m_val['max_drawdown_pips']:.1f}p")

    print(f"\nUNTOUCHED OUT-OF-SAMPLE PERIOD ({str(t_split2)[:10]} to {str(t_end)[:10]}):")
    print(f"  Trades: {m_oos['total_trades']} | WR: {m_oos['win_rate']:.1f}% | Net Pips: {m_oos['net_pips']:+.1f} | PF: {m_oos['profit_factor']:.2f} | Exp: {m_oos['net_expectancy_pips']:+.2f}p | MaxDD: {m_oos['max_drawdown_pips']:.1f}p")
    print(f"  OOS 95% WR Confidence Interval: [{m_oos['win_rate_ci_95'][0]:.1f}%, {m_oos['win_rate_ci_95'][1]:.1f}%]")

    # Cost Sensitivity Stress Test on OOS: +50% increase in transaction costs
    df_oos_stress = df_oos.copy()
    df_oos_stress['costs_pips'] = df_oos_stress['costs_pips'] * 1.50
    df_oos_stress['net_pips'] = df_oos_stress['gross_pips'] - df_oos_stress['costs_pips']
    df_oos_stress['realized_r'] = df_oos_stress['net_pips'] / 10.0
    m_oos_stress = analyze_portfolio_metrics(df_oos_stress, "OOS STRESS (+50% Costs)", 5000.0, 0.01)
    print(f"\nOOS Transaction-Cost Stress Test (+50% spread/slippage/comm):")
    print(f"  Net Pips: {m_oos_stress['net_pips']:+.1f} | PF: {m_oos_stress['profit_factor']:.2f} | Exp: {m_oos_stress['net_expectancy_pips']:+.2f}p")

    print("\n================================================================================")
    print("SECTION G: $5,000 PROP-FIRM RISK MODEL & MONTE CARLO AUDIT")
    print("================================================================================")
    for risk_lvl in [0.005, 0.01]:
        pct_label = "0.5% Risk ($25/trade, 0.25 Lots)" if risk_lvl == 0.005 else "1.0% Risk ($50/trade, 0.50 Lots)"
        pm = analyze_portfolio_metrics(baseline_df, pct_label, account_equity=5000.0, risk_pct=risk_lvl)
        mc = run_monte_carlo(baseline_df, num_simulations=1000, account_equity=5000.0, risk_pct=risk_lvl)

        print(f"\n--- PROP-FIRM EVALUATION: {pct_label} ---")
        print(f"  Starting Balance: $5,000.00")
        print(f"  Ending Balance: ${pm['ending_equity']:.2f} (Net Return: +${pm['net_return_usd']:.2f} / +{pm['net_return_pct']:.1f}%)")
        print(f"  Historical Max Drawdown: ${pm['max_drawdown_usd']:.2f} ({pm['max_drawdown_pct']:.2f}%)")
        print(f"  Daily Limit Breaches (>5% / $250): {pm['daily_limit_breaches']}")
        print(f"  Overall Limit Breach (>10% / $500): {pm['overall_limit_breach']}")
        print(f"  Monte Carlo P50 Max Drawdown: ${mc['p50_max_dd_usd']:.2f}")
        print(f"  Monte Carlo P95 Max Drawdown: ${mc['p95_max_dd_usd']:.2f}")
        print(f"  Monte Carlo P99 Max Drawdown: ${mc['p99_max_dd_usd']:.2f}")
        print(f"  Account Ruin Probability (>10% DD): {mc['account_failure_rate_10pct']:.1f}%")

if __name__ == '__main__':
    main()
