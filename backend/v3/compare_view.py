"""Confronto PAPER fra run V3 indipendenti (Falco Evoluto, Brain Scalp): SOLA LETTURA, nessun file creato.

Le run arrivano da ``V3_COMPARE_RUNS`` (JSON, al massimo 4): ``[{"name": "falco_evoluto", "label": "Falco Evoluto",
"dir": "/opt/superbot-v3-paper-runs/<cartella>", "run_id": "<run>"}]``. Senza variabile o con un valore non valido:
``available: false`` (mai numeri inventati). Ogni run si legge dal SUO journal, dalla SUA configurazione e dal SUO
registro di spesa: nessun dato condiviso fra portafogli.

Metriche (tutte dal journal):
* equity contabilizzata = capitale + PnL realizzato (commissioni incluse); rendimento % sul capitale iniziale;
* drawdown massimo sulla curva contabilizzata (chiusura per chiusura): NON include le oscillazioni delle posizioni
  aperte, che si vedono nel Guardian (equity MTM, picco e giveback di sessione);
* profit factor = somma dei profitti / somma delle perdite (None senza perdite); win rate su vinti+persi;
* LONG/SHORT separati; chiusure manuali e stop protettivi (``stop_kind``) contati a parte.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Optional

from backend.v3.dashboard import build_summary, open_groups
from backend.v3.events import EventJournal

ENV = "V3_COMPARE_RUNS"
PORTFOLIO_ID = "brain"
_NAME = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_RUN = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
_LABEL = re.compile(r"^[A-Za-z0-9 ]{1,32}$")
_CODE = re.compile(r"^[a-z][a-z0-9_:]{0,63}$")
_MICRO = Decimal(1_000_000)


@dataclass(frozen=True)
class RunRef:
    name: str
    label: str
    dir: Path
    run_id: str


def runs_from_env(env: Mapping[str, str]) -> Optional[list[RunRef]]:
    raw = env.get(ENV)
    if not raw:
        return None
    try:
        items = json.loads(raw)
        if type(items) is not list or not 1 <= len(items) <= 4:
            return None
        out = []
        for it in items:
            if (type(it) is not dict or set(it) != {"name", "label", "dir", "run_id"}
                    or not all(type(it[k]) is str for k in it) or not _NAME.match(it["name"])
                    or not _LABEL.match(it["label"]) or not _RUN.match(it["run_id"])
                    or not it["dir"].startswith("/") or ".." in it["dir"]):
                return None
            out.append(RunRef(it["name"], it["label"], Path(it["dir"]), it["run_id"]))
        if len({r.name for r in out}) != len(out) or len({str(r.dir) for r in out}) != len(out):
            return None
        return out
    except (ValueError, TypeError):
        return None


def _d(v) -> Optional[Decimal]:
    try:
        d = Decimal(str(v))
        return d if d.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _s(v) -> Optional[str]:
    return None if v is None else str(v)


def _spend(path: Path, immutable: bool = False) -> dict:
    """Spesa AI della run (micro-dollari nel registro) letta in sola lettura: oggi (UTC) e totale.

    ``immutable``: solo per run ARCHIVIATE (nessun processo le scrive piu'): il registro e' in WAL e, su un mount in sola
    lettura senza ``-shm``, ``mode=ro`` non si apre; ``immutable=1`` lo legge senza creare o toccare file."""
    if not path.is_file():
        return {"day": None, "total": None}
    try:
        uri = path.resolve().as_uri().replace("file://", "file:") + ("?immutable=1" if immutable else "?mode=ro")
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute("SELECT occurred_at, units, provider FROM spend_events").fetchall()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day = sum(u for t, u, _p in rows if type(u) is int and str(t).startswith(today))
        total = sum(u for _, u, _p in rows if type(u) is int)
        by = {}
        for prov in sorted({p for _t, _u, p in rows if p in ("deepseek", "claude")}):   # costi separati per AI
            by[prov] = {"day": str(Decimal(sum(u for t, u, p in rows if p == prov and type(u) is int
                                                and str(t).startswith(today))) / _MICRO),
                        "total": str(Decimal(sum(u for _t, u, p in rows if p == prov and type(u) is int)) / _MICRO)}
        return {"day": str(Decimal(day) / _MICRO), "total": str(Decimal(total) / _MICRO), "by_provider": by}
    except (sqlite3.Error, OSError, ValueError):
        return {"day": None, "total": None}


def _config(path: Path) -> Optional[dict]:
    try:
        from backend.v3.runner.config import load_runner_config
        c = load_runner_config(path.read_bytes())
    except (OSError, ValueError):
        return None
    p = c.risk_policy
    return {"initial_equity": c.initial_equity, "analyst": c.analyst, "cycle_minutes": c.cycle_minutes,
            "daily_cap_usd": str(c.daily_cap_usd), "leverage": [p.min_leverage, p.max_leverage],
            "margin": [_s(p.min_margin), _s(p.max_margin)], "max_positions": p.max_positions,
            "risk_per_trade_pct": str(p.max_loss_fraction * 100), "open_risk_pct": str(p.max_open_risk_fraction * 100),
            "daily_stop_pct": str(c.daily_loss_halt * 100), "guardian": c.guardian is not None,
            "take_profit_r": None if c.exit_policy is None else str(c.exit_policy.take_profit_r),
            "symbols": len(c.symbols), "unico": _unico_config(c)}


def _unico_config(c) -> Optional[dict]:
    """Brain unico (schema 3): le regole in vigore, per la dashboard (None per le altre run)."""
    u = c.unico
    if u is None:
        return None
    t = u.tiers
    return {"leverage_fit": u.leverage_fit, "position_review": u.position_review,
            "partial": None if u.partial is None else {"fraction": str(u.partial.fraction), "at_r": str(u.partial.at_r)},
            "tiers": None if t is None else {"selective_usd": str(t.selective_usd), "protect_usd": str(t.protect_usd)},
            "piggy": None if u.piggy is None else {"reference_equity": str(u.piggy.reference_equity), "tz": u.piggy.tz,
                                                   "hour": u.piggy.hour},
            "max_hold_hours": (None if c.exit_policy is None or c.exit_policy.max_hold_ms is None
                               else c.exit_policy.max_hold_ms // 3_600_000),
            "claude": None if u.claude is None else {"model": u.claude.model, "daily_cap_usd": str(u.claude.daily_cap_usd)},
            "exit": None if c.exit_policy is None else {k: _s(getattr(c.exit_policy, k)) for k in (
                "take_profit_r", "be_at_r", "trail_at_r", "trail_dist_r")}}


def _side_bucket():
    return {"trades": 0, "wins": 0, "losses": 0, "net_pnl": Decimal("0")}


def read_run(ref: RunRef, now_ms: int, *, archived: bool = False) -> dict:
    base = {"name": ref.name, "label": ref.label, "run_id": ref.run_id}
    cfg = _config(ref.dir / "runner_config.json")
    jpath = ref.dir / "journal.db"
    if cfg is None or not jpath.is_file():
        return dict(base, available=False, reason="not_prepared" if cfg is None else "not_started")
    try:
        journal = EventJournal(str(jpath))
        events = journal.list_run(PORTFOLIO_ID, ref.run_id)
        summary = build_summary(journal, PORTFOLIO_ID, ref.run_id)
    except Exception:
        return dict(base, available=False, reason="journal_unreadable")
    start = cfg["initial_equity"]
    equity, peak, max_dd, max_dd_pct = start, start, Decimal("0"), Decimal("0")
    gross_win, gross_loss, wins, losses, manual, protected, fees = (Decimal("0"), Decimal("0"), 0, 0, 0, 0,
                                                                    Decimal("0"))
    sides = {"long": _side_bucket(), "short": _side_bucket()}
    guardian, decisions, reviews = None, [], []
    trades: dict = {}                    # apertura (gruppo di quote) -> [lato, P&L netto]: un trade = un'apertura
    mtm_samples: list[Decimal] = []      # equity a mercato registrate dal Guardian con prezzi verificati
    mtm_incomplete = False
    for r in events:
        ev, p = r.event, (r.event.payload if isinstance(r.event.payload, Mapping) else {})
        if ev.kind in ("paper_close", "paper_reduce"):          # chiusure parziali: P&L dello stesso trade
            pnl = _d(p.get("realized_pnl"))
            if pnl is None:
                continue
            equity += pnl
            peak = max(peak, equity)
            if peak - equity > max_dd:
                max_dd, max_dd_pct = peak - equity, (peak - equity) / peak * 100
            fees += _d(p.get("fees")) or Decimal("0")
            key = p.get("decision_event_id") or p.get("position_id")
            t = trades.setdefault(key, [p.get("side"), Decimal("0")])
            t[1] += pnl
            manual += p.get("reason") == "manual"
            protected += p.get("stop_kind") in ("break_even", "trailing", "protect")
        elif ev.kind == "guardian_state":
            mark = _d(p.get("equity"))
            if mark is None or any(x in (p.get("reasons") or []) for x in ("data_fault", "guardian_error")):
                mtm_incomplete = True                 # feed mancante: nessun valore stimato per quel giro
            else:
                mtm_samples.append(mark)
            guardian = {k: p.get(k) for k in ("state", "reasons", "equity", "session_start_equity", "peak_equity",
                                               "giveback", "floor", "budget", "risk_cap", "open_risk",
                                               "realized_session", "unrealized", "ai_cost_session", "as_of_ms")}
        elif ev.kind == "position_review":
            acts = ("NONE", "HOLD", "CLOSE", "PARTIAL_CLOSE", "MODIFY_STOP", "ADD")      # elenco chiuso
            reviews.append({"ts_ms": ev.occurred_at_ms, "symbol": p.get("symbol"),
                            "proposed": p.get("proposed") if p.get("proposed") in acts else None,
                            "executed": p.get("executed") if p.get("executed") in acts else None,
                            "code": p.get("code") if _CODE.match(str(p.get("code", ""))) else None,
                            "source": p.get("source") if p.get("source") in ("deepseek", "claude", "agreed", "none")
                            else None,
                            "claude": (p.get("claude") or {}).get("action") or (p.get("claude") or {}).get("verdict")
                            if (p.get("claude") or {}).get("status") == "ok" else
                            ("non disponibile" if p.get("claude") else None)})
        elif ev.kind == "brain_decision":
            decisions.append({"ts_ms": ev.occurred_at_ms, "symbol": p.get("symbol"), "kind": p.get("kind"),
                              "status": p.get("status"),
                              "rationale": p.get("rationale") if _CODE.match(str(p.get("rationale", ""))) else None,
                              "risk_reason": p.get("risk_reason") if _CODE.match(str(p.get("risk_reason", "")))
                              else None,
                              "sources": [s for s in (p.get("sources") or []) if isinstance(s, str) and _CODE.match(s)]})
    for side, pnl in trades.values():          # statistiche per TRADE (le quote di un'apertura contano una volta)
        b = sides["long" if side == 1 else "short"]
        b["trades"] += 1
        b["net_pnl"] += pnl
        if pnl > 0:
            wins, gross_win, b["wins"] = wins + 1, gross_win + pnl, b["wins"] + 1
        elif pnl < 0:
            losses, gross_loss, b["losses"] = losses + 1, gross_loss - pnl, b["losses"] + 1
    realized = equity - start                 # P&L di TRADING: realizzato, commissioni incluse, nessun costo AI
    decided = wins + losses
    spend = _spend(ref.dir / "budget.db", immutable=archived)
    ai_total = _d(spend.get("total"))
    after_ai = None if ai_total is None else realized - ai_total     # costi AI sottratti UNA sola volta, qui
    mtm_dd = mtm_dd_pct = None
    if mtm_samples:
        top, mtm_dd, mtm_dd_pct = start, Decimal("0"), Decimal("0")
        for v in mtm_samples:
            top = max(top, v)
            if top - v > mtm_dd:
                mtm_dd, mtm_dd_pct = top - v, (top - v) / top * 100
    for b in sides.values():
        b["net_pnl"] = str(b["net_pnl"])
    moved: dict = {}                            # ultimo stop stretto dall'AI per posizione (solo verso il profitto)
    for r in events:
        if r.event.kind == "stop_move" and isinstance(r.event.payload, Mapping):
            moved[r.event.payload.get("position_id")] = _d(r.event.payload.get("stop_price"))
    hb = None
    try:
        hb = json.loads((ref.dir / "heartbeat.json").read_text())
    except (OSError, ValueError):
        pass
    strategy = None
    if cfg.get("unico"):                         # Brain Live Evolution: versione attiva e cronologia (sola lettura)
        try:
            from backend.v3.strategy_versions import strategy_view
            sv = strategy_view(journal, ref.run_id, (ref.dir / "runner_config.json").read_bytes())
            strategy = {"active": sv["active"], "history": sv["history"][-5:]}
        except Exception:
            strategy = None
    return dict(base, available=True, strategy=strategy,
                config={k: (str(v) if isinstance(v, Decimal) else v) for k, v in cfg.items()},
                state=hb.get("state") if isinstance(hb, dict) and hb.get("state") in ("running", "paused", "halted")
                else None,
                paused=(ref.dir / "pause.flag").exists(),
                initial_equity=str(start), settled_equity=str(equity), net_pnl=str(realized),
                return_pct=str((realized / start * 100).quantize(Decimal("0.01"))),
                ai_cost_total=_s(ai_total), net_after_ai=_s(after_ai),
                return_after_ai_pct=None if after_ai is None else str((after_ai / start * 100).quantize(Decimal("0.01"))),
                # drawdown sui trade CHIUSI (curva contabilizzata) ...
                max_drawdown=str(max_dd), max_drawdown_pct=str(max_dd_pct.quantize(Decimal("0.01"))),
                # ... e drawdown dell'equity A MERCATO, solo dai campioni del Guardian (None senza campioni)
                mtm_drawdown=_s(mtm_dd),
                mtm_drawdown_pct=None if mtm_dd_pct is None else str(mtm_dd_pct.quantize(Decimal("0.01"))),
                mtm_samples=len(mtm_samples), mtm_incomplete=mtm_incomplete,
                profit_factor=None if gross_loss == 0 else str((gross_win / gross_loss).quantize(Decimal("0.01"))),
                wins=wins, losses=losses, closed=len(trades), closes=len(summary.closed_trades),
                win_rate=None if not decided else str((Decimal(wins) * 100 / decided).quantize(Decimal("0.1"))),
                fees=str(fees), by_side=sides, manual_closes=manual, protected_stops=protected,
                open_positions=[{"position_id": o.position_id, "symbol": o.symbol, "side": o.side,
                                 "entry": str(o.fill_price), "stop": str(o.stop_price), "margin": str(o.margin_used),
                                 "leverage": o.leverage, "opened_at_ms": o.opened_at_ms,
                                 "leg": o.leg, "group": o.group, "stop_brain": _s(moved.get(o.position_id)),
                                 "quantity": str(o.quantity), "adds": o.adds, "reduces": o.reduces,
                                 "strategy_version": o.strategy_version or None}
                                for o in summary.open_positions],
                open_trades=open_groups(summary.open_positions),
                guardian=guardian, decisions=decisions[-8:][::-1], reviews=reviews[-8:][::-1], ai_spend=spend,
                piggy=_piggy(cfg, summary, start, now_ms), collaboration=_collaboration(events),
                manual_close_allowed=_close_ready(ref, now_ms),
                close_pending=(ref.dir / "close_request.json").exists())


def _collaboration(events) -> Optional[dict]:
    """DeepSeek + Claude (Brain unico): quante volte Claude e' stato consultato, accordi, proposte di Claude adottate,
    aperture bloccate, Claude non disponibile; e il risultato netto dei trade aperti secondo la fonte della decisione
    (deepseek da solo, accordo, Claude). Tutto ricostruito dal journal (codici, nessun testo libero)."""
    consults = [r.event for r in events if r.event.kind == "ai_consultation"]
    reviews = [r.event.payload for r in events if r.event.kind == "position_review"
               and isinstance(r.event.payload, Mapping) and r.event.payload.get("triggers")]
    if not consults and not reviews:
        return None
    decisions = {(r.event.payload.get("symbol"), r.event.occurred_at_ms): r.event.event_id for r in events
                 if r.event.kind == "brain_decision" and isinstance(r.event.payload, Mapping)
                 and r.event.payload.get("kind") == "OPEN" and r.event.payload.get("status") == "APPROVED"}
    pnl: dict = {}
    for r in events:
        p = r.event.payload if isinstance(r.event.payload, Mapping) else {}
        if r.event.kind in ("paper_close", "paper_reduce") and p.get("decision_event_id"):
            v = _d(p.get("realized_pnl"))
            if v is not None:
                pnl[p["decision_event_id"]] = pnl.get(p["decision_event_id"], Decimal(0)) + v
    results = {k: {"trades": 0, "net_pnl": Decimal(0)} for k in ("deepseek", "agreed", "claude")}
    codes: dict = {}
    for e in consults:
        p = e.payload if isinstance(e.payload, Mapping) else {}
        if p.get("claude") is not None:
            codes[p.get("code")] = codes.get(p.get("code"), 0) + 1
        src = (p.get("final") or {}).get("source")
        did = decisions.get((p.get("symbol"), e.occurred_at_ms))
        if src in results and did in pnl:
            results[src]["trades"] += 1
            results[src]["net_pnl"] += pnl[did]
    asked = sum(codes.values())
    rev = {k: sum(1 for x in reviews if x.get(f) == v) for k, f, v in (
        ("agreed", "source", "agreed"), ("claude_adopted", "source", "claude"), ("deepseek_kept", "source", "deepseek"))}
    rev["unavailable"] = sum(1 for x in reviews if str(x.get("arbiter", "")).startswith("claude_unavailable"))
    rev["consults"] = sum(1 for x in reviews if x.get("claude") is not None)
    return {"entry": {"consults": asked, "agreed": codes.get("claude_confirmed", 0),
                      "claude_adopted": codes.get("claude_stop_adopted", 0) + codes.get("claude_alternative_adopted", 0),
                      "blocked": codes.get("claude_contested", 0) + codes.get("irreconcilable_no_trade", 0),
                      "unavailable": codes.get("claude_unavailable_critical", 0),
                      "deepseek_only": sum(1 for e in consults if (e.payload or {}).get("claude") is None)},
            "review": rev,
            "results": {k: {"trades": v["trades"], "net_pnl": str(v["net_pnl"])} for k, v in results.items()}}


def _piggy(cfg: dict, summary, start: Decimal, now_ms: int) -> Optional[dict]:
    """Salvadanaio del Brain unico, ricostruito con la STESSA funzione del runner (``unico.piggy_from_closed``)."""
    u = cfg.get("unico")
    if not u or not u.get("piggy"):
        return None
    from backend.v3.unico import PiggyPolicy, piggy_from_closed
    pol = PiggyPolicy(Decimal(u["piggy"]["reference_equity"]), u["piggy"]["tz"], u["piggy"]["hour"])
    st = piggy_from_closed(summary.closed_trades, initial_equity=start, now_ms=now_ms, policy=pol)
    return {"total": str(st.total), "operating_equity": str(st.operating_equity), "next_sweep_ms": st.next_sweep_ms,
            "reference_equity": str(pol.reference_equity), "sweeps": [[t, str(v)] for t, v in st.sweeps][-14:]}


def _close_ready(ref: RunRef, now_ms: int) -> bool:
    """Chiusura manuale singola disponibile: portafoglio previsto e servizio uscite di QUESTA run sano (come per RC1)."""
    try:
        from backend.v3_api import _brain_single_close_ready, _compare_run_paths
        p = _compare_run_paths(ref.name)
        return p is not None and p.run_id == ref.run_id and _brain_single_close_ready(p, now_ms)
    except Exception:
        return False


def compare(env: Mapping[str, str], now_ms: int) -> dict:
    runs = runs_from_env(env)
    if runs is None:
        return {"available": False, "generated_at_ms": now_ms, "runs": []}
    return {"available": True, "generated_at_ms": now_ms, "runs": [read_run(r, now_ms) for r in runs]}
