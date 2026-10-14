"""Test del runner in avanti: scambio finto, dati sintetici, nessuna rete."""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import strategy_lab as sl  # noqa: E402
from rule_pool import cli, replay, rules, runner  # noqa: E402
from rule_pool import evidence as ev  # noqa: E402
from rule_pool.journal import Journal  # noqa: E402

M15 = sl.M15
SETTLE = 20_000          # a "now" la barra i risulta chiusa da 20 secondi


def random_walk(n=20000, seed=7):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    o = np.r_[100.0, c[:-1]]
    spread = np.abs(rng.normal(0, 0.0015, n))
    return sl.Bars(np.arange(n, dtype=np.int64) * M15, o, np.maximum(o, c) * (1 + spread),
                   np.minimum(o, c) * (1 - spread), c, rng.lognormal(0, 0.5, n))


class FakeExchange:
    """Serve le candele fino a `now_ms` INCLUSA la candela in formazione, a pagine da 200 (come BitGet)."""

    def __init__(self, series: dict, page=200):
        self.series, self.page, self.now_ms, self.calls = series, page, 0, 0

    def now_after_close_of(self, i: int) -> int:
        self.now_ms = (i + 1) * M15 + SETTLE
        return self.now_ms

    def fetch(self, symbol, since_ms):
        self.calls += 1
        if symbol == "BAD":
            raise RuntimeError("rete giu'")
        b = self.series.get(symbol)
        if b is None:
            return []
        idx = np.flatnonzero((b.t >= since_ms) & (b.t <= self.now_ms))[:self.page]
        return [[int(b.t[i]), b.o[i], b.h[i], b.l[i], b.c[i], b.v[i]] for i in idx]


def two_rules(symbol="X"):
    base = rules.Rule("R_S2", "S2_donchian_1h", (symbol,))
    ctl = rules.Rule("CTL_S2", "S2_donchian_1h", (symbol,), kind="control", base_rule="R_S2")
    return [base, ctl]


# ------------------------------------------------------------------- archivio
def test_store_keeps_only_closed_bars_and_appends():
    b = random_walk(6000)
    ex = FakeExchange({"X": b})
    with tempfile.TemporaryDirectory() as d:
        store = runner.CandleStore(d)
        ex.now_ms = 5000 * M15 + 7 * 60_000                 # la barra 5000 e' in formazione
        assert store.update("X", ex.fetch, ex.now_ms, 0) == 5000
        arr = store.load("X")
        assert len(arr) == 5000 and arr[-1, 0] == 4999 * M15
        ex.now_after_close_of(5009)
        assert store.update("X", ex.fetch, ex.now_ms, 0) == 10
        assert store.update("X", ex.fetch, ex.now_ms, 0) == 0          # idempotente
        arr2 = runner.CandleStore(d).load("X")                          # persiste fra istanze
        assert len(arr2) == 5010 and np.array_equal(arr2[:, 0], b.t[:5010])
        assert np.allclose(arr2[:, 4], b.c[:5010]) and np.all(np.diff(arr2[:, 0]) == M15)
        assert not [f for f in os.listdir(d) if ".tmp" in f]            # scrittura atomica


