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
    return Event(
        event_id=f"brain_step.{seq}",
        portfolio_id=portfolio_id,
        run_id=run_id,
        kind="brain_step",
        occurred_at_ms=ts,
        source="brain_engine",
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
        assert "brain" in txt.lower() or "step" in txt.lower()
