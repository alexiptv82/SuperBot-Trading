"""App PAPER (Trade, Performance, Archivio) di Falco Evoluto e Brain Scalp: SOLA LETTURA, nessun file creato.

Ogni numero viene dal journal, dalla configurazione e dal registro di spesa della SUA run (stessa regola di
``compare_view``). Nulla viene stimato in silenzio: cio' che non e' registrato resta ``None``.

* ``enrich_trades``: aggiunge ai trade di ``v3_api._trades`` lo stop e il take-profit della posizione (calcolato dalla
  politica d'uscita della configurazione della run con ``exits.take_profit_price``, la stessa funzione del servizio
  uscite) e, per le chiusure, P&L lordo e tipo di stop (iniziale, break-even, trailing). Lo stop e' quello
  dell'apertura: la protezione dei profitti puo' averlo spostato, e la chiusura lo dichiara in ``stop_kind``.
* ``performance``: periodo della run, risultati giornalieri (giorno di calendario italiano), curva dell'equity
  contabile (a ogni chiusura) e a mercato (campioni del Guardian con prezzi verificati), statistiche dei trade,
  motivi delle decisioni (anche NO_TRADE) e costi AI per giorno.
* ``archive_index`` / ``archive_detail``: run archiviate dal reset PAPER (``<radice>/reset-<data>/<cartella>`` con
  ``<cartella>.RISULTATI.json``, segno di archivio completo), in sola lettura, mai mescolate alle run attive.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Optional

from backend.v3.compare_view import PORTFOLIO_ID, RunRef, _CODE, _d, _s, read_run
from backend.v3.events import EventJournal

ARCHIVE_ENV = "V3_PAPER_ARCHIVE_ROOT"
DAY_TZ = "Europe/Rome"
_STAMP = re.compile(r"^reset-[0-9]{8}T[0-9]{6}Z$")
_DIR = re.compile(r"^brain-v3-[a-z0-9-]{1,48}$")
_RUN = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
_KEY = re.compile(r"^(reset-[0-9]{8}T[0-9]{6}Z)~(brain-v3-[a-z0-9-]{1,48})$")
_MICRO = Decimal(1_000_000)
MAX_CURVE = 300
LAST_DECISIONS = 40
LABELS = {"brain-v3-falco-evoluto-p1": "Falco Evoluto", "brain-v3-brain-scalp-p1": "Brain Scalp"}


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(DAY_TZ), DAY_TZ
    except Exception:              # immagine senza dati dei fusi: si dichiara UTC, mai un giorno sbagliato in silenzio
        return timezone.utc, "UTC"


def load_config(run_dir: Path):
    try:
        from backend.v3.runner.config import load_runner_config
        return load_runner_config((run_dir / "runner_config.json").read_bytes())
    except (OSError, ValueError):
        return None


def _policy(cfg):
    if cfg is None:
        return None
    if cfg.exit_policy is not None:
        return cfg.exit_policy
    try:
        from backend.v3.runner.exits import load_default_policy
        return load_default_policy()
    except (OSError, ValueError):
        return None


def take_profit(cfg, side, entry, stop) -> Optional[str]:
    """Take-profit della posizione dalla politica d'uscita della run; ``None`` se non calcolabile."""
    policy = _policy(cfg)
    e, s = _d(entry), _d(stop)
    if policy is None or e is None or s is None or type(side) is not int:
        return None
    try:
        from backend.v3.runner.exits import take_profit_price
        return str(take_profit_price(side, e, s, policy))
    except ValueError:
        return None


def _events(run_dir: Path, run_id: str):
    path = run_dir / "journal.db"
    if not path.is_file():
        return None
    try:
        return EventJournal(str(path)).list_run(PORTFOLIO_ID, run_id)
    except Exception:
        return None


def _payload(r) -> Mapping:
    return r.event.payload if isinstance(r.event.payload, Mapping) else {}


