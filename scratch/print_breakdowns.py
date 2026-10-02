import json

with open('C:/Users/NEW/.gemini/antigravity-ide/brain/14fb0bfa-bb1d-4a75-822f-612b2e9da949/scratch/v1_vs_v2_detailed_audit.json', 'r') as f:
    d = json.load(f)

print("=== ASSET BREAKDOWN ===")
for sym, dat in d['Asset_Breakdown'].items():
    v1, v2 = dat['V1'], dat['V2']
    print(f"{sym:7s} | V1: {v1['trades']:2d} tr, {v1['win_rate_pct']:5.1f}% WR, {v1['expectancy_r']:+.3f}R exp, {v1['profit_factor']:4.2f} PF, {v1['max_dd_r']:5.2f}R DD | V2: {v2['trades']:2d} tr, {v2['win_rate_pct']:5.1f}% WR, {v2['expectancy_r']:+.3f}R exp, {v2['profit_factor']:4.2f} PF, {v2['max_dd_r']:5.2f}R DD")

print("\n=== TIMEFRAME BREAKDOWN ===")
for tf, dat in d['Timeframe_Breakdown'].items():
    v1, v2 = dat['V1'], dat['V2']
    print(f"{tf:5s} | V1: {v1['trades']:2d} tr, {v1['win_rate_pct']:5.1f}% WR, {v1['expectancy_r']:+.3f}R exp, {v1['profit_factor']:4.2f} PF | V2: {v2['trades']:2d} tr, {v2['win_rate_pct']:5.1f}% WR, {v2['expectancy_r']:+.3f}R exp, {v2['profit_factor']:4.2f} PF")

print("\n=== SESSION BREAKDOWN ===")
for sess, dat in d['Session_Breakdown'].items():
    v1, v2 = dat['V1'], dat['V2']
    v2_str = f"{v2.get('trades', 0):2d} tr, {v2.get('win_rate_pct', 0.0):5.1f}% WR, {v2.get('expectancy_r', 0.0):+.3f}R exp" if v2.get('trades', 0) > 0 else " 0 tr (BLOCKED)"
    print(f"{sess:28s} | V1: {v1['trades']:2d} tr, {v1['win_rate_pct']:5.1f}% WR, {v1['expectancy_r']:+.3f}R exp | V2: {v2_str}")

print("\n=== ADX BREAKDOWN ===")
for reg, dat in d['ADX_Breakdown'].items():
    v1, v2 = dat['V1'], dat['V2']
    v2_str = f"{v2.get('trades', 0):2d} tr, {v2.get('win_rate_pct', 0.0):5.1f}% WR, {v2.get('expectancy_r', 0.0):+.3f}R exp" if v2.get('trades', 0) > 0 else " 0 tr (BLOCKED)"
    print(f"{reg:25s} | V1: {v1['trades']:2d} tr, {v1['win_rate_pct']:5.1f}% WR, {v1['expectancy_r']:+.3f}R exp | V2: {v2_str}")

