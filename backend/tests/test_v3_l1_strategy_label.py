"""L1 — etichetta della strategia: regola unica, motore, journal, esiti.

Standard (lezione del 4/11): controllo che riesce con input validi, stati ESATTI, input
ostili (tipi sbagliati ma numericamente validi, testo che prova a entrare nel journal),
oracolo indipendente per la regola dell'etichetta, percorso completo coi produttori veri
(BrainEngine -> execute_paper -> close_paper -> extract_outcomes). Nessuna rete, nessun orologio.
"""
from __future__ import annotations

import dataclasses
import json
import os
import random
import tempfile
from decimal import Decimal

import pytest

from backend.v3.brain_f2.analyst import Analyst, MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import (
    BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus,
)
from backend.v3.brain_f2.engine import (
    BrainEngine, BrainPortfolioSnapshot, _ALLOWED_REGIMES, _policy_hash,
)
from backend.v3.features.regime import REGIME_LABELS
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.events import Event, EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.executor.paper_close import close_paper
from backend.v3.learning.expectancy import cell_stats
from backend.v3.outcomes import REGIMES, SCHEMA_VERSION, TradeOutcome, extract_outcomes
from backend.v3.risk import RiskPolicy, RiskQuote
from backend.v3.strategy_label import (
    AI_PREFIX, STRATEGY_ORIGINS, is_valid_strategy_id, normalize_label,
)

D = Decimal
RUN = "r-l1"
TS_DEC = 1_700_000_000_000
T_OPEN = 1_700_000_001_000
T_CLOSE = 1_700_000_061_000
OLD_KEYS = {"kind", "status", "rationale", "sources", "claim", "symbol", "regime"}


# ---------------------------------------------------------------------------
# 1. la regola unica
# ---------------------------------------------------------------------------

def _oracle(sid, origin, allowed):
    """Lettura indipendente della regola (carattere per carattere, niente regex)."""
    if type(origin) is not str or origin not in ("library", "ai_proposed"):
        return ("", "")
    if type(sid) is not str or not 1 <= len(sid) <= 32:
        return ("", "")
    up = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if sid[0] not in up:
        return ("", "")
    if any(c not in up + "0123456789_" for c in sid):
        return ("", "")
    if origin == "ai_proposed":
        return (sid, origin) if sid.startswith("AI_") and len(sid) > 3 else ("", "")
    if sid.startswith("AI_"):
        return ("", "")
    if allowed is not None and sid not in allowed:
        return ("", "")
    return (sid, origin)


