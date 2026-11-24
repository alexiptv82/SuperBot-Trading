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

from backend.v3.dashboard import build_summary
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
            rows = db.execute("SELECT occurred_at, units FROM spend_events").fetchall()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day = sum(u for t, u in rows if type(u) is int and str(t).startswith(today))
        total = sum(u for _, u in rows if type(u) is int)
        return {"day": str(Decimal(day) / _MICRO), "total": str(Decimal(total) / _MICRO)}
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
            "take_profit_r": None if c.exit_policy is None else str(c.exit_policy.take_profit_r)}


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
    guardian, decisions = None, []
    mtm_samples: list[Decimal] = []      # equity a mercato registrate dal Guardian con prezzi verificati
    mtm_incomplete = False
    for r in events:
        ev, p = r.event, (r.event.payload if isinstance(r.event.payload, Mapping) else {})
        if ev.kind == "paper_close":
            pnl = _d(p.get("realized_pnl"))
            if pnl is None:
                continue
            equity += pnl
            peak = max(peak, equity)
            if peak - equity > max_dd:
                max_dd, max_dd_pct = peak - equity, (peak - equity) / peak * 100
            fees += _d(p.get("fees")) or Decimal("0")
            b = sides["long" if p.get("side") == 1 else "short"]
            b["trades"] += 1
            b["net_pnl"] += pnl
            if pnl > 0:
                wins, gross_win, b["wins"] = wins + 1, gross_win + pnl, b["wins"] + 1
            elif pnl < 0:
                losses, gross_loss, b["losses"] = losses + 1, gross_loss - pnl, b["losses"] + 1
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
        elif ev.kind == "brain_decision":
            decisions.append({"ts_ms": ev.occurred_at_ms, "symbol": p.get("symbol"), "kind": p.get("kind"),
                              "status": p.get("status"),
                              "rationale": p.get("rationale") if _CODE.match(str(p.get("rationale", ""))) else None,
                              "risk_reason": p.get("risk_reason") if _CODE.match(str(p.get("risk_reason", "")))
                              else None,
                              "sources": [s for s in (p.get("sources") or []) if isinstance(s, str) and _CODE.match(s)]})
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
    hb = None
    try:
        hb = json.loads((ref.dir / "heartbeat.json").read_text())
    except (OSError, ValueError):
        pass
    return dict(base, available=True, config={k: (str(v) if isinstance(v, Decimal) else v) for k, v in cfg.items()},
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
                wins=wins, losses=losses, closed=len(summary.closed_trades),
                win_rate=None if not decided else str((Decimal(wins) * 100 / decided).quantize(Decimal("0.1"))),
                fees=str(fees), by_side=sides, manual_closes=manual, protected_stops=protected,
                open_positions=[{"position_id": o.position_id, "symbol": o.symbol, "side": o.side,
                                 "entry": str(o.fill_price), "stop": str(o.stop_price), "margin": str(o.margin_used),
                                 "leverage": o.leverage, "opened_at_ms": o.opened_at_ms}
                                for o in summary.open_positions],
                guardian=guardian, decisions=decisions[-8:][::-1], ai_spend=spend,
                manual_close_allowed=_close_ready(ref, now_ms),
                close_pending=(ref.dir / "close_request.json").exists())


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
