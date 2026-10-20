"""Prove del Turbo Scalp in ombra: segnale, ingresso alla barra dopo, stop prima dell'obiettivo, costi,
uscita a tempo, tetto di posizioni, pausa, buchi nei dati, stato e registro."""
import json
import os
import tempfile
import unittest

from desk.turbo_scalp import report, runner, strategy
from desk.turbo_scalp.strategy import Config

BAR = 300_000
T = 1_800_000_000_000 // BAR * BAR


def uptrend(n=140, start=T, step=0.0008):
    """Trend rialzista regolare: ogni barra +0,08%; minimo appena sotto l'apertura."""
    bars, px = [], 100.0
    for i in range(n):
        o = px
        c = px * (1 + step)
        bars.append((start + i * BAR, o, c * 1.0003, o * 0.9997, c))
        px = c
    return bars


def with_pullback_bounce(bars, cfg=Config()):
    """Aggiunge una barra che scende fino all'EMA20 e richiude sopra, verde."""
    closes = [b[4] for b in bars]
    f = strategy.ema_last(closes, cfg.ema_fast)[-1]
    last = bars[-1][4]
    t = bars[-1][0] + BAR
    o = (f + last) / 2
    return bars + [(t, o, last * 1.001, f * 0.999, last * 1.0005)]


class Signal(unittest.TestCase):
    def test_long_bounce_signal(self):
        b = with_pullback_bounce(uptrend())
        sig = strategy.signal(b, Config())
        self.assertIsNotNone(sig)
        self.assertEqual(sig["side"], 1)
        self.assertGreaterEqual(sig["dist"], 0.004)

    def test_no_signal_without_touch(self):
        self.assertIsNone(strategy.signal(uptrend(), Config()))

    def test_short_mirror(self):
        mirrored = [(t, 1e4 / o, 1e4 / lo, 1e4 / h, 1e4 / c) for t, o, h, lo, c in with_pullback_bounce(uptrend())]
        sig = strategy.signal(mirrored, Config())
        self.assertIsNotNone(sig)
        self.assertEqual(sig["side"], -1)

    def test_too_wide_stop_is_skipped(self):
        cfg = Config(sl_max=0.003)
        self.assertIsNone(strategy.signal(with_pullback_bounce(uptrend()), cfg))

    def test_short_or_irregular_history_gives_no_signal(self):
        b = with_pullback_bounce(uptrend())
        self.assertIsNone(strategy.signal(b[-50:], Config()))
        holed = b[:60] + [(t + BAR, o, h, lo, c) for t, o, h, lo, c in b[60:]]
        self.assertIsNone(strategy.signal(holed, Config()))


def run_steps(seq, cfg=Config(), sym="BTC"):
    """Simula il processo: il primo step vede la storia, poi una barra nuova alla volta."""
    st, events = strategy.new_state(cfg), []
    st, _ = strategy.step(st, {sym: seq[:130]}, cfg)
    for i in range(130, len(seq)):
        st, ev = strategy.step(st, {sym: seq[: i + 1]}, cfg)
        events += ev
    return st, events


def signal_then(after):
    """Storia fino al segnale (indice 140) e poi le barre `after` (o, h, l, c relative al prezzo di chiusura)."""
    base = with_pullback_bounce(uptrend())
    last_t, last_c = base[-1][0], base[-1][4]
    extra = [(last_t + (i + 1) * BAR, last_c * o, last_c * h, last_c * lo, last_c * c)
             for i, (o, h, lo, c) in enumerate(after)]
    return base + extra, last_c


