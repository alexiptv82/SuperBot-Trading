"""Test del pool di regole: nessuna rete, solo dati sintetici."""
import dataclasses
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import strategy_lab as sl  # noqa: E402
from rule_pool import allocator as alloc  # noqa: E402
from rule_pool import evidence as ev  # noqa: E402
from rule_pool import pool, replay, rules  # noqa: E402
from rule_pool.journal import ImmutableTradeError, Journal, ParamsChangedError  # noqa: E402

DAY = 86_400_000


def random_walk(n=20000, seed=7):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    o = np.r_[100.0, c[:-1]]
    spread = np.abs(rng.normal(0, 0.0015, n))
    return sl.Bars(np.arange(n, dtype=np.int64) * sl.M15, o, np.maximum(o, c) * (1 + spread),
                   np.minimum(o, c) * (1 - spread), c, rng.lognormal(0, 0.5, n))


def spread_times(n, months=12, start=1_600_000_000_000):
    return (start + np.linspace(0, months * 30 * DAY, n, endpoint=False)).astype(np.int64)


def strong_evidence(n=400, mean=80.0, sd=300.0, seed=1, excess=60.0):
    rng = np.random.default_rng(seed)
    t, x = spread_times(n), rng.normal(mean, sd, n)
    return alloc.RuleEvidence(ev.summarize(t, x), ev.halves_positive(t, x), excess)


# ---------------------------------------------------------------------- regole
def test_rule_hash_stable_and_sensitive():
    a = rules.Rule("A", "S1_donchian_4h", rules.MAJORS)
    assert a.params_hash() == rules.Rule("A", "S1_donchian_4h", rules.MAJORS).params_hash()
    assert a.params_hash() != rules.Rule("A", "S1_donchian_4h", rules.TOP10).params_hash()
    assert a.params_hash() != rules.Rule("A", "S2_donchian_1h", rules.MAJORS).params_hash()
    assert a.params_hash() != rules.Rule("A", "S1_donchian_4h", rules.MAJORS, cost_profile="B").params_hash()
    saved = list(sl.STRATEGIES)
    h_before = a.params_hash()
    try:  # cambiare un'uscita cambia l'hash
        sl.STRATEGIES[0] = dataclasses.replace(
            saved[0], cfg=dataclasses.replace(saved[0].cfg, stop_mult=saved[0].cfg.stop_mult + 1))
        assert a.params_hash() != h_before
    finally:
        sl.STRATEGIES[:] = saved
    assert a.params_hash() == h_before


def test_rule_validation():
    for bad in (lambda: rules.Rule("A", "S1_donchian_4h", ()),
                lambda: rules.Rule("A", "S1_donchian_4h", rules.MAJORS, kind="x"),
                lambda: rules.Rule("A", "S1_donchian_4h", rules.MAJORS, cost_profile="Z"),
                lambda: rules.Rule("A", "S1_donchian_4h", rules.MAJORS, kind="control"),
                lambda: rules.Rule("A", "nope", rules.MAJORS)):
        try:
            bad()
        except (ValueError, KeyError):
            continue
        raise AssertionError("doveva sollevare un errore")


def test_inverse_strategy_source_includes_wrapped_function():
    inv = next(s for s in sl.STRATEGIES if s.name == "S4_pullback_15m_inv")
    assert "def sig_pullback15m" in rules._src(inv.build)


def test_initial_rules_shape():
    rs = rules.initial_rules()
    assert rules.promotable_count(rs) == 3
    ids = {r.rule_id for r in rs}
    assert all(r.base_rule in ids for r in rs if r.kind == "control")
    assert len({r.params_hash() for r in rs}) == len(rs)


# -------------------------------------------------------------------- giornale
def test_journal_frozen_params_and_versions():
    j = Journal()
    r = rules.Rule("A", "S1_donchian_4h", rules.MAJORS)
    j.register_rule(r)
    j.register_rule(r)  # idempotente
    changed = rules.Rule("A", "S1_donchian_4h", rules.TOP10)
    try:
        j.register_rule(changed)
    except ParamsChangedError:
        pass
    else:
        raise AssertionError("parametri cambiati senza nuova versione")
    j.register_rule(dataclasses.replace(changed, version=2))


