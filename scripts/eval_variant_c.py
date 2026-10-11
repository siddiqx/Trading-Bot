import sys
sys.path.append('.')
import pickle
import pandas as pd
from scripts.generate_full_audit_report import analyze_portfolio_metrics

df = pickle.load(open('scripts/six_month_trades_variant_c.pkl', 'rb'))
m_all = analyze_portfolio_metrics(df, "VARIANT C FULL")

df['entry_time_dt'] = pd.to_datetime(df['entry_time'])
t_start = df['entry_time_dt'].min()
t_end = df['entry_time_dt'].max()
t_span = (t_end - t_start)
t_split1 = t_start + t_span * 0.60
t_split2 = t_start + t_span * 0.80

df_dev = df[df['entry_time_dt'] < t_split1]
df_val = df[(df['entry_time_dt'] >= t_split1) & (df['entry_time_dt'] < t_split2)]
df_oos = df[df['entry_time_dt'] >= t_split2]

m_dev = analyze_portfolio_metrics(df_dev, "VARIANT C DEV")
m_val = analyze_portfolio_metrics(df_val, "VARIANT C VAL")
m_oos = analyze_portfolio_metrics(df_oos, "VARIANT C OOS")

print(f"Variant C (Full 6-Month): Trades: {m_all['total_trades']} | WR: {m_all['win_rate']:.1f}% | Net: {m_all['net_pips']:+.1f}p | PF: {m_all['profit_factor']:.2f} | Exp: {m_all['net_expectancy_pips']:+.2f}p | MaxDD: {m_all['max_drawdown_pips']:.1f}p")
print(f"Variant C (Dev 60%):     Trades: {m_dev['total_trades']} | WR: {m_dev['win_rate']:.1f}% | Net: {m_dev['net_pips']:+.1f}p | PF: {m_dev['profit_factor']:.2f} | Exp: {m_dev['net_expectancy_pips']:+.2f}p")
print(f"Variant C (Val 20%):     Trades: {m_val['total_trades']} | WR: {m_val['win_rate']:.1f}% | Net: {m_val['net_pips']:+.1f}p | PF: {m_val['profit_factor']:.2f} | Exp: {m_val['net_expectancy_pips']:+.2f}p")
print(f"Variant C (OOS 20%):     Trades: {m_oos['total_trades']} | WR: {m_oos['win_rate']:.1f}% | Net: {m_oos['net_pips']:+.1f}p | PF: {m_oos['profit_factor']:.2f} | Exp: {m_oos['net_expectancy_pips']:+.2f}p")
