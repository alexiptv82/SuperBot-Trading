"""A1 — uscite meccaniche del Brain (backend/v3/runner/exits.py): test offline.

Oracolo scritto qui con una formulazione DIVERSA dal codice: ogni prezzo e' convertito in multipli di
rischio R (stop = -1, take-profit = +take_profit_r) e tutto e' calcolato in ``Fraction``; il codice
invece lavora sui prezzi con ``Decimal``. Dati sintetici con seme fisso. Ogni caso di errore parte da
un input valido e cambia una cosa sola.
"""
from __future__ import annotations

import ast
import json
import os
import random
import subprocess
import sys
import tempfile
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from backend.v3.events import EventJournal
from backend.v3.executor import paper_close
from backend.v3.executor.paper import execute_paper
from backend.v3.executor.paper_close import CLOSE_REASONS, close_paper
from backend.v3.features.indicators import Bar
from backend.v3.outcomes import EXIT_REASONS, extract_outcomes
from backend.v3.runner import exits
from backend.v3.runner.exits import (
    EXIT_STOP, EXIT_TAKE_PROFIT, EXIT_TIMEOUT, ExitPolicy, ExitSignal, evaluate_exit,
    load_default_policy, load_exit_policy, take_profit_price,
)

D = Decimal
STEP = 60_000
T0 = 1_800_000_000_000 // STEP * STEP
POLICY = ExitPolicy(D("2"), 60 * 3_600_000, D("2"))
ROOT = Path(__file__).resolve().parents[2]


def bar(i, o, h, l, c, step=STEP, t0=T0):
    return Bar(t0 + i * step, D(str(o)), D(str(h)), D(str(l)), D(str(c)), D("1"))


def run(side, bars, *, fill="100", stop=None, opened=T0, policy=POLICY, candle_ms=STEP):
    stop = stop if stop is not None else ("98" if side == 1 else "102")
    return evaluate_exit(side=side, fill_price=D(fill), stop_price=D(stop), opened_at_ms=opened,
                         bars=bars, candle_ms=candle_ms, policy=policy)


def code(fn):
    with pytest.raises(ValueError) as e:
        fn()
    return str(e.value)


# ----------------------------------------------------------------------------- oracolo in R
def _q8(x: Fraction) -> Decimal:
    n = round(x * 10 ** 8)                                  # round() su Fraction: half-even
    return D(n) / D(10 ** 8)


def oracle(side, fill, stop, opened, bars, candle_ms, policy):
    F = Fraction
    fill, stop = F(fill), F(stop)
    risk = abs(fill - stop)
    tp_r, slip = F(policy.take_profit_r), F(policy.stop_slippage_bp) / 10_000

    def r(p):                                               # prezzo -> multiplo di rischio
        return side * (F(p) - fill) / risk

    def px(rr):                                             # multiplo di rischio -> prezzo
        return fill + side * risk * rr

    for b in bars:
        if b.open_time_ms < opened:
            continue
        lo_r, hi_r = min(r(b.low), r(b.high)), max(r(b.low), r(b.high))
        if lo_r <= -1:
            base = px(min(F(-1), r(b.open)))                # stop, o apertura se ha saltato lo stop
            return (EXIT_STOP, _q8(base - side * base * slip), b.open_time_ms)
        if hi_r >= tp_r:
            return (EXIT_TAKE_PROFIT, _q8(px(tp_r)), b.open_time_ms)
        if b.open_time_ms + candle_ms - opened >= policy.max_hold_ms:
            return (EXIT_TIMEOUT, b.close, b.open_time_ms)
    return None


def as_tuple(sig):
    return None if sig is None else (sig.reason, sig.price, sig.bar_open_time_ms)


