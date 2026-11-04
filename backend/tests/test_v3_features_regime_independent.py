"""F7 / P8 - classificatore di regime: verifica INDIPENDENTE (Claude) del modulo di Grok.

Il suo file ha 5 test (un vettore, un troncamento su barre piatte, tre controlli di validazione, purezza
sui moduli e non sui nomi); oracolo, soglie a bordo, ordine delle regole, serie di ingresso a None, scala
estrema e velocita' risultavano NON ESEGUITI. Qui:

* ORACOLO ``Fraction`` scritto dal contratto con algoritmi diversi dal modulo (ATR in forma chiusa, rango
  percentile con ordinamento/bisect, ADX dalle formule a somme pesate), le regole applicate a parte;
* serie di ingresso SOSTITUITE da valori scelti (``monkeypatch``) per provare a bordo ogni soglia, l'ordine
  delle regole, ogni ``None``, e gli argomenti con cui sono chiamate le quattro funzioni di ingresso;
* troncamento con meta-test, validazione esaustiva (codici esatti, ordine), scale estreme per invarianza di
  scala, contesto Decimal ambientale, forma, purezza AST sui NOMI importati, velocita' a 60 000 barre.
"""
from __future__ import annotations

import ast
import copy
import dataclasses
import decimal
import inspect
import random
import time
from bisect import bisect_right
from decimal import ROUND_UP, Context, Decimal, getcontext, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from backend.v3.features import regime as R
from backend.v3.features.indicators import AdxSeries, Bar, check_bars
from backend.v3.features.regime import REGIME_LABELS, RegimeParams, regime_labels

D = Decimal
CMS = 60_000
F = Fraction


# ============================================================ dati
def make_bars(rng: random.Random, length: int, mode: str, t0: int = 0):
    out, price = [], 30
    for k in range(length):
        if mode == "flat":
            o = h = lo = c = price
        else:
            o = price
            if mode == "spiky" and rng.random() < 0.2:
                o = max(1, price + rng.randint(-6, 6))
            c = o + rng.randint(1, 4) if mode == "up" else (max(1, o - rng.randint(1, 4)) if mode == "down" else max(1, o + rng.randint(-4, 4)))
            h = max(o, c) + rng.randint(0, 3)
            lo = max(1, min(o, c) - rng.randint(0, 3))
        out.append(Bar((t0 + k) * CMS, D(o), D(h), D(lo), D(c), D(1)))
        price = c
    return out


