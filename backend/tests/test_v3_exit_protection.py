"""Protezione dei profitti nel runtime delle uscite (break-even, trailing, protezione di quota).

Le regole sono quelle dei bracci PRE-REGISTRATI del laboratorio ``ops/brain-unico/exits/arms.py``: il primo test
dimostra che il runtime produce le stesse uscite del laboratorio, cosi' i risultati del laboratorio valgono anche
per il runtime. Gli altri fissano le garanzie: niente spostamenti anticipati, nessuno sguardo avanti nella candela,
stop che non torna mai indietro, break-even che copre i costi, ripresa identica dopo un buco del feed, e la
politica di oggi (schema 1, Brain RC1) che resta esattamente com'era.
"""
from __future__ import annotations

import importlib.util
import json
import random
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.v3.features.indicators import Bar
from backend.v3.runner.exits import (
    ExitPolicy, default_policy_path, evaluate_exit, favorable_extreme, load_default_policy, load_exit_policy,
    protected_stop,
)

ROOT = Path(__file__).resolve().parents[2] / "ops" / "brain-unico" / "exits"
_spec = importlib.util.spec_from_file_location("exitlab_arms_protection", ROOT / "arms.py")
A = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = A
_spec.loader.exec_module(A)

T0 = 1_763_000_000_000 - 1_763_000_000_000 % 3_600_000
M = 60_000
H24 = 24 * 3_600_000
FEE = D("6")


def rbars(rows, start=T0):
    return [Bar(start + i * M, D(str(o)), D(str(h)), D(str(l)), D(str(c)), D("1")) for i, (o, h, l, c) in enumerate(rows)]


def policy(tp="2", **kw):
    return ExitPolicy(D(tp), H24, D("2"), **{k: (None if v is None else D(v)) for k, v in kw.items()})


def walk(rng, n=1500, vol=0.002):
    px, rows = 100.0, []
    for _ in range(n):
        o = px
        c = max(1.0, o * (1 + rng.gauss(0, vol)))
        h, lo = max(o, c) * (1 + abs(rng.gauss(0, vol / 2))), min(o, c) * (1 - abs(rng.gauss(0, vol / 2)))
        rows.append((round(o, 6), round(h, 6), round(lo, 6), round(c, 6)))
        px = c
    return rows


LAB_ARMS = {a["name"]: a for a in json.loads((ROOT / "preregistration.json").read_text())["arms"]}
PROTECTION_ARMS = ["BE_075", "BE_100", "TR_100_075", "TR_100_100", "PR_100_033", "PR_100_050"]


@pytest.mark.parametrize("name", PROTECTION_ARMS)
def test_runtime_reproduces_the_preregistered_lab_arm(name):
    spec = LAB_ARMS[name]
    arm = A.arms_from_spec({"arms": [{"name": "A0", "family": "baseline", "tp_r": 2.0}, spec]})[1]
    pol = policy(str(spec["tp_r"]), be_at_r=_s(spec.get("be_at_r")), trail_at_r=_s(spec.get("trail_at_r")),
                 trail_dist_r=_s(spec.get("trail_dist_r")), protect_at_r=_s(spec.get("protect_at_r")),
                 protect_frac=_s(spec.get("protect_frac")))
    costs = A.Costs(fee_bp=6, stop_slippage_bp=2, market_slippage_bp=0)   # il runtime esce a timeout senza slippage
    rng = random.Random(sum(map(ord, name)))
    moved = 0
    for _ in range(120):
        side = rng.choice((1, -1))
        rows = walk(rng)
        stop = 100.0 * (1 - side * 0.006)
        lab = A.simulate(A.Position(side, 100.0, stop, T0), A_bars(rows), arm, costs)
        got = evaluate_exit(side=side, fill_price=D("100"), stop_price=D(str(stop)), opened_at_ms=T0, bars=rbars(rows),
                            candle_ms=M, policy=pol, fee_bps=FEE)
        if lab.reason == "open":
            assert got is None
            continue
        assert got is not None and got.reason == lab.reason and got.bar_open_time_ms == lab.exit_ms
        assert float(got.price) == pytest.approx(lab.exit_price, rel=1e-9)
        moved += got.reason == "stop" and got.stop_kind != "initial"
    assert moved > 0                                    # la protezione e' stata davvero esercitata


def _s(v):
    return None if v is None else str(v)


def A_bars(rows):
    return [A.Bar(T0 + i * M, *r) for i, r in enumerate(rows)]