class Simulation(unittest.TestCase):
    def test_first_contact_does_not_rebuild_the_past(self):
        cfg = Config()
        st, ev = strategy.step(strategy.new_state(cfg), {"BTC": with_pullback_bounce(uptrend())}, cfg)
        self.assertEqual(ev, [])
        self.assertEqual(st["open"], {})

    def test_entry_at_next_open_with_slippage(self):
        seq, c = signal_then([(1.0, 1.001, 0.999, 1.0)])
        st, ev = run_steps(seq)
        kinds = [e["ev"] for e in ev]
        self.assertEqual(kinds[:2], ["signal", "fill"])
        fill = ev[1]
        self.assertAlmostEqual(fill["entry"], c * (1 + 2e-4), places=6)
        self.assertIn("BTC", st["open"])

    def test_stop_wins_over_target_in_same_bar(self):
        seq, c = signal_then([(1.0, 1.0, 1.0, 1.0), (1.0, 1.05, 0.95, 1.0)])
        st, ev = run_steps(seq)
        ex = [e for e in ev if e["ev"] == "exit"][0]
        self.assertEqual(ex["why"], "stop")
        self.assertLess(ex["net_r"], -1.0)          # stop + costi: oltre -1R
        self.assertEqual(st["open"], {})

    def test_target_net_of_costs(self):
        seq, c = signal_then([(1.0, 1.0, 1.0, 1.0), (1.0, 1.05, 0.999, 1.04)])
        _, ev = run_steps(seq)
        ex = [e for e in ev if e["ev"] == "exit"][0]
        self.assertEqual(ex["why"], "obiettivo")
        self.assertGreater(ex["net_r"], 1.0)
        self.assertLess(ex["net_r"], 1.5)            # i costi tolgono qualcosa a 1,5R
        notional = 2000.0
        self.assertAlmostEqual(ex["fees_usd"], 6e-4 * notional * (1 + ex["exit"] / ex["entry"]), places=4)

    def test_time_exit(self):
        seq, c = signal_then([(1.0, 1.0005, 0.9995, 1.0)] * 30)
        _, ev = run_steps(seq)
        ex = [e for e in ev if e["ev"] == "exit"][0]
        self.assertEqual(ex["why"], "tempo")
        self.assertEqual(ex["bars"], 24)

    def test_cooldown_after_exit(self):
        cfg = Config()
        seq, c = signal_then([(1.0, 1.0, 1.0, 1.0), (1.0, 1.0, 0.95, 0.96)])
        st, ev = run_steps(seq, cfg)
        ex = [e for e in ev if e["ev"] == "exit"][0]
        self.assertEqual(st["cooldown_until_ms"]["BTC"], ex["exit_bar_ms"] + 3 * BAR)

    def test_max_open_is_global(self):
        cfg = Config(max_open=1)
        seq, _ = signal_then([(1.0, 1.0005, 0.9995, 1.0)] * 3)
        st = strategy.new_state(cfg)
        st, _ = strategy.step(st, {"BTC": seq[:130], "ETH": seq[:130]}, cfg)
        evs = []
        for i in range(130, len(seq)):
            st, ev = strategy.step(st, {"BTC": seq[: i + 1], "ETH": seq[: i + 1]}, cfg)
            evs += ev
        self.assertEqual(len([e for e in evs if e["ev"] == "signal"]), 1)
        self.assertEqual(len(st["open"]) + len(st["pending"]), 1)

    def test_gap_voids_hypothetical_position(self):
        seq, _ = signal_then([(1.0, 1.0005, 0.9995, 1.0)] * 3)
        cfg = Config()
        st = strategy.new_state(cfg)
        st, _ = strategy.step(st, {"BTC": seq[:130]}, cfg)
        for i in range(130, len(seq) - 1):
            st, _ = strategy.step(st, {"BTC": seq[: i + 1]}, cfg)
        self.assertIn("BTC", st["open"])
        jumped = seq + [(seq[-1][0] + 5 * BAR,) + seq[-1][1:]]
        jumped = jumped[:-2] + jumped[-1:]          # manca la barra successiva: buco
        st, ev = strategy.step(st, {"BTC": jumped}, cfg)
        self.assertEqual(ev[0]["ev"], "buco")
        self.assertEqual(st["open"], {})

    def test_step_does_not_mutate_input(self):
        cfg = Config()
        seq, _ = signal_then([(1.0, 1.0, 1.0, 1.0)])
        st = strategy.new_state(cfg)
        st, _ = strategy.step(st, {"BTC": seq[:130]}, cfg)
        before = json.dumps(st, sort_keys=True)
        strategy.step(st, {"BTC": seq}, cfg)
        self.assertEqual(json.dumps(st, sort_keys=True), before)

    def test_replay_is_deterministic(self):
        seq, _ = signal_then([(1.0, 1.05, 0.999, 1.04)] * 2)
        self.assertEqual(run_steps(seq)[1], run_steps(seq)[1])


