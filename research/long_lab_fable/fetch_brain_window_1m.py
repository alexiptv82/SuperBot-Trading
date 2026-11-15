import json, sys, time, urllib.request, urllib.parse, csv, calendar
out, start_s = sys.argv[1], sys.argv[2]
start = calendar.timegm(time.strptime(start_s, "%Y-%m-%dT%H:%M")) * 1000
now = int(time.time() * 1000)
for sym in "BTCUSDT ETHUSDT SOLUSDT XRPUSDT BNBUSDT DOGEUSDT ADAUSDT LINKUSDT".split():
    rows, end = {}, now
    while end > start:
        u = "https://api.bitget.com/api/v2/mix/market/history-candles?" + urllib.parse.urlencode(
            {"symbol": sym, "productType": "USDT-FUTURES", "granularity": "1m", "limit": 200, "endTime": end})
        for i in range(4):
            try:
                d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "study-client"}), timeout=30).read())["data"]
                break
            except Exception:
                time.sleep(2 ** i)
        if not d: break
        for r in d: rows[int(r[0])] = r[:6]
        first = min(int(r[0]) for r in d)
        if first >= end: break
        end = first
        time.sleep(0.05)
    ts = sorted(t for t in rows if t >= start and t + 60000 <= now)
    with open(f"{out}/{sym}_1m.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["ts", "o", "h", "l", "c", "v"]); w.writerows(rows[t] for t in ts)
    gaps = sum(1 for a, b in zip(ts, ts[1:]) if b - a != 60000)
    print(sym, len(ts), "buchi", gaps, time.strftime("%m-%d %H:%M", time.gmtime(ts[0] / 1000)), "->", time.strftime("%m-%d %H:%M", time.gmtime(ts[-1] / 1000)), flush=True)