def random_case(seed):
    rnd = random.Random(seed)
    side = rnd.choice((1, -1))
    fill = D(rnd.randint(5000, 60000)) / 100
    dist = (fill * D(rnd.randint(30, 300)) / 10000).quantize(D("0.01")) or D("0.01")
    stop = fill - side * dist
    vol = rnd.choice((D("0.0008"), D("0.002"), D("0.006")))   # bassa: timeout/nessuna; alta: stop/target
    n = rnd.randint(1, 40)
    opened = T0 + rnd.randint(0, 3) * STEP + rnd.choice((0, 0, 17_000))
    price, bars = fill, []
    for i in range(n):
        o = price
        c = (o * (1 + D(rnd.randint(-100, 100)) / 100 * vol)).quantize(D("0.01"))
        hi = max(o, c) * (1 + D(rnd.randint(0, 100)) / 100 * vol)
        lo = min(o, c) * (1 - D(rnd.randint(0, 100)) / 100 * vol)
        if rnd.random() < 0.05:                              # gap: apertura lontana dalla chiusura precedente
            o = (o * (1 + D(rnd.choice((-3, 3))) * vol)).quantize(D("0.01"))
            hi, lo = max(hi, o), min(lo, o)
        o, c = max(o, D("0.01")), max(c, D("0.01"))
        hi, lo = max(o, c, hi).quantize(D("0.01")), min(o, c, lo).quantize(D("0.01"))
        bars.append(Bar(T0 + i * STEP, o, hi, max(lo, D("0.01")), c, D("1")))
        price = c
    hold = rnd.choice((5, 15, 30, 10_000)) * STEP
    pol = ExitPolicy(D(rnd.choice(("0.5", "1", "1.5", "2", "3"))), hold, D(rnd.choice(("0", "2", "7.5"))))
    return side, fill, stop, opened, bars, pol


# ----------------------------------------------------------------------------- 1. oracolo
@pytest.mark.parametrize("seed", range(300))
def test_evaluate_exit_matches_the_r_multiple_oracle(seed):
    side, fill, stop, opened, bars, pol = random_case(seed)
    got = evaluate_exit(side=side, fill_price=fill, stop_price=stop, opened_at_ms=opened,
                        bars=bars, candle_ms=STEP, policy=pol)
    assert as_tuple(got) == oracle(side, fill, stop, opened, bars, STEP, pol)
    if got is not None:
        assert type(got) is ExitSignal and type(got.price) is D and got.price > 0
        if got.reason != EXIT_TIMEOUT:                       # stop e target sono quantizzati a 8 decimali
            assert got.price.as_tuple().exponent == -8


def test_the_scenarios_exercise_every_outcome():
    seen = set()
    for seed in range(300):
        side, fill, stop, opened, bars, pol = random_case(seed)
        got = oracle(side, fill, stop, opened, bars, STEP, pol)
        seen.add((side, None if got is None else got[0]))
    assert seen >= {(s, r) for s in (1, -1) for r in (None, EXIT_STOP, EXIT_TAKE_PROFIT, EXIT_TIMEOUT)}


# ----------------------------------------------------------------------------- 2. casi a mano
@pytest.mark.parametrize("side,stop,tp", [(1, "98", "104"), (-1, "102", "96")])
def test_take_profit_price(side, stop, tp):
    assert take_profit_price(side, D("100"), D(stop), POLICY) == D(tp)


def test_take_profit_rounds_half_even_not_half_up():
    pol = ExitPolicy(D("2.5"), 3_600_000, D("0"))
    assert take_profit_price(1, D("100"), D("99.99999999"), pol) == D("100.00000002")   # ...025 -> 2 (pari)
    assert take_profit_price(-1, D("100"), D("100.00000001"), pol) == D("99.99999998")  # ...975 -> 8 (pari)


@pytest.mark.parametrize("side,hit,ex", [
    (1, bar(1, 100, 100.5, 97.5, 98), "98"),
    (-1, bar(1, 100, 102.5, 99.5, 102), "102"),
])
def test_stop_exit_price_is_the_stop_with_slippage_against_us(side, hit, ex):
    pol = ExitPolicy(D("2"), 10 ** 12, D("10"))
    got = run(side, [bar(0, 100, 100.5, 99.5, 100), hit], policy=pol)
    stop = D(ex)
    assert got.reason == EXIT_STOP and got.bar_open_time_ms == T0 + STEP
    assert got.price == (stop * (D("0.999") if side == 1 else D("1.001"))).quantize(D("0.00000001"))