def test_schema_1_policy_and_the_installed_file_are_unchanged():
    pol = load_default_policy()
    assert json.loads(default_policy_path().read_text())["schema_version"] == 1 and not pol.protects
    rng = random.Random(3)
    for _ in range(60):
        side = rng.choice((1, -1))
        rows = walk(rng, 600)
        stop = D(str(100.0 * (1 - side * 0.006)))
        kw = dict(side=side, fill_price=D("100"), stop_price=stop, opened_at_ms=T0, bars=rbars(rows), candle_ms=M,
                  policy=pol)
        plain = evaluate_exit(**kw)
        assert evaluate_exit(**kw, fee_bps=FEE, best_before=D("150" if side == 1 else "50")) == plain
        assert plain is None or plain.stop_kind == "initial"


def test_break_even_waits_for_the_trigger_and_never_looks_inside_the_candle():
    pol = policy(be_at_r="1")
    # long da 100, stop 99 (R=1). La candela 1 tocca 100,9 (0,9 R): lo stop NON si muove.
    # La candela 2 tocca 101 (1 R) e nella STESSA candela scende a 99,5: lo stop vale ancora 99 -> nessuna uscita.
    rows = [(100, 100.9, 99.6, 100.5), (100.5, 101.0, 99.5, 100.2), (100.2, 100.3, 100.0, 100.1)]
    assert evaluate_exit(side=1, fill_price=D("100"), stop_price=D("99"), opened_at_ms=T0, bars=rbars(rows[:2]),
                         candle_ms=M, policy=pol, fee_bps=FEE) is None
    # dalla candela 3 lo stop e' al break-even: 100 * (1 + (2*6 + 2) / 10000) = 100,14 -> uscita
    out = evaluate_exit(side=1, fill_price=D("100"), stop_price=D("99"), opened_at_ms=T0, bars=rbars(rows),
                        candle_ms=M, policy=pol, fee_bps=FEE)
    assert out.reason == "stop" and out.stop_kind == "break_even" and out.bar_open_time_ms == T0 + 2 * M
    # uscita = break-even meno lo slippage dello stop: commissioni d'ingresso e d'uscita coperte
    exit_px = out.price
    fees = (D("100") + exit_px) * FEE / D(10000)
    assert exit_px - D("100") - fees >= D("-0.0001")


def test_the_stop_only_moves_towards_profit():
    pol = policy(tp="20", be_at_r="1", trail_at_r="1.5", trail_dist_r="1", protect_at_r="1", protect_frac="0.5")
    rng = random.Random(11)
    for _ in range(40):
        side = rng.choice((1, -1))
        fill, stop = D("100"), D("100") - side * D("0.6")
        best, last = fill, stop
        for o, h, l, c in walk(rng, 400):
            best = max(best, D(str(h))) if side == 1 else min(best, D(str(l)))
            now, _ = protected_stop(side, fill, stop, best, pol, FEE)
            assert side * (now - last) >= 0 and side * (now - stop) >= 0
            last = now


def test_a_feed_gap_does_not_reset_the_protection():
    pol = policy(tp="20", trail_at_r="1", trail_dist_r="1")
    rng = random.Random(5)
    checked = armed = 0
    for _ in range(200):
        side = rng.choice((1, -1))
        rows = walk(rng, 900, 0.0003)
        bars = rbars(rows)
        stop = D("100") - side * D("0.3")
        kw = dict(side=side, fill_price=D("100"), stop_price=stop, opened_at_ms=T0, candle_ms=M,
                  policy=pol, fee_bps=FEE)
        whole = evaluate_exit(bars=bars, **kw)
        cut = 30
        first = evaluate_exit(bars=bars[:cut], **kw)
        if first is not None:
            continue
        best = favorable_extreme(side, None, bars[:cut], T0)
        resumed = evaluate_exit(bars=bars[cut:], best_before=best, **kw)
        assert resumed == whole
        checked += 1
        armed += protected_stop(side, D("100"), stop, best, pol, FEE)[1] != "initial"   # trailing gia' attivo al buco
    assert checked > 10 and armed > 3


def test_short_trailing_mirrors_the_long():
    pol = policy(tp="20", trail_at_r="1", trail_dist_r="1")
    rows = [(100, 100.2, 98.0, 98.2), (98.2, 98.4, 97.5, 97.6), (97.6, 98.6, 97.6, 98.5)]
    # short da 100, stop 101 (R=1). Minimo 97,5 -> trailing a 98,5; la candela 3 tocca 98,6 -> uscita
    out = evaluate_exit(side=-1, fill_price=D("100"), stop_price=D("101"), opened_at_ms=T0, bars=rbars(rows),
                        candle_ms=M, policy=pol, fee_bps=FEE)
    assert out.reason == "stop" and out.stop_kind == "trailing" and out.bar_open_time_ms == T0 + 2 * M
    assert out.price == (D("98.5") * (1 + D("2") / D(10000))).quantize(D("0.00000001"))


