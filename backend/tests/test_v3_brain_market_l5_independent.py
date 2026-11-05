"""L5 — verifica indipendente di Claude sul collegamento della vista di mercato.

Perche' esiste: con i parametri ufficiali molti periodi coincidono (atr, rsi e adx valgono tutti 14;
bollinger e donchian valgono 20, come ema_fast) e nei test con valori finti i periodi piccoli
coincidono a loro volta. Un periodo passato all'indicatore sbagliato darebbe lo stesso numero.
Qui ogni scenario usa **dieci periodi tutti diversi** e confronta ogni campo con le funzioni di
``features/*`` chiamate direttamente, con le formule del contratto riscritte in ``Fraction`` e
arrotondate half-even; verifica inoltre che ``min_bars`` sia il numero minimo vero (primo ``n`` per
cui tutti i valori usati sono definiti), un termine alla volta, e il regime unico.
Dati sintetici con seme fisso; nessun dato di mercato reale.
"""
from __future__ import annotations

import json
import random
from decimal import Decimal
from fractions import Fraction

import pytest

from backend.v3.brain_f2.contracts import DecisionKind, MarketContext
from backend.v3.brain_f3.providers import TransportResponse
from backend.v3.brain_market.deepseek_l5 import DeepSeekL5Analyst
from backend.v3.brain_market.params import IndicatorParams, MarketViewParams, TimeframeSpec
from backend.v3.brain_market.view import build_market_view, min_bars, regime_for_context
from backend.v3.brain_view.menu import build_menu, menu_payload
from backend.v3.brain_view.params import ViewParams
from backend.v3.features.indicators import Bar, adx, atr, bollinger, donchian, ema, macd, rsi
from backend.v3.features.levels import atr_percentile
from backend.v3.features.regime import RegimeParams, regime_labels
from backend.v3.knowledge.library import load_library
from backend.v3.outcomes import REGIMES