class TestNormalizeLabel:
    @pytest.mark.parametrize("sid,origin,allowed,expected", [
        ("S07", "library", frozenset({"S07"}), ("S07", "library")),
        ("S07", "library", None, ("S07", "library")),                      # membership non richiesta
        ("S07", "library", frozenset({"S05"}), ("", "")),                  # non nell'elenco
        ("S07", "library", frozenset(), ("", "")),                         # elenco vuoto scarta tutto
        ("AI_BREAKOUT_1", "ai_proposed", frozenset(), ("AI_BREAKOUT_1", "ai_proposed")),
        ("AI_X", "ai_proposed", None, ("AI_X", "ai_proposed")),
        ("AI_", "ai_proposed", None, ("", "")),                            # solo il prefisso
        ("S07", "ai_proposed", None, ("", "")),                            # manca AI_
        ("AI_S07", "library", None, ("", "")),                             # AI_ non è libreria
        ("A" * 32, "library", None, ("A" * 32, "library")),                # 32 ok
        ("A" * 33, "library", None, ("", "")),                             # 33 no
        ("", "library", None, ("", "")),
        ("s07", "library", None, ("", "")),                                # minuscolo
        ("S 07", "library", None, ("", "")),
        ("S07\n", "library", None, ("", "")),                              # newline finale
        ("S07 ", "library", None, ("", "")),
        ("С" + "07", "library", None, ("", "")),                      # 'С' cirillica
        ("07", "library", None, ("", "")),                                 # inizia con cifra
        ("_S07", "library", None, ("", "")),
        ("S07", "LIBRARY", None, ("", "")),
        ("S07", "library ", None, ("", "")),
        ("S07", "", None, ("", "")),
        ("S07", "ai", None, ("", "")),
        ("S07", None, None, ("", "")),
        (None, "library", None, ("", "")),
        (None, None, None, ("", "")),
    ])
    def test_table(self, sid, origin, allowed, expected):
        assert normalize_label(sid, origin, allowed) == expected

    def test_exact_types_only(self):
        class S(str):
            pass
        for bad in (True, False, 7, 1.5, b"S07", bytearray(b"S07"), S("S07"), ["S07"], {"S": 7}, object()):
            assert normalize_label(bad, "library", None) == ("", "")
            assert normalize_label("S07", bad, None) == ("", "")
        assert normalize_label("S07", S("library"), None) == ("", "")      # origin sottoclasse

    def test_is_valid_strategy_id(self):
        assert is_valid_strategy_id("S07") and is_valid_strategy_id("AI_X")
        assert not is_valid_strategy_id("s07") and not is_valid_strategy_id(None)
        assert not is_valid_strategy_id("S07\n")

    def test_constants(self):
        assert STRATEGY_ORIGINS == {"library", "ai_proposed"} and AI_PREFIX == "AI_"

    def test_against_independent_oracle_on_random_strings(self):
        rnd = random.Random(20261105)
        alphabet = ["S", "A", "I", "_", "0", "7", "9", "s", "a", "-", " ", "\n", "С", "Z"]
        allowed_sets = [None, frozenset(), frozenset({"S07", "S05", "AB", "A_1"})]
        seen_ok = 0
        for _ in range(20000):
            n = rnd.choice([0, 1, 2, 3, 4, 5, 31, 32, 33])
            sid = "".join(rnd.choice(alphabet) for _ in range(n))
            if rnd.random() < 0.3:
                sid = rnd.choice(["S07", "S05", "AB", "A_1", "AI_X", "AI_", "AI_A1"])
            origin = rnd.choice(["library", "ai_proposed", "library", "x", "", None])
            allowed = rnd.choice(allowed_sets)
            want = _oracle(sid, origin, allowed)
            assert normalize_label(sid, origin, allowed) == want, (sid, origin, allowed)
            seen_ok += want != ("", "")
        assert seen_ok > 500          # il campione contiene molti casi validi, non solo scarti


# ---------------------------------------------------------------------------
# helper comuni (produttori veri)
# ---------------------------------------------------------------------------

def _journal() -> EventJournal:
    j = EventJournal(os.path.join(tempfile.mkdtemp(), "journal.db"))
    j.init_schema()
    return j


class LabelAnalyst(Analyst):
    """Come il mock (apre long in trend), ma con l'etichetta scelta dal test."""

    def __init__(self, sid, sor, entry_factor="1"):
        self.sid, self.sor, self.entry_factor = sid, sor, D(entry_factor)

    def analyze(self, context, open_positions):
        prop = OpenProposal(
            symbol=context.symbol, side=1, entry_price=context.price * self.entry_factor,
            stop_price=context.price * D("0.98"), leverage=2, rationale="Mock trend following",
            confidence=0.6, originating_ai="deepseek", context_hash="mock",
            strategy_id=self.sid, strategy_origin=self.sor)
        return BrainDecision(kind=DecisionKind.OPEN, proposal=prop,
                             rationale="DeepSeek propone ingresso in trend", sources=["deepseek:mock"],
                             occurred_at_ms=context.timestamp_ms)


def _engine(journal, analyst, *, allowed=("S07", "S05"), run=RUN, **kw) -> BrainEngine:
    policy = RiskPolicy(D(".02"), D(".05"), D(".1"), D(".3"), D("450"), D("16"), D(".5"))
    snapshot = BrainPortfolioSnapshot(D("1000"), D("1000"), D("0"), D("0"))
    params = {"exchange_leverage_limit": 10, "quantity_step": D(".001"),
              "minimum_notional": D("5"), "maintenance_fraction": D(".004"),
              "market_data_fresh": True, "paused": False, "daily_loss_latched": False}
    extra = {} if allowed is ... else {"allowed_strategy_ids": allowed}
    extra.update(kw)
    return BrainEngine(
        analyst=analyst, reviewer=MockClaudeReviewer(always_approve=True),
        risk_policy=policy, portfolio_snapshot=snapshot, market_params=params,
        journal=journal, portfolio_id="brain", run_id=run,
        policy_verifier=lambda m, p: True,
        policy_mandate={"version": "l1", "approved_by": "operator", "approved": True,
                        "portfolio_id": "brain", "run_id": run, "policy_hash": _policy_hash(policy)},
        **extra)


