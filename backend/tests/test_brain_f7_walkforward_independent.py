"""P6 walk-forward — verifica indipendente (Claude), scritta dal contratto del prompt e non dal modulo.

Cosa prova, oltre ai 6 test di Grok (``test_brain_f7_walkforward.py``):

* **Oracolo ``Fraction``** con algoritmi diversi dal modulo: appartenenza ai fold con cicli espliciti sui
  timestamp, medie esatte in razionali arrotondate UNA volta (4 decimali, half-even), ``decay`` dai valori
  esatti. Per la *selezione* l'oracolo chiama il vero ``cell_stats`` su insiemi di train costruiti da lui
  (la statistica e' gia' verificata in #44: qui si verificano affettamento e aggregazione).
* ``cell_stats`` **sostituito da uno stub** (``monkeypatch``): ogni regola di selezione/misura senza dipendere
  dalla statistica, e gli argomenti con cui viene chiamato (1 + numero di fold chiamate).
* **Nessuna fuga d'informazione** con meta-test (una selezione che usa anche il test viene riconosciuta).
* Validazione esaustiva con l'ordine dei codici; scale estreme; contesto Decimal ambientale; purezza ``ast``
  sui NOMI importati; velocita' a 60 000 trade (con ``cell_stats`` stub: si misura solo il modulo).
"""
from __future__ import annotations

import ast
import collections.abc
import copy
import dataclasses
import inspect
import itertools
import random
import time
from decimal import ROUND_DOWN, Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from backend.v3.learning import walkforward as wf
from backend.v3.learning.expectancy import CellStats, cell_stats, default_cell_key
from backend.v3.outcomes import TradeOutcome

DAY = 86_400_000
STAT = dict(min_trades=4, min_days=3, confidence=Decimal("0.9"), n_boot=200, seed=7)


# ---------------------------------------------------------------------------
# costruzione dati
# ---------------------------------------------------------------------------

def out(pid="p", closed=DAY, symbol="A", side=1, net="10", regime="TRENDING", status="linked",
        reason="take_profit", **over) -> TradeOutcome:
    base = dict(
        schema_version=1, position_id=pid, portfolio_id="brain", run_id="r1",
        symbol=symbol, side=side, originating_ai="deepseek", leverage=5,
        opened_at_ms=1, closed_at_ms=closed, hold_ms=1,
        entry_price=Decimal("100"), exit_price=Decimal("101"), quantity=Decimal("1"),
        notional_entry=Decimal("100"), margin_used=Decimal("20"), gross_pnl=Decimal("1"),
        fees=Decimal("0.1"), realized_pnl=Decimal("0.9"), gross_bp=Decimal("100"),
        costs_bp=Decimal("10"), net_bp=Decimal(net), stop_distance_bp=Decimal("50"),
        r_multiple=Decimal("1"), exit_reason=reason, loss_exceeds_margin=False,
        decision_event_id="e", link_status=status, decision_regime=regime,
    )
    base.update(over)
    return TradeOutcome(**base)


def folds_of(start_d=0, end_d=8, train_d=3, test_d=2, step_d=3, emb_d=0, expanding=False):
    return wf.make_folds(start_ms=start_d * DAY, end_ms=end_d * DAY, train_ms=train_d * DAY,
                         test_ms=test_d * DAY, step_ms=step_d * DAY, embargo_ms=emb_d * DAY,
                         expanding=expanding)


def run(outcomes, folds, **over):
    kw = dict(STAT)
    kw.update(over)
    return wf.walk_forward(outcomes, folds, **kw)


def sd(d):
    return None if d is None else str(d)


def flat(rep):
    """Report -> tuple di int/str/None confrontabile alla lettera (i Decimal come stringhe: 4 decimali, niente -0)."""
    folds = []
    for fr in rep.folds:
        f = fr.fold
        folds.append((
            f.index, f.train_start_ms, f.train_end_ms, f.test_start_ms, f.test_end_ms,
            fr.n_train_outcomes, fr.n_test_outcomes, fr.n_cells_evaluated, fr.n_selected,
            tuple((c.key, c.train_n, sd(c.train_mean_net_bp), sd(c.train_ci_low), c.test_n,
                   sd(c.test_mean_net_bp)) for c in fr.selected),
            fr.selected_test_n, sd(fr.selected_test_mean_net_bp), fr.rest_test_n,
            sd(fr.rest_test_mean_net_bp)))
    return (tuple(folds), rep.n_selections, rep.n_folds_with_selection, rep.is_n, sd(rep.is_mean_net_bp),
            rep.oos_n, sd(rep.oos_mean_net_bp), rep.rest_n, sd(rep.rest_mean_net_bp), sd(rep.decay_bp))


# ---------------------------------------------------------------------------
# oracolo (Fraction; cicli espliciti; nessun codice del modulo)
# ---------------------------------------------------------------------------

def q4s(fr):
    """Fraction -> stringa a 4 decimali, half-even, senza zero negativo."""
    n = round(fr * 10000)                      # Fraction.__round__ senza cifre: half-even
    return str(Decimal(f"{n}E-4"))             # costruzione esatta: scaleb() arrotonderebbe al contesto ambientale


def fmean(vals):
    return Fraction(sum((Fraction(v) for v in vals), Fraction(0)), len(vals))


def o_members(outcomes, fold, statuses):
    train, test = [], []
    for o in outcomes:
        if o.link_status not in statuses:
            continue
        t = o.closed_at_ms
        if fold.train_start_ms <= t and t < fold.train_end_ms:
            train.append(o)
        if fold.test_start_ms <= t and t < fold.test_end_ms:
            test.append(o)
    return train, test


def o_walk(outcomes, folds, *, key=default_cell_key, statuses=frozenset({"linked"}), **stat):
    rows = []
    is_vals, oos_vals, rest_vals = [], [], []
    for fold in folds:
        train, test = o_members(outcomes, fold, statuses)
        cs = cell_stats(train, key=key, link_statuses=statuses, **stat)
        n_eval = sum(1 for c in cs if c.status != "insufficient")
        sel = [c for c in cs if c.status == "positive"]
        sel_ids = [(c.key, repr(c.key)) for c in sel]
        tident = []
        for o in test:
            k = key(o)
            tident.append((k, repr(k)))
        rident = []
        for o in train:
            k = key(o)
            rident.append((k, repr(k)))
        cells = []
        sel_test, rest_test, sel_train = [], [], []
        for o, idt in zip(test, tident):
            (sel_test if idt in sel_ids else rest_test).append(o.net_bp)
        for c, cid in zip(sel, sel_ids):
            mine = [o.net_bp for o, idt in zip(test, tident) if idt == cid]
            for o, idt in zip(train, rident):
                if idt == cid:
                    sel_train.append(o.net_bp)
            cells.append((c.key, c.n, str(c.mean_net_bp), str(c.ci_low), len(mine),
                          q4s(fmean(mine)) if mine else None))
        is_vals += sel_train
        oos_vals += sel_test
        rest_vals += rest_test
        rows.append((fold.index, fold.train_start_ms, fold.train_end_ms, fold.test_start_ms, fold.test_end_ms,
                     len(train), len(test), n_eval, len(sel), tuple(cells),
                     len(sel_test), q4s(fmean(sel_test)) if sel_test else None,
                     len(rest_test), q4s(fmean(rest_test)) if rest_test else None))
    is_m = fmean(is_vals) if is_vals else None
    oos_m = fmean(oos_vals) if oos_vals else None
    return (tuple(rows), sum(r[8] for r in rows), sum(1 for r in rows if r[8] > 0),
            len(is_vals), q4s(is_m) if is_m is not None else None,
            len(oos_vals), q4s(oos_m) if oos_m is not None else None,
            len(rest_vals), q4s(fmean(rest_vals)) if rest_vals else None,
            q4s(is_m - oos_m) if is_m is not None and oos_m is not None else None)