@pytest.mark.parametrize("side,touch,short_of_it,reason", [
    (1, dict(l="98"), dict(l="98.01"), EXIT_STOP),            # long: il minimo tocca lo stop
    (1, dict(h="104"), dict(h="103.99"), EXIT_TAKE_PROFIT),   # long: il massimo tocca il target
    (-1, dict(h="102"), dict(h="101.99"), EXIT_STOP),         # short: il massimo tocca lo stop
    (-1, dict(l="96"), dict(l="96.01"), EXIT_TAKE_PROFIT),    # short: il minimo tocca il target
])
def test_exact_touch_triggers_and_one_tick_short_does_not(side, touch, short_of_it, reason):
    """Uguaglianza esatta = colpito; un centesimo prima = no (distingue <= da <)."""
    def make(over):
        h = over.get("h", "100.5" if side == 1 else "101.5")
        l = over.get("l", "99.5" if side == 1 else "98.5")
        return [bar(0, 100, h, l, 100)]
    assert run(side, make(touch)).reason == reason
    assert run(side, make(short_of_it)) is None


def test_gap_through_the_stop_exits_at_the_open_not_at_the_stop():
    pol = ExitPolicy(D("2"), 10 ** 12, D("0"))
    assert run(1, [bar(0, 96, 97, 95, 96)], policy=pol).price == D("96")           # apre sotto lo stop (98)
    assert run(-1, [bar(0, 104, 105, 103, 104)], policy=pol).price == D("104")     # apre sopra lo stop (102)
    assert run(1, [bar(0, 99, 99.5, 97, 98)], policy=pol).price == D("98")         # nessun gap: lo stop


def test_stop_exit_price_rounds_half_even_not_half_up():
    """Pareggio esatto al nono decimale: ...996|5 -> 6 (pari) per il long, ...002|5 -> 2 (pari) per lo short."""
    pol = ExitPolicy(D("2"), 10 ** 12, D("0.0000875"))
    got = run(1, [bar(0, 5, 5, 3, 4)], fill="5", stop="4", policy=pol)
    assert got.price == D("3.99999996")
    pol = ExitPolicy(D("2"), 10 ** 12, D("0.000125"))
    got = run(-1, [bar(0, 1.5, 2.1, 1.4, 1.5)], fill="1", stop="2", policy=pol)
    assert got.price == D("2.00000002")


def test_policy_boundary_values_are_accepted():
    bars = [bar(0, 100, 100.5, 99.5, 100)]
    for pol in (ExitPolicy(D("20"), 1, D("100")), ExitPolicy(D("0.0001"), 10 ** 12, D("0")),
                ExitPolicy(D("2"), 1, D("100"))):
        run(1, bars, policy=pol)


def test_stop_wins_when_stop_and_target_are_in_the_same_bar():
    assert run(1, [bar(0, 100, 105, 97, 100)]).reason == EXIT_STOP
    assert run(-1, [bar(0, 100, 103, 95, 100)]).reason == EXIT_STOP


def test_take_profit_fills_at_the_target_even_if_the_bar_opens_beyond_it():
    got = run(1, [bar(0, 106, 107, 105, 106)])
    assert (got.reason, got.price) == (EXIT_TAKE_PROFIT, D("104"))
    got = run(-1, [bar(0, 94, 95, 93, 94)])
    assert (got.reason, got.price) == (EXIT_TAKE_PROFIT, D("96"))


def test_bars_before_the_open_instant_are_ignored_and_the_bar_at_the_instant_counts():
    bars = [bar(0, 100, 100.5, 90, 91), bar(1, 100, 100.5, 99.5, 100), bar(2, 100, 100.5, 90, 91)]
    assert run(1, bars, opened=T0 + 2 * STEP).bar_open_time_ms == T0 + 2 * STEP    # la barra 2 e' alla pari
    assert run(1, bars, opened=T0 + 1 * STEP).bar_open_time_ms == T0 + 2 * STEP    # la 1 e' tranquilla
    assert run(1, bars, opened=T0 + 1).bar_open_time_ms == T0 + 2 * STEP           # 1 ms dopo la barra 0 e 1: salta
    assert run(1, bars[:2], opened=T0 + 1) is None
    assert run(1, bars[:2], opened=T0).bar_open_time_ms == T0                      # inclusa: apre all'istante


