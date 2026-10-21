"""Riepilogo in sola lettura dell'AI in ombra (per il workflow di controllo e per chi guarda i file a mano).
Legge solo i file in <out-root>/ai e stampa testo. Nessuna scrittura, nessuna rete, nessuna chiave."""
import glob
import json
import os
import sys
import time


def _lines(pattern: str) -> list:
    out = []
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path) as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
        except OSError:
            pass
    return out


def _fmt(ms) -> str:
    return time.strftime("%d/%m %H:%M", time.gmtime(ms / 1000)) if ms else "-"


def build(root: str, now_ms: int) -> str:
    base = os.path.join(root, "ai")
    try:
        with open(os.path.join(base, "status.json")) as f:
            s = json.load(f)
    except (OSError, ValueError):
        return "AI in ombra: nessun status.json (container non partito o cartella vuota)"
    trades = _lines(os.path.join(base, "trades-*.jsonl"))
    cycles = _lines(os.path.join(base, "cycles-*.jsonl"))
    m, sp = s.get("model", {}), s.get("spend", {})
    out = ["AI IN OMBRA %s | battito %d min fa | simboli %s/%s | modo %s applicato %s" % (
        s.get("algo"), (now_ms - s["ts_ms"]) // 60000, s.get("symbols_ok"), s.get("symbols_total"), s.get("mode"), s.get("applied")),
        "modello: chiamate ok %s fallite %s ultimo errore '%s' serie %s | spesa oggi %.4f/%.2f mese %.4f/%.1f $" % (
            m.get("calls_ok"), m.get("calls_failed"), m.get("last_error"), m.get("fail_streak"),
            sp.get("day_usd", 0), sp.get("daily_cap", 0), sp.get("month_usd", 0), sp.get("monthly_cap", 0)),
        "conto virtuale: equity %.2f | aperte %s | chiusure registrate %s" % (s.get("equity", 0), s.get("open"), s.get("closed_total"))]
    full = [t for t in trades if not t.get("partial")]
    if trades:
        net = sum(t["net"] for t in trades)
        wins = sum(1 for t in full if t["net"] > 0)
        by_side = {}
        for t in full:
            k = "long" if t["side"] == 1 else "short"
            a = by_side.setdefault(k, [0, 0, 0.0])
            a[0] += 1
            a[1] += 1 if t["net"] > 0 else 0
            a[2] += t["net"]
        why = {}
        for t in full:
            why[t["why"]] = why.get(t["why"], 0) + 1
        out.append("trade chiusi %d (parziali %d): vincenti %d (%.0f%%) netto %.2f $ | %s" % (
            len(full), len(trades) - len(full), wins, 100.0 * wins / max(1, len(full)), net,
            " ".join("%s %d/%d %.1f$" % (k, v[1], v[0], v[2]) for k, v in sorted(by_side.items()))))
        out.append("uscite: " + ", ".join("%s %d" % kv for kv in sorted(why.items(), key=lambda kv: -kv[1])[:6]))
        out.append("ultimi trade: " + " | ".join("%s %s %+.1f$ %s" % (
            t["symbol"], "L" if t["side"] == 1 else "S", t["net"], t["why"][:14]) for t in trades[-6:]))
    else:
        out.append("trade chiusi: nessuno")
    rej, acc_n, fills = {}, 0, 0
    for c in cycles:
        for r in (c.get("decision") or {}).get("results") or []:
            if r["accepted"]:
                acc_n += 1
            else:
                rej[r["reason"]] = rej.get(r["reason"], 0) + 1
        fills += sum(1 for e in c.get("events", []) if e.get("ev") == "fill")
    called = sum(1 for c in cycles if (c.get("decision") or {}).get("called"))
    out.append("cicli %d, chiamate %d, voci accettate %d, aperture eseguite %d | scartate: %s" % (
        len(cycles), called, acc_n, fills, ", ".join("%s %d" % kv for kv in sorted(rej.items(), key=lambda kv: -kv[1])[:6]) or "-"))
    reads = [(c["bar_t"], c["decision"].get("market_read")) for c in cycles if (c.get("decision") or {}).get("market_read")]
    for t, r in reads[-2:]:
        out.append("lettura %s: %s" % (_fmt(t), r[:160]))
    errs = [c["decision"] for c in cycles if (c.get("decision") or {}).get("error")]
    if errs:
        out.append("ultimo errore modello: %s" % errs[-1].get("error_msg", errs[-1].get("error")))
    return "\n".join(out)


if __name__ == "__main__":
    print(build(os.environ.get("AI_OUT", "/out"), int(time.time() * 1000)))
    sys.exit(0)