def o_folds(start, end, train, test, step, embargo, expanding):
    """Stessa definizione ma con il numero di fold in forma chiusa (nessun ciclo while)."""
    room = end - start - train - embargo - test
    if room < 0:
        return []
    count = room // step + 1
    out_ = []
    for k in range(count):
        tr_end = start + k * step + train
        out_.append((k, start if expanding else start + k * step, tr_end, tr_end + embargo,
                     tr_end + embargo + test))
    return out_


# ---------------------------------------------------------------------------
# dataset casuali (validi) con casi difficili
# ---------------------------------------------------------------------------

def gen(seed):
    r = random.Random(seed)
    train_d = r.choice([6, 8, 10])
    test_d = r.choice([2, 3, 4])
    step_d = test_d + r.choice([0, 0, 1, 2])
    emb_d = r.choice([0, 0, 1, 2])
    expanding = r.random() < 0.4
    n_f = r.randint(3, 6)
    start_d = r.choice([0, 3])
    end_d = start_d + train_d + emb_d + test_d + (n_f - 1) * step_d + r.choice([0, 0, 1])
    folds = folds_of(start_d, end_d, train_d, test_d, step_d, emb_d, expanding)
    n_cells = r.randint(3, 7)
    drift = {s: r.choice([-40, 0, 60, 120, 200] if seed % 6 else [-40, -10, 0, 5]) for s in range(n_cells)}   # alcuni dataset senza edge
    trades = []
    pid = 0
    lo, hi = max(1, start_d * DAY - 2 * DAY), end_d * DAY + 2 * DAY      # cell_stats: closed_at_ms > 0
    for s in range(n_cells):
        for _ in range(r.randint(25, 60)):
            pid += 1
            net = drift[s] + r.randint(-30, 30)
            net = Decimal(net) if r.random() < 0.5 else Decimal(net * 100 + r.randint(-99, 99)) / Decimal(100)
            trades.append(out(f"t{pid}", r.randint(lo, hi), f"S{s}", r.choice([1, -1]) if s % 2 else 1,
                              str(net), r.choice(["TRENDING", "RANGING"]) if s % 3 == 0 else "TRENDING"))
    # trade esattamente sui confini di ogni fold (e a un ms di distanza), in celle casuali
    for f in folds:
        for t in {f.train_start_ms, f.train_end_ms - 1, f.train_end_ms, f.test_start_ms - 1,
                  f.test_start_ms, f.test_end_ms - 1, f.test_end_ms}:
            pid += 1
            s = r.randrange(n_cells)
            trades.append(out(f"b{pid}", max(1, t), f"S{s}", 1, str(drift[s] + r.randint(-30, 30))))
    # una cella che compare solo nel test (mai vista nel train)
    for f in folds[:2]:
        pid += 1
        trades.append(out(f"n{pid}", f.test_start_ms + 1, "NEW", 1, "50"))
    # trade non collegati con valori enormi: non devono mai contare con il filtro di default
    for _ in range(8):
        pid += 1
        trades.append(out(f"u{pid}", r.randint(lo, hi), "S0", 1, "99999", status="unlinked"))
    r.shuffle(trades)
    return trades, folds


SEEDS = list(range(24))
DATA = {s: gen(s) for s in SEEDS}
VARIANTS = [
    dict(),
    dict(min_trades=6, min_days=4, confidence=Decimal("0.8"), seed=3),
    dict(key=lambda o: (o.symbol,)),
    dict(statuses=frozenset({"linked", "unlinked"}), min_trades=5),
    dict(key=lambda o: (o.side, o.decision_regime), seed=11),
]


def stat_for(variant):
    kw = dict(STAT)
    kw.update({k: v for k, v in variant.items() if k not in ("key", "statuses")})
    return kw


class TestAgainstOracle:
    @pytest.mark.parametrize("seed,vi", [(s_, v_) for s_ in SEEDS for v_ in range(len(VARIANTS))
                                         if v_ < 2 or s_ % 3 == 0])     # le varianti 2-4 su un terzo dei seed
    def test_report_equals_oracle(self, seed, vi):
        trades, folds = DATA[seed]
        v = VARIANTS[vi]
        kw = stat_for(v)
        extra = {}
        if "key" in v:
            extra["key"] = v["key"]
        if "statuses" in v:
            extra["link_statuses"] = v["statuses"]
        got = wf.walk_forward(trades, folds, **kw, **extra)
        ref = o_walk(trades, folds, key=v.get("key", default_cell_key),
                     statuses=v.get("statuses", frozenset({"linked"})), **kw)
        assert flat(got) == ref

    def test_guards_the_datasets_contain_the_hard_cases(self):
        n_sel = n_nosel_folds = n_empty_sel_test = n_never_seen = n_boundary = 0
        n_rest_and_sel = n_none_means = 0
        for seed in SEEDS:
            trades, folds = DATA[seed]
            ref = o_walk(trades, folds, **STAT)
            n_sel += ref[1]
            for row in ref[0]:
                n_nosel_folds += row[8] == 0
                n_empty_sel_test += any(c[4] == 0 for c in row[9])
                n_rest_and_sel += row[10] > 0 and row[12] > 0
                n_none_means += row[11] is None
            for f in folds:
                _, test = o_members(trades, f, {"linked"})
                train, _ = o_members(trades, f, {"linked"})
                seen = {default_cell_key(o) for o in train}
                n_never_seen += any(default_cell_key(o) not in seen for o in test)
                ts = {o.closed_at_ms for o in trades}
                n_boundary += sum(x in ts for x in (f.train_end_ms, f.test_start_ms, f.test_end_ms,
                                                    f.train_end_ms - 1, f.test_end_ms - 1))
        assert n_sel >= 40, n_sel                    # ci sono selezioni vere
        assert n_nosel_folds >= 5, n_nosel_folds     # e fold senza selezione
        assert n_empty_sel_test >= 3, n_empty_sel_test   # celle selezionate senza trade nel test
        assert n_none_means >= 3, n_none_means       # selected_test_mean None
        assert n_rest_and_sel >= 20, n_rest_and_sel
        assert n_never_seen >= 10, n_never_seen      # celle del test mai viste nel train
        assert n_boundary >= 200, n_boundary         # trade esattamente sui confini

    def test_half_even_ties_are_rounded_to_even(self):
        """Medie esatte con un 5 come quinto decimale: arrotondano a pari (0,00005 -> 0,0000; 0,00015 -> 0,0002)."""
        for mean, exp in (("0.00005", "0.0000"), ("0.00015", "0.0002"), ("-0.00005", "0.0000"),
                          ("0.00025", "0.0002"), ("-0.00015", "-0.0002")):
            trades = [out(f"a{i}", DAY * (i % 3) + 5 + i, net="10") for i in range(6)]
            trades += [out("x1", 3 * DAY + 5, net=mean), out("x2", 4 * DAY + 5, net=mean)]
            rep = run(trades, folds_of(0, 6, 3, 3, 3, 0, False))
            assert str(rep.oos_mean_net_bp) == exp, (mean, rep.oos_mean_net_bp)
            assert str(rep.folds[0].selected[0].test_mean_net_bp) == exp


# ---------------------------------------------------------------------------
# vettore a mano (tutti i numeri calcolati a mano, riga per riga)
# ---------------------------------------------------------------------------

def hand_vector():
    t = []
    add = lambda sym, day, net: t.append(out(f"h{len(t)}", int(day * DAY), sym, 1, str(net)))
    # fold 0: train [0,3) giorni
    for d in (0.5, 1.5, 2.5):
        add("A", d, 100)
        add("B", d, -100)
    for d in (0.5, 1.5):
        add("C", d, 100)
    # fold 0: test [3,5)  (e train del fold 1: [3,6))
    add("A", 3.5, 60); add("A", 4.5, 60); add("B", 3.5, 7); add("C", 4.0, 11); add("D", 4.5, -9)
    add("A", 5.5, 60)
    # fold 1: test [6,8)
    add("A", 6.5, 20); add("A", 7.5, 30); add("B", 6.5, -50); add("E", 7.0, 5)
    return t


