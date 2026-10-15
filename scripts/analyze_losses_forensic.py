import json
from collections import Counter

with open("trade_records.json", "r", encoding="utf-8") as f:
    data = json.load(f)

completed = data.get("completed_trades", [])
print(f"Total completed trades: {len(completed)}")

outcomes = Counter(t.get("outcome") for t in completed)
print("Outcomes:", outcomes)

pairs = Counter(t.get("symbol") for t in completed)
print("Pairs:", pairs)

total_pips = sum(float(t.get("realized_pips") or 0.0) for t in completed)
total_r = sum(float(t.get("realized_r") or 0.0) for t in completed)
print(f"Total Net Pips: {total_pips:.1f} | Total Net R: {total_r:.2f}")

print("\n--- DETAILED TRADE LOG ---")
for i, t in enumerate(completed, 1):
    sym = t.get("symbol") or t.get("pair")
    direction = t.get("direction")
    entry = t.get("entry")
    exit_p = t.get("exit_price")
    outcome = t.get("outcome")
    pips = t.get("realized_pips")
    r = t.get("realized_r")
    opened = t.get("opened_at", "N/A")
    closed = t.get("closed_at", "N/A")
    sl = t.get("stop_loss")
    tp = t.get("take_profit")
    sl_p = t.get("sl_pips")
    tp_p = t.get("tp_pips")
    diag = t.get("diagnostic", {})
    factor = diag.get("primary_factor", "N/A")
    mfe = diag.get("mfe_pips", "N/A")
    mae = diag.get("mae_pips", "N/A")
    print(f"{i:2d}. {opened[:16]} | {sym:6s} {direction:5s} | In: {entry} Sl:{sl} Tp:{tp} (SL:{sl_p}p TP:{tp_p}p) -> Out: {exit_p} | {outcome:10s} | {pips:6}p ({r:5}R) | Diag: {factor} MFE:{mfe} MAE:{mae}")

print("\n--- LOSS PATTERNS BY PAIR ---")
for p in set(t.get("symbol") for t in completed if t.get("symbol")):
    p_trades = [t for t in completed if t.get("symbol") == p]
    p_wins = [t for t in p_trades if t.get("outcome") == "WIN"]
    p_losses = [t for t in p_trades if t.get("outcome") == "LOSS"]
    p_be = [t for t in p_trades if t.get("outcome") == "BREAK_EVEN"]
    p_pips = sum(float(t.get("realized_pips") or 0.0) for t in p_trades)
    p_r = sum(float(t.get("realized_r") or 0.0) for t in p_trades)
    print(f"{p:6s}: {len(p_wins)}W / {len(p_losses)}L / {len(p_be)}BE | Net: {p_pips:+.1f}p ({p_r:+.2f}R)")

print("\n--- LOSS REASONS / POST-MORTEM ---")
loss_trades = [t for t in completed if t.get("outcome") == "LOSS"]
for lt in loss_trades:
    sym = lt.get("symbol")
    opened = lt.get("opened_at", "N/A")[:16]
    diag = lt.get("diagnostic", {})
    print(f"{opened} {sym:6s} {lt.get('direction'):5s} SL:{lt.get('sl_pips')}p | MFE:{diag.get('mfe_pips')} | MAE:{diag.get('mae_pips')} | Factor: {diag.get('primary_factor')} | Detail: {diag.get('loss_reason')}")
