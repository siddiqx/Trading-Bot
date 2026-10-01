import httpx

headers = {'User-Agent': 'Mozilla/5.0'}
tickers = [
    'XAUUSD=X', 'XAU-USD', 'XAUUSD', 'GC=F', 'ZG=F', 'GLD',
    'XAU=X', 'FOREX:XAUUSD', '^XAU', 'XAU.F'
]

print("Testing Yahoo Finance Gold Tickers:")
for t in tickers:
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=2d&interval=15m"
        r = httpx.get(url, headers=headers, timeout=5)
        d = r.json()
        res = d.get('chart', {}).get('result')
        if res:
            q = res[0]['indicators']['quote'][0]
            closes = [c for c in q.get('close', []) if c is not None]
            print(f"FOUND: {t:<15} -> Latest: {closes[-1] if closes else 'Empty'}")
        else:
            err = d.get('chart', {}).get('error', {}).get('code', 'Unknown')
            print(f"NOT FOUND: {t:<15} ({err})")
    except Exception as e:
        print(f"ERROR: {t:<15} ({e})")