class TestHandVector:
    def test_make_folds_by_hand(self):
        f = folds_of(0, 8, 3, 2, 3, 0, False)
        assert [dataclasses.astuple(x) for x in f] == [
            (0, 0, 3 * DAY, 3 * DAY, 5 * DAY), (1, 3 * DAY, 6 * DAY, 6 * DAY, 8 * DAY)]

    def test_report_by_hand(self):
        rep = run(hand_vector(), folds_of(0, 8, 3, 2, 3, 0, False), min_trades=3, min_days=3)
        f0, f1 = rep.folds
        key_a = ("A", 1, "TRENDING", False)
        assert (f0.n_train_outcomes, f0.n_test_outcomes, f0.n_cells_evaluated, f0.n_selected) == (8, 5, 2, 1)
        assert [(c.key, c.train_n, str(c.train_mean_net_bp), str(c.train_ci_low), c.test_n,
                 str(c.test_mean_net_bp)) for c in f0.selected] == [(key_a, 3, "100.0000", "100.0000", 2, "60.0000")]
        assert (f0.selected_test_n, str(f0.selected_test_mean_net_bp)) == (2, "60.0000")
        assert (f0.rest_test_n, str(f0.rest_test_mean_net_bp)) == (3, "3.0000")        # (7+11-9)/3
        assert (f1.n_train_outcomes, f1.n_test_outcomes, f1.n_cells_evaluated, f1.n_selected) == (6, 4, 1, 1)
        assert [(c.key, c.train_n, str(c.train_mean_net_bp), c.test_n, str(c.test_mean_net_bp))
                for c in f1.selected] == [(key_a, 3, "60.0000", 2, "25.0000")]          # (20+30)/2
        assert (f1.selected_test_n, str(f1.selected_test_mean_net_bp)) == (2, "25.0000")
        assert (f1.rest_test_n, str(f1.rest_test_mean_net_bp)) == (2, "-22.5000")        # (-50+5)/2
        assert (rep.n_selections, rep.n_folds_with_selection) == (2, 2)
        assert (rep.is_n, str(rep.is_mean_net_bp)) == (6, "80.0000")                    # (300+180)/6
        assert (rep.oos_n, str(rep.oos_mean_net_bp)) == (4, "42.5000")                  # (60+60+20+30)/4
        assert (rep.rest_n, str(rep.rest_mean_net_bp)) == (5, "-7.2000")                # (7+11-9-50+5)/5
        assert str(rep.decay_bp) == "37.5000"

    def test_hand_vector_equals_oracle(self):
        t, f = hand_vector(), folds_of(0, 8, 3, 2, 3, 0, False)
        assert flat(run(t, f, min_trades=3, min_days=3)) == o_walk(t, f, min_trades=3, min_days=3,
                                                                    **{k: v for k, v in STAT.items()
                                                                       if k not in ("min_trades", "min_days")})

    def test_decay_uses_exact_values_not_the_rounded_means(self):
        """is = 10,00004 (-> 10,0000) e oos = 5,00006 (-> 5,0001): decay esatto 4,99998 -> 5,0000
        (non 10,0000 - 5,0001 = 4,9999)."""
        tr = [out(f"a{i}", DAY * (1 + i) + 5, net="10.00004") for i in range(5)]
        te = [out("b0", DAY * 7 + 5, net="5.00006")]
        rep = run(tr + te, folds_of(0, 8, 6, 2, 2, 0, False), min_trades=5)
        assert str(rep.is_mean_net_bp) == "10.0000" and str(rep.oos_mean_net_bp) == "5.0001"
        assert str(rep.decay_bp) == "5.0000"

    def test_decay_negative_zero_is_zero(self):
        tr = [out(f"a{i}", DAY * (1 + i) + 5, net="0.0001") for i in range(5)]
        te = [out("b0", DAY * 7 + 5, net="0.00012")]
        rep = run(tr + te, folds_of(0, 8, 6, 2, 2, 0, False), min_trades=5)
        assert (str(rep.is_mean_net_bp), str(rep.oos_mean_net_bp)) == ("0.0001", "0.0001")
        assert str(rep.decay_bp) == "0.0000"                 # esatto -0,00002 -> "0.0000", mai "-0.0000"

    def test_no_negative_zero_anywhere(self):
        tr = [out(f"a{i}", DAY * (1 + i) + 5, net="10") for i in range(5)]
        te = [out("b0", DAY * 7 + 5, net="-0.00001"), out("b1", DAY * 7 + 9, net="-0.00001", symbol="Z")]
        rep = run(tr + te, folds_of(0, 8, 6, 2, 2, 0, False), min_trades=5)
        text = repr(flat(rep))
        assert "-0.0000" not in text and "0.0000" in text
        assert str(rep.folds[0].selected[0].test_mean_net_bp) == "0.0000"
        assert str(rep.folds[0].rest_test_mean_net_bp) == "0.0000"


# ---------------------------------------------------------------------------
# make_folds
# ---------------------------------------------------------------------------

MF = dict(start_ms=0, end_ms=20 * DAY, train_ms=5 * DAY, test_ms=2 * DAY, step_ms=3 * DAY, embargo_ms=DAY,
          expanding=False)


def mf(**over):
    kw = dict(MF)
    kw.update(over)
    return wf.make_folds(**kw)


MF_ORDER = ["invalid_window", "invalid_lengths", "invalid_embargo", "invalid_expanding", "no_folds"]
MF_BAD_BY_CODE = {
    "invalid_window": dict(start_ms=DAY + 1), "invalid_lengths": dict(train_ms=0),
    "invalid_embargo": dict(embargo_ms=-DAY), "invalid_expanding": dict(expanding=1),
    "no_folds": dict(end_ms=DAY),
}
MF_PAIRS = [(a, b) for i, a in enumerate(MF_ORDER) for b in MF_ORDER[i + 1:]]