def _step(j, analyst, *, ts=TS_DEC, allowed=("S07", "S05"), regime="TRENDING"):
    return _engine(j, analyst, allowed=allowed).step(MarketContext("BTCUSDT", D("50000"), ts, regime))


def _decision_payload(j, eid):
    found = [s.event.payload for s in j.list_run("brain", RUN) if s.event.event_id == eid]
    assert len(found) == 1
    return found[0]


def _all_decision_payloads(j):
    return [s.event.payload for s in j.list_run("brain", RUN) if s.event.kind == "brain_decision"]


def _open_close(j, decision, *, price="51000"):
    pid = execute_paper(decision, portfolio_id="hawk", run_id=RUN, journal=j, now_ms=T_OPEN).position_id
    close_paper(portfolio_id="hawk", run_id=RUN, position_id=pid, exit_price=D(price),
                reason="brain_close", fee_bps=6, journal=j, now_ms=T_CLOSE)
    return pid


def _one(j) -> TradeOutcome:
    rep = extract_outcomes(j, "hawk", RUN)
    assert len(rep.outcomes) == 1 and rep.skipped == (), rep
    return rep.outcomes[0]


# ---------------------------------------------------------------------------
# 2. motore e journal
# ---------------------------------------------------------------------------

class TestEngine:
    def test_control_labeled_open_reaches_the_journal(self):
        j = _journal()
        d = _step(j, LabelAnalyst("S07", "library"))
        assert (d.kind, d.status) == (DecisionKind.OPEN, ProposalStatus.APPROVED)     # controllo
        assert (d.proposal.strategy_id, d.proposal.strategy_origin) == ("S07", "library")
        p = _decision_payload(j, d.journal_event_id)
        assert p["strategy_id"] == "S07" and p["strategy_origin"] == "library"
        assert set(p) == OLD_KEYS | {"strategy_id", "strategy_origin"}

    def test_ai_proposed_label(self):
        j = _journal()
        d = _step(j, LabelAnalyst("AI_RANGE_FADE", "ai_proposed"), allowed=())
        p = _decision_payload(j, d.journal_event_id)
        assert (p["strategy_id"], p["strategy_origin"]) == ("AI_RANGE_FADE", "ai_proposed")

    def test_unlabeled_decision_writes_exactly_the_old_payload(self):
        j = _journal()
        d = _step(j, MockDeepSeekAnalyst())
        assert d.kind == DecisionKind.OPEN and d.status == ProposalStatus.APPROVED
        assert set(_decision_payload(j, d.journal_event_id)) == OLD_KEYS
        assert (d.proposal.strategy_id, d.proposal.strategy_origin) == (None, None)

    def test_unlabeled_hash_is_unchanged_by_the_engine_default(self):
        # stesso input con e senza elenco dell'engine: l'evento senza etichetta e' identico
        j1, j2 = _journal(), _journal()
        d1 = _step(j1, MockDeepSeekAnalyst(), allowed=...)
        d2 = _step(j2, MockDeepSeekAnalyst(), allowed=("S07",))
        p1, p2 = _decision_payload(j1, d1.journal_event_id), _decision_payload(j2, d2.journal_event_id)
        p1.pop("claim"), p2.pop("claim")                      # uuid casuale per scrittura
        assert p1 == p2

    @pytest.mark.parametrize("sid,sor", [
        ("S99", "library"),            # non nell'elenco
        ("s07", "library"), ("S07\n", "library"), ("S 07", "library"),
        ("S07", "LIBRARY"), ("S07", None), (None, "library"), ("S07", "ai_proposed"),
        ("AI_S07", "library"), ("AI_", "ai_proposed"),
        (7, "library"), (True, "library"), (b"S07", "library"),
        ("S07; DROP TABLE", "library"), ("x" * 5000, "library"),
    ])
    def test_bad_label_is_dropped_and_the_trade_goes_on(self, sid, sor):
        j = _journal()
        d = _step(j, LabelAnalyst(sid, sor))
        assert (d.kind, d.status) == (DecisionKind.OPEN, ProposalStatus.APPROVED)
        assert (d.proposal.strategy_id, d.proposal.strategy_origin) == (None, None)
        assert set(_decision_payload(j, d.journal_event_id)) == OLD_KEYS

    def test_library_label_needs_the_engine_allowlist(self):
        j = _journal()
        d = _step(j, LabelAnalyst("S07", "library"), allowed=...)       # nessun elenco
        assert d.proposal.strategy_id is None
        assert set(_decision_payload(j, d.journal_event_id)) == OLD_KEYS
        d2 = _step(_journal(), LabelAnalyst("AI_X", "ai_proposed"), allowed=...)   # ai_proposed: senza elenco
        assert d2.proposal.strategy_id == "AI_X"

    def test_rejected_decisions_carry_no_label(self):
        j = _journal()
        d = _step(j, LabelAnalyst("S07", "library", entry_factor="1.5"))     # prezzo lontano dal mercato
        assert d.kind == DecisionKind.NO_TRADE and d.status == ProposalStatus.REJECTED
        assert d.proposal is None
        for p in _all_decision_payloads(j):
            assert "strategy_id" not in p and "strategy_origin" not in p

    def test_free_text_never_reaches_the_journal(self):
        j = _journal()
        _step(j, LabelAnalyst("IGNORE_PREVIOUS_RULES", "library"), allowed=("S07",))
        blob = json.dumps(_all_decision_payloads(j))
        assert "IGNORE" not in blob

    @pytest.mark.parametrize("bad", ["S07", "SAB", "A", b"S07", 5, ["s07"], ["S07", 3], [None], [True], ["S07\n"], object()])
    def test_constructor_rejects_bad_allowlists(self, bad):
        with pytest.raises(ValueError) as e:
            _engine(_journal(), MockDeepSeekAnalyst(), allowed=bad)
        assert str(e.value) == "invalid_strategy_ids"

    def test_constructor_accepts_iterables(self):
        e = _engine(_journal(), MockDeepSeekAnalyst(), allowed=(s for s in ("S07", "S05")))
        assert e.allowed_strategy_ids == frozenset({"S07", "S05"})
        assert _engine(_journal(), MockDeepSeekAnalyst(), allowed=[]).allowed_strategy_ids == frozenset()
        assert _engine(_journal(), MockDeepSeekAnalyst(), allowed=...).allowed_strategy_ids == frozenset()

    def test_old_constructor_call_still_works(self):
        policy = RiskPolicy(D(".02"), D(".05"), D(".1"), D(".3"), D("450"), D("16"), D(".5"))
        e = BrainEngine(analyst=MockDeepSeekAnalyst(), reviewer=MockClaudeReviewer(always_approve=True),
                        risk_policy=policy,
                        portfolio_snapshot=BrainPortfolioSnapshot(D("1000"), D("1000"), D("0"), D("0")),
                        journal=_journal(), run_id=RUN)
        assert e.allowed_strategy_ids == frozenset()