D = Decimal
TS = (1_800_000_000_000 // 14_400_000) * 14_400_000 + 7 * 60_000      # 7 minuti dopo una chiusura da 4 h
STEPS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
DAY = 86_400_000


# ----------------------------------------------------------------------------------------------
# generatore di dati e parametri (scritti qui, nessun codice condiviso con i test di ChatGPT)

def _series(seed: int, n: int, step: int, ts: int = TS) -> list[Bar]:
    """n barre contigue, chiuse prima di ``ts``; volatilita' a tratti, trend a tratti."""
    rnd = random.Random(seed)
    end = ts - ts % step
    price = D(3000 + rnd.randint(0, 900))
    drift = D(rnd.choice((-3, -1, 0, 1, 3))) / 10
    out = []
    for i in range(n):
        vol = 6 if (i // 25 + seed) % 2 else 45
        if i % 70 == 69:
            drift = -drift
        close = price + drift * 10 + D(rnd.randint(-vol * 10, vol * 10)) / 10
        high = max(price, close) + D(rnd.randint(0, vol * 4)) / 10
        low = min(price, close) - D(rnd.randint(0, vol * 4)) / 10
        out.append(Bar(end - (n - i) * step, price, high, low, close, D(rnd.randint(1, 50))))
        price = close
    return out


def _distinct_params(seed: int, *, pct_lo: int = 2, pct_hi: int = 12) -> MarketViewParams:
    rnd = random.Random(7000 + seed)
    # dieci periodi diversi, e diversi anche dal 9 fisso dell'EMA9 (campo ema9_gap_bp)
    vals = rnd.sample([x for x in range(2, 18) if x != 9], 10)
    ef, es = sorted(vals[0:2])
    mf, ms = sorted(vals[2:4])
    atr_n, rsi_n, sig, bb_n, dn, adx_n = vals[4:10]
    ind = IndicatorParams(ema_fast=ef, ema_slow=es, atr_n=atr_n, rsi_n=rsi_n, macd_fast=mf,
                          macd_slow=ms, macd_signal=sig, bb_n=bb_n,
                          bb_k=D(rnd.choice(("1.5", "1.7", "2.3", "2.6"))),
                          donchian_n=dn, adx_n=adx_n)
    wins = rnd.sample(range(pct_lo, pct_hi + 1), 3)
    specs = tuple(TimeframeSpec(name, STEPS[name], w) for name, w in zip(("15m", "1h", "4h"), wins))
    trend = rnd.randint(18, 28)
    reg = RegimeParams(shock_tr_mult=D(rnd.choice(("2", "2.5", "3"))),
                       expansion_pct_min=D(rnd.randint(60, 90)),
                       adx_trend_min=D(trend), adx_range_max=D(rnd.randint(10, trend - 4)))
    return MarketViewParams("15m", rnd.choice((1, 2, 3)), specs, ind, reg)


def _bars_for(p: MarketViewParams, seed: int, extra: int) -> dict[str, list[Bar]]:
    return {s.name: _series(seed * 10 + j, min_bars(s, p.indicators) + extra, s.candle_ms)
            for j, s in enumerate(p.timeframes)}


# ----------------------------------------------------------------------------------------------
# oracolo: formule del contratto in Fraction, arrotondamento half-even, funzioni di features/*

def _fmt(x: Fraction, places: int) -> str:
    n = round(x * 10 ** places)                       # round() su Fraction: half-even
    sign = "-" if n < 0 else ""
    n = abs(n)
    return f"{sign}{n // 10 ** places}.{n % 10 ** places:0{places}d}"


def _sgn(a, b) -> int:
    a, b = Fraction(a), Fraction(b)
    return (a > b) - (a < b)


def _values(bars, spec, ind):
    """I quindici valori usati sull'ultima barra, chiamando direttamente le funzioni di features/*."""
    step = spec.candle_ms
    closes = [b.close for b in bars]
    m = macd(bars, ind.macd_fast, ind.macd_slow, ind.macd_signal, candle_ms=step)
    bb = bollinger(bars, ind.bb_n, ind.bb_k, candle_ms=step)
    dc = donchian(bars, ind.donchian_n, candle_ms=step)
    ad = adx(bars, ind.adx_n, candle_ms=step)
    return {
        "ef": ema(closes, ind.ema_fast)[-1], "es": ema(closes, ind.ema_slow)[-1],
        "atr": atr(bars, ind.atr_n, candle_ms=step)[-1],
        "pct": atr_percentile(bars, ind.atr_n, spec.pct_window, candle_ms=step)[-1],
        "rsi": rsi(bars, ind.rsi_n, candle_ms=step)[-1],
        "line": m.line[-1], "sig": m.signal[-1], "hist": m.hist[-1],
        "pb": bb.percent_b[-1], "bw": bb.bandwidth[-1],
        "dh": dc.high[-1], "dl": dc.low[-1],
        "pdi": ad.plus_di[-1], "mdi": ad.minus_di[-1], "adx": ad.adx[-1],
    }


def _oracle_vwap(bars):
    """VWAP giornaliero (sessione UTC 00:00) sull'ultima barra, in Fraction; None se non calcolabile.

    Scritto qui dal contratto: prezzo tipico (H+L+C)/3 pesato per il volume, dalle barre della sessione
    dell'ultima barra. Se la prima barra passata cade a meta' sessione e la sessione e' la stessa,
    la sessione e' incompleta: None. Volume totale zero: None."""
    day = bars[-1].open_time_ms // DAY
    session = [b for b in bars if b.open_time_ms // DAY == day]
    if session[0] is bars[0] and bars[0].open_time_ms % DAY != 0:
        return None
    vol = sum(Fraction(b.volume) for b in session)
    if vol == 0:
        return None
    return sum((Fraction(b.high) + Fraction(b.low) + Fraction(b.close)) / 3 * Fraction(b.volume)
               for b in session) / vol


def _expected_extras(bars):
    close = Fraction(bars[-1].close)
    e9 = ema([b.close for b in bars], 9)[-1]
    vw = _oracle_vwap(bars)
    return {
        "ema9_gap_bp": None if e9 is None else _fmt((close - Fraction(e9)) / close * 10_000, 2),
        "vwap_gap_bp": None if vw is None else _fmt((close - vw) / close * 10_000, 2),
    }


def _expected_entry(bars, spec, p):
    v = _values(bars, spec, p.indicators)
    assert all(x is not None for x in v.values())
    close = Fraction(bars[-1].close)
    f = {k: Fraction(x) for k, x in v.items()}
    bp = Fraction(10_000)
    return {
        "tf": spec.name, "status": "ok", "close": str(bars[-1].close),
        "regime": regime_labels(bars, p.indicators.atr_n, spec.pct_window, p.indicators.adx_n,
                                p.regime, candle_ms=spec.candle_ms)[-1],
        "ema_fast_gap_bp": _fmt((close - f["ef"]) / close * bp, 2),
        "ema_slow_gap_bp": _fmt((close - f["es"]) / close * bp, 2),
        "ema_cross": _sgn(f["ef"], f["es"]),
        "atr_bp": _fmt(f["atr"] / close * bp, 2),
        "atr_pct_rank": _fmt(f["pct"], 2),
        "rsi": _fmt(f["rsi"], 2),
        "macd_hist_bp": _fmt(f["hist"] / close * bp, 2),
        "macd_above_signal": _sgn(f["line"], f["sig"]),
        "bb_pct_b": _fmt(f["pb"], 4),
        "bb_bandwidth": _fmt(f["bw"], 4),
        "donchian_pos": "0.5000" if f["dh"] == f["dl"] else _fmt((close - f["dl"]) / (f["dh"] - f["dl"]), 4),
        "adx": _fmt(f["adx"], 2),
        "di_dir": _sgn(f["pdi"], f["mdi"]),
        **_expected_extras(bars),
    }


def _expected_view(bars_by_tf, p):
    entries = [_expected_entry(bars_by_tf[s.name], s, p) for s in p.timeframes]
    base = next(e for e in entries if e["tf"] == p.base_timeframe)
    return {"base_tf": p.base_timeframe, "regime": base["regime"], "timeframes": entries}


# ----------------------------------------------------------------------------------------------
# 1. ogni campo, con periodi tutti diversi

@pytest.mark.parametrize("seed", range(24))
def test_every_field_matches_direct_indicator_calls_with_distinct_periods(seed):
    p = _distinct_params(seed)
    ind = p.indicators
    periods = [ind.ema_fast, ind.ema_slow, ind.atr_n, ind.rsi_n, ind.macd_fast, ind.macd_slow,
               ind.macd_signal, ind.bb_n, ind.donchian_n, ind.adx_n]
    assert len(set(periods)) == 10 and 9 not in periods   # guardia: un periodo scambiato cambia il numero
    bars = _bars_for(p, seed, extra=seed % 7)
    got = build_market_view(bars, timestamp_ms=TS, params=p)
    assert got == _expected_view(bars, p)
    assert json.loads(json.dumps(got)) == got           # serializzabile, nessun float nascosto
    assert regime_for_context(bars, timestamp_ms=TS, params=p) == got["regime"]


def test_scenarios_really_exercise_the_branches():
    """Guardia: gli scenari producono segni di ogni tipo, piu' regimi e valori fuori da [0, 1]."""
    signs = {"ema_cross": set(), "macd_above_signal": set(), "di_dir": set()}
    regimes, pb_out, pos = set(), False, []
    for seed in range(24):
        p = _distinct_params(seed)
        view = build_market_view(_bars_for(p, seed, 0), timestamp_ms=TS, params=p)
        for e in view["timeframes"]:
            regimes.add(e["regime"])
            for k in signs:
                signs[k].add(e[k])
            pb_out |= not (Fraction(e["bb_pct_b"]) <= 1 and Fraction(e["bb_pct_b"]) >= 0)
            pos.append(Fraction(e["donchian_pos"]))
    assert all({-1, 1} <= v for v in signs.values()), signs
    assert len(regimes) >= 3 and regimes <= set(REGIMES), regimes
    assert pb_out
    assert min(pos) >= 0 and max(pos) <= 1


# ----------------------------------------------------------------------------------------------
# 1b. campi opzionali ema9_gap_bp e vwap_gap_bp (schede S25-S27): oracolo Fraction, None, bordi di sessione

def _extras_view(seed, ts, counts):
    """Vista a tre timeframe con ``counts`` barre ciascuno; parametri a periodi tutti diversi."""
    p = _distinct_params(seed)
    bars = {s.name: _series(seed * 10 + j, counts[s.name], s.candle_ms, ts)
            for j, s in enumerate(p.timeframes)}
    return p, bars, build_market_view(bars, timestamp_ms=ts, params=p)


_MIDNIGHT = (TS // DAY) * DAY
_SESSION_INSTANTS = (                       # ultima barra chiusa: a fine sessione, prima barra, a meta'
    _MIDNIGHT + 7 * 60_000, _MIDNIGHT + 900_000 + 7 * 60_000, _MIDNIGHT + 3_600_000 + 7 * 60_000,
    _MIDNIGHT + 4 * 3_600_000 + 7 * 60_000, _MIDNIGHT + 13 * 3_600_000 + 7 * 60_000,
)


@pytest.mark.parametrize("ts", _SESSION_INSTANTS)
@pytest.mark.parametrize("seed", range(6))
def test_extra_fields_match_the_fraction_oracle_across_session_boundaries(seed, ts):
    counts = {"15m": 400, "1h": 130, "4h": 40}          # oltre due giorni su ogni timeframe
    p, bars, view = _extras_view(seed, ts, counts)
    for entry in view["timeframes"]:
        assert entry["status"] == "ok"
        want = _expected_extras(bars[entry["tf"]])
        assert (entry["ema9_gap_bp"], entry["vwap_gap_bp"]) == (want["ema9_gap_bp"], want["vwap_gap_bp"])
        assert entry["vwap_gap_bp"] is not None         # barre dall'inizio di una sessione: sempre definito
    assert view == _expected_view(bars, p)


def test_vwap_is_the_typical_price_of_the_first_bar_right_after_midnight():
    """Prima barra di una sessione: il VWAP e' il suo prezzo tipico; gap = (close - tp) / close."""
    ts = _MIDNIGHT + 900_000 + 7 * 60_000
    p, bars, view = _extras_view(3, ts, {"15m": 400, "1h": 130, "4h": 40})
    b = bars["15m"][-1]
    assert b.open_time_ms == _MIDNIGHT
    tp = (Fraction(b.high) + Fraction(b.low) + Fraction(b.close)) / 3
    entry = next(e for e in view["timeframes"] if e["tf"] == "15m")
    assert entry["vwap_gap_bp"] == _fmt((Fraction(b.close) - tp) / Fraction(b.close) * 10_000, 2)


def test_incomplete_first_session_gives_none_but_keeps_status_and_other_fields():
    """Tutte le barre nella stessa sessione e la prima a meta' giornata: VWAP None, il resto invariato."""
    ts = _MIDNIGHT + 12 * 3_600_000 + 7 * 60_000
    p = _distinct_params(5)
    n = min_bars(p.timeframes[0], p.indicators) + 2
    assert n * 900_000 < 12 * 3_600_000                  # tutte dentro la stessa sessione
    bars = {"15m": _series(51, n, 900_000, ts)}
    view = build_market_view(bars, timestamp_ms=ts, params=p)
    e = next(x for x in view["timeframes"] if x["tf"] == "15m")
    assert e["status"] == "ok" and e["vwap_gap_bp"] is None
    assert e["ema9_gap_bp"] == _expected_extras(bars["15m"])["ema9_gap_bp"]
    assert {k: v for k, v in e.items() if k != "vwap_gap_bp"} == {
        k: v for k, v in _expected_entry(bars["15m"], p.timeframes[0], p).items() if k != "vwap_gap_bp"}


def test_zero_volume_session_gives_none_and_zero_volume_bar_is_weightless():
    ts = _MIDNIGHT + 3 * 3_600_000 + 7 * 60_000
    p, bars, _ = _extras_view(2, ts, {"15m": 400, "1h": 130, "4h": 40})
    series = bars["15m"]
    today = [i for i, b in enumerate(series) if b.open_time_ms // DAY == series[-1].open_time_ms // DAY]
    assert len(today) == 12                              # 00:00 .. 02:45
    zero = [type(b)(b.open_time_ms, b.open, b.high, b.low, b.close, D(0)) for b in series]
    # tutta la sessione corrente senza volume: VWAP non calcolabile, stato invariato
    allz = series[:today[0]] + [zero[i] for i in today]
    e = next(x for x in build_market_view({"15m": allz}, timestamp_ms=ts, params=p)["timeframes"]
             if x["tf"] == "15m")
    assert e["status"] == "ok" and e["vwap_gap_bp"] is None
    # una sola barra senza volume dentro la sessione: non pesa, il resto e' invariato
    one = list(series)
    one[today[1]] = zero[today[1]]
    e = next(x for x in build_market_view({"15m": one}, timestamp_ms=ts, params=p)["timeframes"]
             if x["tf"] == "15m")
    assert e["vwap_gap_bp"] == _expected_extras(one)["vwap_gap_bp"] is not None


def test_ema9_none_below_nine_bars_and_never_changes_status():
    """Periodi piccoli: min_bars = 7 < 9. Con 7 e 8 barre lo stato e' ok ma EMA9 non e' definita."""
    ind = IndicatorParams(ema_fast=2, ema_slow=4, atr_n=3, rsi_n=5, macd_fast=2, macd_slow=5,
                          macd_signal=3, bb_n=6, bb_k=D("2"), donchian_n=7, adx_n=4)
    spec = TimeframeSpec("15m", 900_000, 2)
    p = MarketViewParams("15m", 1, (spec,), ind, _distinct_params(1).regime)
    assert min_bars(spec, ind) == 7
    for n in (7, 8, 9, 10):
        bars = {"15m": _series(14, n, 900_000)}
        e = build_market_view(bars, timestamp_ms=TS, params=p)["timeframes"][0]
        assert e["status"] == "ok"
        assert (e["ema9_gap_bp"] is None) == (n < 9)
        assert e["ema9_gap_bp"] == _expected_extras(bars["15m"])["ema9_gap_bp"]


def test_extra_fields_ignore_the_configured_ema_periods():
    """EMA9 e' fisso a 9: con le stesse barre, cambiare ema_fast/ema_slow non lo sposta (e il VWAP nemmeno)."""
    import dataclasses
    p = _distinct_params(4)
    q = dataclasses.replace(p, indicators=dataclasses.replace(
        p.indicators, ema_fast=p.indicators.ema_fast + 20, ema_slow=p.indicators.ema_slow + 30))
    bars = _bars_for(q, 4, extra=10)                      # abbastanza barre per entrambe le configurazioni
    a = build_market_view(bars, timestamp_ms=TS, params=p)
    b = build_market_view(bars, timestamp_ms=TS, params=q)
    assert [e["status"] for e in a["timeframes"]] == [e["status"] for e in b["timeframes"]] == ["ok"] * 3
    for x, y in zip(a["timeframes"], b["timeframes"]):
        assert (x["ema9_gap_bp"], x["vwap_gap_bp"]) == (y["ema9_gap_bp"], y["vwap_gap_bp"])
        assert x["ema_fast_gap_bp"] != y["ema_fast_gap_bp"]


# ----------------------------------------------------------------------------------------------
# 2. min_bars: il minimo vero, un termine alla volta

def _defined(bars, spec, ind) -> bool:
    return all(x is not None for x in _values(bars, spec, ind).values())


def _first_defined_n(series, spec, ind) -> int:
    for n in range(1, len(series) + 1):
        if _defined(series[:n], spec, ind):
            return n
    raise AssertionError("mai definito")


# periodi piccoli per tutti, tranne un termine che deve dominare (valore massimo unico)
_BASE = dict(ema_fast=2, ema_slow=3, atr_n=2, rsi_n=2, macd_fast=2, macd_slow=3, macd_signal=2,
             bb_n=2, donchian_n=2, adx_n=2)
_DOMINATORS = {
    "ema_slow": dict(ema_slow=41), "rsi_n": dict(rsi_n=41),
    "macd": dict(macd_slow=30, macd_signal=12), "bb_n": dict(bb_n=41),
    "donchian_n": dict(donchian_n=41), "adx_n": dict(adx_n=21),
    "atr_n": dict(atr_n=41),
}


@pytest.mark.parametrize("name", sorted(_DOMINATORS))
def test_min_bars_is_the_true_minimum_when_one_indicator_dominates(name):
    ind = IndicatorParams(bb_k=D("2"), **{**_BASE, **_DOMINATORS[name]})
    spec = TimeframeSpec("15m", STEPS["15m"], 2)
    series = _series(3, 90, spec.candle_ms)
    assert _first_defined_n(series, spec, ind) == min_bars(spec, ind)


def test_min_bars_is_the_true_minimum_when_the_percentile_window_dominates():
    ind = IndicatorParams(bb_k=D("2"), **_BASE)
    spec = TimeframeSpec("15m", STEPS["15m"], 40)
    series = _series(4, 90, spec.candle_ms)
    assert _first_defined_n(series, spec, ind) == min_bars(spec, ind) == 40 + 2 - 1


@pytest.mark.parametrize("seed", range(8))
def test_min_bars_is_the_true_minimum_with_distinct_random_periods(seed):
    p = _distinct_params(seed, pct_lo=2, pct_hi=30)
    for j, spec in enumerate(p.timeframes):
        series = _series(seed * 10 + j, min_bars(spec, p.indicators) + 6, spec.candle_ms)
        assert _first_defined_n(series, spec, p.indicators) == min_bars(spec, p.indicators)


@pytest.mark.parametrize("name", sorted(_DOMINATORS))
def test_view_status_flips_exactly_at_min_bars(name):
    ind = IndicatorParams(bb_k=D("2"), **{**_BASE, **_DOMINATORS[name]})
    spec = TimeframeSpec("15m", STEPS["15m"], 2)
    p = MarketViewParams("15m", 1, (spec,), ind, RegimeParams(D("3"), D("80"), D("25"), D("20")))
    n = min_bars(spec, ind)
    series = _series(5, n + 3, spec.candle_ms)
    for k, want in ((n - 1, "insufficient_history"), (n, "ok"), (n + 1, "ok")):
        got = build_market_view({"15m": series[-k:]}, timestamp_ms=TS, params=p)["timeframes"][0]
        assert got["status"] == want, (k, got)


# ----------------------------------------------------------------------------------------------
# 3. freschezza e barra aperta con numeri scritti a mano

@pytest.mark.parametrize("age", (1, 2, 3))
@pytest.mark.parametrize("tf", ("15m", "1h", "4h"))
def test_freshness_and_open_bar_boundaries(tf, age):
    base = _distinct_params(1)
    p = MarketViewParams(tf, age, (next(s for s in base.timeframes if s.name == tf),),
                         base.indicators, base.regime)
    spec = p.timeframes[0]
    step = spec.candle_ms
    series = _series(11, min_bars(spec, p.indicators) + 2, step)
    end = series[-1].open_time_ms + step                      # istante di chiusura dell'ultima barra

    def status(ts):
        return build_market_view({tf: series}, timestamp_ms=ts, params=p)["timeframes"][0]["status"]

    assert status(end) == "ok"                                # chiusa proprio ora
    assert status(end + age * step - 1) == "ok"               # un millisecondo prima del limite
    assert status(end + age * step) == "stale"                # sul limite: vecchia
    with pytest.raises(ValueError) as exc:
        build_market_view({tf: series}, timestamp_ms=end - 1, params=p)
    assert str(exc.value) == "future_bar"                     # non ancora chiusa: mai tagliata in silenzio
    # con il solo timeframe base vecchio, il regime della vista e' UNKNOWN
    stale_view = build_market_view({tf: series}, timestamp_ms=end + age * step, params=p)
    assert stale_view["regime"] == "UNKNOWN"


def test_base_not_first_and_other_timeframes_stale_or_missing():
    p = _distinct_params(2)
    p = MarketViewParams("1h", 1, p.timeframes, p.indicators, p.regime)
    bars = _bars_for(p, 2, 3)
    view = build_market_view(bars, timestamp_ms=TS, params=p)
    assert view == _expected_view(bars, p)
    assert view["regime"] == view["timeframes"][1]["regime"] == regime_for_context(bars, timestamp_ms=TS, params=p)
    # il base manca: UNKNOWN; gli altri restano calcolati
    no_base = {k: v for k, v in bars.items() if k != "1h"}
    v2 = build_market_view(no_base, timestamp_ms=TS, params=p)
    assert v2["regime"] == "UNKNOWN"
    assert [e["status"] for e in v2["timeframes"]] == ["ok", "missing", "ok"]
    assert v2["timeframes"][0] == view["timeframes"][0] and v2["timeframes"][2] == view["timeframes"][2]


def test_regime_is_unknown_when_base_history_is_short():
    p = _distinct_params(3)
    bars = _bars_for(p, 3, 0)
    bars["15m"] = bars["15m"][1:]                              # una barra in meno del minimo
    view = build_market_view(bars, timestamp_ms=TS, params=p)
    assert view["timeframes"][0]["status"] == "insufficient_history"
    assert view["regime"] == "UNKNOWN" and regime_for_context(bars, timestamp_ms=TS, params=p) == "UNKNOWN"
    assert "UNKNOWN" in REGIMES


# ----------------------------------------------------------------------------------------------
# 4. nessun look-ahead con periodi diversi: la vista a t coincide con la serie completa all'indice k-1

@pytest.mark.parametrize("seed", range(6))
def test_view_at_each_instant_equals_the_full_series_at_that_index(seed):
    p = _distinct_params(seed, pct_hi=8)
    spec = p.timeframes[0]
    step, ind = spec.candle_ms, p.indicators
    need = min_bars(spec, ind)
    full = _series(seed + 40, need + 30, step)                 # chiude prima di TS
    full_regime = regime_labels(full, ind.atr_n, spec.pct_window, ind.adx_n, p.regime, candle_ms=step)
    single = MarketViewParams("15m", 1, (spec,), ind, p.regime)
    for k in range(need, len(full) + 1, 3):
        ts = full[k - 1].open_time_ms + step                   # esattamente alla chiusura della barra k-1
        got = build_market_view({"15m": full[:k]}, timestamp_ms=ts, params=single)["timeframes"][0]
        want = _expected_entry(full[:k], spec, single)
        assert got == want
        assert got["regime"] == full_regime[k - 1]             # indice k-1 della serie COMPLETA
        assert got["rsi"] == _fmt(Fraction(rsi(full, ind.rsi_n, candle_ms=step)[k - 1]), 2)
    # guardia: la vista discrimina (cambiare una barra prima di t la cambia)
    k = need + 10
    ts = full[k - 1].open_time_ms + step
    base_view = build_market_view({"15m": full[:k]}, timestamp_ms=ts, params=single)
    b = full[k - 3]
    changed = list(full[:k])
    changed[k - 3] = Bar(b.open_time_ms, b.open, b.high + 50, b.low, b.close, b.volume)
    assert build_market_view({"15m": changed}, timestamp_ms=ts, params=single) != base_view


# ----------------------------------------------------------------------------------------------
# 5. l'adattatore passa al modello la vista dell'oracolo, non una sua versione

class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, payload):
        self.calls.append(payload)
        content = '{"kind":"OPEN","side":1,"entry_price":"100","stop_price":"99","leverage":2,"confidence":0.5}'
        return TransportResponse(200, {"choices": [{"finish_reason": "stop", "message": {"content": content}}]})


def test_adapter_hands_the_oracle_view_to_the_model():
    p = _distinct_params(5)
    bars = _bars_for(p, 5, 2)
    rec, asked = _Recorder(), []
    view_params = ViewParams(3, 2, D("0.90"), 200, 20261105, 12)
    a = DeepSeekL5Analyst(transport=rec, model="m", outcomes_source=lambda: [],
                          bars_source=lambda s: asked.append(s) or bars, view_params=view_params,
                          market_params=p, menu=build_menu(load_library()),
                          spending_gate=lambda _: True, enabled=True)
    expected = _expected_view(bars, p)
    ctx = MarketContext("BTCUSDT", D("3000"), TS, expected["regime"])
    d = a.analyze(ctx, [])
    assert d.kind == DecisionKind.OPEN and asked == ["BTCUSDT"] and len(rec.calls) == 1
    info = json.loads(rec.calls[0]["messages"][1]["content"])
    assert info["market"] == expected
    assert info["regime"] == info["market"]["regime"] == info["scoreboard"]["regime"] == ctx.regime
    assert info["strategies"] == menu_payload(a.menu)