class TestMakeFolds:
    def test_values_rolling_and_expanding(self):
        r = mf()
        assert [dataclasses.astuple(x) for x in r] == [
            (0, 0, 5 * DAY, 6 * DAY, 8 * DAY), (1, 3 * DAY, 8 * DAY, 9 * DAY, 11 * DAY),
            (2, 6 * DAY, 11 * DAY, 12 * DAY, 14 * DAY), (3, 9 * DAY, 14 * DAY, 15 * DAY, 17 * DAY),
            (4, 12 * DAY, 17 * DAY, 18 * DAY, 20 * DAY)]
        e = mf(expanding=True)
        assert [x.train_start_ms for x in e] == [0] * 5
        assert [(x.train_end_ms, x.test_start_ms, x.test_end_ms) for x in e] == [
            (x.train_end_ms, x.test_start_ms, x.test_end_ms) for x in r]

    def test_last_fold_that_fits_and_the_one_that_does_not(self):
        assert len(mf(end_ms=20 * DAY)) == 5               # test_end == end_ms: entra (<=)
        assert len(mf(end_ms=20 * DAY - 1)) == 4           # un ms in meno: esce
        assert len(mf(end_ms=20 * DAY - DAY)) == 4
        assert len(mf(end_ms=21 * DAY - 1)) == 5

    def test_embargo_zero_and_types(self):
        r = mf(embargo_ms=0)
        assert all(x.test_start_ms == x.train_end_ms for x in r)
        assert type(r) is tuple and all(type(x) is wf.Fold for x in r)
        assert all(type(v) is int for x in r for v in dataclasses.astuple(x))

    @pytest.mark.parametrize("seed", range(60))
    def test_equals_closed_form_oracle(self, seed):
        r = random.Random(seed)
        kw = dict(start_ms=r.choice([0, 1, 5]) * DAY, train_ms=r.randint(1, 9) * DAY,
                  test_ms=0, step_ms=0, embargo_ms=r.choice([0, 0, 1, 3]) * DAY, expanding=r.random() < .5)
        kw["test_ms"] = r.randint(1, 5) * DAY
        kw["step_ms"] = kw["test_ms"] + r.choice([0, 0, 1, 4]) * DAY
        kw["end_ms"] = kw["start_ms"] + r.randint(1, 60) * DAY + r.choice([0, 0, 7, DAY - 1])
        exp = o_folds(kw["start_ms"], kw["end_ms"], kw["train_ms"], kw["test_ms"], kw["step_ms"],
                      kw["embargo_ms"], kw["expanding"])
        if not exp:
            with pytest.raises(ValueError, match="^no_folds$"):
                wf.make_folds(**kw)
        else:
            assert [dataclasses.astuple(x) for x in wf.make_folds(**kw)] == exp

    def test_properties_tests_never_overlap_and_are_chronological(self):
        for expanding in (False, True):
            r = mf(expanding=expanding, step_ms=2 * DAY)
            for a, b in zip(r, r[1:]):
                assert b.test_start_ms >= a.test_end_ms
                assert a.train_end_ms <= a.test_start_ms < a.test_end_ms

    BAD = [
        ("invalid_window", dict(start_ms=-DAY)), ("invalid_window", dict(start_ms=DAY + 1)),
        ("invalid_window", dict(start_ms=float(DAY))), ("invalid_window", dict(start_ms=None)),
        ("invalid_window", dict(start_ms=False)),                 # 0 e' valido: il tipo conta
        ("invalid_window", dict(end_ms=0)), ("invalid_window", dict(end_ms=-1)),
        ("invalid_window", dict(end_ms=float(20 * DAY))), ("invalid_window", dict(end_ms="x")),
        ("invalid_window", dict(start_ms=3 * DAY, end_ms=3 * DAY)),
        ("invalid_lengths", dict(step_ms=float(3 * DAY))), ("invalid_lengths", dict(test_ms=float(2 * DAY))),
        ("invalid_lengths", dict(step_ms=None)), ("invalid_lengths", dict(train_ms=None)),
        ("invalid_lengths", dict(train_ms=0)), ("invalid_lengths", dict(train_ms=-DAY)),
        ("invalid_lengths", dict(train_ms=5 * DAY + 1)), ("invalid_lengths", dict(train_ms=float(5 * DAY))),
        ("invalid_lengths", dict(train_ms=True)), ("invalid_lengths", dict(test_ms=0)),
        ("invalid_lengths", dict(test_ms=DAY // 2)), ("invalid_lengths", dict(test_ms=None)),
        ("invalid_lengths", dict(step_ms=0)), ("invalid_lengths", dict(step_ms=3 * DAY + 5)),
        ("invalid_lengths", dict(step_ms=DAY)),                    # step < test (2 giorni)
        ("invalid_lengths", dict(step_ms=1)),
        ("invalid_embargo", dict(embargo_ms=-DAY)), ("invalid_embargo", dict(embargo_ms=1)),
        ("invalid_embargo", dict(embargo_ms=float(DAY))), ("invalid_embargo", dict(embargo_ms=False)),
        ("invalid_embargo", dict(embargo_ms=None)),
        ("invalid_expanding", dict(expanding=1)), ("invalid_expanding", dict(expanding=0)),
        ("invalid_expanding", dict(expanding=None)), ("invalid_expanding", dict(expanding="True")),
        ("no_folds", dict(end_ms=7 * DAY)), ("no_folds", dict(end_ms=DAY)),
    ]

    @pytest.mark.parametrize("code,over", BAD)
    def test_every_code_exact_message(self, code, over):
        with pytest.raises(ValueError) as e:
            mf(**over)
        assert str(e.value) == code

    @pytest.mark.parametrize("a,b", MF_PAIRS)
    def test_error_order_every_pair(self, a, b):
        over = dict(MF_BAD_BY_CODE[b])
        over.update(MF_BAD_BY_CODE[a])
        # no_folds come prima fra i due dipende dai dati: end_ms=DAY farebbe fallire anche "invalid_window"
        if a != "invalid_window" and "end_ms" in over:
            over["end_ms"] = 20 * DAY
        if b == "no_folds":
            over["end_ms"] = DAY if a != "invalid_window" else DAY * 3
        with pytest.raises(ValueError) as e:
            mf(**over)
        assert str(e.value) == a

    def test_signature_is_keyword_only_without_defaults(self):
        sig = inspect.signature(wf.make_folds)
        assert list(sig.parameters) == ["start_ms", "end_ms", "train_ms", "test_ms", "step_ms",
                                        "embargo_ms", "expanding"]
        assert all(p.kind is inspect.Parameter.KEYWORD_ONLY and p.default is inspect.Parameter.empty
                   for p in sig.parameters.values())


# ---------------------------------------------------------------------------
# walk_forward con cell_stats sostituito da uno stub
# ---------------------------------------------------------------------------

def cs(key, status, n=5, mean="10", ci_low="1"):
    insuff = status == "insufficient"
    return CellStats(key=key, n=n, n_days=5, mean_net_bp=Decimal(mean), median_net_bp=Decimal(mean),
                     mean_costs_bp=Decimal("1"), mean_r=None, win_rate=Decimal("0.5"),
                     ci_low=None if insuff else Decimal(ci_low), ci_high=None if insuff else Decimal("99"),
                     status=status)


class Spy:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []

    def __call__(self, outcomes, **kw):
        self.calls.append((outcomes, kw))
        return self.responder(len(self.calls) - 1, outcomes)


K = lambda sym: (sym, 1, "TRENDING", False)


def stubbed(monkeypatch, responder, outcomes, folds, **over):
    spy = Spy(responder)
    monkeypatch.setattr(wf, "cell_stats", spy)
    return run(outcomes, folds, **over), spy


class TestRulesWithStubbedCellStats:
    def _data(self):
        t = []
        for sym, day, net in [("A", 0.5, 1), ("B", 0.5, 2), ("C", 1.5, 3), ("D", 2.5, 4),        # train fold 0
                              ("A", 3.5, 10), ("A", 4.5, 20), ("B", 4.0, 7), ("D", 4.2, 5), ("Z", 4.4, -3)]:  # test
            t.append(out(f"s{len(t)}", int(day * DAY), sym, 1, str(net)))
        return t, folds_of(0, 5, 3, 2, 3, 0, False)

    def test_only_positive_is_selected_and_evaluated_excludes_only_insufficient(self, monkeypatch):
        t, f = self._data()
        resp = lambda i, o: () if i == 0 else (
            cs(K("A"), "positive", 7, "3.5", "0.5"), cs(K("B"), "negative"), cs(K("C"), "inconclusive"),
            cs(K("D"), "insufficient"))
        rep, spy = stubbed(monkeypatch, resp, t, f)
        fr = rep.folds[0]
        assert (fr.n_cells_evaluated, fr.n_selected) == (3, 1)
        assert [c.key for c in fr.selected] == [K("A")]
        c = fr.selected[0]
        assert (c.train_n, c.train_mean_net_bp, c.train_ci_low) == (7, Decimal("3.5"), Decimal("0.5"))
        assert (c.test_n, str(c.test_mean_net_bp)) == (2, "15.0000")
        assert (fr.selected_test_n, fr.rest_test_n) == (2, 3)
        assert str(fr.rest_test_mean_net_bp) == "3.0000"                 # (7+5-3)/3

    def test_selection_follows_the_stub_order(self, monkeypatch):
        t, f = self._data()
        resp = lambda i, o: () if i == 0 else (cs(K("D"), "positive"), cs(K("A"), "positive"), cs(K("B"), "positive"))
        rep, _ = stubbed(monkeypatch, resp, t, f)
        assert [c.key for c in rep.folds[0].selected] == [K("D"), K("A"), K("B")]

    def test_number_of_calls_and_their_arguments(self, monkeypatch):
        t, f = self._data()
        t.append(out("u1", int(0.7 * DAY), "A", 1, "1", status="unlinked"))
        f = folds_of(0, 8, 3, 2, 3, 0, False)
        statuses = frozenset({"linked", "unlinked"})
        keyf = lambda o: (o.symbol, o.side, o.decision_regime, o.is_manual)
        sentinel = dict(min_trades=4, min_days=3, confidence=Decimal("0.9"), n_boot=200, seed=12345)
        rep, spy = stubbed(monkeypatch, lambda i, o: (), t, f, key=keyf, link_statuses=statuses, **sentinel)
        assert len(spy.calls) == 1 + len(f)                              # validazione + una per fold
        first_o, first_kw = spy.calls[0]
        assert first_o is t                                              # l'intero campione, lo stesso oggetto
        for (o, kw), fold in zip(spy.calls[1:], f):
            exp = [x for x in t if x.link_status in statuses and fold.train_start_ms <= x.closed_at_ms < fold.train_end_ms]
            assert o == exp                                              # solo i trade ammessi del TRAIN, nell'ordine
            assert isinstance(o, list)
        for _, kw in spy.calls:
            assert set(kw) == {"min_trades", "min_days", "confidence", "n_boot", "seed", "key", "link_statuses"}
            assert kw["min_trades"] == 4 and kw["min_days"] == 3 and kw["confidence"] == Decimal("0.9")
            assert kw["n_boot"] == 200 and kw["seed"] == 12345          # lo stesso seed a ogni fold
            assert kw["key"] is keyf and kw["link_statuses"] is statuses

    def test_key_is_never_evaluated_on_trades_with_a_status_that_is_not_admitted(self):
        """cell_stats non chiama key() sui trade filtrati: nemmeno il walk-forward (qui key solleverebbe)."""
        t = [out(f"k{i}", int((i + 0.5) * DAY), "A", 1, "10") for i in range(6)]
        t += [out(f"u{i}", int((i + 0.5) * DAY), "A", 1, "10", status="unlinked") for i in range(6)]
        seen = []

        def key(o):
            seen.append(o.link_status)
            if o.link_status != "linked":
                raise RuntimeError("key chiamata su un trade non ammesso")
            return (o.symbol,)
        rep = run(t, folds_of(0, 8, 3, 2, 3, 0, False), key=key, min_trades=3)
        assert set(seen) == {"linked"} and rep.n_selections >= 1

    def test_the_result_of_the_first_validation_call_is_ignored(self, monkeypatch):
        t, f = self._data()
        resp = lambda i, o: (cs(K("A"), "positive"),) if i == 0 else ()
        rep, _ = stubbed(monkeypatch, resp, t, f)
        assert rep.n_selections == 0 and all(fr.selected == () for fr in rep.folds)

    def test_selected_cell_without_test_trades_and_cells_never_seen_in_train(self, monkeypatch):
        t, f = self._data()
        resp = lambda i, o: () if i == 0 else (cs(K("C"), "positive"),)    # C non ha trade nel test
        rep, _ = stubbed(monkeypatch, resp, t, f)
        fr = rep.folds[0]
        c = fr.selected[0]
        assert (c.test_n, c.test_mean_net_bp) == (0, None)
        assert (fr.selected_test_n, fr.selected_test_mean_net_bp) == (0, None)
        assert (fr.rest_test_n, str(fr.rest_test_mean_net_bp)) == (5, "7.8000")      # 10+20+7+5-3 = 39 / 5
        assert rep.oos_n == 0 and rep.oos_mean_net_bp is None and rep.decay_bp is None

    def test_selected_plus_rest_equals_test_outcomes_and_unseen_cells_go_to_rest(self, monkeypatch):
        t, f = self._data()
        resp = lambda i, o: () if i == 0 else (cs(K("A"), "positive"),)
        rep, _ = stubbed(monkeypatch, resp, t, f)
        fr = rep.folds[0]
        assert fr.selected_test_n + fr.rest_test_n == fr.n_test_outcomes == 5
        assert fr.rest_test_n == 3                                    # B, D e la cella Z mai vista nel train

    def test_cell_identity_separates_one_from_true(self, monkeypatch):
        t = [out("a", int(3.5 * DAY), "A", 1, "10"), out("b", int(4.5 * DAY), "A", 1, "30"),
             out("c", int(0.5 * DAY), "A", 1, "1")]
        f = folds_of(0, 5, 3, 2, 3, 0, False)
        keyf = lambda o: (1,) if o.position_id in ("a", "c") else (True,)
        resp = lambda i, o: () if i == 0 else (cs((1,), "positive"),)
        rep, _ = stubbed(monkeypatch, resp, t, f, key=keyf)
        fr = rep.folds[0]
        assert (fr.selected_test_n, str(fr.selected_test_mean_net_bp)) == (1, "10.0000")      # solo la cella (1,)
        assert (fr.rest_test_n, str(fr.rest_test_mean_net_bp)) == (1, "30.0000")              # (True,) e' un'altra
        assert (fr.selected[0].test_n, str(fr.selected[0].test_mean_net_bp)) == (1, "10.0000")

    def test_is_mean_comes_from_exact_train_trades_of_selected_cells(self, monkeypatch):
        t, f = self._data()
        # A ha nel train un solo trade (net 1): is = 1.0000, anche se lo stub dichiara mean 3.5 per la cella
        resp = lambda i, o: () if i == 0 else (cs(K("A"), "positive", 7, "3.5", "0.5"),)
        rep, _ = stubbed(monkeypatch, resp, t, f)
        assert (rep.is_n, str(rep.is_mean_net_bp)) == (1, "1.0000")

    def test_aggregates_across_folds(self, monkeypatch):
        t = [out(f"x{i}", int((i + 0.5) * DAY), "A", 1, str(i)) for i in range(0, 10)]
        f = folds_of(0, 10, 3, 2, 3, 0, False)                       # 2 fold: test [3,5) e [6,8)
        resp = lambda i, o: () if i == 0 else (cs(K("A"), "positive"),)
        rep, _ = stubbed(monkeypatch, resp, t, f)
        assert rep.n_selections == len(f) and rep.n_folds_with_selection == len(f)
        assert rep.is_n == sum(fr.n_train_outcomes for fr in rep.folds)
        assert rep.oos_n == sum(fr.selected_test_n for fr in rep.folds)
        assert rep.rest_n == 0 and rep.rest_mean_net_bp is None

    def test_selection_is_decided_with_train_trades_only(self, monkeypatch):
        """Le chiamate per fold ricevono SOLO trade con chiusura nel train (niente test, niente embargo)."""
        t, _ = self._data()
        f = folds_of(0, 6, 3, 2, 3, 1, False)                         # embargo 1 giorno: test [4,6)
        _, spy = stubbed(monkeypatch, lambda i, o: (), t, f)
        for (o, _kw), fold in zip(spy.calls[1:], f):
            assert all(fold.train_start_ms <= x.closed_at_ms < fold.train_end_ms for x in o)
            assert not any(fold.train_end_ms <= x.closed_at_ms for x in o)


# ---------------------------------------------------------------------------
# nessuna fuga d'informazione (con meta-test)
# ---------------------------------------------------------------------------

def single(f):
    return [dataclasses.replace(f, index=0)]


def perturb_test_window(trades, f, rng):
    new = []
    for o in trades:
        if f.test_start_ms <= o.closed_at_ms < f.test_end_ms:
            new.append(dataclasses.replace(o, net_bp=-o.net_bp * 3 + Decimal(17)))
        else:
            new.append(o)
    for i in range(6):
        new.append(out(f"extra{i}", rng.randrange(f.test_start_ms, f.test_end_ms), f"S{i % 3}", 1, "777"))
    new.append(out("extra-new-cell", f.test_start_ms + 5, "BRAND-NEW", 1, "-500"))
    return new


def perturb_embargo(trades, f, rng):
    new = []
    for o in trades:
        if f.train_end_ms <= o.closed_at_ms < f.test_start_ms:
            new.append(dataclasses.replace(o, net_bp=o.net_bp * 5 + Decimal(1000)))
        else:
            new.append(o)
    for i in range(5):
        if f.test_start_ms > f.train_end_ms:
            new.append(out(f"emb{i}", rng.randrange(f.train_end_ms, f.test_start_ms), f"S{i}", 1, "9999"))
    return new


def leaky_selected_keys(trades, f):
    """Versione volutamente sbagliata: sceglie usando anche i trade di test."""
    train, test = o_members(trades, f, {"linked"})
    cs_ = cell_stats(train + test, key=default_cell_key, link_statuses=frozenset({"linked"}), **STAT)
    return [c.key for c in cs_ if c.status == "positive"]


def real_selected_keys(trades, f):
    rep = run(trades, single(f))
    return [c.key for c in rep.folds[0].selected]


class TestNoLeak:
    @pytest.mark.parametrize("seed", SEEDS[:12])
    def test_changing_or_adding_test_trades_never_changes_the_selection(self, seed):
        trades, folds = DATA[seed]
        rng = random.Random(seed)
        for f in folds[:3]:
            base = run(trades, single(f)).folds[0]
            alt = run(perturb_test_window(trades, f, rng), single(f)).folds[0]
            assert [(c.key, c.train_n, c.train_mean_net_bp, c.train_ci_low) for c in base.selected] == \
                   [(c.key, c.train_n, c.train_mean_net_bp, c.train_ci_low) for c in alt.selected]
            assert (base.n_train_outcomes, base.n_cells_evaluated, base.n_selected) == \
                   (alt.n_train_outcomes, alt.n_cells_evaluated, alt.n_selected)

    @pytest.mark.parametrize("seed", SEEDS[:12])
    def test_changing_the_embargo_changes_nothing_at_all(self, seed):
        trades, folds = DATA[seed]
        rng = random.Random(seed)
        for f in folds[:3]:
            assert flat(run(trades, single(f))) == flat(run(perturb_embargo(trades, f, rng), single(f)))

    def test_changing_a_train_trade_of_a_selected_cell_changes_is(self):
        trades, folds = DATA[0]
        done = 0
        for f in folds:
            rep = run(trades, single(f))
            if not rep.folds[0].selected:
                continue
            cid = rep.folds[0].selected[0].key
            train, _ = o_members(trades, f, {"linked"})
            victim = next(o for o in train if default_cell_key(o) == cid)
            alt = [dataclasses.replace(o, net_bp=o.net_bp + Decimal(1000)) if o is victim else o for o in trades]
            assert run(alt, single(f)).is_mean_net_bp != rep.is_mean_net_bp
            done += 1
        assert done >= 1

    def test_meta_a_leaky_selection_is_detected_by_the_perturbation_test(self):
        """Cella X: nel train rende poco (negativa/inconclusiva), nel test tantissimo. Una selezione che usa
        anche il test la sceglie e CAMBIA quando si perturba il test; quella vera no."""
        trades = []
        for i in range(6):
            trades.append(out(f"x-tr{i}", int((i + 0.5) * DAY), "X", 1, str(-10 + (i % 2) * 4)))
        for i in range(6):
            trades.append(out(f"x-te{i}", int((6.2 + i * 0.4) * DAY), "X", 1, "500"))
        f = folds_of(0, 9, 6, 3, 3, 0, False)[0]
        rng = random.Random(1)
        alt = perturb_test_window(trades, f, rng)
        assert real_selected_keys(trades, f) == real_selected_keys(alt, f)
        assert real_selected_keys(trades, f) == []
        assert leaky_selected_keys(trades, f) == [("X", 1, "TRENDING", False)]        # la fuga sceglie X
        assert leaky_selected_keys(alt, f) != leaky_selected_keys(trades, f)          # e il test la RILEVA


# ---------------------------------------------------------------------------
# validazione di walk_forward
# ---------------------------------------------------------------------------

VT = [out(f"v{i}", int((i + 0.5) * DAY), "A", 1, "10") for i in range(6)]
VF = folds_of(0, 8, 3, 2, 3, 0, False)


def call(**over):
    kw = dict(outcomes=VT, folds=VF, **STAT)
    kw.update(over)
    outcomes, folds = kw.pop("outcomes"), kw.pop("folds")
    return wf.walk_forward(outcomes, folds, **kw)


INHERITED = [
    ("invalid_outcome", dict(outcomes=None)),
    ("invalid_min_trades", dict(min_trades=0)),
    ("invalid_min_days", dict(min_days=1)),
    ("invalid_confidence", dict(confidence=Decimal("1"))),
    ("invalid_n_boot", dict(n_boot=199)),
    ("invalid_seed", dict(seed=True)),
    ("invalid_key", dict(key=5)),
    ("invalid_link_statuses", dict(link_statuses={"linked"})),
    ("invalid_folds", dict(folds=None)),
]


class _Seq(collections.abc.Sequence):
    def __init__(self, items):
        self._i = list(items)

    def __getitem__(self, i):
        return self._i[i]

    def __len__(self):
        return len(self._i)


def bad_fold(**over):
    f = dataclasses.replace(VF[0], **over)
    return [f]


class TestValidation:
    @pytest.mark.parametrize("code,over", INHERITED)
    def test_each_code_exact_message(self, code, over):
        with pytest.raises(ValueError) as e:
            call(**over)
        assert str(e.value) == code and e.value.__cause__ is None

    @pytest.mark.parametrize("i,j", list(itertools.combinations(range(len(INHERITED)), 2)))
    def test_error_order_every_pair(self, i, j):
        over = dict(INHERITED[j][1])
        over.update(INHERITED[i][1])
        with pytest.raises(ValueError) as e:
            call(**over)
        assert str(e.value) == INHERITED[i][0]

    @pytest.mark.parametrize("outs", [None, 5, "abc", (x for x in VT), iter(VT), [VT[0], None], [VT[0], {}],
                                      VT[:-1] + [dataclasses.replace(VT[0], net_bp=Decimal("NaN"))],
                                      VT[:-1] + [dataclasses.replace(VT[0], closed_at_ms=True)],
                                      {VT[0]}])
    def test_invalid_outcome_variants_win_over_bad_folds(self, outs):
        with pytest.raises(ValueError) as e:
            call(outcomes=outs, folds=None)
        assert str(e.value) == "invalid_outcome"

    @pytest.mark.parametrize("folds", [
        None, [], (), 5, "abc", {}, {0: VF[0]}, (f for f in VF), iter(VF), [None], [VF[0], None], [dict()],
        [dataclasses.astuple(VF[0])],
    ])
    def test_invalid_folds_shapes(self, folds):
        with pytest.raises(ValueError) as e:
            call(folds=folds)
        assert str(e.value) == "invalid_folds"

    def test_a_subclass_of_fold_is_rejected_like_the_exact_type_checks_elsewhere(self):
        # stessa severita' di `type(v) is not int` / `type(expanding) is not bool`: solo `Fold` esatto
        class FoldX(wf.Fold):
            pass

        f = VF[0]
        sub = FoldX(f.index, f.train_start_ms, f.train_end_ms, f.test_start_ms, f.test_end_ms)
        assert isinstance(sub, wf.Fold) and type(sub) is not wf.Fold
        with pytest.raises(ValueError) as e:
            call(folds=[sub])
        assert str(e.value) == "invalid_folds"
        with pytest.raises(ValueError) as e:
            call(folds=[f, sub])
        assert str(e.value) == "invalid_folds"

    @pytest.mark.parametrize("over", [
        dict(train_start_ms=False), dict(index=False), dict(train_end_ms=float(3 * DAY)),
        dict(test_start_ms=None), dict(test_end_ms="x"),
        dict(train_start_ms=-1), dict(train_start_ms=3 * DAY),                    # train_start >= train_end
        dict(train_end_ms=3 * DAY + 1, test_start_ms=3 * DAY),                    # train_end > test_start
        dict(test_end_ms=3 * DAY), dict(test_start_ms=5 * DAY, test_end_ms=5 * DAY),
        dict(index=1), dict(index=-1),
    ])
    def test_invalid_single_fold(self, over):
        with pytest.raises(ValueError) as e:
            call(folds=bad_fold(**over))
        assert str(e.value) == "invalid_folds"

    @pytest.mark.parametrize("pos", [0, 1, 2, 3])
    def test_every_fold_is_checked_not_only_the_first(self, pos):
        folds = list(folds_of(0, 20, 3, 2, 3, 0, False))[:4]
        assert len(folds) == 4
        folds[pos] = dataclasses.replace(folds[pos], train_start_ms=-5)
        with pytest.raises(ValueError) as e:
            call(folds=folds)
        assert str(e.value) == "invalid_folds"

    @pytest.mark.parametrize("pos", [1, 2, 3])
    def test_wrong_index_in_any_position(self, pos):
        folds = list(folds_of(0, 20, 3, 2, 3, 0, False))[:4]
        folds[pos] = dataclasses.replace(folds[pos], index=pos + 1)
        with pytest.raises(ValueError):
            call(folds=folds)

    def test_overlapping_and_unordered_tests(self):
        a = folds_of(0, 20, 3, 2, 3, 0, False)
        over = [a[0], dataclasses.replace(a[1], train_end_ms=a[0].test_end_ms - 1, test_start_ms=a[0].test_end_ms - 1)]
        with pytest.raises(ValueError) as e:
            call(folds=over)
        assert str(e.value) == "invalid_folds"
        swapped = [dataclasses.replace(a[1], index=0), dataclasses.replace(a[0], index=1)]
        with pytest.raises(ValueError) as e:
            call(folds=swapped)
        assert str(e.value) == "invalid_folds"
        same = [a[0], dataclasses.replace(a[0], index=1)]
        with pytest.raises(ValueError):
            call(folds=same)

    def test_valid_unusual_folds_are_accepted(self):
        a = folds_of(0, 20, 3, 2, 3, 0, False)
        touching = [a[0], dataclasses.replace(a[1], test_start_ms=a[0].test_end_ms, train_end_ms=a[0].test_end_ms)]
        assert len(call(folds=touching).folds) == 2                     # test_start[k+1] == test_end[k]: ok
        gap = [a[0], dataclasses.replace(a[2], index=1)]
        assert len(call(folds=gap).folds) == 2                          # buchi fra i test: ok
        exp = list(folds_of(0, 20, 3, 2, 3, 0, True))
        assert len(call(folds=exp).folds) == len(exp)                   # train che si allarga: ok
        assert len(call(folds=tuple(a)).folds) == len(a)
        assert len(call(folds=list(a)).folds) == len(a)

    def test_any_collections_abc_sequence_of_folds_is_a_valid_sequence(self):
        """Il contratto dice «sequenza» (come per outcomes), non «list o tuple»."""
        a = folds_of(0, 20, 3, 2, 3, 0, False)
        assert flat(call(folds=_Seq(a))) == flat(call(folds=a))

    def test_bool_for_int_arguments_with_numerically_valid_values(self):
        with pytest.raises(ValueError, match="^invalid_min_trades$"):
            call(min_trades=True)                                       # 1 e' un valore valido
        with pytest.raises(ValueError, match="^invalid_seed$"):
            call(seed=False)                                            # 0 e' un valore valido
        with pytest.raises(ValueError, match="^invalid_folds$"):
            call(folds=bad_fold(train_start_ms=False))                  # 0 e' un valore valido
        with pytest.raises(ValueError, match="^invalid_folds$"):
            call(folds=bad_fold(index=False))                           # indice atteso 0

    def test_no_arguments_have_numeric_defaults_and_all_are_keyword_only(self):
        sig = inspect.signature(wf.walk_forward)
        assert list(sig.parameters) == ["outcomes", "folds", "min_trades", "min_days", "confidence", "n_boot",
                                        "seed", "key", "link_statuses"]
        for n in ("min_trades", "min_days", "confidence", "n_boot", "seed"):
            p = sig.parameters[n]
            assert p.kind is inspect.Parameter.KEYWORD_ONLY and p.default is inspect.Parameter.empty
        assert sig.parameters["key"].default is default_cell_key
        assert sig.parameters["link_statuses"].default == frozenset({"linked"})

    def test_validation_happens_before_any_calculation(self, monkeypatch):
        spy = Spy(lambda i, o: ())
        monkeypatch.setattr(wf, "cell_stats", spy)
        with pytest.raises(ValueError):
            call(folds=None)
        assert len(spy.calls) == 1                       # solo la chiamata di validazione, nessuna per fold


# ---------------------------------------------------------------------------
# invarianti b-f
# ---------------------------------------------------------------------------

class TestInvariants:
    @pytest.mark.parametrize("seed", SEEDS[:10])
    def test_b_a_trade_is_in_at_most_one_test_window(self, seed):
        trades, folds = DATA[seed]
        rep = run(trades, folds)
        linked = [o for o in trades if o.link_status == "linked"]
        in_tests = sum(1 for o in linked if any(f.test_start_ms <= o.closed_at_ms < f.test_end_ms for f in folds))
        assert sum(fr.n_test_outcomes for fr in rep.folds) == in_tests
        for fr in rep.folds:
            assert fr.selected_test_n + fr.rest_test_n == fr.n_test_outcomes

    @pytest.mark.parametrize("seed", SEEDS[:10])
    def test_c_input_order_is_irrelevant(self, seed):
        trades, folds = DATA[seed]
        base = flat(run(trades, folds))
        for k in range(3):
            sh = list(trades)
            random.Random(k).shuffle(sh)
            assert flat(run(sh, folds)) == base
        assert flat(run(list(reversed(trades)), folds)) == base

    @pytest.mark.parametrize("seed", SEEDS[:6])
    def test_d_inputs_are_not_mutated(self, seed):
        trades, folds = DATA[seed]
        t0, f0 = list(trades), list(folds)
        snap_t, snap_f = copy.deepcopy(trades), copy.deepcopy(folds)
        run(trades, folds)
        assert trades == t0 and all(a is b for a, b in zip(trades, t0)) and len(trades) == len(t0)
        assert list(folds) == f0 and trades == snap_t and folds == snap_f

    @pytest.mark.parametrize("seed", SEEDS[:6])
    def test_e_same_input_same_output_and_other_inputs_pass_through(self, seed):
        trades, folds = DATA[seed]
        assert flat(run(trades, folds)) == flat(run(trades, folds))

    @pytest.mark.parametrize("seed", SEEDS[:8])
    def test_f_ambient_decimal_context_is_irrelevant(self, seed):
        trades, folds = DATA[seed]
        base, base5 = flat(run(trades, folds)), flat(run(trades, folds, min_trades=5))
        with localcontext() as c:
            c.prec = 5
            c.rounding = ROUND_DOWN
            assert flat(run(trades, folds)) == base
            assert flat(run(trades, folds, min_trades=5)) == base5

    def test_shape_immutability_and_types(self):
        trades, folds = DATA[1]
        rep = run(trades, folds)
        assert type(rep.folds) is tuple and all(type(fr.selected) is tuple for fr in rep.folds)
        for ob in (rep, rep.folds[0], rep.folds[0].fold):
            with pytest.raises(dataclasses.FrozenInstanceError):
                setattr(ob, "index" if isinstance(ob, wf.Fold) else "folds", 1)
        names = [fl.name for fl in dataclasses.fields(wf.WalkForwardReport)]
        assert names == ["folds", "n_selections", "n_folds_with_selection", "is_n", "is_mean_net_bp", "oos_n",
                         "oos_mean_net_bp", "rest_n", "rest_mean_net_bp", "decay_bp"]
        assert [fl.name for fl in dataclasses.fields(wf.FoldResult)] == [
            "fold", "n_train_outcomes", "n_test_outcomes", "n_cells_evaluated", "n_selected", "selected",
            "selected_test_n", "selected_test_mean_net_bp", "rest_test_n", "rest_test_mean_net_bp"]
        assert [fl.name for fl in dataclasses.fields(wf.SelectedCell)] == [
            "key", "train_n", "train_mean_net_bp", "train_ci_low", "test_n", "test_mean_net_bp"]
        assert [fl.name for fl in dataclasses.fields(wf.Fold)] == [
            "index", "train_start_ms", "train_end_ms", "test_start_ms", "test_end_ms"]
        for fr in rep.folds:
            for v in (fr.selected_test_mean_net_bp, fr.rest_test_mean_net_bp):
                assert v is None or v.as_tuple().exponent == -4

    def test_empty_outcomes_gives_empty_report(self):
        rep = run([], VF)
        assert rep.n_selections == 0 and rep.is_mean_net_bp is None and rep.oos_mean_net_bp is None
        assert rep.rest_mean_net_bp is None and rep.decay_bp is None
        assert all((fr.n_train_outcomes, fr.n_test_outcomes, fr.n_selected) == (0, 0, 0) for fr in rep.folds)


# ---------------------------------------------------------------------------
# scale estreme: risultato uguale all'oracolo oppure errore tipizzato, mai eccezione grezza
# ---------------------------------------------------------------------------

def hugeset(v, n=8):
    t = [out(f"h{i}", int((i % 4 + 0.5) * DAY), "A", 1, v) for i in range(n)]
    t += [out(f"g{i}", int((4 + i % 2 + 0.5) * DAY), "A", 1, v) for i in range(3)]
    return t


class TestExtremeScales:
    @pytest.mark.parametrize("v", ["1E+50", "9.99E+55", "1E+56", "-1E+56", "1E+57", "1E+100", "1E+999990",
                                   "9E+999999", "-9E+999999", "1E-50", "1E-999990", "-1E-999990"])
    def test_correct_or_typed_error_never_raw(self, v):
        t = hugeset(v)
        f = folds_of(0, 6, 4, 2, 4, 0, False)
        try:
            rep = run(t, f, min_trades=4)
        except ValueError as e:
            assert str(e) == "invalid_outcome" and e.__cause__ is None
        else:
            if abs(Decimal(v).adjusted()) <= 200:     # con esponenti enormi i Fraction sarebbero interi da milioni di cifre
                assert flat(rep) == o_walk(t, f, min_trades=4,
                                           **{k: x for k, x in STAT.items() if k != "min_trades"})

    def test_tiny_values_are_zero_not_negative_zero(self):
        t = hugeset("-1E-30")
        rep = run(t, folds_of(0, 6, 4, 2, 4, 0, False), min_trades=4)
        assert "-0.0000" not in repr(flat(rep))

    def test_decay_that_cannot_be_represented_is_a_typed_error(self):
        """is = +9E+55 e oos = -9E+55: ogni media sta in 60 cifre, il decadimento (1,8E+56) no."""
        t = [out(f"a{i}", int((i + 0.5) * DAY), "A", 1, "9E+55") for i in range(3)]
        t += [out(f"b{i}", int((3.5 + i) * DAY), "A", 1, "-9E+55") for i in range(2)]
        with pytest.raises(ValueError) as e:
            run(t, folds_of(0, 6, 3, 2, 3, 0, False), min_trades=3, min_days=3)
        assert str(e.value) == "invalid_outcome" and e.value.__cause__ is None and e.value.__suppress_context__


# ---------------------------------------------------------------------------
# purezza (sui NOMI), forma del sorgente
# ---------------------------------------------------------------------------

SRC = Path(wf.__file__).read_text()
TREE = ast.parse(SRC)


class TestPurity:
    def test_imports_are_standard_library_plus_the_two_internal_modules_by_name(self):
        std = {"__future__", "collections.abc", "dataclasses", "decimal", "typing"}
        internal = {"backend.v3.learning.expectancy": {"CellStats", "cell_stats", "default_cell_key"},
                    "backend.v3.outcomes": {"TradeOutcome"}}
        seen = {}
        for n in ast.walk(TREE):
            if isinstance(n, ast.Import):
                raise AssertionError(f"import semplice vietato: {[a.name for a in n.names]}")
            if isinstance(n, ast.ImportFrom):
                assert n.level == 0
                if n.module in internal:
                    seen[n.module] = {a.name for a in n.names}
                else:
                    assert n.module in std, n.module
        assert seen == internal

    def test_every_imported_name_is_used(self):
        imported = {}
        for n in ast.walk(TREE):
            if isinstance(n, ast.ImportFrom) and n.module != "__future__":
                for a in n.names:
                    imported[a.asname or a.name] = n.module
        used = {n.id for n in ast.walk(TREE) if isinstance(n, ast.Name)}
        unused = sorted(set(imported) - used)
        assert not unused, f"nomi importati e mai usati: {unused}"

    def test_no_float_clock_randomness_io(self):
        names = {n.id for n in ast.walk(TREE) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(TREE) if isinstance(n, ast.Attribute)}
        assert not (names & {"float", "open", "print", "input", "eval", "exec", "__import__", "random", "time",
                             "datetime", "os", "sys"})
        assert not (attrs & {"time", "now", "random", "randrange", "open", "read_text", "getenv"})
        consts = [n.value for n in ast.walk(TREE) if isinstance(n, ast.Constant) and isinstance(n.value, float)]
        assert consts == []

    def test_key_cell_stats_and_default_are_module_globals(self):
        for n in ("cell_stats", "default_cell_key", "CellStats", "TradeOutcome"):
            assert hasattr(wf, n)

    def test_cell_stats_is_the_expectancy_one(self):
        import backend.v3.learning.expectancy as ex
        assert wf.cell_stats is ex.cell_stats and wf.default_cell_key is ex.default_cell_key

    def test_dead_code_is_absent(self):
        defined = {n.name for n in TREE.body if isinstance(n, ast.FunctionDef)}
        used = {n.id for n in ast.walk(TREE) if isinstance(n, ast.Name)}
        assert not [d for d in defined if not d.startswith("__") and d not in used and d not in
                    {"make_folds", "walk_forward"}], "funzioni private mai chiamate"


# ---------------------------------------------------------------------------
# velocita' (cell_stats stub: si misura solo il modulo). >= 60 000 trade
# ---------------------------------------------------------------------------

def fast_cell_stats(trades, **kw):
    groups = {}
    for o in trades:
        groups.setdefault(default_cell_key(o), []).append(o)
    return tuple(cs(k, "positive", len(v)) for k, v in groups.items())


def big(n, ncells, days=600, seed=1):
    r = random.Random(seed)
    return [out(f"p{i}", DAY + r.randrange(days) * DAY + r.randrange(DAY), f"S{r.randrange(ncells)}", 1,
                str(r.randint(-300, 300))) for i in range(n)]


def timed(monkeypatch, n, ncells, n_folds=40):
    monkeypatch.setattr(wf, "cell_stats", fast_cell_stats)
    trades = big(n, ncells)
    folds = folds_of(0, 620, 120, 10, 10, 0, False)[:n_folds]
    t0 = time.perf_counter()
    rep = run(trades, folds)
    dt = time.perf_counter() - t0
    assert len(rep.folds) == len(folds) and rep.n_selections > 0
    return dt


class TestSpeed:
    def test_60000_trades_20_cells_40_folds(self, monkeypatch):
        assert timed(monkeypatch, 60_000, 20) < 6.0

    def test_time_grows_linearly_with_the_number_of_trades(self, monkeypatch):
        small = min(timed(monkeypatch, 15_000, 20) for _ in range(2))
        large = min(timed(monkeypatch, 60_000, 20) for _ in range(2))
        assert large / max(small, 1e-3) < 6.0, (small, large)               # lineare ~4, quadratico ~16

    def test_many_cells_cost_the_same_as_few(self, monkeypatch):
        few = timed(monkeypatch, 15_000, 75)
        many = timed(monkeypatch, 15_000, 300)
        assert many < 10.0, many
        assert many / max(few, 0.3) < 2.5, (few, many)                    # O(N), non O(N * celle selezionate)