def enrich_trades(data: dict, run_dir: Path, run_id: str) -> dict:
    """Stop, take-profit, P&L lordo e tipo di stop accanto ai trade di ``_trades`` (stesso journal)."""
    cfg = load_config(run_dir)
    opens, closes = {}, {}
    for r in _events(run_dir, run_id) or []:
        p = _payload(r)
        pid = p.get("position_id")
        if type(pid) is not str:
            continue
        if r.event.kind == "paper_open":
            opens[pid] = p
        elif r.event.kind == "paper_close":
            closes[pid] = p
    for t in data.get("open_positions") or []:
        o = opens.get(t.get("position_id"), {})
        t["take_profit"] = take_profit(cfg, t.get("side"), t.get("entry"), t.get("stop"))
        t["notional"] = _s(o.get("notional"))
    for t in data.get("closed_trades") or []:
        o, c = opens.get(t.get("position_id"), {}), closes.get(t.get("position_id"), {})
        stop = _s(o.get("stop_price"))
        t["stop"] = stop
        t["take_profit"] = take_profit(cfg, t.get("side"), o.get("fill_price"), stop) if stop else None
        t["gross_pnl"] = _s(c.get("gross_pnl"))
        kind = c.get("stop_kind")
        t["stop_kind"] = kind if kind in ("initial", "break_even", "trailing", "protect") else None
        t["opened_at_ms"] = c.get("opened_at_ms") if type(c.get("opened_at_ms")) is int else None
    data["fee_bps"] = None if cfg is None else str(cfg.fee_bps)
    data["take_profit_r"] = None if _policy(cfg) is None else str(_policy(cfg).take_profit_r)
    return data


def _spend_by_day(path: Path, tz, immutable: bool = False) -> Optional[dict]:
    """Costi AI per giorno; ``immutable`` solo per le run archiviate (vedi ``compare_view._spend``)."""
    if not path.is_file():
        return None
    try:
        uri = path.resolve().as_uri().replace("file://", "file:") + ("?immutable=1" if immutable else "?mode=ro")
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute("SELECT occurred_at, units FROM spend_events").fetchall()
    except (sqlite3.Error, OSError):
        return None
    out: dict = {}
    for t, u in rows:
        try:
            when = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except ValueError:
            return None             # registro non interpretabile: nessun costo per giorno, mai una cifra parziale
        if type(u) is not int:
            continue
        day = when.astimezone(tz).date().isoformat()
        out[day] = out.get(day, 0) + u
    return {k: Decimal(v) / _MICRO for k, v in out.items()}


def _thin(points: list) -> list:
    if len(points) <= MAX_CURVE:
        return points
    step = len(points) / (MAX_CURVE - 1)
    return [points[int(i * step)] for i in range(MAX_CURVE - 1)] + [points[-1]]


def _day(ms: int, tz) -> str:
    return datetime.fromtimestamp(ms / 1000, tz).date().isoformat()


