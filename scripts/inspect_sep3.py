import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np

def inspect_sep3():
    with open('archives/data_cache_orb.pkl', 'rb') as f:
        data = pickle.load(f)
    pairs_data = data[1]
    
    pair = 'USDJPY'
    m15 = pairs_data[pair]['M15'].copy()
    m15['time_dt'] = pd.to_datetime(m15['time'], unit='s')
    
    sep3 = m15[(m15['time_dt'] >= '2026-09-03 08:00:00') & (m15['time_dt'] <= '2026-09-03 18:00:00')].copy()
    print("USDJPY Sep 3 bars:")
    for idx, row in sep3.iterrows():
        t = row['time_dt']
        o = row['open']
        h = row['high']
        l = row['low']
        c = row['close']
        print(f"{t} | O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f} | Bar Range: {(h-l):.2f}")

if __name__ == '__main__':
    inspect_sep3()
