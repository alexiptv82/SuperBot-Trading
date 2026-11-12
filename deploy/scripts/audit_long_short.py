#!/usr/bin/env python3
"""Audit LONG vs SHORT dei registri PAPER (sola lettura): la parte quantitativa dell'audit RC84 del 12/11/2026.

  python3 -I audit_long_short.py --history /percorso/hawk/trade_history.jsonl --label Falco \
      [--since 2026-11-11T00:00:00Z] [--cutoff 2026-11-12T12:37:00Z] [--open-state /percorso/state.json]

Legge il trade_history.jsonl scritto dal desk (engine._close / partial_close: net, net_r, mae_r, mfe_r, hold_min,
side, leverage, trade_type, source, confidence, why, open_ms, close_ms, dca_count, partial) e stampa le tabelle
richieste dall'audit: LONG/SHORT x origine (claude / rules / rules_long_s25) x orizzonte (scalp/medio), chiusure
complete e parziali, prima e dopo il rilascio indicato con --cutoff. Per ogni riga: numero, win rate, profit factor,
P&L netto, risultato medio in R, MAE/MFE medi in R, durata media, leva media e conteggio dei motivi di chiusura.
In coda: ogni LONG perdente con le feature registrate all'apertura, se nel record (features/why), per il riscontro
dello stato del mercato all'ingresso. Non scrive nulla e non apre la rete: si lancia su una COPIA dei dati
(o sul ripristino di un backup), mai sui file vivi mentre il bot li scrive.
"""
import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone


def ts_ms(text):
    return int(datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)


def fmt_ms(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%m-%d %H:%M")


def load_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and "net" in row and "side" in row and "close_ms" in row:
                rows.append(row)
    return rows


def mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and math.isfinite(x)]
    return sum(xs) / len(xs) if xs else None


def agg(rows):
    """Aggrega per TRADE (i parziali con lo stesso id si sommano: net_r e' additivo)."""
    trades = {}
    for r in rows:
        key = r.get("id") or (r.get("symbol"), r.get("open_ms"))
        t = trades.setdefault(key, {"net": 0.0, "net_r": 0.0, "has_r": False, "rows": []})
        t["net"] += r.get("net") or 0.0
        if isinstance(r.get("net_r"), (int, float)):
            t["net_r"] += r["net_r"]
            t["has_r"] = True
        t["rows"].append(r)
    out = []
    for t in trades.values():
        last = max(t["rows"], key=lambda r: r.get("close_ms") or 0)
        full = [r for r in t["rows"] if not r.get("partial")]
        out.append({"net": t["net"], "net_r": t["net_r"] if t["has_r"] else None,
                    "why": (full[-1] if full else last).get("why"), "last": last, "n_partial": len(t["rows"]) - len(full),
                    "closed": bool(full)})
    return out


def table(name, rows):
    trades = agg(rows)
    if not trades:
        return
    nets = [t["net"] for t in trades]
    wins = [n for n in nets if n > 0]
    losses = [-n for n in nets if n < 0]
    pf = (sum(wins) / sum(losses)) if losses else float("inf") if wins else None
    rs = [t["net_r"] for t in trades if t["net_r"] is not None]
    lasts = [t["last"] for t in trades]
    print(f"\n== {name}: {len(trades)} trade ({sum(1 for t in trades if not t['closed'])} solo parziali)")
    print(f"   win rate {100 * len(wins) / len(trades):.0f}%   profit factor {pf if pf is None else round(pf, 2)}   "
          f"P&L netto {sum(nets):+.2f}$   media R {round(mean(rs), 2) if rs else '-'}")
    print(f"   MAE medio R {round(mean([r.get('mae_r') for r in lasts]) or 0, 2)}   "
          f"MFE medio R {round(mean([r.get('mfe_r') for r in lasts]) or 0, 2)}   "
          f"durata media {round((mean([r.get('hold_min') for r in lasts]) or 0) / 60, 1)}h   "
          f"leva media {round(mean([r.get('leverage') for r in lasts]) or 0, 1)}x")
    why = Counter(str(t["why"])[:40] for t in trades)
    print("   motivi:", ", ".join(f"{w} x{n}" for w, n in why.most_common(6)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--history", required=True, help="trade_history.jsonl del portafoglio (COPIA, non il file vivo)")
    ap.add_argument("--label", default="")
    ap.add_argument("--since", default="2026-11-11T00:00:00Z", help="considera solo chiusure da questo istante UTC")
    ap.add_argument("--cutoff", default="2026-11-12T12:37:00Z", help="rilascio RC84: separa prima/dopo")
    ap.add_argument("--open-state", default="", help="state.json per elencare le posizioni ancora aperte (facolt.)")
    a = ap.parse_args(argv)
    rows = [r for r in load_rows(a.history) if (r.get("close_ms") or 0) >= ts_ms(a.since)]
    cut = ts_ms(a.cutoff)
    name = a.label or os.path.basename(os.path.dirname(os.path.abspath(a.history)))
    print(f"# {name}: {len(rows)} righe di chiusura dal {a.since} (parziali comprese)")
    for era, sel in (("prima di RC84", [r for r in rows if r["close_ms"] < cut]),
                     ("dopo RC84", [r for r in rows if r["close_ms"] >= cut])):
        print(f"\n#### {era}")
        for side, sname in ((1, "LONG"), (-1, "SHORT")):
            srows = [r for r in sel if r.get("side") == side]
            table(f"{sname} (tutti)", srows)
            for src in sorted({str(r.get("source")) for r in srows}):
                for tt in sorted({str(r.get("trade_type")) for r in srows if str(r.get("source")) == src}):
                    table(f"{sname} {src} {tt}",
                          [r for r in srows if str(r.get("source")) == src and str(r.get("trade_type")) == tt])
    losers = [t for t in agg(rows) if t["net"] < 0 and t["last"].get("side") == 1]
    if losers:
        print(f"\n#### LONG perdenti ({len(losers)}): contesto registrato all'apertura")
        for t in sorted(losers, key=lambda t: t["net"]):
            r = t["last"]
            print(f"- {r.get('symbol')} {fmt_ms(r.get('open_ms') or 0)}->{fmt_ms(r['close_ms'])} "
                  f"{r.get('leverage')}x {r.get('trade_type')} src={r.get('source')} conf={r.get('confidence')} "
                  f"net {t['net']:+.2f}$ R {t['net_r'] if t['net_r'] is not None else '-'} "
                  f"mae {r.get('mae_r')} mfe {r.get('mfe_r')} why='{r.get('why')}'")
            feats = r.get("features") or {}
            ctx = {k: feats[k] for k in ("ema50_200_4h", "ema20_50_1h", "rsi1h", "roc24h", "daily_trend",
                                         "trend_change", "trend_change_h4", "vol_ratio") if k in feats}
            if ctx or r.get("reason"):
                print(f"    ingresso: {ctx if ctx else ''} motivo='{str(r.get('reason'))[:100]}'")
    if a.open_state and os.path.isfile(a.open_state):
        try:
            with open(a.open_state, encoding="utf-8") as f:
                st = json.load(f)
            pos = (st.get("main") or {}).get("positions") or st.get("positions") or {}
            print(f"\n#### posizioni ancora aperte: {len(pos)}")
            for sym, p in pos.items():
                if isinstance(p, dict):
                    print(f"- {sym} side={p.get('side')} lev={p.get('leverage')} entry={p.get('entry')} "
                          f"type={p.get('trade_type')} source={p.get('source')}")
        except (OSError, ValueError):
            print("\n#### posizioni aperte: state.json illeggibile")
    return 0


if __name__ == "__main__":
    sys.exit(main())
