import json

with open('C:/Users/NEW/.gemini/antigravity-ide/brain/14fb0bfa-bb1d-4a75-822f-612b2e9da949/scratch/historical_simulation_trades.json', 'r') as f:
    trades = json.load(f)

# V1 vs V2 trade matching
v1_lost_v2_won = []
v1_lost_v2_be = []
v1_won_v2_lost = []
both_won = []
both_lost = []
v2_skipped = []

for t in trades:
    adx_val = t.get("adx", 25.0)
    is_overlap = (t.get("session") == "London/New York Overlap")
    is_adx_blocked = (20.0 < adx_val < 30.0)

    orig_outcome = t.get("outcome")
    orig_r = t.get("realized_r")
    target_rr = t.get("target_rr", 1.75)
    path = t.get("path_order")
    mfe_r = t.get("mfe_r", 0.0)

    if is_overlap or is_adx_blocked:
        v2_skipped.append({
            "trade": t,
            "reason": "LONDON_NY_OVERLAP" if is_overlap else f"ADX_CHOP ({adx_val:.1f})",
            "v1_outcome": orig_outcome,
            "v1_r": orig_r
        })
        continue

    # V2 executed
    be_triggered = (path == "+1R BEFORE -1R") or (mfe_r >= 1.0)
    if orig_outcome == "WIN":
        v2_outcome = "WIN"
        v2_r = target_rr
    elif orig_outcome == "LOSS":
        if be_triggered:
            v2_outcome = "BREAK_EVEN"
            v2_r = 0.0
        else:
            v2_outcome = "LOSS"
            v2_r = -1.0
    else:
        v2_outcome = orig_outcome
        v2_r = orig_r

    if orig_outcome == "WIN" and v2_outcome == "WIN":
        both_won.append({"trade": t, "v1_r": orig_r, "v2_r": v2_r})
    elif orig_outcome == "LOSS" and v2_outcome == "LOSS":
        both_lost.append({"trade": t, "v1_r": orig_r, "v2_r": v2_r})
    elif orig_outcome == "LOSS" and v2_outcome == "BREAK_EVEN":
        v1_lost_v2_be.append({"trade": t, "v1_r": orig_r, "v2_r": v2_r})
    elif orig_outcome == "WIN" and v2_outcome == "LOSS":
        v1_won_v2_lost.append({"trade": t, "v1_r": orig_r, "v2_r": v2_r})

print(f"Total Trades: {len(trades)}")
print(f"V2 Skipped: {len(v2_skipped)}")
print(f"Both Won: {len(both_won)}")
print(f"Both Lost: {len(both_lost)}")
print(f"V1 Lost -> V2 Saved at BE: {len(v1_lost_v2_be)}")
print(f"V1 Won -> V2 Lost: {len(v1_won_v2_lost)}")

print("\n--- Samples of V1 Lost -> V2 Saved at Break-Even ---")
for x in v1_lost_v2_be[:3]:
    t = x["trade"]
    print(f"  {t['symbol']} {t['timeframe']} {t['direction']} on {t['signal_time']}: MFE = +{t['mfe_r']:.2f}R | V1: {x['v1_r']:+.2f}R -> V2: {x['v2_r']:+.2f}R (Saved +1.0R)")

print("\n--- Samples of V2 Skipped Bad Trades (Avoided Losses) ---")
skipped_losses = [x for x in v2_skipped if x['v1_outcome'] == 'LOSS']
print(f"Total Skipped Losses: {len(skipped_losses)} out of {len(v2_skipped)} skipped ({len(skipped_losses)/len(v2_skipped)*100:.1f}%)")
for x in skipped_losses[:3]:
    t = x["trade"]
    print(f"  {t['symbol']} {t['timeframe']} {t['direction']} on {t['signal_time']} | Reason: {x['reason']} | Avoided V1 Loss: {x['v1_r']:+.2f}R")