def _tr(**kw):
    base = dict(rule_id="A", version=1, venue="replay", symbol="BTC", side=1, entry_t=1000,
                entry_px=100.0, status="open")
    base.update(kw)
    return base


def test_journal_closed_trade_is_immutable():
    j = Journal()
    assert j.upsert_trade(_tr()) == "inserted"
    closed = _tr(status="closed", exit_t=2000, exit_px=101.0, why="stop", hold_h=4.0,
                 gross_bp=100.0, cost_bp=16.0, funding_bp=0.5, net_bp=83.5, mae_bp=-10.0, mfe_bp=120.0)
    assert j.upsert_trade(closed) == "updated"
    assert j.upsert_trade(dict(closed)) == "unchanged"
    try:
        j.upsert_trade(dict(closed, net_bp=50.0))
    except ImmutableTradeError:
        pass
    else:
        raise AssertionError("un trade chiuso non deve cambiare")
    t, x = j.closed_arrays("A", 1, "replay")
    assert list(t) == [1000] and list(x) == [83.5]


def test_journal_state_change_logged_once():
    j = Journal()
    assert j.set_state("A", 1, "CANDIDATA", ["avvio"]) is True
    assert j.set_state("A", 1, "CANDIDATA") is False
    assert j.set_state("A", 1, "IDONEA", ["ok"]) is True
    assert [e["detail"].split(":")[0] for e in j.events()] == ["None -> CANDIDATA", "CANDIDATA -> IDONEA"]


# ------------------------------------------------------------------- evidenze
def test_summarize_matches_manual_computation():
    rng = np.random.default_rng(3)
    n = 240
    t, x = spread_times(n, months=8), rng.normal(20.0, 400.0, n)
    s = ev.summarize(t, x)
    assert s.n == n and abs(s.mean - x.mean()) < 1e-9
    se = x.std(ddof=1) / math.sqrt(n)
    assert abs(s.t_iid - x.mean() / se) < 1e-9
    assert abs(s.ci_low - (x.mean() - 1.96 * se)) < 1e-9 and abs(s.ci_high - (x.mean() + 1.96 * se)) < 1e-9
    by = {}
    for ti, xi in zip(t, x):
        by.setdefault(ev.month_key(int(ti)), []).append(xi)
    m = np.array([np.mean(v) for v in by.values()])
    assert s.n_months == len(by)
    assert abs(s.t_month - m.mean() / (m.std(ddof=1) / math.sqrt(len(m)))) < 1e-9
    assert s.t_gate == min(s.t_iid, s.t_month)


def test_summarize_edge_cases():
    assert ev.summarize([], []) is None
    s = ev.summarize([1000], [5.0])
    assert s.n == 1 and math.isnan(s.t_iid) and math.isnan(s.t_gate)
    s2 = ev.summarize([1000, 2000, 3000], [5.0, 5.0, 5.0])  # varianza zero
    assert math.isnan(s2.t_iid)


def test_bonferroni_and_required_n():
    assert abs(ev.bonferroni_z(1) - 1.6449) < 1e-3
    assert abs(ev.bonferroni_z(10) - 2.5758) < 1e-3
    assert ev.bonferroni_z(3) > ev.bonferroni_z(1)
    assert ev.required_n(500, 100, 2.6) == 169
    assert ev.required_n(500, 50, 2.6) == 676
    assert ev.required_n(500, 30, 2.6) == 1878
    assert ev.required_n(500, 20, 2.6) == 4225


def test_net_bp_costs_and_funding():
    assert ev.net_bp(100.0, 1, 8.0, 16.0) == 100.0 - 16.0 - 1.0
    assert ev.net_bp(100.0, -1, 8.0, 16.0) == 84.0     # i short non pagano funding (come nel lab)
    assert ev.net_bp(-30.0, 1, 0.0, 16.0) == -46.0


