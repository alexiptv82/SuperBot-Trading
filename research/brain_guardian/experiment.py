"""Esperimento PREREGISTRATO: varianti di uscita, filtri e protezioni di portafoglio su candele reali Bitget 1m.

Due modi:
* ``structural``: ingressi di CONTROLLO (lato casuale, stop 0,40-0,91% come il Brain, ogni ora). Misura cosa fanno
  le regole quando l'ingresso NON ha vantaggio: una variante che migliora qui migliora la gestione, non il segnale.
* ``brain``: ingressi VERI dal pacchetto di esportazione del journal (``journal_export.py``); prima si verifica che il
  replay della variante A riproduca le chiusure reali, poi si confrontano le varianti sugli stessi ingressi.

Calibrazione e verifica separate nel tempo (``--split``): la combinazione E si sceglie solo nel primo periodo.
Nessuna rete: le candele sono CSV ``ts,o,h,l,c,v`` gia' scaricati.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

from research.brain_guardian.replay import (HOUR, MINUTE, Bar, Costs, Entry, EntryFilter, ExitPolicy,
                                            PortfolioGuard, Variant, metrics, run_portfolio, simulate_exit)

# Ingressi veri: il fill_price del journal include gia' lo slippage d'ingresso (mai contarlo due volte).
BRAIN_COSTS = Costs(fee_bp=6.0, entry_slippage_bp=0.0, stop_slippage_bp=2.0)

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT")

# ---- varianti fissate PRIMA di eseguire (non modificare dopo aver visto i risultati)
VARIANTS = {
    "A_baseline": Variant("A_baseline"),
    "B1_breakeven_1R": Variant("B1_breakeven_1R", exit=ExitPolicy("B1", be_trigger_r=1.0)),
    "B2_trailing_1R": Variant("B2_trailing_1R", exit=ExitPolicy("B2", tp_r=None, trail_trigger_r=1.0, trail_r=1.0)),
    "B3_partial_half_1R": Variant("B3_partial_half_1R", exit=ExitPolicy("B3", partial_r=1.0, partial_frac=0.5)),
    "C1_stop_4x_costs": Variant("C1_stop_4x_costs", filt=EntryFilter(min_stop_cost_mult=4.0)),
    "C2_stop_1p5_atr": Variant("C2_stop_1p5_atr", filt=EntryFilter(min_stop_atr_mult=1.5)),
    "D1_cooldown_4h": Variant("D1_cooldown_4h", guard=PortfolioGuard(cooldown_h_after_stop=4)),
    "D2_max2_same_side": Variant("D2_max2_same_side", guard=PortfolioGuard(max_same_side_open=2)),
    "D3_equity_brakes": Variant("D3_equity_brakes", guard=PortfolioGuard(hwm_drawdown_halt=0.10, daily_loss_halt=0.05)),
}
FAMILIES = {"exit": ("A_baseline", "B1_breakeven_1R", "B2_trailing_1R", "B3_partial_half_1R"),
            "filter": ("A_baseline", "C1_stop_4x_costs", "C2_stop_1p5_atr"),
            "guard": ("A_baseline", "D1_cooldown_4h", "D2_max2_same_side", "D3_equity_brakes")}


def load_bars(folder: Path, symbols) -> dict:
    out = {}
    for s in symbols:
        p = folder / f"{s}_1m.csv"
        if not p.exists():
            continue
        rows = []
        with p.open() as fh:
            for r in csv.reader(fh):
                if r and r[0].isdigit():
                    rows.append(Bar(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])))
        rows.sort(key=lambda b: b.t)
        out[s] = rows
    return out


def control_entries(bars: dict, start: int, end: int, seed: int) -> list:
    rng = random.Random(seed)
    out = []
    for s, bs in bars.items():
        idx = {b.t: b for b in bs}
        t = (start // HOUR + 1) * HOUR
        while t < end:
            prev = idx.get(t - MINUTE)
            if prev is not None:
                side = rng.choice((1, -1))
                dist = rng.uniform(0.0040, 0.0091)
                out.append(Entry(t + 20_000, s, side, prev.c, prev.c * (1 - side * dist), f"ctl{seed}"))
            t += HOUR
    return out


def brain_entries(export: dict) -> tuple[list, list]:
    entries, actual = [], []
    for t in export["trades"]:
        if not t.get("symbol") or t.get("side") not in (1, -1):
            continue
        e = Entry(int(t["opened_ms"]), t["symbol"], int(t["side"]), float(t["fill_price"]), float(t["stop_price"]),
                  t["position_id"])
        entries.append(e)
        actual.append(t)
    return entries, actual


def combo(is_results: dict) -> Variant:
    """Combinazione E: per famiglia la variante migliore per PnL netto nel SOLO periodo di calibrazione."""
    pick = {f: max(names, key=lambda n: is_results[n]["net_pnl"]) for f, names in FAMILIES.items()}
    ex, fl, gd = (VARIANTS[pick[f]] for f in ("exit", "filter", "guard"))
    return Variant("E_combo[" + "+".join(pick.values()) + "]", exit=ex.exit, filt=fl.filt, guard=gd.guard)


def run_all(entries, bars, variants, costs: Costs = Costs()) -> dict:
    return {name: metrics(run_portfolio(entries, bars, v, costs)) for name, v in variants.items()}


def fidelity(entries, actual, bars) -> list:
    """Variante A sugli STESSI ingressi e con la STESSA quantita' reale: motivo e PnL netto contro il journal."""
    out = []
    for e, t in zip(entries, actual):
        c = t.get("close")
        if not c:
            continue
        fee = float(c.get("fee_bps") or 6)
        try:
            r = simulate_exit(e, bars.get(e.symbol) or [], float(t["quantity"]), ExitPolicy(),
                              Costs(fee_bp=fee, entry_slippage_bp=0.0, stop_slippage_bp=2.0))
        except ValueError:
            out.append({"id": t["position_id"][:10], "reason_real": c["reason"], "reason_replay": "no_bars"})
            continue
        out.append({"id": t["position_id"][:10], "reason_real": c["reason"], "reason_replay": r.reason,
                    "pnl_real": round(float(c["realized_pnl"]), 4), "pnl_replay": round(r.pnl, 4),
                    "exit_bar_replay": r.exit_t // MINUTE - 1,
                    # il journal registra l'elaborazione del servizio uscite: di norma il minuto DOPO la candela.
                    # Un ritardo > 0 indica uscite tardive (feed fermo o servizio lento): da contare sui dati veri.
                    "close_delay_min": int(c["closed_ms"]) // MINUTE - r.exit_t // MINUTE})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("structural", "brain"))
    ap.add_argument("--bars", required=True)
    ap.add_argument("--start-ms", type=int, default=1790812800000)       # 2026-10-01
    ap.add_argument("--split-ms", type=int, default=1793491200000)       # 2026-11-01
    ap.add_argument("--end-ms", type=int, default=None)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--export")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.mode == "structural":
        bars = load_bars(Path(a.bars), SYMBOLS)
        end = a.end_ms or min(bs[-1].t for bs in bars.values()) - 25 * HOUR
        report = {"mode": "structural", "symbols": sorted(bars), "start_ms": a.start_ms, "split_ms": a.split_ms,
                  "end_ms": end, "seeds": {}}
        for seed in range(1, a.seeds + 1):
            ins = control_entries(bars, a.start_ms, a.split_ms, seed)
            oos = control_entries(bars, a.split_ms, end, 1000 + seed)
            r_is = run_all(ins, bars, VARIANTS)
            e = combo(r_is)
            r_is[e.name] = metrics(run_portfolio(ins, bars, e))
            r_oos = run_all(oos, bars, VARIANTS)
            r_oos[e.name] = metrics(run_portfolio(oos, bars, e))
            report["seeds"][seed] = {"in_sample": r_is, "out_of_sample": r_oos, "combo": e.name}
            print(f"seed {seed}: combo={e.name}", file=sys.stderr)
    else:
        export = json.loads(Path(a.export).read_text())
        entries, actual = brain_entries(export)
        bars = load_bars(Path(a.bars), sorted({e.symbol for e in entries}))
        fid = fidelity(entries, actual, bars)
        split = [e for e in entries if e.t < a.split_ms], [e for e in entries if e.t >= a.split_ms]
        r_is = run_all(split[0], bars, VARIANTS, BRAIN_COSTS) if split[0] else {}
        e = combo(r_is) if r_is else None
        r_oos = run_all(split[1], bars, VARIANTS, BRAIN_COSTS) if split[1] else {}
        if e and split[1]:
            r_oos[e.name] = metrics(run_portfolio(split[1], bars, e, BRAIN_COSTS))
        report = {"mode": "brain", "fidelity": fid,
                  "fidelity_reason_match": sum(f["reason_real"] == f["reason_replay"] for f in fid) / len(fid)
                  if fid else None,
                  "late_exits": sum(1 for f in fid if (f.get("close_delay_min") or 0) > 0),
                  "all": run_all(entries, bars, VARIANTS, BRAIN_COSTS), "in_sample": r_is, "out_of_sample": r_oos,
                  "combo": None if e is None else e.name}
    Path(a.out).write_text(json.dumps(report, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
