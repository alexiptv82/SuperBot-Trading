"""Resoconto serale di UN bot (Hawk o Bull), SOLA LETTURA. Solo libreria standard.

Uso (sul VPS, via ssh con lo script su stdin):  python3 -I - <cartella-dati> <nome> [<ts_ms_adesso>] < report_serale.py
Legge solo heartbeat.json, state_v2.json e learning_log.jsonl. Non scrive nulla, non apre la rete.
Tutti i numeri sono del conto di prova (paper). Le finestre sono rispetto a "adesso" (ultime 24 ore e le 24 prima)
e ai giorni UTC; la base di confronto e' l'inizio (12-15/10), quando il bot apriva molto e vinceva molto.
"""
import collections
import json
import os
import sys
import time

H24 = 24 * 3600 * 1000
START_DAYS = ("10-12", "10-13", "10-14", "10-15")      # i primi giorni, il riferimento "come prima"


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def day(ms):
    return time.strftime("%m-%d", time.gmtime(ms / 1000))


def load_rows(path):
    rows, bad = [], 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    bad += 1
    except OSError:
        return None, 0
    return rows, bad


def close_ts(r):
    return r.get("close_ms") or r.get("ts") or 0


def trades_from_closes(closes):
    """Raggruppa le chiusure per id: un trade e' CHIUSO quando ha almeno una chiusura non parziale."""
    T = {}
    for n, r in enumerate(closes):
        key = r.get("id") if r.get("id") is not None else "senza-id-%d" % n
        t = T.setdefault(key, {"net": 0.0, "ts": 0, "final": False, "mfe": 0.0, "side": r.get("side"),
                               "symbol": r.get("symbol"), "why": None, "lev": r.get("leverage")})
        t["net"] += _f(r.get("net"))
        t["mfe"] = max(t["mfe"], _f(r.get("mfe_r")))
        if close_ts(r) >= t["ts"]:
            t["ts"] = close_ts(r)
            if not r.get("partial"):
                t["why"] = str(r.get("why"))
        if not r.get("partial"):
            t["final"] = True
    return [t for t in T.values() if t["final"]]


def summ(trades):
    n = len(trades)
    if not n:
        return "n=0"
    w = sum(1 for t in trades if t["net"] > 0)
    tot = sum(t["net"] for t in trades)
    return "n=%d vincenti=%d%% netto=%+.1f$ medio=%+.2f$" % (n, round(100.0 * w / n), tot, tot / n)


def section_state(d, now_ms):
    try:
        hb = json.load(open(os.path.join(d, "heartbeat.json")))
        print("battito: modalita=%s posizioni=%s eta=%ds" % (hb.get("mode"), hb.get("open_positions"),
                                                              now_ms / 1000 - hb.get("ts", 0)))
    except Exception as e:
        print("battito: non leggibile (%s)" % type(e).__name__)
    try:
        st = json.load(open(os.path.join(d, "state_v2.json")))
    except Exception as e:
        print("stato: non leggibile (%s)" % type(e).__name__)
        return
    m = st.get("main") or {}
    lp = st.get("last_prices") or {}
    upnl_tot = margin_tot = 0.0
    n_up = n_dn = 0
    pos = []
    for sym, p in (m.get("positions") or {}).items():
        q, e = _f(p.get("qty")), _f(p.get("entry"))
        px = lp.get(sym)
        sgn = 1 if p.get("side") == 1 else -1
        upnl = (float(px) - e) * q * sgn if px and e else None
        if upnl is not None:
            upnl_tot += upnl
            n_up += upnl > 0
            n_dn += upnl <= 0
        margin_tot += _f(p.get("total_margin"))
        pos.append("%s %s x%s margine %.0f$ %s" % (sym, "L" if sgn == 1 else "S", p.get("leverage"),
                                                  _f(p.get("total_margin")),
                                                  ("%+.1f$" % upnl) if upnl is not None else "n.d."))
    print("APERTE %d: pnl non realizzato %+.1f$ (in utile %d, in perdita %d) | margine impegnato %.0f$ | "
          "equity stimata %.0f$ | inizio giorno %.0f$" % (
              len(pos), upnl_tot, n_up, n_dn, margin_tot,
              _f(m.get("cash")) + margin_tot + upnl_tot, _f(m.get("day_start_equity"))))
    for line in pos:
        print("  " + line)
    bud = st.get("budget") or {}
    print("budget Claude del giorno: speso %.3f$ in %s chiamate (totale dall'inizio %.2f$)" % (
        _f(bud.get("spent")), bud.get("calls"), _f(bud.get("total_spent"))))


