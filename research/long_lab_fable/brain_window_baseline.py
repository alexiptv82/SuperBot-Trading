"""Controllo: ingressi SHORT e LONG a OGNI ora su ciascuno degli 8 simboli di Brain, nella finestra in cui Brain ha
operato, con le regole di uscita di Brain (stop fisso, target 2R, 24 h, stop prima del target, 2 bp, 6 bp/lato).
Candele reali Bitget 1m. Non usa alcun dato della VPS."""
import calendar, json, sys, time
import numpy as np
D = sys.argv[1]
SYMS = "BTCUSDT ETHUSDT SOLUSDT XRPUSDT BNBUSDT DOGEUSDT ADAUSDT LINKUSDT".split()
ms = lambda s: calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M")) * 1000
W0, W1 = ms("2026-11-13T14:00"), ms("2026-11-15T06:00")
A = {s: np.loadtxt(f"{D}/{s}_1m.csv", delimiter=",", skiprows=1) for s in SYMS}
def trade(a, k, side, s):
    """decisione all'inizio del minuto k (indice): fill = chiusura del minuto k-1 +/- 2 bp; barre da k+1."""
    fill = a[k - 1, 4] * (1 + side * 2e-4)
    stop, tgt = fill * (1 - side * s), fill * (1 + side * 2 * s)
    for j in range(k + 1, min(len(a), k + 1 + 1440)):
        o, h, l, c = a[j, 1:5]
        if (side == 1 and l <= stop) or (side == -1 and h >= stop):
            base = min(stop, o) if side == 1 else max(stop, o)
            return side * (base * (1 - side * 2e-4) / fill - 1) - 12e-4, "stop"
        if (side == 1 and h >= tgt) or (side == -1 and l <= tgt):
            return side * (tgt / fill - 1) - 12e-4, "tp"
    if k + 1 + 1440 <= len(a):
        return side * (a[k + 1440, 4] / fill - 1) - 12e-4, "tempo"
    return None, "aperta"
out = {"finestra_utc": ["2026-11-13 14:00", "2026-11-15 06:00"], "mercato_pct": {}, "esiti": {}}
for s in SYMS:
    a = A[s]; i0, i1 = np.searchsorted(a[:, 0], W0), np.searchsorted(a[:, 0], W1)
    out["mercato_pct"][s] = round((a[i1, 4] / a[i0, 4] - 1) * 100, 2)
out["mercato_pct"]["media"] = round(float(np.mean(list(out["mercato_pct"].values()))), 2)
for stop in (0.005, 0.0075, 0.009):
    for side, lab in ((-1, "SHORT"), (1, "LONG")):
        nets, whys = [], {}
        for s in SYMS:
            a = A[s]
            for t in range(W0, W1 + 1, 3_600_000):
                k = int(np.searchsorted(a[:, 0], t))
                r, why = trade(a, k, side, stop)
                whys[why] = whys.get(why, 0) + 1
                if r is not None: nets.append(r)
        x = np.array(nets)
        out["esiti"][f"{lab}_stop_{stop*100:.2f}%"] = {
            "n": len(x), "vincenti": round(float((x > 0).mean()), 3), "media_bp": round(float(x.mean()) * 1e4, 1),
            "usdt_medio_su_7000_nozionale": round(float(x.mean()) * 7000, 1), "uscite": whys,
            "pareggio_vincenti_teorico": round((stop + 12e-4 + 2e-4) / (3 * stop), 3)}
print(json.dumps(out, indent=1))
