"""Istante decisionale PER SIMBOLO (laboratorio) confrontato con il comportamento attuale (un istante per ciclo).

Stesso scenario per le due modalita': 8 simboli, modello lento (orologio che avanza durante la chiamata), il sidecar
delle uscite che scrive un evento con l'ora reale a meta' ciclo. Si confrontano: timestamp, identificativi,
deduplicazione, thesis_id, freschezza di candele e prezzo, compatibilita' con il Dataset Builder.
Il runner cablato (`wiring.py`) resta in modalita' "cycle".
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tests.test_v3_runner_cycle import POLICY, RULES, RUN, VIEW, ScriptAnalyst, _events, _journal, _mandate
from backend.v3.decision_snapshot_v2 import SNAPSHOT_KIND
from backend.v3.events import Event
from backend.v3.features.indicators import Bar
from backend.v3.runner import decision_trace as dt
from backend.v3.runner.cycle import CycleBars, MarketEntryAnalyst, run_brain_cycle
from backend.v3.runner.thesis import ReentryPolicy

D = Decimal
STEP = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
G = (1_700_000_000_000 // 14_400_000) * 14_400_000
NOW = G + 20_000
SLOT_END = G + 3_600_000                                      # ciclo orario
SYMBOLS = tuple(f"S{i}USDT" for i in range(8))
ROOT = Path(__file__).resolve().parents[3]


def _price(open_ms: int) -> D:
    """Prezzo funzione dell'ISTANTE (non della posizione nella finestra): stesse candele per ogni richiesta."""
    k = open_ms // 900_000
    return D("100") + D(k % 13) / 10 + D(k % 7) / 20


def tbars(tf: str, now_ms: int, n: int = 60) -> list[Bar]:
    step = STEP[tf]
    last = now_ms // step * step - step
    out = []
    for i in range(n):
        t = last - (n - 1 - i) * step
        o, c = _price(t), _price(t + step - 900_000)
        out.append(Bar(t, o, max(o, c) + D("0.2"), min(o, c) - D("0.2"), c, D("10")))
    return out


class TimeStore:
    """Candele chiuse all'istante richiesto (come il CandleStore reale)."""

    def __init__(self):
        self.calls = []

    def refresh(self, symbol, tf, now_ms):
        self.calls.append((symbol, tf, now_ms))
        return tbars(tf, now_ms)


class Clock:
    def __init__(self, t=NOW + 1_000):
        self.t = t

    def __call__(self):
        return self.t


class SlowModel(ScriptAnalyst):
    """Il modello impiega ``latency`` ms; alla chiamata ``exit_at`` il sidecar scrive un'uscita con l'ora reale."""

    def __init__(self, clock, journal, latency=45_000, exit_at=3, **kw):
        super().__init__(**kw)
        self.clock, self.journal, self.latency, self.exit_at, self.seen = clock, journal, latency, exit_at, []
        self.walls: list = []

    def analyze(self, context, open_positions):
        self.seen.append((context.symbol, context.timestamp_ms, context.price))
        self.walls.append(self.clock.t)                                      # ora reale della chiamata
        self.clock.t += self.latency
        if len(self.seen) == self.exit_at:
            self.journal.append(Event(f"exit-{self.clock.t}", "brain", RUN, "paper_close", self.clock.t,
                                      "exit_service", {"position_id": "old", "realized_pnl": "0"}))
        return super().analyze(context, open_positions)


