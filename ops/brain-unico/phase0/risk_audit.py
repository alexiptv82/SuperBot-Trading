"""Verifica dei limiti di rischio PAPER su un journal V3 (di una COPIA o in sola lettura): solo numeri.

Risponde a: "i limiti di rischio hanno retto?" per una run (es. MiniMax) leggendo `paper_open`, `paper_close` e
`brain_decision` del journal e confrontandoli con la politica dichiarata nella configurazione della gara.

Cosa controlla (tutto in sola lettura, nessun contenuto di testo viene esportato: solo conteggi, rapporti, codici):
- tetto di perdita per posizione: rischio allo stop (distanza dallo stop x quantita' + costi stimati) / capitale
  e / margine, contro `max_loss_fraction` e `max_loss_margin_fraction`;
- rischio aperto aggregato, margine per posizione e totale, leva, soglia minima di capitale;
- perdita realizzata contro il tetto per posizione (gap e slippage possono superare la stima: e' dichiarato);
- freno giornaliero (avviso 35 %, blocco 50 %) in versione LIMITE INFERIORE (solo realizzato: il non realizzato non e'
  nel journal): se si apre dopo che il solo realizzato ha gia' superato il blocco, e' una prova di violazione;
- coerenza del registro: aperture senza chiusura (posizioni aperte), chiusure senza apertura (orfane), doppie
  chiusure, durata oltre il massimo della politica di uscita, motivi di uscita, chiusure manuali.

LIMITE DICHIARATO: il capitale usato dal sistema comprende il non realizzato, che il journal non registra. Qui il
capitale e' "iniziale + realizzato": i rapporti sono INDICATIVI (per questo si riportano sia >1,0 sia >1,1 del tetto).
Una violazione certa richiede un rapporto molto sopra 1 o un'apertura dopo il blocco provato dal solo realizzato.
"""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Optional
from urllib.parse import quote

DAY_MS = 86_400_000
HOUR_MS = 3_600_000
Q = Decimal("0.0001")


def _d(v: Any, default: str = "0") -> Decimal:
    try:
        out = Decimal(str(v))
        return out if out.is_finite() else Decimal(default)
    except Exception:
        return Decimal(default)


def _s(x: Decimal) -> str:
    return str(x.quantize(Q, rounding=ROUND_HALF_EVEN))


def read_events(db_path: str) -> list:
    con = sqlite3.connect("file:" + quote(db_path, safe="/") + "?mode=ro", uri=True, timeout=2)
    try:
        con.execute("PRAGMA query_only=1")
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='v3_events'").fetchone():
            return []
        rows = []
        for seq, kind, ts, payload in con.execute(
                "SELECT seq,kind,occurred_at_ms,payload_json FROM v3_events ORDER BY seq"):
            try:
                p = json.loads(payload)
            except ValueError:
                p = {}
            rows.append((seq, kind, ts, p if isinstance(p, dict) else {}))
        return rows
    finally:
        con.close()


