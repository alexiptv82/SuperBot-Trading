"""F6 — Dashboard unificata: test offline.

Verifica build_summary / build_all_summaries / format_summary
usando EventJournal reali in directory temporanee.
Nessuna API esterna, nessuna scrittura fuori da tmpdir.
"""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest

from backend.v3.events import Event, EventJournal
from backend.v3.dashboard import (
    OpenPosition, ClosedTrade, PortfolioSummary,
    build_summary, build_all_summaries, format_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _journal(td: str) -> EventJournal:
    j = EventJournal(Path(td) / "j.sqlite")
    j.init_schema()
    return j


def _open_event(portfolio_id: str, run_id: str, position_id: str,
                symbol: str = "BTCUSDT", side: int = 1,
                fill_price: str = "50000", quantity: str = "0.01",
                margin_used: str = "50", leverage: int = 10,
                stop_price: str = "49000", ts: int = 1_700_000_000_000) -> Event:
    return Event(
        event_id=f"paper_open.{position_id}",
        portfolio_id=portfolio_id,
        run_id=run_id,
        kind="paper_open",
        occurred_at_ms=ts,
        source="executor.paper",
        payload={
            "position_id": position_id,
            "symbol": symbol,
            "side": side,
            "fill_price": fill_price,
            "quantity": quantity,
            "margin_used": margin_used,
            "leverage": leverage,
            "stop_price": stop_price,
        },
    )


def _close_event(portfolio_id: str, run_id: str, position_id: str,
                 symbol: str = "BTCUSDT", realized_pnl: str = "12.5",
                 ts: int = 1_700_000_001_000) -> Event:
    return Event(
        event_id=f"paper_close.{position_id}",
        portfolio_id=portfolio_id,
        run_id=run_id,
        kind="paper_close",
        occurred_at_ms=ts,
        source="executor.paper",
        payload={
            "position_id": position_id,
            "symbol": symbol,
            "realized_pnl": realized_pnl,
        },
    )


def _brain_event(portfolio_id: str, run_id: str, seq: int,
                 kind: str = "OPEN", status: str = "APPROVED",
                 ts: int = 1_700_000_002_000) -> Event:
    # Stessa forma dell'evento scritto da BrainEngine._append_durable
    # (kind="brain_decision", source="brain_f2_engine"). Il test
    # TestRealProducers sotto verifica che resti allineata al produttore vero.
    return Event(
        event_id=f"brain_decision.{seq}",
        portfolio_id=portfolio_id,
        run_id=run_id,
        kind="brain_decision",
        occurred_at_ms=ts,
        source="brain_f2_engine",
        payload={"kind": kind, "status": status},
    )


# ---------------------------------------------------------------------------
# TestEmptyJournal
# ---------------------------------------------------------------------------

class TestEmptyJournal:
    def test_empty_journal_produces_zero_summary(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            s = build_summary(j, "hawk", "run1")
        assert s.total_events == 0
        assert s.open_positions == ()
        assert s.closed_trades == ()
        assert s.realized_pnl == Decimal("0")
        assert s.last_event_ms is None

    def test_empty_summary_has_correct_portfolio_id(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            s = build_summary(j, "bull", "run-x")
        assert s.portfolio_id == "bull"
        assert s.run_id == "run-x"

    def test_empty_summary_brain_counters_zero(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            s = build_summary(j, "brain", "r1")
        assert s.brain_steps == 0
        assert s.brain_approvals == 0

    def test_build_all_summaries_empty(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            summaries = build_all_summaries(j, "run1")
        assert len(summaries) == 3
        assert all(s.total_events == 0 for s in summaries)
        pids = [s.portfolio_id for s in summaries]
        assert set(pids) == {"hawk", "bull", "brain"}


# ---------------------------------------------------------------------------
# TestOpenPosition
# ---------------------------------------------------------------------------

class TestOpenPosition:
    def test_single_open_appears_in_summary(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_open_event("hawk", "r1", "pos001"))
            s = build_summary(j, "hawk", "r1")
        assert len(s.open_positions) == 1
        assert s.open_positions[0].position_id == "pos001"
        assert s.open_positions[0].symbol == "BTCUSDT"

    def test_open_side_long(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_open_event("hawk", "r1", "pos002", side=1))
            s = build_summary(j, "hawk", "r1")
        assert s.open_positions[0].side == 1

    def test_open_side_short(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_open_event("hawk", "r1", "pos003", side=-1))
            s = build_summary(j, "hawk", "r1")
        assert s.open_positions[0].side == -1

    def test_open_fill_price_decimal(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_open_event("hawk", "r1", "pos004", fill_price="49999.99"))
            s = build_summary(j, "hawk", "r1")
        assert s.open_positions[0].fill_price == Decimal("49999.99")

    def test_margin_in_use_sum(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_open_event("hawk", "r1", "pos005", margin_used="100",
                                 ts=1_700_000_000_000))
            j.append(_open_event("hawk", "r1", "pos006", margin_used="75",
                                 ts=1_700_000_000_001))
            s = build_summary(j, "hawk", "r1")
        assert s.margin_in_use == Decimal("175")

    def test_two_open_positions_total_events(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_open_event("bull", "r2", "posA", ts=1_700_000_000_000))
            j.append(_open_event("bull", "r2", "posB", ts=1_700_000_000_001))
            s = build_summary(j, "bull", "r2")
        assert s.total_events == 2
        assert len(s.open_positions) == 2


# ---------------------------------------------------------------------------
# TestClosePosition
# ---------------------------------------------------------------------------

class TestClosePosition:
    def test_close_removes_from_open(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_open_event("hawk", "r1", "pos007", ts=1_000))
            j.append(_close_event("hawk", "r1", "pos007", ts=2_000))
            s = build_summary(j, "hawk", "r1")
        assert len(s.open_positions) == 0
        assert len(s.closed_trades) == 1

    def test_close_pnl_accumulated(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_open_event("hawk", "r1", "pos008", ts=1_000))
            j.append(_close_event("hawk", "r1", "pos008",
                                  realized_pnl="12.5", ts=2_000))
            s = build_summary(j, "hawk", "r1")
        assert s.realized_pnl == Decimal("12.5")

    def test_close_negative_pnl(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_open_event("hawk", "r1", "pos009", ts=1_000))
            j.append(_close_event("hawk", "r1", "pos009",
                                  realized_pnl="-8.3", ts=2_000))
            s = build_summary(j, "hawk", "r1")
        assert s.realized_pnl == Decimal("-8.3")

    def test_multiple_close_pnl_sum(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            for i, pnl in enumerate(["5.0", "-2.0", "10.0"], start=10):
                pid = f"pos0{i}"
                j.append(_open_event("hawk", "r1", pid, ts=i * 1000))
                j.append(_close_event("hawk", "r1", pid,
                                      realized_pnl=pnl, ts=i * 1000 + 500))
            s = build_summary(j, "hawk", "r1")
        assert s.realized_pnl == Decimal("13.0")
        assert len(s.closed_trades) == 3

    def test_close_without_prior_open_still_recorded(self):
        """paper_close senza paper_open precedente non crasha."""
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_close_event("hawk", "r1", "ghost", realized_pnl="0", ts=1_000))
            s = build_summary(j, "hawk", "r1")
        assert len(s.closed_trades) == 1


# ---------------------------------------------------------------------------
# TestBrainSteps
# ---------------------------------------------------------------------------

class TestBrainSteps:
    def test_brain_steps_counted(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_brain_event("brain", "r1", 1, kind="OPEN", status="APPROVED"))
            j.append(_brain_event("brain", "r1", 2, kind="NO_TRADE", status="NO_TRADE"))
            s = build_summary(j, "brain", "r1")
        assert s.brain_steps == 2

    def test_brain_approvals_counted(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_brain_event("brain", "r1", 1, kind="OPEN", status="APPROVED"))
            j.append(_brain_event("brain", "r1", 2, kind="OPEN", status="APPROVED"))
            j.append(_brain_event("brain", "r1", 3, kind="NO_TRADE", status="NO_TRADE"))
            s = build_summary(j, "brain", "r1")
        assert s.brain_approvals == 2

    def test_brain_no_approvals_when_no_open(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_brain_event("brain", "r1", 1, kind="NO_TRADE", status="NO_TRADE"))
            s = build_summary(j, "brain", "r1")
        assert s.brain_approvals == 0


# ---------------------------------------------------------------------------
# TestLastEventMs
# ---------------------------------------------------------------------------

class TestLastEventMs:
    def test_last_event_ms_single_event(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_open_event("hawk", "r1", "posX", ts=1_700_000_000_000))
            s = build_summary(j, "hawk", "r1")
        assert s.last_event_ms == 1_700_000_000_000

    def test_last_event_ms_is_max(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_open_event("hawk", "r1", "posY", ts=1_000))
            j.append(_open_event("hawk", "r1", "posZ", ts=9_999))
            s = build_summary(j, "hawk", "r1")
        assert s.last_event_ms == 9_999


# ---------------------------------------------------------------------------
# TestFormatSummary
# ---------------------------------------------------------------------------

class TestFormatSummary:
    def test_format_contains_portfolio_id(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            s = build_summary(j, "hawk", "r1")
        txt = format_summary(s)
        assert "HAWK" in txt

    def test_format_contains_run_id(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            s = build_summary(j, "hawk", "run-abc")
        txt = format_summary(s)
        assert "run-abc" in txt

    def test_format_contains_pnl(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_open_event("hawk", "r1", "posW", ts=1_000))
            j.append(_close_event("hawk", "r1", "posW",
                                  realized_pnl="7.5", ts=2_000))
            s = build_summary(j, "hawk", "r1")
        txt = format_summary(s)
        assert "7.5" in txt

    def test_format_open_position_shown(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_open_event("bull", "r1", "pos_fmt",
                                 symbol="ETHUSDT", side=1, ts=1_000))
            s = build_summary(j, "bull", "r1")
        txt = format_summary(s)
        assert "ETHUSDT" in txt
        assert "OPEN" in txt

    def test_format_brain_steps_shown(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            j.append(_brain_event("brain", "r1", 1))
            s = build_summary(j, "brain", "r1")
        txt = format_summary(s)
        assert "brain steps : 1 (1 approvati)" in txt


# ---------------------------------------------------------------------------
# TestRealProducers — la dashboard deve leggere cio' che i moduli scrivono DAVVERO
# ---------------------------------------------------------------------------
# Gli altri test costruiscono gli eventi a mano. Questi usano i produttori veri
# (BrainEngine ed execute_paper): se un produttore cambia nome o forma
# dell'evento, qui si rompe subito invece di mostrare zeri in silenzio.

from backend.v3.brain_f2.analyst import MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import (
    BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus,
)
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot, _policy_hash
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.executor.paper import execute_paper
from backend.v3.risk import RiskPolicy, RiskQuote

_ENGINE_RUN = "r-f6-engine"


def _real_engine(journal: EventJournal) -> BrainEngine:
    """Motore configurato in modo valido: run_id e mandato coerenti.

    Senza run_id il motore risponde NO_TRADE('invalid_input') prima ancora di
    analizzare, quindi non scrive la decisione che vogliamo osservare.
    """
    policy = RiskPolicy(Decimal(".02"), Decimal(".05"), Decimal(".1"),
                        Decimal(".3"), Decimal("450"), Decimal("16"), Decimal(".5"))
    snapshot = BrainPortfolioSnapshot(Decimal("1000"), Decimal("1000"),
                                      Decimal("0"), Decimal("0"))
    params = {"exchange_leverage_limit": 10, "quantity_step": Decimal(".001"),
              "minimum_notional": Decimal("5"), "maintenance_fraction": Decimal(".004"),
              "market_data_fresh": True, "paused": False, "daily_loss_latched": False}
    return BrainEngine(
        analyst=MockDeepSeekAnalyst(),
        reviewer=MockClaudeReviewer(always_approve=True),
        risk_policy=policy, portfolio_snapshot=snapshot, market_params=params,
        journal=journal, portfolio_id="brain", run_id=_ENGINE_RUN,
        policy_verifier=lambda m, p: True,
        policy_mandate={"version": "f6-test", "approved_by": "operator",
                        "approved": True, "portfolio_id": "brain",
                        "run_id": _ENGINE_RUN,
                        "policy_hash": _policy_hash(policy)},
    )


class TestRealProducers:
    def test_dashboard_sees_real_brain_engine_decision(self):
        with TemporaryDirectory() as td:
            j = _journal(td)
            eng = _real_engine(j)
            decision = eng.step(MarketContext("BTCUSDT", Decimal("50000"),
                                              1_700_000_000_000, "TRENDING"))
            s = build_summary(j, "brain", _ENGINE_RUN)
        assert s.brain_steps == 1, "il motore ha scritto un evento che la dashboard non riconosce"
        # Il motore deve aver davvero ragionato (non fermarsi per input non valido):
        assert decision.rationale != "invalid_input"
        expected = int(decision.kind == DecisionKind.OPEN
                       and decision.status == ProposalStatus.APPROVED)
        assert s.brain_approvals == expected

    def test_dashboard_sees_real_execute_paper_open(self):
        proposal = OpenProposal(
            symbol="BTCUSDT", side=1, entry_price=Decimal("30000"),
            stop_price=Decimal("29000"), leverage=5, rationale="deepseek:analysis",
            confidence=0.75, originating_ai="deepseek", context_hash="abc123")
        quote = RiskQuote(allowed=True, reason="ok", quantity=Decimal("0.01"),
                          notional=Decimal("300"), margin=Decimal("60"),
                          worst_case_loss_estimate=Decimal("30"),
                          risk_budget=Decimal("450"))
        decision = BrainDecision(
            kind=DecisionKind.OPEN, proposal=proposal, risk_quote=quote,
            rationale="deepseek:analysis", sources=["deepseek:analysis"],
            occurred_at_ms=1_700_000_000_000, status=ProposalStatus.APPROVED)
        with TemporaryDirectory() as td:
            j = _journal(td)
            receipt = execute_paper(decision, portfolio_id="hawk", run_id="r-real",
                                    journal=j, now_ms=1_700_000_001_000)
            s = build_summary(j, "hawk", "r-real")
        assert len(s.open_positions) == 1
        pos = s.open_positions[0]
        assert pos.position_id == receipt.position_id
        assert pos.symbol == "BTCUSDT"
        assert pos.fill_price == receipt.fill_price
        assert pos.margin_used == Decimal("60")
        assert s.margin_in_use == Decimal("60")

    def test_no_producer_writes_paper_close_yet(self):
        """Documenta un buco noto: nessun modulo di backend/v3 scrive paper_close.

        Se questo test inizia a fallire, significa che e' stato aggiunto un
        esecutore di chiusura: aggiornare il contratto in dashboard.py e
        sostituire questo test con uno che usa il produttore vero.
        """
        from pathlib import Path as _P
        root = _P(__file__).resolve().parents[1] / "v3"
        writers = [
            str(p.relative_to(root)) for p in root.rglob("*.py")
            if p.name != "dashboard.py" and '"paper_close"' in p.read_text(encoding="utf-8")
        ]
        assert writers == [], f"paper_close ora ha un produttore: {writers}"