def performance(run_dir: Path, run_id: str, now_ms: int, *, archived: bool = False) -> dict:
    """Periodo, risultati giornalieri, curve, statistiche e motivi delle decisioni della run (sola lettura)."""
    cfg = load_config(run_dir)
    events = _events(run_dir, run_id)
    if cfg is None or events is None:
        return {"available": False, "run_id": run_id}
    tz, tz_name = _tz()
    start_eq = cfg.initial_equity
    eq = start_eq
    started = events[0].event.occurred_at_ms if events else None
    first_decision = None
    curve = [] if started is None else [{"t": started, "equity": str(eq)}]
    mtm = []
    days: dict = {}
    trades = []
    reasons, risk, regimes, kinds = {}, {}, {}, {}
    last = []

    def bucket(day):
        return days.setdefault(day, {"date": day, "trades": 0, "wins": 0, "losses": 0, "gross": Decimal(0),
                                     "fees": Decimal(0), "net": Decimal(0)})

    for r in events:
        ev, p = r.event, _payload(r)
        if ev.kind == "paper_close":
            pnl = _d(p.get("realized_pnl"))
            if pnl is None:
                continue
            eq += pnl
            curve.append({"t": ev.occurred_at_ms, "equity": str(eq)})
            b = bucket(_day(ev.occurred_at_ms, tz))
            b["trades"] += 1
            b["wins"] += pnl > 0
            b["losses"] += pnl < 0
            b["gross"] += _d(p.get("gross_pnl")) or Decimal(0)
            b["fees"] += _d(p.get("fees")) or Decimal(0)
            b["net"] += pnl
            held = p.get("held_ms")
            trades.append((pnl, held if type(held) is int and held >= 0 else None))
        elif ev.kind == "guardian_state":
            mark = _d(p.get("equity"))
            if mark is not None and not any(x in (p.get("reasons") or []) for x in ("data_fault", "guardian_error")):
                at = p.get("as_of_ms") if type(p.get("as_of_ms")) is int else ev.occurred_at_ms
                mtm.append({"t": at, "equity": str(mark)})
        elif ev.kind == "brain_decision":
            first_decision = first_decision or ev.occurred_at_ms
            code = p.get("rationale") if _CODE.match(str(p.get("rationale", ""))) else None
            rr = p.get("risk_reason") if _CODE.match(str(p.get("risk_reason", ""))) else None
            reg = p.get("regime") if _CODE.match(str(p.get("regime", "")).lower()) else None
            kind = p.get("kind") if p.get("kind") in ("OPEN", "NO_TRADE", "CLOSE", "MODIFY_STOP", "HOLD") else None
            status = p.get("status") if _CODE.match(str(p.get("status", "")).lower()) else None
            reasons[code or "—"] = reasons.get(code or "—", 0) + 1
            if rr:
                risk[rr] = risk.get(rr, 0) + 1
            if reg:
                regimes[reg] = regimes.get(reg, 0) + 1
            key = f"{kind or '—'}:{status or '—'}"
            kinds[key] = kinds.get(key, 0) + 1
            last.append({"ts_ms": ev.occurred_at_ms, "symbol": p.get("symbol") if _CODE.match(
                str(p.get("symbol", "")).lower()) else None, "kind": kind, "status": status, "rationale": code,
                "risk_reason": rr, "regime": reg})

    spend = _spend_by_day(run_dir / "budget.db", tz, immutable=archived)
    daily = []
    if started is not None:
        d0 = datetime.fromtimestamp(started / 1000, tz).date()
        d1 = datetime.fromtimestamp(now_ms / 1000, tz).date()
        running = start_eq
        d = d0
        while d <= d1 and len(daily) < 400:
            k = d.isoformat()
            b = days.get(k) or {"date": k, "trades": 0, "wins": 0, "losses": 0, "gross": Decimal(0),
                                "fees": Decimal(0), "net": Decimal(0)}
            running += b["net"]
            ai = None if spend is None else spend.get(k, Decimal(0))
            daily.append({"date": k, "trades": b["trades"], "wins": b["wins"], "losses": b["losses"],
                          "gross": str(b["gross"]), "fees": str(b["fees"]), "net": str(b["net"]),
                          "ai_cost": _s(ai), "net_after_ai": None if ai is None else str(b["net"] - ai),
                          "equity_end": str(running)})
            d += timedelta(days=1)
    wins = [t for t, _ in trades if t > 0]
    losses = [t for t, _ in trades if t < 0]
    holds = [h for _, h in trades if h is not None]
    stats = {"avg_win": _s(sum(wins) / len(wins)) if wins else None,
             "avg_loss": _s(sum(losses) / len(losses)) if losses else None,
             "best": _s(max(t for t, _ in trades)) if trades else None,
             "worst": _s(min(t for t, _ in trades)) if trades else None,
             "avg_hold_ms": int(sum(holds) / len(holds)) if holds else None,
             "payoff": (None if not wins or not losses
                        else str((sum(wins) / len(wins) / (-sum(losses) / len(losses))).quantize(Decimal("0.01"))))}
    return {"available": True, "run_id": run_id, "day_tz": tz_name, "started_at_ms": started,
            "first_decision_ms": first_decision, "generated_at_ms": now_ms,
            "daily": daily, "curve_settled": _thin(curve), "curve_market": _thin(mtm), "stats": stats,
            "decisions": {"total": len(last), "by_reason": reasons, "by_risk_reason": risk, "by_regime": regimes,
                          "by_kind": kinds, "last": last[-LAST_DECISIONS:][::-1]}}