# ---------------------------------------------------------------------------
# 3. esiti: l'etichetta arriva nel TradeOutcome
# ---------------------------------------------------------------------------

def _raw_decision(j, eid, over=None, *, ts=TS_DEC, symbol="BTCUSDT", kind="OPEN", status="APPROVED"):
    p = {"kind": kind, "status": status, "rationale": "risk_quote_ok", "sources": [],
         "claim": "c", "symbol": symbol, "regime": "TRENDING"}
    p.update(over or {})
    j.append(Event(eid, "brain", RUN, "brain_decision", ts, "brain_f2_engine", p))


def _hand(link, *, symbol="BTCUSDT"):
    prop = OpenProposal(symbol=symbol, side=1, entry_price=D("30000"), stop_price=D("29000"),
                        leverage=5, rationale="deepseek:analysis", confidence=0.75,
                        originating_ai="deepseek", context_hash="h")
    quote = RiskQuote(allowed=True, reason="ok", quantity=D("0.01"), notional=D("300"),
                      margin=D("60"), worst_case_loss_estimate=D("30"), risk_budget=D("450"))
    return BrainDecision(kind=DecisionKind.OPEN, proposal=prop, risk_quote=quote,
                         rationale="deepseek:analysis", sources=["deepseek:analysis"],
                         occurred_at_ms=TS_DEC, status=ProposalStatus.APPROVED, journal_event_id=link)


