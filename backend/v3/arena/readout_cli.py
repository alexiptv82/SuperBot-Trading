"""Readout in sola lettura delle tre run Arena (ripiego da Termius, senza web ne' app).

    python3 -s -m backend.v3.arena.readout_cli --day 2026-11-18 [--root /opt/superbot-ai-arena-paper] [--json]

Usa lo stesso lettore verificato della dashboard (catena hash del journal, provenienza, PnL riconciliato).
Non scrive nulla, non apre il journal in scrittura, non usa rete, non chiama modelli.
Le posizioni aperte non hanno PnL non realizzato: il lettore non ha una quotazione verificata e non la inventa.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
import time

from backend.v3.arena.read_view import read_arena
from backend.v3.arena.trial_plan import build_trial_plan

ROOT = Path("/opt/superbot-ai-arena-paper")


def _ts(ms) -> str:
    return "n.d." if type(ms) is not int else datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%d/%m %H:%M:%S UTC")


def _side(value) -> str:
    return {1: "LONG", -1: "SHORT"}.get(value, "?")


def render(view: dict) -> str:
    rows = [f"ARENA READOUT (sola lettura) generato {_ts(view['generated_at_ms'])}"]
    for name in ("deepseek", "qwen", "minimax"):
        w = view["portfolios"][name]
        rows.append("")
        rows.append(f"== {name}  modello={w['model']}  stato={w['state']}  dati={w['data_status']}")
        if w["data_status"] != "VERIFIED":
            rows.append("   nessun numero mostrato: journal non verificato o gara non avviata")
            continue
        rows.append(f"   T0 {_ts(w['trial_start_ms'])}  ultimo aggiornamento {_ts(w['updated_ms'])}")
        rows.append(f"   capitale iniziale {w['initial_capital']}  PnL realizzato {w['realized_pnl']}  "
                    f"PnL oggi {w['day_pnl']}  equity {w['equity'] if w['equity'] is not None else 'n.d. (posizioni aperte non valutate)'}")
        rows.append(f"   chiuse {w['total_closed']}  win rate {('%.1f%%' % float(w['win_rate'])) if w['win_rate'] else 'n.d.'}  "
                    f"margine impegnato {w['margin_in_use']}  decisioni {w['decision_count']} (no-trade {w['no_trade_count']})")
        rows.append(f"   APERTE: {w['open_count']}  (PnL non realizzato: n.d., nessuna quotazione verificata)")
        for p in w["open_positions"] or []:
            rows.append(f"     {p['symbol']:<12} {_side(p['side']):<5} x{p['leverage']:<3} entry {p['entry']}  stop {p['stop']}  "
                        f"margine {p['margin']}  aperta {_ts(p['opened_at_ms'])}")
        rows.append(f"   CHIUSE (ultime {min(10, len(w['closed_trades'] or []))}):")
        for t in (w["closed_trades"] or [])[:10]:
            rows.append(f"     {t['symbol']:<12} {_side(t['side']):<5} x{t['leverage']:<3} PnL {t['realized_pnl']:>12}  "
                        f"{t['exit_reason']:<14} chiusa {_ts(t['closed_at_ms'])}")
    return "\n".join(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True, help="giorno della gara, AAAA-MM-GG")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--now-ms", type=int, default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        plans = build_trial_plan(date.fromisoformat(args.day), root=Path(args.root))
        view = read_arena(plans, args.now_ms if args.now_ms is not None else int(time.time() * 1000))
    except (ValueError, OSError) as exc:
        print("ARENA_READOUT RESULT=FAILED_" + type(exc).__name__)
        return 2
    print(json.dumps(view, indent=1, sort_keys=True) if args.json else render(view))
    return 0


if __name__ == "__main__":
    sys.exit(main())
