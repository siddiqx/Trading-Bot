import sys
sys.path.append('.')
import pickle
import pandas as pd
import numpy as np
from verify_pine_script_exact_logic import *

with open('archives/data_cache_orb.pkl', 'rb') as f:
    data = pickle.load(f)
pairs_data = data[1]
pairs = ['USDCAD', 'USDCHF', 'USDJPY', 'AUDUSD']

# Let's run and print 6M
# Run script
