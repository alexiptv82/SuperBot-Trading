#!/usr/bin/env python3
"""Audit LONG vs SHORT dei registri PAPER di Falco e Toro (RC84, fase 1). SOLA LETTURA, nessuna rete, solo libreria standard.

Uso sulla VPS (copie coerenti fatte da questo programma in una cartella temporanea privata, poi cancellate):
    python3 -I audit_long_short.py --vps /opt/superbot-desk-data
Uso su copie gia' fatte (una cartella per portafoglio, con trade_history.jsonl, learning_log.jsonl, state_v2.json, archive/):
    python3 -I audit_long_short.py --portfolio Falco=/copie/hawk --portfolio Toro=/copie/bull

Che cosa fa:
  * collega ogni chiusura di trade_history.jsonl (anche delle run archiviate dai reset) all'evento "open" di
    learning_log.jsonl con la chiave (simbolo, id, istante di apertura): l'id del motore riparte da 1 a ogni reset,
    quindi da solo non identifica un trade; le chiusure parziali si sommano nel loro trade; le posizioni ancora
    aperte vengono da state_v2.json;
  * separa per ORA DI APERTURA (report principale) e, in un secondo report, per ORA DI CHIUSURA: prima e dopo il
    rilascio RC84 (predefinito 2026-11-12T11:37:00Z = 12:37 Europe/Rome, ora solare UTC+1);
  * confronta LONG e SHORT per portafoglio, strategia (Claude / Rules / S25), orizzonte, durata, leva, funding,
    distanza di SL/TP, R:R pianificato e contesto di mercato registrato all'ingresso;
  * diagnostica ogni trade S25 con le condizioni che ne avevano autorizzato l'ingresso.
Non scrive mai nelle cartelle dei dati: apre i file originali solo in lettura. Stampa solo dati PAPER (nessuna credenziale).
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

VERSION = "audit-long-short-2"
DEFAULT_SINCE = "2026-11-11T00:00:00Z"
DEFAULT_CUTOFF = "2026-11-12T11:37:00Z"          # 12:37 Europe/Rome il 12/11/2026 (CET = UTC+1)
# Explicit dataset selection: do not silently analyze old legacy wallets instead of RC84.
VPS_LAYOUTS = {
    "legacy": (("Falco", "hawk"), ("Toro", "bull")),
    "rc84": (("Falco", "classic-hawk-paper20261111"),
             ("Toro", "classic-bull-paper20261111")),
}
DATA_FILES = ("trade_history.jsonl", "learning_log.jsonl", "state_v2.json")
STRATEGY = {"claude": "Claude", "rules": "Rules", "rules_long_s25": "S25"}
H = 3_600_000
S25_CHASE_ATR = 0.5
S25_STOP_ATR = 1.5
S25_TARGET_ATR = 1.5
CONTEXT_WINDOW_MS = 2 * H


# ---------------------------------------------------------------------------------------------- utilita'
def ts_ms(text):
    return int(datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)


def fmt_ms(ms):
    if not isinstance(ms, (int, float)) or ms <= 0:
        return "-"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%d/%m %H:%MZ")


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else None


def mean(xs):
    xs = [x for x in (num(v) for v in xs) if x is not None]
    return sum(xs) / len(xs) if xs else None


def f2(x, nd=2, suffix=""):
    return "-" if x is None else ("%." + str(nd) + "f%s") % (x, suffix)


def pct(x, nd=2):
    return "-" if x is None else "%.*f%%" % (nd, 100 * x)


def say(msg=""):
    print(msg, flush=True)


# ------------------------------------------------------------------------------------- copie coerenti
def _sig(path):
    st = os.stat(path)
    return (st.st_ino, st.st_size, st.st_mtime_ns)


def snapshot(src_dir, dst_dir, attempts=6):
    """Copia i registri di UN portafoglio in dst_dir. Coerente = nessun file sorgente e' cambiato durante il giro
    di copia (stesso inode, dimensione e data). Apre i sorgenti SOLO in lettura. Ritorna (coerente, tentativi, file)."""
    src_dir, dst_dir = os.path.realpath(src_dir), os.path.realpath(dst_dir)
    if dst_dir == src_dir or dst_dir.startswith(src_dir + os.sep):
        raise SystemExit("ERRORE: la cartella delle copie non puo' stare dentro i dati")
    names = [n for n in DATA_FILES if os.path.isfile(os.path.join(src_dir, n))]
    arch = os.path.join(src_dir, "archive")
    if os.path.isdir(arch):
        for run in sorted(os.listdir(arch)):
            rel = os.path.join("archive", run, "trade_history.jsonl")
            if os.path.isfile(os.path.join(src_dir, rel)):
                names.append(rel)
    for attempt in range(1, attempts + 1):
        before = {n: _sig(os.path.join(src_dir, n)) for n in names}
        for n in names:
            dst = os.path.join(dst_dir, n)
            os.makedirs(os.path.dirname(dst), mode=0o700, exist_ok=True)
            with open(os.path.join(src_dir, n), "rb") as fi, open(dst, "wb") as fo:
                shutil.copyfileobj(fi, fo)
        after = {n: _sig(os.path.join(src_dir, n)) for n in names}
        if before == after and all(os.path.getsize(os.path.join(dst_dir, n)) == after[n][1] for n in names):
            return True, attempt, names
        time.sleep(1.0)
    return False, attempts, names


# ------------------------------------------------------------------------------------------- lettura
def read_jsonl(path):
    rows, bad = [], 0
    try:
        with open(path, "rb") as f:
            for raw in f:
                if not raw.strip():
                    continue
                try:
                    row = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    bad += 1                     # anche l'ultima riga a meta' se il file era in scrittura
                    continue
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    bad += 1
    except OSError:
        pass
    return rows, bad


def load_portfolio(label, folder):
    """Tutto cio' che serve di un portafoglio, letto da una cartella di COPIE."""
    p = {"label": label, "dir": folder, "integrity": Counter(), "notes": []}
    hist_files = [("corrente", os.path.join(folder, "trade_history.jsonl"))]
    arch = os.path.join(folder, "archive")
    if os.path.isdir(arch):
        hist_files += [("archivio " + r, os.path.join(arch, r, "trade_history.jsonl")) for r in sorted(os.listdir(arch))
                       if os.path.isfile(os.path.join(arch, r, "trade_history.jsonl"))]
    hist, seen = [], set()
    for origin, path in hist_files:
        rows, bad = read_jsonl(path)
        p["integrity"]["righe storico illeggibili"] += bad
        for r in rows:
            if not all(k in r for k in ("symbol", "side", "close_ms", "net", "open_ms")):
                p["integrity"]["righe storico senza campi minimi"] += 1
                continue
            ident = json.dumps(r, sort_keys=True)
            if ident in seen:
                p["integrity"]["righe storico duplicate (ignorate)"] += 1
                continue
            seen.add(ident)
            hist.append((origin, r))
    p["hist"] = hist
    learn, bad = read_jsonl(os.path.join(folder, "learning_log.jsonl"))
    p["integrity"]["righe learning illeggibili"] += bad
    p["learn"] = learn
    try:
        with open(os.path.join(folder, "state_v2.json"), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
        p["notes"].append("state_v2.json assente o illeggibile: posizioni aperte non disponibili")
    p["state"] = st if isinstance(st, dict) else {}
    return p


# --------------------------------------------------------------------------------------- ricostruzione
def build_trades(p):
    """Trade = (simbolo, id, open_ms). I parziali si sommano; finale = riga non parziale; aperti da state_v2.json."""
    opens = {}
    closes = defaultdict(list)
    for e in p["learn"]:
        if e.get("ev") == "open" and "id" in e and "symbol" in e:
            key = (e["symbol"], e["id"], e.get("ts"))
            if key in opens:
                p["integrity"]["eventi open duplicati nel learning"] += 1
            opens[key] = e
        elif e.get("ev") == "close" and "id" in e:
            closes[(e.get("symbol"), e.get("id"), e.get("open_ms"))].append(e)
    trades = {}
    for origin, r in p["hist"]:
        key = (r["symbol"], r.get("id"), r["open_ms"])
        t = trades.setdefault(key, {"portfolio": p["label"], "symbol": r["symbol"], "id": r.get("id"),
                                    "open_ms": r["open_ms"], "side": r["side"], "rows": [], "origins": set()})
        t["rows"].append(r)
        t["origins"].add(origin)
    positions = ((p["state"].get("main") or {}).get("positions") or {}) if p["state"] else {}
    run_no = p["state"].get("run_no")
    last_prices = p["state"].get("last_prices") or {}
    for sym, pos in positions.items():
        if not isinstance(pos, dict):
            continue
        key = (pos.get("symbol", sym), pos.get("id"), pos.get("open_ms"))
        t = trades.setdefault(key, {"portfolio": p["label"], "symbol": key[0], "id": key[1], "open_ms": key[2],
                                    "side": pos.get("side"), "rows": [], "origins": set()})
        t["position"] = pos
        t["origins"].add("aperta")
        px = num(last_prices.get(sym)) if isinstance(last_prices, dict) else None
        if px and num(pos.get("entry")) and num(pos.get("qty")):
            t["unrealized_est"] = pos["side"] * (px - pos["entry"]) * pos["qty"]
    ids_by_symbol = defaultdict(set)
    for t in trades.values():
        if t["symbol"] and t["id"] is not None:
            ids_by_symbol[t["id"]].add(t["open_ms"])
    p["integrity"]["id riusati dopo un reset (distinti da open_ms)"] = sum(1 for v in ids_by_symbol.values() if len(v) > 1)
    out = []
    for key, t in trades.items():
        rows = sorted(t["rows"], key=lambda r: (r.get("close_ms") or 0, bool(not r.get("partial"))))
        finals = [r for r in rows if not r.get("partial")]
        parts = [r for r in rows if r.get("partial")]
        if len(finals) > 1:
            p["integrity"]["trade con piu' chiusure finali"] += 1
        final = finals[-1] if finals else None
        pos = t.get("position")
        if final and pos:
            p["integrity"]["trade chiuso ma ancora nello stato"] += 1
        status = "chiuso" if final else ("aperto" if pos else "parziali senza chiusura finale")
        if status.startswith("parziali"):
            p["integrity"]["parziali senza finale ne' posizione aperta"] += 1
        oe = opens.get(key)
        if oe is None:
            p["integrity"]["trade senza evento open nel learning"] += 1
        lc = closes.get(key, [])
        if rows and len(lc) < len(rows):
            p["integrity"]["chiusure dello storico assenti nel learning"] += len(rows) - len(lc)
        first = rows[0] if rows else {}
        src = (oe or {}).get("source") or first.get("source") or (pos or {}).get("source") or "?"
        realized = sum(num(r.get("net")) or 0.0 for r in rows)
        rs = [num(r.get("net_r")) for r in rows]
        last = final or (rows[-1] if rows else {})
        tr = {
            "portfolio": t["portfolio"], "symbol": t["symbol"], "id": t["id"], "open_ms": t["open_ms"],
            "side": t["side"], "source": src, "strategy": STRATEGY.get(src, "altro:" + str(src)),
            "trade_type": (oe or {}).get("trade_type") or first.get("trade_type") or (pos or {}).get("trade_type") or "?",
            "status": status, "close_ms": final.get("close_ms") if final else None,
            "net": realized, "net_r": sum(x for x in rs if x is not None) if rs and all(x is not None for x in rs) else None,
            "fees": sum(num(r.get("fees")) or 0.0 for r in rows), "funding": sum(num(r.get("funding")) or 0.0 for r in rows),
            "why": final.get("why") if final else None, "n_partial": len(parts),
            "mae_r": num(last.get("mae_r")), "mfe_r": num(last.get("mfe_r")),
            "hold_h": (num(final.get("hold_min")) / 60.0) if final and num(final.get("hold_min")) is not None else None,
            "leverage": num((oe or {}).get("leverage")) or num(first.get("leverage")) or num((pos or {}).get("leverage")),
            "margin": num((oe or {}).get("margin_first")) or num((pos or {}).get("total_margin")) or num(first.get("margin")),
            "dca": max([num(r.get("dca_count")) or 0 for r in rows] or [num((pos or {}).get("dca_count")) or 0]),
            "confidence": (oe or {}).get("confidence", first.get("confidence")),
            "reason": str((oe or {}).get("features", {}).get("reason") or first.get("reason") or (pos or {}).get("reason") or "")[:140],
            "open_event": oe, "run_no": (oe or {}).get("run_no", run_no if pos else None),
            "origins": sorted(t["origins"]), "unrealized_est": t.get("unrealized_est"),
        }
        entry = num((oe or {}).get("entry")) or num((pos or {}).get("entry0")) or num(first.get("entry"))
        sl, tp = num((oe or {}).get("sl")), num((oe or {}).get("tp"))
        if sl is None and pos:
            sl, tp = num(pos.get("sl")), num(pos.get("tp"))
        tr["entry"], tr["sl"], tr["tp"] = entry, sl, tp
        tr["sl_pct"] = abs(entry - sl) / entry if entry and sl else None
        tr["tp_pct"] = abs(tp - entry) / entry if entry and tp else None
        tr["rr"] = tr["tp_pct"] / tr["sl_pct"] if tr["sl_pct"] and tr["tp_pct"] else None
        risk = num((oe or {}).get("risk_plan_usd")) or num(first.get("risk_plan_usd")) or num((pos or {}).get("risk_plan_usd"))
        tr["risk_usd"] = risk
        tr["cost_r"] = (tr["fees"] + tr["funding"]) / risk if risk and rows else None
        tr["features"] = (oe or {}).get("features") or (pos or {}).get("features") or {}
        out.append(tr)
    return sorted(out, key=lambda x: (x["open_ms"] or 0, x["portfolio"], x["symbol"]))


# --------------------------------------------------------------------------------------------- metriche
def metrics(trades):
    closed = [t for t in trades if t["status"] == "chiuso"]
    nets = [t["net"] for t in closed]
    wins, losses = [n for n in nets if n > 0], [-n for n in nets if n < 0]
    m = {"n": len(closed), "aperti": sum(1 for t in trades if t["status"] != "chiuso"),
         "win": len(wins), "wr": len(wins) / len(closed) if closed else None,
         "pf": (sum(wins) / sum(losses)) if losses else (float("inf") if wins else None),
         "net": sum(nets), "net_ex_funding": sum(t["net"] + t["funding"] for t in closed),
         "funding": sum(t["funding"] for t in closed), "fees": sum(t["fees"] for t in closed),
         "r": mean(t["net_r"] for t in closed), "mae": mean(t["mae_r"] for t in closed),
         "mfe": mean(t["mfe_r"] for t in closed), "hold": mean(t["hold_h"] for t in closed),
         "lev": mean(t["leverage"] for t in closed), "sl": mean(t["sl_pct"] for t in closed),
         "rrp": mean(t["rr"] for t in closed), "cost_r": mean(t["cost_r"] for t in closed),
         "why": Counter(str(t["why"]) for t in closed)}
    return m


HEAD = ("%-34s %3s %3s %5s %6s %10s %10s %6s %5s %5s %6s %5s %6s %5s %6s" %
        ("gruppo", "n", "ap", "win%", "PF", "netto$", "ex-fund$", "R", "MAE", "MFE", "ore", "leva", "SL%", "R:R", "costR"))


def line(name, trades):
    m = metrics(trades)
    if m["n"] == 0 and m["aperti"] == 0:
        return
    pf = "-" if m["pf"] is None else ("inf" if m["pf"] == float("inf") else "%.2f" % m["pf"])
    say("%-34s %3d %3d %5s %6s %10s %10s %6s %5s %5s %6s %5s %6s %5s %6s" % (
        name[:34], m["n"], m["aperti"], "-" if m["wr"] is None else "%.0f" % (100 * m["wr"]), pf,
        f2(m["net"]), f2(m["net_ex_funding"]), f2(m["r"]), f2(m["mae"]), f2(m["mfe"]), f2(m["hold"], 1),
        f2(m["lev"], 0), f2(None if m["sl"] is None else 100 * m["sl"]), f2(m["rrp"]), f2(m["cost_r"])))
    if m["why"]:
        say("%-34s     motivi: %s" % ("", ", ".join("%s x%d" % (w[:28], n) for w, n in m["why"].most_common(4))))


def era_of(ms, since, cutoff):
    if ms is None:
        return None
    return "0 prima del periodo" if ms < since else ("1 prima di RC84" if ms < cutoff else "2 dopo RC84")


def grouped_report(title, trades, key_ms, since, cutoff):
    say("\n" + "=" * 110)
    say(title)
    say("=" * 110)
    say(HEAD)
    eras = defaultdict(list)
    for t in trades:
        e = era_of(key_ms(t), since, cutoff)
        if e is not None:
            eras[e].append(t)
    for e in sorted(eras):
        say("--- %s" % e[2:])
        for pf in sorted({t["portfolio"] for t in eras[e]}):
            for side, sname in ((1, "LONG"), (-1, "SHORT")):
                sel = [t for t in eras[e] if t["portfolio"] == pf and t["side"] == side]
                if not sel:
                    continue
                line("%s %s (tutti)" % (pf, sname), sel)
                for strat in sorted({t["strategy"] for t in sel}):
                    for tt in sorted({t["trade_type"] for t in sel if t["strategy"] == strat}):
                        line("  %s %s %s %s" % (pf, sname, strat, tt),
                             [t for t in sel if t["strategy"] == strat and t["trade_type"] == tt])


def summary_report(trades):
    say("\n" + "=" * 110)
    say("RIEPILOGO PER PORTAFOGLIO, LATO E STRATEGIA (trade aperti nel periodo; netto realizzato)")
    say("=" * 110)
    say(HEAD)
    for pf in sorted({t["portfolio"] for t in trades}):
        for side, sname in ((1, "LONG"), (-1, "SHORT")):
            for strat in sorted({t["strategy"] for t in trades if t["portfolio"] == pf and t["side"] == side}):
                line("%s %s %s" % (pf, sname, strat), [t for t in trades if t["portfolio"] == pf and t["side"] == side
                                                       and t["strategy"] == strat])
    for side, sname in ((1, "LONG"), (-1, "SHORT")):
        line("TOTALE %s" % sname, [t for t in trades if t["side"] == side])


def context_report(trades):
    """Esito per contesto registrato all'ingresso dal punteggio del desk (solo trade che lo hanno)."""
    say("\n" + "=" * 110)
    say("CONTESTO DI MERCATO ALL'INGRESSO (feature del desk registrate nell'evento open; i valori sono quelli del codice)")
    say("=" * 110)
    with_ctx = [t for t in trades if t["status"] == "chiuso" and "ema50_200_4h" in (t["features"] or {})]
    say("trade chiusi con contesto: %d su %d (S25 non registra il contesto del desk: vedi la diagnostica S25)"
        % (len(with_ctx), sum(1 for t in trades if t["status"] == "chiuso")))
    if not with_ctx:
        return
    say(HEAD)
    for side, sname in ((1, "LONG"), (-1, "SHORT")):
        sel = [t for t in with_ctx if t["side"] == side]
        for feat, lab in (("ema50_200_4h", "trend4h(cod.)"), ("ema20_50_1h", "trend1h"), ("daily_trend", "trend1d")):
            for val, vlab in ((side, "a favore"), (-side, "contro"), (0, "assente")):
                line("%s %s %s" % (sname, lab, vlab), [t for t in sel if (t["features"] or {}).get(feat) == val])
        for lo, hi in ((0, 30), (30, 50), (50, 70), (70, 101)):
            line("%s RSI1h %d-%d" % (sname, lo, hi - 1 if hi < 101 else 100),
                 [t for t in sel if num((t["features"] or {}).get("rsi1h")) is not None and lo <= t["features"]["rsi1h"] < hi])
        line("%s con funding registrato" % sname, [t for t in sel if num((t["features"] or {}).get("funding_rate")) is not None])


def nearest_desk_context(t, learn_all):
    """Per S25 (che non registra il contesto del desk): la riga del learning piu' vicina nel tempo, stesso simbolo,
    di QUALUNQUE portafoglio, con le feature del punteggio del desk (open o candidato), entro 2 ore."""
    best = None
    for pf, e in learn_all:
        fe = e.get("features") or {}
        if e.get("symbol") != t["symbol"] or "ema50_200_4h" not in fe or num(e.get("ts")) is None:
            continue
        d = abs(e["ts"] - t["open_ms"])
        if d <= CONTEXT_WINDOW_MS and (best is None or d < best[0]):
            best = (d, pf, e)
    return best


def s25_report(trades, learn_all, since):
    s25 = [t for t in trades if t["source"] == "rules_long_s25" and (t["open_ms"] or 0) >= since]
    say("\n" + "=" * 110)
    say("DIAGNOSTICA S25 (%d trade nel periodo): condizioni che hanno autorizzato ogni ingresso" % len(s25))
    say("=" * 110)
    if not s25:
        return
    say("Regole S25 (long_s25.py): candela 1h chiusa con EMA9 che incrocia SOPRA il VWAP giornaliero e chiusura sopra entrambi;")
    say("ingresso nell'ora successiva se il prezzo supera il massimo della candela di segnale (trigger) di non piu' di")
    say("%.1f ATR; stop %.1f ATR, target %.1f ATR (R:R 1:1), uscita a tempo dopo 12 ore; leva 15x; NESSUN filtro di trend"
        % (S25_CHASE_ATR, S25_STOP_ATR, S25_TARGET_ATR))
    say("4h/1d, di regime, di volume o di funding. 'pareggio' = win rate minimo per non perdere con R:R 1:1 e questi costi.")
    for t in s25:
        fe = t["features"] or {}
        oe = t["open_event"] or {}
        price = num(oe.get("price")) or t["entry"]
        atr_, trig, e9, vw = num(fe.get("atr1h")), num(fe.get("trigger")), num(fe.get("ema9")), num(fe.get("vwap"))
        say("\n- %s %s id=%s run=%s  aperto %s  chiuso %s  stato=%s  esito='%s'" % (
            t["portfolio"], t["symbol"], t["id"], t["run_no"], fmt_ms(t["open_ms"]), fmt_ms(t["close_ms"]),
            t["status"], t["why"]))
        say("    risultato: netto %s$  R %s  MAE %sR  MFE %sR  durata %sh  leva %sx  margine %s$  commissioni %s$  funding %s$" % (
            f2(t["net"]), f2(t["net_r"]), f2(t["mae_r"]), f2(t["mfe_r"]), f2(t["hold_h"], 1), f2(t["leverage"], 0),
            f2(t["margin"], 0), f2(t["fees"]), f2(t["funding"])))
        if not fe:
            say("    ingresso: evento open NON trovato nel learning (feature S25 non disponibili)")
        else:
            sig_end = num(fe.get("signal_open_ms"))
            say("    segnale: candela 1h aperta %s, EMA9 %s VWAP di %s bp; trigger %s; ATR1h %s (%s del prezzo)" % (
                fmt_ms(sig_end), "sopra il" if e9 and vw and e9 > vw else "NON sopra il",
                f2((e9 - vw) / vw * 1e4, 1) if e9 and vw else "-",
                f2(trig, 6), f2(atr_, 6), pct(atr_ / price) if atr_ and price else "-"))
            say("    ingresso: prezzo %s, %s min dopo la chiusura della candela di segnale, sopra il trigger di %s ATR (limite %.1f)" % (
                f2(price, 6), f2((t["open_ms"] - sig_end - H) / 60000, 0) if sig_end else "-",
                f2((price - trig) / atr_, 2) if price and trig and atr_ else "-", S25_CHASE_ATR))
        say("    piano: SL %s (-%s) TP %s (+%s) R:R %s; 1R = %s$; costi del trade = %s R -> pareggio con win rate %s" % (
            f2(t["sl"], 6), pct(t["sl_pct"]), f2(t["tp"], 6), pct(t["tp_pct"]), f2(t["rr"]), f2(t["risk_usd"]),
            f2(t["cost_r"]), pct((1 + t["cost_r"]) / 2, 0) if t["cost_r"] is not None else "-"))
        twins = [u for u in s25 if u is not t and u["symbol"] == t["symbol"] and u["portfolio"] != t["portfolio"]
                 and abs((u["open_ms"] or 0) - (t["open_ms"] or 0)) <= 15 * 60_000]
        if twins:
            say("    DUPLICATO: stessa apertura S25 anche su %s (%s)" % (twins[0]["portfolio"], fmt_ms(twins[0]["open_ms"])))
        ctx = nearest_desk_context(t, learn_all)
        if ctx:
            d, pf, e = ctx
            c = e["features"]
            sign = {1: "su", -1: "giu", 0: "assente"}
            say("    contesto desk piu' vicino (%s, %s, %+d min): trend4h(cod.) %s, trend1h %s, trend1d %s, RSI1h %s, ROC24h %s, "
                "punteggi long/short %s/%s" % (pf, e.get("ev"), (e["ts"] - t["open_ms"]) / 60000, sign.get(c.get("ema50_200_4h"), "?"),
                                               sign.get(c.get("ema20_50_1h"), "?"), sign.get(c.get("daily_trend"), "?"),
                                               c.get("rsi1h"), pct(num(c.get("roc24h"))), c.get("sig_long"), c.get("sig_short")))
        else:
            say("    contesto desk: nessuna riga del learning con il punteggio del desk entro 2 ore su questo simbolo")


def open_report(trades):
    op = [t for t in trades if t["status"] != "chiuso"]
    say("\n" + "=" * 110)
    say("POSIZIONI ANCORA APERTE (%d) - stima non realizzata sull'ultimo prezzo salvato nello stato, se presente" % len(op))
    say("=" * 110)
    for t in op:
        say("- %s %s %s %s %s aperta %s leva %sx SL %s TP %s parziali %d realizzato %s$ stima aperta %s$ (%s)" % (
            t["portfolio"], t["symbol"], "LONG" if t["side"] == 1 else "SHORT", t["strategy"], t["trade_type"],
            fmt_ms(t["open_ms"]), f2(t["leverage"], 0), f2(t["sl"], 6), f2(t["tp"], 6), t["n_partial"], f2(t["net"]),
            f2(t["unrealized_est"]), t["status"]))


def integrity_report(portfolios, trades):
    say("\n" + "=" * 110)
    say("INTEGRITA' DEI REGISTRI")
    say("=" * 110)
    for p in portfolios:
        tr = [t for t in trades if t["portfolio"] == p["label"]]
        say("%s: righe storico %d (file: %s), eventi learning %d, trade ricostruiti %d (chiusi %d, aperti %d), run nel learning %s" % (
            p["label"], len(p["hist"]), ", ".join(sorted({o for o, _ in p["hist"]})) or "nessuno", len(p["learn"]), len(tr),
            sum(1 for t in tr if t["status"] == "chiuso"), sum(1 for t in tr if t["status"] != "chiuso"),
            sorted({e.get("run_no") for e in p["learn"] if e.get("run_no") is not None})))
        for k, v in sorted(p["integrity"].items()):
            if v:
                say("   %s: %d" % (k, v))
        for n in p["notes"]:
            say("   NOTA: " + n)


# --------------------------------------------------------------------------------------------------- main
def analyze(portfolios_dirs, since, cutoff, copies_info):
    portfolios = [load_portfolio(lab, d) for lab, d in portfolios_dirs]
    trades = []
    for p in portfolios:
        trades += build_trades(p)
    learn_all = [(p["label"], e) for p in portfolios for e in p["learn"]]
    in_window = [t for t in trades if (t["open_ms"] or 0) >= since or (t["close_ms"] or 0) >= since or t["status"] != "chiuso"]
    say("# %s - periodo dal %s; rilascio RC84 %s (12:37 Europe/Rome)" % (VERSION, fmt_ms(since), fmt_ms(cutoff)))
    for info in copies_info:
        say("# " + info)
    integrity_report(portfolios, trades)
    opened = [t for t in in_window if (t["open_ms"] or 0) >= since]
    summary_report(opened)
    grouped_report("REPORT PRINCIPALE - per ORA DI APERTURA", in_window, lambda t: t["open_ms"], since, cutoff)
    grouped_report("REPORT SECONDARIO - per ORA DI CHIUSURA (solo trade chiusi)",
                   [t for t in in_window if t["status"] == "chiuso"], lambda t: t["close_ms"], since, cutoff)
    context_report(opened)
    s25_report(trades, learn_all, since)
    open_report(in_window)
    say("\nLegenda: n=chiusi, ap=aperti, netto$=realizzato dopo commissioni/slippage/funding, ex-fund$=netto senza il funding")
    say("(nel PAPER il funding e' addebitato solo ai LONG), R=risultato medio in multipli del rischio pianificato, MAE/MFE in R,")
    say("ore=durata media, SL%=distanza media dello stop, R:R=pianificato TP/SL, costR=commissioni+funding in R.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--vps", help="radice dei dati: /opt/superbot-v3-paper-runs (RC84) o /opt/superbot-desk-data (legacy)")
    ap.add_argument("--layout", choices=("legacy", "rc84"), default="legacy",
                    help="nome layout obbligatorio da specificare esplicitamente per analisi RC84: --layout rc84")
    g.add_argument("--portfolio", action="append", help="ETICHETTA=CARTELLA di copie gia' fatte (ripetibile)")
    ap.add_argument("--since", default=DEFAULT_SINCE)
    ap.add_argument("--cutoff", default=DEFAULT_CUTOFF, help="rilascio RC84 in UTC (predefinito 12:37 Europe/Rome = 11:37Z)")
    ap.add_argument("--keep-copies", default="", help="con --vps: conserva le copie in questa cartella (nuova, fuori dai dati)")
    a = ap.parse_args(argv)
    since, cutoff = ts_ms(a.since), ts_ms(a.cutoff)
    if a.portfolio:
        dirs = []
        for spec in a.portfolio:
            lab, _, d = spec.partition("=")
            if not lab or not os.path.isdir(d):
                ap.error("--portfolio vuole ETICHETTA=CARTELLA esistente: %s" % spec)
            dirs.append((lab, d))
        return analyze(dirs, since, cutoff, ["analisi di copie gia' fatte: " + ", ".join("%s=%s" % x for x in dirs)])
    root = a.vps
    if a.keep_copies:
        if os.path.exists(a.keep_copies):
            raise SystemExit("ERRORE: --keep-copies deve essere una cartella nuova")
        os.makedirs(a.keep_copies, mode=0o700)
        work = a.keep_copies
    else:
        work = tempfile.mkdtemp(prefix="audit-long-short-")
    try:
        os.chmod(work, 0o700)
        dirs, info = [], ["LAYOUT=%s ROOT=%s" % (a.layout, root)]
        for lab, sub in VPS_LAYOUTS[a.layout]:
            src = os.path.join(root, sub)
            if not os.path.isdir(src):
                if a.layout == "rc84":
                    raise SystemExit("ERRORE: wallet RC84 mancante: %s" % src)
                info.append("%s: cartella %s assente" % (lab, src))
                continue
            if a.layout == "rc84":
                missing = [n for n in DATA_FILES if not os.path.isfile(os.path.join(src, n))]
                if missing:
                    raise SystemExit("ERRORE: dataset RC84 incompleto in %s: %s" % (src, ",".join(missing)))
            ok, att, names = snapshot(src, os.path.join(work, sub))
            if not ok:
                raise SystemExit("ERRORE: copia NON COERENTE, rapporto non generato; riprovare piu' tardi")
            digest = hashlib.sha256()
            for n in names:
                with open(os.path.join(work, sub, n), "rb") as f:
                    digest.update(n.encode() + b"\0" + f.read())
            info.append("%s: copia %s di %d file in %d tentativ%s (impronta copie %s)" % (
                lab, "COERENTE" if ok else "NON COERENTE: i file cambiavano durante la copia, risultati da ripetere",
                len(names), att, "o" if att == 1 else "i", digest.hexdigest()[:16]))
            dirs.append((lab, os.path.join(work, sub)))
        if not dirs:
            raise SystemExit("ERRORE: nessun portafoglio trovato sotto %s" % root)
        return analyze(dirs, since, cutoff, info + ["copie in %s (%s)" % (work, "conservate" if a.keep_copies else "cancellate alla fine")])
    finally:
        if not a.keep_copies:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
