"""P10 — verifica indipendente (Claude): adattatore ed etichette riscritti da zero con Fraction, numeri del rapporto
ricalcolati a parte, segmentazione dei buchi, e prove di sistema con la catena VERA (rilevatore -> P5 -> adattatore ->
P4/P6 -> controlli -> verdetto) su mercati sintetici dove la risposta giusta e' nota.

Nessun codice condiviso con i moduli: le barriere si cercano con uno scanner scritto qui, gli arrotondamenti con
`Fraction` (mezzo-pari, come dice il contratto), il verdetto con una funzione scritta dal testo della pre-registrazione.
"""
from __future__ import annotations

import json
import random
from dataclasses import replace
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path

import pytest

from backend.v3.detectors import breakout as B
from backend.v3.detectors import common as C
from backend.v3.features.indicators import Bar
from backend.v3.lab import adapter as A
from backend.v3.lab import controls as K
from backend.v3.lab import evaluate as E
from backend.v3.lab import run as R
from backend.v3.lab import verdict as V
from backend.v3.lab.protocol import load_protocol
from backend.v3.learning.opportunity import Candidate, Candle, label_candidates

MS = 900_000
DAY = 86_400_000
BASE = (1_700_000_000_000 // DAY) * DAY
PREREG = Path(R.__file__).parent / "preregistration.json"


# ----------------------------------------------------------------------------- utilita'

def rnd(x: F, places: int) -> F:
    """Mezzo-pari (Fraction.__round__ arrotonda al pari), esatto."""
    scale = 10 ** places
    return F(round(x * scale), scale)


def fx(d) -> F:
    return F(d)


def make_protocol(**patch):
    raw = json.loads(PREREG.read_text())
    raw["symbols"] = ["BTCUSDT"]
    raw["min_segment_bars"] = 300
    raw["regime"]["pct_window"] = 288
    e = raw["evaluation"]
    e.update(warmup_days=5, train_days=40, test_days=15, step_days=15, embargo_days=1)
    e["wf"].update(min_trades=15, min_days=5, n_boot=200)
    e["whole"].update(min_trades=15, min_days=5, n_boot=500)
    raw["controls"].update(n_shifts=20, min_shift_days=10)
    raw["verdict"].update(min_oos_trades=40, min_folds_with_selection=2)
    for k, v in patch.items():
        raw[k] = v
    return load_protocol(raw)


def bars_from_returns(rets, seed, start_index=0, p0=30000.0, wick=0.0008):
    r = random.Random(seed)
    p, out = p0, []
    for i, ret in enumerate(rets):
        o, c = p, p * (1 + ret)
        h = max(o, c) * (1 + abs(r.gauss(0, wick)))
        l = min(o, c) * (1 - abs(r.gauss(0, wick)))
        out.append(Bar(BASE + (start_index + i) * MS, D(f"{o:.2f}"), D(f"{h:.2f}"), D(f"{l:.2f}"), D(f"{c:.2f}"), D(10)))
        p = c
    return out


def rets_trend(n, seed, drift=0.0015, sd=0.0025):
    r, out, sign, left = random.Random(seed), [], 1, 0
    while len(out) < n:
        if left == 0:
            sign, left = r.choice((1, -1)), r.randint(30, 120)
        out.append(sign * drift + r.gauss(0, sd))
        left -= 1
    return out


def rets_meanrev(n, seed, phi=-0.6, sd=0.0025):
    r, out, prev = random.Random(seed), [], 0.0
    for _ in range(n):
        prev = phi * prev + r.gauss(0, sd)
        out.append(prev)
    return out


def rets_drift(n, seed, mu=0.0004, sd=0.0025):
    r = random.Random(seed)
    return [mu + r.gauss(0, sd) for _ in range(n)]


# ----------------------------------------------------------------------------- scanner indipendente

def scan(by_time, cand, horizon_bars, policy, cost):
    """Etichetta di un candidato, riscritta dal testo del contratto. Restituisce un dict o None se incompleta."""
    start = -(-cand.signal_time_ms // MS) * MS
    window = []
    for k in range(horizon_bars):
        b = by_time.get(start + k * MS)
        if b is None:
            return None
        window.append(b)
    entry, stop, target = fx(cand.entry_price), fx(cand.stop_price), fx(cand.target_price)
    side = cand.side
    barrier, touch, exit_p, amb = "timeout", None, fx(window[-1].close), False
    for b in window:
        lo, hi = fx(b.low), fx(b.high)
        s_hit = lo <= stop if side == 1 else hi >= stop
        t_hit = hi >= target if side == 1 else lo <= target
        if s_hit or t_hit:
            amb = s_hit and t_hit
            pick_stop = s_hit and (policy == "stop_first" or not t_hit)
            barrier = "stop" if pick_stop else "target"
            exit_p = stop if pick_stop else target
            touch = b.open_time_ms
            break
    gross = side * (exit_p - entry) / entry * 10000
    return dict(barrier=barrier, touch=touch, exit=exit_p, amb=amb,
                gross=rnd(gross, 4), net=rnd(gross - F(cost), 4), start=start)


def closed_at(lab, horizon_bars):
    if lab["barrier"] in ("target", "stop"):
        return lab["touch"] + MS
    return lab["start"] + horizon_bars * MS


def dist_bp(c):
    return abs(fx(c.entry_price) - fx(c.stop_price)) / fx(c.entry_price) * 10000


def random_world(seed, n=1500):
    """Barre casuali con code larghe (tocchi ambigui frequenti) e candidati casuali, alcuni vicino alla fine (incompleti)."""
    r = random.Random(seed)
    bars = bars_from_returns([r.gauss(0, 0.003) for _ in range(n)], seed, wick=0.003)
    cands, used = [], set()
    pool = list(range(40, n - 40))
    r.shuffle(pool)
    for i in pool[:140] + list(range(n - 6, n)):               # gli ultimi 6: orizzonte incompleto per costruzione
        side = r.choice((1, -1))
        entry = bars[i].close
        d = entry * D(str(round(r.choice((r.uniform(0.0015, 0.006), r.uniform(0.01, 0.03))), 5)))   # barriere vicine e lontane (scadenze)
        rr = D(str(round(r.uniform(1.0, 3.0), 2)))
        stop, target = entry - side * d, entry + side * rr * d
        t = bars[i].open_time_ms + MS + (1234 if len(cands) % 25 == 7 else 0)      # alcuni segnali NON allineati
        if t in used:
            continue
        used.add(t)
        cands.append(Candidate(f"X:BTCUSDT:{t}:{'L' if side == 1 else 'S'}", "BTCUSDT", side, t, entry, stop, target))
    cands.sort(key=lambda c: c.signal_time_ms)
    return bars, cands


# ----------------------------------------------------------------------------- 1. adattatore

@pytest.mark.parametrize("seed", [5, 17])
@pytest.mark.parametrize("policy", ["stop_first", "target_first"])
@pytest.mark.parametrize("unit,cost", [(D("1000"), D("12")), (D("777.7777"), D("7.31"))])
def test_adapter_rewritten_from_the_contract_matches_field_by_field(seed, policy, unit, cost):
    bars, cands = random_world(seed)
    candles = [Candle(b.open_time_ms, b.open, b.high, b.low, b.close) for b in bars]
    hbars = 16
    labels = label_candidates(cands, {"BTCUSDT": candles}, candle_ms=MS, horizons_ms=[hbars * MS], cost_bp=cost, ambiguous_policy=policy)
    regimes = {c.signal_time_ms - MS: random.Random(c.signal_time_ms).choice(["RANGE", "SHOCK", "TREND_UP"]) for c in cands}
    outs, n_inc = A.outcomes_from_labels(cands, labels, strategy_id="S07", run_id="r-1", horizon_ms=hbars * MS, candle_ms=MS,
                                         cost_bp=cost, unit_notional=unit, regimes=regimes)
    by_time = {b.open_time_ms: b for b in bars}
    expected = [(c, scan(by_time, c, hbars, policy, cost)) for c in cands]
    complete = [(c, lab) for c, lab in expected if lab is not None]
    # guardie: l'esperimento contiene davvero tutti i casi
    kinds = [lab["barrier"] for _, lab in complete]
    assert kinds.count("target") >= 5 and kinds.count("stop") >= 5 and kinds.count("timeout") >= 3
    assert sum(lab["amb"] for _, lab in complete) >= 3
    assert len(expected) - len(complete) >= 3 and n_inc == len(expected) - len(complete)
    assert {c.side for c, _ in complete} == {1, -1}
    assert any(c.signal_time_ms % MS for c, _ in complete)
    assert len(outs) == len(complete)
    for o, (c, lab) in zip(outs, complete):
        closed = closed_at(lab, hbars)
        gross_pnl = rnd(F(unit) * lab["gross"] / 10000, 8)
        fees = rnd(F(unit) * F(cost) / 10000, 8)
        assert (o.schema_version, o.position_id, o.portfolio_id, o.run_id) == (1, c.candidate_id, "lab", "r-1")
        assert (o.symbol, o.side, o.originating_ai, o.leverage) == (c.symbol, c.side, "S07", 1)
        assert (o.opened_at_ms, o.closed_at_ms, o.hold_ms) == (c.signal_time_ms, closed, closed - c.signal_time_ms)
        assert (o.entry_price, F(o.exit_price)) == (c.entry_price, lab["exit"])
        assert F(o.quantity) == rnd(F(unit) / fx(c.entry_price), 8)
        assert (o.notional_entry, o.margin_used) == (unit, unit)
        assert (F(o.gross_bp), F(o.net_bp), o.costs_bp) == (lab["gross"], lab["net"], cost)
        assert (F(o.gross_pnl), F(o.fees), F(o.realized_pnl)) == (gross_pnl, fees, gross_pnl - fees)
        assert F(o.stop_distance_bp) == rnd(dist_bp(c), 4)
        assert F(o.r_multiple) == rnd(lab["net"] / dist_bp(c), 4)
        assert o.exit_reason == ("stop" if lab["barrier"] == "stop" else "brain_close")
        assert o.loss_exceeds_margin is (F(o.realized_pnl) < -F(unit))
        assert (o.decision_event_id, o.link_status) == (c.candidate_id, "linked")
        assert o.decision_regime == regimes[c.signal_time_ms - MS]


def test_adapter_outcomes_are_read_by_p4_and_p6():
    from backend.v3.learning.expectancy import cell_stats
    bars, cands = random_world(5)
    candles = [Candle(b.open_time_ms, b.open, b.high, b.low, b.close) for b in bars]
    labels = label_candidates(cands, {"BTCUSDT": candles}, candle_ms=MS, horizons_ms=[16 * MS], cost_bp=D(12), ambiguous_policy="stop_first")
    outs, _ = A.outcomes_from_labels(cands, labels, strategy_id="S07", run_id="r", horizon_ms=16 * MS, candle_ms=MS, cost_bp=D(12),
                                     unit_notional=D(1000), regimes={c.signal_time_ms - MS: "RANGE" for c in cands})
    cells = cell_stats(outs, min_trades=10, min_days=2, confidence=D("0.9"), n_boot=200, seed=1)
    assert sum(c.n for c in cells) == len(outs)


# ----------------------------------------------------------------------------- 2. numeri del rapporto ricalcolati a parte

def s07_world(seed=11, n=4000):
    bars = bars_from_returns(rets_trend(n, seed, drift=0.0007), seed)
    raw = json.loads(PREREG.read_text())
    raw["symbols"] = ["BTCUSDT"]
    raw["min_segment_bars"] = 300
    raw["risk"].update(stop_atr_mult="0.4", target_r_mult="1")        # barriere strette: molti tocchi, anche ambigui
    raw["evaluation"].update(warmup_days=5)
    raw["evaluation"]["whole"].update(min_trades=15, min_days=5, n_boot=500)
    raw["evaluation"]["wf"].update(min_trades=15, min_days=5, n_boot=200)
    raw["verdict"].update(min_oos_trades=40, min_folds_with_selection=2)
    raw["controls"].update(n_shifts=20, min_shift_days=10)
    p = load_protocol(raw)
    cands = B.detect_donchian_breakout("BTCUSDT", bars, B.DonchianParams(20, None), p.risk, candle_ms=MS)
    candles = [Candle(b.open_time_ms, b.open, b.high, b.low, b.close) for b in bars]
    regimes = {b.open_time_ms: "RANGE" for b in bars}
    return p, bars, cands, candles, regimes


def mean4(values):
    return rnd(sum(values, F(0)) / len(values), 4) if values else None


def test_report_numbers_recomputed_independently():
    p, bars, cands, candles, regimes = s07_world()
    assert len(cands) >= 60
    out = E.evaluate_candidates(p, "S07", "BTCUSDT", cands, candles, regimes, ())
    h = p.labeling.primary_horizon_ms // MS
    by_time = {b.open_time_ms: b for b in bars}
    day_start = -(-bars[0].open_time_ms // DAY) * DAY + p.evaluation.warmup_days * DAY
    cost = F(p.labeling.primary_cost_bp)

    labs = [(c, scan(by_time, c, h, "stop_first", cost)) for c in cands]
    comp = [(c, lab) for c, lab in labs if lab is not None]
    inev = [(c, lab) for c, lab in comp if c.signal_time_ms >= day_start]
    assert len(inev) >= 50 and len(comp) - len(inev) >= 3        # guardia: il filtro del periodo toglie qualcosa

    assert out["counts"] == dict(candidates=len(cands), complete=len(comp), incomplete=len(cands) - len(comp), in_eval=len(inev))
    assert out["whole"]["n"] == len(inev)
    assert F(out["whole"]["mean_net_bp"]) == mean4([lab["net"] for _, lab in inev])
    rs = [rnd(lab["net"] / dist_bp(c), 4) for c, lab in inev]
    assert F(out["whole"]["mean_r"]) == mean4(rs)
    assert sum(v["n"] for v in out["by_side"].values()) == len(inev)

    # drawdown massimo in R: somma cumulata in ordine di chiusura (poi id)
    order = sorted(inev, key=lambda t: (closed_at(t[1], h), t[0].candidate_id))
    peak = tot = dd = F(0)
    for (c, lab) in order:
        tot += rnd(lab["net"] / dist_bp(c), 4)
        peak = max(peak, tot)
        dd = max(dd, peak - tot)
    assert F(out["max_dd_r"]) == rnd(dd, 4) and dd > 0

    # barriere e ambigui su TUTTE le etichette complete (non solo nel periodo)
    assert out["barriers"] == {k: sum(lab["barrier"] == k for _, lab in comp) for k in ("target", "stop", "timeout")}
    n_amb = sum(lab["amb"] for _, lab in comp)
    assert n_amb >= 1 and out["ambiguous"]["n"] == n_amb and F(out["ambiguous"]["share"]) == rnd(F(n_amb, len(comp)), 4)

    # stress di costo e limite con la politica opposta
    for c_str, cell in out["stress"].items():
        lab_c = [scan(by_time, c, h, "stop_first", F(c_str)) for c, _ in inev]
        assert F(cell["mean_net_bp"]) == mean4([x["net"] for x in lab_c])
    lab_b = [scan(by_time, c, h, "target_first", cost) for c, _ in inev]
    assert F(out["bound"]["cell"]["mean_net_bp"]) == mean4([x["net"] for x in lab_b])
    assert out["bound"]["policy"] == "target_first"

    # controllo invertito: speculare scritto qui
    inv = []
    for c, _ in inev:
        e = fx(c.entry_price)
        inv.append(Candidate("INV:" + c.candidate_id, c.symbol, -c.side, c.signal_time_ms, c.entry_price,
                             2 * c.entry_price - c.stop_price, 2 * c.entry_price - c.target_price))
    lab_i = [scan(by_time, c, h, "stop_first", cost) for c in inv]
    assert out["inverted"]["n_skipped"] == 0
    assert F(out["inverted"]["cell"]["mean_net_bp"]) == mean4([x["net"] for x in lab_i])
    assert out["inverted"]["cell"]["n"] == len(inev)

    # scarto d'ingresso: close del segnale contro apertura della barra successiva, positivo = gia' mosso a sfavore
    gaps = [c.side * (fx(by_time[c.signal_time_ms].open) - fx(c.entry_price)) / fx(c.entry_price) * 10000
            for c in cands if c.signal_time_ms >= day_start and c.signal_time_ms in by_time]
    assert out["entry_gap"]["n"] == len(gaps) and F(out["entry_gap"]["mean_adverse_gap_bp"]) == mean4(gaps)

    # nessun controllo a scorrimento passato: rango assente e E4 fallita
    assert out["shift_control"]["n_used"] == 0 and out["shift_control"]["rank_pct"] is None
    assert json.loads(json.dumps(out)) == out


# ----------------------------------------------------------------------------- 3. buchi: l'esecutore spezza, non attraversa

def test_run_lab_splits_at_gaps_and_candidates_match_per_segment_detection():
    p = make_protocol(strategies=json.loads(PREREG.read_text())["strategies"])
    p = replace(p, controls=replace(p.controls, n_shifts=2, min_shift_days=10))
    rets = rets_trend(4200, 3, drift=0.0008)
    all_bars = bars_from_returns(rets, 3)
    # tre segmenti: [0,1700) , [1705, 3300) , [3310, 3410) (corto: scartato) , [3420, 4200)
    cuts = [(1700, 1705), (3300, 3310), (3410, 3420)]
    bars = [b for i, b in enumerate(all_bars) if not any(a <= i < z for a, z in cuts)]
    res = R.run_lab(p, {"BTCUSDT": bars})
    d = res["data"]["BTCUSDT"]
    assert (d["n_bars"], d["n_segments"], d["n_kept_segments"]) == (len(bars), 4, 3)
    assert d["n_missing_bars"] == sum(z - a for a, z in cuts) and d["first_open_ms"] == bars[0].open_time_ms
    kept = [s for s in R.split_contiguous(bars, MS) if len(s) >= p.min_segment_bars]
    assert len(kept) == 3
    dets = {"donchian": B.detect_donchian_breakout}
    from backend.v3.detectors import reversal as RV, trend as TR
    dets.update(bb_macd=RV.detect_bollinger_macd_reversal, ema_cross_adx=TR.detect_ema_cross_adx)
    assert [r["strategy_id"] for r in res["results"]] == ["S07", "S05", "S02"]
    total = 0
    for strat, r in zip(p.strategies, res["results"]):
        want = sum(len(dets[strat.kind]("BTCUSDT", s, strat.params, p.risk, candle_ms=MS)) for s in kept)
        assert r["counts"]["candidates"] == want, strat.id
        total += want
    assert total >= 30 and res["results"][0]["counts"]["candidates"] >= 15      # guardia: ci sono candidati veri
    assert [s["verdict"] for s in res["summary"]] == [r["verdict"] for r in res["results"]]
    assert "verdict" not in res and len(res["summary"]) == 3                      # nessun verdetto aggregato


def test_shifted_sets_keep_cooldown_and_roughly_the_same_number_of_signals():
    p = make_protocol()
    bars = bars_from_returns(rets_drift(5000, 9, mu=0.0, sd=0.003), 9)
    cands = B.detect_donchian_breakout("BTCUSDT", bars, B.DonchianParams(20, None), p.risk, candle_ms=MS)
    sets = K.shifted_candidate_sets("BTCUSDT", [bars], cands, strategy_id="S07", risk=p.risk, candle_ms=MS,
                                    n_shifts=6, min_shift_bars=960, seed=1)
    assert len(sets) == 6 and len(set(sets)) == 6 and len(cands) >= 100
    for s in sets:
        times = [c.signal_time_ms for c in s]
        assert times == sorted(times) and len(set(times)) == len(times)
        assert all(b - a > p.risk.cooldown_bars * MS for a, b in zip(times, times[1:]))
        assert 0.9 * len(cands) <= len(s) <= 1.1 * len(cands)


# ----------------------------------------------------------------------------- 4. catena vera su mercati dove la risposta e' nota

N_DAYS = 150


def run_s07(rets, seed):
    p = make_protocol(strategies=[s for s in json.loads(PREREG.read_text())["strategies"] if s["id"] == "S07"])
    return R.run_lab(p, {"BTCUSDT": bars_from_returns(rets, seed)})["results"][0]


def test_system_trend_market_gives_evidence_and_every_control_agrees():
    r = run_s07(rets_trend(N_DAYS * 96, 101), 101)
    assert r["verdict"] == "EVIDENZA_POSITIVA" and r["failed"] == []
    w = r["whole"]
    assert w["n"] > 1000 and F(w["ci_low"]) > 30                                   # vantaggio vero e grande
    assert F(r["inverted"]["cell"]["mean_net_bp"]) < 0                            # il contrario perde
    assert F(r["shift_control"]["rank_pct"]) == 100 and r["shift_control"]["n_used"] == 20
    assert F(r["stress"]["20"]["mean_net_bp"]) > 0 and F(r["stress"]["0"]["mean_net_bp"]) > F(w["mean_net_bp"])


def test_system_mean_reverting_market_is_negative_for_a_breakout_rule():
    r = run_s07(rets_meanrev(N_DAYS * 96, 101), 101)
    assert r["verdict"] == "NEGATIVO" and r["failed"] == []
    assert F(r["whole"]["ci_high"]) < 0 and F(r["stress"]["0"]["mean_net_bp"]) < 0


@pytest.mark.parametrize("seed", [101, 202])
def test_system_drift_without_information_is_not_called_evidence(seed):
    """Mercato con forte deriva al rialzo, nessuna informazione: l'aspettativa e' positiva (E1 vera) ma la deriva non e' un
    vantaggio del segnale. Il controllo a scorrimento lo vede (E4 fallita) e il verdetto non e' EVIDENZA_POSITIVA."""
    r = run_s07(rets_drift(N_DAYS * 96, seed), seed)
    assert F(r["whole"]["ci_low"]) > 0 and F(r["whole"]["mean_net_bp"]) > 0       # la deriva da sola farebbe sembrare il segnale buono
    assert r["verdict"] == "POSITIVO_INCONCLUDENTE" and "E4" in r["failed"]
    assert F(r["shift_control"]["rank_pct"]) < 95


def test_system_pure_random_walk_is_never_evidence():
    rg = random.Random(7)
    r = run_s07([rg.gauss(0, 0.0025) for _ in range(N_DAYS * 96)], 7)
    assert r["verdict"] in ("NEGATIVO", "NULLO")
    assert F(r["stress"]["0"]["mean_net_bp"]) < 15                                 # senza costi, nessun vantaggio grosso


# ----------------------------------------------------------------------------- 5. verdetto riscritto dal testo della pre-registrazione

def oracle(ws, mean, lo, hi, nf, oos_n, oos, ism, inv, rank, ratio, min_oos, min_f, pct):
    if ws == "insufficient" or mean is None or lo is None or hi is None:
        return "DATI_INSUFFICIENTI", ()
    if hi < 0:
        return "NEGATIVO", ()
    ok = {
        "E1": mean > 0 and lo > 0,
        "E2": nf >= min_f and oos_n >= min_oos and oos is not None and ism is not None and oos > 0 and oos >= ratio * ism,
        "E3": inv is not None and inv < mean and inv <= 0,
        "E4": rank is not None and rank >= pct,
    }
    bad = tuple(k for k in ("E1", "E2", "E3", "E4") if not ok[k])
    if not bad:
        return "EVIDENZA_POSITIVA", ()
    if mean > 0:
        return "POSITIVO_INCONCLUDENTE", bad
    return "NULLO", ()


def test_classify_matches_an_independent_reading_of_the_rule_on_20000_boundary_heavy_cases():
    rg = random.Random(2026)
    pick = lambda *xs: rg.choice(xs)
    D_ = D
    seen = set()
    for _ in range(20000):
        ws = pick("insufficient", "positive", "negative", "inconclusive")
        mean = pick(None, D_("-5"), D_("0"), D_("3"), D_("40"))
        lo = pick(None, D_("-2"), D_("0"), D_("1"))
        hi = pick(None, D_("-1"), D_("0"), D_("9"))
        nf, oos_n = pick(0, 2, 3, 4), pick(0, 99, 100, 101)
        oos, ism = pick(None, D_("-1"), D_("0"), D_("10"), D_("19"), D_("20"), D_("21")), pick(None, D_("0"), D_("20"), D_("40"))
        inv = pick(None, D_("-30"), D_("0"), D_("3"), D_("40"), D_("45"))
        rank = pick(None, D_("94.9999"), D_("95"), D_("100"), D_("0"))
        kw = dict(oos_over_train_min=D_("0.5"), min_oos_trades=100, min_folds_with_selection=3, control_percentile_min=D_("95"))
        got = V.classify(whole_status=ws, mean_net_bp=mean, ci_low=lo, ci_high=hi, n_folds_with_selection=nf, oos_n=oos_n,
                         oos_mean_net_bp=oos, is_mean_net_bp=ism, inverted_mean_net_bp=inv, shift_rank_pct=rank, **kw)
        want = oracle(ws, mean, lo, hi, nf, oos_n, oos, ism, inv, rank, D_("0.5"), 100, 3, D_("95"))
        assert got == want, (ws, mean, lo, hi, nf, oos_n, oos, ism, inv, rank)
        seen.add(got)
    kinds = {v for v, _ in seen}
    assert kinds == {"DATI_INSUFFICIENTI", "NEGATIVO", "EVIDENZA_POSITIVA", "POSITIVO_INCONCLUDENTE", "NULLO"}   # guardia: tutti i rami sono coperti
    assert any(v == "POSITIVO_INCONCLUDENTE" and len(f) >= 3 for v, f in seen)
