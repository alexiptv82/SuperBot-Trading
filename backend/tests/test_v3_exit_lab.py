"""Laboratorio delle uscite (ops/brain-unico/exits): bracci controfattuali e valutazione pre-registrata.
Il riferimento coincide con il runtime; nessuno sguardo avanti; costi uguali per tutti; regole statistiche fisse."""
from __future__ import annotations

import importlib.util
import json
import random
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from backend.v3.features.indicators import Bar as RBar
from backend.v3.runner.exits import ExitPolicy, evaluate_exit

ROOT = Path(__file__).resolve().parents[2] / "ops" / "brain-unico" / "exits"


def _load(name):
    spec = importlib.util.spec_from_file_location("exitlab_" + name, ROOT / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod                        # richiesto da @dataclass
    spec.loader.exec_module(mod)
    return mod


A = _load("arms")
E = _load("evaluate")
SPEC = json.loads((ROOT / "preregistration.json").read_text())
T0 = 1_763_000_000_000 - 1_763_000_000_000 % 3_600_000      # inizio d'ora UTC
M = 60_000
NOCOST = A.Costs(fee_bp=0, stop_slippage_bp=0, market_slippage_bp=0)
BASE = A.Arm("A0", "baseline", tp_r=2.0)


def bars_from(prices, start=T0):
    """Candele 1m da una lista di (open, high, low, close)."""
    return [A.Bar(start + i * M, *p) for i, p in enumerate(prices)]


def test_the_baseline_reproduces_the_runtime_exit_rule():
    rng = random.Random(7)
    pol = ExitPolicy(Decimal("2"), 24 * 3_600_000, Decimal("2"))
    costs = A.Costs(fee_bp=0, stop_slippage_bp=2, market_slippage_bp=0)
    checked = 0
    for k in range(300):
        side = rng.choice((1, -1))
        px, rows = 100.0, []
        for i in range(1500):
            o = px
            c = max(1.0, o * (1 + rng.gauss(0, 0.002)))
            h, lo = max(o, c) * (1 + abs(rng.gauss(0, 0.001))), min(o, c) * (1 - abs(rng.gauss(0, 0.001)))
            rows.append((round(o, 6), round(h, 6), round(lo, 6), round(c, 6)))
            px = c
        bars = bars_from(rows)
        stop = 100.0 * (1 - side * 0.01)
        pos = A.Position(side, 100.0, stop, T0)
        mine = A.simulate(pos, bars, BASE, costs)
        ref = evaluate_exit(side=side, fill_price=Decimal("100"), stop_price=Decimal(str(stop)), opened_at_ms=T0,
                            bars=[RBar(b.open_time_ms, Decimal(str(b.open)), Decimal(str(b.high)), Decimal(str(b.low)),
                                       Decimal(str(b.close)), Decimal("1")) for b in bars],
                            candle_ms=M, policy=pol)
        if ref is None:
            assert mine.reason == "open"
            continue
        assert mine.reason == ref.reason and mine.exit_ms == ref.bar_open_time_ms, k
        assert abs(mine.exit_price - float(ref.price)) < 1e-6, k
        checked += 1
    assert checked > 250


def test_trailing_never_uses_the_current_candle_to_move_its_own_stop():
    # long 100, stop 99 (R=1). Candela 1: massimo 101.5 (attiva il trailing a 1R) e minimo 99.5: con lo sguardo
    # avanti il nuovo stop (100.5) sarebbe toccato nella stessa candela; correttamente vale dalla successiva.
    arm = A.Arm("TR", "trailing", tp_r=None, trail_at_r=1.0, trail_dist_r=1.0)
    bars = bars_from([(100, 101.5, 99.5, 101), (101, 101.2, 100.4, 100.6)])
    out = A.simulate(A.Position(1, 100.0, 99.0, T0), bars, arm, NOCOST)
    assert (out.reason, out.exit_ms) == ("stop", T0 + M)
    assert out.exit_price == pytest.approx(100.5) and out.net_r == pytest.approx(0.5)


def test_break_even_moves_the_stop_to_entry_plus_costs_after_the_activation():
    arm = A.Arm("BE", "break_even", tp_r=2.0, be_at_r=1.0)
    costs = A.Costs(fee_bp=6, stop_slippage_bp=2, market_slippage_bp=2)
    bars = bars_from([(100, 101.1, 99.9, 101), (101, 101, 99.95, 100)])
    out = A.simulate(A.Position(1, 100.0, 99.0, T0), bars, arm, costs)
    assert out.reason == "stop"
    assert out.exit_price == pytest.approx(100.14 * (1 - 2e-4))      # ingresso + 14 bp, meno la slippage
    assert -0.02 < out.net_r < 0.01                                   # circa pari, costi inclusi
    base = A.simulate(A.Position(1, 100.0, 99.0, T0), bars, BASE, costs)
    assert base.reason == "open"                                      # il riferimento resta aperto


def test_profit_protection_locks_a_fraction_of_the_favourable_excursion():
    arm = A.Arm("PR", "protect", tp_r=2.0, protect_at_r=1.0, protect_frac=0.5)
    bars = bars_from([(100, 101.6, 100, 101.5), (101.5, 101.5, 100.7, 100.75)])
    out = A.simulate(A.Position(1, 100.0, 99.0, T0), bars, arm, NOCOST)
    assert out.reason == "stop" and out.exit_price == pytest.approx(100.8) and out.mfe_r == pytest.approx(1.6)


def test_reversal_needs_known_history_and_fires_only_at_an_hour_close():
    arm = A.Arm("INV", "reversal", tp_r=2.0, reversal_ema=3)
    rows = [(100, 100.2, 99.9, 100.1)] * 59 + [(100.1, 100.1, 99.5, 99.6)]      # chiude l'ora a 99.6
    out = A.simulate(A.Position(1, 100.0, 98.0, T0), bars_from(rows), arm, NOCOST)
    assert out.reason == "open"                                                   # senza storia: niente
    out = A.simulate(A.Position(1, 100.0, 98.0, T0), bars_from(rows), arm, NOCOST, prior_hour_closes=[100, 100.2, 100.4])
    assert (out.reason, out.exit_ms, out.exit_price) == ("reversal", T0 + 59 * M, pytest.approx(99.6))


def test_funding_is_charged_at_each_crossed_deadline_and_the_long_pays():
    start = T0 - T0 % (8 * 3_600_000) + 8 * 3_600_000 - 2 * M                    # 2 minuti prima di una scadenza
    rows = [(100, 100.1, 99.9, 100)] * 10
    arm = A.Arm("X", "baseline", tp_r=2.0, max_hold_ms=10 * M)
    costs = A.Costs(fee_bp=0, stop_slippage_bp=0, market_slippage_bp=0, funding=lambda ts: 0.0001)
    lng = A.simulate(A.Position(1, 100.0, 99.0, start), bars_from(rows, start), arm, costs)
    sht = A.simulate(A.Position(-1, 100.0, 101.0, start), bars_from(rows, start), arm, costs)
    assert lng.funding_r == pytest.approx(0.01) and sht.funding_r == pytest.approx(-0.01)
    assert lng.net_r == pytest.approx(-0.01) and sht.net_r == pytest.approx(0.01)


def test_costs_are_identical_for_every_arm():
    costs = A.Costs(fee_bp=6, stop_slippage_bp=2, market_slippage_bp=2)
    bars = bars_from([(100, 102.5, 99.95, 102)])
    for arm in A.arms_from_spec(SPEC):
        out = A.simulate(A.Position(1, 100.0, 99.0, T0), bars, arm, costs)
        if arm.tp_r == 2.0:
            assert out.reason == "take_profit"
            assert out.net_r == pytest.approx(2.0 - 6e-4 * (100 + 102))           # stessa formula per tutti


def test_the_preregistration_is_complete_and_fixed():
    arms = A.arms_from_spec(SPEC)
    assert len(arms) == 9 and sum(a.family == "baseline" for a in arms) == 1
    assert {a.family for a in arms} == {"baseline", "break_even", "trailing", "protect", "reversal"}
    r = SPEC["rules"]
    assert (r["calibration_fraction"], r["embargo_days"], r["min_test_trades"], r["min_test_days"]) == (0.6, 1, 100, 20)
    assert "Falco e Toro (non certificati semanticamente)" in SPEC["data"]["excluded"]
    with pytest.raises(ValueError):
        A.arms_from_spec({"arms": [a for a in SPEC["arms"] if a["family"] != "baseline"]})


def _trades(n_days, per_day, effect, calib_effect=None, seed=1):
    rng = random.Random(seed)
    out = []
    names = [a["name"] for a in SPEC["arms"]]
    for d in range(n_days):
        day = "2026-%02d-%02d" % (1 + d // 28, 1 + d % 28)
        for i in range(per_day):
            base = rng.gauss(0, 1)
            eff = calib_effect if (calib_effect is not None and d < int(n_days * 0.6)) else effect
            res = {n: base + rng.gauss(0, 0.05) for n in names}
            res["TR_100_075"] = base + eff + rng.gauss(0, 0.05)
            out.append({"id": "%d-%d" % (d, i), "day": day, "attested": True, "results": res})
    return out


def test_unattested_trades_are_refused():
    t = _trades(5, 2, 0.0)
    t[0]["attested"] = False
    with pytest.raises(ValueError, match="unattested_trades"):
        E.evaluate(t, SPEC)


def test_a_small_sample_is_never_declared_superior():
    res = E.evaluate(_trades(10, 3, 0.5), SPEC)
    assert res["families"]["trailing"]["verdict"] == "campione_insufficiente"


def test_a_real_out_of_sample_effect_is_found_and_only_then():
    res = E.evaluate(_trades(60, 6, 0.4), SPEC)
    tr = res["families"]["trailing"]
    assert tr["arm"] == "TR_100_075" and tr["verdict"] == "superiore_nello_scenario" and tr["ci_low"] > 0
    assert res["families"]["break_even"]["verdict"] == "non_dimostrato"


def test_an_effect_seen_only_in_calibration_does_not_pass_the_test_window():
    res = E.evaluate(_trades(60, 6, effect=-0.3, calib_effect=0.6), SPEC)
    tr = res["families"]["trailing"]
    assert tr["arm"] == "TR_100_075"                     # scelto sulla calibrazione...
    assert tr["verdict"] == "non_dimostrato"            # ...ma il test fuori campione lo smentisce


def test_the_embargo_separates_calibration_and_test_days():
    days = ["d%02d" % i for i in range(10)]
    cal, test = E.split_days(days, 0.6, 1)
    assert cal == set(days[:6]) and test == set(days[7:]) and not cal & test


def test_superiority_must_hold_in_every_funding_scenario():
    good = E.evaluate(_trades(60, 6, 0.4), SPEC)
    bad = E.evaluate(_trades(60, 6, 0.0, seed=2), SPEC)
    assert E.combine_scenarios([good, good])["trailing"] == "superiore_proposta_al_proprietario"
    assert E.combine_scenarios([good, bad])["trailing"] == "non_dimostrato"
    assert E.holm_alphas(4, 0.05) == pytest.approx([0.0125, 0.05 / 3, 0.025, 0.05])


def test_stop_and_target_in_the_same_candle_the_stop_wins_as_in_the_runtime():
    bars = bars_from([(100, 102.5, 98.5, 101)])                       # tocca 102 (2R) e 99 (stop) insieme
    out = A.simulate(A.Position(1, 100.0, 99.0, T0), bars, BASE, NOCOST)
    ref = evaluate_exit(side=1, fill_price=Decimal("100"), stop_price=Decimal("99"), opened_at_ms=T0,
                        bars=[RBar(T0, Decimal("100"), Decimal("102.5"), Decimal("98.5"), Decimal("101"), Decimal("1"))],
                        candle_ms=M, policy=ExitPolicy(Decimal("2"), 24 * 3_600_000, Decimal("0")))
    assert out.reason == ref.reason == "stop" and out.net_r == pytest.approx(-1.0)