def test_halves_positive():
    t = np.arange(10)
    assert ev.halves_positive(t, [1] * 10)
    assert not ev.halves_positive(t, [5] * 5 + [-1] * 5)
    assert not ev.halves_positive(t, [-1] * 5 + [5] * 5)
    assert ev.halves_positive(t[::-1], [1] * 10)  # l'ordine di inserimento non conta
    assert not ev.halves_positive([1], [1.0])


def test_gate_accepts_clear_edge_and_rejects_the_rest():
    gate, k = ev.Gate(), 3
    e = strong_evidence()
    assert ev.check_gate(e.summary, k, gate, e.halves_ok, e.excess)["pass"]
    null = strong_evidence(mean=0.0, seed=2)
    assert not ev.check_gate(null.summary, k, gate, null.halves_ok, null.excess)["pass"]
    few = strong_evidence(n=100, mean=200.0)
    assert not ev.check_gate(few.summary, k, gate, few.halves_ok, few.excess)["checks"]["trade"]
    t, x = spread_times(400, months=4), np.random.default_rng(4).normal(80, 300, 400)
    s = ev.summarize(t, x)
    assert not ev.check_gate(s, k, gate, True, 10.0)["checks"]["mesi"]
    assert not ev.check_gate(e.summary, k, gate, e.halves_ok, -1.0)["pass"]       # peggio del controllo
    assert not ev.check_gate(e.summary, k, gate, e.halves_ok, None)["pass"]       # controllo mancante
    assert not ev.check_gate(e.summary, k, gate, False, e.excess)["pass"]         # una meta' negativa
    assert not ev.check_gate(None, k, gate, False, None)["pass"]


def test_gate_false_positive_rate_with_many_rules_is_controlled():
    """10 regole senza alcun vantaggio (media netta 0, caso piu' favorevole al falso positivo):
    la probabilita' che almeno una superi la soglia deve restare vicina al 5%, non al 40%."""
    rng = np.random.default_rng(11)
    gate, k, sims, hits, naive_hits = ev.Gate(), 10, 300, 0, 0
    t = spread_times(400)
    for _ in range(sims):
        any_pass, any_naive = False, False
        for _ in range(k):
            x = rng.normal(0.0, 500.0, 400)
            s = ev.summarize(t, x)
            if ev.check_gate(s, k, gate, ev.halves_positive(t, x), 1.0)["pass"]:
                any_pass = True
            if s.t_gate >= 2.0 and ev.halves_positive(t, x):
                any_naive = True
        hits += any_pass
        naive_hits += any_naive
    assert hits / sims <= 0.10, hits / sims
    assert naive_hits > hits      # senza correzione i falsi positivi sarebbero molti di piu'


def test_futility_and_control_alarm():
    gate = ev.Gate()
    t, x = spread_times(150), np.random.default_rng(5).normal(-60, 300, 150)
    assert ev.futility(ev.summarize(t, x), gate)
    assert not ev.futility(ev.summarize(t[:50], x[:50]), gate)       # troppo pochi trade
    assert not ev.futility(None, gate)
    e = strong_evidence()
    assert ev.control_alarm([e.summary], 3, gate)                    # un "controllo" con vantaggio forte
    null = strong_evidence(mean=-16.0, seed=9)
    assert not ev.control_alarm([null.summary, None], 3, gate)
    # vantaggio "solo" sopra la soglia di promozione (t ~ 2,5): non basta per l'allarme
    t = spread_times(400)
    x = np.random.default_rng(12).normal(0, 1, 400)
    x = (x - x.mean()) / x.std(ddof=1) * 300.0 + 37.5            # t_iid = 37,5 / (300/20) = 2,5 esatto
    mild = ev.summarize(t, x)
    assert abs(mild.t_iid - 2.5) < 1e-9
    assert not ev.control_alarm([mild], 3, gate)


