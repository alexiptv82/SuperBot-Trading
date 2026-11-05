"""P2 — legame decisione -> posizione: test offline.

``BrainDecision.journal_event_id`` deve valere l'event_id dell'evento
``brain_decision`` scritto dal motore, e SOLO per una decisione OPEN/APPROVED
realmente scritta. Standard (lezione del 4/11): un test di controllo con motore
valido, asserzioni esatte, e almeno un mutante che fa fallire ogni test.

Il motore e' configurato in modo valido (run_id, mandato coerente, journal con
schema): un motore non valido risponderebbe NO_TRADE('invalid_input') prima di
raggiungere i controlli che i test dichiarano di verificare.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from decimal import Decimal

import pytest

from backend.v3.brain_f2.analyst import Analyst, MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import (
    BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus,
)
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot, _policy_hash
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.events import Event, EventJournal
from backend.v3.risk import RiskPolicy

RUN = "r-p2-link"
TS = 1_700_000_000_000
EID_RE = re.compile(r"^brain-req-[0-9a-f]{32}$")
FORGED = "brain-req-forgedforgedforgedforgedforged00"


def _journal() -> EventJournal:
    j = EventJournal(os.path.join(tempfile.mkdtemp(), "journal.db"))
    j.init_schema()
    return j


def _engine(journal, analyst=None) -> BrainEngine:
    policy = RiskPolicy(Decimal(".02"), Decimal(".05"), Decimal(".1"),
                        Decimal(".3"), Decimal("450"), Decimal("16"), Decimal(".5"))
    snapshot = BrainPortfolioSnapshot(Decimal("1000"), Decimal("1000"),
                                      Decimal("0"), Decimal("0"))
    params = {"exchange_leverage_limit": 10, "quantity_step": Decimal(".001"),
              "minimum_notional": Decimal("5"), "maintenance_fraction": Decimal(".004"),
              "market_data_fresh": True, "paused": False, "daily_loss_latched": False}
    return BrainEngine(
        analyst=analyst or MockDeepSeekAnalyst(),
        reviewer=MockClaudeReviewer(always_approve=True),
        risk_policy=policy, portfolio_snapshot=snapshot, market_params=params,
        journal=journal, portfolio_id="brain", run_id=RUN,
        policy_verifier=lambda m, p: True,
        policy_mandate={"version": "p2-test", "approved_by": "operator",
                        "approved": True, "portfolio_id": "brain", "run_id": RUN,
                        "policy_hash": _policy_hash(policy)},
    )


def _ctx(symbol="BTCUSDT", regime="TRENDING", ts=TS, price="50000") -> MarketContext:
    return MarketContext(symbol, Decimal(price), ts, regime)


def _events(journal):
    return [s.event for s in journal.list_run("brain", RUN) if s.event.kind == "brain_decision"]


def _open_decision(**over) -> BrainDecision:
    prop = OpenProposal(symbol="BTCUSDT", side=1, entry_price=Decimal("50000"),
                        stop_price=Decimal("49000"), leverage=2, rationale="deepseek:analysis",
                        confidence=0.9, originating_ai="deepseek", context_hash="h")
    kw = dict(kind=DecisionKind.OPEN, proposal=prop, rationale="deepseek:analysis",
              sources=["deepseek:analysis"], occurred_at_ms=TS)
    kw.update(over)
    return BrainDecision(**kw)


class _Scripted(Analyst):
    """Analista che restituisce una decisione scelta dal test (anche ostile)."""

    def __init__(self, make):
        self.make = make

    def analyze(self, context, open_positions):
        return self.make(context)


# ---------------------------------------------------------------------------
# controllo + legame
# ---------------------------------------------------------------------------

class TestLinkOnApprovedOpen:
    def test_control_valid_engine_approves(self):
        """Senza questo controllo gli altri test potrebbero passare per un motore mal configurato."""
        d = _engine(_journal()).step(_ctx())
        assert (d.kind, d.status, d.rationale) == (
            DecisionKind.OPEN, ProposalStatus.APPROVED, "risk_quote_ok")

    def test_id_equals_the_journal_event_id(self):
        j = _journal()
        d = _engine(j).step(_ctx())
        evs = _events(j)
        assert len(evs) == 1
        assert d.journal_event_id == evs[0].event_id
        assert EID_RE.match(d.journal_event_id)

    def test_payload_has_symbol_and_regime(self):
        j = _journal()
        _engine(j).step(_ctx(symbol="BTCUSDT", regime="TRENDING"))
        p = _events(j)[0].payload
        assert (p["symbol"], p["regime"]) == ("BTCUSDT", "TRENDING")
        assert set(p) == {"kind", "status", "rationale", "sources", "claim", "symbol", "regime"}

    def test_memory_episode_keeps_the_id(self):
        j = _journal()
        eng = _engine(j)
        d = eng.step(_ctx())
        assert eng.memory[-1].decision.journal_event_id == d.journal_event_id

    def test_second_distinct_step_gets_a_distinct_id(self):
        j = _journal()
        eng = _engine(j)
        a = eng.step(_ctx(ts=TS))
        b = eng.step(_ctx(ts=TS + 60_000))
        assert a.journal_event_id and b.journal_event_id and a.journal_event_id != b.journal_event_id
        assert {e.event_id for e in _events(j)} == {a.journal_event_id, b.journal_event_id}

    def test_construction_without_id_is_backward_compatible(self):
        assert BrainDecision(kind=DecisionKind.NO_TRADE).journal_event_id is None
        d = BrainDecision(DecisionKind.NO_TRADE, None, None, "r", [], 1, ProposalStatus.REJECTED)
        assert d.journal_event_id is None


# ---------------------------------------------------------------------------
# nessun legame se non c'e' una scrittura approvata
# ---------------------------------------------------------------------------

class TestNoIdWithoutApprovedWrite:
    def test_no_trade_has_no_id_but_is_audited(self):
        j = _journal()
        d = _engine(j).step(_ctx(regime="UNKNOWN"))
        assert d.kind == DecisionKind.NO_TRADE and d.journal_event_id is None
        evs = _events(j)  # il motore ha scritto l'audit: None non significa "nulla scritto"
        assert len(evs) == 1 and evs[0].payload["kind"] == "NO_TRADE"
        assert evs[0].payload["regime"] == "UNKNOWN"

    def test_journal_write_failure_means_no_id(self):
        class _Failing(EventJournal):
            def append(self, event):
                raise RuntimeError("disk full")

        base = _journal()
        d = _engine(_Failing(base.filename)).step(_ctx())
        assert d.rationale == "journal_persist_failed"
        assert d.kind == DecisionKind.NO_TRADE and d.journal_event_id is None
        assert _events(base) == []

    def test_lost_write_means_no_id(self):
        """Scrittura 'riconosciuta' ma non persistita: il motore non deve dare un id."""
        class _Lossy(EventJournal):
            def append(self, event):
                return None  # non scrive nulla

        base = _journal()
        d = _engine(_Lossy(base.filename)).step(_ctx())
        assert d.rationale == "journal_persist_failed" and d.journal_event_id is None

    def test_foreign_claim_means_no_id(self):
        """L'evento nel journal ha lo stesso id ma un claim diverso dal nostro: non e' la nostra scrittura."""
        class _Foreign(EventJournal):
            def append(self, event):
                payload = dict(event.payload, claim="not-our-claim")
                return super().append(Event(event.event_id, event.portfolio_id, event.run_id,
                                            event.kind, event.occurred_at_ms, event.source, payload))

        base = _journal()
        d = _engine(_Foreign(base.filename)).step(_ctx())
        assert d.rationale == "journal_persist_failed" and d.journal_event_id is None

    def test_replay_of_same_step_is_rejected_without_id(self):
        """Stesso run/timestamp/simbolo: l'evento esiste con altro claim -> nessun id."""
        j = _journal()
        eng = _engine(j)
        first = eng.step(_ctx())
        second = eng.step(_ctx())
        assert first.journal_event_id is not None
        assert second.rationale == "journal_persist_failed" and second.journal_event_id is None
        assert len(_events(j)) == 1

    def test_append_durable_return_values(self):
        j = _journal()
        eng = _engine(j)
        out = eng._append_durable(_open_decision(), _ctx())
        assert isinstance(out, str) and out == _events(j)[0].event_id
        eng.journal = None
        assert eng._append_durable(_open_decision(), _ctx(ts=TS + 1)) is None