class TestOutcomes:
    def test_schema_version_is_2_and_fields_exist(self):
        assert SCHEMA_VERSION == 2
        names = {f.name for f in dataclasses.fields(TradeOutcome)}
        assert {"strategy_id", "strategy_origin"} <= names

    def test_control_full_chain_library(self):
        j = _journal()
        d = _step(j, LabelAnalyst("S07", "library"))
        _open_close(j, d)
        o = _one(j)
        assert (o.link_status, o.strategy_id, o.strategy_origin) == ("linked", "S07", "library")
        assert o.decision_regime == "TRENDING" and o.schema_version == 2
        dct = o.to_dict()
        assert dct["strategy_id"] == "S07" and dct["strategy_origin"] == "library"
        assert json.loads(json.dumps(dct)) == dct

    def test_full_chain_ai_proposed(self):
        j = _journal()
        _open_close(j, _step(j, LabelAnalyst("AI_PULLBACK", "ai_proposed"), allowed=()))
        o = _one(j)
        assert (o.strategy_id, o.strategy_origin) == ("AI_PULLBACK", "ai_proposed")

    def test_unlabeled_decision_gives_empty_label(self):
        j = _journal()
        _open_close(j, _step(j, MockDeepSeekAnalyst()))
        o = _one(j)
        assert (o.link_status, o.strategy_id, o.strategy_origin) == ("linked", "", "")

    def test_unlinked_position_gives_empty_label(self):
        j = _journal()
        _open_close(j, _hand(None))
        o = _one(j)
        assert (o.link_status, o.strategy_id, o.strategy_origin) == ("unlinked", "", "")

    def test_dangling_gives_empty_label(self):
        j = _journal()
        _open_close(j, _hand("brain-req-" + "a" * 32))
        o = _one(j)
        assert (o.link_status, o.strategy_id, o.strategy_origin) == ("dangling", "", "")

    LABEL_CASES = [
        ({"strategy_id": "S07", "strategy_origin": "library"}, ("S07", "library")),
        ({"strategy_id": "S99", "strategy_origin": "library"}, ("S99", "library")),   # membership: non qui
        ({"strategy_id": "AI_X", "strategy_origin": "ai_proposed"}, ("AI_X", "ai_proposed")),
        ({"strategy_id": "S07"}, ("", "")),                                           # mezza etichetta
        ({"strategy_origin": "library"}, ("", "")),
        ({"strategy_id": "s07", "strategy_origin": "library"}, ("", "")),
        ({"strategy_id": "S07", "strategy_origin": "other"}, ("", "")),
        ({"strategy_id": 7, "strategy_origin": "library"}, ("", "")),
        ({"strategy_id": True, "strategy_origin": "library"}, ("", "")),
        ({"strategy_id": "AI_X", "strategy_origin": "library"}, ("", "")),
        ({"strategy_id": "S07", "strategy_origin": "ai_proposed"}, ("", "")),
        ({"strategy_id": ["S07"], "strategy_origin": ["library"]}, ("", "")),
        ({"strategy_id": "S07\n", "strategy_origin": "library"}, ("", "")),
        ({"strategy_id": None, "strategy_origin": None}, ("", "")),
    ]

    @pytest.mark.parametrize("extra,expected", LABEL_CASES)
    def test_journal_payload_is_revalidated_when_read(self, extra, expected):
        j = _journal()
        _raw_decision(j, "dec-1", extra)
        _open_close(j, _hand("dec-1"))
        o = _one(j)
        assert o.link_status == "linked"
        assert (o.strategy_id, o.strategy_origin) == expected

    @pytest.mark.parametrize("kw,status", [
        ({"kind": "NO_TRADE", "status": "REJECTED"}, "wrong_decision"),
        ({"kind": "OPEN", "status": "RISK_REJECTED"}, "wrong_decision"),
        ({"symbol": "ETHUSDT"}, "symbol_mismatch"),
        ({"ts": T_OPEN + 5_000}, "decision_after_open"),
    ])
    def test_label_is_trusted_only_when_linked(self, kw, status):
        j = _journal()
        _raw_decision(j, "dec-1", {"strategy_id": "S07", "strategy_origin": "library"}, **kw)
        _open_close(j, _hand("dec-1"))
        o = _one(j)
        assert o.link_status == status
        assert (o.strategy_id, o.strategy_origin) == ("", "")

    def test_two_strategies_two_outcomes(self):
        j = _journal()
        d1 = _step(j, LabelAnalyst("S07", "library"), ts=TS_DEC)
        d2 = _step(j, LabelAnalyst("S05", "library"), ts=TS_DEC + 1000)
        for n, d in enumerate((d1, d2)):
            pid = execute_paper(d, portfolio_id="hawk", run_id=RUN, journal=j, now_ms=T_OPEN + n).position_id
            close_paper(portfolio_id="hawk", run_id=RUN, position_id=pid, exit_price=D("51000"),
                        reason="brain_close", fee_bps=6, journal=j, now_ms=T_CLOSE + n)
        rep = extract_outcomes(j, "hawk", RUN)
        assert sorted(o.strategy_id for o in rep.outcomes) == ["S05", "S07"]

    def test_deterministic_extraction(self):
        j = _journal()
        _open_close(j, _step(j, LabelAnalyst("S07", "library")))
        a = extract_outcomes(j, "hawk", RUN)
        b = extract_outcomes(j, "hawk", RUN)
        assert a == b and a.outcomes[0].to_dict() == b.outcomes[0].to_dict()


