"""Regression: V2 partial fills use ROUND_DOWN; final closes use HALF_EVEN.

A real partial from paper_scale must not disappear from Trade/learning because
outcomes.py incorrectly applies the final-close rounding contract.
"""
from decimal import Decimal as D, ROUND_DOWN, ROUND_HALF_EVEN

from backend.tests.test_brain_f7_outcomes import RUN, T_OPEN, _hand, _journal, _open
from backend.v3.events import Event
from backend.v3.executor.paper_close import close_paper
from backend.v3.executor.paper_scale import reduce_paper
from backend.v3.outcomes import extract_outcomes


def _real_partial_and_final():
    j = _journal()
    pid = _open(
        j,
        _hand(side=1, entry="100.1234567", stop="99", qty="1.234",
              margin="100", lev=20, symbol="BTCUSDT"),
        portfolio="brain", run=RUN, now=T_OPEN,
    )
    partial = reduce_paper(
        portfolio_id="brain", run_id=RUN, position_id=pid,
        fraction=D("0.35"), exit_price=D("102.9876543"),
        reason="take_profit", fee_bps=D(6), journal=j,
        quantity_step=D("0.001"), now_ms=T_OPEN + 60_000,
    )
    close_paper(
        portfolio_id="brain", run_id=RUN, position_id=pid,
        exit_price=D("103.1"), reason="brain_close", fee_bps=6,
        journal=j, now_ms=T_OPEN + 120_000,
    )
    return j, partial


def test_real_v2_partial_and_final_are_both_verified():
    j, partial = _real_partial_and_final()
    # Prove that producer rounding differs from the legacy final-close rule.
    gross = (D(partial["exit_price"]) - D(partial["entry_price"])) * D(partial["quantity"])
    assert D(partial["gross_pnl"]) == gross.quantize(D("1e-8"), rounding=ROUND_DOWN)
    assert D(partial["gross_pnl"]) != gross.quantize(D("1e-8"), rounding=ROUND_HALF_EVEN)

    rep = extract_outcomes(j, "brain", RUN)
    assert not rep.skipped
    assert len(rep.outcomes) == 2
    assert not rep.open_position_ids
    events = j.list_run("brain", RUN)
    expected = sum((D(e.event.payload["realized_pnl"]) for e in events
                    if e.event.kind in ("paper_reduce", "paper_close")), D(0))
    assert sum((o.realized_pnl for o in rep.outcomes), D(0)) == expected


def test_corrupted_real_partial_is_still_rejected():
    original, _ = _real_partial_and_final()
    damaged = _journal()
    for se in original.list_run("brain", RUN):
        e = se.event
        payload = e.payload
        if e.kind == "paper_reduce":
            payload = dict(payload, fees="999.00000000")
        damaged.append(Event(e.event_id, e.portfolio_id, e.run_id, e.kind,
                             e.occurred_at_ms, e.source, payload))
    rep = extract_outcomes(damaged, "brain", RUN)
    assert len(rep.outcomes) == 1
    assert [s.code for s in rep.skipped] == ["inconsistent_close"]