def test_store_ignores_overlapping_and_future_rows():
    b = random_walk(3000)

    def messy(symbol, since):          # righe sovrapposte, duplicate e dal futuro
        rows = [[int(b.t[i]), b.o[i], b.h[i], b.l[i], b.c[i], b.v[i]]
                for i in range(max(0, since // M15 - 3), min(len(b), since // M15 + 40))]
        return rows + rows[:2] + [[int(b.t[2999]) + 10 * M15, 1, 1, 1, 1, 1]]

    with tempfile.TemporaryDirectory() as d:
        store = runner.CandleStore(d)
        now = 2000 * M15 + SETTLE
        store.update("X", messy, now, 0)
        arr = store.load("X")
        assert np.array_equal(arr[:, 0], b.t[:len(arr)]) and arr[-1, 0] == runner.last_closed_open(now)
        assert len(set(arr[:, 0])) == len(arr)


# --------------------------------------------------------------- equivalenza
def _run_forward(series, rules_, start_i, end_i, step, back=None):
    ex = FakeExchange(series)
    j = Journal()
    msgs = []
    with tempfile.TemporaryDirectory() as d:
        store = runner.CandleStore(d)
        if back is not None:
            j.set_meta("backfill_from_ms", str(back))
        res = None
        for i in range(start_i, end_i, step):
            res = runner.run_once(j, rules_, store, ex.fetch, ex.now_after_close_of(i), notify=msgs.append)
    return j, res, msgs


def test_forward_run_matches_batch_when_archive_starts_with_the_series():
    b = random_walk(20000, seed=7)
    rs = two_rules()
    j, res, msgs = _run_forward({"X": b}, rs, 16000, 20000, 64)
    fwd = int(j.get_meta("forward_from_ms"))
    full = replay.frames_for(b)
    for rule, venue_fn in ((rs[0], replay.compute_trades), (rs[1], replay.control_records)):
        batch = [x for x in venue_fn(rule, "X", full)
                 if x["status"] == "closed" and x["entry_t"] >= fwd]
        # i trade chiusi nel giornale devono essere quelli del calcolo su tutta la serie
        rows = {x["entry_t"]: x for x in j.all_trades(rule.rule_id, 1, "paper") if x["status"] == "closed"}
        # il runner vede i dati solo fino all'ultimo giro; un trade si registra chiuso quando la sua
        # barra di uscita e' completa (anche per l'uscita Donchian, decisa a barra precedente chiusa)
        last_t = (list(range(16000, 20000, 64))[-1] + 1) * M15
        expect = {x["entry_t"]: x for x in batch if x["exit_t"] + rule.tf_ms <= last_t}
        assert expect, rule.rule_id
        for t, x in expect.items():
            assert t in rows, (rule.rule_id, t)
            assert rows[t]["side"] == x["side"] and abs(rows[t]["net_bp"] - x["net_bp"]) < 1e-9
        assert all(t >= fwd for t in rows)                       # nulla prima dell'attivazione
        assert set(rows) <= {x["entry_t"] for x in batch}         # niente trade che il batch non ha
    assert msgs == [] and res["errors"] == {} and not res["alarm"]


def test_forward_run_with_later_archive_start_matches_most_trades():
    """Informativo: l'archivio in produzione parte ~12 mesi fa, non dal 2019. Gli indicatori
    ricorsivi (EMA/RMA) hanno un residuo di avvio: qui si misura quante decisioni cambiano."""
    b = random_walk(40000, seed=11)
    rs = two_rules()[:1]
    j, _, _ = _run_forward({"X": b}, rs, 34000, 40000, 64, back=int(b.t[4000]))
    fwd = int(j.get_meta("forward_from_ms"))
    batch = {x["entry_t"]: x for x in replay.compute_trades(rs[0], "X", replay.frames_for(b))
             if x["status"] == "closed" and x["entry_t"] >= fwd}
    rows = {x["entry_t"]: x for x in j.all_trades("R_S2", 1, "paper") if x["status"] == "closed"}
    common = [t for t in rows if t in batch and rows[t]["side"] == batch[t]["side"]]
    frac = len(common) / max(1, len(rows))
    print(f"   [info] ingressi identici con archivio piu' corto: {len(common)}/{len(rows)} ({100 * frac:.0f}%)")
    assert len(rows) >= 5 and frac >= 0.9, frac
    diffs = [abs(rows[t]["net_bp"] - batch[t]["net_bp"]) for t in common if t in batch]
    assert np.median(diffs) < 1.0, np.median(diffs)


# ------------------------------------------------------------ errori e dati
def test_one_symbol_failing_does_not_block_the_others_and_stale_data_is_flagged():
    b = random_walk(20000)
    ex = FakeExchange({"X": b})
    rs = [rules.Rule("R_S2", "S2_donchian_1h", ("X", "BAD"))]
    j = Journal()
    with tempfile.TemporaryDirectory() as d:
        store = runner.CandleStore(d)
        res = runner.run_once(j, rs, store, ex.fetch, ex.now_after_close_of(19000))
        assert "BAD" in res["errors"] and "X" not in res["errors"]
        assert res["fresh"]["X"] == 19000 * M15
        # l'exchange smette di dare dati nuovi (ex.now_ms resta fermo) mentre passano 5 ore: "dati vecchi"
        res = runner.run_once(j, rs, store, ex.fetch, ex.now_ms + 5 * 3_600_000)
        assert res["errors"]["X"] == "dati vecchi"


def test_short_history_gives_no_signals():
    b = random_walk(8000)
    ex = FakeExchange({"X": b})
    j = Journal()
    with tempfile.TemporaryDirectory() as d:
        res = runner.run_once(j, two_rules(), runner.CandleStore(d), ex.fetch, ex.now_after_close_of(7999))
    assert "storico insufficiente" in res["errors"]["X"]
    assert j.all_trades("R_S2", 1, "paper") == []


# ---------------------------------------------------------------- notifiche
def _fill_paper(j, rule_id, n, mean, sd, seed, symbol="Z"):
    rng = np.random.default_rng(seed)
    start = 1_600_000_000_000
    for t, x in zip((start + np.linspace(0, 360 * 86_400_000, n, endpoint=False)).astype(np.int64),
                    rng.normal(mean, sd, n)):
        j.upsert_trade(dict(rule_id=rule_id, version=1, venue="paper", symbol=symbol, side=1, entry_t=int(t),
                            entry_px=100.0, status="closed", exit_t=int(t) + 1, exit_px=101.0, why="stop",
                            hold_h=1.0, gross_bp=float(x) + 16.0, cost_bp=16.0, funding_bp=0.0,
                            net_bp=float(x), mae_bp=-1.0, mfe_bp=1.0))


def test_notifications_only_on_real_transitions_and_alarm_changes():
    rs = [rules.Rule("R_A", "S2_donchian_1h", ("Z",)),
          rules.Rule("CTL_A", "S2_donchian_1h", ("Z",), kind="control", base_rule="R_A")]
    ex, j, msgs = FakeExchange({}), Journal(), []
    with tempfile.TemporaryDirectory() as d:
        store = runner.CandleStore(d)
        now = 100 * M15
        runner.run_once(j, rs, store, ex.fetch, now, gate=ev.Gate(), notify=msgs.append)
        assert msgs == []                                         # primo avvio: nessun messaggio
        _fill_paper(j, "R_A", 400, 90.0, 300.0, 1)
        _fill_paper(j, "CTL_A", 900, -16.0, 300.0, 2)
        runner.run_once(j, rs, store, ex.fetch, now, notify=msgs.append)
        assert len(msgs) == 1 and "R_A CANDIDATA -> IDONEA" in msgs[0]
        runner.run_once(j, rs, store, ex.fetch, now, notify=msgs.append)
        assert len(msgs) == 1                                     # nessuna ripetizione
        _fill_paper(j, "CTL_A", 900, 120.0, 300.0, 3, symbol="Z2")             # un controllo con vantaggio enorme
        runner.run_once(j, rs, store, ex.fetch, now, notify=msgs.append)
        assert len(msgs) == 2 and "ALLARME" in msgs[1]
        runner.run_once(j, rs, store, ex.fetch, now, notify=msgs.append)
        assert len(msgs) == 2


def test_report_contains_state_progress_and_control():
    rs = [rules.Rule("R_A", "S2_donchian_1h", ("Z",)),
          rules.Rule("CTL_A", "S2_donchian_1h", ("Z",), kind="control", base_rule="R_A")]
    ex, j = FakeExchange({}), Journal()
    with tempfile.TemporaryDirectory() as d:
        res = runner.run_once(j, rs, runner.CandleStore(d), ex.fetch, 100 * M15)
        txt0 = runner.render_report(j, rs, res)
        assert "R_A: CANDIDATA, nessun trade chiuso ancora" in txt0 and "K=1" in txt0
        _fill_paper(j, "R_A", 120, 5.0, 300.0, 4)
        _fill_paper(j, "CTL_A", 300, -16.0, 300.0, 5)
        txt = runner.render_report(j, rs, res)
        assert "120/300 trade chiusi" in txt and "controllo" in txt and "mesi" in txt
        assert "Allarme controlli: no" in txt and "Z: storico insufficiente" in txt


# ---------------------------------------------------------------------- cli
def test_next_run_is_the_next_quarter_hour_plus_margin():
    base = 1_700_000_100_000 // M15 * M15
    assert cli.next_run_ms(base + 3 * 60_000) == base + M15 + cli.RUN_OFFSET_MS
    assert cli.next_run_ms(base + cli.RUN_OFFSET_MS) == base + M15 + cli.RUN_OFFSET_MS
    assert cli.next_run_ms(base + M15 - 1) == base + M15 + cli.RUN_OFFSET_MS
    assert cli.next_run_ms(base + M15 + 1) == base + 2 * M15 + cli.RUN_OFFSET_MS


def test_iteration_survives_errors_and_alerts_once_on_changed_params():
    def boom(symbol, since):
        raise AssertionError("non deve scaricare: i parametri sono cambiati")

    with tempfile.TemporaryDirectory() as d:
        j = cli.open_journal(d)
        original = rules.initial_rules()[0]
        import dataclasses
        j.register_rule(dataclasses.replace(original, symbols=rules.TOP10 + ("EXTRA/USDT:USDT",)))
        msgs = []
        assert cli.iteration(j, d, msgs.append, fetch=boom, now_ms=10 ** 12) is None
        assert cli.iteration(j, d, msgs.append, fetch=boom, now_ms=10 ** 12) is None
        assert len(msgs) == 1 and "parametri cambiati" in msgs[0]
        # un errore qualsiasi non ferma il giro
        j2 = cli.open_journal(tempfile.mkdtemp())
        res = cli.iteration(j2, d, None, fetch=lambda s, since: (_ for _ in ()).throw(KeyError("x")),
                            now_ms=10 ** 12)
        assert res is not None and len(res["errors"]) == 10      # errore di rete: il giro finisce, segnalando i simboli


def test_health_tracks_last_successful_round_and_startup_grace():
    j = Journal()
    now = 10 ** 12
    assert cli.health(j, now)[0] is False                       # mai partito, nessun giro
    j.set_meta("started_ms", str(now - 10 * 60_000))
    assert cli.health(j, now)[0] is True                        # appena partito: sta scaricando
    assert cli.health(j, now + 2 * 3_600_000)[0] is False       # partito da ore senza mai riuscire
    j.set_meta("last_ok_ms", str(now))
    assert cli.health(j, now + 30 * 60_000)[0] is True
    assert cli.health(j, now + 50 * 60_000)[0] is False         # troppo vecchio


def test_iteration_records_last_ok_only_on_success():
    with tempfile.TemporaryDirectory() as d:
        j = cli.open_journal(d)
        res = cli.iteration(j, d, None, fetch=lambda s, since: [], now_ms=10 ** 12)
        assert res is not None and j.get_meta("last_ok_ms") == str(10 ** 12)
        j2 = cli.open_journal(tempfile.mkdtemp())
        import dataclasses
        j2.register_rule(dataclasses.replace(rules.initial_rules()[0], symbols=("Q/USDT:USDT",)))
        assert cli.iteration(j2, d, None, fetch=lambda s, since: [], now_ms=10 ** 12) is None
        assert j2.get_meta("last_ok_ms") is None


def test_store_skips_an_exchange_data_hole_in_the_middle_of_history():
    b = random_walk(3000)
    hole = (1000, 1900)                        # ~9 giorni di barre che l'exchange non serve

    class Holey(FakeExchange):
        def fetch(self, symbol, since_ms):
            return [r for r in super().fetch(symbol, since_ms)
                    if not (hole[0] * M15 <= r[0] < hole[1] * M15)]

    ex = Holey({"X": b})
    now = ex.now_after_close_of(2999)
    with tempfile.TemporaryDirectory() as d:
        store = runner.CandleStore(d)
        added = store.update("X", ex.fetch, now, 0)
        arr = store.load("X")
        assert int(arr[-1, 0]) == 2999 * M15 - M15 or int(arr[-1, 0]) == runner.last_closed_open(now)
        assert added == len(arr) == 3000 - (hole[1] - hole[0]) - 1 or added == len(arr)
        assert store.skipped > 0
        assert not np.any((arr[:, 0] >= hole[0] * M15) & (arr[:, 0] < hole[1] * M15))


def test_store_stops_at_the_head_without_skipping_when_nothing_new():
    b = random_walk(500)
    ex = FakeExchange({"X": b})
    now = ex.now_after_close_of(499)
    with tempfile.TemporaryDirectory() as d:
        store = runner.CandleStore(d)
        store.update("X", ex.fetch, now, 0)
        calls = ex.calls
        assert store.update("X", ex.fetch, now, 0) == 0
        assert ex.calls - calls <= 2
        assert store.skipped == 0


def test_v1_benchmark_reads_a_copy_and_computes_net_bp_on_notional():
    import sqlite3
    from rule_pool import v1_benchmark as v1
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "bot.db")
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE trades (entry_price REAL, quantity REAL, pnl REAL, status TEXT, close_time TEXT)")
        con.executemany("INSERT INTO trades VALUES (?,?,?,?,?)", [
            (100.0, 2.0, 2.0, "closed", "2026-10-01 10:00:00"),      # +100 bp
            (100.0, 1.0, -0.5, "closed", "2026-10-02 10:00:00"),     # -50 bp
            (100.0, 1.0, 9.0, "open", None),                         # ignorato
        ])
        con.commit()
        con.close()
        before = open(p, "rb").read()
        t, x = v1.read_v1(p)
        assert list(np.round(x, 6)) == [100.0, -50.0]
        assert open(p, "rb").read() == before                        # originale intatto
        assert "V1" in v1.line(p)
    assert v1.read_v1("/non/esiste.db") is None
    assert "non leggibile" in v1.line("/non/esiste.db")
