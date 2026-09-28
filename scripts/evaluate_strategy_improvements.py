"""High-speed vectorized quantitative strategy improvement research."""

import pickle
import numpy as np
import pandas as pd
from research_signal_frequency import compute_adx, resample_h1_to_h4


def run_experiment():
    with open("archives/data_cache_orb.pkl", "rb") as f:
        key, data = pickle.load(f)

    pairs = ['EURUSD', 'USDJPY', 'GBPUSD', 'AUDUSD', 'USDCAD', 'USDCHF']

    exit_modes = [
        "Fixed_2R_Baseline",
        "Fixed_3R_BE1.5",
        "Chandelier_Trail_2.5ATR",
        "Donchian_10_Channel_Exit",
        "Hybrid_50TP2R_50Trail"
    ]

    all_results = {mode: [] for mode in exit_modes}

    for pair in pairs:
        df_h1 = data[pair]['H1'].copy()
        df_h1['time'] = pd.to_datetime(df_h1['time'], unit='s', utc=True)
        df_h1.set_index('time', inplace=True)
        df_h1.sort_index(inplace=True)
        df_h1 = df_h1[~df_h1.index.duplicated(keep='first')]

        df_h4 = resample_h1_to_h4(df_h1)
        df = df_h1.merge(df_h4[['htf_bullish', 'htf_bearish']], left_index=True, right_index=True, how='left')
        df['htf_bullish'] = df['htf_bullish'].ffill().fillna(False)
        df['htf_bearish'] = df['htf_bearish'].ffill().fillna(False)

        df['adx'] = compute_adx(df, 14)
        df['roc'] = ((df['close'] - df['close'].shift(20)) / df['close'].shift(20)) * 100.0

        df['donchian_high'] = df['high'].shift(1).rolling(20).max()
        df['donchian_low'] = df['low'].shift(1).rolling(20).min()
        df['donchian_exit_high'] = df['high'].shift(1).rolling(10).max()
        df['donchian_exit_low'] = df['low'].shift(1).rolling(10).min()

        vol_col = 'tick_volume' if 'tick_volume' in df.columns else 'volume'
        df['vol_ma'] = df[vol_col].rolling(20).mean()
        df['vol_filter'] = df[vol_col] >= (df['vol_ma'] * 0.9)

        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift(1)).abs(),
            (df['low'] - df['close'].shift(1)).abs()
        ], axis=1).max(axis=1)
        df['atr'] = tr.ewm(alpha=1.0/14.0, adjust=False).mean()

        # Extract NumPy arrays for high speed
        c_arr = df['close'].values
        h_arr = df['high'].values
        l_arr = df['low'].values
        atr_arr = df['atr'].values
        don_h_arr = df['donchian_high'].values
        don_l_arr = df['donchian_low'].values
        don_eh_arr = df['donchian_exit_high'].values
        don_el_arr = df['donchian_exit_low'].values
        htf_b_arr = df['htf_bullish'].values
        htf_s_arr = df['htf_bearish'].values
        adx_arr = df['adx'].values
        roc_arr = df['roc'].values
        vol_arr = df['vol_filter'].values

        n = len(c_arr)

        for mode in exit_modes:
            position = 0
            entry_price = 0.0
            initial_sl = 0.0
            current_sl = 0.0
            tp_price = 0.0
            r_dist = 0.0
            peak_price = 0.0
            trough_price = 0.0
            half_closed = False
            realized_r_half = 0.0
            trade_rs = []

            for i in range(250, n):
                c = c_arr[i]
                h = h_arr[i]
                l = l_arr[i]
                atr = atr_arr[i]
                don_eh = don_eh_arr[i]
                don_el = don_el_arr[i]

                if position == 1:
                    if h > peak_price:
                        peak_price = h

                    if mode == "Fixed_2R_Baseline":
                        if l <= current_sl:
                            trade_rs.append(-1.0)
                            position = 0
                        elif h >= tp_price:
                            trade_rs.append(2.0)
                            position = 0

                    elif mode == "Fixed_3R_BE1.5":
                        if h >= (entry_price + 1.5 * r_dist):
                            if current_sl < entry_price:
                                current_sl = entry_price
                        if l <= current_sl:
                            r_res = (current_sl - entry_price) / r_dist
                            trade_rs.append(max(r_res, -1.0))
                            position = 0
                        elif h >= tp_price:
                            trade_rs.append(3.0)
                            position = 0

                    elif mode == "Chandelier_Trail_2.5ATR":
                        trail_stop = peak_price - (2.5 * atr)
                        if trail_stop > current_sl:
                            current_sl = trail_stop
                        if l <= current_sl:
                            r_res = (current_sl - entry_price) / r_dist
                            trade_rs.append(r_res)
                            position = 0

                    elif mode == "Donchian_10_Channel_Exit":
                        if l <= initial_sl:
                            trade_rs.append(-1.0)
                            position = 0
                        elif l <= don_el:
                            exit_p = min(c, don_el)
                            r_res = (exit_p - entry_price) / r_dist
                            trade_rs.append(r_res)
                            position = 0

                    elif mode == "Hybrid_50TP2R_50Trail":
                        if not half_closed and h >= (entry_price + 2.0 * r_dist):
                            half_closed = True
                            realized_r_half = 2.0
                            if current_sl < entry_price:
                                current_sl = entry_price

                        if half_closed:
                            runner_stop = peak_price - (2.5 * atr)
                            if runner_stop > current_sl:
                                current_sl = runner_stop

                        if l <= current_sl:
                            r_res_2 = (current_sl - entry_price) / r_dist
                            if half_closed:
                                trade_rs.append((realized_r_half + r_res_2) / 2.0)
                            else:
                                trade_rs.append(-1.0)
                            position = 0

                elif position == -1:
                    if l < trough_price:
                        trough_price = l

                    if mode == "Fixed_2R_Baseline":
                        if h >= current_sl:
                            trade_rs.append(-1.0)
                            position = 0
                        elif l <= tp_price:
                            trade_rs.append(2.0)
                            position = 0

                    elif mode == "Fixed_3R_BE1.5":
                        if l <= (entry_price - 1.5 * r_dist):
                            if current_sl > entry_price:
                                current_sl = entry_price
                        if h >= current_sl:
                            r_res = (entry_price - current_sl) / r_dist
                            trade_rs.append(max(r_res, -1.0))
                            position = 0
                        elif l <= tp_price:
                            trade_rs.append(3.0)
                            position = 0

                    elif mode == "Chandelier_Trail_2.5ATR":
                        trail_stop = trough_price + (2.5 * atr)
                        if trail_stop < current_sl:
                            current_sl = trail_stop
                        if h >= current_sl:
                            r_res = (entry_price - current_sl) / r_dist
                            trade_rs.append(r_res)
                            position = 0

                    elif mode == "Donchian_10_Channel_Exit":
                        if h >= initial_sl:
                            trade_rs.append(-1.0)
                            position = 0
                        elif h >= don_eh:
                            exit_p = max(c, don_eh)
                            r_res = (entry_price - exit_p) / r_dist
                            trade_rs.append(r_res)
                            position = 0

                    elif mode == "Hybrid_50TP2R_50Trail":
                        if not half_closed and l <= (entry_price - 2.0 * r_dist):
                            half_closed = True
                            realized_r_half = 2.0
                            if current_sl > entry_price:
                                current_sl = entry_price

                        if half_closed:
                            runner_stop = trough_price + (2.5 * atr)
                            if runner_stop < current_sl:
                                current_sl = runner_stop

                        if h >= current_sl:
                            r_res_2 = (entry_price - current_sl) / r_dist
                            if half_closed:
                                trade_rs.append((realized_r_half + r_res_2) / 2.0)
                            else:
                                trade_rs.append(-1.0)
                            position = 0

                if position == 0 and atr > 0:
                    long_trig = htf_b_arr[i] and (adx_arr[i] >= 18.0) and (roc_arr[i] > 0) and (c > don_h_arr[i]) and vol_arr[i]
                    short_trig = htf_s_arr[i] and (adx_arr[i] >= 18.0) and (roc_arr[i] < 0) and (c < don_l_arr[i]) and vol_arr[i]

                    if long_trig:
                        position = 1
                        entry_price = c
                        r_dist = 1.75 * atr
                        initial_sl = entry_price - r_dist
                        current_sl = initial_sl
                        tp_price = entry_price + (2.0 * r_dist if "2R" in mode else 3.0 * r_dist)
                        peak_price = h
                        half_closed = False
                    elif short_trig:
                        position = -1
                        entry_price = c
                        r_dist = 1.75 * atr
                        initial_sl = entry_price + r_dist
                        current_sl = initial_sl
                        tp_price = entry_price - (2.0 * r_dist if "2R" in mode else 3.0 * r_dist)
                        trough_price = l
                        half_closed = False

            gross_profit = sum([r for r in trade_rs if r > 0])
            gross_loss = abs(sum([r for r in trade_rs if r < 0]))
            pf = (gross_profit / gross_loss) if gross_loss > 0 else 0
            win_cnt = len([r for r in trade_rs if r > 0])
            total_cnt = len(trade_rs)
            wr = (win_cnt / total_cnt * 100) if total_cnt > 0 else 0
            net_r = sum(trade_rs)
            exp_r = net_r / total_cnt if total_cnt > 0 else 0

            all_results[mode].append({
                'Pair': pair,
                'Trades': total_cnt,
                'WinRate%': round(wr, 1),
                'ProfitFactor': round(pf, 2),
                'Net_R': round(net_r, 1),
                'Exp_R': round(exp_r, 3)
            })

    print("=" * 80)
    print(" EMPIRICAL RESEARCH RESULTS: 4.7 YEARS (2022-2026) ACROSS 6 MAJOR PAIRS")
    print("=" * 80)

    for mode in exit_modes:
        m_df = pd.DataFrame(all_results[mode])
        tot_trades = m_df['Trades'].sum()
        tot_net_r = m_df['Net_R'].sum()
        avg_pf = m_df['ProfitFactor'].mean()
        avg_wr = m_df['WinRate%'].mean()
        overall_exp = tot_net_r / tot_trades if tot_trades > 0 else 0

        print(f"\n--- MODEL: {mode} ---")
        print(m_df.to_string(index=False))
        print(f" PORTFOLIO SUMMARY: Trades = {tot_trades} | WinRate = {round(avg_wr, 1)}% | Avg PF = {round(avg_pf, 2)} | Net Return = +{round(tot_net_r, 1)}R | Exp = +{round(overall_exp, 3)}R/trade")


if __name__ == '__main__':
    run_experiment()