def test_first_trigger_wins_and_later_bars_are_not_considered():
    bars = [bar(0, 100, 100.5, 99.5, 100), bar(1, 100, 105, 99.5, 104), bar(2, 100, 100.5, 90, 91)]
    got = run(1, bars)
    assert (got.reason, got.bar_open_time_ms) == (EXIT_TAKE_PROFIT, T0 + STEP)


def test_timeout_boundary_and_price():
    hold = 5 * STEP
    pol = ExitPolicy(D("20"), hold, D("0"))
    quiet = [bar(i, 100, 100.2, 99.8, D("100") + D(i) / 100) for i in range(8)]
    got = run(1, quiet, policy=pol)
    assert (got.reason, got.bar_open_time_ms, got.price) == (EXIT_TIMEOUT, T0 + 4 * STEP, D("100.04"))
    assert run(1, quiet[:4], policy=pol) is None                                    # 4 minuti: non ancora
    assert run(1, quiet[:5], policy=pol).reason == EXIT_TIMEOUT                     # 5 minuti esatti: >=
    late = ExitPolicy(D("20"), hold + 1, D("0"))
    assert run(1, quiet[:5], policy=late) is None                                   # un ms in meno: no


def test_stop_and_target_take_precedence_over_the_timeout_in_the_closing_bar():
    pol = ExitPolicy(D("2"), 2 * STEP, D("0"))
    assert run(1, [bar(0, 100, 100.2, 99.8, 100), bar(1, 100, 100.2, 97, 98)], policy=pol).reason == EXIT_STOP
    assert run(1, [bar(0, 100, 100.2, 99.8, 100), bar(1, 100, 105, 99.8, 104)], policy=pol).reason == EXIT_TAKE_PROFIT


def test_no_bars_or_nothing_happens_returns_none():
    assert run(1, []) is None
    assert run(1, [bar(0, 100, 100.5, 99.5, 100)]) is None


def test_inputs_are_not_modified_and_the_result_is_deterministic():
    bars = [bar(0, 100, 100.5, 99.5, 100), bar(1, 100, 105, 99.5, 104)]
    before = list(bars)
    assert run(1, bars) == run(1, bars) and bars == before


# ----------------------------------------------------------------------------- 3. errori
def _ok(**over):
    kw = dict(side=1, fill_price=D("100"), stop_price=D("98"), opened_at_ms=T0, bars=[bar(0, 100, 101, 99, 100)],
              candle_ms=STEP, policy=POLICY)
    kw.update(over)
    return lambda: evaluate_exit(**kw)


def test_control_valid_call_works():
    assert _ok()() is None


