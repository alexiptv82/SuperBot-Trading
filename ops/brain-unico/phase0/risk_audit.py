"""Verifica dei limiti di rischio PAPER su un journal V3 (di una COPIA o in sola lettura): solo numeri.

Risponde a una domanda stretta: "il journal contiene la PROVA di una violazione dei limiti?". NON risponde a "tutti i
limiti sono stati rispettati": per questo il verdetto distingue `no_breach_proven` (nessuna violazione provata dai dati
disponibili) da `fully_checked` (che qui e' SEMPRE falso: il journal non contiene il non realizzato, la storia dei blocchi
del freno giornaliero ne' la politica effettivamente caricata dalla run).

Cosa controlla (sola lettura, nessun testo esportato: solo conteggi, rapporti, codici):
- tetto di perdita per posizione (rischio allo stop = distanza x quantita' + costi stimati) su capitale e su margine;
- rischio aperto aggregato, margine per posizione e totale, leva, soglia minima di capitale;
- perdita realizzata contro il tetto (gap e slippage possono superare la stima: dichiarato);
- freno giornaliero UTC (avviso 35 %, blocco 50 %) come LIMITE INFERIORE (solo realizzato), con ripartizione per giorno;
- coerenza: aperture senza chiusura, chiusure orfane o doppie, durata oltre il massimo, motivi di uscita, manuali;
- DATI MANCANTI: un evento senza i campi numerici necessari NON vale zero: e' contato in `data_gaps` e rende falso
  `no_breach_proven`.

Politica: e' la copia incorporata nel bundle (config pubbliche dell'Arena); `policy.verified_against_run` e' falso perche'
il journal non la riporta. Un −40 % aggregato in pochi giorni resta strategicamente inadatto a un futuro profilo LIVE
anche se compatibile con questa politica permissiva.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Optional
from urllib.parse import quote

DAY_MS = 86_400_000
HOUR_MS = 3_600_000
Q = Decimal("0.0001")
OPEN_FIELDS = ("fill_price", "stop_price", "quantity", "notional", "margin_used", "leverage")
NOT_CHECKABLE = ("unrealized_equity", "daily_guard_exact_with_unrealized", "guard_block_history", "policy_effectively_loaded_by_run")


def _d(v: Any, default: str = "0") -> Decimal:
    try:
        out = Decimal(str(v))
        return out if out.is_finite() else Decimal(default)
    except Exception:
        return Decimal(default)


def _has(p: dict, key: str) -> bool:
    try:
        return key in p and p[key] is not None and Decimal(str(p[key])).is_finite()
    except Exception:
        return False


def _s(x: Decimal) -> str:
    return str(x.quantize(Q, rounding=ROUND_HALF_EVEN))


def policy_hash(policy: dict) -> str:
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


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


def analyze(events: list, policy: dict, exit_max_hold_hours: int = 24, now_ms: Optional[int] = None) -> dict:
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
    gaps = {"opens_incomplete": 0, "closes_incomplete": 0, "events_unparsable": 0}
    mx = dict(risk_ratio=Decimal(0), risk_margin_ratio=Decimal(0), open_risk_ratio=Decimal(0),
              total_margin_ratio=Decimal(0), position_margin_ratio=Decimal(0), realized_loss_ratio=Decimal(0),
              daily_loss_fraction=Decimal(0))
    reasons: dict[str, int] = {}
    decisions: dict[str, int] = {}
    realized_total, fees_total = Decimal(0), Decimal(0)
    day, day_start_capital, day_realized, day_halt_at = None, init, Decimal(0), None
    days_warn, days_halt = set(), set()
    daily: dict[int, dict] = {}
    first_ts = last_ts = None
    equity_at_open: dict[str, Decimal] = {}
    max_hold_ms = exit_max_hold_hours * HOUR_MS

    for _seq, kind, ts, p in events:
        first_ts = ts if first_ts is None else min(first_ts, ts)
        last_ts = ts if last_ts is None else max(last_ts, ts)
        d = ts // DAY_MS
        if day != d:
            day, day_start_capital, day_realized, day_halt_at = d, equity, Decimal(0), None
            daily.setdefault(d, {"start": day_start_capital, "realized": Decimal(0), "opens": 0, "opens_after_halt": 0})
        if kind in ("paper_open", "paper_close") and not p:
            gaps["events_unparsable"] += 1
        if kind == "brain_decision":
            key = f"{p.get('kind', '?')}:{p.get('status', '?')}"
            decisions[key] = decisions.get(key, 0) + 1
        elif kind == "paper_open":
            pid = str(p.get("position_id", ""))
            cnt["opens"] += 1
            daily[d]["opens"] += 1
            if not all(_has(p, k) for k in OPEN_FIELDS):
                gaps["opens_incomplete"] += 1                    # dato mancante: NON si inventa ne' si tratta come zero
                open_pos[pid] = {"risk": Decimal(0), "margin": Decimal(0), "ts": ts}
                equity_at_open[pid] = equity
                continue
            fill, stop, qty = _d(p["fill_price"]), _d(p["stop_price"]), _d(p["quantity"])
            notional, margin, lev = _d(p["notional"]), _d(p["margin_used"]), int(_d(p["leverage"]))
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
                daily[d]["opens_after_halt"] += 1
        elif kind == "paper_close":
            pid = str(p.get("position_id", ""))
            if pid in seen_closed:
                cnt["duplicate_closes"] += 1
                continue
            seen_closed.add(pid)
            cnt["closes"] += 1
            if pid not in open_pos:
                cnt["orphan_closes"] += 1
            eq_open = equity_at_open.get(pid, equity)
            open_pos.pop(pid, None)
            reason = str(p.get("reason", "?"))
            reasons[reason] = reasons.get(reason, 0) + 1
            cnt["manual_closes"] += reason == "manual"
            if not _has(p, "realized_pnl"):
                gaps["closes_incomplete"] += 1                   # PnL mancante: l'equity non si aggiorna con uno zero inventato
                continue
            realized, fees = _d(p["realized_pnl"]), _d(p.get("fees"))
            equity += realized
            realized_total += realized
            fees_total += fees
            cnt["wins"] += realized > 0
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
            daily[d]["realized"] += realized
            frac = (-day_realized / day_start_capital) if day_realized < 0 and day_start_capital > 0 else Decimal(0)
            mx["daily_loss_fraction"] = max(mx["daily_loss_fraction"], frac)
            if frac >= warn:
                days_warn.add(day)
            if frac >= halt:
                days_halt.add(day)
                day_halt_at = day_halt_at or ts

    ref = now_ms if now_ms is not None else last_ts          # l'eta' delle posizioni aperte si misura da ADESSO, non dall'ultimo evento
    ages = [(ref - o["ts"]) for o in open_pos.values()] if ref else []
    overdue = sum(1 for a in ages if a > max_hold_ms + HOUR_MS)
    day_rows = []
    for dd in sorted(daily):
        v = daily[dd]
        loss = max(Decimal(0), -v["realized"])
        day_rows.append({"day": time.strftime("%Y-%m-%d", time.gmtime(dd * DAY_MS / 1000)),
                         "start_capital": _s(v["start"]), "realized": _s(v["realized"]),
                         "realized_loss_fraction": _s(loss / v["start"]) if v["start"] > 0 else "0.0000",
                         "opens": v["opens"], "opens_after_halt_proof": v["opens_after_halt"]})
    return {
        "schema": 2, "classification": "NUMBERS_ONLY",
        "policy": {"hash": policy_hash(policy), "source": "embedded_copy_of_public_arena_config", "verified_against_run": False},
        "approximation": "equity=initial+realized (unrealized not in journal)",
        "window": {"first_event_ms": first_ts, "last_event_ms": last_ts,
                   "hours": _s(Decimal((last_ts or 0) - (first_ts or 0)) / Decimal(HOUR_MS)) if first_ts else "0"},
        "trades": {"opened": cnt["opens"], "closed": cnt["closes"], "still_open": len(open_pos),
                   "wins": cnt["wins"], "losses": cnt["closes"] - cnt["wins"], "realized_pnl": _s(realized_total),
                   "fees": _s(fees_total), "exit_reasons": dict(sorted(reasons.items())),
                   "oldest_open_age_hours": _s(Decimal(max(ages, default=0)) / Decimal(HOUR_MS)),
                   "open_overdue": overdue, "open_age_reference": "now" if now_ms is not None else "last_event"},
        "equity_realized_only": {"initial": _s(init), "now": _s(equity), "min": _s(min_equity),
                                 "max_drawdown_fraction": _s(max_dd), "floor": _s(floor)},
        "ratios_vs_limit": {k: _s(v) for k, v in mx.items()},
        "violations_or_flags": {k: cnt[k] for k in (
            "risk_over_cap", "risk_over_cap_10pct", "risk_over_margin_cap", "open_risk_over", "total_margin_over",
            "position_margin_over", "leverage_out_of_range", "open_below_floor", "realized_loss_over_cap",
            "realized_loss_over_cap_150pct", "loss_exceeds_margin", "held_over_max", "orphan_closes",
            "duplicate_closes", "manual_closes", "opens_after_daily_halt_proof")},
        "data_gaps": gaps,
        "daily_guard_lower_bound": {"days_at_or_over_warn": len(days_warn), "days_at_or_over_halt": len(days_halt),
                                    "max_daily_loss_fraction": _s(mx["daily_loss_fraction"]),
                                    "warn": _s(warn), "halt": _s(halt), "by_day_utc": day_rows},
        "decisions": dict(sorted(decisions.items())),
        "verdict": _verdict(cnt, gaps, overdue),
    }


def _verdict(cnt: dict, gaps: dict, overdue: int) -> dict:
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
    if overdue:
        soft.append("open_positions_overdue_for_exit")           # l'exit service non sta chiudendo: serve attenzione, non timeout
    if any(gaps.values()):
        soft.append("data_gaps_present")
    return {"no_breach_proven": not hard and not any(gaps.values()), "fully_checked": False,
            "not_checkable": list(NOT_CHECKABLE), "hard_flags": hard, "soft_flags": soft}


def analyze_db(db_path: str, policy: dict, exit_max_hold_hours: int = 24, now_ms: Optional[int] = None) -> dict:
    return analyze(read_events(db_path), policy, exit_max_hold_hours, now_ms)


def open_positions_status(db_path: str) -> dict:
    """Stato leggero di un journal (da usare su COPIE): posizioni aperte, orfane, ultimo evento. Solo numeri."""
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
