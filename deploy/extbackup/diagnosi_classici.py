#!/usr/bin/env python3
"""Diagnostica in SOLA LETTURA della contabilita' e dello storico di Falco (hawk) e Toro (bull).

Uso (root): python3 -I diagnosi_classici.py <cartella-strumenti> <cartella-dati-desk> [<registro-della-prova>]

Apre i file solo in lettura, non scrive nulla, non chiama la rete ne' docker. Stampa soltanto conteggi, id,
date, motivi di chiusura e importi PAPER aggregati: nessun prompt, nessuna nota, nessun testo dei trade.
Usa le stesse funzioni del ripristino (restore_external_backup.py, verificato con SHA-256) per la contabilita'.
"""
import importlib.util
import json
import os
import sys
import time
from collections import Counter

PORTFOLIOS = (("hawk", "Falco"), ("bull", "Toro"))


def load(tools):
    spec = importlib.util.spec_from_file_location("restore_ext", os.path.join(tools, "restore_external_backup.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_json(path):
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    with open(path, encoding="utf8") as f:
        return json.load(f)


def read_jsonl(path):
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    rows, bad = [], 0
    with open(path, encoding="utf8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                bad += 1
    return rows, bad


def utc(ms):
    if not isinstance(ms, (int, float)) or isinstance(ms, bool) or ms <= 0:
        return "-"
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ms / 1000))


def key(r):
    return (r.get("id"), r.get("open_ms"), r.get("close_ms"), round(float(r.get("net") or 0), 6))


def capital_section(st, base):
    cap = st.get("capital")
    if not isinstance(cap, dict):
        print("  salvadanaio: assente nello stato")
        return
    v = cap.get("vault") or {}
    pending = sum(float(x.get("remaining", 0) or 0) for x in (v.get("pending") or []) if isinstance(x, dict))
    proc = Counter("saldo" if val == "settlement" else "prelievo" for _e, val in (v.get("processed") or []))
    print("  salvadanaio: policy %s | schema %s | saldo %s | in attesa %.4f | revisione %s | ultimo rollover %s"
          % (cap.get("policy"), cap.get("schema_version"), v.get("balance"), pending, v.get("revision"),
             v.get("last_rollover_day")))
    print("  salvadanaio: operazioni registrate %s | fondi esterni esclusi %s | stato %s"
          % (dict(proc), cap.get("excluded_external_funds"), cap.get("status")))
    for name in ("salvadanaio-journal.jsonl", "capital-v1-journal.jsonl"):
        r = read_jsonl(os.path.join(base, name))
        if r is None:
            print("  %s: assente" % name)
            continue
        rows, bad = r
        deltas = [float(x["cash_delta"]) for x in rows if isinstance(x, dict) and "cash_delta" in x]
        print("  %s: %d righe (%d illeggibili) | righe con cash_delta %d, somma %.4f"
              % (name, len(rows), bad, len(deltas), sum(deltas)))


def accounting_section(mod, st, closed):
    acc = mod.engine_accounting(st, closed)
    m = st["main"]
    if "errore" in acc:
        print("  contabilita': NON ricostruibile: %s" % acc["errore"])
        return
    naive = m["cash"] + acc["vault"] - (acc["start"] + acc["net"])
    print("  contabilita': capitale iniziale %.4f | somma net %.4f | somma variazioni di cassa %.4f"
          % (acc["start"], acc["net"], acc["delta"]))
    print("  contabilita': cassa %.4f | salvadanaio %.4f | impegno posizioni aperte %.4f | commissione %s bp"
          % (m["cash"], acc["vault"], acc["committed"], acc["fee_bp"]))
    print("  contabilita': differenza con la regola semplice (net) %.4f | con la regola del motore %.4f"
          % (naive, acc["diff"]))
    print("  contabilita': perdite oltre il margine assorbite dal motore: %d trade, %.4f"
          % (acc["absorbed"], acc["excess"]))
    for c in closed:
        r = mod.close_cash_delta(c, acc["fee_bp"])
        if r and r[1] > 1e-6:
            print("    assorbita: id %s | chiuso %s | motivo %s | net %.4f | margine %.4f | eccedenza %.4f"
                  % (c.get("id"), utc(c.get("close_ms")), str(c.get("why"))[:30], float(c["net"]),
                     float(c["margin"]), r[1]))


def history_section(st, base, closed):
    run, started = st.get("run_no"), st.get("run_started_ms")
    r = read_jsonl(os.path.join(base, "trade_history.jsonl"))
    if r is None:
        print("  storico: assente")
        return
    hist, bad = r
    tags = Counter(x.get("run_no") if isinstance(x.get("run_no"), int) else "senza" for x in hist)
    print("  storico: %d righe (%d illeggibili) | etichette run %s | parziali %d"
          % (len(hist), bad, dict(tags), sum(1 for x in hist if x.get("partial"))))
    hk, sk = Counter(key(x) for x in hist), Counter(key(c) for c in closed)
    only_h = [x for x in hist if (hk - sk)[key(x)] > 0]
    only_s = [c for c in closed if (sk - hk)[key(c)] > 0]
    dup = sum(n - 1 for n in hk.values() if n > 1)
    print("  confronto: in comune %d | solo nello storico %d | solo nello stato %d | doppioni esatti nello "
          "storico %d" % (sum((hk & sk).values()), len(only_h), len(only_s), dup))
    state_ids = {c.get("id"): c for c in closed}
    for label, rows in (("solo nello storico", only_h), ("solo nello stato", only_s)):
        if not rows:
            continue
        ids = [x.get("id") for x in rows]
        ids_num = [i for i in ids if isinstance(i, int)]
        opens = [x.get("open_ms") for x in rows if isinstance(x.get("open_ms"), (int, float))]
        closes = [x.get("close_ms") for x in rows if isinstance(x.get("close_ms"), (int, float))]
        print("  %s: %d righe | id %s..%s | aperti %s .. %s | chiusi %s .. %s"
              % (label, len(rows), min(ids_num) if ids_num else "-", max(ids_num) if ids_num else "-",
                 utc(min(opens) if opens else 0), utc(max(opens) if opens else 0),
                 utc(min(closes) if closes else 0), utc(max(closes) if closes else 0)))
        print("    id: %s" % ids[:60])
        if label == "solo nello storico":
            if isinstance(started, (int, float)):
                print("    aperti prima dell'inizio della run corrente (%s): %d"
                      % (utc(started), sum(1 for o in opens if o < started)))
            same_id = [x for x in rows if x.get("id") in state_ids]
            same_pos = sum(1 for x in same_id if state_ids[x["id"]].get("open_ms") == x.get("open_ms"))
            print("    con un id presente nello stato: %d (stessa apertura %d, apertura diversa = id riusato %d)"
                  % (len(same_id), same_pos, len(same_id) - same_pos))
            print("    parziali %d | motivi %s" % (sum(1 for x in rows if x.get("partial")),
                                                    dict(Counter(str(x.get("why"))[:25] for x in rows))))
            print("    oltre next_id=%s: %d" % (st["main"].get("next_id"),
                                                sum(1 for i in ids_num if i >= st["main"].get("next_id", 0))))
    # registro di apprendimento: a quale run appartengono le chiusure
    lr = read_jsonl(os.path.join(base, "learning_log.jsonl"))
    if lr is not None:
        closes = [x for x in lr[0] if x.get("ev") == "close"]
        by_run = Counter(x.get("run_no") for x in closes)
        print("  apprendimento: chiusure per run %s" % dict(by_run))
        if only_h:
            lk = {}
            for x in closes:
                lk.setdefault(key(x), x.get("run_no"))
            found = Counter(lk.get(key(x), "assente") for x in only_h)
            print("    righe 'solo nello storico' ritrovate nel registro di apprendimento, per run: %s" % dict(found))
    # archivi delle run precedenti (solo nomi e conteggi)
    arch = os.path.join(base, "archive")
    if os.path.isdir(arch) and not os.path.islink(arch):
        names = sorted(n for n in os.listdir(arch) if os.path.isdir(os.path.join(arch, n)))
        print("  archivi delle run precedenti: %d" % len(names))
        hk_only = Counter(key(x) for x in only_h)
        for n in names:
            d = os.path.join(arch, n)
            s = read_json(os.path.join(d, "state_v2.json")) or {}
            h = read_jsonl(os.path.join(d, "trade_history.jsonl"))
            hrows = h[0] if h else []
            inside = sum((Counter(key(x) for x in hrows) & hk_only).values())
            print("    %s: run %s | storico %d righe | di cui 'solo nello storico' attuale %d"
                  % (n, s.get("run_no"), len(hrows), inside))
    else:
        print("  archivi delle run precedenti: nessuna cartella archive/")


def main():
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        return 2
    mod = load(sys.argv[1])
    desk = sys.argv[2]
    for p, label in PORTFOLIOS:
        base = os.path.join(desk, p)
        print("== %s (%s)" % (label, p))
        try:
            st = read_json(os.path.join(base, "state_v2.json"))
        except ValueError:
            st = None
        if not isinstance(st, dict) or not isinstance(st.get("main"), dict):
            print("  stato: assente o illeggibile")
            continue
        m = st["main"]
        closed = m.get("closed") or []
        print("  stato: run %s | iniziata %s | modo %s | next_id %s | chiusi %d (parziali %d) | posizioni aperte %d"
              % (st.get("run_no"), utc(st.get("run_started_ms")), st.get("mode"), m.get("next_id"), len(closed),
                 sum(1 for c in closed if c.get("partial")), len(m.get("positions") or {})))
        capital_section(st, base)
        accounting_section(mod, st, closed)
        history_section(st, base, closed)
    if len(sys.argv) == 4 and os.path.isfile(sys.argv[3]):
        print("== problemi registrati dalla prova (%s)" % os.path.basename(sys.argv[3]))
        with open(sys.argv[3], encoding="utf8", errors="replace") as f:
            for line in f:
                if "ERRORE:" in line or "ANOMALIA" in line or "RISULTATO" in line:
                    print("  " + line.strip()[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
