import pickle
import pandas as pd
import numpy as np

def run_research():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]

    # Let's inspect EURUSD first
    eur = pairs_data['EURUSD']['H1'].copy()
    eur['time_dt'] = pd.to_datetime(eur['time'], unit='s')
    print("EURUSD total bars:", len(eur), "from", eur['time_dt'].iloc[0], "to", eur['time_dt'].iloc[-1])

    # Let's test why the current script produced 0 trades
    # Calculate indicators
    donchian_len = 20
    eur['highest_20'] = eur['high'].shift(1).rolling(donchian_len).max()
    eur['lowest_20'] = eur['low'].shift(1).rolling(donchian_len).min()
    
    eur['highest_48'] = eur['high'].shift(1).rolling(48).max()
    eur['lowest_48'] = eur['low'].shift(1).rolling(48).min()
    eur['eq_48'] = (eur['highest_48'] + eur['lowest_48']) / 2.0
    
    # Donchian crossovers
    eur['cross_long'] = (eur['close'] > eur['highest_20']) & (eur['close'].shift(1) <= eur['highest_20'].shift(1))
    eur['cross_short'] = (eur['close'] < eur['lowest_20']) & (eur['close'].shift(1) >= eur['lowest_20'].shift(1))
    
    print("Total cross_long:", eur['cross_long'].sum())
    print("Total cross_short:", eur['cross_short'].sum())
    
    # Check how many cross_long satisfy in_discount (close <= eq_48)
    long_in_discount = eur['cross_long'] & (eur['close'] <= eur['eq_48'])
    short_in_premium = eur['cross_short'] & (eur['close'] >= eur['eq_48'])
    
    print("cross_long in_discount count:", long_in_discount.sum())
    print("cross_short in_premium count:", short_in_premium.sum())

run_research()
