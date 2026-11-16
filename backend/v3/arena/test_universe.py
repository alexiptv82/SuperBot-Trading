"""Pure tests for Top-23-by-capitalisation + XAU/XAG dynamic PAPER Arena."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from unittest import TestCase, main

from backend.v3.arena.universe import (
    RankedAsset, FuturesContract, SignalScreen,
    build_universe, pick_ai_shortlist, UNIVERSE_SLOTS, METAL_SYMBOLS,
)

NOW = 1795000000000
# Symbol names intentionally synthetic; no assumptions about November rankings.
COINS = tuple(f"C{i:03d}" for i in range(1, 35))


def contract(symbol: str, **kwargs):
    p = dict(
        symbol=symbol, product_type="USDT-FUTURES",
        contract_type="perpetual", status="normal",
        quote_volume_24h_usdt=Decimal("20000000"),
        spread_bps=Decimal("5"),
        min_leverage=1, max_leverage=50,
        closed_bars_verified=True, observed_ms=NOW - 5000,
    )
    return FuturesContract(**{**p, **kwargs})


def fixture():
    assets = [
        RankedAsset(
            asset_id=f"asset-{ticker.lower()}", ticker=ticker,
            market_cap_rank=rank, market_cap_usd=Decimal(10000000000 - rank * 1000000),
            classification="native", observed_ms=NOW - 1000,
        )
        for rank, ticker in enumerate(COINS, start=1)
    ]
    contracts = {ticker+"USDT": contract(ticker+"USDT") for ticker in COINS}
    contracts["XAUUSDT"] = contract("XAUUSDT")
    contracts["XAGUSDT"] = contract("XAGUSDT")
    return assets, contracts


def build(assets, contracts):
    return build_universe(tuple(assets), contracts, now_ms=NOW)


def screen(symbol: str, side: str, score: str = "0.8", **kwargs):
    p = dict(
        symbol=symbol, side=side, quality=Decimal(score),
        market_data_timestamp_ms=NOW - 60000,
        closed_bars_only=True, contract_liquid=True,
    )
    return SignalScreen(**{**p, **kwargs})


class UniverseTests(TestCase):
    def test_exactly_23_crypto_plus_two_distinct_metals(self):
        assets, contracts = fixture()
        v = build(assets, contracts)
        self.assertTrue(v.complete)
        self.assertEqual(v.crypto_count, 23)
        self.assertEqual(v.metal_count, 2)
        self.assertEqual(len(v.markets), 25)
        self.assertEqual(len(set(v.tradeable_symbols)), 25)
        self.assertEqual(v.tradeable_symbols[-2:], METAL_SYMBOLS)
        self.assertEqual(v.markets[0].crypto_rank, 1)
        self.assertEqual(v.markets[22].crypto_rank, 23)
        self.assertEqual(v.mode, "PAPER_OFFLINE_READONLY")

    def test_stablecoin_wrapped_and_tokenized_metal_excluded_from_crypto_slots(self):
        assets, contracts = fixture()
        assets[1] = replace(assets[1], classification="stablecoin")
        assets[2] = replace(assets[2], classification="wrapped")
        assets[3] = replace(assets[3], classification="tokenized_metal")
        assets[4] = replace(assets[4], classification="unknown")
        v = build(assets, contracts)
        ranks = [x.crypto_rank for x in v.markets if x.kind == "crypto"]
        self.assertEqual(ranks[0], 1)
        self.assertNotIn(2, ranks)
        self.assertNotIn(3, ranks)
        self.assertNotIn(4, ranks)
        self.assertNotIn(5, ranks)
        self.assertEqual(ranks[-1], 27)
        self.assertEqual(len(v.markets), 25)

    def test_unavailable_top_coin_is_replaced_by_next_ranked_tradable_coin(self):
        assets, contracts = fixture()
        contracts["C002USDT"] = contract("C002USDT", status="maintenance")
        result = build(assets, contracts)
        self.assertTrue(result.complete)
        crypto_ranks = [x.crypto_rank for x in result.markets if x.kind == "crypto"]
        self.assertEqual(crypto_ranks[-1], 24)
        self.assertNotIn(2, crypto_ranks)

    def test_metals_remain_reserved_not_backfilled_when_no_contract(self):
        assets, contracts = fixture()
        contracts.pop("XAUUSDT")
        value = build(assets, contracts)
        self.assertFalse(value.complete)
        self.assertEqual(len(value.markets), 25)
        self.assertEqual(value.markets[-2].symbol, "XAUUSDT")
        self.assertFalse(value.markets[-2].tradeable)
        self.assertEqual(value.markets[-2].reason, "BITGET_CONTRACT_UNAVAILABLE")
        self.assertEqual(value.tradeable_symbols[-1], "XAGUSDT")

    def test_metals_require_safe_leverage_and_closed_bars(self):
        assets, contracts = fixture()
        contracts["XAGUSDT"] = contract("XAGUSDT", max_leverage=10)
        contracts["XAUUSDT"] = contract("XAUUSDT", closed_bars_verified=False)
        result = build(assets, contracts)
        self.assertFalse(result.complete)
        self.assertFalse(result.markets[-1].tradeable)
        self.assertEqual(result.markets[-1].reason, "UNSUPPORTED_LEVERAGE")
        self.assertEqual(result.markets[-2].reason, "STALE_CONTRACT_OR_FEED")

    def test_bad_24h_volume_and_spread_prevent_tradeability(self):
        assets, contracts = fixture()
        contracts["C001USDT"] = contract("C001USDT", spread_bps=Decimal("40"))
        contracts["C002USDT"] = contract(
            "C002USDT", quote_volume_24h_usdt=Decimal("200000")
        )
        result = build(assets, contracts)
        self.assertEqual([x.crypto_rank for x in result.markets[:3]], [3, 4, 5])

    def test_ranking_source_must_be_fresh_and_unambiguous(self):
        assets, contracts = fixture()
        assets[0] = replace(assets[0], observed_ms=NOW - 3 * 86400000)
        with self.assertRaisesRegex(ValueError, "untrusted_ranked_asset"):
            build(assets, contracts)
        assets, contracts = fixture()
        assets.append(replace(assets[0], asset_id="fake-same-rank"))
        with self.assertRaisesRegex(ValueError, "duplicate_market_cap_rank"):
            build(assets, contracts)
        assets, contracts = fixture()
        assets.append(replace(assets[0], market_cap_rank=999))
        with self.assertRaisesRegex(ValueError, "duplicate_asset_id"):
            build(assets, contracts)

    def test_incomplete_ranking_never_pads_with_fake_symbols(self):
        assets, contracts = fixture()
        v = build(assets[:4], contracts)
        self.assertFalse(v.complete)
        self.assertEqual(v.crypto_count, 4)
        self.assertEqual(len(v.markets), 6)

    def test_all_25_watched_but_eight_or_fewer_expensive_ai_reviews(self):
        assets, contracts = fixture()
        v = build(assets, contracts)
        rows = tuple(
            screen(symbol, "LONG" if i % 2 == 0 else "SHORT",
                   score=str(Decimal("1") - Decimal(i) / 100))
            for i, symbol in enumerate(v.tradeable_symbols)
        )
        result = pick_ai_shortlist(v, rows, now_ms=NOW)
        self.assertEqual(len(result.watched_symbols), 25)
        self.assertEqual(len(result.ai_shortlist), 8)
        self.assertEqual(len(result.bullish_candidates), 4)
        self.assertEqual(len(result.bearish_candidates), 4)
        self.assertEqual(len(set(result.ai_shortlist)), 8)
        self.assertEqual(result.mode, "PAPER_OFFLINE_READONLY")

    def test_no_trade_and_bad_candles_never_get_deep_ai_slot(self):
        assets, contracts = fixture()
        v = build(assets, contracts)
        signals = (
            screen(v.tradeable_symbols[0], "NO_TRADE", "1"),
            screen(v.tradeable_symbols[1], "SHORT", "0.99", closed_bars_only=False),
            screen(v.tradeable_symbols[2], "LONG", "0.99",
                   market_data_timestamp_ms=NOW - 2 * 3600000),
            screen(v.tradeable_symbols[3], "LONG", "0.55"),
        )
        result = pick_ai_shortlist(v, signals, now_ms=NOW)
        self.assertEqual(result.ai_shortlist, (v.tradeable_symbols[3],))

    def test_shortlist_includes_metals_if_signals_are_best(self):
        assets, contracts = fixture()
        v = build(assets, contracts)
        signals = (screen("XAUUSDT", "LONG", "0.95"),
                   screen("XAGUSDT", "SHORT", "0.99"))
        result = pick_ai_shortlist(v, signals, now_ms=NOW)
        self.assertEqual(set(result.ai_shortlist), {"XAUUSDT", "XAGUSDT"})

    def test_invalid_signals_cannot_cross_scope(self):
        assets, contracts = fixture()
        v = build(assets, contracts)
        with self.assertRaisesRegex(ValueError, "invalid_signal_batch"):
            pick_ai_shortlist(v, (screen("DOGEFAKEUSDT","SHORT"),), now_ms=NOW)
        good = screen(v.tradeable_symbols[0], "LONG")
        with self.assertRaisesRegex(ValueError, "invalid_signal_batch"):
            pick_ai_shortlist(v, (good, good), now_ms=NOW)
        with self.assertRaisesRegex(ValueError, "invalid_signal_batch"):
            pick_ai_shortlist(v, (screen(v.tradeable_symbols[0],
                                         "SHORT", score="NaN"),), now_ms=NOW)

    def test_eight_is_configurable_not_a_fixed_universe_size(self):
        assets, contracts = fixture()
        v = build(assets, contracts)
        signals = tuple(screen(s, "SHORT", score="0.7")
                        for s in v.tradeable_symbols)
        result = pick_ai_shortlist(v, signals, now_ms=NOW, slots=12)
        self.assertEqual(len(result.ai_shortlist), 12)
        self.assertEqual(len(result.watched_symbols), 25)
        with self.assertRaises(ValueError):
            pick_ai_shortlist(v, signals, now_ms=NOW, slots=26)

    def test_existing_position_never_disappears_from_exit_watch(self):
        assets, contracts = fixture()
        v = build(assets, contracts)
        # C001 was open yesterday but today has dropped out of the top list.
        open_symbol = "OLDCOINUSDT"
        fresh_signal = screen(v.tradeable_symbols[0], "LONG", "0.99")
        result = pick_ai_shortlist(
            v, (fresh_signal,), now_ms=NOW,
            open_position_symbols=(open_symbol,),
        )
        self.assertIn(open_symbol, result.exit_monitor_symbols)
        self.assertNotIn(open_symbol, result.ai_shortlist)
        self.assertEqual(len(result.watched_symbols), 25)

    def test_existing_position_cannot_be_selected_for_duplicate_open(self):
        assets, contracts = fixture()
        v = build(assets, contracts)
        already = v.tradeable_symbols[0]
        signals = (screen(already, "SHORT", "1"),
                   screen(v.tradeable_symbols[1], "LONG", "0.9"))
        result = pick_ai_shortlist(
            v, signals, now_ms=NOW,
            open_position_symbols=(already,),
        )
        self.assertEqual(result.ai_shortlist, (v.tradeable_symbols[1],))
        self.assertEqual(result.exit_monitor_symbols, (already,))

    def test_untrusted_open_positions_cannot_modify_exit_watch(self):
        assets, contracts = fixture()
        v = build(assets, contracts)
        for opened in (("BTCUSDT", "BTCUSDT"), ("bad symbol",)):
            with self.assertRaisesRegex(ValueError, "invalid_scan_request"):
                pick_ai_shortlist(
                    v, (), now_ms=NOW, open_position_symbols=opened
                )

    def test_selection_never_sends_orders_or_creates_files(self):
        # Pure functions: no filesystem, API, budget ledger, or trade objects.
        assets, contracts = fixture()
        before = dict(contracts)
        v = build(assets, contracts)
        selection = pick_ai_shortlist(v, (), now_ms=NOW)
        self.assertEqual(selection.ai_shortlist, ())
        self.assertEqual(contracts, before)


if __name__ == "__main__":
    main()