def test_policy_file_schema_2_and_invalid_combinations():
    base = {"schema_version": 2, "take_profit_r": "3", "max_hold_hours": 24, "stop_slippage_bp": "2",
            "be_at_r": "1", "trail_at_r": "1.5", "trail_dist_r": "1", "protect_at_r": None, "protect_frac": None}
    pol = load_exit_policy(json.dumps(base).encode())
    assert pol.protects and pol.be_at_r == D("1") and pol.protect_at_r is None
    off = dict(base, be_at_r=None, trail_at_r=None, trail_dist_r=None)
    assert not load_exit_policy(json.dumps(off).encode()).protects
    for bad in (dict(base, trail_dist_r=None),                       # trailing a meta'
                dict(base, protect_at_r="1"),                        # protezione senza quota
                dict(base, protect_at_r="1", protect_frac="1"),      # quota fuori (0, 1)
                dict(base, be_at_r="0"),
                dict(base, be_at_r=1.0),                             # numero non stringa
                {k: v for k, v in base.items() if k != "be_at_r"},  # chiave mancante
                dict(base, schema_version=3)):
        with pytest.raises(ValueError, match="invalid_policy"):
            load_exit_policy(json.dumps(bad).encode())
    v1_with_extra = {"schema_version": 1, "take_profit_r": "2", "max_hold_hours": 24, "stop_slippage_bp": "2",
                     "be_at_r": "1"}
    with pytest.raises(ValueError, match="invalid_policy"):
        load_exit_policy(json.dumps(v1_with_extra).encode())


def test_break_even_without_fees_fails_closed():
    pol = policy(be_at_r="1")
    rows = [(100, 101.5, 100, 101), (101, 101.2, 100.9, 101)]
    with pytest.raises(ValueError, match="invalid_fee"):
        evaluate_exit(side=1, fill_price=D("100"), stop_price=D("99"), opened_at_ms=T0, bars=rbars(rows), candle_ms=M,
                      policy=pol)


def test_monitor_carries_the_protection_across_a_feed_gap_and_reports_it(tmp_path):
    from backend.tests.test_v3_exit_service import NOW, RUN, _close_events, _journal, _open
    from backend.v3.runner.monitor import run_exit_monitor
    j = _journal(tmp_path)
    t0 = NOW - 120_000
    pid = _open(j, now=t0, entry="100", stop="98")                       # long, R circa 2
    bars = [Bar(t0, D("100"), D("104"), D("99.9"), D("103.9"), D("1")),     # +2 R: trailing a 0,5 R dal massimo
            Bar(t0 + 2 * M, D("103"), D("103.2"), D("102.5"), D("102.6"), D("1"))]   # minuto t0+M mancante
    pol = policy(tp="20", trail_at_r="1", trail_dist_r="0.5")
    rep = run_exit_monitor(journal=j, portfolio_id="brain", run_id=RUN, fetch_bars=lambda s, a, b: bars,
                           policy=pol, fee_bps=6, now_ms=NOW + 300_000)
    assert rep.closed == ((pid, "stop"),) and rep.protected == ((pid, "trailing"),) and rep.errors == ()
    assert len(_close_events(j)) == 1
    # politica di oggi (schema 1): stesso feed, esce come sempre a take-profit 2R, nessuno stop spostato
    other = tmp_path / "b"
    other.mkdir()
    j2 = _journal(other)
    pid2 = _open(j2, now=t0, entry="100", stop="98")
    rep2 = run_exit_monitor(journal=j2, portfolio_id="brain", run_id=RUN, fetch_bars=lambda s, a, b: bars,
                            policy=load_default_policy(), fee_bps=6, now_ms=NOW + 300_000)
    assert rep2.closed == ((pid2, "take_profit"),) and rep2.protected == ()


def test_net_target_proposal_is_explicit_and_not_applied():
    from backend.v3.runner.exits import gross_r_for_net_target
    d, c = D("0.005"), D("0.0016")
    k = gross_r_for_net_target(d, c, D("3"))
    assert k.quantize(D("0.01")) == D("4.28")
    assert ((D("3") * d - c) / (d + c)).quantize(D("0.01")) == D("2.03")      # 3R lordi = circa 2R netti
    assert gross_r_for_net_target(d, D("0"), D("3")) == D("3")               # senza costi lordo = netto
    for bad in ((D("0"), c, D("3")), (d, c, D("0")), (d, D("-1"), D("3"))):
        with pytest.raises(ValueError):
            gross_r_for_net_target(*bad)
    assert load_default_policy().take_profit_r == D("2")                     # nessuna politica cambiata
