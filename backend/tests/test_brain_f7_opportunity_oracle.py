"""F7 / P5 — etichettatura delle opportunita': verifica INDIPENDENTE (Claude) del modulo di Grok.

Perche' un secondo file di test: quelli di Grok (test_brain_f7_opportunity.py) hanno
un "oracolo" che e' una copia dell'algoritmo del modulo (stessa formula, stessa
struttura) e che non e' mai stato eseguito (il generatore produce candele non valide
e il test si ferma in validazione); confronta solo stato/barriera/ambiguita', non
prezzi, tocchi e bp; la sua guardia e' un `or`. Qui:

* un ORACOLO scritto dal testo del contratto con un algoritmo DIVERSO (filtra la
  serie per intervallo invece di cercare per indice, `Fraction` esatta) confronta
  OGNI campo di OGNI etichetta su dataset casuali con equalita' esatte sui livelli,
  buchi, ambiguita' e timeout, con guardie che dimostrano che i casi ci sono;
* valori calcolati a mano con stringhe esatte (compresi i pareggi dell'arrotondamento);
* codici d'errore esatti, in ordine, per ogni argomento e per ogni elemento (non solo
  il primo), input ostili (generatori, insiemi, NaN, bool, float, id con "\n");
* invarianti: coerenza fra orizzonti, ordine, nessuna mutazione, contesto Decimal;
* purezza del modulo (AST).
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import itertools
import random
from collections.abc import Mapping
from decimal import ROUND_UP, Decimal, getcontext, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from backend.v3.learning import opportunity as op
from backend.v3.learning.opportunity import (
    Candidate, Candle, HorizonLabel, OpportunityLabel, label_candidates,
)

D = Decimal


def _c(t, o, h, l, c) -> Candle:
    return Candle(t, D(str(o)), D(str(h)), D(str(l)), D(str(c)))


def _k(cid="c1", sym="BTC", side=1, ts=500, entry="100", stop=None, target=None) -> Candidate:
    if stop is None:
        stop = "90" if side == 1 else "110"
    if target is None:
        target = "115" if side == 1 else "85"
    return Candidate(cid, sym, side, ts, D(str(entry)), D(str(stop)), D(str(target)))


KW = dict(candle_ms=1000, horizons_ms=[1000], cost_bp=D("10"), ambiguous_policy="stop_first")


def _lab(cands, candles, **kw):
    return label_candidates(cands, candles, **{**KW, **kw})


def _h0(cand, series, **kw) -> HorizonLabel:
    return _lab([cand], {"BTC": series}, **kw)[0].horizons[0]


# ---------------------------------------------------------------------------
# ORACOLO: algoritmo diverso (filtro per intervallo, Fraction), nessun codice del modulo
# ---------------------------------------------------------------------------

def _q4(x: Fraction) -> D:
    scaled = x * 10000
    q, rem = divmod(scaled.numerator, scaled.denominator)
    twice = 2 * rem
    if twice > scaled.denominator or (twice == scaled.denominator and q % 2 == 1):
        q += 1
    return D(q).scaleb(-4)


def oracle(cand: Candidate, series, candle_ms: int, h: int, cost, policy: str):
    """-> ("incomplete",) oppure (barrier, ambiguous, touch, exit_price, gross_bp, net_bp)."""
    s = cand.signal_time_ms
    start = s if s % candle_ms == 0 else s - (s % candle_ms) + candle_ms
    win = [cn for cn in series if start <= cn.open_time_ms < start + h]
    n = h // candle_ms
    if len(win) != n or any(cn.open_time_ms != start + i * candle_ms for i, cn in enumerate(win)):
        return ("incomplete",)
    entry, stop, target = Fraction(cand.entry_price), Fraction(cand.stop_price), Fraction(cand.target_price)
    barrier, amb, touch = "timeout", False, None
    for cn in win:
        lo, hi = Fraction(cn.low), Fraction(cn.high)
        st, tg = (lo <= stop, hi >= target) if cand.side == 1 else (hi >= stop, lo <= target)
        if st or tg:
            amb = st and tg
            barrier = ("stop" if policy == "stop_first" else "target") if amb else ("stop" if st else "target")
            touch = cn.open_time_ms
            break
    px = {"stop": stop, "target": target, "timeout": Fraction(win[-1].close)}[barrier]
    gross = cand.side * (px - entry) / entry * 10000
    return (barrier, amb, touch, px, _q4(gross), _q4(gross - Fraction(cost)))


def _assert_label_matches_oracle(lab: HorizonLabel, exp, h: int):
    assert lab.horizon_ms == h
    if exp == ("incomplete",):
        assert lab == HorizonLabel(h, "incomplete", None, False, None, None, None, None)
        return
    barrier, amb, touch, px, gross, net = exp
    assert (lab.status, lab.barrier, lab.ambiguous, lab.touch_time_ms) == ("complete", barrier, amb, touch)
    assert Fraction(lab.exit_price) == px
    assert (lab.gross_bp, lab.net_bp) == (gross, net)


def _random_case(seed: int):
    """Dataset ripetibile con equalita' esatte sui livelli, buchi, ambiguita' e timeout."""
    rng = random.Random(seed)
    candle_ms = rng.choice([1000, 5000])
    candles: dict[str, list[Candle]] = {}
    for sym in ("BTC", "ETH"):
        series, t = [], candle_ms * rng.randint(0, 3)
        for _ in range(rng.randint(8, 30)):
            o = rng.randint(92, 108)
            hi = o + rng.choice([0, 1, 3, 7, 15, 18])
            lo = o - rng.choice([0, 1, 3, 7, 10, 18])
            cl = rng.randint(lo, hi)
            if rng.random() < 0.08:
                t += candle_ms                      # buco: manca una candela
            series.append(_c(t, o, hi, lo, cl))
            t += candle_ms
        candles[sym] = series
    cands = []
    for j in range(rng.randint(3, 8)):
        side = rng.choice([-1, 1])
        d_stop, d_tgt = rng.choice([2, 5, 10]), rng.choice([2, 5, 15])
        stop, target = (100 - d_stop, 100 + d_tgt) if side == 1 else (100 + d_stop, 100 - d_tgt)
        horizon_end = candles["BTC"][-1].open_time_ms + candle_ms
        cands.append(_k(f"r{seed}-{j}", rng.choice(["BTC", "ETH", "SOL"]), side,
                        rng.randint(1, horizon_end), 100, stop, target))
    horizons = rng.choice([[candle_ms], [candle_ms, 3 * candle_ms], [candle_ms, 2 * candle_ms, 6 * candle_ms]])
    cost = rng.choice([D(0), D(10), D("12.3456"), D("0.00005"), D("33.3333")])
    return candle_ms, candles, cands, horizons, cost, rng.choice(["stop_first", "target_first"])


# ---------------------------------------------------------------------------
# controllo e valori calcolati a mano
# ---------------------------------------------------------------------------

class TestControlAndHandNumbers:
    # (side, serie di una candela, barriera, exit, gross, net) con entry 100 e cost 10
    LONG = dict(stop="90", target="115")

    @pytest.mark.parametrize("side,candle,barrier,exit_px,gross,net", [
        (1, (1000, 100, 120, 99, 110), "target", "115", "1500.0000", "1490.0000"),
        (1, (1000, 100, 105, 85, 90), "stop", "90", "-1000.0000", "-1010.0000"),
        (1, (1000, 100, 105, 95, 102), "timeout", "102", "200.0000", "190.0000"),
        (-1, (1000, 100, 105, 80, 90), "target", "85", "1500.0000", "1490.0000"),
        (-1, (1000, 100, 115, 95, 110), "stop", "110", "-1000.0000", "-1010.0000"),
        (-1, (1000, 100, 105, 95, 98), "timeout", "98", "200.0000", "190.0000"),
        (1, (1000, 100, 101, 90.5, 90.6), "timeout", "90.6", "-940.0000", "-950.0000"),
        (-1, (1000, 100, 109, 99, 109), "timeout", "109", "-900.0000", "-910.0000"),
    ])
    def test_hand_values(self, side, candle, barrier, exit_px, gross, net):
        lab = _h0(_k(side=side), [_c(*candle)])
        assert (lab.status, lab.barrier, lab.ambiguous) == ("complete", barrier, False)
        assert str(lab.exit_price) == exit_px
        assert (str(lab.gross_bp), str(lab.net_bp)) == (gross, net)
        assert lab.touch_time_ms == (None if barrier == "timeout" else 1000)
        assert lab.horizon_ms == 1000

    def test_non_round_numbers(self):
        # entry 3, close 3.1: +333.33333 bp; costo 12.3456 -> netto 320.98773.. -> 320.9877
        lab = _h0(_k(entry="3", stop="2", target="9"), [_c(1000, 3, 4, 2.5, "3.1")], cost_bp=D("12.3456"))
        assert (str(lab.gross_bp), str(lab.net_bp)) == ("333.3333", "320.9877")

    @pytest.mark.parametrize("close,gross", [
        (200000001, "0.0000"),       # 0.00005 esatto: pari -> 0.0000 (half-up darebbe 0.0001)
        (200000003, "0.0002"),       # 0.00015 esatto: pari -> 0.0002
        (200000005, "0.0002"),       # 0.00025 esatto: pari -> 0.0002 (half-up darebbe 0.0003)
        (199999999, "0.0000"),       # -0.00005 -> 0.0000
        (199999997, "-0.0002"),      # -0.00015 -> -0.0002
    ])
    def test_gross_rounds_half_even_on_exact_ties(self, close, gross):
        cand = _k(entry="200000000", stop="100000000", target="400000000")
        lab = _h0(cand, [_c(1000, 200000000, 300000000, 100000001, close)], cost_bp=D(0))
        assert str(lab.gross_bp) == gross

    def test_net_is_rounded_from_the_exact_gross_not_from_the_rounded_one(self):
        # gross esatto 0.00015, costo 0.00005: netto esatto 0.0001. Se si sottraesse al gross
        # gia' arrotondato (0.0002) si avrebbe 0.00015 -> 0.0002
        cand = _k(entry="200000000", stop="100000000", target="400000000")
        lab = _h0(cand, [_c(1000, 200000000, 300000000, 100000001, 200000003)], cost_bp=D("0.00005"))
        assert (str(lab.gross_bp), str(lab.net_bp)) == ("0.0002", "0.0001")

    def test_no_negative_zero(self):
        cand = _k(entry="1000000000", stop="900000000", target="1100000000")
        lab = _h0(cand, [_c(1000, 1000000000, 1000000001, 999999999, 999999999)], cost_bp=D(0))
        assert str(lab.gross_bp) == "0.0000" and str(lab.net_bp) == "0.0000"

    def test_cost_is_subtracted_for_every_barrier(self):
        for candle in [(1000, 100, 120, 99, 110), (1000, 100, 105, 85, 90), (1000, 100, 105, 95, 102)]:
            a = _h0(_k(), [_c(*candle)], cost_bp=D(0))
            b = _h0(_k(), [_c(*candle)], cost_bp=D("25"))
            assert a.gross_bp == b.gross_bp and a.net_bp - b.net_bp == D("25")
            assert a.net_bp == a.gross_bp

    def test_candidates_are_independent_and_follow_input_order(self):
        candles = {"BTC": [_c(1000, 100, 120, 99, 110)], "ETH": [_c(1000, 100, 105, 85, 90)]}
        res = _lab([_k("a", "BTC"), _k("b", "ETH"), _k("c", "BTC", -1)], candles)
        assert [(r.candidate_id, r.symbol, r.side) for r in res] == [("a", "BTC", 1), ("b", "ETH", 1), ("c", "BTC", -1)]
        assert [r.horizons[0].barrier for r in res] == ["target", "stop", "stop"]

    def test_result_types(self):
        res = _lab([_k()], {"BTC": [_c(1000, 100, 105, 95, 102)]}, horizons_ms=[1000])
        assert isinstance(res, tuple) and isinstance(res[0], OpportunityLabel) and isinstance(res[0].horizons, tuple)
        assert isinstance(res[0].horizons[0], HorizonLabel)
        assert _lab([], {}) == ()


# ---------------------------------------------------------------------------
# la finestra
# ---------------------------------------------------------------------------

class TestWindow:
    def _two(self):
        # candela 1000 tocca l'obiettivo (high 120); candela 2000 e' tranquilla (close 101)
        return [_c(1000, 100, 120, 99, 110), _c(2000, 101, 104, 99, 101)]

    def test_signal_exactly_on_a_candle_start_includes_that_candle(self):
        lab = _h0(_k(ts=1000), self._two())
        assert (lab.barrier, lab.touch_time_ms) == ("target", 1000)

    def test_signal_one_ms_later_excludes_the_containing_candle(self):
        lab = _h0(_k(ts=1001), self._two())                        # la finestra e' la candela 2000
        assert (lab.barrier, lab.touch_time_ms, str(lab.exit_price)) == ("timeout", None, "101")

    def test_signal_in_the_middle_of_a_candle_is_excluded_too(self):
        assert _h0(_k(ts=1500), self._two()).barrier == "timeout"
        assert _h0(_k(ts=1999), self._two()).barrier == "timeout"

    def test_signal_before_the_first_candle_uses_the_next_grid_point(self):
        assert _h0(_k(ts=1), self._two()).barrier == "target"

    def test_a_touch_before_the_window_does_not_count(self):
        series = [_c(0, 100, 130, 80, 100)] + self._two()[1:]       # candela 0 sarebbe un tocco
        assert _h0(_k(ts=1), series).status == "incomplete"          # finestra = candela 1000: manca
        series = [_c(0, 100, 130, 80, 100), _c(1000, 100, 104, 99, 100)]
        assert _h0(_k(ts=1), series).barrier == "timeout"

    @pytest.mark.parametrize("touch_at", [0, 1, 2, 3])
    def test_touch_on_first_middle_and_last_candle_of_the_window(self, touch_at):
        series = [_c(1000 * (i + 1), 100, 104, 99, 101) for i in range(4)]
        series[touch_at] = _c(1000 * (touch_at + 1), 100, 120, 99, 110)
        lab = _h0(_k(ts=500), series, horizons_ms=[4000])
        assert (lab.barrier, lab.touch_time_ms) == ("target", 1000 * (touch_at + 1))

    def test_candles_after_the_window_are_ignored(self):
        series = [_c(1000, 100, 104, 99, 101), _c(2000, 100, 130, 80, 100)]
        lab = _h0(_k(), series, horizons_ms=[1000])
        assert (lab.barrier, str(lab.exit_price)) == ("timeout", "101")

    def test_level_equality_counts_as_a_touch(self):
        assert _h0(_k(), [_c(1000, 100, 104, 90, 95)]).barrier == "stop"          # low == stop
        assert _h0(_k(), [_c(1000, 100, 115, 99, 105)]).barrier == "target"       # high == target
        assert _h0(_k(), [_c(1000, 100, 114.99, 90.01, 105)]).barrier == "timeout"
        assert _h0(_k(side=-1), [_c(1000, 100, 110, 96, 105)]).barrier == "stop"  # high == stop
        assert _h0(_k(side=-1), [_c(1000, 100, 104, 85, 95)]).barrier == "target"  # low == target
        assert _h0(_k(side=-1), [_c(1000, 100, 109.99, 85.01, 95)]).barrier == "timeout"

    def test_multi_candle_window_uses_the_close_of_the_last_candle(self):
        series = [_c(1000, 100, 104, 99, 101), _c(2000, 101, 106, 100, 105), _c(3000, 105, 107, 101, 103)]
        lab = _h0(_k(), series, horizons_ms=[3000])
        assert (lab.barrier, str(lab.exit_price)) == ("timeout", "103")


class TestIncomplete:
    FULL = [_c(1000 * i, 100, 104, 99, 101) for i in range(1, 6)]

    def _assert_incomplete(self, lab, h):
        assert lab == HorizonLabel(h, "incomplete", None, False, None, None, None, None)

    def test_control_full_series_is_complete(self):
        assert _h0(_k(), self.FULL, horizons_ms=[3000]).status == "complete"

    def test_hole_in_the_middle(self):
        series = [c for c in self.FULL if c.open_time_ms != 2000]
        self._assert_incomplete(_h0(_k(), series, horizons_ms=[3000]), 3000)

    def test_first_candle_missing(self):
        series = [c for c in self.FULL if c.open_time_ms != 1000]
        self._assert_incomplete(_h0(_k(), series, horizons_ms=[3000]), 3000)

    def test_series_ends_early(self):
        self._assert_incomplete(_h0(_k(), self.FULL[:2], horizons_ms=[3000]), 3000)

    def test_series_starts_after_the_signal_window(self):
        self._assert_incomplete(_h0(_k(ts=500), self.FULL[2:], horizons_ms=[1000]), 1000)

    def test_empty_series_and_missing_symbol(self):
        self._assert_incomplete(_h0(_k(), []), 1000)
        self._assert_incomplete(_lab([_k(sym="ETH")], {"BTC": self.FULL})[0].horizons[0], 1000)
        self._assert_incomplete(_lab([_k()], {})[0].horizons[0], 1000)

    def test_horizons_are_independent(self):
        series = self.FULL[:2]
        hs = _lab([_k()], {"BTC": series}, horizons_ms=[1000, 2000, 3000])[0].horizons
        assert [h.status for h in hs] == ["complete", "complete", "incomplete"]
        assert [h.horizon_ms for h in hs] == [1000, 2000, 3000]

    def test_hole_beyond_a_touch_does_not_make_the_short_horizon_incomplete(self):
        series = [_c(1000, 100, 120, 99, 110), _c(3000, 100, 104, 99, 101)]       # buco in 2000
        hs = _lab([_k()], {"BTC": series}, horizons_ms=[1000, 3000])[0].horizons
        assert (hs[0].status, hs[0].barrier) == ("complete", "target")
        assert hs[1].status == "incomplete"

    def test_a_gap_in_another_symbol_does_not_matter(self):
        candles = {"BTC": self.FULL, "ETH": [self.FULL[0], self.FULL[3]]}
        assert _lab([_k(sym="BTC")], candles, horizons_ms=[3000])[0].horizons[0].status == "complete"
        assert _lab([_k(sym="ETH")], candles, horizons_ms=[3000])[0].horizons[0].status == "incomplete"


class TestAmbiguity:
    BOTH = [_c(1000, 100, 120, 80, 100)]                 # tocca stop (80<=90) e obiettivo (120>=115)

    def test_both_policies_long(self):
        a = _h0(_k(), self.BOTH, ambiguous_policy="stop_first")
        b = _h0(_k(), self.BOTH, ambiguous_policy="target_first")
        assert (a.ambiguous, a.barrier, str(a.exit_price), str(a.gross_bp)) == (True, "stop", "90", "-1000.0000")
        assert (b.ambiguous, b.barrier, str(b.exit_price), str(b.gross_bp)) == (True, "target", "115", "1500.0000")
        assert a.touch_time_ms == b.touch_time_ms == 1000

    def test_both_policies_short(self):
        series = [_c(1000, 100, 120, 80, 100)]           # high 120>=110 stop, low 80<=85 target
        a = _h0(_k(side=-1), series, ambiguous_policy="stop_first")
        b = _h0(_k(side=-1), series, ambiguous_policy="target_first")
        assert (a.ambiguous, a.barrier, str(a.gross_bp)) == (True, "stop", "-1000.0000")
        assert (b.ambiguous, b.barrier, str(b.gross_bp)) == (True, "target", "1500.0000")

    def test_stop_and_target_in_different_candles_are_not_ambiguous(self):
        series = [_c(1000, 100, 104, 85, 95), _c(2000, 95, 120, 94, 110)]
        lab = _h0(_k(), series, horizons_ms=[2000], ambiguous_policy="target_first")
        assert (lab.ambiguous, lab.barrier, lab.touch_time_ms) == (False, "stop", 1000)

    def test_policy_does_not_change_unambiguous_labels(self):
        for candle in [(1000, 100, 120, 99, 110), (1000, 100, 105, 85, 90), (1000, 100, 105, 95, 102)]:
            assert _h0(_k(), [_c(*candle)], ambiguous_policy="stop_first") == \
                _h0(_k(), [_c(*candle)], ambiguous_policy="target_first")

    def test_ambiguity_flag_belongs_to_the_touch_candle_only(self):
        series = [_c(1000, 100, 104, 99, 101), _c(2000, 100, 120, 80, 100), _c(3000, 100, 120, 80, 100)]
        lab = _h0(_k(), series, horizons_ms=[3000], ambiguous_policy="stop_first")
        assert (lab.ambiguous, lab.touch_time_ms) == (True, 2000)


# ---------------------------------------------------------------------------
# l'oracolo contro il modulo (ogni campo, ogni orizzonte)
# ---------------------------------------------------------------------------

class TestAgainstOracle:
    SEEDS = range(80)

    def test_every_field_of_every_label_matches_the_oracle(self):
        stats = dict(labels=0, ambiguous=0, incomplete=0, timeout=0, stop=0, target=0, long=0, short=0,
                     equality_touch=0, short_window_complete_long_incomplete=0)
        for seed in self.SEEDS:
            candle_ms, candles, cands, horizons, cost, policy = _random_case(seed)
            got = label_candidates(cands, candles, candle_ms=candle_ms, horizons_ms=horizons,
                                   cost_bp=cost, ambiguous_policy=policy)
            assert len(got) == len(cands)
            for cand, lab in zip(cands, got):
                assert (lab.candidate_id, lab.symbol, lab.side) == (cand.candidate_id, cand.symbol, cand.side)
                assert [h.horizon_ms for h in lab.horizons] == horizons
                for h, hl in zip(horizons, lab.horizons):
                    exp = oracle(cand, candles.get(cand.symbol, []), candle_ms, h, cost, policy)
                    _assert_label_matches_oracle(hl, exp, h)
                    stats["labels"] += 1
                    stats["long" if cand.side == 1 else "short"] += 1
                    if hl.status == "incomplete":
                        stats["incomplete"] += 1
                        continue
                    stats[hl.barrier] += 1
                    stats["ambiguous"] += hl.ambiguous
                    if hl.barrier != "timeout":
                        cn = next(c for c in candles[cand.symbol] if c.open_time_ms == hl.touch_time_ms)
                        level = cand.stop_price if hl.barrier == "stop" else cand.target_price
                        if level in (cn.low, cn.high):
                            stats["equality_touch"] += 1
                if (lab.horizons[0].status == "complete" and lab.horizons[-1].status == "incomplete"):
                    stats["short_window_complete_long_incomplete"] += 1
        # guardie: il confronto prova qualcosa solo se i casi difficili ci sono davvero
        assert stats["labels"] > 500, stats
        for name in ("ambiguous", "incomplete", "timeout", "stop", "target", "long", "short",
                     "equality_touch", "short_window_complete_long_incomplete"):
            assert stats[name] >= 10, (name, stats)

    def test_horizon_consistency_on_random_data(self):
        checked = 0
        for seed in self.SEEDS:
            candle_ms, candles, cands, _h, cost, policy = _random_case(seed)
            horizons = [candle_ms, 2 * candle_ms, 4 * candle_ms, 8 * candle_ms]
            for lab in label_candidates(cands, candles, candle_ms=candle_ms, horizons_ms=horizons,
                                        cost_bp=cost, ambiguous_policy=policy):
                done = [h for h in lab.horizons if h.status == "complete"]
                for i, short in enumerate(done):
                    if short.barrier in ("stop", "target"):
                        for longer in done[i + 1:]:
                            assert (longer.barrier, longer.touch_time_ms, longer.exit_price,
                                    longer.ambiguous, longer.gross_bp, longer.net_bp) == \
                                (short.barrier, short.touch_time_ms, short.exit_price,
                                 short.ambiguous, short.gross_bp, short.net_bp)
                            checked += 1
                # un orizzonte lungo completo implica completi tutti i piu' corti
                statuses = [h.status for h in lab.horizons]
                assert statuses == sorted(statuses, key=lambda s: s != "complete")
        assert checked > 50

    def test_never_stop_at_15_minutes_and_target_at_1_hour(self):
        """La frase del contratto con orizzonti veri (15 min, 1 h, 4 h)."""
        m = 60_000
        series = [_c(i * 5 * m, 100, 104, 99, 101) for i in range(1, 60)]
        series[2] = _c(3 * 5 * m, 100, 104, 85, 90)                               # stop a +15 min
        series[8] = _c(9 * 5 * m, 100, 130, 99, 120)                              # obiettivo dopo
        res = label_candidates([_k(ts=m)], {"BTC": series}, candle_ms=5 * m,
                               horizons_ms=[15 * m, 60 * m, 240 * m], cost_bp=D(0),
                               ambiguous_policy="stop_first")[0].horizons
        assert [(h.barrier, h.touch_time_ms) for h in res] == [("stop", 3 * 5 * m)] * 3


# ---------------------------------------------------------------------------
# invarianti
# ---------------------------------------------------------------------------

class TestInvariants:
    def _case(self):
        candle_ms, candles, cands, horizons, cost, policy = _random_case(7)
        return dict(candles=candles, cands=cands,
                    kw=dict(candle_ms=candle_ms, horizons_ms=horizons, cost_bp=cost, ambiguous_policy=policy))

    def test_candidate_order_does_not_change_any_label(self):
        c = self._case()
        ref = {r.candidate_id: r for r in label_candidates(c["cands"], c["candles"], **c["kw"])}
        assert len(ref) == len(c["cands"]) >= 3
        for s in range(5):
            shuffled = c["cands"][:]
            random.Random(s).shuffle(shuffled)
            out = label_candidates(shuffled, c["candles"], **c["kw"])
            assert [r.candidate_id for r in out] == [x.candidate_id for x in shuffled]
            assert {r.candidate_id: r for r in out} == ref

    def test_inputs_are_not_modified(self):
        c = self._case()
        cands, candles = c["cands"][:], {k: v[:] for k, v in c["candles"].items()}
        label_candidates(c["cands"], c["candles"], **c["kw"])
        assert c["cands"] == cands and all(a is b for a, b in zip(c["cands"], cands))
        assert c["candles"] == candles
        horizons = list(c["kw"]["horizons_ms"])
        assert c["kw"]["horizons_ms"] == horizons

    def test_deterministic(self):
        c = self._case()
        assert label_candidates(c["cands"], c["candles"], **c["kw"]) == \
            label_candidates(c["cands"], c["candles"], **c["kw"])

    def test_accepts_tuples_and_lists(self):
        c = self._case()
        a = label_candidates(c["cands"], c["candles"], **c["kw"])
        b = label_candidates(tuple(c["cands"]), {k: tuple(v) for k, v in c["candles"].items()}, **c["kw"])
        assert a == b
        kw = dict(c["kw"], horizons_ms=tuple(c["kw"]["horizons_ms"]))
        assert label_candidates(c["cands"], c["candles"], **kw) == a

    def test_ambient_decimal_context_does_not_change_the_result_nor_leak(self):
        candle_ms, candles, cands, horizons, cost, policy = _random_case(11)
        kw = dict(candle_ms=candle_ms, horizons_ms=horizons, cost_bp=cost, ambiguous_policy=policy)
        # prezzo con molte cifre: il risultato dipende dalla precisione di lavoro
        cands = cands + [_k("long-digits", "BTC", 1, 1, "333.333333333333333333333", "300", "400")]
        ref = label_candidates(cands, candles, **kw)
        with localcontext() as ctx:
            ctx.prec = 5
            ctx.rounding = ROUND_UP
            assert label_candidates(cands, candles, **kw) == ref
            assert getcontext().prec == 5 and getcontext().rounding == ROUND_UP        # non toccato
        assert getcontext().prec == 28

    def test_candle_index_is_built_once_per_symbol_not_per_candidate(self):
        class Counting(dict):
            gets = 0

            def get(self, key, default=None):
                type(self).gets += 1
                return super().get(key, default)
        series = [_c(1000 * i, 100, 104, 99, 101) for i in range(1, 30)]
        candles = Counting({"BTC": series, "ETH": series})
        cands = [_k(f"c{i}", "BTC" if i % 2 else "ETH", 1, 500 + i) for i in range(40)]
        label_candidates(cands, candles, **KW)
        assert Counting.gets == 2

    def test_numeric_out_of_range_has_its_own_code(self):
        cand = Candidate("c1", "BTC", 1, 500, D("1E-900000"), D("1E-900001"), D("2E+10"))
        candles = {"BTC": [Candle(1000, D("1E-900000"), D("3E+10"), D("1E-900000"), D("1E-900000"))]}
        with pytest.raises(ValueError) as ei:
            _lab([cand], candles)
        assert str(ei.value) == "numeric_out_of_range"


# ---------------------------------------------------------------------------
# validazione: codici esatti, ordine, ogni elemento, input ostili
# ---------------------------------------------------------------------------

GOOD_CANDLES = {"BTC": [_c(1000, 100, 105, 95, 102), _c(2000, 102, 106, 98, 104)]}
GOOD_CANDS = [_k("a"), _k("b", side=-1)]


def _err(**over) -> str:
    args = dict(candidates=GOOD_CANDS, candles=GOOD_CANDLES, **KW)
    args.update(over)
    with pytest.raises(ValueError) as ei:
        label_candidates(args.pop("candidates"), args.pop("candles"), **args)
    return str(ei.value)


# (override, codice) nell'ordine del contratto
ORDERED = [
    (dict(candle_ms=0), "invalid_candle_ms"),
    (dict(horizons_ms=[]), "invalid_horizons"),
    (dict(cost_bp=D("-1")), "invalid_cost_bp"),
    (dict(ambiguous_policy="maybe"), "invalid_ambiguous_policy"),
    (dict(candidates=[None]), "invalid_candidate"),
    (dict(candles=[]), "invalid_candles"),
]


class TestValidation:
    def test_control_valid_call_succeeds(self):
        assert len(label_candidates(GOOD_CANDS, GOOD_CANDLES, **KW)) == 2

    @pytest.mark.parametrize("override,code", ORDERED)
    def test_exact_codes(self, override, code):
        assert _err(**override) == code

    @pytest.mark.parametrize("i,j", list(itertools.combinations(range(6), 2)))
    def test_first_failing_check_in_contract_order_wins(self, i, j):
        merged = {**ORDERED[i][0], **ORDERED[j][0]}
        assert _err(**merged) == ORDERED[i][1]

    @pytest.mark.parametrize("bad", [True, False, 0, -1, 1.0, "1000", None, D("1000")])
    def test_candle_ms(self, bad):
        assert _err(candle_ms=bad) == "invalid_candle_ms"

    @pytest.mark.parametrize("bad", [
        [], (), None, 1000, "1000", {1000}, (h for h in [1000]), iter([1000]), b"x",
        [True], [0], [-1000], [500], [1000, 1000], [2000, 1000], [1000.0], [D(1000)], ["1000"], [None],
        [1000, 1500], [1000, True], [1000, 2000, 2000]])
    def test_horizons(self, bad):
        assert _err(horizons_ms=bad) == "invalid_horizons"

    @pytest.mark.parametrize("ok", [[1000], (1000,), [1000, 2000, 5000], [3000]])
    def test_horizons_valid(self, ok):
        assert len(label_candidates(GOOD_CANDS, GOOD_CANDLES, **{**KW, "horizons_ms": ok})) == 2

    @pytest.mark.parametrize("bad", [
        10.0, 10, "10", None, True, D("NaN"), D("sNaN"), D("Infinity"), D("-Infinity"), D("-0.0001")])
    def test_cost_bp(self, bad):
        assert _err(cost_bp=bad) == "invalid_cost_bp"

    def test_cost_bp_zero_is_valid(self):
        assert len(label_candidates(GOOD_CANDS, GOOD_CANDLES, **{**KW, "cost_bp": D(0)})) == 2

    @pytest.mark.parametrize("bad", [None, "", "stop", "STOP_FIRST", "stop_first ", ["stop_first"], True, 1,
                                     "mid", "both", "first", "target", "stop_last", "worst_case", "best_case"])
    def test_ambiguous_policy(self, bad):
        assert _err(ambiguous_policy=bad) == "invalid_ambiguous_policy"

    # --- candidates -------------------------------------------------------
    @pytest.mark.parametrize("bad", [
        None, 5, "abc", b"abc", {_k()}, {"a": _k()}, iter([_k()]), (k for k in [_k()]), frozenset([_k()]), 1.5])
    def test_candidates_must_be_a_sequence_never_an_iterator(self, bad):
        """Un generatore validato verrebbe consumato e il calcolo vedrebbe zero candidati."""
        assert _err(candidates=bad) == "invalid_candidate"

    @pytest.mark.parametrize("bad_item", [None, "x", 5, {"id": 1}, object()])
    def test_every_element_is_checked_wherever_it_sits(self, bad_item):
        for pos in (0, 1, 2):
            cands = [_k("a"), _k("b")]
            cands.insert(pos, bad_item)
            assert _err(candidates=cands) == "invalid_candidate"

    @pytest.mark.parametrize("over", [
        dict(cid=""), dict(cid="-x"), dict(cid="_x"), dict(cid=" x"), dict(cid="a b"), dict(cid="a/b"),
        dict(cid="x" * 129), dict(cid="c1\n"), dict(cid="\nc1"), dict(cid="è"), dict(cid=None), dict(cid=5),
        dict(sym=""), dict(sym=None), dict(sym=5),
        dict(side=0), dict(side=2), dict(side=-2), dict(side=True), dict(side=1.0), dict(side="1"), dict(side=None),
        dict(ts=0), dict(ts=-1), dict(ts=True), dict(ts=1.5), dict(ts=None), dict(ts="500"),
        dict(entry=D("NaN")), dict(entry=D("sNaN")), dict(entry=D("Infinity")), dict(entry=D(0)), dict(entry=D(-1)),
        dict(entry=100.0), dict(entry=100), dict(entry="100"), dict(entry=None),
        dict(stop=D("NaN")), dict(stop=D(0)), dict(stop=D(-90)), dict(stop=90.0), dict(stop=None), dict(stop=D("Infinity")),
        dict(target=D("NaN")), dict(target=D(0)), dict(target=D(-115)), dict(target=115.0), dict(target=None),
        dict(target=D("Infinity")),
        dict(stop=D(100)), dict(stop=D(101)), dict(target=D(100)), dict(target=D(99)),         # lato sbagliato (long)
        dict(side=-1, stop=D(100)), dict(side=-1, stop=D(90)), dict(side=-1, target=D(100)), dict(side=-1, target=D(115)),
    ])
    def test_invalid_candidate_fields_at_any_position(self, over):
        kw = dict(cid="bad", sym="BTC", side=1, ts=500, entry=D(100), stop=D(90), target=D(115))
        kw.update(over)
        if kw["side"] == -1:
            kw.setdefault("stop", D(110))
            if "stop" not in over:
                kw["stop"] = D(110)
            if "target" not in over:
                kw["target"] = D(85)
        bad = Candidate(kw["cid"], kw["sym"], kw["side"], kw["ts"], kw["entry"], kw["stop"], kw["target"])
        for pos in (0, 2):
            cands = [_k("a"), _k("b")]
            cands.insert(pos, bad)
            assert _err(candidates=cands) == "invalid_candidate", over

    def test_valid_extremes_are_accepted(self):
        ok = [_k("x" * 128), _k("A.b_c-d:e", side=-1), _k("0", ts=1)]
        assert len(label_candidates(ok, GOOD_CANDLES, **KW)) == 3

    def test_duplicate_candidate_id(self):
        assert _err(candidates=[_k("a"), _k("b"), _k("a", side=-1)]) == "invalid_candidate"

    # --- candles ----------------------------------------------------------
    @pytest.mark.parametrize("bad", [None, [], [GOOD_CANDLES], "BTC", 5, (c for c in []), {1, 2}, [("BTC", [])]])
    def test_candles_must_be_a_mapping(self, bad):
        assert _err(candles=bad) == "invalid_candles"

    @pytest.mark.parametrize("bad_series", [
        None, 5, set(GOOD_CANDLES["BTC"]), (c for c in GOOD_CANDLES["BTC"]),
        iter(GOOD_CANDLES["BTC"]), "abc", {1: 2},
        # un insieme/frozenset di UNA sola candela e' valido come contenuto: solo il tipo lo respinge
        {GOOD_CANDLES["BTC"][0]}, frozenset(GOOD_CANDLES["BTC"][:1])])
    def test_each_series_must_be_a_sequence_never_an_iterator(self, bad_series):
        assert _err(candles={"BTC": bad_series}) == "invalid_candles"

    def test_keys_must_be_strings(self):
        assert _err(candles={5: GOOD_CANDLES["BTC"]}) == "invalid_candles"
        assert _err(candles={None: []}) == "invalid_candles"

    @staticmethod
    def _series_with(pos, **over):
        """Tre candele valide (1000, 2000, 3000) con quella in `pos` modificata SOLO nei campi dati.
        L'orario resta quello dello slot: cosi' l'unico difetto e' quello dichiarato (un orario
        duplicato o fuori ordine farebbe fallire la serie per un altro motivo e nasconderebbe
        l'assenza del controllo specifico)."""
        series = [_c(t, 100, 105, 95, 102) for t in (1000, 2000, 3000)]
        fields = dict(open_time_ms=1000 * (pos + 1), open=D(100), high=D(105), low=D(95), close=D(102))
        fields.update(over)
        series[pos] = Candle(**fields)
        return series

    @pytest.mark.parametrize("pos", [0, 1, 2])
    def test_control_a_series_with_no_defect_is_valid(self, pos):
        series = self._series_with(pos)
        res = label_candidates([_k()], {"BTC": series}, **{**KW, "horizons_ms": [1000, 3000]})
        assert [h.status for h in res[0].horizons] == ["complete", "complete"]

    @pytest.mark.parametrize("bad_element", [None, "x", 5, (1000, 100, 105, 95, 102), {"open_time_ms": 1000}, object()])
    def test_elements_that_are_not_candles(self, bad_element):
        for pos in (0, 1, 2):
            series = self._series_with(pos)
            series[pos] = bad_element
            assert _err(candles={"BTC": series}) == "invalid_candles"

    @pytest.mark.parametrize("over", [
        dict(open=D("NaN")), dict(high=D("NaN")), dict(low=D("NaN")), dict(close=D("NaN")),
        dict(open=D("sNaN")), dict(high=D("Infinity")), dict(low=D("-Infinity")),
        dict(open=D(0)), dict(low=D(0)), dict(high=D(0)), dict(close=D(0)),
        dict(open=D(-1)), dict(close=D(-102)),
        dict(open=100.0), dict(high=105), dict(close="102"), dict(low=None), dict(open=None),
        dict(high=D(94), low=D(95)),                       # high < low
        dict(low=D(101)),                                  # low > open
        dict(open=D(103), close=D(100), low=D(101)),       # low > close
        dict(high=D(99)),                                  # high < open
        dict(high=D(101)),                                 # high < close
        dict(open_time_ms=1500),                           # fuori griglia
        dict(open_time_ms=1000.0), dict(open_time_ms=None), dict(open_time_ms="1000"),
        dict(open_time_ms=-1000),
    ], ids=lambda o: ",".join(f"{k}={v!r}" for k, v in o.items()))
    def test_every_candle_is_checked_wherever_it_sits(self, over):
        for pos in (0, 1, 2):
            assert _err(candles={"BTC": self._series_with(pos, **over)}) == "invalid_candles", pos

    def test_open_time_must_be_a_real_int_even_when_the_grid_would_accept_it(self):
        for bad in (True, 2.0, 2):
            candle = Candle(bad, D(100), D(105), D(95), D(102))
            if type(bad) is int:                                       # controllo: 2 e' valido
                assert len(label_candidates(GOOD_CANDS, {"BTC": [candle]}, **{**KW, "candle_ms": 1, "horizons_ms": [1]})) == 2
            else:
                assert _err(candles={"BTC": [candle]}, candle_ms=1, horizons_ms=[1]) == "invalid_candles"

    def test_horizon_must_be_a_real_int_even_when_the_grid_would_accept_it(self):
        assert _err(candle_ms=1, horizons_ms=[True]) == "invalid_horizons"
        assert _err(candle_ms=1, horizons_ms=[2.0]) == "invalid_horizons"
        assert len(label_candidates(GOOD_CANDS, GOOD_CANDLES, **{**KW, "candle_ms": 1, "horizons_ms": [2]})) == 2

    def test_candles_of_an_unreferenced_symbol_are_validated_too(self):
        bad = {"BTC": GOOD_CANDLES["BTC"], "XRP": [Candle(1000, D("NaN"), D(5), D(4), D(4))]}
        assert _err(candles=bad) == "invalid_candles"

    def test_series_must_be_strictly_increasing(self):
        a, b = _c(1000, 100, 105, 95, 102), _c(2000, 102, 106, 98, 104)
        assert _err(candles={"BTC": [a, a]}) == "invalid_candles"
        assert _err(candles={"BTC": [b, a]}) == "invalid_candles"
        assert _err(candles={"BTC": [a, b, a]}) == "invalid_candles"

    def test_candles_must_sit_on_the_candle_grid(self):
        assert _err(candles={"BTC": [_c(1500, 100, 105, 95, 102)]}) == "invalid_candles"
        assert _err(candles={"BTC": [_c(1001, 100, 105, 95, 102)]}, candle_ms=1000) == "invalid_candles"

    def test_valid_extremes_are_accepted_by_candles(self):
        doji = _c(0, 100, 100, 100, 100)                     # open_time 0 e doji: validi
        assert len(label_candidates([_k(ts=1)], {"BTC": [doji], "ETH": [], "SOL": ()}, **KW)) == 1
        assert _lab([], {"BTC": []}) == ()

    def test_candidate_errors_come_before_candle_errors(self):
        assert _err(candidates=[None], candles=[]) == "invalid_candidate"

    def test_a_mapping_that_is_not_a_dict_is_accepted(self):
        class M(Mapping):
            def __getitem__(self, k): return GOOD_CANDLES[k]
            def __iter__(self): return iter(GOOD_CANDLES)
            def __len__(self): return len(GOOD_CANDLES)
        assert len(label_candidates(GOOD_CANDS, M(), **KW)) == 2


# ---------------------------------------------------------------------------
# contratto pubblico e purezza
# ---------------------------------------------------------------------------

class TestPublicContractAndPurity:
    def test_dataclass_fields_and_frozen(self):
        names = lambda cls: [f.name for f in dataclasses.fields(cls)]      # noqa: E731
        assert names(Candle) == ["open_time_ms", "open", "high", "low", "close"]
        assert names(Candidate) == ["candidate_id", "symbol", "side", "signal_time_ms", "entry_price",
                                    "stop_price", "target_price"]
        assert names(HorizonLabel) == ["horizon_ms", "status", "barrier", "ambiguous", "touch_time_ms",
                                       "exit_price", "gross_bp", "net_bp"]
        assert names(OpportunityLabel) == ["candidate_id", "symbol", "side", "horizons"]
        for obj in (_c(1000, 1, 1, 1, 1), _k(), _h0(_k(), [_c(1000, 100, 105, 95, 102)])):
            with pytest.raises(dataclasses.FrozenInstanceError):
                setattr(obj, dataclasses.fields(obj)[0].name, 0)

    def test_signature_has_no_defaults_for_model_choices(self):
        params = inspect.signature(label_candidates).parameters
        assert list(params) == ["candidates", "candles", "candle_ms", "horizons_ms", "cost_bp", "ambiguous_policy"]
        for name in ("candle_ms", "horizons_ms", "cost_bp", "ambiguous_policy"):
            assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
            assert params[name].default is inspect.Parameter.empty, name
        with pytest.raises(TypeError):
            label_candidates(GOOD_CANDS, GOOD_CANDLES)                             # type: ignore[call-arg]
        with pytest.raises(TypeError):
            label_candidates(GOOD_CANDS, GOOD_CANDLES, 1000, [1000], D(0), "stop_first")   # type: ignore[call-arg]

    def test_module_is_pure_stdlib_no_io_no_clock_no_random_no_float(self):
        src = Path(op.__file__).read_text()
        tree = ast.parse(src)
        allowed = {"__future__", "re", "collections.abc", "dataclasses", "decimal", "typing"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        assert imported <= allowed, imported - allowed
        # solo i nomi LETTI: il campo `open: Decimal` di Candle e' un nome in scrittura, non la funzione open()
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        assert not names & {"float", "open", "print", "input", "exec", "eval", "__import__", "random", "time"}
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, float)]

    def test_no_modeling_constant_hardcoded(self):
        tree = ast.parse(Path(op.__file__).read_text())
        nums = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)}
        assert nums <= {-1, 0, 1, 60, 128, 10000}, nums          # 10000 = bp, 60 = cifre del contesto, 128 = id