def analyze(events: list, policy: dict, exit_max_hold_hours: int = 24) -> dict:
    rp = policy["risk_policy"]
    init = _d(policy["initial_equity"])
    cap = _d(rp["max_loss_fraction"])
    cap_margin = _d(rp.get("max_loss_margin_fraction", "1"))
    open_cap, pos_margin_cap, tot_margin_cap = (_d(rp["max_open_risk_fraction"]), _d(rp["max_position_margin_fraction"]),
                                                _d(rp["max_total_margin_fraction"]))
    floor, cost_bp = _d(rp["minimum_equity"]), _d(rp["estimated_roundtrip_cost_bp"])
    lev_min, lev_max = int(rp.get("min_leverage", 1)), int(rp.get("max_leverage", 125))
    warn, halt = _d(policy["daily_loss_warn_fraction"]), _d(policy["daily_loss_halt_fraction"])

    equity = init
    min_equity, peak, max_dd = init, init, Decimal(0)
    open_pos: dict[str, dict] = {}
    seen_closed: set = set()
    cnt = dict(opens=0, closes=0, wins=0, orphan_closes=0, duplicate_closes=0, manual_closes=0, loss_exceeds_margin=0,
               held_over_max=0, leverage_out_of_range=0, open_below_floor=0, open_risk_over=0, position_margin_over=0,
               total_margin_over=0, risk_over_cap=0, risk_over_cap_10pct=0, risk_over_margin_cap=0,
               realized_loss_over_cap=0, realized_loss_over_cap_150pct=0, opens_after_daily_halt_proof=0)
    mx = dict(risk_ratio=Decimal(0), risk_margin_ratio=Decimal(0), open_risk_ratio=Decimal(0),
              total_margin_ratio=Decimal(0), position_margin_ratio=Decimal(0), realized_loss_ratio=Decimal(0),
              daily_loss_fraction=Decimal(0))
    reasons: dict[str, int] = {}
    decisions: dict[str, int] = {}
    realized_total, fees_total = Decimal(0), Decimal(0)
    day, day_start_capital, day_realized, day_halt_at = None, init, Decimal(0), None
    days_warn, days_halt = set(), set()
    first_ts = last_ts = None
    equity_at_open: dict[str, Decimal] = {}
    max_hold_ms = exit_max_hold_hours * HOUR_MS

    for _seq, kind, ts, p in events:
        first_ts = ts if first_ts is None else min(first_ts, ts)
        last_ts = ts if last_ts is None else max(last_ts, ts)
        d = ts // DAY_MS
        if day != d:
            day, day_start_capital, day_realized, day_halt_at = d, equity, Decimal(0), None
        if kind == "brain_decision":
            key = f"{p.get('kind', '?')}:{p.get('status', '?')}"
            decisions[key] = decisions.get(key, 0) + 1
        elif kind == "paper_open":
            pid = str(p.get("position_id", ""))
            fill, stop, qty = _d(p.get("fill_price")), _d(p.get("stop_price")), _d(p.get("quantity"))
            notional, margin, lev = _d(p.get("notional")), _d(p.get("margin_used")), int(_d(p.get("leverage")))
            cnt["opens"] += 1
            risk = abs(fill - stop) * qty + notional * cost_bp / Decimal(10000)
            eq = equity if equity > 0 else Decimal("0.0001")
            r_cap = risk / eq / cap if cap else Decimal(0)
            r_mar = (risk / margin / cap_margin) if margin > 0 and cap_margin else Decimal(0)
            mx["risk_ratio"], mx["risk_margin_ratio"] = max(mx["risk_ratio"], r_cap), max(mx["risk_margin_ratio"], r_mar)
            cnt["risk_over_cap"] += r_cap > 1
            cnt["risk_over_cap_10pct"] += r_cap > Decimal("1.1")
            cnt["risk_over_margin_cap"] += r_mar > Decimal("1.0001")
            open_pos[pid] = {"risk": risk, "margin": margin, "ts": ts}
            equity_at_open[pid] = equity
            tot_risk = sum((o["risk"] for o in open_pos.values()), Decimal(0))
            tot_margin = sum((o["margin"] for o in open_pos.values()), Decimal(0))
            mx["open_risk_ratio"] = max(mx["open_risk_ratio"], tot_risk / eq / open_cap if open_cap else Decimal(0))
            mx["total_margin_ratio"] = max(mx["total_margin_ratio"], tot_margin / eq / tot_margin_cap)
            mx["position_margin_ratio"] = max(mx["position_margin_ratio"], margin / eq / pos_margin_cap)
            cnt["open_risk_over"] += tot_risk / eq > open_cap
            cnt["total_margin_over"] += tot_margin / eq > tot_margin_cap
            cnt["position_margin_over"] += margin / eq > pos_margin_cap
            cnt["leverage_out_of_range"] += not (lev_min <= lev <= lev_max)
            cnt["open_below_floor"] += equity <= floor
            if day_halt_at is not None:
                cnt["opens_after_daily_halt_proof"] += 1
        elif kind == "paper_close":
            pid = str(p.get("position_id", ""))
            realized, fees = _d(p.get("realized_pnl")), _d(p.get("fees"))
            if pid in seen_closed:
                cnt["duplicate_closes"] += 1
                continue
            seen_closed.add(pid)
            cnt["closes"] += 1
            if pid not in open_pos:
                cnt["orphan_closes"] += 1
            eq_open = equity_at_open.get(pid, equity)
            open_pos.pop(pid, None)
            equity += realized
            realized_total += realized
            fees_total += fees
            cnt["wins"] += realized > 0
            reason = str(p.get("reason", "?"))
            reasons[reason] = reasons.get(reason, 0) + 1
            cnt["manual_closes"] += reason == "manual"
            cnt["loss_exceeds_margin"] += bool(p.get("loss_exceeds_margin"))
            cnt["held_over_max"] += _d(p.get("held_ms")) > max_hold_ms + HOUR_MS
            if realized < 0 and eq_open > 0 and cap:
                ratio = (-realized) / eq_open / cap
                mx["realized_loss_ratio"] = max(mx["realized_loss_ratio"], ratio)
                cnt["realized_loss_over_cap"] += ratio > 1
                cnt["realized_loss_over_cap_150pct"] += ratio > Decimal("1.5")
            min_equity, peak = min(min_equity, equity), max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak)
            day_realized += realized
            frac = (-day_realized / day_start_capital) if day_realized < 0 and day_start_capital > 0 else Decimal(0)
            mx["daily_loss_fraction"] = max(mx["daily_loss_fraction"], frac)
            if frac >= warn:
                days_warn.add(day)
            if frac >= halt:
                days_halt.add(day)
                day_halt_at = day_halt_at or ts

    still_open = len(open_pos)
    oldest = max(((last_ts - o["ts"]) for o in open_pos.values()), default=0) if last_ts else 0
    return {
        "schema": 1, "classification": "NUMBERS_ONLY", "approximation": "equity=initial+realized (unrealized not in journal)",
        "window": {"first_event_ms": first_ts, "last_event_ms": last_ts,
                   "hours": _s(Decimal((last_ts or 0) - (first_ts or 0)) / Decimal(HOUR_MS)) if first_ts else "0"},
        "trades": {"opened": cnt["opens"], "closed": cnt["closes"], "still_open": still_open,
                   "wins": cnt["wins"], "losses": cnt["closes"] - cnt["wins"], "realized_pnl": _s(realized_total),
                   "fees": _s(fees_total), "exit_reasons": dict(sorted(reasons.items())),
                   "oldest_open_age_hours": _s(Decimal(oldest) / Decimal(HOUR_MS))},
        "equity_realized_only": {"initial": _s(init), "now": _s(equity), "min": _s(min_equity),
                                 "max_drawdown_fraction": _s(max_dd), "floor": _s(floor)},
        "ratios_vs_limit": {k: _s(v) for k, v in mx.items()},
        "violations_or_flags": {k: cnt[k] for k in (
            "risk_over_cap", "risk_over_cap_10pct", "risk_over_margin_cap", "open_risk_over", "total_margin_over",
            "position_margin_over", "leverage_out_of_range", "open_below_floor", "realized_loss_over_cap",
            "realized_loss_over_cap_150pct", "loss_exceeds_margin", "held_over_max", "orphan_closes",
            "duplicate_closes", "manual_closes", "opens_after_daily_halt_proof")},
        "daily_guard_lower_bound": {"days_at_or_over_warn": len(days_warn), "days_at_or_over_halt": len(days_halt),
                                    "max_daily_loss_fraction": _s(mx["daily_loss_fraction"]),
                                    "warn": _s(warn), "halt": _s(halt)},
        "decisions": dict(sorted(decisions.items())),
        "verdict": _verdict(cnt, mx),
    }


