"""Universo comune: regole deterministiche su dati finti. Nessuna rete."""
from __future__ import annotations

import pytest

from backend.v3.arena import universe as U


def coin(sym, price, cid=None):
    return {"id": cid or sym.lower(), "symbol": sym.lower(), "current_price": price, "market_cap": 1}


def contract(pair, status="normal", lever="100"):
    return {"symbol": pair, "symbolStatus": status, "symbolType": "perpetual", "maxLever": lever}


OK = lambda pair: {"ok": True, "code": "ok"}  # noqa: E731


def snap(ranking, contracts, tickers, probe=OK, target=3):
    return U.build_snapshot(ranking, contracts, probe, tickers=tickers, as_of_ms=1, min_leverage=20,
                            crypto_target=target)


def test_takes_the_first_eligible_in_ranking_order_plus_verified_metals():
    ranking = [coin("BTC", 100), coin("USDT", 1), coin("ETH", 10), coin("LEO", 5), coin("SOL", 2), coin("ADA", 1)]
    contracts = [contract(p) for p in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "XAUUSDT", "XAGUSDT")]
    tickers = [{"symbol": "BTCUSDT", "lastPr": "100.5"}, {"symbol": "ETHUSDT", "lastPr": "10"},
               {"symbol": "SOLUSDT", "lastPr": "2.01"}, {"symbol": "ADAUSDT", "lastPr": "1"}]
    s = snap(ranking, contracts, tickers)
    assert s["symbols"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XAUUSDT", "XAGUSDT"]
    assert s["crypto_target_met"] is True
    reasons = {e["symbol"]: e["reason"] for e in s["excluded_before_target"]}
    assert reasons == {"USDT": "stablecoin", "LEO": "no_bitget_usdt_perpetual"}


def test_same_ticker_different_asset_is_excluded_by_price_identity():
    ranking = [coin("GRAM", 1.05, "the-open-network"), coin("BTC", 100)]
    tickers = [{"symbol": "GRAMUSDT", "lastPr": "0.002"}, {"symbol": "BTCUSDT", "lastPr": "100"}]
    s = snap(ranking, [contract("GRAMUSDT"), contract("BTCUSDT")], tickers, target=2)
    assert s["symbols"] == ["BTCUSDT"] and s["crypto_target_met"] is False
    assert s["excluded_before_target"][0]["reason"] == "identity_price_mismatch"
    s = snap(ranking, [contract("GRAMUSDT"), contract("BTCUSDT")], [{"symbol": "BTCUSDT", "lastPr": "100"}], target=2)
    assert s["excluded_before_target"][0]["reason"] == "identity_price_missing"


def test_contract_status_leverage_and_feed_gaps_exclude_never_presume():
    ranking = [coin("AAA", 1), coin("BBB", 1), coin("CCC", 1), coin("DDD", 1)]
    contracts = [contract("AAAUSDT", status="restrictedAPI"), contract("BBBUSDT", lever="10"),
                 contract("CCCUSDT"), contract("DDDUSDT"), contract("XAUUSDT")]
    tickers = [{"symbol": p, "lastPr": "1"} for p in ("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT")]
    probe = lambda pair: {"ok": False, "code": "history_gap_or_short"} if pair in ("CCCUSDT", "XAUUSDT") else OK(pair)  # noqa: E731
    s = snap(ranking, contracts, tickers, probe=probe, target=4)
    assert s["symbols"] == ["DDDUSDT"]
    assert [e["reason"] for e in s["excluded_before_target"]] == [
        "contract_not_normal", "max_leverage_below_mandate", "feed_history_gap_or_short"]
    assert s["metals"] == [{"pair": "XAUUSDT", "included": False, "reason": "feed_history_gap_or_short"},
                           {"pair": "XAGUSDT", "included": False, "reason": "no_bitget_usdt_perpetual"}]


def test_snapshot_is_deterministic_and_rejects_empty_input():
    ranking = [coin("BTC", 100)]
    a = snap(ranking, [contract("BTCUSDT")], [{"symbol": "BTCUSDT", "lastPr": "100"}], target=1)
    b = snap(ranking, [contract("BTCUSDT")], [{"symbol": "BTCUSDT", "lastPr": "100"}], target=1)
    assert a == b and len(a["symbols_sha256"]) == 64
    with pytest.raises(ValueError):
        snap([], [], [])


def test_committed_snapshot_matches_the_three_configs():
    import json
    from pathlib import Path

    from backend.v3.arena.prepare import config_path
    snap_file = Path(__file__).resolve().parents[3] / "docs/v3/arena_universe_snapshot_20261117.json"
    data = json.loads(snap_file.read_text())
    assert data["crypto_target_met"] is True and len(data["crypto_included"]) == 25
    assert {m["pair"] for m in data["metals"] if m["included"]} == {"XAUUSDT", "XAGUSDT"}
    for provider in ("deepseek", "qwen", "minimax"):
        assert json.loads(config_path(provider).read_text())["symbols"] == data["symbols"]
