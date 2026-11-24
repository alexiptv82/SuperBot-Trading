"""Revisione AI delle posizioni aperte del Brain unico PAPER (24/11/2026): DeepSeek PROPONE, il codice DECIDE.

Per ogni apertura (una o due quote con lo stesso stop) il modello vede il mercato (stessa vista dell'analista), la
posizione (lato, ingresso, prezzo, stop, R, durata, quote aperte) e il modo del Guardian, e propone una sola azione:

* ``HOLD``          nessuna azione;
* ``CLOSE``         chiudere tutte le quote ora;
* ``PARTIAL_CLOSE`` incassare subito la quota ``tp1`` (solo se sono aperte entrambe le quote);
* ``MODIFY_STOP``   stringere lo stop a ``stop_price``.

Il validatore (``validate``) esegue solo cio' che rispetta regole fisse: lo stop si sposta SOLO verso il profitto e
resta ad almeno ``MIN_STOP_GAP_BP`` dal prezzo; la presa parziale esiste solo con due quote aperte; tutto il resto
diventa HOLD con un codice. Le chiusure passano dal servizio delle uscite (``brain_close_request.json``, motivo
``brain_close``); gli stop stretti sono eventi ``stop_move`` che il monitor applica dalla candela successiva.
Stop, take-profit e durata massima deterministici restano SEMPRE attivi: se l'AI non risponde (budget, rete, formato)
la posizione resta protetta esattamente come prima. Ogni revisione e' registrata (``position_review``) con codici
fissi, mai testo libero del modello.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping, Optional

from backend.v3.brain_f3.providers import ProviderUnavailable, Transport, _bounded_decimal, _call, _json_object
from backend.v3.dashboard import build_summary
from backend.v3.events import Event, EventJournal
from backend.v3.runner.manual_close import BRAIN_CHANNEL
from backend.v3.runner.monitor import STOP_MOVE_KIND, stop_moves_by_position

ACTIONS = ("HOLD", "CLOSE", "PARTIAL_CLOSE", "MODIFY_STOP")
MIN_STOP_GAP_BP = Decimal("5")          # uno stop stretto resta ad almeno 5 bp dal prezzo (non scatta all'istante)
REVIEW_KIND = "position_review"
_BP = Decimal(10000)

SYSTEM_PROMPT = (
    'You manage one open PAPER crypto/metal perpetual futures position. Return only JSON, exactly one of '
    '{"action":"HOLD"}, {"action":"CLOSE"}, {"action":"PARTIAL_CLOSE"}, {"action":"MODIFY_STOP","stop_price":"123.45"}; '
    'you may add "confidence" (0 to 1). The position object gives side (1 long, -1 short), entry, current price, '
    'current stop, initial stop, r_now (profit in multiples of the initial risk), minutes open, take-profit levels '
    'and which legs are open: leg tp1 (first take profit, about 35 percent of the size) and leg runner (the rest). '
    'The market object gives indicators on closed candles only (distances in basis points of the last close, atr_bp). '
    'Use CLOSE when the trade thesis is invalidated or momentum turned clearly against the position. Use '
    'PARTIAL_CLOSE to bank the tp1 leg early when the profit is meaningful but continuation is doubtful. Use '
    'MODIFY_STOP only to tighten the stop toward profit at a level coherent with structure and volatility, never to '
    'widen it. Otherwise HOLD: deterministic stop, take-profit and time exits stay active anyway. Round-trip costs '
    'are about 16 basis points. Do not close a healthy trade just because it is open. No tools, no orders, no '
    'execution authority: code validates every proposal.')


@dataclass(frozen=True)
class ReviewProposal:
    action: str
    stop_price: Optional[Decimal] = None
    confidence: Optional[float] = None


@dataclass(frozen=True)
class GroupView:
    group: str
    symbol: str
    side: int
    fill_price: Decimal
    initial_stop: Decimal
    stop_now: Decimal                     # stop iniziale o l'ultimo stretto dall'AI (il monitor puo' averlo alzato)
    opened_at_ms: int
    legs: Mapping[str, str]               # nome quota ("" | tp1 | runner) -> position_id
    take_profit_r: Mapping[str, Optional[Decimal]]


@dataclass(frozen=True)
class ReviewOutcome:
    group: str
    symbol: str
    proposed: str
    executed: str
    code: str


def groups_from_journal(journal: EventJournal, run_id: str) -> list[GroupView]:
    summary = build_summary(journal, "brain", run_id)
    moves = stop_moves_by_position(journal, "brain", run_id)
    out: dict[str, dict] = {}
    for p in summary.open_positions:
        g = out.setdefault(p.group, {"positions": [], "stop": p.stop_price})
        g["positions"].append(p)
        for _at, level in moves.get(p.position_id, ()):
            if p.side * (level - g["stop"]) > 0:
                g["stop"] = level
    views = []
    for gid, g in out.items():
        ps = g["positions"]
        first = min(ps, key=lambda x: x.opened_at_ms)
        views.append(GroupView(gid, first.symbol, first.side, first.fill_price, first.stop_price, g["stop"],
                               first.opened_at_ms, {p.leg: p.position_id for p in ps},
                               {p.leg: p.take_profit_r for p in ps}))
    return sorted(views, key=lambda v: (v.opened_at_ms, v.group))


def validate(proposal: ReviewProposal, view: GroupView, price: Decimal) -> tuple[str, str, tuple[str, ...]]:
    """``(azione eseguita, codice, position_id coinvolti)``. Tutto cio' che non rispetta le regole diventa HOLD."""
    if proposal.action == "HOLD":
        return "HOLD", "hold", ()
    if proposal.action == "CLOSE":
        return "CLOSE", "close_all_legs", tuple(view.legs.values())
    if proposal.action == "PARTIAL_CLOSE":
        if "tp1" in view.legs and "runner" in view.legs:
            return "PARTIAL_CLOSE", "close_tp1_leg", (view.legs["tp1"],)
        return "HOLD", "partial_not_available", ()
    if proposal.action == "MODIFY_STOP":
        new = proposal.stop_price
        if type(new) is not Decimal or not new.is_finite() or new <= 0:
            return "HOLD", "stop_invalid", ()
        if view.side * (new - view.stop_now) <= 0:
            return "HOLD", "stop_not_tighter", ()                 # mai allargare (ne' ripetere) lo stop
        if view.side * (price - new) < price * MIN_STOP_GAP_BP / _BP:
            return "HOLD", "stop_too_close_to_price", ()
        return "MODIFY_STOP", "stop_tightened", tuple(view.legs.values())
    return "HOLD", "action_invalid", ()