# ---------------------------------------------------------------------------
# analista ostile: l'id lo assegna SOLO il motore
# ---------------------------------------------------------------------------

class TestHostileAnalystCannotInjectAnId:
    def test_no_trade_with_forged_id_is_cleaned(self):
        j = _journal()
        eng = _engine(j, _Scripted(lambda c: BrainDecision(
            kind=DecisionKind.NO_TRADE, rationale="DeepSeek: condizioni non sufficientemente chiare",
            sources=["deepseek:mock"], occurred_at_ms=c.timestamp_ms, journal_event_id=FORGED)))
        d = eng.step(_ctx())
        assert d.kind == DecisionKind.NO_TRADE
        assert d.journal_event_id is None

    def test_hold_with_forged_id_is_cleaned(self):
        j = _journal()
        eng = _engine(j, _Scripted(lambda c: BrainDecision(
            kind=DecisionKind.HOLD, rationale="DeepSeek: mantenere, nessuna nuova azione",
            sources=["deepseek:mock"], occurred_at_ms=c.timestamp_ms, journal_event_id=FORGED)))
        d = eng.step(_ctx())
        assert d.kind == DecisionKind.HOLD
        assert d.journal_event_id is None

    def test_open_with_forged_id_gets_the_real_one(self):
        j = _journal()
        eng = _engine(j, _Scripted(lambda c: _open_decision(journal_event_id=FORGED)))
        d = eng.step(_ctx())
        assert d.status == ProposalStatus.APPROVED
        assert d.journal_event_id != FORGED
        assert d.journal_event_id == _events(j)[0].event_id

    def test_risk_rejected_open_with_forged_id_is_cleaned(self):
        """OPEN respinto dal risk gate (leva oltre il limite): niente id, anche se iniettato."""
        j = _journal()

        def hostile(c):
            d = _open_decision(journal_event_id=FORGED)
            d.proposal = OpenProposal(symbol=c.symbol, side=1, entry_price=c.price,
                                      stop_price=c.price * Decimal("0.98"), leverage=100,
                                      rationale="deepseek:analysis", confidence=0.9,
                                      originating_ai="deepseek", context_hash="h")
            return d
        d = _engine(j, _Scripted(hostile)).step(_ctx())
        assert d.status != ProposalStatus.APPROVED
        assert d.journal_event_id is None