# ---------------------------------------------------------------------------
# 4. il tabellone: la chiave di cella per strategia funziona
# ---------------------------------------------------------------------------

class TestScoreboardKey:
    def test_cell_stats_groups_by_strategy_regime_side(self):
        j = _journal()
        _open_close(j, _step(j, LabelAnalyst("S07", "library")))
        base = _one(j)
        day = 86_400_000
        outs = []
        for i in range(6):
            sid = ("S07", "S05")[i % 2]
            outs.append(dataclasses.replace(
                base, position_id=f"p{i}", strategy_id=sid, strategy_origin="library",
                opened_at_ms=base.opened_at_ms + i * day, closed_at_ms=base.closed_at_ms + i * day))
        cells = cell_stats(outs, min_trades=1, min_days=2, confidence=D("0.9"), n_boot=200, seed=1,
                           key=lambda o: (o.strategy_id, o.decision_regime, o.side))
        assert {c.key for c in cells} == {("S07", "TRENDING", 1), ("S05", "TRENDING", 1)}
        assert sorted(c.n for c in cells) == [3, 3]


# ---------------------------------------------------------------------------
# 5. vocabolario dei regimi: le 6 etichette di P8 sono registrabili e rileggibili
# ---------------------------------------------------------------------------

class TestRegimeVocabulary:
    OLD = {"TRENDING", "RANGING", "VOLATILE", "UNKNOWN"}

    def test_engine_and_outcomes_share_one_vocabulary(self):
        assert _ALLOWED_REGIMES == REGIMES                       # niente deriva fra scrittore e lettore
        assert self.OLD <= REGIMES                               # le 4 storiche restano
        assert set(REGIME_LABELS) <= REGIMES                     # le 6 di P8 ci sono tutte
        assert REGIMES == self.OLD | set(REGIME_LABELS)          # e nient'altro

    @pytest.mark.parametrize("regime", sorted(set(REGIME_LABELS)))
    def test_p8_regime_survives_decision_journal_and_outcome(self, regime):
        j = _journal()
        d = _step(j, LabelAnalyst("S07", "library"), regime=regime)
        # MockDeepSeek apre solo in TRENDING: qui il nostro analista apre in ogni regime
        assert (d.kind, d.status) == (DecisionKind.OPEN, ProposalStatus.APPROVED)
        assert _decision_payload(j, d.journal_event_id)["regime"] == regime
        _open_close(j, d)
        o = _one(j)
        assert (o.link_status, o.decision_regime, o.strategy_id) == ("linked", regime, "S07")

    @pytest.mark.parametrize("regime", ["trend_up", "TREND_UP ", "TREND-UP", "ALL", "REVERSAL_CANDIDATE", "", "x" * 40])
    def test_other_strings_still_become_unknown(self, regime):
        j = _journal()
        d = _step(j, LabelAnalyst("S07", "library"), regime=regime)
        assert _decision_payload(j, d.journal_event_id)["regime"] == "UNKNOWN"
