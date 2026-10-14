"""Edge scan: esiste una fetta dei segnali V1 con vantaggio LORDO sopra i costi?

Per ogni segnale storico (stessi segnali e stesse candele del simulatore dei
profili) misura il rendimento lordo in punti base (bp) dopo lo slippage e
prima delle commissioni, con diversi modi di uscita:

  P8    uscita come il bot attuale (stop 8 x ATR, TP 1.5 / 3.0 x stop, max 12 h)
  P1    uscita come il vecchio bot (stop 1 x ATR)
  H30 / H120 / H720   uscita a tempo fisso dopo 30 / 120 / 720 minuti

I segnali si ripetono ogni 5 minuti sullo stesso movimento: per non contare
due volte la stessa operazione, dentro ogni fetta si tiene un solo segnale per
simbolo alla volta (il successivo solo dopo l'uscita del precedente).

Controllo anti-fortuna (leave-one-window-out): le fette si SCELGONO su una
finestra di 30 giorni e si VERIFICANO sull'altra, mai sulla stessa.

Sola lettura: non tocca il bot ne' l'exchange (a parte il download di candele
pubbliche se la cache manca).
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys
import time
from collections import defaultdict

import risk_profile_sim as sim
from risk_profiles import MEDIUM_TP_RATIO, SCALP_TP_RATIO

ONE_HOUR_MS = 3_600_000

# nome -> (tipo, parametro)
SCHEMES = {
    "P8": ("profile", 8.0),
    "P1": ("profile", 1.0),
    "H30": ("horizon", 30),
    "H120": ("horizon", 120),
    "H720": ("horizon", 720),
}
STRENGTH_STEPS = (50, 60, 70, 80, 90)
DIM_ORDER = ("tipo", "simbolo", "lato", "ora", "forza")


# ─────────────────────────────────────────────────────────────────────────────
# Misura per segnale
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_signal(candles: list, sig: dict, scheme: str, slip: float,
                    max_hold: int = 720):
    """(indice_uscita, rendimento_lordo_bp) o None se il segnale non e' valutabile."""
    kind, param = SCHEMES[scheme]
    is_long = sig["side"] == "long"
    sgn = 1.0 if is_long else -1.0
    i = sig["i"]
    price = sig["price"]
    entry = price * (1.0 + sgn * slip)               # slippage avverso in ingresso
    if kind == "profile":
        mult = (1.0 if sig["trade_type"] == "scalp" else 2.0) * param
        dist = sig["atr"] * mult
        if not (dist > 0):
            return None
        ratio = SCALP_TP_RATIO if sig["trade_type"] == "scalp" else MEDIUM_TP_RATIO
        sl = price - sgn * dist
        tp = price + sgn * dist * ratio
        if sl <= 0 or tp <= 0:
            return None
        liq = 0.0 if is_long else 1e18               # senza liquidazione: il rischio e' a parte
        j, exit_price, _ = sim.simulate_exit(candles, i, sig["side"], sl, tp, liq, max_hold, slip)
    else:
        j = i + int(param)
        if j >= len(candles):
            return None
        exit_price = candles[j][4] * (1.0 - sgn * slip)
    gross_bp = sgn * (exit_price - entry) / entry * 10_000.0
    return j, gross_bp


def deoverlap(rows: list) -> list:
    """rows: (simbolo, i_ingresso, j_uscita, lordo_bp). Un solo segnale per
    simbolo alla volta: il successivo solo dopo l'uscita del precedente."""
    last: dict = {}
    out = []
    for r in sorted(rows, key=lambda r: (r[0], r[1])):
        if r[1] <= last.get(r[0], -1):
            continue
        out.append(r)
        last[r[0]] = r[2]
    return out