@pytest.mark.parametrize("over,expected", [
    (dict(policy=None), "invalid_policy"),
    (dict(policy=ExitPolicy(1, POLICY.max_hold_ms, D("2"))), "invalid_policy"),
    (dict(policy=ExitPolicy(D("0"), POLICY.max_hold_ms, D("2"))), "invalid_policy"),
    (dict(policy=ExitPolicy(D("20.0001"), POLICY.max_hold_ms, D("2"))), "invalid_policy"),
    (dict(policy=ExitPolicy(D("NaN"), POLICY.max_hold_ms, D("2"))), "invalid_policy"),
    (dict(policy=ExitPolicy(D("2"), 0, D("2"))), "invalid_policy"),
    (dict(policy=ExitPolicy(D("2"), True, D("2"))), "invalid_policy"),
    (dict(policy=ExitPolicy(D("2"), POLICY.max_hold_ms, D("-0.1"))), "invalid_policy"),
    (dict(policy=ExitPolicy(D("2"), POLICY.max_hold_ms, D("100.1"))), "invalid_policy"),
    (dict(policy=ExitPolicy(D("2"), POLICY.max_hold_ms, 2)), "invalid_policy"),
    (dict(side=0), "invalid_side"), (dict(side=True), "invalid_side"), (dict(side=2), "invalid_side"),
    (dict(side="1"), "invalid_side"),
    (dict(fill_price=100), "invalid_position"), (dict(fill_price=100.0), "invalid_position"),
    (dict(stop_price=98.0), "invalid_position"), (dict(fill_price=D("0")), "invalid_position"),
    (dict(stop_price=D("0")), "invalid_position"), (dict(stop_price=D("NaN")), "invalid_position"),
    (dict(stop_price=D("100")), "invalid_position"), (dict(stop_price=D("101")), "invalid_position"),
    (dict(side=-1), "invalid_position"),                                  # stop 98 sotto il prezzo: sbagliato per uno short
    (dict(opened_at_ms=0), "invalid_opened_at"), (dict(opened_at_ms=True), "invalid_opened_at"),
    (dict(opened_at_ms=float(T0)), "invalid_opened_at"), (dict(opened_at_ms=-1), "invalid_opened_at"),
    (dict(bars=None), "invalid_bars"), (dict(bars="x"), "invalid_bars"),
    (dict(bars=[bar(0, 100, 101, 99, 100), bar(2, 100, 101, 99, 100)]), "invalid_bars"),   # buco
    (dict(bars=[bar(1, 100, 101, 99, 100), bar(0, 100, 101, 99, 100)]), "invalid_bars"),   # ordine
    (dict(bars=[Bar(T0, 100.0, D("101"), D("99"), D("100"), D("1"))]), "invalid_bars"),
    (dict(bars=[Bar(T0, D("100"), D("99"), D("101"), D("100"), D("1"))]), "invalid_bars"),  # high < low
    (dict(bars=[Bar(T0 + 1, D("100"), D("101"), D("99"), D("100"), D("1"))]), "invalid_bars"),  # fuori griglia
    (dict(candle_ms=0), "invalid_candle_ms"), (dict(candle_ms=True), "invalid_candle_ms"),
    (dict(candle_ms=60.0), "invalid_candle_ms"),
])
def test_bad_inputs_fail_with_exact_codes(over, expected):
    assert code(_ok(**over)) == expected


def test_policy_is_checked_before_position_and_position_before_bars():
    assert code(_ok(policy=None, side=0, bars=None)) == "invalid_policy"
    assert code(_ok(side=0, bars=None)) == "invalid_side"
    assert code(_ok(opened_at_ms=0, bars=None)) == "invalid_opened_at"


# ----------------------------------------------------------------------------- 4. politica da file
def test_default_policy_file_and_values():
    assert load_default_policy() == ExitPolicy(D("2"), 24 * 3_600_000, D("2"))
    raw = (ROOT / "backend/v3/runner/exit_policy.json").read_bytes()
    assert load_exit_policy(raw) == load_default_policy()


def _policy_raw(**over):
    d = {"schema_version": 1, "take_profit_r": "2", "max_hold_hours": 60, "stop_slippage_bp": "2"}
    d.update(over)
    return json.dumps(d).encode()


def test_policy_loader_control():
    assert load_exit_policy(_policy_raw(take_profit_r="1.5", max_hold_hours=12, stop_slippage_bp="0")) \
        == ExitPolicy(D("1.5"), 12 * 3_600_000, D("0"))


@pytest.mark.parametrize("raw", [
    _policy_raw(schema_version=2), _policy_raw(schema_version=True), _policy_raw(schema_version="1"),
    _policy_raw(take_profit_r="0"), _policy_raw(take_profit_r="21"), _policy_raw(take_profit_r=2),
    _policy_raw(take_profit_r="2."), _policy_raw(take_profit_r=" 2"), _policy_raw(take_profit_r="1e1"),
    _policy_raw(take_profit_r="-2"), _policy_raw(take_profit_r="2.00001"), _policy_raw(take_profit_r="٢"),
    _policy_raw(max_hold_hours=0), _policy_raw(max_hold_hours=721), _policy_raw(max_hold_hours=True),
    _policy_raw(max_hold_hours="60"), _policy_raw(max_hold_hours=1.5),
    _policy_raw(stop_slippage_bp="100.1"), _policy_raw(stop_slippage_bp="-1"), _policy_raw(stop_slippage_bp=2),
    b'{"schema_version":1,"take_profit_r":"2","max_hold_hours":60}',
    b'{"schema_version":1,"take_profit_r":"2","max_hold_hours":60,"stop_slippage_bp":"2","x":1}',
    b'{"schema_version":1,"take_profit_r":"2","take_profit_r":"3","max_hold_hours":60,"stop_slippage_bp":"2"}',
    b'{"schema_version":1,"take_profit_r":NaN,"max_hold_hours":60,"stop_slippage_bp":"2"}',
    b'[]', b'null', b'', b'\xff', b'{',
])
def test_policy_loader_rejects(raw):
    assert code(lambda: load_exit_policy(raw)) == "invalid_policy"


