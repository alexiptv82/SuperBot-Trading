"""RC79: all tests synthetic, read only, no external imports or network."""
import pytest
from v3.observability.post_trade_review import (
    ReviewDataError, aggregate_fills, review_positions,
)


def close(id=1, symbol="ARB", opened=1000, closed=2000, *, net=-12, margin=10,
          entry=0.16, exit=0.17, side=-1, partial=False, **kw):
    return dict(id=id, symbol=symbol, open_ms=opened, close_ms=closed,
                net=net, margin=margin, entry=entry, exit=exit, side=side,
                partial=partial, source="rules", **kw)


def test_eight_closures_are_not_equity_and_arb_loss_summed():
    h = aggregate_fills([close(id=62, net=-122.6256, margin=100, opened=1000,
                               exit=0.16818363)], portfolio="hawk", run_id="legacy-nov")
    b = aggregate_fills([close(id=19, net=-226.8574, margin=185, opened=1200,
                               exit=0.16818363)], portfolio="bull", run_id="legacy-nov")
    reports = review_positions(h + b)
    assert round(sum(x["net"] for x in h + b), 4) == -349.483
    assert {r["loss_pct_of_reported_margin"] for r in reports} == {-122.63, -122.63}
    assert all("same_symbol_same_direction_cross_portfolio" in r["flags"] for r in reports)
    assert all(r["verdict"] == "evidenza_insufficiente" for r in reports)


def test_partial_fills_count_one_position_even_if_four_rows():
    rows = [close(id=5, closed=i + 2000, net=1.0, margin=10, partial=True) for i in range(4)]
    result = aggregate_fills(rows, portfolio="bull", run_id="old")
    assert len(result) == 1
    assert result[0]["fills"] == 4
    assert result[0]["net"] == 4
    assert result[0]["margin"] == 40


def test_same_id_new_run_and_same_symbol_do_not_merge():
    a = aggregate_fills([close()], portfolio="hawk", run_id="run-one")
    b = aggregate_fills([close()], portfolio="hawk", run_id="run-two")
    assert a[0]["run_id"] != b[0]["run_id"]


def test_duplicate_id_only_when_explicit_fill_id():
    row = close(fill_id="f-001")
    x = aggregate_fills([row, row], portfolio="hawk", run_id="run")
    assert len(x) == 1 and x[0]["fills"] == 1
    row = close()
    assert aggregate_fills([row, row], portfolio="hawk", run_id="run")[0]["fills"] == 2


@pytest.mark.parametrize("changed", [{"net": float("nan")}, {"open_ms": None},
                                     {"id": None}, {"side": 0}, {"close_ms": 1}])
def test_invalid_or_ambiguous_input_fails_closed(changed):
    row = close()
    row.update(changed)
    with pytest.raises(ReviewDataError):
        aggregate_fills([row], portfolio="hawk", run_id="v1")


def test_unknown_fees_not_invented():
    row = close()
    records = aggregate_fills([row], portfolio="hawk", run_id="run")
    assert records[0]["fees"] is None
    assert records[0]["funding"] is None
    assert set(records[0]["unknown_financial_fields"]) >= {"fees", "funding"}


def test_stop_from_exit_only_is_not_enough_to_assert_stop_triggered():
    p = aggregate_fills([close()], portfolio="hawk", run_id="run")
    ident = ("hawk", "run", "ARB", "1", 1000)
    r = review_positions(p, entry_stop_evidence={ident: {
        "verified": True, "source_ref": "snapshot:abc", "initial_stop": .162}},
        monitoring_evidence={ident: {
            "verified": True, "source_ref": "audit:rc76", "coverage": "disabled"}})[0]
    assert "exit_beyond_verified_initial_stop" in r["flags"]
    assert "monitoring_disabled_during_position" in r["flags"]
    assert r["verdict"] == "evidenza_insufficiente"


def test_proven_management_failure_requires_verified_time_path():
    p = aggregate_fills([close()], portfolio="hawk", run_id="run")
    ident = ("hawk", "run", "ARB", "1", 1000)
    r = review_positions(p, entry_stop_evidence={ident: {
        "verified": True, "source_ref": "snapshot:abc", "initial_stop": .162}},
        monitoring_evidence={ident: {
            "verified": True, "source_ref": "feed:h1", "coverage": "disabled",
            "stop_crossing_verified": True, "continuous_price_path_verified": True}})[0]
    assert r["verdict"] == "problema_gestione"
    assert r["can_autolearn"] is False and r["can_trade"] is False


def test_nondirectional_or_distant_peers_not_flagged():
    a = aggregate_fills([close()], portfolio="hawk", run_id="a")
    b = aggregate_fills([close(side=1, opened=1000, closed=2000)], portfolio="bull", run_id="b")
    c = aggregate_fills([close(opened=1000000, closed=1002000)], portfolio="bull", run_id="b")
    assert not any(r["peer_positions"] for r in review_positions(a + b + c))


def test_no_mutation_of_input():
    row = close()
    old = dict(row)
    aggregate_fills([row], portfolio="hawk", run_id="run")
    assert row == old


def test_dca_entry_change_keeps_position_together_with_quality_flag():
    a = close(id=5, partial=True)
    b = close(id=5, closed=2100, entry=.165, partial=False)
    records = aggregate_fills([a, b], portfolio="hawk", run_id="one-run")
    assert len(records) == 1 and records[0]["fills"] == 2
    assert records[0]["entry"] is None
    assert "entry_changed_across_fills" in records[0]["data_quality_flags"]