def test_control_alarm_false_alarm_rate_is_tiny():
    rng = np.random.default_rng(21)
    gate, t, hits = ev.Gate(), spread_times(430), 0
    for _ in range(1000):
        hits += ev.control_alarm([ev.summarize(t, rng.normal(-16.0, 200.0, 430))], 3, gate)
    assert hits <= 5, hits       # attesi ~1 su 1000 (p ~ 0,13% a z=3)


# ------------------------------------------------------------------ allocatore
def test_allocator_transitions():
    gate, k = ev.Gate(), 3
    good, null = strong_evidence(), strong_evidence(mean=0.0, seed=2)
    out = alloc.decide({"A": alloc.State.CANDIDATA, "B": alloc.State.CANDIDATA},
                       {"A": good, "B": null}, k, gate)
    assert out["A"][0] == alloc.State.IDONEA and out["B"][0] == alloc.State.CANDIDATA
    assert "non passa" in out["B"][1][0]
    # idonea ma live spento: resta idonea
    assert alloc.decide({"A": alloc.State.IDONEA}, {"A": good}, k, gate)["A"][0] == alloc.State.IDONEA
    # una regola idonea che non supera piu' la soglia torna candidata
    assert alloc.decide({"B": alloc.State.IDONEA}, {"B": null}, k, gate)["B"][0] == alloc.State.CANDIDATA


def test_allocator_live_promotion_limits_and_alarm():
    gate, k = ev.Gate(max_live=2), 3
    evs = {r: strong_evidence(mean=m, seed=s) for r, m, s in (("A", 150, 1), ("B", 120, 2), ("C", 90, 3))}
    states = {r: alloc.State.IDONEA for r in evs}
    out = alloc.decide(states, evs, k, gate, live_enabled=True)
    live = sorted(r for r, (st, _) in out.items() if st == alloc.State.LIVE_PICCOLO)
    assert live == ["A", "B"]                                         # le due con t piu' alto
    assert out["C"][0] == alloc.State.IDONEA
    out2 = alloc.decide(states, evs, k, gate, live_enabled=True, alarm=True)
    assert all(st == alloc.State.IDONEA for st, _ in out2.values())          # congelato: nessuna promozione
    assert all("allarme" in why[0] for _, why in out2.values())
    out3 = alloc.decide(states, evs, k, gate, live_enabled=False)
    assert all(st == alloc.State.IDONEA for st, _ in out3.values())
    # una regola gia' live NON viene retrocessa da un allarme (potrebbe essere falso): resta ferma
    out4 = alloc.decide({"A": alloc.State.LIVE_PICCOLO}, {"A": evs["A"]}, k, gate, live_enabled=True, alarm=True)
    assert out4["A"][0] == alloc.State.LIVE_PICCOLO


def test_allocator_retire_demote_and_terminal():
    gate, k = ev.Gate(), 3
    t, x = spread_times(150), np.random.default_rng(5).normal(-60, 300, 150)
    loser = alloc.RuleEvidence(ev.summarize(t, x), False, -5.0)
    out = alloc.decide({"L": alloc.State.CANDIDATA}, {"L": loser}, k, gate)
    assert out["L"][0] == alloc.State.RITIRATA
    # terminale: anche con evidenza ottima non risale
    out = alloc.decide({"L": alloc.State.RITIRATA}, {"L": strong_evidence()}, k, gate)
    assert out["L"][0] == alloc.State.RITIRATA
    # retrocessione in live
    bad_live = dataclasses.replace(
        strong_evidence(), live=ev.summarize(spread_times(60), np.random.default_rng(6).normal(-80, 200, 60)))
    out = alloc.decide({"A": alloc.State.LIVE_PICCOLO}, {"A": bad_live}, k, gate, live_enabled=True)
    assert out["A"][0] == alloc.State.RETROCESSA
    ok_live = dataclasses.replace(
        strong_evidence(), live=ev.summarize(spread_times(60), np.random.default_rng(6).normal(80, 200, 60)))
    out = alloc.decide({"A": alloc.State.LIVE_PICCOLO}, {"A": ok_live}, k, gate, live_enabled=True)
    assert out["A"][0] == alloc.State.LIVE_PICCOLO