def _cycle(j, model, clock, *, instant, now=NOW, store=None, policy=None, symbols=SYMBOLS):
    return run_brain_cycle(
        now_ms=now, journal=j, run_id=RUN, symbols=symbols, store=store or TimeStore(), bars_holder=CycleBars(),
        analyst=MarketEntryAnalyst(model), view_params=VIEW, risk_policy=POLICY, mandate=_mandate(),
        policy_verifier=lambda m, p: True, market_rules=lambda s: RULES, initial_equity=D("100000"),
        slippage_bps=2, allowed_strategy_ids=("S25",), trace="required", wall_ms=clock,
        price_source=lambda sym, at: _price(at // 900_000 * 900_000), reentry_policy=policy,
        instant=instant, slot_start_ms=G if instant == "per_symbol" else None,
        slot_end_ms=SLOT_END if instant == "per_symbol" else None)


def _scenario(instant, kind="NO_TRADE"):
    j, clock = _journal(), Clock()
    model = SlowModel(clock, j, kind=kind)
    return j, model, _cycle(j, model, clock, instant=instant)


# ------------------------------------------------------------------------------------------------ confronto

def test_with_one_instant_per_cycle_later_decisions_are_late_and_not_valid():
    j, model, rep = _scenario("cycle")
    codes = [c for _, c, _, _ in rep.traces]
    # l'uscita arriva durante la 3a chiamata al modello: da quella decisione in poi la scrittura e' tardiva
    assert codes[:2] == ["recorded"] * 2 and set(codes[2:]) == {"recorded_decision_written_late"}
    assert dt.trace_coverage(j, RUN).valid == 2
    assert {ts for _, ts, _ in model.seen} == {NOW}                         # tutti decisi "a NOW"


def test_with_one_instant_per_symbol_every_decision_is_on_time_and_valid():
    j, model, rep = _scenario("per_symbol")
    assert [c for _, c, _, _ in rep.traces] == ["recorded"] * 8
    cov = dt.trace_coverage(j, RUN)
    assert (cov.decisions, cov.valid) == (8, 8)
    ts = [t for _, t in rep.instants]
    assert ts == sorted(ts) and len(set(ts)) == 8 and ts[0] >= NOW
    assert [t for _, t, _ in model.seen] == ts                              # il modello decide a quell'istante


def test_per_symbol_inputs_are_fresher():
    """Ciclo lento che attraversa la chiusura di una candela da 15 m."""
    runs = {}
    for mode in ("cycle", "per_symbol"):
        j, clock, store = _journal(), Clock(NOW + 600_000), TimeStore()   # 5 min prima della chiusura dei 15 m
        model = SlowModel(clock, j, latency=100_000, exit_at=99)
        _cycle(j, model, clock, instant=mode, store=store)
        ages = [w - ts for (_, ts, _), w in zip(model.seen, model.walls)]   # eta' dell'istante dei dati
        last_15m = [tbars("15m", t)[-1].open_time_ms for s_, tf, t in store.calls if tf == "15m"]
        runs[mode] = (ages, last_15m)
        prices = [(ts, p) for (_, ts, p) in model.seen]
        assert all(p == _price(ts // 900_000 * 900_000) for ts, p in prices)      # prezzo all'istante della decisione
        if mode == "per_symbol":
            assert len({p for _, p in prices}) > 1                                 # dopo la chiusura, prezzo nuovo
    cycle_ages, cycle_15m = runs["cycle"]
    sym_ages, sym_15m = runs["per_symbol"]
    assert cycle_ages == sorted(cycle_ages) and cycle_ages[-1] >= 7 * 100_000      # cresce con la coda del ciclo
    assert all(a <= 0 for a in sym_ages) or max(sym_ages) == 0
    assert len(set(cycle_15m)) == 1 and len(set(sym_15m)) == 2                   # nuova candela vista solo per simbolo


def test_decision_ids_are_distinct_and_tied_to_their_instant():
    j, _, rep = _scenario("per_symbol", kind="OPEN")
    decs = _events(j, "brain_decision")
    assert len({d.event_id for d in decs}) == 8
    assert {(d.payload["symbol"], d.occurred_at_ms) for d in decs} == set(rep.instants)
    for d in decs:                                                           # snapshot legato allo stesso istante
        snap = [e for e in _events(j, SNAPSHOT_KIND) if e.payload["decision_event_id"] == d.event_id][0]
        assert snap.payload["decision_ts_ms"] == snap.payload["snapshot_captured_at_ms"] == d.occurred_at_ms
        assert snap.payload["feature_asof_ms"] <= d.occurred_at_ms


# ------------------------------------------------------------------------------------------------ deduplicazione

def test_a_restart_in_the_same_slot_does_not_decide_again_per_symbol():
    j, clock = _journal(), Clock()
    _cycle(j, SlowModel(clock, j, latency=1_000, exit_at=99, kind="NO_TRADE"), clock, instant="per_symbol")
    clock.t = NOW + 125_000                                                  # riavvio: stesso slot, nuovo NOW
    rep2 = _cycle(j, SlowModel(clock, j, latency=1_000, exit_at=99, kind="NO_TRADE"), clock, instant="per_symbol",
                  now=NOW + 120_000)
    assert len(_events(j, "brain_decision")) == 8 and rep2.decisions == ()
    assert {c for _, c in rep2.errors} == {"already_decided_in_slot"}


def _cycle_mode(j, clock, now, *, slot=True, kind="NO_TRADE", symbols=SYMBOLS):
    return run_brain_cycle(
        now_ms=now, journal=j, run_id=RUN, symbols=symbols, store=TimeStore(), bars_holder=CycleBars(),
        analyst=MarketEntryAnalyst(SlowModel(clock, j, latency=1_000, exit_at=99, kind=kind)), view_params=VIEW,
        risk_policy=POLICY, mandate=_mandate(), policy_verifier=lambda m, p: True, market_rules=lambda s: RULES,
        initial_equity=D("100000"), slippage_bps=2, allowed_strategy_ids=("S25",), trace="required", wall_ms=clock,
        price_source=lambda sym, at: _price(at // 900_000 * 900_000),
        slot_start_ms=G if slot else None, slot_end_ms=SLOT_END if slot else None)


def test_defect_without_slot_bounds_a_restart_decides_every_symbol_again():
    """Difetto classificato (20/11): senza limiti dello slot un riavvio ridecide tutto (comportamento precedente)."""
    j, clock = _journal(), Clock()
    _cycle_mode(j, clock, NOW, slot=False)
    _cycle_mode(j, clock, NOW + 120_000, slot=False)
    assert len(_events(j, "brain_decision")) == 16


def test_fixed_with_slot_bounds_cycle_mode_does_not_decide_again_after_a_restart():
    j, clock = _journal(), Clock()
    _cycle_mode(j, clock, NOW)
    rep2 = _cycle_mode(j, clock, NOW + 120_000)
    assert len(_events(j, "brain_decision")) == 8 and rep2.decisions == ()
    assert {c for _, c in rep2.errors} == {"already_decided_in_slot"}


def test_a_restart_after_a_partial_cycle_decides_only_the_missing_symbols():
    j, clock = _journal(), Clock()
    _cycle_mode(j, clock, NOW, symbols=SYMBOLS[:3])                         # crash dopo 3 simboli
    rep2 = _cycle_mode(j, clock, NOW + 120_000)
    assert [d[0] for d in rep2.decisions] == list(SYMBOLS[3:])
    assert len(_events(j, "brain_decision")) == 8


@pytest.mark.parametrize("mode", ["cycle", "per_symbol"])
def test_no_double_open_after_a_restart_in_the_same_slot(mode):
    j, clock = _journal(), Clock()
    first = (_cycle_mode(j, clock, NOW, kind="OPEN") if mode == "cycle"
             else _cycle(j, SlowModel(clock, j, latency=1_000, exit_at=99, kind="OPEN"), clock, instant="per_symbol"))
    opened = {s for s, _ in first.opened}
    assert opened
    clock.t = NOW + 125_000
    second = (_cycle_mode(j, clock, NOW + 120_000, kind="OPEN") if mode == "cycle"
              else _cycle(j, SlowModel(clock, j, latency=1_000, exit_at=99, kind="OPEN"), clock,
                          instant="per_symbol", now=NOW + 120_000))
    assert second.opened == () and len(_events(j, "paper_open")) == len(opened)
    # anche un simbolo chiuso nel frattempo non si riapre nello stesso slot
    pid = first.opened[0][1]
    j.append(Event("close-x", "brain", RUN, "paper_close", NOW + 130_000, "exit_service",
                   {"position_id": pid, "symbol": first.opened[0][0], "realized_pnl": "-1"}))
    clock.t = NOW + 200_000
    third = (_cycle_mode(j, clock, NOW + 190_000, kind="OPEN") if mode == "cycle"
             else _cycle(j, SlowModel(clock, j, latency=1_000, exit_at=99, kind="OPEN"), clock,
                         instant="per_symbol", now=NOW + 190_000))
    assert third.opened == ()


def test_slot_bounds_are_validated():
    with pytest.raises(ValueError, match="invalid_slot"):
        run_brain_cycle(now_ms=NOW, journal=_journal(), run_id=RUN, symbols=(), store=None, bars_holder=None,
                        analyst=None, view_params=None, risk_policy=None, mandate=None, policy_verifier=None,
                        market_rules=None, initial_equity=D("1"), slippage_bps=0, slot_start_ms=NOW + 1,
                        slot_end_ms=SLOT_END)


def test_the_wired_runner_passes_the_runner_slot():
    src = (ROOT / "backend/v3/runner/wiring.py").read_text()
    assert "slot_start = slot * config.cycle_ms" in src
    assert "slot_start_ms=slot_start, slot_end_ms=slot_start + config.cycle_ms" in src


def test_a_decision_outside_the_current_slot_does_not_count_as_already_decided():
    j, clock = _journal(), Clock()
    j.append(Event("brain-req-next", "brain", RUN, "brain_decision", SLOT_END, "brain_f2_engine",
                   {"kind": "NO_TRADE", "status": "REJECTED", "symbol": SYMBOLS[0]}))
    rep = _cycle(j, SlowModel(clock, j, latency=1_000, exit_at=99, kind="NO_TRADE"), clock, instant="per_symbol",
                 symbols=SYMBOLS[:1])
    assert len(rep.decisions) == 1 and rep.errors == ()


def test_an_instant_outside_the_slot_or_going_back_decides_nothing():
    j, clock = _journal(), Clock(SLOT_END)
    rep = _cycle(j, SlowModel(clock, j, exit_at=99), clock, instant="per_symbol", symbols=SYMBOLS[:2])
    assert rep.decisions == () and {c for _, c in rep.errors} == {"instant_out_of_slot"}

    class Back(Clock):
        def __call__(self):
            self.t -= 5_000
            return self.t
    j2, back = _journal(), Back(NOW + 50_000)
    rep2 = _cycle(j2, SlowModel(back, j2, latency=0, exit_at=99), back, instant="per_symbol", symbols=SYMBOLS[:2])
    assert len(rep2.decisions) == 1 and ("S1USDT", "instant_out_of_slot") in rep2.errors


def test_per_symbol_needs_a_clock_and_a_slot():
    with pytest.raises(ValueError, match="per_symbol_requires_clock_and_slot"):
        run_brain_cycle(now_ms=NOW, journal=_journal(), run_id=RUN, symbols=(), store=None, bars_holder=None,
                        analyst=None, view_params=None, risk_policy=None, mandate=None, policy_verifier=None,
                        market_rules=None, initial_equity=D("1"), slippage_bps=0, instant="per_symbol")
    with pytest.raises(ValueError, match="invalid_instant_mode"):
        run_brain_cycle(now_ms=NOW, journal=_journal(), run_id=RUN, symbols=(), store=None, bars_holder=None,
                        analyst=None, view_params=None, risk_policy=None, mandate=None, policy_verifier=None,
                        market_rules=None, initial_equity=D("1"), slippage_bps=0, instant="symbol")


# ------------------------------------------------------------------------------------------------ tesi e builder

def test_thesis_chains_work_with_per_symbol_instants():
    j, clock = _journal(), Clock()
    policy = ReentryPolicy()
    r1 = _cycle(j, SlowModel(clock, j, latency=1_000, exit_at=99, kind="OPEN"), clock, instant="per_symbol",
                policy=policy, symbols=SYMBOLS[:1])
    pid = r1.opened[0][1]
    j.append(Event("close-a", "brain", RUN, "paper_close", NOW + 1_800_000, "exit_service",
                   {"position_id": pid, "symbol": SYMBOLS[0], "realized_pnl": "-1"}))
    clock.t = NOW + 3_600_000 + 5_000
    r2 = run_brain_cycle(
        now_ms=NOW + 3_600_000, journal=j, run_id=RUN, symbols=SYMBOLS[:1], store=TimeStore(),
        bars_holder=CycleBars(), analyst=MarketEntryAnalyst(SlowModel(clock, j, latency=1_000, exit_at=99, kind="OPEN")),
        view_params=VIEW, risk_policy=POLICY, mandate=_mandate(), policy_verifier=lambda m, p: True,
        market_rules=lambda s: RULES, initial_equity=D("100000"), slippage_bps=2, allowed_strategy_ids=("S25",),
        trace="required", wall_ms=clock, price_source=lambda sym, at: _price(at // 900_000 * 900_000),
        reentry_policy=policy, instant="per_symbol", slot_start_ms=G + 3_600_000, slot_end_ms=SLOT_END + 3_600_000)
    assert r1.theses[0][1] == r2.theses[0][1] and r2.theses[0][2] == 2


def test_the_dataset_builder_admits_per_symbol_snapshots_and_verifies_their_features():
    sys.path.insert(0, str(ROOT / "ops" / "brain-unico" / "training"))
    try:
        import readers as R
        import snapshot_link as SL
        import snapshot_verify as SV
    finally:
        sys.path.pop(0)
    j, _, rep = _scenario("per_symbol")
    data = R.read_v3(str(j.filename))
    for did, dec in data["decisions"].items():
        assert SL.admit(did, dec, data["snapshots"].get(did), [], data["timeline"]).status == "admitted"
    # archivio con le stesse candele (funzione dell'istante): le feature di ogni simbolo si ricalcolano
    import json, tempfile
    root = Path(tempfile.mkdtemp())
    for tf, step in STEP.items():
        (root / tf).mkdir()
        (root / tf / "candles_meta.json").write_text(json.dumps(
            {"exchange": "bitget", "market": "m", "price_basis": "last", "source": "s", "interval_ms": step}))
        bars = {b.open_time_ms: b for _, t in rep.instants for b in tbars(tf, t)}
        for sym in SYMBOLS:
            (root / tf / f"{sym}.jsonl").write_text("".join(json.dumps(
                {"t": b.open_time_ms, "o": str(b.open), "h": str(b.high), "l": str(b.low), "c": str(b.close),
                 "v": str(b.volume)}) + "\n" for _, b in sorted(bars.items())))
    dc = SV.DecisionCandles(str(root))
    verdicts = {SV.verify(s[0]["p"], dc)[0] for s in data["snapshots"].values()}
    assert verdicts == {"verified"}


def test_the_wired_runner_keeps_the_current_mode():
    assert "instant=" not in (ROOT / "backend/v3/runner/wiring.py").read_text()