def _verdict(cnt: dict, mx: dict) -> dict:
    hard = []
    if cnt["opens_after_daily_halt_proof"]:
        hard.append("opens_after_daily_halt_proven_by_realized_only")
    if cnt["leverage_out_of_range"]:
        hard.append("leverage_out_of_policy_range")
    if cnt["open_below_floor"]:
        hard.append("open_at_or_below_minimum_equity")
    if cnt["risk_over_cap_10pct"] or cnt["risk_over_margin_cap"]:
        hard.append("per_position_risk_clearly_over_cap")
    if cnt["open_risk_over"] or cnt["total_margin_over"] or cnt["position_margin_over"]:
        hard.append("aggregate_risk_or_margin_over_limit_indicative")
    if cnt["orphan_closes"] or cnt["duplicate_closes"]:
        hard.append("journal_consistency_problem")
    soft = []
    if cnt["realized_loss_over_cap"]:
        soft.append("realized_loss_over_cap_gap_or_slippage")
    if cnt["held_over_max"]:
        soft.append("positions_held_over_policy_max_hold")
    return {"limits_held": not hard, "hard_flags": hard, "soft_flags": soft}


def analyze_db(db_path: str, policy: dict, exit_max_hold_hours: int = 24) -> dict:
    return analyze(read_events(db_path), policy, exit_max_hold_hours)


def open_positions_status(db_path: str) -> dict:
    """Stato leggero di un journal: posizioni aperte, orfane, ultimo evento. Solo numeri."""
    opened, closed, orphan, last = set(), set(), 0, None
    for _seq, kind, ts, p in read_events(db_path):
        last = ts if last is None else max(last, ts)
        pid = str(p.get("position_id", ""))
        if kind == "paper_open":
            opened.add(pid)
        elif kind == "paper_close":
            if pid not in opened:
                orphan += 1
            closed.add(pid)
    return {"opened": len(opened), "closed": len(closed & opened), "open_now": len(opened - closed),
            "orphan_closes": orphan, "last_event_ms": last}


if __name__ == "__main__":
    import sys
    with open(sys.argv[2]) as fh:
        cfg = json.load(fh)
    print(json.dumps(analyze_db(sys.argv[1], cfg), indent=1, sort_keys=True))
