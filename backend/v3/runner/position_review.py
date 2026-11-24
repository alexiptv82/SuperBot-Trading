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
Stop, take-profit e protezioni deterministici restano SEMPRE attivi: se l'AI non risponde (budget, rete, formato)
la posizione resta protetta esattamente come prima. Nessuna chiusura per solo tempo (24/11): la durata e' solo un dato.
Con Claude consulente (``consult.py``) le azioni importanti passano dall'arbitro prima del validatore. Ogni revisione e' registrata (``position_review``) con codici
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
from backend.v3.unico import parse_reasons

ACTIONS = ("HOLD", "CLOSE", "PARTIAL_CLOSE", "MODIFY_STOP")
MIN_STOP_GAP_BP = Decimal("5")          # uno stop stretto resta ad almeno 5 bp dal prezzo (non scatta all'istante)
REVIEW_KIND = "position_review"
_BP = Decimal(10000)

SYSTEM_PROMPT = (
    'You manage one open PAPER crypto/metal perpetual futures position. Return only JSON, exactly one of '
    '{"action":"HOLD"}, {"action":"CLOSE"}, {"action":"PARTIAL_CLOSE"}, {"action":"MODIFY_STOP","stop_price":"123.45"}; '
    'you may add "confidence" (0 to 1), "reasons" (up to 6 codes from: trend_up, trend_down, trend_weakening, '
    'trend_change, momentum_strong, momentum_fading, volume_confirms, volume_weak, volatility_high, overextended, '
    'reversal_risk, profit_at_risk, costs_high, funding_adverse, better_opportunity, thesis_intact, '
    'thesis_invalidated, liquidity_thin) and "uncertain": true when the picture is unclear. The position object gives '
    'side (1 long, -1 short), entry, current price, current and initial stop, r_now (profit in multiples of the '
    'initial risk), net_pnl and roe_pct (net profit after estimated closing fees and return on margin), mfe_r and '
    'giveback (maximum profit reached and the share of it given back), regime at entry and now, funding rate, '
    'minutes open, take-profit levels and which legs are open: tp1 (first take profit at 2R, about 35 percent) and '
    'runner (the rest, toward 3.5R). The market object gives indicators on closed candles only. Weigh net profit, '
    'trend strength, probability and edge of continuation, reversal risk and the profit that could be given back, '
    'volatility, momentum, volume, costs, funding and better uses of the capital. Use CLOSE when the thesis is '
    'invalidated or the risk of giving back the profit outweighs the expected continuation; PARTIAL_CLOSE to bank the '
    'tp1 leg early; MODIFY_STOP only to tighten the stop toward profit at a level coherent with structure and '
    'volatility. Otherwise HOLD. Time alone is never a reason to close: a trade may last minutes or days. A return of '
    '20 percent on margin is a moment to reassess, not a mandatory exit. Deterministic stop and take-profit orders '
    'stay active anyway. No tools, no orders, no execution authority: code validates every proposal.')


