"""F7 / P4 — expectancy per cella: verifica INDIPENDENTE (Claude) del modulo di Grok.

Perche' un secondo file di test: quelli di Grok (test_brain_f7_expectancy.py)
usano solo confidence=0.9 / n_boot=200, dove la regola degli indici percentile
"floor / ceil-1" e quella con arrotondamento half-even danno lo stesso numero:
non possono accorgersi della differenza. Qui:

* un ORACOLO riscritto dal testo del contratto con ``fractions.Fraction``
  (aritmetica esatta, nessun codice condiviso col modulo) verifica ogni numero
  dell'intervallo, per piu' confidence / n_boot / seed;
* gli indici percentile sono verificati anche da soli, con valori calcolati a mano;
* controlli con input validi (se il controllo non passa, il test non prova nulla),
  codici d'errore ESATTI, input ostili, invarianti (ordine, seed, contesto Decimal,
  PYTHONHASHSEED), formato esatto, purezza del modulo;
* un test con i produttori VERI: BrainEngine -> execute_paper -> close_paper ->
  extract_outcomes -> cell_stats, con i numeri attesi ricavati in forma chiusa.
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import itertools
import os
import random
import subprocess
import sys
import tempfile
from decimal import ROUND_UP, Decimal, localcontext
from fractions import Fraction
from math import ceil, floor
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.v3.brain_f2.analyst import MockDeepSeekAnalyst
from backend.v3.brain_f2.contracts import (
    BrainDecision, DecisionKind, MarketContext, OpenProposal, ProposalStatus,
)
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot, _policy_hash
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.events import EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.executor.paper_close import close_paper
from backend.v3.learning import expectancy as ex
from backend.v3.learning.expectancy import CellStats, cell_stats, default_cell_key, format_cells
from backend.v3.outcomes import LINK_STATUSES, TradeOutcome, extract_outcomes
from backend.v3.risk import RiskPolicy, RiskQuote

D = Decimal
DAY = 86_400_000
T0 = 20_000 * DAY               # mezzanotte UTC: i giorni si contano da qui
_ids = itertools.count(1)

BASE = dict(min_trades=1, min_days=2, confidence=D("0.9"), n_boot=200, seed=1)


# ---------------------------------------------------------------------------
# costruzione dei dati
# ---------------------------------------------------------------------------

def _o(day=0, net="100", *, ms=0, costs="20", r="1.5", symbol="BTCUSDT", side=1,
       regime="TRENDING", reason="brain_close", link="linked", **over) -> TradeOutcome:
    """TradeOutcome valido costruito a mano (e' un dataclass pubblico)."""
    net_d = D(net)
    closed = T0 + day * DAY + ms
    realized = D("1") if net_d > 0 else (D("-1") if net_d < 0 else D("0"))
    base = dict(
        schema_version=1, position_id=f"p{next(_ids)}", portfolio_id="hawk", run_id="r",
        symbol=symbol, side=side, originating_ai="deepseek", leverage=5,
        opened_at_ms=closed - 60_000, closed_at_ms=closed, hold_ms=60_000,
        entry_price=D("100"), exit_price=D("101"), quantity=D("1"), notional_entry=D("100"),
        margin_used=D("20"), gross_pnl=D("1"), fees=D("0.2"), realized_pnl=realized,
        gross_bp=net_d + D(costs), costs_bp=D(costs), net_bp=net_d,
        stop_distance_bp=D("100"), r_multiple=None if r is None else D(r),
        exit_reason=reason, loss_exceeds_margin=False, decision_event_id="d1",
        link_status=link, decision_regime=regime)
    base.update(over)
    return TradeOutcome(**base)


def _cs(outs, **kw):
    return cell_stats(outs, **{**BASE, **kw})


def _cell(outs, **kw) -> CellStats:
    cells = _cs(outs, **kw)
    assert len(cells) == 1, cells
    return cells[0]


def _dataset(seed: int, n_days: int, max_per_day: int = 4) -> list[TradeOutcome]:
    """Dati sintetici ripetibili: piu' trade per giorno, 4 decimali, r a volte None."""
    rng = random.Random(seed)
    out = []
    for d in range(n_days):
        for _ in range(rng.randint(1, max_per_day)):
            out.append(_o(d, D(rng.randint(-300000, 300000)).scaleb(-4),
                          ms=rng.randint(0, DAY - 1),
                          costs=D(rng.randint(500, 3000)).scaleb(-2),
                          r=None if rng.random() < 0.3 else D(rng.randint(-300, 300)).scaleb(-2)))
    return out


# ---------------------------------------------------------------------------
# ORACOLO: riscritto dal testo del contratto, esatto (Fraction), senza codice del modulo
# ---------------------------------------------------------------------------

def _q4(x: Fraction) -> Decimal:
    """Arrotonda a 4 decimali half-even con soli interi (indipendente da Decimal.quantize)."""
    scaled = x * 10000
    q, rem = divmod(scaled.numerator, scaled.denominator)
    twice = 2 * rem
    if twice > scaled.denominator or (twice == scaled.denominator and q % 2 == 1):
        q += 1
    return D(q).scaleb(-4)


def _exp_simple(trades) -> dict:
    nets = sorted(Fraction(t.net_bp) for t in trades)
    n = len(nets)
    med = nets[n // 2] if n % 2 else (nets[n // 2 - 1] + nets[n // 2]) / 2
    rs = [Fraction(t.r_multiple) for t in trades if t.r_multiple is not None]
    return dict(
        n=n, n_days=len({t.closed_at_ms // DAY for t in trades}),
        mean_net_bp=_q4(sum(nets) / n), median_net_bp=_q4(med),
        mean_costs_bp=_q4(sum(Fraction(t.costs_bp) for t in trades) / n),
        mean_r=_q4(sum(rs) / len(rs)) if rs else None,
        win_rate=_q4(Fraction(sum(1 for t in trades if t.realized_pnl > 0), n)))


def _boot_means(trades, nb: int, seed: int, key) -> list[Fraction]:
    by_day: dict[int, list[Fraction]] = {}
    for t in trades:
        by_day.setdefault(t.closed_at_ms // DAY, []).append(Fraction(t.net_bp))
    days = sorted(by_day)
    rng = random.Random(f"{seed}|{key!r}")
    means = []
    for _ in range(nb):
        chosen = [days[rng.randrange(len(days))] for _ in range(len(days))]
        vals = [v for d in chosen for v in by_day[d]]
        means.append(sum(vals) / len(vals))
    return sorted(means)


def _oracle_idx(conf: str, nb: int) -> tuple[int, int]:
    alpha = 1 - Fraction(D(conf))
    return floor(alpha / 2 * nb), ceil((1 - alpha / 2) * nb) - 1


def _oracle_ci(trades, conf: str, nb: int, seed: int, key):
    means = _boot_means(trades, nb, seed, key)
    lo, hi = _oracle_idx(conf, nb)
    return _q4(means[lo]), _q4(means[hi]), means, lo, hi


def _oracle_status(lo: Decimal, hi: Decimal) -> str:
    return "positive" if lo > 0 else ("negative" if hi < 0 else "inconclusive")


KEY0 = ("BTCUSDT", 1, "TRENDING", False)      # chiave di default degli _o() standard


def _assert_matches_oracle(cell: CellStats, trades, conf: str, nb: int, seed: int, key=KEY0):
    lo, hi, _m, _l, _h = _oracle_ci(trades, conf, nb, seed, key)
    for name, value in _exp_simple(trades).items():
        assert getattr(cell, name) == value, name
    assert cell.key == key
    assert (cell.ci_low, cell.ci_high) == (lo, hi)
    assert cell.status == _oracle_status(lo, hi)


# ---------------------------------------------------------------------------
# l'oracolo stesso: se e' sbagliato, tutto il resto non prova nulla
# ---------------------------------------------------------------------------

class TestOracleSelfCheck:
    @pytest.mark.parametrize("num,den,expected", [
        (1, 3, "0.3333"), (2, 3, "0.6667"), (5, 20000, "0.0002"),     # 0.00025 -> pari
        (15, 100000, "0.0002"), (35, 100000, "0.0004"),                # 0.00015 -> 0.0002 ; 0.00035 -> 0.0004
        (-25, 100000, "-0.0002"), (0, 1, "0.0000"), (91, 10, "9.1000"),
    ])
    def test_half_even(self, num, den, expected):
        assert str(_q4(Fraction(num, den))) == expected

    def test_oracle_indexes_hand_values(self):
        assert _oracle_idx("0.95", 300) == (7, 292)       # 7.5 -> floor 7 ; 292.5 -> ceil 293 - 1
        assert _oracle_idx("0.9", 200) == (10, 189)


# ---------------------------------------------------------------------------
# indici percentile: floor / ceil-1 (la regola che l'arrotondamento half-even viola)
# ---------------------------------------------------------------------------

class TestPercentileIndexes:
    @pytest.mark.parametrize("conf,nb,expected", [
        ("0.95", 300, (7, 292)),     # alpha/2*n = 7.5   (half-even darebbe 8 e 291)
        ("0.95", 220, (5, 214)),     # 5.5               (half-even darebbe 6 e 213)
        ("0.9", 200, (10, 189)),     # esatto: i due metodi coincidono
        ("0.9", 201, (10, 190)),     # 10.05 / 190.95
        ("0.8", 250, (25, 224)),
        ("0.95", 1000, (25, 974)),
        ("0.99", 250, (1, 248)),     # 1.25
        ("0.5", 201, (50, 150)),
    ])
    def test_hand_values(self, conf, nb, expected):
        assert ex._percentile_indexes(D(conf), nb) == expected

    def test_symmetry_and_range_for_many_inputs(self):
        for conf in ("0.0001", "0.1", "0.5", "0.6827", "0.8", "0.9", "0.95", "0.99", "0.9999"):
            for nb in (200, 201, 250, 299, 300, 1000, 1001):
                lo, hi = ex._percentile_indexes(D(conf), nb)
                assert 0 <= lo <= hi < nb, (conf, nb, lo, hi)
                assert hi == nb - 1 - lo, (conf, nb)
                assert (lo, hi) == _oracle_idx(conf, nb)


# ---------------------------------------------------------------------------
# controllo + numeri calcolati a mano
# ---------------------------------------------------------------------------

class TestControlAndHandNumbers:
    def test_control_three_statuses(self):
        """Controllo: input validi producono davvero i tre stati attesi."""
        pos = [_o(i, "100") for i in range(6)]
        neg = [_o(i, "-100") for i in range(6)]
        mixed = [_o(i, "100" if i % 2 else "-100") for i in range(6)]
        assert _cell(pos).status == "positive"
        assert _cell(neg).status == "negative"
        assert _cell(mixed).status == "inconclusive"

    def _hand(self):
        return [
            _o(0, "10", r="1"), _o(0, "20", r=None), _o(1, "-30", r="-1"),
            _o(1, "40", r="2"), _o(2, "5.5", r="3"),
        ]

    def test_hand_example_odd_n_exact_strings(self):
        c = _cell(self._hand())
        assert (c.n, c.n_days) == (5, 3)
        assert str(c.mean_net_bp) == "9.1000"          # 45.5 / 5
        assert str(c.median_net_bp) == "10.0000"       # -30 5.5 [10] 20 40
        assert str(c.mean_costs_bp) == "20.0000"
        assert str(c.mean_r) == "1.2500"               # (1 -1 2 3) / 4: il None non conta
        assert str(c.win_rate) == "0.8000"             # 4 vittorie su 5
        assert c.key == KEY0

    def test_hand_example_even_n_exact_strings(self):
        c = _cell(self._hand() + [_o(2, "4.5", r="0")])
        assert (c.n, c.n_days) == (6, 3)
        assert str(c.mean_net_bp) == "8.3333"          # 50 / 6
        assert str(c.median_net_bp) == "7.7500"        # (5.5 + 10) / 2
        assert str(c.mean_r) == "1.0000"               # (1 -1 2 3 0) / 5
        assert str(c.win_rate) == "0.8333"             # 5 / 6

    def test_even_median_rounds_half_even_not_half_up(self):
        # (0.0002 + 0.0003) / 2 = 0.00025 -> 0.0002 (pari); half-up darebbe 0.0003
        c = _cell([_o(0, "0.0002"), _o(1, "0.0003")])
        assert str(c.median_net_bp) == "0.0002"
        c = _cell([_o(0, "0.0001"), _o(1, "0.0002")])      # 0.00015 -> 0.0002
        assert str(c.median_net_bp) == "0.0002"
        c = _cell([_o(0, "0.0003"), _o(1, "0.0004")])      # 0.00035 -> 0.0004
        assert str(c.median_net_bp) == "0.0004"

    def test_mean_r_is_none_when_no_trade_has_r(self):
        assert _cell([_o(0, r=None), _o(1, r=None)]).mean_r is None

    def test_no_negative_zero_in_the_report(self):
        c = _cell([_o(0, "-0.00004"), _o(1, "-0.00004")])
        assert str(c.mean_net_bp) == "0.0000" and str(c.ci_high) == "0.0000"

    def test_win_rate_counts_net_wins_not_gross(self):
        """is_win guarda il netto (realized_pnl): lordo positivo ma netto negativo non e' una vittoria."""
        c = _cell([_o(0, "-3", gross_pnl=D("1"), realized_pnl=D("-0.1")), _o(1, "5")])
        assert str(c.win_rate) == "0.5000"


# ---------------------------------------------------------------------------
# l'intervallo contro l'oracolo esatto
# ---------------------------------------------------------------------------

class TestIntervalAgainstOracle:
    @pytest.mark.parametrize("conf,nb,seed,n_days", [
        ("0.9", 200, 1, 6),
        ("0.95", 300, 7, 8),      # 7.5: floor != half-even
        ("0.95", 220, 3, 12),     # 5.5: floor != half-even
        ("0.8", 250, 11, 5),
        ("0.99", 1000, 5, 10),
        ("0.5", 201, 9, 4),
        ("0.6827", 400, 21, 9),
    ])
    def test_every_number_matches_the_oracle(self, conf, nb, seed, n_days):
        trades = _dataset(100 + seed, n_days)
        c = _cell(trades, confidence=D(conf), n_boot=nb, seed=seed)
        _assert_matches_oracle(c, trades, conf, nb, seed)

    @pytest.mark.parametrize("conf,nb,seed", [("0.95", 300, 7), ("0.95", 220, 3)])
    def test_dataset_discriminates_the_index_rule(self, conf, nb, seed):
        """Guardia: sul dataset usato, scambiare floor/ceil con half-even cambia davvero il numero."""
        trades = _dataset(100 + seed, 8)
        _lo, _hi, means, lo, hi = _oracle_ci(trades, conf, nb, seed, KEY0)
        assert means[lo] != means[lo + 1], "dataset inutile: ci_low non cambierebbe"
        assert means[hi] != means[hi - 1], "dataset inutile: ci_high non cambierebbe"

    def test_blocks_of_days_not_single_trades(self):
        """Un giorno con tanti trade pesa come UN blocco: il bootstrap per trade darebbe un altro intervallo."""
        trades = [_o(0, "80", ms=i) for i in range(8)]                 # 8 trade, un solo giorno
        trades += [_o(d, str(-20 - d)) for d in range(1, 7)]           # 6 giorni da un trade
        c = _cell(trades, confidence=D("0.8"), n_boot=300, seed=4)
        _assert_matches_oracle(c, trades, "0.8", 300, 4)

        vals = [Fraction(t.net_bp) for t in trades]                    # bootstrap per trade, stesso rng
        rng = random.Random(f"4|{KEY0!r}")
        tm = sorted(sum(vals[rng.randrange(len(vals))] for _ in vals) / len(vals) for _ in range(300))
        lo, hi = _oracle_idx("0.8", 300)
        assert (_q4(tm[lo]), _q4(tm[hi])) != (c.ci_low, c.ci_high), "il test non distingue blocchi da trade"

    def test_constant_return_collapses_the_interval(self):
        trades = [_o(0, "50"), _o(0, "50", ms=5), _o(1, "50"), _o(2, "50"), _o(2, "50", ms=9)]
        c = _cell(trades)
        assert str(c.ci_low) == str(c.ci_high) == "50.0000"
        assert c.status == "positive"

    def test_cell_does_not_depend_on_other_cells(self):
        """Ogni cella ha il suo generatore (seme + chiave): la presenza di altre celle non lo sposta."""
        a = _dataset(1, 7)
        b = [_o(t.closed_at_ms // DAY - 20_000, t.net_bp, symbol="ETHUSDT") for t in _dataset(2, 7)]
        alone = _cell(a, n_boot=250, seed=3)
        both = {c.key: c for c in _cs(a + b, n_boot=250, seed=3)}
        assert both[KEY0] == alone
        _assert_matches_oracle(both[("ETHUSDT", 1, "TRENDING", False)], b, "0.9", 250, 3,
                               key=("ETHUSDT", 1, "TRENDING", False))


# ---------------------------------------------------------------------------
# il win rate non decide; soglie dello stato
# ---------------------------------------------------------------------------

class TestStatusIsNotWinRate:
    def test_90_percent_wins_but_negative(self):
        # 36 giorni da +1 e 4 giorni da -1000: win rate 0.9, media netta molto negativa.
        # P(nessun giorno perdente nel campione) = 0.9^40 = 1.5% < 5%: l'intervallo e' tutto sotto zero
        trades = [_o(d, "1") for d in range(36)] + [_o(36 + d, "-1000") for d in range(4)]
        c = _cell(trades, n_boot=400, seed=1)
        assert str(c.win_rate) == "0.9000" and c.mean_net_bp < 0
        assert c.status == "negative"
        _assert_matches_oracle(c, trades, "0.9", 400, 1)

    def test_10_percent_wins_but_positive(self):
        trades = [_o(d, "-1") for d in range(36)] + [_o(36 + d, "1000") for d in range(4)]
        c = _cell(trades, n_boot=400, seed=1)
        assert str(c.win_rate) == "0.1000" and c.mean_net_bp > 0
        assert c.status == "positive"
        _assert_matches_oracle(c, trades, "0.9", 400, 1)

    def test_nine_small_wins_one_big_loss_is_never_positive(self):
        trades = [_o(d, "10") for d in range(9)] + [_o(9, "-200")]
        c = _cell(trades)
        assert str(c.win_rate) == "0.9000" and c.mean_net_bp < 0 and c.status != "positive"

    def test_zero_return_is_inconclusive_not_positive_or_negative(self):
        c = _cell([_o(d, "0") for d in range(5)])
        assert (str(c.ci_low), str(c.ci_high), c.status) == ("0.0000", "0.0000", "inconclusive")

    def test_status_follows_the_reported_four_decimal_values(self):
        """0.00004 si riporta come 0.0000: lo stato non puo' dire 'positive' con ci_low = 0.0000."""
        c = _cell([_o(d, "0.00004") for d in range(5)])
        assert str(c.ci_low) == "0.0000" and c.status == "inconclusive"
        c = _cell([_o(d, "0.00006") for d in range(5)])
        assert str(c.ci_low) == "0.0001" and c.status == "positive"


# ---------------------------------------------------------------------------
# celle insufficienti
# ---------------------------------------------------------------------------

class TestInsufficient:
    def test_one_day_with_many_trades_is_insufficient(self):
        """E' il punto dei blocchi: 50 trade dello stesso giorno valgono UN giorno."""
        c = _cell([_o(0, "10", ms=i) for i in range(50)], min_trades=5, min_days=2)
        assert (c.n, c.n_days, c.status) == (50, 1, "insufficient")
        assert c.ci_low is None and c.ci_high is None
        assert str(c.mean_net_bp) == "10.0000" and str(c.win_rate) == "1.0000"   # le statistiche semplici ci sono

    def test_threshold_boundaries(self):
        trades = [_o(d, "10") for d in range(4)]                  # n = 4, n_days = 4
        assert _cell(trades, min_trades=4, min_days=4).status == "positive"
        assert _cell(trades, min_trades=5, min_days=4).status == "insufficient"     # n < min_trades
        assert _cell(trades, min_trades=4, min_days=5).status == "insufficient"     # n_days < min_days

    def test_insufficient_cell_keeps_its_real_numbers(self):
        c = _cell([_o(0, "10"), _o(1, "30")], min_trades=3)
        assert (c.n, c.n_days, c.status) == (2, 2, "insufficient")
        assert (str(c.mean_net_bp), str(c.median_net_bp)) == ("20.0000", "20.0000")
        assert c.ci_low is None and c.ci_high is None

    def test_sufficient_cell_always_has_an_interval(self):
        c = _cell([_o(d, "10") for d in range(3)])
        assert c.ci_low is not None and c.ci_high is not None and c.ci_low <= c.ci_high


# ---------------------------------------------------------------------------
# filtro link_statuses e celle
# ---------------------------------------------------------------------------

class TestFilterAndCells:
    def _all_statuses(self):
        return [_o(i, "10", link=s, position_id=f"id-{s}") for i, s in enumerate(LINK_STATUSES)]

    def test_default_keeps_only_linked(self):
        c = _cell(self._all_statuses())
        assert (c.n, c.n_days) == (1, 1)

    @pytest.mark.parametrize("status", LINK_STATUSES)
    def test_each_status_selects_exactly_itself(self, status):
        outs = self._all_statuses() + [_o(10, "10", link=status), _o(11, "10", link=status)]
        c = _cell(outs, link_statuses=frozenset({status}))
        assert (c.n, c.n_days) == (3, 3)

    def test_excluded_trades_count_nowhere(self):
        """Ne' in n, ne' nei giorni, ne' nella media."""
        outs = [_o(0, "10"), _o(1, "10"), _o(2, "1000", link="dangling"), _o(3, "1000", link="unlinked")]
        c = _cell(outs)
        assert (c.n, c.n_days, str(c.mean_net_bp)) == (2, 2, "10.0000")
        c = _cell(outs, link_statuses=frozenset({"linked", "dangling", "unlinked"}))
        assert (c.n, c.n_days, str(c.mean_net_bp)) == (4, 4, "505.0000")

    def test_empty_filter_and_empty_input_give_empty_result(self):
        assert _cs([_o(0)], link_statuses=frozenset()) == ()
        assert _cs([]) == () and _cs(()) == ()
        assert _cs([_o(0, link="dangling")]) == ()

    def test_accepts_tuple_and_list(self):
        outs = [_o(d, "10") for d in range(3)]
        assert _cs(tuple(outs)) == _cs(outs) != ()

    def test_manual_and_brain_never_mixed_by_default(self):
        brain = [_o(d, "100", reason="brain_close") for d in range(4)]
        manual = [_o(d, "-100", reason="manual") for d in range(4)]
        cells = {c.key: c for c in _cs(brain + manual)}
        assert set(cells) == {KEY0, ("BTCUSDT", 1, "TRENDING", True)}
        assert cells[KEY0].status == "positive" and cells[("BTCUSDT", 1, "TRENDING", True)].status == "negative"
        assert all(c.n == 4 for c in cells.values())

    def test_custom_key_can_merge(self):
        outs = [_o(d, "100", reason="brain_close") for d in range(3)] + \
               [_o(d, "-100", reason="manual", side=-1) for d in range(3)]
        c = _cell(outs, key=lambda o: (o.symbol,))
        assert c.key == ("BTCUSDT",) and c.n == 6 and str(c.mean_net_bp) == "0.0000"

    def test_cells_sorted_by_str_of_key_values(self):
        outs = []
        for sym, side, reg, reason in [("ETHUSDT", 1, "TRENDING", "brain_close"),
                                       ("BTCUSDT", 1, "TRENDING", "manual"),
                                       ("BTCUSDT", 1, "TRENDING", "brain_close"),
                                       ("BTCUSDT", -1, "RANGING", "brain_close")]:
            outs += [_o(d, "10", symbol=sym, side=side, regime=reg, reason=reason) for d in range(3)]
        keys = [c.key for c in _cs(outs)]
        assert keys == [("BTCUSDT", -1, "RANGING", False),     # "-1" < "1"
                        ("BTCUSDT", 1, "TRENDING", False),     # "False" < "True"
                        ("BTCUSDT", 1, "TRENDING", True),
                        ("ETHUSDT", 1, "TRENDING", False)]

    def test_default_cell_key_is_symbol_side_regime_manual(self):
        assert default_cell_key(_o(symbol="X", side=-1, regime="RANGING", reason="manual")) == \
            ("X", -1, "RANGING", True)
        assert default_cell_key(_o()) == KEY0


# ---------------------------------------------------------------------------
# invarianti
# ---------------------------------------------------------------------------

def _multi_cell_dataset():
    outs = []
    for i, (sym, side, reg, reason) in enumerate([
            ("BTCUSDT", 1, "TRENDING", "brain_close"), ("BTCUSDT", 1, "TRENDING", "manual"),
            ("ETHUSDT", -1, "RANGING", "stop"), ("BTCUSDT", -1, "VOLATILE", "brain_close")]):
        outs += [dataclasses.replace(t, symbol=sym, side=side, decision_regime=reg, exit_reason=reason,
                                     position_id=f"c{i}-{t.position_id}") for t in _dataset(40 + i, 8)]
    return outs


class TestInvariants:
    def test_trade_order_is_irrelevant(self):
        outs = _multi_cell_dataset()
        ref = _cs(outs, confidence=D("0.95"), n_boot=300, seed=17)
        assert len(ref) == 4
        for s in range(5):
            shuffled = outs[:]
            random.Random(s).shuffle(shuffled)
            assert _cs(shuffled, confidence=D("0.95"), n_boot=300, seed=17) == ref
        assert _cs(list(reversed(outs)), confidence=D("0.95"), n_boot=300, seed=17) == ref

    def test_same_seed_same_result_and_each_seed_matches_its_oracle(self):
        trades = _dataset(77, 9)
        results = {}
        for seed in (1, 2, 3):
            a, b = _cell(trades, n_boot=300, seed=seed), _cell(trades, n_boot=300, seed=seed)
            assert a == b
            _assert_matches_oracle(a, trades, "0.9", 300, seed)
            results[seed] = (a.ci_low, a.ci_high)
        assert len(set(results.values())) == 3, "i semi non cambiano l'intervallo: dataset inutile"

    def test_input_is_not_modified(self):
        outs = _multi_cell_dataset()
        snapshot = outs[:]
        before = [t.to_dict() for t in outs]
        _cs(outs)
        assert outs == snapshot and all(a is b for a, b in zip(outs, snapshot))
        assert [t.to_dict() for t in outs] == before

    def test_ambient_decimal_context_does_not_change_the_result(self):
        outs = _dataset(5, 8)
        ref = _cs(outs, confidence=D("0.95"), n_boot=300, seed=7)
        with localcontext() as ctx:
            ctx.prec = 5
            ctx.rounding = ROUND_UP
            assert _cs(outs, confidence=D("0.95"), n_boot=300, seed=7) == ref

    def test_result_is_independent_of_pythonhashseed(self):
        repo = Path(__file__).resolve().parents[2]
        code = ("from test_brain_f7_expectancy_oracle import _dataset, _cs, D; "
                "print(repr(_cs(_dataset(9, 8), confidence=D('0.95'), n_boot=300, seed=5)))")
        outputs = []
        for hash_seed in ("1", "2", "random"):
            env = dict(os.environ, PYTHONHASHSEED=hash_seed, PYTHONDONTWRITEBYTECODE="1",
                       PYTHONPATH=os.pathsep.join(
                           [str(repo), str(repo / "backend"), str(Path(__file__).parent),
                            os.environ.get("PYTHONPATH", "")]))
            r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                               env=env, cwd=str(repo), timeout=120)
            assert r.returncode == 0, r.stderr
            outputs.append(r.stdout.strip())
        assert outputs[0] == outputs[1] == outputs[2] != ""
        assert outputs[0] == repr(_cs(_dataset(9, 8), confidence=D("0.95"), n_boot=300, seed=5))

    def test_equal_but_differently_written_keys_are_different_cells_in_any_order(self):
        """(1,) e (True,) sono uguali per Python ma hanno repr diverso: se si fondessero, la cella
        dipenderebbe da quale trade arriva per primo (e dal seme che ne deriva)."""
        a = [dataclasses.replace(t, symbol="A") for t in _dataset(11, 8)]
        b = [dataclasses.replace(t, symbol="B") for t in _dataset(12, 8)]
        key = lambda o: (1,) if o.symbol == "A" else (True,)         # noqa: E731
        fwd = _cs(a + b, key=key, n_boot=250)
        rev = _cs(b + a, key=key, n_boot=250)
        assert fwd == rev and len(fwd) == 2
        got = {repr(c.key): c for c in fwd}
        _assert_matches_oracle(got["(1,)"], a, "0.9", 250, 1, key=(1,))
        _assert_matches_oracle(got["(True,)"], b, "0.9", 250, 1, key=(True,))

    def test_keys_with_the_same_str_are_ordered_deterministically(self):
        a = [dataclasses.replace(t, symbol="A") for t in _dataset(13, 5)]
        b = [dataclasses.replace(t, symbol="B") for t in _dataset(14, 5)]
        key = lambda o: (1,) if o.symbol == "A" else ("1",)          # noqa: E731
        fwd, rev = _cs(a + b, key=key), _cs(b + a, key=key)
        assert fwd == rev
        assert [c.key for c in fwd] == [("1",), (1,)]


# ---------------------------------------------------------------------------
# validazione: codici ESATTI, bool al posto di int, input ostili
# ---------------------------------------------------------------------------

GOOD = [_o(0, "10"), _o(1, "20"), _o(2, "30")]


def _err(**kw) -> str:
    args = dict(BASE)
    outs = kw.pop("outs", GOOD)
    args.update(kw)
    with pytest.raises(ValueError) as ei:
        cell_stats(outs, **args)
    return str(ei.value)


# (override, codice) nell'ordine del contratto
ORDERED_ERRORS = [
    (dict(outs=["x"]), "invalid_outcome"),
    (dict(min_trades=0), "invalid_min_trades"),
    (dict(min_days=1), "invalid_min_days"),
    (dict(confidence=D("1")), "invalid_confidence"),
    (dict(n_boot=199), "invalid_n_boot"),
    (dict(seed=1.5), "invalid_seed"),
    (dict(key=None), "invalid_key"),
    (dict(link_statuses={"linked"}), "invalid_link_statuses"),
]


class TestValidation:
    def test_control_valid_call_succeeds(self):
        assert len(cell_stats(GOOD, **BASE)) == 1
        # i valori limite sono validi
        assert _cs(GOOD, min_trades=1, min_days=2, n_boot=200)[0].status == "positive"

    @pytest.mark.parametrize("override,code", ORDERED_ERRORS)
    def test_exact_codes(self, override, code):
        assert _err(**override) == code

    @pytest.mark.parametrize("i,j", [(i, j) for i in range(8) for j in range(i + 1, 8)])
    def test_first_failing_check_in_contract_order_wins(self, i, j):
        both = {**ORDERED_ERRORS[i][0], **ORDERED_ERRORS[j][0]}
        assert _err(**both) == ORDERED_ERRORS[i][1]

    @pytest.mark.parametrize("name,code", [
        ("min_trades", "invalid_min_trades"), ("min_days", "invalid_min_days"),
        ("n_boot", "invalid_n_boot"), ("seed", "invalid_seed")])
    @pytest.mark.parametrize("bad", [True, False, 5.0, "5", None, D("5")])
    def test_int_parameters_reject_bool_float_str_none_decimal(self, name, code, bad):
        assert _err(**{name: bad}) == code

    @pytest.mark.parametrize("name,value,code", [
        ("min_trades", 0, "invalid_min_trades"), ("min_trades", -3, "invalid_min_trades"),
        ("min_days", 1, "invalid_min_days"), ("min_days", 0, "invalid_min_days"),
        ("n_boot", 199, "invalid_n_boot"), ("n_boot", 0, "invalid_n_boot")])
    def test_int_parameter_bounds(self, name, value, code):
        assert _err(**{name: value}) == code

    @pytest.mark.parametrize("bad", [
        D("0"), D("1"), D("-0.5"), D("1.5"), 0.9, 1, 0, "0.9", None, True,
        D("NaN"), D("sNaN"), D("Infinity"), D("-Infinity")])
    def test_confidence_must_be_a_finite_decimal_strictly_between_0_and_1(self, bad):
        assert _err(confidence=bad) == "invalid_confidence"

    @pytest.mark.parametrize("ok", [D("0.0001"), D("0.5"), D("0.9"), D("0.9999")])
    def test_confidence_valid_values(self, ok):
        assert len(_cs(GOOD, confidence=ok)) == 1

    def test_seed_accepts_negative_and_huge_ints(self):
        assert len(_cs(GOOD, seed=-5)) == 1 and len(_cs(GOOD, seed=10 ** 30)) == 1

    @pytest.mark.parametrize("bad", [
        {"linked"}, ["linked"], ("linked",), "linked", None, frozenset({"linked", "nope"}),
        frozenset({1}), frozenset({"LINKED"}), True])
    def test_link_statuses_must_be_a_frozenset_of_known_statuses(self, bad):
        assert _err(link_statuses=bad) == "invalid_link_statuses"

    def test_link_statuses_valid_values(self):
        assert len(_cs(GOOD, link_statuses=frozenset(LINK_STATUSES))) == 1
        assert len(_cs(GOOD, link_statuses=frozenset({"linked"}))) == 1

    # --- outcomes ---------------------------------------------------------
    @pytest.mark.parametrize("bad", [
        None, 5, "abc", b"abc", {1}, {"a": 1}, iter(GOOD), (o for o in GOOD), SimpleNamespace(), 3.5])
    def test_outcomes_must_be_a_sequence(self, bad):
        assert _err(outs=bad) == "invalid_outcome"

    @pytest.mark.parametrize("bad_item", [
        "x", None, 5, {"net_bp": 1}, SimpleNamespace(**{f.name: 1 for f in dataclasses.fields(TradeOutcome)})])
    def test_every_element_must_be_a_trade_outcome(self, bad_item):
        for position in (0, 2):
            outs = GOOD[:]
            outs.insert(position, bad_item)
            assert _err(outs=outs) == "invalid_outcome"

    @pytest.mark.parametrize("over", [
        dict(net_bp=D("NaN")), dict(net_bp=D("sNaN")), dict(net_bp=D("Infinity")),
        dict(net_bp=1.5), dict(net_bp=1), dict(net_bp="1"), dict(net_bp=None),
        dict(net_bp=D("1E+100")),                                   # finito ma oltre ogni scala
        dict(costs_bp=D("NaN")), dict(costs_bp=2.0), dict(costs_bp=None),
        dict(realized_pnl=D("NaN")), dict(realized_pnl=1.0), dict(realized_pnl=None),
        dict(r_multiple=D("NaN")), dict(r_multiple=1.0), dict(r_multiple="1"), dict(r_multiple=D("Infinity")),
        dict(closed_at_ms=1.7e12), dict(closed_at_ms=True), dict(closed_at_ms=None),
        dict(closed_at_ms=0), dict(closed_at_ms=-5), dict(closed_at_ms="1700000000000"),
        dict(link_status=None), dict(link_status=["linked"]),
    ])
    def test_malformed_hand_built_outcomes_are_rejected_wherever_they_sit(self, over):
        for position in (0, 3):
            outs = GOOD[:]
            outs.insert(position, _o(5, **over))
            assert _err(outs=outs) == "invalid_outcome", over

    def test_malformed_outcome_is_rejected_even_if_the_filter_would_drop_it(self):
        assert _err(outs=GOOD + [_o(5, link="dangling", net_bp=D("NaN"))]) == "invalid_outcome"

    # --- key --------------------------------------------------------------
    @pytest.mark.parametrize("bad", [None, "x", 5, [], 1.5])
    def test_key_must_be_callable(self, bad):
        assert _err(key=bad) == "invalid_key"

    @pytest.mark.parametrize("ret", [[1], "abc", None, 5, {"a": 1}, frozenset({1}), ([1],), ({"a": 1},)])
    def test_key_must_return_a_hashable_tuple_on_the_first_trade(self, ret):
        assert _err(key=lambda o: ret) == "invalid_key"

    @pytest.mark.parametrize("second", [
        "stringa", [1], None, ([1],),
        ValueError("boom"), ValueError("invalid_key"), KeyError("x"), TypeError("t"), ZeroDivisionError()])
    def test_key_is_checked_on_every_trade_not_just_the_first(self, second):
        n = {"i": 0}

        def key(o):
            n["i"] += 1
            if n["i"] == 1:
                return ("a",)
            if isinstance(second, BaseException):
                raise second
            return second
        assert _err(key=key) == "invalid_key"

    def test_key_with_a_raising_value_error_still_reports_the_contract_code(self):
        def key(o):
            raise ValueError("messaggio mio")
        assert _err(key=key) == "invalid_key"

    def test_key_is_called_once_per_kept_trade_and_never_for_dropped_ones(self):
        seen = []

        def key(o):
            seen.append(o.position_id)
            return (o.symbol,)
        outs = GOOD + [_o(7, link="dangling"), _o(8, link="unlinked")]
        _cs(outs, key=key)
        assert sorted(seen) == sorted(o.position_id for o in GOOD)

    def test_a_key_that_fails_only_on_dropped_trades_is_fine(self):
        def key(o):
            if o.link_status != "linked":
                raise RuntimeError("non deve essere chiamata")
            return (o.symbol,)
        outs = GOOD + [_o(7, link="dangling")]
        assert len(_cs(outs, key=key)) == 1
        assert _err(outs=outs, key=key, link_statuses=frozenset({"linked", "dangling"})) == "invalid_key"

    def test_no_key_call_happens_before_parameters_are_validated(self):
        calls = []
        assert _err(n_boot=100, key=lambda o: calls.append(o) or ("k",)) == "invalid_n_boot"
        assert calls == []

    def test_custom_key_with_a_tuple_of_hashable_values_works(self):
        c = _cell(GOOD, key=lambda o: ("x", 1, None, (2, 3), frozenset({4})))
        assert c.key == ("x", 1, None, (2, 3), frozenset({4}))
        assert _cell(GOOD, key=lambda o: ()).key == ()


# ---------------------------------------------------------------------------
# format_cells: output esatto
# ---------------------------------------------------------------------------

HEADER = ("key | n | n_days | mean_net_bp | median_net_bp | mean_costs_bp | mean_r | "
          "win_rate | ci_low | ci_high | status")


class TestFormat:
    def test_exact_output_for_hand_built_cells(self):
        cells = (
            CellStats(key=("BTCUSDT", 1, "TRENDING", False), n=6, n_days=3,
                      mean_net_bp=D("8.3333"), median_net_bp=D("7.7500"), mean_costs_bp=D("20.0000"),
                      mean_r=D("1.2500"), win_rate=D("0.8333"), ci_low=D("-2.5000"),
                      ci_high=D("14.0000"), status="inconclusive"),
            CellStats(key=("ETHUSDT", -1, "", True), n=1, n_days=1,
                      mean_net_bp=D("-5.0000"), median_net_bp=D("-5.0000"), mean_costs_bp=D("12.1200"),
                      mean_r=None, win_rate=D("0.0000"), ci_low=None, ci_high=None, status="insufficient"),
        )
        assert format_cells(cells) == "\n".join([
            HEADER,
            "('BTCUSDT', 1, 'TRENDING', False) | 6 | 3 | 8.3333 | 7.7500 | 20.0000 | 1.2500 | 0.8333 "
            "| -2.5000 | 14.0000 | inconclusive",
            "('ETHUSDT', -1, '', True) | 1 | 1 | -5.0000 | -5.0000 | 12.1200 | - | 0.0000 | - | - "
            "| insufficient",
        ])

    def test_empty_gives_only_the_header_and_no_trailing_newline(self):
        assert format_cells(()) == HEADER and format_cells([]) == HEADER

    def test_end_to_end_row_carries_the_interval(self):
        trades = [_o(0, "10", r="1"), _o(0, "20", r=None), _o(1, "-30", r="-1"),
                  _o(1, "40", r="2"), _o(2, "5.5", r="3")]
        c = _cell(trades, n_boot=300, seed=2)
        lo, hi, *_ = _oracle_ci(trades, "0.9", 300, 2, KEY0)
        expected = (f"('BTCUSDT', 1, 'TRENDING', False) | 5 | 3 | 9.1000 | 10.0000 | 20.0000 | 1.2500 "
                    f"| 0.8000 | {lo} | {hi} | {_oracle_status(lo, hi)}")
        assert format_cells((c,)) == HEADER + "\n" + expected

    def test_deterministic_and_does_not_hide_the_interval(self):
        cells = _cs(_multi_cell_dataset(), n_boot=250)
        text = format_cells(cells)
        assert text == format_cells(cells) == format_cells(list(cells))
        assert len(text.splitlines()) == 1 + len(cells)
        for c in cells:
            assert str(c.ci_low) in text and str(c.ci_high) in text


# ---------------------------------------------------------------------------
# contratto pubblico e purezza del modulo
# ---------------------------------------------------------------------------

class TestPublicContractAndPurity:
    def test_cellstats_fields_and_frozen(self):
        assert [f.name for f in dataclasses.fields(CellStats)] == [
            "key", "n", "n_days", "mean_net_bp", "median_net_bp", "mean_costs_bp", "mean_r",
            "win_rate", "ci_low", "ci_high", "status"]
        c = _cell(GOOD)
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.n = 99  # type: ignore[misc]

    def test_signature_has_no_defaults_for_the_statistical_choices(self):
        params = inspect.signature(cell_stats).parameters
        assert list(params) == ["outcomes", "min_trades", "min_days", "confidence", "n_boot", "seed",
                                "key", "link_statuses"]
        for name in ("min_trades", "min_days", "confidence", "n_boot", "seed"):
            assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
            assert params[name].default is inspect.Parameter.empty, name
        assert params["key"].default is default_cell_key
        assert params["link_statuses"].default == frozenset({"linked"})
        with pytest.raises(TypeError):
            cell_stats(GOOD)                                     # type: ignore[call-arg]
        with pytest.raises(TypeError):
            cell_stats(GOOD, 1, 2, D("0.9"), 200, 1)             # type: ignore[call-arg]

    def test_module_is_pure_stdlib_no_io_no_clock_no_float(self):
        src = Path(ex.__file__).read_text()
        tree = ast.parse(src)
        allowed = {"__future__", "random", "collections.abc", "dataclasses", "decimal", "typing",
                   "backend.v3.outcomes"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        assert imported <= allowed, imported - allowed
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert not names & {"float", "open", "print", "input", "exec", "eval", "__import__"}
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, float)]

    def test_no_statistical_threshold_is_hardcoded(self):
        """Le uniche costanti numeriche ammesse: 0/1/2, quantum, ms per giorno, 60 cifre del contesto."""
        tree = ast.parse(Path(ex.__file__).read_text())
        nums = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)}
        assert nums <= {0, 1, 2, 60, 86_400_000, 200, 4}, nums
        # 200 e' il minimo di n_boot del contratto (validazione), non un default: nessun default numerico
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "cell_stats":
                defaults = [d for d in node.args.kw_defaults if d is not None]
                assert all(not isinstance(d, ast.Constant) for d in defaults)


# ---------------------------------------------------------------------------
# produttori VERI: BrainEngine -> execute_paper -> close_paper -> extract_outcomes -> cell_stats
# ---------------------------------------------------------------------------

RUN = "r-p4"
TS_DEC = 1_700_000_000_000
T_OPEN = TS_DEC + 1_000


def _journal() -> EventJournal:
    j = EventJournal(os.path.join(tempfile.mkdtemp(), "journal.db"))
    j.init_schema()
    return j


def _engine(journal) -> BrainEngine:
    policy = RiskPolicy(D(".02"), D(".05"), D(".1"), D(".3"), D("450"), D("16"), D(".5"))
    snapshot = BrainPortfolioSnapshot(D("1000"), D("1000"), D("0"), D("0"))
    params = {"exchange_leverage_limit": 10, "quantity_step": D(".001"),
              "minimum_notional": D("5"), "maintenance_fraction": D(".004"),
              "market_data_fresh": True, "paused": False, "daily_loss_latched": False}
    return BrainEngine(
        analyst=MockDeepSeekAnalyst(), reviewer=MockClaudeReviewer(always_approve=True),
        risk_policy=policy, portfolio_snapshot=snapshot, market_params=params,
        journal=journal, portfolio_id="brain", run_id=RUN,
        policy_verifier=lambda m, p: True,
        policy_mandate={"version": "p4", "approved_by": "operator", "approved": True,
                        "portfolio_id": "brain", "run_id": RUN, "policy_hash": _policy_hash(policy)})


def _brain(journal, ts: int = TS_DEC) -> BrainDecision:
    """Un contesto identico e' un replay per il motore: ogni decisione ha il suo timestamp."""
    return _engine(journal).step(MarketContext("BTCUSDT", D("50000"), ts, "TRENDING"))


def _hand_unlinked() -> BrainDecision:
    prop = OpenProposal(symbol="BTC/USDT:USDT", side=1, entry_price=D("30000"), stop_price=D("29000"),
                        leverage=5, rationale="deepseek:analysis", confidence=0.75,
                        originating_ai="deepseek", context_hash="h")
    quote = RiskQuote(allowed=True, reason="ok", quantity=D("0.01"), notional=D("300"),
                      margin=D("60"), worst_case_loss_estimate=D("30"), risk_budget=D("450"))
    return BrainDecision(kind=DecisionKind.OPEN, proposal=prop, risk_quote=quote,
                         rationale="deepseek:analysis", sources=["deepseek:analysis"],
                         occurred_at_ms=TS_DEC, status=ProposalStatus.APPROVED, journal_event_id=None)


FEE = 6


def _net_bp(entry: str, exit_: str, side: int = 1) -> Decimal:
    """Forma chiusa: (lordo - costi round-trip) in bp dell'entry notional, 4 decimali half-even."""
    e, x = D(entry), D(exit_)
    gross = D(side) * (x - e) / e * 10000
    costs = D(FEE) * (e + x) / e
    return (gross - costs).quantize(D("0.0001"))


class TestRealProducers:
    # (giorno dopo l'apertura, prezzo di uscita, motivo)
    BRAIN = [(0, "51000", "brain_close"), (0, "49500", "stop"), (1, "52000", "brain_close"),
             (1, "50500", "brain_close"), (2, "49000", "stop"), (2, "51000", "brain_close")]
    MANUAL = [(0, "50500", "manual"), (1, "49000", "manual"), (2, "52000", "manual")]

    def _build(self):
        j = _journal()
        expected_brain, expected_manual = [], []
        decision_ts = itertools.count(TS_DEC)
        for plan, bucket in ((self.BRAIN, expected_brain), (self.MANUAL, expected_manual)):
            for k, (dday, px, reason) in enumerate(plan):
                d = _brain(j, next(decision_ts))
                assert (d.kind, d.status) == (DecisionKind.OPEN, ProposalStatus.APPROVED)      # controllo
                rec = execute_paper(d, portfolio_id="hawk", run_id=RUN, journal=j, now_ms=T_OPEN)
                assert rec.fill_price == D("50000") and rec.decision_event_id == d.journal_event_id
                closed = T_OPEN + 60_000 + dday * DAY + k          # k: ordine distinguibile nello stesso giorno
                close_paper(portfolio_id="hawk", run_id=RUN, position_id=rec.position_id,
                            exit_price=D(px), reason=reason, fee_bps=FEE, journal=j, now_ms=closed)
                bucket.append((closed // DAY, _net_bp("50000", px)))
        # due posizioni aperte "a mano" (nessuna decisione collegata): vanno escluse di default
        for k in range(2):
            rec = execute_paper(_hand_unlinked(), portfolio_id="hawk", run_id=RUN, journal=j, now_ms=T_OPEN)
            close_paper(portfolio_id="hawk", run_id=RUN, position_id=rec.position_id,
                        exit_price=D("31000"), reason="brain_close", fee_bps=FEE, journal=j,
                        now_ms=T_OPEN + 60_000 + k * DAY)
        return j, expected_brain, expected_manual

    def test_chain_produces_the_expected_cells(self):
        j, exp_brain, exp_manual = self._build()
        rep = extract_outcomes(j, "hawk", RUN)
        assert rep.skipped == () and rep.open_position_ids == ()
        assert rep.link_counts()["linked"] == 9 and rep.link_counts()["unlinked"] == 2
        assert len(rep.outcomes) == 11

        cells = cell_stats(rep.outcomes, min_trades=3, min_days=3, confidence=D("0.9"), n_boot=300, seed=11)
        by_key = {c.key: c for c in cells}
        assert set(by_key) == {("BTCUSDT", 1, "TRENDING", False), ("BTCUSDT", 1, "TRENDING", True)}

        for key, expected, plan in ((("BTCUSDT", 1, "TRENDING", False), exp_brain, self.BRAIN),
                                    (("BTCUSDT", 1, "TRENDING", True), exp_manual, self.MANUAL)):
            c = by_key[key]
            nets = sorted(Fraction(v) for _, v in expected)
            n = len(nets)
            assert (c.n, c.n_days) == (n, len({d for d, _ in expected}))
            assert c.mean_net_bp == _q4(sum(nets) / n)
            assert c.median_net_bp == _q4((nets[n // 2 - 1] + nets[n // 2]) / 2 if n % 2 == 0 else nets[n // 2])
            # costi round-trip in forma chiusa: fee * (entry + exit) / entry
            assert c.mean_costs_bp == _q4(sum(Fraction(FEE) * (50000 + Fraction(px)) / 50000
                                              for _, px, _ in plan) / n)
            # l'intervallo e' quello dell'oracolo sui numeri in forma chiusa
            fake = [_o(0, v, closed_at_ms=d * DAY) for d, v in expected]
            lo, hi, *_ = _oracle_ci(fake, "0.9", 300, 11, key)
            assert (c.ci_low, c.ci_high) == (lo, hi)
            assert c.status == _oracle_status(lo, hi) != "insufficient"

        # win rate dei trade Brain: uscite a 51000, 52000, 50500, 51000 vincono; 49500 e 49000 perdono
        assert str(by_key[("BTCUSDT", 1, "TRENDING", False)].win_rate) == "0.6667"
        assert str(by_key[("BTCUSDT", 1, "TRENDING", True)].win_rate) == "0.6667"

    def test_unlinked_trades_are_excluded_by_default_and_included_on_request(self):
        j, exp_brain, exp_manual = self._build()
        rep = extract_outcomes(j, "hawk", RUN)
        kw = dict(min_trades=1, min_days=2, confidence=D("0.9"), n_boot=200, seed=3)
        default = cell_stats(rep.outcomes, **kw)
        assert sum(c.n for c in default) == 9
        with_unlinked = cell_stats(rep.outcomes, link_statuses=frozenset({"linked", "unlinked"}), **kw)
        assert sum(c.n for c in with_unlinked) == 11
        extra = [c for c in with_unlinked if c.key[0] == "BTC/USDT:USDT"]
        assert len(extra) == 1 and extra[0].key[2] == "" and extra[0].n == 2     # nessun regime: non c'e' decisione
        # 30000 -> 31000, fee 6 bp: la stessa cifra del test degli esiti
        assert str(extra[0].mean_net_bp) == "321.1333"

    def test_result_is_stable_across_repeated_extraction(self):
        j, *_ = self._build()
        kw = dict(min_trades=1, min_days=2, confidence=D("0.95"), n_boot=300, seed=5)
        a = cell_stats(extract_outcomes(j, "hawk", RUN).outcomes, **kw)
        b = cell_stats(extract_outcomes(j, "hawk", RUN).outcomes, **kw)
        assert a == b and format_cells(a) == format_cells(b)