def summarize(rows: list, fee_rt_bps: float) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "mean": 0.0, "win_net": 0.0, "t": 0.0, "net": -fee_rt_bps}
    vals = [r[3] for r in rows]
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1) if n > 1 else 0.0
    se = math.sqrt(var / n) if var > 0 else 0.0
    return {
        "n": n,
        "mean": mean,
        "win_net": 100.0 * sum(1 for v in vals if v > fee_rt_bps) / n,
        "t": mean / se if se > 0 else 0.0,
        "net": mean - fee_rt_bps,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Fette
# ─────────────────────────────────────────────────────────────────────────────

def signal_features(sig: dict) -> dict:
    hour = int((sig["ts"] // ONE_HOUR_MS) % 24)
    start = (hour // 4) * 4
    return {
        "tipo": [sig["trade_type"]],
        "simbolo": [sig["symbol"].split("/")[0]],
        "lato": [sig["side"]],
        "ora": [f"h{start:02d}-{start + 3:02d}"],
        "forza": [f"f>={t}" for t in STRENGTH_STEPS if sig["strength"] >= t],
    }


def build_slices(signals: list) -> dict:
    """chiave (tuple di 'dim=valore' ordinato) -> lista di indici di segnale.
    Singole dimensioni e tutte le coppie di dimensioni."""
    slices: dict = defaultdict(list)
    for k, sig in enumerate(signals):
        feats = signal_features(sig)
        for r in (1, 2):
            for dims in itertools.combinations(DIM_ORDER, r):
                for combo in itertools.product(*(feats[d] for d in dims)):
                    key = tuple(f"{d}={v}" for d, v in zip(dims, combo))
                    slices[key].append(k)
    return slices


def slice_name(key: tuple) -> str:
    return " & ".join(key)


# ─────────────────────────────────────────────────────────────────────────────
# Analisi
# ─────────────────────────────────────────────────────────────────────────────

def analyze_window(signals: list, candles: dict, slip: float, max_hold: int) -> dict:
    """Per ogni schema: righe (simbolo, i, j, lordo) per segnale (None se non valutabile)."""
    per_scheme: dict = {}
    for name in SCHEMES:
        rows = []
        for sig in signals:
            res = evaluate_signal(candles[sig["symbol"]], sig, name, slip, max_hold)
            rows.append(None if res is None else (sig["symbol"], sig["i"], res[0], res[1]))
        per_scheme[name] = rows
    return per_scheme


def slice_rows(rows_by_signal: list, idxs: list) -> list:
    return deoverlap([rows_by_signal[k] for k in idxs if rows_by_signal[k] is not None])


def slice_stats(rows_by_signal: list, slices: dict, fee: float) -> dict:
    return {key: summarize(slice_rows(rows_by_signal, idxs), fee) for key, idxs in slices.items()}


def gate_oos(a_stats: dict, b_rows: list, b_slices: dict, fee: float,
             k: float, min_n: int) -> dict:
    """Sceglie su A le fette con media lorda >= k x costi (n >= min_n) e le
    verifica su B (unione delle fette scelte, poi un solo segnale per simbolo)."""
    chosen = [key for key, s in a_stats.items() if s["n"] >= min_n and s["mean"] >= k * fee]
    confirmed = 0
    union: set = set()
    for key in chosen:
        idxs = b_slices.get(key, [])
        union.update(idxs)
        if summarize(slice_rows(b_rows, idxs), fee)["mean"] >= fee and len(idxs) > 0:
            confirmed += 1
    pooled = summarize(slice_rows(b_rows, sorted(union)), fee)
    return {"chosen": len(chosen), "confirmed": confirmed, "pooled": pooled}


def fmt(s: dict) -> str:
    return f"n{s['n']} {s['mean']:+.1f}bp t{s['t']:+.1f}"


def run(args) -> dict:
    fee = args.fee_rt_bps
    slip = args.slip_bps / 10_000.0
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    offsets = [float(x) for x in args.offsets.split(",") if x.strip()]
    windows: dict = {}
    for off in offsets:
        end_ms = int(time.time() * 1000 - off * 86_400_000) if off > 0 else None
        tag = f"c{args.candles}_o{off:g}"
        candles: dict = {}
        signals: list = []
        print(f"\n##### Finestra offset {off:g} giorni #####", flush=True)
        for sym in symbols:
            data = sim.load_or_fetch_candles(sym, args.candles, end_ms, args.cache_dir, tag)
            if len(data) < sim.WINDOW_SIZE * 60 + args.max_hold + 10:
                print(f"  [skip] {sym}: storico insufficiente")
                continue
            candles[sym] = data
            signals.extend(sim.load_or_generate_signals(
                sym, data, args.stride, args.max_hold, args.cache_dir, tag))
        if not signals:
            print("Nessun segnale.", file=sys.stderr)
            sys.exit(1)
        label = f"W{off:g}"
        slices = build_slices(signals)
        per_scheme = analyze_window(signals, candles, slip, args.max_hold)
        stats = {name: slice_stats(rows, slices, fee) for name, rows in per_scheme.items()}
        base = {name: summarize(deoverlap([r for r in rows if r]), fee) for name, rows in per_scheme.items()}
        windows[label] = {"signals": signals, "slices": slices, "rows": per_scheme,
                          "stats": stats, "base": base}
        print(f"  {label}: {len(signals)} segnali, {len(slices)} fette", flush=True)

    labels = list(windows)
    report: dict = {"fee_rt_bps": fee, "slip_bps": args.slip_bps, "windows": labels}
    out_lines: dict = {}

    # 1) Baseline per schema e finestra
    lines = [f"Costi di andata/ritorno {fee:g} bp; 'lordo' = dopo slippage, prima delle commissioni",
             "un solo segnale per simbolo alla volta; vincita = lordo > costi"]
    for name in SCHEMES:
        parts = []
        for lab in labels:
            b = windows[lab]["base"][name]
            parts.append(f"{lab}: n{b['n']} lordo {b['mean']:+.1f} netto {b['net']:+.1f} win {b['win_net']:.0f}% t{b['t']:+.1f}")
        lines.append(f"{name}: " + " | ".join(parts))
    out_lines["Baseline per schema"] = lines
    report["base"] = {lab: windows[lab]["base"] for lab in labels}

    # 2) Fette singole per lo schema P8 (il bot attuale) e H120
    for scheme in ("P8", "H120"):
        lines = [f"schema {scheme} (lordo bp, un segnale per simbolo alla volta)"]
        keys = sorted({k for lab in labels for k in windows[lab]["slices"] if len(k) == 1})
        for key in keys:
            cells = []
            for lab in labels:
                s = windows[lab]["stats"][scheme].get(key)
                cells.append(f"{lab} {fmt(s)}" if s and s["n"] else f"{lab} -")
            lines.append(f"{slice_name(key)}: " + " | ".join(cells))
        out_lines[f"Fette singole {scheme}"] = lines

    # 3) Scelta su una finestra, verifica sull'altra
    lines = [f"scelgo su A le fette con n>={args.min_n} e lordo >= k x {fee:g} bp, verifico su B",
             "chosen = fette scelte; ok = quante restano >= costi su B; OOS = unione delle fette su B"]
    gate_report = []
    for name in SCHEMES:
        for k in (1.0, 1.5):
            for a, b in itertools.permutations(labels, 2):
                g = gate_oos(windows[a]["stats"][name], windows[b]["rows"][name],
                             windows[b]["slices"], fee, k, args.min_n)
                p = g["pooled"]
                lines.append(f"{name} k{k:g} {a}->{b}: chosen {g['chosen']} ok {g['confirmed']} | OOS n{p['n']} lordo {p['mean']:+.1f} netto {p['net']:+.1f} t{p['t']:+.1f}")
                gate_report.append({"scheme": name, "k": k, "from": a, "to": b, **{
                    "chosen": g["chosen"], "confirmed": g["confirmed"], "oos": p}})
    out_lines["Scelta su A, verifica su B"] = lines
    report["gate"] = gate_report

    # 4) Migliori fette in-sample e loro esito fuori campione (P8 e H120)
    for scheme in ("P8", "H120"):
        lines = [f"schema {scheme}: top 6 su A (n>={args.min_n}) -> stesso filtro su B"]
        for a, b in itertools.permutations(labels, 2):
            top = sorted(((k, s) for k, s in windows[a]["stats"][scheme].items() if s["n"] >= args.min_n),
                         key=lambda kv: kv[1]["mean"], reverse=True)[:6]
            for key, s in top:
                sb = windows[b]["stats"][scheme].get(key, {"n": 0, "mean": 0.0, "t": 0.0})
                lines.append(f"{a}->{b} {slice_name(key)}: A {fmt(s)} | B {fmt(sb)}")
        out_lines[f"Top in-sample {scheme}"] = lines

    # 5) Fette con lordo >= costi in TUTTE le finestre (n>=min_n ovunque)
    lines = []
    stable_report = []
    for name in SCHEMES:
        both_pos = both_fee = tot = 0
        found = []
        for key in windows[labels[0]]["slices"]:
            ss = [windows[lab]["stats"][name].get(key) for lab in labels]
            if any(s is None or s["n"] < args.min_n for s in ss):
                continue
            tot += 1
            if all(s["mean"] > 0 for s in ss):
                both_pos += 1
            if all(s["mean"] >= fee for s in ss):
                both_fee += 1
                found.append((min(s["mean"] for s in ss), key, ss))
        lines.append(f"{name}: fette valutabili {tot}, lordo>0 in tutte {both_pos}, lordo>=costi in tutte {both_fee}")
        for _, key, ss in sorted(found, key=lambda x: x[0], reverse=True)[:4]:
            lines.append("   " + slice_name(key) + ": " + " | ".join(
                f"{lab} {fmt(s)}" for lab, s in zip(labels, ss)))
            stable_report.append({"scheme": name, "slice": slice_name(key)})
    out_lines["Fette stabili in tutte le finestre"] = lines
    report["stable"] = stable_report

    for title, lines in out_lines.items():
        print(f"\n===== {title} =====")
        print("\n".join(lines))
        if args.annotate:
            # le annotazioni hanno un limite di lunghezza: spezza in blocchi
            chunk = 14
            for part, start in enumerate(range(0, len(lines), chunk), 1):
                suffix = f" ({part})" if len(lines) > chunk else ""
                sim.notice(f"Edge scan - {title}{suffix}", [l[:230] for l in lines[start:start + chunk]])
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Edge scan sui segnali V1")
    ap.add_argument("--symbols", default=sim.DEFAULT_SYMBOLS)
    ap.add_argument("--candles", type=int, default=43200)
    ap.add_argument("--stride", type=int, default=5)
    ap.add_argument("--max-hold", type=int, default=720)
    ap.add_argument("--offsets", default="0,30", help="finestre (giorni fa), separate da virgola")
    ap.add_argument("--fee-rt-bps", type=float, default=12.0, help="commissioni andata+ritorno in bp")
    ap.add_argument("--slip-bps", type=float, default=2.0, help="slippage per lato in bp")
    ap.add_argument("--min-n", type=int, default=40)
    ap.add_argument("--cache-dir", default="")
    ap.add_argument("--out", default="edge_scan_results.json")
    ap.add_argument("--annotate", action="store_true")
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    sim.NOTICE_LABEL = args.label
    report = run(args)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1, default=str)
    print(f"\nRisultati salvati in {args.out}")


if __name__ == "__main__":
    main()