# ---------------------------------------------------------------------------
# allowlist di symbol / regime / id
# ---------------------------------------------------------------------------

class TestAllowlists:
    @pytest.mark.parametrize("regime", ["TRENDING", "RANGING", "VOLATILE", "UNKNOWN"])
    def test_valid_regimes_are_stored_as_is(self, regime):
        j = _journal()
        _engine(j).step(_ctx(regime=regime))
        assert _events(j)[0].payload["regime"] == regime

    @pytest.mark.parametrize("regime", ["trending", "TRENDING; DROP TABLE", "x" * 500, ""])
    def test_hostile_regime_is_sanitized(self, regime):
        j = _journal()
        _engine(j).step(_ctx(regime=regime))
        raw = json.dumps(dict(_events(j)[0].payload))
        assert _events(j)[0].payload["regime"] == "UNKNOWN"
        assert "DROP" not in raw and "xxxx" not in raw

    @pytest.mark.parametrize("symbol", [
        "api_key=SECRET123", "btcusdt", "BTC USDT", "BTC\nUSDT", "-BTC", "A" * 33, "BTC<script>"])
    def test_hostile_symbol_is_sanitized(self, symbol):
        j = _journal()
        _engine(j).step(_ctx(symbol=symbol))
        raw = json.dumps(dict(_events(j)[0].payload))
        assert _events(j)[0].payload["symbol"] == "unknown"
        assert "SECRET123" not in raw and "script" not in raw

    @pytest.mark.parametrize("symbol", ["BTCUSDT", "BTC/USDT:USDT", "A" * 32, "1000PEPE_USDT"])
    def test_valid_symbols_are_stored_as_is(self, symbol):
        j = _journal()
        _engine(j).step(_ctx(symbol=symbol))
        assert _events(j)[0].payload["symbol"] == symbol

    @pytest.mark.parametrize("bad", ["", "has space", "x" * 129, 123, None, b"abc", "-lead", "a/b"])
    def test_normalize_drops_malformed_ids(self, bad):
        eng = _engine(_journal())
        d = _open_decision(status=ProposalStatus.APPROVED, journal_event_id=bad)
        assert eng._normalize(d).journal_event_id is None

    def test_normalize_keeps_a_wellformed_id_on_approved_open(self):
        eng = _engine(_journal())
        d = _open_decision(status=ProposalStatus.APPROVED, journal_event_id="brain-req-" + "a" * 32)
        assert eng._normalize(d).journal_event_id == "brain-req-" + "a" * 32

    def test_normalize_drops_the_id_when_not_approved_open(self):
        eng = _engine(_journal())
        for kw in (dict(status=ProposalStatus.REJECTED),
                   dict(status=ProposalStatus.DRAFT),
                   dict(kind=DecisionKind.NO_TRADE, status=ProposalStatus.REJECTED, proposal=None),
                   dict(kind=DecisionKind.HOLD, status=ProposalStatus.DRAFT, proposal=None)):
            d = _open_decision(journal_event_id="brain-req-" + "a" * 32, **kw)
            assert eng._normalize(d).journal_event_id is None, kw


# ---------------------------------------------------------------------------
# riesame delle posizioni: scritture extra non toccano l'id della decisione
# ---------------------------------------------------------------------------

class TestReevaluateDoesNotChangeTheId:
    def test_reevaluate_keeps_id_and_adds_no_second_event_for_it(self):
        j = _journal()
        eng = _engine(j)
        ctx = _ctx()
        d = eng.step(ctx)
        before = d.journal_event_id
        eng.open_positions = [{"id": "p1"}]
        eng._reevaluate_positions(ctx, d)
        assert d.journal_event_id == before
        assert [e.event_id for e in _events(j)].count(before) == 1
        assert j.verify_chain()[0] >= 1
