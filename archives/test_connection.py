import MetaTrader5 as mt5

if not mt5.initialize():
    print("Initialize failed:", mt5.last_error())
    quit()

print("Terminal info:", mt5.terminal_info())
print("Account info:", mt5.account_info())

symbol = "XAUUSD"
selected = mt5.symbol_select(symbol, True)
print("symbol_select result:", selected)

info = mt5.symbol_info(symbol)
print("symbol_info:", info)

rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 10)
print("copy_rates_from_pos result:", rates)

if rates is None:
    print("Error code:", mt5.last_error())

mt5.shutdown()
