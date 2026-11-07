"""Shadow-only incremental Market Quality Monitor. No Bitget/network/runtime calls."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from backend.v3.observability.liquidity_quote import BookSample
from backend.v3.observability.market_quality import (
    FullBookFrame, MarketQualitySnapshot, SequenceCursor,
    mid_markout_after, observe_market_quality,
)

NOW = 300_000_000


def frame(*, bids=None, asks=None, event_ts_ms=NOW-1000, received_ts_ms=NOW-500,
          connection_id="session-1", seq=900, pseq=None, is_snapshot=True, symbol="BTCUSDT"):
    bids = bids if bids is not None else ((D("99.99"),D("5")),(D("99.95"),D("10")), (D("99"),D("20")))
    asks = asks if asks is not None else ((D("100.01"),D("5")),(D("100.05"),D("10")),(D("101"),D("20")))
    return FullBookFrame(
        BookSample(symbol,event_ts_ms,bids,asks), symbol=symbol, venue="BITGET",
        instrument_type="USDT_PERPETUAL", source_version="UTA_V3_L2", qty_unit="BASE",
        connection_id=connection_id, event_ts_ms=event_ts_ms, received_ts_ms=received_ts_ms,
        is_snapshot=is_snapshot, seq=seq, pseq=pseq)


def observe(f=None, **kwargs):
    args = dict(now_ms=NOW, frame=frame() if f is None else f,
                intended_side="LONG", notional_usdt=D("200"))
    args.update(kwargs)
    return observe_market_quality(**args)


def test_snapshot_metrics_and_cursor():
    snapshot, cursor = observe(fee_roundtrip_bps=D("12"))
    assert snapshot.status == "OBSERVED"
    assert snapshot.observational_only is True
    assert snapshot.midpoint == D("100")
    assert snapshot.spread_bps == D("2")
    assert snapshot.microprice_delta_bps == 0
    assert snapshot.depth_bid_10bps_usdt == D("99.99")*5+D("99.95")*10
    assert snapshot.depth_ask_10bps_usdt == D("100.01")*5+D("100.05")*10
    assert abs(snapshot.imbalance_top5) < D("0.1")
    assert snapshot.entry_impact_bps > 0
    assert snapshot.exit_impact_bps > 0
    assert abs(snapshot.estimated_roundtrip_bps_ex_funding - (snapshot.entry_impact_bps+snapshot.exit_impact_bps+D("12"))) < D("0.00000000001")
    assert cursor == SequenceCursor("session-1", 900, NOW-500)
    assert not hasattr(snapshot, "markout_30s_bps")  # future cannot leak into entry-time signal
    assert not hasattr(snapshot, "approved")         # never an order permission


def test_same_qualities_not_total_cost_without_fees():
    snap, _ = observe()
    assert snap.status == "OBSERVED"
    assert snap.estimated_roundtrip_bps_ex_funding is None


def test_no_book_unknown_no_cursor():
    snap, cursor = observe_market_quality(now_ms=NOW, frame=None, intended_side="LONG", notional_usdt=D("20"))
    assert (snap.status, snap.reason, cursor) == ("UNKNOWN", "book_feed_missing", None)


@pytest.mark.parametrize("field,value", [
    ("venue", "BINANCE"), ("instrument_type", "SPOT"),
    ("source_version", "BITGET_V2"), ("qty_unit", "CONTRACTS"),
])
def test_unverified_source_never_observed(field, value):
    snap, cursor = observe(replace(frame(), **{field:value}))
    assert snap.status == "UNKNOWN" and cursor is None
    assert snap.spread_bps is None


def test_qty_base_required_not_arbitrary_contract_units():
    snap, _ = observe(replace(frame(), qty_unit="RAW_CONTRACTS"))
    assert snap.reason == "unverified_book_source_or_units"


def test_stale_receive_rejected():
    f = frame(event_ts_ms=NOW-8000, received_ts_ms=NOW-7000)
    snap,cursor = observe(f)
    assert snap.status == "UNKNOWN" and snap.reason == "stale_or_delayed_book" and cursor is None


def test_excessive_transport_lag_rejected():
    f = frame(event_ts_ms=NOW-7000, received_ts_ms=NOW-500)
    snap,_ = observe(f)
    assert snap.status == "UNKNOWN" and snap.reason == "stale_or_delayed_book"


@pytest.mark.parametrize("event,receive",[(NOW+100,NOW+100),(NOW-100,NOW+100),(0,NOW-500),(NOW-300,NOW-400)])
def test_invalid_timestamps_are_unknown(event,receive):
    f=frame(event_ts_ms=event,received_ts_ms=receive)
    snap,cursor=observe(f)
    assert snap.status=="UNKNOWN" and cursor is None


def test_symbol_mismatch_rejected():
    f=frame()
    snap,cursor=observe(replace(f,symbol="ETHUSDT"))
    assert snap.status=="INVALID" and cursor is None


def test_book_timestamp_mismatch_rejected():
    f=frame()
    snap,_=observe(replace(f,book=replace(f.book,timestamp_ms=f.event_ts_ms+1)))
    assert snap.reason=="book_identity_mismatch"


def test_crossed_book_invalid():
    f=frame(bids=((D("101"),D("1")),),asks=((D("100"),D("1")),))
    snap,cursor=observe(f)
    assert snap.status=="INVALID" and cursor is None


def test_unsorted_depth_invalid():
    f=frame(bids=((D("99"),D("1")),(D("99.9"),D("1"))))
    snap,cursor=observe(f)
    assert snap.status=="INVALID" and cursor is None


def test_missing_depth_not_observed():
    snap,cursor=observe(notional_usdt=D("100000"))
    assert snap.status=="INSUFFICIENT"
    assert snap.estimated_roundtrip_bps_ex_funding is None
    assert snap.entry_impact_bps is None
    assert cursor is not None


def test_short_changes_which_side_is_entry():
    f=frame(bids=((D("99.99"),D("1")),(D("99.95"),D("100"))),
            asks=((D("100.01"),D("100")),(D("100.05"),D("1"))))
    long,_=observe(f)
    short,_=observe_market_quality(now_ms=NOW,frame=f,intended_side="SHORT",notional_usdt=D("200"))
    assert long.entry_impact_bps < short.entry_impact_bps


def test_microprice_skew_has_direction():
    f=frame(bids=((D("99.99"),D("50")),),asks=((D("100.01"),D("1")),))
    snap,_=observe(f,notional_usdt=D("50"))
    assert snap.status=="OBSERVED"
    assert snap.microprice_delta_bps>0
    assert snap.imbalance_top5>0


def test_delta_with_proven_continuity_is_observed():
    first,cursor=observe()
    f=frame(event_ts_ms=NOW-600,received_ts_ms=NOW-100,seq=901,pseq=900,is_snapshot=False)
    snap,nxt=observe(f,previous=cursor)
    assert snap.status=="OBSERVED" and nxt.seq==901


def test_increment_without_previous_is_unknown():
    f=frame(is_snapshot=False,seq=901,pseq=900)
    snap,cursor=observe(f)
    assert snap.reason=="unproven_sequence" and cursor is None


def test_sequence_gap_rejected():
    previous=SequenceCursor("session-1",895,NOW-1000)
    f=frame(is_snapshot=False,seq=901,pseq=900)
    snap,cursor=observe(f,previous=previous)
    assert snap.reason=="sequence_gap" and cursor is None


def test_reordered_sequence_rejected():
    previous=SequenceCursor("session-1",900,NOW-1000)
    f=frame(is_snapshot=False,seq=900,pseq=900)
    snap,cursor=observe(f,previous=previous)
    assert snap.reason=="replayed_or_reordered_book" and cursor is None


def test_reconnect_needs_snapshot_not_delta():
    previous=SequenceCursor("other-session",800,NOW-1000)
    f=frame(is_snapshot=False,seq=901,pseq=800)
    snap,cursor=observe(f,previous=previous)
    assert snap.reason=="reconnect_requires_snapshot" and cursor is None


def test_reconnect_snapshot_resets_sequence():
    previous=SequenceCursor("old-session",1050,NOW-1500)
    f=frame(connection_id="new-session",seq=20,is_snapshot=True)
    snap,cursor=observe(f,previous=previous)
    assert snap.status=="OBSERVED" and cursor.seq==20 and cursor.connection_id=="new-session"


def test_overlapping_feed_timestamp_invalid():
    previous=SequenceCursor("session-1",900,NOW-400)
    f=frame(is_snapshot=False,seq=901,pseq=900,received_ts_ms=NOW-500)
    snap,cursor=observe(f,previous=previous)
    assert snap.reason=="replayed_or_reordered_book" and cursor is None


@pytest.mark.parametrize("override", [
    {"now_ms": 0},
    {"intended_side": "BUY"},
    {"notional_usdt": D("NaN")},
    {"fee_roundtrip_bps": D("-1")},
    {"fee_roundtrip_bps": D("Infinity")},
    {"max_age_ms": -1},
    {"max_transport_lag_ms": -1},
])
def test_invalid_requests_raise(override):
    args=dict(now_ms=NOW,frame=frame(),intended_side="LONG",notional_usdt=D("200"))
    args.update(override)
    with pytest.raises(ValueError,match="invalid_market_quality_request"):
        observe_market_quality(**args)


def test_markout_ex_post_30s_and_short_sign():
    entry,_=observe()
    later=replace(entry,event_ts_ms=entry.event_ts_ms+30000,midpoint=D("101"))
    long=mid_markout_after(at_entry=entry,later=later,side="LONG",horizon_ms=30000)
    short=mid_markout_after(at_entry=entry,later=later,side="SHORT",horizon_ms=30000)
    assert long.status=="OBSERVED" and long.signed_mid_move_bps==D("100")
    assert short.signed_mid_move_bps==D("-100")
    assert long.reason=="ex_post_midpoint_not_pnl"


def test_markout_too_early_cannot_use_future():
    entry,_=observe()
    later=replace(entry,event_ts_ms=entry.event_ts_ms+29000,midpoint=D("101"))
    result=mid_markout_after(at_entry=entry,later=later,side="LONG",horizon_ms=30000)
    assert result.status=="UNKNOWN" and result.signed_mid_move_bps is None


def test_markout_stale_or_mismatch_is_unknown():
    entry,_=observe()
    later=replace(entry,event_ts_ms=entry.event_ts_ms+60000,midpoint=D("101"),symbol="ETHUSDT")
    assert mid_markout_after(at_entry=entry,later=later,side="LONG",horizon_ms=60000).status=="UNKNOWN"
    later=replace(later,symbol="BTCUSDT",status="UNKNOWN")
    assert mid_markout_after(at_entry=entry,later=later,side="LONG",horizon_ms=60000).status=="UNKNOWN"


def test_markout_too_late_is_unknown():
    entry,_=observe()
    later=replace(entry,event_ts_ms=entry.event_ts_ms+70000,midpoint=D("101"))
    assert mid_markout_after(at_entry=entry,later=later,side="LONG",horizon_ms=60000).status=="UNKNOWN"


def test_no_writes_in_pure_observation(tmp_path):
    files_before = tuple(tmp_path.iterdir())
    entry,_=observe()
    later=replace(entry,event_ts_ms=entry.event_ts_ms+30000)
    mid_markout_after(at_entry=entry,later=later,side="LONG",horizon_ms=30000)
    assert tuple(tmp_path.iterdir())==files_before


def test_same_session_snapshot_replay_is_invalid():
    previous=SequenceCursor("session-1",900,NOW-900)
    snap,cursor=observe(frame(seq=900),previous=previous)
    assert snap.status=="INVALID" and snap.reason=="replayed_or_reordered_book" and cursor is None


def test_invalid_previous_cursor_is_not_trusted():
    snap,cursor=observe(previous={"connection_id":"session-1","seq":900})
    assert snap.status=="INVALID" and snap.reason=="invalid_sequence_cursor" and cursor is None


def test_fake_negative_sequence_is_invalid():
    snap,cursor=observe(frame(seq=-1))
    assert snap.status=="INVALID" and cursor is None


def test_snapshot_same_connection_newer_sequence_accepted():
    old=SequenceCursor("session-1",899,NOW-900)
    snap,cursor=observe(previous=old)
    assert snap.status=="OBSERVED" and cursor.seq==900


def test_invalid_cursor_values_fail_closed():
    snap,cursor=observe(previous=SequenceCursor("session-1", "900", NOW-1000))
    assert snap.status=="INVALID" and cursor is None