# ------------------------------------------------------------------ archivio delle run PAPER (reset)
def _archive_root(env: Mapping[str, str]) -> Optional[Path]:
    raw = env.get(ARCHIVE_ENV) or ""
    if not raw.startswith("/") or ".." in raw:
        return None
    root = Path(raw)
    return root if root.is_dir() else None


def _archived(root: Path) -> list[tuple[str, str, str, dict]]:
    out = []
    try:
        stamps = sorted((p for p in root.iterdir() if p.is_dir() and _STAMP.match(p.name)), reverse=True)
    except OSError:
        return out
    for st in stamps:
        try:
            names = sorted(st.iterdir())
        except OSError:
            continue
        for f in names:
            if not f.name.endswith(".RISULTATI.json"):
                continue
            folder = f.name[: -len(".RISULTATI.json")]
            if not _DIR.match(folder) or not (st / folder).is_dir():
                continue
            try:
                res = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            if not isinstance(res, dict) or type(res.get("run_id")) is not str or not _RUN.match(res["run_id"]):
                continue
            out.append((st.name, folder, res["run_id"], res))
    return out


def _ref(root: Path, stamp: str, folder: str, run_id: str) -> RunRef:
    return RunRef("archivio", LABELS.get(folder, folder), root / stamp / folder, run_id)


_LIVE_ONLY = ("state", "paused", "manual_close_allowed", "close_pending", "ai_spend")


def archive_index(env: Mapping[str, str], now_ms: int) -> dict:
    root = _archive_root(env)
    if root is None:
        return {"available": False, "generated_at_ms": now_ms, "runs": []}
    runs = []
    for stamp, folder, run_id, res in _archived(root):
        ref = _ref(root, stamp, folder, run_id)
        row = read_run(ref, now_ms, archived=True)
        for k in _LIVE_ONLY:
            row.pop(k, None)
        row["name"] = f"{stamp}~{folder}"
        row["archive"] = stamp
        row["archived_at_ms"] = res.get("closed_at_ms") if type(res.get("closed_at_ms")) is int else None
        evs = _events(ref.dir, run_id) or []
        row["started_at_ms"] = evs[0].event.occurred_at_ms if evs else None
        runs.append(row)
    return {"available": True, "generated_at_ms": now_ms, "runs": runs}


def archive_detail(env: Mapping[str, str], key: str, now_ms: int) -> Optional[dict]:
    """Trade chiusi e performance di UNA run archiviata, ``None`` se la chiave non esiste."""
    m = _KEY.match(key or "")
    root = _archive_root(env)
    if not m or root is None:
        return None
    hit = next((x for x in _archived(root) if x[0] == m.group(1) and x[1] == m.group(2)), None)
    if hit is None:
        return None
    ref = _ref(root, hit[0], hit[1], hit[2])
    from backend.v3.outcomes import extract_outcomes
    try:
        outcomes = extract_outcomes(EventJournal(str(ref.dir / "journal.db")), PORTFOLIO_ID, ref.run_id).outcomes
    except Exception:
        outcomes = ()
    closed = [{"position_id": o.position_id, "symbol": o.symbol, "side": o.side, "leverage": o.leverage,
               "margin": str(o.margin_used), "entry": str(o.entry_price), "exit": str(o.exit_price),
               "fees": str(o.fees), "realized_pnl": str(o.realized_pnl), "exit_reason": o.exit_reason,
               "hold_ms": o.hold_ms, "regime": o.decision_regime or None, "closed_at_ms": o.closed_at_ms}
              for o in sorted(outcomes, key=lambda o: o.closed_at_ms, reverse=True)]
    data = enrich_trades({"open_positions": [], "closed_trades": closed}, ref.dir, ref.run_id)
    return {"key": key, "label": ref.label, "run_id": ref.run_id, "archive": hit[0],
            "closed_trades": data["closed_trades"],
            "performance": performance(ref.dir, ref.run_id, now_ms, archived=True)}