@dataclass(frozen=True)
class ReviewProposal:
    action: str
    stop_price: Optional[Decimal] = None
    confidence: Optional[float] = None
    reasons: tuple = ()
    uncertain: bool = False


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
    quantity: Decimal = Decimal("0")      # somma delle quote aperte
    margin: Decimal = Decimal("0")
    regime_entry: Optional[str] = None    # regime registrato nella decisione di apertura


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
        regime = None
        try:
            dec = journal.get(gid) if gid.startswith("brain-req-") else None
            regime = dec.event.payload.get("regime") if dec is not None and dec.event.run_id == run_id else None
        except Exception:
            regime = None
        views.append(GroupView(gid, first.symbol, first.side, first.fill_price, first.stop_price, g["stop"],
                               first.opened_at_ms, {p.leg: p.position_id for p in ps},
                               {p.leg: p.take_profit_r for p in ps}, sum((p.quantity for p in ps), Decimal("0")),
                               sum((p.margin_used for p in ps), Decimal("0")),
                               regime if isinstance(regime, str) else None))
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

    def review(self, view: GroupView, *, price: Decimal, now_ms: int, mode: str, metrics=None,
               funding=None, market=None) -> ReviewProposal:
        risk = abs(view.fill_price - view.initial_stop)
        r_now = (view.side * (price - view.fill_price) / risk) if risk > 0 else Decimal("0")
        targets = {leg or "single": None if tp is None else str(
            view.fill_price + view.side * tp * risk) for leg, tp in view.take_profit_r.items()}
        pos = {"side": view.side, "entry": str(view.fill_price), "price": str(price),
               "stop_now": str(view.stop_now), "initial_stop": str(view.initial_stop),
               "r_now": str(r_now.quantize(Decimal("0.01"))),
               "minutes_open": max(0, (now_ms - view.opened_at_ms) // 60_000),
               "legs_open": sorted(k or "single" for k in view.legs), "take_profit_prices": targets,
               "funding_rate": None if funding is None else str(funding)}
        if metrics is not None:
            pos.update({k: v for k, v in metrics.payload().items() if k != "r_now"})
            pos["net_pnl"] = str(net_pnl(view, price).quantize(Decimal("0.01")))
        info = {"symbol": view.symbol, "timestamp_ms": now_ms, "guardian_mode": mode, "position": pos,
                "market": market if market is not None else self.market_view(view.symbol, now_ms)}
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
            reasons = parse_reasons(obj.pop("reasons", None))
            uncertain = obj.pop("uncertain", False)
            if type(uncertain) is not bool:
                raise ValueError()
            allowed = {"action", "confidence"} | ({"stop_price"} if action == "MODIFY_STOP" else set())
            if action not in ACTIONS or not set(obj) <= allowed or (action == "MODIFY_STOP") != ("stop_price" in obj):
                raise ValueError()
            conf = obj.get("confidence")
            if conf is not None and (type(conf) not in (int, float) or not math.isfinite(conf) or not 0 <= conf <= 1):
                raise ValueError()
            stop = _bounded_decimal(obj["stop_price"]) if action == "MODIFY_STOP" else None
            return ReviewProposal(action, stop, None if conf is None else float(conf), reasons, uncertain)
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


FEE_FRACTION = Decimal("0.0006")                     # commissione per lato stimata (6 bp), come la configurazione


def net_pnl(view: GroupView, price: Decimal) -> Decimal:
    """P&L netto se si chiudesse ora: movimento meno commissioni di andata e ritorno stimate."""
    gross = view.side * (price - view.fill_price) * view.quantity
    return gross - (view.fill_price + price) * view.quantity * FEE_FRACTION


def metrics_for(view: GroupView, price: Decimal, best: Optional[Decimal], regime_now: Optional[str]):
    from backend.v3.runner.consult import PositionMetrics
    risk = abs(view.fill_price - view.initial_stop)
    r_now = view.side * (price - view.fill_price) / risk if risk > 0 else Decimal("0")
    roe = net_pnl(view, price) / view.margin * 100 if view.margin > 0 else Decimal("0")
    mfe = giveback = None
    if best is not None and risk > 0:
        mfe = max(view.side * (best - view.fill_price) / risk, r_now, Decimal("0"))
        giveback = (mfe - r_now) / mfe if mfe > 0 else Decimal("0")
    return PositionMetrics(r_now, roe, mfe, giveback, view.regime_entry, regime_now)


def review_open_positions(*, journal: EventJournal, run_id: str, data_dir: Path, now_ms: int, reviewer,
                          price_of: Callable[[str, int], Decimal], mode: str = "NORMAL", consultant=None,
                          best_of: Optional[Callable] = None, funding_of: Optional[Callable] = None,
                          market_of: Optional[Callable] = None) -> tuple[ReviewOutcome, ...]:
    """Una revisione per apertura; scrive gli eventi ``position_review`` / ``stop_move`` e al massimo UNA richiesta di
    chiusura. Un errore su un'apertura non ferma le altre e non tocca mai la posizione (resta protetta).

    Con ``consultant`` (Claude): se scatta un criterio (``consult.position_triggers``) Claude valuta in modo
    indipendente e l'arbitro (``consult.arbitrate_position``) decide; poi il validatore. Nel journal: proposta di
    DeepSeek, valutazione di Claude, criteri, decisione finale con la sua fonte e il codice, metriche."""
    from backend.v3.runner.consult import POSITION_PROMPT, arbitrate_position, position_triggers
    outcomes: list[ReviewOutcome] = []
    to_close: list[str] = []
    if consultant is not None:
        consultant.start_cycle(now_ms // 900_000)
    for i, view in enumerate(groups_from_journal(journal, run_id)):
        proposed, executed, code, ids, extra = "NONE", "HOLD", "", (), {}
        try:
            price = price_of(view.symbol, now_ms)
            if type(price) is not Decimal or not price.is_finite() or price <= 0:
                raise ValueError("price")
            market = None
            if market_of is not None:
                try:
                    market = market_of(view.symbol, now_ms)
                except Exception:
                    market = None
            best = None
            if best_of is not None:
                try:
                    best = best_of(view.symbol, view.side, view.opened_at_ms, now_ms)
                except Exception:
                    best = None
            funding = None
            if funding_of is not None:
                try:
                    funding = funding_of(view.symbol)
                except Exception:
                    funding = None
            m = metrics_for(view, price, best, (market or {}).get("regime") if isinstance(market, dict) else None)
            extra["metrics"] = m.payload()
            try:
                prop = reviewer.review(view, price=price, now_ms=now_ms, mode=mode, metrics=m, funding=funding,
                                       market=market)
            except ProviderUnavailable as exc:
                code = str(exc) if str(exc) in ("budget_denied", "invalid_model_output") else "ai_unavailable"
                prop = None
            if prop is not None:
                proposed = prop.action
                extra["deepseek"] = {"action": prop.action, "confidence": prop.confidence,
                                     "reasons": list(prop.reasons), "uncertain": prop.uncertain,
                                     "stop_price": None if prop.stop_price is None else str(prop.stop_price)}
                final = prop
                if consultant is not None:
                    triggers = position_triggers(prop.action, prop.uncertain, m)
                    if "action_proposed" not in triggers and consultant.cooling(view.group, now_ms):
                        triggers = ()                    # stessa posizione appena valutata: nessuna spesa in piu'
                    claude = None
                    if triggers:
                        info = {"symbol": view.symbol, "timestamp_ms": now_ms, "guardian_mode": mode,
                                "market": market, "position": {
                                    "side": view.side, "entry": str(view.fill_price), "price": str(price),
                                    "stop_now": str(view.stop_now), "initial_stop": str(view.initial_stop),
                                    "net_pnl": str(net_pnl(view, price).quantize(Decimal("0.01"))),
                                    "funding_rate": None if funding is None else str(funding),
                                    "minutes_open": max(0, (now_ms - view.opened_at_ms) // 60_000),
                                    "legs_open": sorted(k or "single" for k in view.legs), **m.payload()},
                                "deepseek": extra["deepseek"]}
                        claude = consultant.ask(POSITION_PROMPT, info, key=view.group, now_ms=now_ms, position=True)
                    v = arbitrate_position(prop.action, prop.stop_price, prop.confidence, claude, m, view.side)
                    extra.update(triggers=list(triggers), claude=None if claude is None else claude.payload(),
                                 source=v.source, arbiter=v.code,
                                 disagreement=bool(claude is not None and claude.status == "ok"
                                                   and claude.verdict != "CONFIRM"))
                    final = ReviewProposal(v.action, v.stop, prop.confidence, prop.reasons, prop.uncertain)
                executed, code, ids = validate(final, view, price)
                if extra.get("arbiter", "no_consult_needed") not in ("no_consult_needed", "claude_confirmed") \
                        and executed == "HOLD" and code == "hold":
                    code = extra["arbiter"]              # HOLD deciso dall'arbitro: il motivo e' il suo
                if prop.confidence is not None:
                    extra["confidence"] = str(prop.confidence)
                if executed == "MODIFY_STOP":
                    extra.update(stop_price=str(final.stop_price), previous_stop=str(view.stop_now))
                    for pid in ids:
                        journal.append(Event(
                            event_id=f"stop_move.{pid}.{now_ms}", portfolio_id="brain", run_id=run_id,
                            kind=STOP_MOVE_KIND, occurred_at_ms=now_ms, source="runner.position_review",
                            payload={"position_id": pid, "stop_price": str(final.stop_price),
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