@pytest.mark.parametrize("raw", ["{}", None, 1, bytearray(b"{}"), _policy_raw().decode()])
def test_policy_loader_takes_only_bytes(raw):
    assert code(lambda: load_exit_policy(raw)) == "invalid_policy"


def test_default_policy_loads_from_any_cwd(tmp_path):
    src = "from backend.v3.runner.exits import load_default_policy as f; print(f().max_hold_ms)"
    for cwd in (ROOT, Path("/tmp")):
        env = dict(os.environ, PYTHONPATH=f"{ROOT}:{ROOT / 'backend'}")
        out = subprocess.run([sys.executable, "-c", src], cwd=cwd, env=env, capture_output=True,
                             text=True, check=True)
        assert out.stdout.strip() == str(24 * 3_600_000)


# ----------------------------------------------------------------------------- 5. igiene
def test_module_is_pure_no_float_no_network_no_clock():
    tree = ast.parse((ROOT / "backend/v3/runner/exits.py").read_text(encoding="utf-8"))
    assert [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and type(n.value) is float] == []
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imported.add(n.module or "")
    assert not imported & {"time", "datetime", "socket", "urllib", "requests", "os", "random"}
    assert not any(m.startswith("backend.v3.executor") or m.startswith("backend.v3.events") for m in imported)
    reads = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "read_bytes"]
    assert len(reads) == 1                                                  # solo load_default_policy


# ----------------------------------------------------------------------------- 6. vocabolario dei motivi
def test_exit_reasons_are_one_vocabulary_in_executor_and_outcomes():
    assert CLOSE_REASONS == EXIT_REASONS
    assert {EXIT_STOP, EXIT_TAKE_PROFIT, EXIT_TIMEOUT} <= CLOSE_REASONS
    assert {"manual", "brain_close", "liquidation"} <= CLOSE_REASONS
    assert paper_close.CLOSE_REASONS is CLOSE_REASONS


def _journal():
    j = EventJournal(os.path.join(tempfile.mkdtemp(), "journal.db"))
    j.init_schema()
    return j


@pytest.mark.parametrize("reason", [EXIT_STOP, EXIT_TAKE_PROFIT, EXIT_TIMEOUT])
def test_new_reasons_travel_from_close_paper_to_the_outcome(reason):
    """Produttori veri: execute_paper -> close_paper -> extract_outcomes."""
    from backend.tests.test_brain_f7_outcomes import _hand, _report
    j = _journal()
    pid = execute_paper(_hand(), portfolio_id="hawk", run_id="r-a1", journal=j,
                        now_ms=1_700_000_001_000).position_id
    rec = close_paper(portfolio_id="hawk", run_id="r-a1", position_id=pid, exit_price=D("31000"),
                      reason=reason, fee_bps=6, journal=j, now_ms=1_700_000_061_000)
    assert rec.reason == reason
    out = _report(j, run="r-a1").outcomes
    assert [o.exit_reason for o in out] == [reason]


def test_unknown_reason_is_still_refused():
    from backend.tests.test_brain_f7_outcomes import _hand
    j = _journal()
    pid = execute_paper(_hand(), portfolio_id="hawk", run_id="r-a1", journal=j,
                        now_ms=1_700_000_001_000).position_id
    for bad in ("tp", "take-profit", "TIMEOUT", "", None, "stop "):
        with pytest.raises(Exception) as e:
            close_paper(portfolio_id="hawk", run_id="r-a1", position_id=pid, exit_price=D("31000"),
                        reason=bad, fee_bps=6, journal=j, now_ms=1_700_000_061_000)
        assert str(e.value) == "invalid_reason"