class DeepSeekPositionReviewer:
    """Una chiamata DeepSeek per apertura, sullo stesso trasporto metrato (stessa spesa e stesso tetto giornaliero)."""

    def __init__(self, *, transport: Transport, model: str, spending_gate, max_tokens: int,
                 market_view: Callable[[str, int], dict]):
        if type(max_tokens) is not int or not 1 <= max_tokens <= 65_536:
            raise ValueError("invalid_max_tokens")
        self.transport, self.model, self.gate = transport, model, spending_gate
        self.max_tokens, self.market_view = max_tokens, market_view

    def review(self, view: GroupView, *, price: Decimal, now_ms: int, mode: str) -> ReviewProposal:
        risk = abs(view.fill_price - view.initial_stop)
        r_now = (view.side * (price - view.fill_price) / risk) if risk > 0 else Decimal("0")
        targets = {leg or "single": None if tp is None else str(
            view.fill_price + view.side * tp * risk) for leg, tp in view.take_profit_r.items()}
        info = {"symbol": view.symbol, "timestamp_ms": now_ms, "guardian_mode": mode,
                "position": {"side": view.side, "entry": str(view.fill_price), "price": str(price),
                             "stop_now": str(view.stop_now), "initial_stop": str(view.initial_stop),
                             "r_now": str(r_now.quantize(Decimal("0.01"))),
                             "minutes_open": max(0, (now_ms - view.opened_at_ms) // 60_000),
                             "legs_open": sorted(k or "single" for k in view.legs),
                             "take_profit_prices": targets},
                "market": self.market_view(view.symbol, now_ms)}
        payload = {"model": self.model, "stream": False, "max_tokens": self.max_tokens,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": json.dumps(info, sort_keys=True)}]}
        body = _call(self.transport, self.gate, "deepseek", self.model, True, payload)
        try:
            choices = body["choices"]
            if type(choices) is not list or len(choices) != 1 or choices[0]["finish_reason"] != "stop":
                raise ValueError()
            obj = _json_object(choices[0]["message"]["content"])
            action = obj.get("action")
            allowed = {"action", "confidence"} | ({"stop_price"} if action == "MODIFY_STOP" else set())
            if action not in ACTIONS or not set(obj) <= allowed or (action == "MODIFY_STOP") != ("stop_price" in obj):
                raise ValueError()
            conf = obj.get("confidence")
            if conf is not None and (type(conf) not in (int, float) or not math.isfinite(conf) or not 0 <= conf <= 1):
                raise ValueError()
            stop = _bounded_decimal(obj["stop_price"]) if action == "MODIFY_STOP" else None
            return ReviewProposal(action, stop, None if conf is None else float(conf))
        except Exception:
            raise ProviderUnavailable("invalid_model_output") from None


def _write_close_request(data_dir: Path, ids: list[str], now_ms: int) -> bool:
    """Richiesta atomica al servizio delle uscite; ``False`` se ce n'e' gia' una in attesa (si riprova al giro dopo)."""
    target = data_dir / BRAIN_CHANNEL["request_file"]
    if target.exists() or (data_dir / BRAIN_CHANNEL["work_file"]).exists():
        return False
    fd, tmp = tempfile.mkstemp(dir=data_dir, prefix=".brain_close_request.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"ts_ms": now_ms, "position_ids": ids}, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    return True


def review_open_positions(*, journal: EventJournal, run_id: str, data_dir: Path, now_ms: int, reviewer,
                          price_of: Callable[[str, int], Decimal], mode: str = "NORMAL") -> tuple[ReviewOutcome, ...]:
    """Una revisione per apertura; scrive gli eventi ``position_review`` / ``stop_move`` e al massimo UNA richiesta di
    chiusura. Un errore su un'apertura non ferma le altre e non tocca mai la posizione (resta protetta)."""
    outcomes: list[ReviewOutcome] = []
    to_close: list[str] = []
    for i, view in enumerate(groups_from_journal(journal, run_id)):
        proposed, executed, code, ids, extra = "NONE", "HOLD", "", (), {}
        try:
            price = price_of(view.symbol, now_ms)
            if type(price) is not Decimal or not price.is_finite() or price <= 0:
                raise ValueError("price")
            try:
                prop = reviewer.review(view, price=price, now_ms=now_ms, mode=mode)
            except ProviderUnavailable as exc:
                code = str(exc) if str(exc) in ("budget_denied", "invalid_model_output") else "ai_unavailable"
                prop = None
            if prop is not None:
                proposed = prop.action
                executed, code, ids = validate(prop, view, price)
                if prop.confidence is not None:
                    extra["confidence"] = str(prop.confidence)
                if executed == "MODIFY_STOP":
                    extra.update(stop_price=str(prop.stop_price), previous_stop=str(view.stop_now))
                    for pid in ids:
                        journal.append(Event(
                            event_id=f"stop_move.{pid}.{now_ms}", portfolio_id="brain", run_id=run_id,
                            kind=STOP_MOVE_KIND, occurred_at_ms=now_ms, source="runner.position_review",
                            payload={"position_id": pid, "stop_price": str(prop.stop_price),
                                     "previous_stop": str(view.stop_now), "symbol": view.symbol}))
                elif executed in ("CLOSE", "PARTIAL_CLOSE"):
                    to_close.extend(ids)
        except Exception:
            code = code or "review_failed"
        journal.append(Event(
            event_id=f"{REVIEW_KIND}.{now_ms}.{i}", portfolio_id="brain", run_id=run_id, kind=REVIEW_KIND,
            occurred_at_ms=now_ms, source="runner.position_review",
            payload={"symbol": view.symbol, "group": view.group, "side": view.side, "proposed": proposed,
                     "executed": executed, "code": code or "ai_unavailable", "guardian_mode": mode, **extra}))
        outcomes.append(ReviewOutcome(view.group, view.symbol, proposed, executed, code or "ai_unavailable"))
    if to_close and not _write_close_request(data_dir, to_close, now_ms):
        outcomes = [o if o.executed not in ("CLOSE", "PARTIAL_CLOSE")
                    else ReviewOutcome(o.group, o.symbol, o.proposed, o.executed, "close_request_pending")
                    for o in outcomes]
    return tuple(outcomes)