def with_spikes(bars, rng):
    out = list(bars)
    for _ in range(max(1, len(out) // 12)):
        k = rng.randrange(len(out))
        b = out[k]
        out[k] = Bar(b.open_time_ms, b.open, b.high + rng.randint(5, 25), b.low, b.close, b.volume)
    return out


def hl_bars(pairs, t0=0):
    out = []
    for k, (h, lo) in enumerate(pairs):
        mid = (D(h) + D(lo)) / 2
        out.append(Bar((t0 + k) * CMS, mid, D(h), D(lo), mid, D(1)))
    return out


MODES = ("walk", "up", "down", "flat", "spiky")
LENGTHS = (1, 2, 3, 6, 12, 25, 40, 70)
DATASETS = []
_rng = random.Random(20261104)
for _i, (_m, _n) in enumerate((m, n) for m in MODES for n in LENGTHS):
    _b = make_bars(_rng, _n, _m, t0=_i % 5)
    DATASETS.append((f"{_m}-{_n}", _b))
    if _m != "flat" and _n >= 12:
        DATASETS.append((f"{_m}-{_n}-spike", with_spikes(_b, _rng)))
VECTOR_HL = [(101, 99), (103, 100), (101, 99), (104, 100), (102, 99), (104, 100), (102, 99), (103, 100),
             (112, 99), (113, 106), (116, 111), (121, 115), (125, 120), (129, 124), (126, 121), (120, 115),
             (114, 109), (108, 103), (102, 97), (100, 98), (101, 99), (100, 98), (101, 98), (100, 99)]
VECTOR_LABELS = ("UNCERTAIN", "UNCERTAIN", "UNCERTAIN", "EXPANSION", "RANGE", "EXPANSION", "RANGE", "RANGE",
                 "SHOCK", "TREND_UP", "TREND_UP", "TREND_UP", "TREND_UP", "TREND_UP", "UNCERTAIN", "EXPANSION",
                 "EXPANSION", "EXPANSION", "EXPANSION", "TREND_DOWN", "TREND_DOWN", "TREND_DOWN", "RANGE", "RANGE")
VECTOR_PARAMS = RegimeParams(D("1.5"), D("100"), D("60"), D("40"))
DATASETS.append(("vector", hl_bars(VECTOR_HL)))
NSETS = [(1, 1, 1), (2, 3, 2), (2, 4, 3), (3, 5, 2), (5, 4, 5), (1, 2, 4), (3, 1, 1), (14, 20, 14)]
# (shock_tr_mult, expansion_pct_min, adx_trend_min, adx_range_max); pct 100/50/25/75 sono esatti con finestra 4
PSETS = [(F(3, 2), F(100), F(25), F(10)), (F(2), F(75), F(20), F(19)), (F(1), F(0), F(15), F(5)),
         (F(5, 4), F(50), F(30), F(29)), (F(3), F(100), F(60), F(40)), (F(7, 5), F(25), F(10), F(0))]


def params_of(t):
    return RegimeParams(*(D(x.numerator) / D(x.denominator) for x in t))


# ============================================================ oracolo (Fraction)
def closed_form(vals, alpha: Fraction):
    beta = 1 - alpha
    pw = [F(1)]
    for _ in range(len(vals)):
        pw.append(pw[-1] * beta)
    return [alpha * sum((pw[j] * vals[i - j] for j in range(i)), F(0)) + pw[i] * vals[0] for i in range(len(vals))]


def o_tr(bars):
    out = []
    for i, b in enumerate(bars):
        h, lo = F(b.high), F(b.low)
        out.append(h - lo if i == 0 else max(h - lo, abs(h - F(bars[i - 1].close)), abs(lo - F(bars[i - 1].close))))
    return out


def o_series(bars, atr_n, win, adx_n):
    """(tr, atr, atr_percentile, +DI, -DI, ADX) come Fraction / None, secondo i contratti di P7 e P7b."""
    n = len(bars)
    tr = o_tr(bars)
    e = closed_form(tr, F(1, atr_n))
    a = [None if i < atr_n - 1 else e[i] for i in range(n)]
    p = [None] * n
    for i in range((atr_n - 1) + (win - 1), n):
        w = sorted(a[i - win + 1:i + 1])
        p[i] = 100 * F(bisect_right(w, a[i]), win)
    H, L = [F(b.high) for b in bars], [F(b.low) for b in bars]
    pdm, mdm = [F(0)], [F(0)]
    for i in range(1, n):
        up, dn = H[i] - H[i - 1], L[i - 1] - L[i]
        pdm.append(up if (up > dn and up > 0) else F(0))
        mdm.append(dn if (dn > up and dn > 0) else F(0))
    ta = closed_form(tr, F(1, adx_n))
    ps, ms = closed_form(pdm, F(1, adx_n)), closed_form(mdm, F(1, adx_n))
    pdi = [100 * ps[i] / ta[i] if ta[i] != 0 else F(0) for i in range(n)]
    mdi = [100 * ms[i] / ta[i] if ta[i] != 0 else F(0) for i in range(n)]
    dx = [100 * abs(pdi[i] - mdi[i]) / (pdi[i] + mdi[i]) if pdi[i] + mdi[i] > 0 else F(0) for i in range(n)]
    ad = closed_form(dx, F(1, adx_n))
    return (tr, a, p, [None if i < adx_n - 1 else pdi[i] for i in range(n)],
            [None if i < adx_n - 1 else mdi[i] for i in range(n)], [None if i < 2 * adx_n - 2 else ad[i] for i in range(n)])


AMBIG = "AMBIG"
NEAR = F(1, 10**45)


def near(x, y):
    return abs(x - y) <= NEAR * max(1, abs(y))


_WIDE = Context(prec=400)


def decimal_exact(x: Fraction) -> bool:
    """x e' rappresentabile esattamente con i 60 cifre significative del contesto degli indicatori?"""
    d = _WIDE.divide(D(x.numerator), D(x.denominator))
    return F(d) == x and len(d.normalize(_WIDE).as_tuple().digits) <= 60


def ambiguous(x, y, *operands):
    """Confronto x ? y indefinito per l'oracolo: quasi-pareggio, tranne il pareggio esatto i cui OPERANDI (le serie
    degli indicatori da cui x e y derivano) il Decimal rappresenta esattamente: li' modulo e oracolo concordano e il
    caso si DEVE provare."""
    if not near(x, y):
        return False
    return not (x == y and all(decimal_exact(v) for v in (operands or (x, y))))


def o_rules(series, mult, exp_min, trend_min, range_max):
    """Etichette attese. ``AMBIG`` dove un confronto cade (quasi) esattamente su una soglia razionale che il
    Decimal a 60 cifre degli indicatori non rappresenta (p.es. ATR = 20/3 con n=3 e tr = 1.5*ATR): li' l'etichetta
    del modulo segue i Decimal arrotondati, non i razionali, e il confronto con l'oracolo non e' definito."""
    tr, a, p, pdi, mdi, adx = series
    out = []
    for i in range(len(tr)):
        if None in (a[i], p[i], pdi[i], mdi[i], adx[i]):
            out.append("UNCERTAIN")
        elif (ambiguous(tr[i], mult * a[i], tr[i], a[i]) or ambiguous(adx[i], trend_min) or ambiguous(adx[i], range_max)
              or ambiguous(pdi[i], mdi[i])):
            out.append(AMBIG)
        elif tr[i] > mult * a[i]:
            out.append("SHOCK")
        elif p[i] >= exp_min:
            out.append("EXPANSION")
        elif adx[i] >= trend_min and pdi[i] > mdi[i]:
            out.append("TREND_UP")
        elif adx[i] >= trend_min and mdi[i] > pdi[i]:
            out.append("TREND_DOWN")
        elif adx[i] <= range_max:
            out.append("RANGE")
        else:
            out.append("UNCERTAIN")
    return tuple(out)


# ============================================================ vettore e controlli a mano
class TestHandVector:
    def test_grok_vector_exact(self):
        assert regime_labels(hl_bars(VECTOR_HL), 2, 3, 2, VECTOR_PARAMS, candle_ms=CMS) == VECTOR_LABELS

    def test_vector_agrees_with_the_oracle(self):
        """Se no, l'errore e' mio (o del contratto) e non del modulo."""
        ser = o_series(hl_bars(VECTOR_HL), 2, 3, 2)
        assert o_rules(ser, F(3, 2), F(100), F(60), F(40)) == VECTOR_LABELS
        tr, a, p, pdi, mdi, adx = ser
        assert tr[8] == 13 and a[8] == F(1033, 128) and tr[8] > F(3, 2) * a[8]                   # SHOCK a k=8
        assert p[3] == 100 and F(56) < adx[14] < F(57) and pdi[14] > mdi[14]                     # k=3 EXPANSION, k=14 fra le soglie
        assert tr[9] <= F(3, 2) * a[9] and p[9] == F(200, 3) and adx[9] > 79 and pdi[9] > 38 and mdi[9] < 2

    def test_guard_all_labels_in_vector(self):
        assert set(VECTOR_LABELS) == set(REGIME_LABELS)


# ============================================================ contro l'oracolo
class TestAgainstOracle:
    def test_every_label_every_dataset(self):
        seen, ties, shorts, ambig, total = {k: 0 for k in REGIME_LABELS}, 0, 0, 0, 0
        for name, bars in DATASETS:
            for an, w, adn in NSETS:
                ser = o_series(bars, an, w, adn)
                shorts += (an - 1) + (w - 1) >= len(bars) or 2 * adn - 2 >= len(bars)
                for t in PSETS:
                    got = regime_labels(bars, an, w, adn, params_of(t), candle_ms=CMS)
                    want = o_rules(ser, *t)
                    assert len(got) == len(want)
                    assert all(x == AMBIG or g == x for g, x in zip(got, want)), (name, (an, w, adn), t,
                                                                               [i for i, (g, x) in enumerate(zip(got, want)) if x != AMBIG and g != x][:5])
                    for lab in want:
                        if lab != AMBIG:
                            seen[lab] += 1
                    ambig += want.count(AMBIG)
                    total += len(want)
                    ties += sum(1 for x in ser[2] if x is not None and x == t[1])       # p == soglia di expansion esatta
        assert all(seen[k] > 200 for k in REGIME_LABELS), seen                          # tutte e sei, ciascuna ben rappresentata
        assert 0 < ambig < total * 0.03, (ambig, total)                                 # i casi non definiti ci sono ma sono pochi
        assert ties > 100 and shorts > 100, (ties, shorts)

    def test_exact_rational_tie_follows_the_decimal_values_of_the_inputs(self):
        """Limite noto e dichiarato: tr = 10 e ATR = 20/3 (n=3): tr == 1.5*ATR in razionali, ma l'ATR Decimal e'
        6.666...6 (60 cifre) e 1.5*ATR = 9.999...9 < tr. Il modulo confronta i Decimal degli indicatori, quindi SHOCK."""
        bars = dict(DATASETS)["down-6"]
        ser = o_series(bars, 3, 1, 1)
        assert ser[0][2] == 10 and ser[1][2] == F(20, 3) and ser[0][2] == F(3, 2) * ser[1][2]
        assert o_rules(ser, F(3, 2), F(100), F(25), F(10))[2] == AMBIG
        assert regime_labels(bars, 3, 1, 1, params_of(PSETS[0]), candle_ms=CMS)[2] == "SHOCK"
        with localcontext(R._CTX):
            tr = R.true_range(bars, candle_ms=CMS)
            a = R.atr(bars, 3, candle_ms=CMS)
            assert tr[2] > D("1.5") * a[2]
        assert regime_labels(bars, 3, 1, 1, params_of((F(2), F(100), F(25), F(10))), candle_ms=CMS)[2] == "EXPANSION"   # 2*ATR > tr: niente tie

    def test_shock_is_present_in_random_data(self):
        """Guardia: lo SHOCK non e' solo nel vettore a mano."""
        cnt = 0
        for name, bars in DATASETS:
            if name.endswith("spike") and len(bars) >= 12:
                cnt += o_rules(o_series(bars, 2, 3, 2), F(3, 2), F(100), F(25), F(10)).count("SHOCK")
        assert cnt >= 10, cnt


# ============================================================ serie di ingresso sostituite
BASE = dict(tr=D(1), a=D(1), p=D(10), pdi=D(30), mdi=D(10), adx=D(25))            # UNCERTAIN: ADX fra le soglie
SP = RegimeParams(D("1.5"), D("80"), D("30"), D("20"))


def run_stub(monkeypatch, rows, params=SP, atr_n=2, pct_window=3, adx_n=2):
    """rows: lista di dict (uno per barra) con le sei serie; None ammesso."""
    n = len(rows)
    col = lambda k: tuple(r[k] for r in rows)
    monkeypatch.setattr(R, "true_range", lambda b, *, candle_ms: col("tr"))
    monkeypatch.setattr(R, "atr", lambda b, nn, *, candle_ms: col("a"))
    monkeypatch.setattr(R, "atr_percentile", lambda b, nn, w, *, candle_ms: col("p"))
    monkeypatch.setattr(R, "adx", lambda b, nn, *, candle_ms: AdxSeries(col("pdi"), col("mdi"), col("adx")))
    return regime_labels(hl_bars([(11, 9)] * n), atr_n, pct_window, adx_n, params, candle_ms=CMS)


def one(monkeypatch, **over):
    return run_stub(monkeypatch, [{**BASE, **over}])[0]


class TestRulesWithStubbedInputs:
    def test_control_is_uncertain(self, monkeypatch):
        assert one(monkeypatch) == "UNCERTAIN"

    @pytest.mark.parametrize("tr,want", [(D("1.5"), "UNCERTAIN"), (D("1.5000000001"), "SHOCK"), (D("1.4999999999"), "UNCERTAIN"), (D(9), "SHOCK")])
    def test_shock_threshold_is_strict(self, monkeypatch, tr, want):
        assert one(monkeypatch, tr=tr) == want

    @pytest.mark.parametrize("tr", [D("3.0"), D("0.75")])
    def test_shock_multiplies_atr_not_tr(self, monkeypatch, tr):
        a = tr / D("1.5")                                      # a diverso da 1: tr == 1.5*a esatto -> non shock
        assert one(monkeypatch, tr=tr, a=a) == "UNCERTAIN"
        assert one(monkeypatch, tr=tr + D("0.0001"), a=a) == "SHOCK"

    @pytest.mark.parametrize("p,want", [(D(80), "EXPANSION"), (D("79.9999"), "UNCERTAIN"), (D(100), "EXPANSION"), (D(0), "UNCERTAIN")])
    def test_expansion_threshold_is_inclusive(self, monkeypatch, p, want):
        assert one(monkeypatch, p=p) == want

    @pytest.mark.parametrize("adx,pdi,mdi,want", [
        (D(30), D(40), D(10), "TREND_UP"), (D("29.9999"), D(40), D(10), "UNCERTAIN"), (D(99), D(40), D(10), "TREND_UP"),
        (D(30), D(10), D(40), "TREND_DOWN"), (D("29.9999"), D(10), D(40), "UNCERTAIN"),
        (D(50), D(25), D(25), "UNCERTAIN"),                                   # +DI == -DI con ADX sopra: nessun trend
        (D(50), D("25.0000001"), D(25), "TREND_UP"), (D(50), D(25), D("25.0000001"), "TREND_DOWN"),
    ])
    def test_trend_rules(self, monkeypatch, adx, pdi, mdi, want):
        assert one(monkeypatch, adx=adx, pdi=pdi, mdi=mdi) == want

    @pytest.mark.parametrize("adx,want", [(D(20), "RANGE"), (D("20.0000001"), "UNCERTAIN"), (D(0), "RANGE"), (D("19.9999"), "RANGE")])
    def test_range_threshold_is_inclusive(self, monkeypatch, adx, want):
        assert one(monkeypatch, adx=adx) == want

    def test_range_ignores_di(self, monkeypatch):
        assert one(monkeypatch, adx=D(5), pdi=D(40), mdi=D(1)) == "RANGE"
        assert one(monkeypatch, adx=D(5), pdi=D(1), mdi=D(40)) == "RANGE"

    @pytest.mark.parametrize("over,want", [
        (dict(tr=D(5), p=D(100)), "SHOCK"),                                   # SHOCK prima di EXPANSION
        (dict(tr=D(5), adx=D(50)), "SHOCK"),                                  # SHOCK prima di TREND
        (dict(tr=D(5), adx=D(5)), "SHOCK"),                                   # SHOCK prima di RANGE
        (dict(tr=D(5), p=D(100), adx=D(50)), "SHOCK"),
        (dict(p=D(90), adx=D(50)), "EXPANSION"),                              # EXPANSION prima di TREND
        (dict(p=D(90), adx=D(50), pdi=D(1), mdi=D(40)), "EXPANSION"),
        (dict(p=D(90), adx=D(5)), "EXPANSION"),                               # EXPANSION prima di RANGE
    ])
    def test_rule_order(self, monkeypatch, over, want):
        assert one(monkeypatch, **over) == want

    @pytest.mark.parametrize("name", ["a", "p", "pdi", "mdi", "adx"])
    def test_each_none_alone_is_uncertain_even_if_a_later_rule_would_fire(self, monkeypatch, name):
        strong = dict(tr=D(5), a=D(1), p=D(100), pdi=D(40), mdi=D(1), adx=D(80))
        assert one(monkeypatch, **strong) == "SHOCK"                           # controllo: senza None scatta una regola
        assert one(monkeypatch, **{**strong, name: None}) == "UNCERTAIN"
        for alt in (dict(tr=D(1), p=D(10), adx=D(50)), dict(tr=D(1), p=D(10), adx=D(5)), dict(tr=D(1), p=D(90), adx=D(50))):
            assert one(monkeypatch, **{**strong, **alt, name: None}) == "UNCERTAIN"

    def test_none_only_affects_its_own_bar(self, monkeypatch):
        rows = [{**BASE, "adx": D(50)}, {**BASE, "adx": None}, {**BASE, "adx": D(5)}, {**BASE, "tr": D(5)}]
        assert run_stub(monkeypatch, rows) == ("TREND_UP", "UNCERTAIN", "RANGE", "SHOCK")

    def test_no_memory_between_bars(self, monkeypatch):
        rows = [{**BASE, "adx": D(50)}, {**BASE}, {**BASE, "adx": D(50), "pdi": D(5), "mdi": D(40)}, {**BASE}]
        assert run_stub(monkeypatch, rows) == ("TREND_UP", "UNCERTAIN", "TREND_DOWN", "UNCERTAIN")

    def test_thresholds_come_from_params_not_from_constants(self, monkeypatch):
        other = RegimeParams(D(3), D(50), D(60), D(40))
        rows = [{**BASE, "adx": D(30)}]
        assert run_stub(monkeypatch, rows, SP) == ("TREND_UP",)                # ADX 30 >= 30
        assert run_stub(monkeypatch, rows, other) == ("RANGE",)                # ADX 30 <= 40
        rows = [{**BASE, "adx": D(50)}]
        assert run_stub(monkeypatch, rows, SP) == ("TREND_UP",)
        assert run_stub(monkeypatch, rows, other) == ("UNCERTAIN",)            # fra 40 e 60
        assert run_stub(monkeypatch, [{**BASE, "tr": D(2)}], SP) == ("SHOCK",)  # 2 > 1.5
        assert run_stub(monkeypatch, [{**BASE, "tr": D(2)}], other) == ("RANGE",)   # 2 <= 3 e ADX 25 <= 40
        assert run_stub(monkeypatch, [{**BASE, "p": D(60)}], SP) == ("UNCERTAIN",)
        assert run_stub(monkeypatch, [{**BASE, "p": D(60), "adx": D(5)}], other) == ("EXPANSION",)   # 60 >= 50

    def test_input_functions_called_once_with_the_right_arguments(self, monkeypatch):
        calls = []
        for nm in ("true_range", "atr", "atr_percentile", "adx"):
            real = getattr(R, nm)

            def make(nm, real):
                def spy(*args, **kw):
                    calls.append((nm, args[1:], tuple(sorted(kw.items()))))
                    return real(*args, **kw)
                return spy
            monkeypatch.setattr(R, nm, make(nm, real))
        regime_labels(make_bars(random.Random(3), 30, "walk"), 2, 5, 7, SP, candle_ms=CMS)
        assert sorted(calls) == sorted([("true_range", (), (("candle_ms", CMS),)), ("atr", (2,), (("candle_ms", CMS),)),
                                        ("atr_percentile", (2, 5), (("candle_ms", CMS),)), ("adx", (7,), (("candle_ms", CMS),))])


# ============================================================ nessun look-ahead
def prefix_violations(fn, bars):
    full = tuple(fn(bars))
    return [m for m in range(len(bars) + 1) if tuple(fn(bars[:m])) != full[:m]]


class TestNoLookahead:
    def test_truncation_invariance(self):
        for name, bars in DATASETS[::11] + [d for d in DATASETS if d[0] in ("vector", "spiky-70-spike")]:
            for an, w, adn in ((2, 3, 2), (3, 5, 3)):
                for t in (PSETS[0], PSETS[4]):
                    assert prefix_violations(lambda b: regime_labels(b, an, w, adn, params_of(t), candle_ms=CMS), bars) == [], (name, an, w, adn)

    def test_the_check_can_see_real_lookahead(self):
        def next_bar_shock(bars):                              # SHOCK deciso con il true range della barra SUCCESSIVA
            ser = o_series(bars, 2, 3, 2)
            tr, a = ser[0], ser[1]
            return tuple("SHOCK" if (i + 1 < len(bars) and a[i] is not None and tr[i + 1] > F(3, 2) * a[i]) else "-" for i in range(len(bars)))

        def centered_percentile(bars):                         # percentile su finestra centrata
            a = o_series(bars, 2, 3, 2)[1]
            out = []
            for i in range(len(bars)):
                w = [x for x in a[max(0, i - 1):i + 2] if x is not None]
                out.append(100 * F(bisect_right(sorted(w), a[i]), len(w)) if a[i] is not None and w else None)
            return tuple(out)
        bars = dict(DATASETS)["spiky-70-spike"]
        for bad in (next_bar_shock, centered_percentile):
            assert prefix_violations(bad, bars) != [], bad.__name__

    def test_changing_the_future_does_not_change_the_past(self):
        bars = dict(DATASETS)["walk-70"]
        base = regime_labels(bars, 3, 4, 3, params_of(PSETS[0]), candle_ms=CMS)
        for cut in (10, 30, 55):
            tail = [dataclasses.replace(b, high=b.high + 9) for b in bars[cut:]]
            got = regime_labels(list(bars[:cut]) + tail, 3, 4, 3, params_of(PSETS[0]), candle_ms=CMS)
            assert got[:cut] == base[:cut], cut


# ============================================================ validazione
def good_bars(n=12):
    return make_bars(random.Random(5), n, "walk", t0=3)


def expect(code, *a, **k):
    with pytest.raises(ValueError) as e:
        regime_labels(*a, **k)
    assert str(e.value) == code, (str(e.value), code)


def call(bars=None, atr_n=2, pct_window=3, adx_n=2, params=SP, candle_ms=CMS):
    return regime_labels(good_bars() if bars is None else bars, atr_n, pct_window, adx_n, params, candle_ms=candle_ms)


def P(**over):
    base = dict(shock_tr_mult=D("1.5"), expansion_pct_min=D(80), adx_trend_min=D(30), adx_range_max=D(20))
    return RegimeParams(**{**base, **over})


BAD_CMS = [True, False, 0, -1, 60000.0, "60000", None, D(60000), [1]]


class TestValidation:
    def test_control_and_empty_and_one_bar(self):
        assert len(call()) == 12 and call([]) == () and len(call(good_bars(1))) == 1

    @pytest.mark.parametrize("bad", BAD_CMS)
    def test_candle_ms(self, bad):
        expect("invalid_candle_ms", good_bars(), 2, 3, 2, SP, candle_ms=bad)

    @pytest.mark.parametrize("bad", BAD_CMS)
    def test_candle_ms_is_checked_before_everything_else(self, bad):
        expect("invalid_candle_ms", [None], 0, 0, 0, None, candle_ms=bad)

    @pytest.mark.parametrize("which", [0, 1, 2])
    @pytest.mark.parametrize("bad", [True, False, 0, -1, 1.0, 2.5, "3", None, D(3), [3]])
    def test_integer_parameters(self, which, bad):
        args = [2, 3, 2]
        args[which] = bad
        expect("invalid_period", good_bars(), *args, SP, candle_ms=CMS)

    def test_bool_as_valid_number(self):
        for which in range(3):                                  # True == 1 e' numericamente valido: solo il tipo lo rifiuta
            args = [1, 1, 1]
            args[which] = True
            expect("invalid_period", good_bars(), *args, SP, candle_ms=CMS)
        call(atr_n=1, pct_window=1, adx_n=1)

    def test_integer_parameters_in_signature_order(self):
        expect("invalid_period", [None], 0, 0, 0, None, candle_ms=CMS)
        expect("invalid_period", good_bars(), 2, 0, True, SP, candle_ms=CMS)
        for args in ((0, 3, 2), (2, 0, 2), (2, 3, 0)):
            expect("invalid_period", [None], *args, None, candle_ms=CMS)           # periodo prima di params e di bars

    @pytest.mark.parametrize("bad", [None, {"shock_tr_mult": 1}, (D(1), D(50), D(30), D(10)), "x", 1, [D(1)] * 4])
    def test_params_wrong_type(self, bad):
        expect("invalid_threshold", good_bars(), 2, 3, 2, bad, candle_ms=CMS)

    def test_params_subclass_is_refused(self):
        class Sub(RegimeParams):
            pass
        expect("invalid_threshold", good_bars(), 2, 3, 2, Sub(D(1), D(50), D(30), D(10)), candle_ms=CMS)

    @pytest.mark.parametrize("field", ["shock_tr_mult", "expansion_pct_min", "adx_trend_min", "adx_range_max"])
    @pytest.mark.parametrize("bad", [1.5, 2, "1", None, D("NaN"), D("sNaN"), D("Infinity"), D("-Infinity")])
    def test_params_each_field_type_and_finiteness(self, field, bad):
        expect("invalid_threshold", good_bars(), 2, 3, 2, P(**{field: bad}), candle_ms=CMS)

    def test_range_bool_true_is_refused_by_type_even_if_numerically_valid(self):
        expect("invalid_threshold", good_bars(), 2, 3, 2, P(adx_trend_min=D(5), adx_range_max=True), candle_ms=CMS)
        expect("invalid_threshold", good_bars(), 2, 3, 2, P(shock_tr_mult=True), candle_ms=CMS)
        expect("invalid_threshold", good_bars(), 2, 3, 2, P(expansion_pct_min=True), candle_ms=CMS)
        expect("invalid_threshold", good_bars(), 2, 3, 2, P(adx_trend_min=True, adx_range_max=D(0)), candle_ms=CMS)
        expect("invalid_threshold", good_bars(), 2, 3, 2, P(adx_range_max=0), candle_ms=CMS)
        expect("invalid_threshold", good_bars(), 2, 3, 2, P(expansion_pct_min=0), candle_ms=CMS)

    @pytest.mark.parametrize("over", [
        dict(shock_tr_mult=D(0)), dict(shock_tr_mult=D("-0.1")), dict(shock_tr_mult=D("-0")),
        dict(expansion_pct_min=D("-0.0001")), dict(expansion_pct_min=D("100.0001")),
        dict(adx_trend_min=D(0), adx_range_max=D(0)), dict(adx_trend_min=D("-1"), adx_range_max=D("-2")),
        dict(adx_range_max=D("-0.0001")),
        dict(adx_range_max=D(30)), dict(adx_range_max=D(31)), dict(adx_trend_min=D(20)), dict(adx_trend_min=D(19)),
    ])
    def test_params_ranges_and_relation(self, over):
        expect("invalid_threshold", good_bars(), 2, 3, 2, P(**over), candle_ms=CMS)

    @pytest.mark.parametrize("over", [
        dict(expansion_pct_min=D(0)), dict(expansion_pct_min=D(100)), dict(adx_range_max=D(0)), dict(shock_tr_mult=D("0.0001")),
        dict(adx_range_max=D("29.9999")), dict(adx_trend_min=D("20.0001")), dict(shock_tr_mult=D(1000), adx_trend_min=D(100)),
        dict(expansion_pct_min=D("-0")),
    ])
    def test_params_valid_edges_are_accepted(self, over):
        assert len(call(params=P(**over))) == 12

    def test_params_checked_before_bars_and_after_integers(self):
        expect("invalid_threshold", [None], 2, 3, 2, P(adx_range_max=D(30)), candle_ms=CMS)
        expect("invalid_period", good_bars(), 0, 3, 2, P(adx_range_max=D(30)), candle_ms=CMS)

    @pytest.mark.parametrize("bad", [None, "abc", b"abc", 5, {1}, {"a": 1}, (x for x in range(3)), iter([]),
                                     set(good_bars(3)), frozenset(good_bars(3)), dict.fromkeys(good_bars(3))])
    def test_bars_container(self, bad):
        expect("invalid_bars", bad, 2, 3, 2, SP, candle_ms=CMS)

    def test_bar_defects_each_alone_at_three_positions(self):
        base = good_bars()
        cases = {
            "not a Bar": lambda b, p: [None if i == p else x for i, x in enumerate(b)],
            "price float": lambda b, p: _with(b, p, close=100.5),
            "price zero": lambda b, p: _with(b, p, low=D(0)),
            "volume negative": lambda b, p: _with(b, p, volume=D("-1")),
            "low above high": lambda b, p: _with(b, p, low=b[p].high + 1),
            "close above high": lambda b, p: _with(b, p, close=b[p].high + 1),
            "time not aligned": lambda b, p: _with(b, p, open_time_ms=b[p].open_time_ms + 1),
        }
        for make in cases.values():
            for pos in (0, len(base) // 2, len(base) - 1):
                expect("invalid_bars", make(base, pos), 2, 3, 2, SP, candle_ms=CMS)

    def test_gaps_duplicates_ordering(self):
        base = good_bars(10)
        for k in (1, 5, 8):
            expect("invalid_bars", base[:k] + base[k + 1:], 2, 3, 2, SP, candle_ms=CMS)
        for k in (1, 5, 9):
            dup = list(base)
            dup[k] = dataclasses.replace(dup[k], open_time_ms=dup[k - 1].open_time_ms)
            expect("invalid_bars", dup, 2, 3, 2, SP, candle_ms=CMS)
            back = list(base)
            back[k], back[k - 1] = back[k - 1], back[k]
            expect("invalid_bars", back, 2, 3, 2, SP, candle_ms=CMS)


def _with(bars, pos, **over):
    out = list(bars)
    out[pos] = dataclasses.replace(out[pos], **over)
    return out


# ============================================================ scale estreme
BIGCTX = Context(prec=120, Emax=decimal.MAX_EMAX, Emin=decimal.MIN_EMIN)


def rescaled(e):
    with localcontext(BIGCTX):
        return [Bar(b.open_time_ms, b.open.scaleb(e), b.high.scaleb(e), b.low.scaleb(e), b.close.scaleb(e), b.volume)
                for b in hl_bars(VECTOR_HL)]


class TestExtremeScales:
    @pytest.mark.parametrize("e", [-100_000, -300, 300, 100_000])
    def test_supported_range_is_identical(self, e):
        assert regime_labels(rescaled(e), 2, 3, 2, VECTOR_PARAMS, candle_ms=CMS) == VECTOR_LABELS

    @pytest.mark.parametrize("e", [-10**9, -1_000_100, -1_000_020, -999_990, -999_999, -600_000, 600_000, 999_990, 999_999,
                                   1_000_010, 1_000_100, 10**9])
    def test_beyond_range_identical_or_typed(self, e):
        try:
            got = regime_labels(rescaled(e), 2, 3, 2, VECTOR_PARAMS, candle_ms=CMS)
        except ValueError as exc:
            assert str(exc) == "numeric_out_of_range", (e, str(exc))
            assert exc.__cause__ is None and exc.__suppress_context__ is True
            return
        assert got == VECTOR_LABELS, e

    def test_refusal_really_happens_and_is_clean(self):
        refused = 0
        for e in (-10**9, 10**9, 1_000_100, -1_000_100):
            try:
                regime_labels(rescaled(e), 2, 3, 2, VECTOR_PARAMS, candle_ms=CMS)
            except ValueError as exc:
                refused += 1
                assert str(exc) == "numeric_out_of_range"
        assert refused >= 2

    @pytest.mark.parametrize("m", [D("1E+1000005"), D("1E+1500000"), D("1E+999999999")])
    def test_huge_multiplier_is_a_typed_error_not_a_raw_one(self, m):
        with pytest.raises(ValueError) as e:
            regime_labels(hl_bars(VECTOR_HL), 2, 3, 2, RegimeParams(m, D(100), D(60), D(40)), candle_ms=CMS)
        assert str(e.value) == "numeric_out_of_range" and e.value.__cause__ is None and e.value.__suppress_context__ is True

    @pytest.mark.parametrize("m", [D("1E-1000010"), D("1E-999999999")])
    def test_tiny_multiplier_is_correct_or_typed(self, m):
        want = regime_labels(hl_bars(VECTOR_HL), 2, 3, 2, RegimeParams(D("1E-30"), D(100), D(60), D(40)), candle_ms=CMS)
        assert "SHOCK" in want
        try:
            got = regime_labels(hl_bars(VECTOR_HL), 2, 3, 2, RegimeParams(m, D(100), D(60), D(40)), candle_ms=CMS)
        except ValueError as e:
            assert str(e) == "numeric_out_of_range"
        else:
            assert got == want

    def test_ambient_traps_of_the_caller_do_not_matter(self):
        with localcontext() as c:
            c.traps[decimal.Overflow] = False
            c.traps[decimal.Underflow] = False
            c.Emax, c.Emin = decimal.MAX_EMAX, decimal.MIN_EMIN
            for e in (10**9, -10**9):
                try:
                    got = regime_labels(rescaled(e), 2, 3, 2, VECTOR_PARAMS, candle_ms=CMS)
                except ValueError as exc:
                    assert str(exc) == "numeric_out_of_range"
                else:
                    assert got == VECTOR_LABELS


# ============================================================ contesto, forma, immutabilita'
class TestContextShapeImmutability:
    def test_decimal_context_independence(self):
        bars = dict(DATASETS)["spiky-70-spike"]
        base = regime_labels(bars, 3, 5, 3, SP, candle_ms=CMS)
        with localcontext() as c:
            c.prec = 5
            c.rounding = ROUND_UP
            assert regime_labels(bars, 3, 5, 3, SP, candle_ms=CMS) == base
        with localcontext() as c:
            c.prec = 200
            c.traps[decimal.InvalidOperation] = False
            assert regime_labels(bars, 3, 5, 3, SP, candle_ms=CMS) == base
        assert getcontext().prec == 28

    def test_inputs_not_mutated_deterministic_tuple_equals_list(self):
        bars = list(dict(DATASETS)["walk-70"])
        snap = copy.deepcopy(bars)
        params = copy.deepcopy(SP)
        a = regime_labels(bars, 3, 4, 3, SP, candle_ms=CMS)
        assert bars == snap and SP == params and regime_labels(bars, 3, 4, 3, SP, candle_ms=CMS) == a
        assert regime_labels(tuple(bars), 3, 4, 3, SP, candle_ms=CMS) == a

    def test_shapes(self):
        out = call(good_bars(30))
        assert type(out) is tuple and len(out) == 30 and all(type(x) is str and x in REGIME_LABELS for x in out)
        assert REGIME_LABELS == ("TREND_UP", "TREND_DOWN", "RANGE", "EXPANSION", "SHOCK", "UNCERTAIN") and type(REGIME_LABELS) is tuple
        assert [f.name for f in dataclasses.fields(RegimeParams)] == ["shock_tr_mult", "expansion_pct_min", "adx_trend_min", "adx_range_max"]
        assert all(f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING for f in dataclasses.fields(RegimeParams))
        with pytest.raises(dataclasses.FrozenInstanceError):
            SP.shock_tr_mult = D(1)

    def test_signature(self):
        params = inspect.signature(regime_labels).parameters
        assert list(params) == ["bars", "atr_n", "pct_window", "adx_n", "params", "candle_ms"]
        assert params["candle_ms"].kind is inspect.Parameter.KEYWORD_ONLY
        assert all(p.default is inspect.Parameter.empty for p in params.values())
        with pytest.raises(TypeError):
            regime_labels(good_bars(), 2, 3, 2, SP, CMS)


# ============================================================ purezza e prestazioni
class TestPurityAndSpeed:
    src = Path(R.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    def test_imports_and_imported_names(self):
        mods = set()
        names = {}
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Import):
                mods |= {a.name for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                mods.add(n.module or "")
                names[n.module] = {a.name for a in n.names}
        assert mods <= {"__future__", "dataclasses", "decimal", "typing", "backend.v3.features.indicators", "backend.v3.features.levels"}, mods
        assert names["decimal"] <= {"Decimal", "localcontext"}
        assert names["backend.v3.features.indicators"] <= {"Bar", "check_bars", "true_range", "atr", "adx", "_CTX"}
        assert names["backend.v3.features.levels"] <= {"atr_percentile"}

    def test_no_float_clock_random_io_numeric_defaults(self):
        loads = {n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        attrs = {n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute)}
        assert not loads & {"float", "open", "print", "eval", "exec", "compile", "__import__", "input"}
        assert not attrs & {"now", "today", "time", "random", "uniform", "urlopen", "system", "popen", "read_text", "environ"}
        assert [n for n in ast.walk(self.tree) if isinstance(n, ast.Constant) and type(n.value) is float] == []
        for fn in ast.walk(self.tree):
            if isinstance(fn, ast.FunctionDef):
                for d in list(fn.args.defaults) + [x for x in fn.args.kw_defaults if x is not None]:
                    assert not (isinstance(d, ast.Constant) and isinstance(d.value, (int, float)) and not isinstance(d.value, bool)), fn.name

    def test_public_function_uses_the_pinned_context(self):
        fn = next(n for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef) and n.name == "regime_labels")
        assert any(isinstance(n, ast.Name) and n.id == "_CTX" for n in ast.walk(fn))

    def test_linear_time(self):
        small = make_bars(random.Random(2), 15_000, "spiky")
        big = make_bars(random.Random(2), 60_000, "spiky")
        t = time.perf_counter()
        regime_labels(small, 14, 50, 14, VECTOR_PARAMS, candle_ms=CMS)
        t_small = time.perf_counter() - t
        t = time.perf_counter()
        regime_labels(big, 14, 50, 14, VECTOR_PARAMS, candle_ms=CMS)
        t_big = time.perf_counter() - t
        assert t_big < 10.0, t_big
        assert t_big < 9 * max(t_small, 0.05), (t_small, t_big)                    # x4 barre: lineare ~4, quadratico ~16
