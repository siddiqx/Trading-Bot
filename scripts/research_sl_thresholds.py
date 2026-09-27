import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.deep_research_draining_trades import run_deep_trade_collector

def analyze_sl_impact():
    df_t, _ = run_deep_trade_collector()
    print(f"Total trades collected: {len(df_t)}")

    df_losses = df_t[df_t['res'] == 'LOSS']
    df_wins = df_t[df_t['res'] == 'WIN']

    print("\n" + "="*80)
    print("SL PIPS DISTRIBUTION ACROSS WINS vs LOSSES")
    print("="*80)
    for threshold in [18.0, 20.0, 22.0, 24.0, 26.0, 30.0]:
        loss_over = df_losses[df_losses['sl_pips'] > threshold]
        win_over = df_wins[df_wins['sl_pips'] > threshold]
        n_loss = len(loss_over)
        n_win = len(win_over)
        total = n_loss + n_win
        loss_pips = loss_over['pips'].sum()
        win_pips = win_over['pips'].sum()
        net = win_pips + loss_pips
        wr = (n_win / total * 100) if total > 0 else 0
        print(f"SL > {threshold:4.1f}p : Wins={n_win:2d} (+{win_pips:6.1f}p) | Losses={n_loss:2d} ({loss_pips:6.1f}p) | Net: {net:+6.1f}p | WR: {wr:4.1f}%")

    print("\n" + "="*80)
    print("DETAILED BREAKDOWN OF ALL WINS WITH SL > 22 PIPS")
    print("="*80)
    wins_wide = df_wins[df_wins['sl_pips'] > 22.0]
    print(wins_wide[['pair', 'time', 'type', 'pips', 'sl_pips', 'hold_bars', 'hour', 'dist_e50_pips']].to_string())

    print("\n" + "="*80)
    print("DETAILED BREAKDOWN OF ALL LOSSES WITH SL > 22 PIPS")
    print("="*80)
    loss_wide = df_losses[df_losses['sl_pips'] > 22.0]
    print(loss_wide[['pair', 'time', 'type', 'pips', 'sl_pips', 'hold_bars', 'hour', 'dist_e50_pips']].to_string())

if __name__ == "__main__":
    analyze_sl_impact()