# ---------------------------------------------------------------------- replay
def test_compute_trades_costs_match_naive_recomputation():
    b15 = random_walk()
    frames = replay.frames_for(b15)
    for name, sym_rule in (("S1_donchian_4h", None), ("S2_donchian_1h", None)):
        r = rules.Rule("R", name, ("X",))
        s = r.strat()
        raw = sl.run_strategy(frames[s.tf], s.build(frames), s.cfg, r.tf_ms)
        recs = replay.compute_trades(r, "X", frames)
        assert len(recs) == len(raw) and len(raw) > 5
        n_open = 0
        for rec, tr in zip(recs, raw):
            assert rec["entry_t"] == tr["t"] and rec["side"] == tr["side"] and rec["entry_px"] == tr["entry"]
            if rec["status"] == "open":
                n_open += 1
                assert tr["why"] == "end"
                continue
            fund = (tr["hold_h"] / 8.0) if tr["side"] == 1 else 0.0       # 1 bp / 8h
            assert abs(rec["net_bp"] - (tr["gross"] - 16.0 - fund)) < 1e-9
            assert rec["exit_t"] >= rec["entry_t"]
            assert rec["mae_bp"] <= rec["gross_bp"] + 1e-6      # l'esito sta dentro l'escursione
            assert rec["gross_bp"] <= rec["mfe_bp"] + 1e-6
        assert n_open <= 1


def test_mae_mfe_on_crafted_path():
    o = [100, 100, 101, 103, 104]
    h = [100, 102, 105, 104, 106]
    lo = [100, 99, 100, 97, 103]
    c = [100, 101, 104, 98, 105]
    b = sl.Bars(np.arange(5, dtype=np.int64) * sl.H1, *(np.array(a, float) for a in (o, h, lo, c)),
                np.ones(5))
    mae, mfe = replay._mae_mfe(b, 1, 3, 1, "stop", 100.0)           # long da barra 1 a 3
    assert abs(mae - (97 / 100 - 1) * 1e4) < 1e-9 and abs(mfe - (105 / 100 - 1) * 1e4) < 1e-9
    mae, mfe = replay._mae_mfe(b, 1, 3, -1, "stop", 100.0)          # stesso percorso, short
    assert abs(mae - (1 - 105 / 100) * 1e4) < 1e-9 and abs(mfe - (1 - 97 / 100) * 1e4) < 1e-9
    mae, mfe = replay._mae_mfe(b, 1, 3, 1, "donchian", 100.0)       # la barra 3 conta solo come apertura
    assert abs(mae - (99 / 100 - 1) * 1e4) < 1e-9 and abs(mfe - (105 / 100 - 1) * 1e4) < 1e-9