def section_log(rows, now_ms):
    opens = [r for r in rows if r.get("ev") == "open" and r.get("ts")]
    closes = [r for r in rows if r.get("ev") == "close" and close_ts(r)]
    cands = [r for r in rows if r.get("ev") == "candidate" and r.get("ts")]
    calls = [r for r in rows if r.get("ev") == "claude_call" and r.get("ts")]
    trades = trades_from_closes(closes)

    def win(lst, key, lo, hi):
        return [x for x in lst if lo <= key(x) < hi]
    t24 = (now_ms - H24, now_ms + 1)
    t48 = (now_ms - 2 * H24, now_ms - H24)
    print("--- ULTIME 24 ORE (e le 24 prima) ---")
    for lab, (lo, hi) in (("ultime 24h", t24), ("24h prima", t48)):
        o = win(opens, lambda r: r["ts"], lo, hi)
        c = win(closes, close_ts, lo, hi)
        tr = win(trades, lambda t: t["ts"], lo, hi)
        L = sum(1 for r in o if r.get("side") == 1)
        src = dict(collections.Counter(str(r.get("source")) for r in o))
        cl = win(calls, lambda r: r["ts"], lo, hi)
        okc = sum(1 for r in cl if r.get("ok"))
        print("%s: aperture %d (long %d / short %d) %s | trade chiusi: %s | realizzato (incl. parziali) %+.1f$ | "
              "Claude: %d chiamate (%d lette) %.3f$" % (
                  lab, len(o), L, len(o) - L, src, summ(tr), sum(_f(r.get("net")) for r in c),
                  len(cl), okc, sum(_f(r.get("cost_usd")) for r in cl)))
    last = win(trades, lambda t: t["ts"], *t24)
    why = collections.Counter(t["why"] for t in last)
    print("motivi di uscita (24h): %s" % dict(why.most_common(6)))
    rec24 = sorted(win(closes, close_ts, *t24), key=close_ts)
    print("chiusure delle ultime 24h (ora UTC | simbolo lato leva | P=parziale | motivo | netto | netto in R | massimo in R):")
    for r in rec24[-16:]:
        t = time.gmtime(close_ts(r) / 1000)
        print("  %02d:%02d | %s %s x%s | %s | %s | %+.1f$ | %s | %s" % (
            t.tm_hour, t.tm_min, r.get("symbol"), "L" if r.get("side") == 1 else "S", r.get("leverage"),
            "P" if r.get("partial") else "-", str(r.get("why"))[:22], _f(r.get("net")),
            r.get("net_r"), r.get("mfe_r")))
    # profitto restituito: arrivato a +1R di massimo favorevole e finito in perdita
    for thr in (0.5, 1.0):
        hit = [t for t in last if t["mfe"] >= thr]
        lost = [t for t in hit if t["net"] < 0]
        print("toccato +%.1fR (24h): %d su %d trade, di cui finiti in perdita %d (%+.1f$)" % (
            thr, len(hit), len(last), len(lost), sum(t["net"] for t in lost)))
    rej = collections.Counter(str(r.get("status"))[:34] for r in win(cands, lambda r: r["ts"], *t24)
                              if str(r.get("status")).startswith("rifiutata"))
    n_c = len(win(cands, lambda r: r["ts"], *t24))
    print("candidati (24h): %d | rifiuti principali: %s" % (n_c, dict(rej.most_common(5))))

    print("--- PER GIORNO UTC (ultimi 6) ---")
    D_o, D_t = collections.defaultdict(list), collections.defaultdict(list)
    for r in opens:
        D_o[day(r["ts"])].append(r)
    for t in trades:
        D_t[day(t["ts"])].append(t)
    days = sorted(set(D_o) | set(D_t))[-6:]
    for k in days:
        print("  %s: aperture %2d | trade chiusi %s" % (k, len(D_o.get(k, [])), summ(D_t.get(k, []))))

    print("--- RIFERIMENTO: primi giorni (12-15/10) ---")
    so = [r for r in opens if day(r["ts"]) in START_DAYS]
    st = [t for t in trades if day(t["ts"]) in START_DAYS]
    nd = len(set(day(r["ts"]) for r in so)) or 1
    print("aperture al giorno %.1f | trade chiusi %s" % (len(so) / nd, summ(st)))
    print("TUTTO dall'inizio: aperture %d | trade chiusi %s | Claude %d chiamate %.2f$" % (
        len(opens), summ(trades), len(calls), sum(_f(r.get("cost_usd")) for r in calls)))


def main(argv):
    d, name = argv[0], argv[1]
    now_ms = int(argv[2]) if len(argv) > 2 else int(time.time() * 1000)
    print("=== %s (conto di prova) ===" % name.upper())
    section_state(d, now_ms)
    rows, bad = load_rows(os.path.join(d, "learning_log.jsonl"))
    if rows is None:
        print("learning_log.jsonl: non leggibile")
        return 0
    if bad:
        print("(righe illeggibili nel registro: %d)" % bad)
    section_log(rows, now_ms)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
