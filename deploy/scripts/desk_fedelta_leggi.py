"""Lettore di sola lettura per il controllo di fedelta' del banco di prova: legge learning_log.jsonl di UN bot e stampa,
una riga JSON per trade, le informazioni dell'apertura e della chiusura. Non scrive nulla.
Uso: python3 -I - <cartella-dati-del-bot> [data-inizio YYYY-MM-DD]   (legge lo script da stdin)"""
import json
import sys
import time

KEEP = ("sig_side", "sig_score", "sig_long", "sig_short", "atr_pct", "sig_sl_pct", "sig_tp_pct", "rsi1h", "roc24h",
        "vol_ratio", "ema20_50_1h", "ema50_200_4h", "daily_trend", "price", "conf", "dec_sl_pct", "dec_tp_pct")


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    since = sys.argv[2] if len(sys.argv) > 2 else "2026-10-12"
    since_ms = int(time.mktime(time.strptime(since, "%Y-%m-%d")) * 1000)
    opens, trades = {}, {}
    with open(folder.rstrip("/") + "/learning_log.jsonl", encoding="utf-8") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if not isinstance(e, dict):
                continue
            k = (e.get("run_no"), e.get("id"))
            if e.get("ev") == "open":
                opens[k] = e
            elif e.get("ev") == "close":
                t = trades.setdefault(k, {"net": 0.0, "done": False})
                try:
                    t["net"] += float(e.get("net") or 0.0)
                except (TypeError, ValueError):
                    pass
                if not e.get("partial"):
                    t["done"] = True
                    t["cts"] = e.get("close_ms") or e.get("ts")
                    t["why"] = str(e.get("why") or "")[:40]
    n = 0
    for k, o in opens.items():
        ts = o.get("ts") or 0
        if ts < since_ms:
            continue
        t = trades.get(k)
        f = o.get("features") or {}
        row = {"id": o.get("id"), "ts": ts, "sym": o.get("symbol"), "side": o.get("side"), "px": o.get("price"),
               "entry": o.get("entry"), "sl": o.get("sl"), "tp": o.get("tp"), "lev": o.get("leverage"),
               "mar": o.get("margin_first"), "type": o.get("trade_type"), "src": o.get("source"),
               "conf": o.get("confidence"), "split": bool(o.get("split_plan")),
               "f": {x: f.get(x) for x in KEEP},
               "net": (t or {}).get("net") if t and t.get("done") else None,
               "cts": (t or {}).get("cts") if t and t.get("done") else None,
               "why": (t or {}).get("why") if t and t.get("done") else None}
        print(json.dumps(row, separators=(",", ":")))
        n += 1
    sys.stderr.write(f"[LETTURA] {n} aperture dal {since}\n")


main()