def _prefix_frames(b15, tf_ms, bar_t):
    return replay.frames_for(b15.head(int((bar_t + tf_ms) // sl.M15)))


def _check_prefix_stability(name, step_bars):
    b15 = random_walk()
    r = rules.Rule("R", name, ("X",))
    full = replay.compute_trades(r, "X", replay.frames_for(b15))
    final_closed = {x["entry_t"]: x for x in full if x["status"] == "closed"}
    j = Journal()
    seen_closed = set()
    for k in range(step_bars, len(b15) + 1, step_bars):
        frames = replay.frames_for(b15.head(k))
        replay.sync_journal(j, r, "X", frames)           # solleva se un trade chiuso cambia
        for row in j.all_trades("R", 1, "replay"):
            if row["status"] == "closed":
                seen_closed.add(row["entry_t"])
                assert row["entry_t"] in final_closed       # mai un trade chiuso poi sparito
    replay.sync_journal(j, r, "X", replay.frames_for(b15))
    rows = {x["entry_t"]: x for x in j.all_trades("R", 1, "replay")}
    assert set(rows) == {x["entry_t"] for x in full}
    for t, x in final_closed.items():
        assert abs(rows[t]["net_bp"] - x["net_bp"]) < 1e-9 and rows[t]["status"] == "closed"
    assert len(seen_closed) > 0
    return len(full)


def test_prefix_stability_s1_4h():
    assert _check_prefix_stability("S1_donchian_4h", 64) >= 5


def test_prefix_stability_s2_1h():
    assert _check_prefix_stability("S2_donchian_1h", 64) >= 5


def _pending_matches_lab(name):
    b15 = random_walk()
    r = rules.Rule("R", name, ("X",))
    s = r.strat()
    frames = replay.frames_for(b15)
    b, sig = frames[s.tf], s.build(frames)
    raw = sl.run_strategy(b, sig, s.cfg, r.tf_ms)
    entries = {tr["e"]: tr for tr in raw}
    ends = [(tr["e"], tr["e"] + int(round(tr["hold_h"] * sl.H1 / r.tf_ms)) - 1) for tr in raw]
    checked = 0
    for i in np.flatnonzero(sig.side != 0):
        if i + 1 >= len(b):
            continue
        busy = any(e0 <= i < j0 for e0, j0 in ends)
        p = replay.pending_signal(r, _prefix_frames(b15, r.tf_ms, b.t[i]), busy=busy)
        lab = entries.get(i + 1)
        assert (p is not None) == (lab is not None), (name, int(i), busy)
        if lab is not None:
            assert p["side"] == lab["side"] and p["enter_at_t"] == lab["t"]
            assert abs(p["stop_dist"] - s.cfg.stop_mult * sig.atr[i]) < 1e-9
            checked += 1
    assert checked >= 5
    # con una posizione aperta non si genera mai un nuovo ingresso
    i = int(next(iter(np.flatnonzero(sig.side != 0))))
    assert replay.pending_signal(r, _prefix_frames(b15, r.tf_ms, b.t[i]), busy=True) is None


def test_pending_signal_matches_lab_entries_s1():
    _pending_matches_lab("S1_donchian_4h")


def test_pending_signal_matches_lab_entries_s2():
    _pending_matches_lab("S2_donchian_1h")


# ----------------------------------------------------------- controllo e pool
def test_control_is_deterministic_and_loses_about_the_costs():
    b15 = random_walk()
    frames = replay.frames_for(b15)
    base = rules.Rule("R_S2", "S2_donchian_1h", ("X",))
    ctl = rules.Rule("CTL_S2", "S2_donchian_1h", ("X",), kind="control", base_rule="R_S2")
    a, b = replay.control_records(ctl, "X", frames), replay.control_records(ctl, "X", frames)
    assert [x["entry_t"] for x in a] == [x["entry_t"] for x in b] and len(a) > 30
    assert len({x["entry_t"] for x in a}) == len(a)
    s = ev.summarize([x["entry_t"] for x in a], [x["net_bp"] for x in a])
    assert s.mean < 0 and s.t_gate < 2.0          # su un random walk senza vantaggio non guadagna
    assert all(x["rule_id"] == "CTL_S2" for x in a)
    assert len(replay.compute_trades(base, "X", frames)) > 5


def test_control_prefix_stability_even_with_colliding_entries():
    """Due ingressi casuali sulla stessa candela non devono scambiarsi quando arrivano nuovi dati.
    Si provano piu' semi (l'id della regola); con trade vicini le collisioni sono frequenti."""
    b15 = random_walk(seed=7)
    full_frames = replay.frames_for(b15)
    collisions = 0
    for rid in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"):
        ctl = rules.Rule(rid, "S2_donchian_1h", ("X",), kind="control", base_rule="R")
        full = replay.control_records(ctl, "X", full_frames)
        j = Journal()
        for k in range(256, len(b15) + 1, 256):
            replay.sync_journal(j, ctl, "X", replay.frames_for(b15.head(k)))   # solleva se qualcosa cambia
        replay.sync_journal(j, ctl, "X", full_frames)
        rows = {x["entry_t"]: x for x in j.all_trades(rid, 1, "replay")}
        assert set(rows) == {x["entry_t"] for x in full}, rid
        for x in full:
            assert rows[x["entry_t"]]["side"] == x["side"] and abs(rows[x["entry_t"]]["net_bp"] - x["net_bp"]) < 1e-9
        raw = sl.run_strategy(full_frames["1h"], ctl.strat().build(full_frames), ctl.strat().cfg, sl.H1)
        collisions += len(raw) * 3 - len(full)       # draw scartati (collisioni e fuori range)
    assert collisions > 0


def _fill(j, rule_id, n, mean, sd, seed, version=1):
    rng = np.random.default_rng(seed)
    for i, (t, x) in enumerate(zip(spread_times(n), rng.normal(mean, sd, n))):
        j.upsert_trade(dict(rule_id=rule_id, version=version, venue="replay", symbol="X", side=1,
                            entry_t=int(t), entry_px=100.0, status="closed", exit_t=int(t) + 1,
                            exit_px=101.0, why="stop", hold_h=1.0, gross_bp=x + 16.0, cost_bp=16.0,
                            funding_bp=0.0, net_bp=float(x), mae_bp=-1.0, mfe_bp=1.0))


def test_pool_end_to_end_promotion_and_idempotence():
    rs = rules.initial_rules()
    j = Journal()
    _fill(j, "R_S1_majors", 400, 90.0, 300.0, 1)
    _fill(j, "CTL_S1_majors", 900, -16.0, 300.0, 2)
    _fill(j, "R_S2_majors", 400, -20.0, 300.0, 3)
    _fill(j, "CTL_S2_majors", 900, -16.0, 300.0, 4)
    r1 = pool.evaluate_pool(j, rs)
    assert r1["decisions"]["R_S1_majors"][0] == alloc.State.IDONEA
    assert r1["decisions"]["R_S2_majors"][0] == alloc.State.CANDIDATA
    assert r1["decisions"]["R_S2_top10"][0] == alloc.State.CANDIDATA        # nessun dato: resta ferma
    assert not r1["alarm"] and r1["k"] == 3
    assert pool.evaluate_pool(j, rs)["changed"] == []                        # idempotente
    r3 = pool.evaluate_pool(j, rs, live_enabled=True)
    assert r3["decisions"]["R_S1_majors"][0] == alloc.State.LIVE_PICCOLO
    assert j.get_state("R_S1_majors", 1) == "LIVE_PICCOLO"


def test_pool_alarm_when_control_shows_an_edge():
    rs = rules.initial_rules()
    j = Journal()
    _fill(j, "R_S1_majors", 400, 90.0, 300.0, 1)
    _fill(j, "CTL_S1_majors", 900, 90.0, 300.0, 2)       # un controllo che "guadagna": errore di sistema
    r = pool.evaluate_pool(j, rs)
    assert r["alarm"]
    assert r["decisions"]["R_S1_majors"][0] == alloc.State.CANDIDATA


def test_pool_on_synthetic_random_walk_never_promotes():
    rs = [r for r in rules.initial_rules() if r.rule_id.endswith("S2_majors")]
    rs = [dataclasses.replace(r, symbols=("X", "Y")) for r in rs]
    j = Journal()
    for sym, seed in (("X", 7), ("Y", 8)):
        frames = replay.frames_for(random_walk(seed=seed))
        for r in rs:
            replay.sync_journal(j, r, sym, frames)
    r = pool.evaluate_pool(j, rs)
    assert all(st != alloc.State.IDONEA and st != alloc.State.LIVE_PICCOLO for st, _ in r["decisions"].values())
    assert not r["alarm"]