class Runner(unittest.TestCase):
    def test_journal_state_status_and_report(self):
        seq, _ = signal_then([(1.0, 1.0, 1.0, 1.0), (1.0, 1.05, 0.999, 1.04)])
        cfg = Config(symbols=("BTC",))
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "turbo")
            n = 130
            runner.run_once(out, cfg, seq[n - 1][0] + BAR + 1, fetch=lambda s, now, c: seq[:n])
            for i in range(n, len(seq)):
                now = seq[i][0] + BAR + 1
                runner.run_once(out, cfg, now, fetch=lambda s, now, c, i=i: seq[: i + 1])
            status = json.load(open(os.path.join(out, "status.json")))
            self.assertEqual(status["mode"], "ombra")
            self.assertFalse(status["applied"])
            lines = [json.loads(x) for f in os.listdir(out) if f.startswith("events-")
                     for x in open(os.path.join(out, f))]
            self.assertTrue(all(not ln["applied"] for ln in lines))
            # un evento ripetuto (arresto tra registro e stato) non si conta due volte
            path = [os.path.join(out, f) for f in os.listdir(out) if f.startswith("events-")][0]
            with open(path, "a") as f:
                f.write(open(path).read().splitlines()[-1] + "\n")
                f.write('{"troncata\n')
            exits, signals = report.read_exits(out)
            self.assertEqual(len(exits), 1)
            self.assertEqual(signals, 1)
            self.assertEqual(strategy.summarize(exits)["trades"], 1)

    def test_failing_symbol_does_not_stop_others_and_catches_up(self):
        cfg = Config(symbols=("BTC", "ETH"))
        seq = uptrend(140)

        def fetch(sym, now, c):
            if sym == "ETH":
                raise ValueError("giu'")
            return seq
        with tempfile.TemporaryDirectory() as d:
            st, _ = runner.run_once(d, cfg, seq[-1][0] + BAR + 1, fetch=fetch)
            self.assertIn("BTC", st["last_bar_ms"])
            self.assertNotIn("ETH", st["last_bar_ms"])
            status = json.load(open(os.path.join(d, "status.json")))
            self.assertIn("ETH", status["errors"])

    def test_config_change_restarts_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "state.json")
            json.dump(dict(strategy.new_state(Config()), config_hash="altro"), open(p, "w"))
            st, note = runner.load_state(p, Config())
            self.assertIsNotNone(note)
            self.assertEqual(st["open"], {})

    def test_fetch_rejects_wrong_clock(self):
        cfg = Config()

        class Resp:
            def __init__(self, rows):
                self.body = json.dumps({"code": "00000", "data": rows}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return self.body
        rows = [[str(T + i * BAR), "1", "1", "1", "1", "1"] for i in range(10)]
        now = T + 9 * BAR + 10_000                     # l'ultima riga e' la barra in formazione: ok
        bars = runner.fetch_closed_bars("BTC", now, cfg, opener=lambda r, timeout: Resp(rows))
        self.assertEqual(len(bars), 9)
        with self.assertRaises(ValueError):
            runner.fetch_closed_bars("BTC", now + 3 * BAR, cfg, opener=lambda r, timeout: Resp(rows))


if __name__ == "__main__":
    unittest.main()
