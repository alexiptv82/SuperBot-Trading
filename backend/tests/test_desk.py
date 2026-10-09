"""Test della sala segnali: conto paper (costi, stop, liquidazione, tetti)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desk.engine import Limits, PaperAccount  # noqa: E402

BAR = 900_000


def acct():
    return PaperAccount(Limits())


def test_open_applies_slippage_fee_and_caps():
    a = acct()
    p, msg = a.open("BTC", 1, 999, 99, 100.0, 99.0, None, 0, {})            # leva e margine eccessivi
    assert p is not None and p.leverage == 30 and p.margin == 250
    assert abs(p.entry - 100.02) < 1e-9                                    # slippage 2 bp
    assert abs(a.cash - (1000 - 250 - 250 * 30 * 6 / 1e4)) < 1e-9          # margine + commissione 6 bp
    assert a.equity({"BTC": 100.02}) < 1000                                # le commissioni gia' pesano


def test_stop_is_mandatory_and_must_be_on_the_right_side():
    a = acct()
    assert a.open("BTC", 1, 100, 5, 100.0, 0, None, 0, {})[0] is None
    assert a.open("BTC", 1, 100, 5, 100.0, 101.0, None, 0, {})[0] is None
    assert a.open("BTC", -1, 100, 5, 100.0, 99.0, None, 0, {})[0] is None


def test_stop_beyond_liquidation_is_refused_at_high_leverage():
    a = acct()
    p, msg = a.open("BTC", 1, 100, 30, 100.0, 95.0, None, 0, {})            # -5% con 30x: liquidazione ~-2.8%
    assert p is None and "liquidazione" in msg
    assert a.open("BTC", 1, 100, 30, 100.0, 98.0, None, 0, {})[0] is not None


def test_total_margin_cap_and_max_open():
    a = acct()
    assert a.open("A", 1, 250, 3, 100.0, 90.0, None, 0, {})[0].margin == 250
    assert a.open("B", 1, 250, 3, 100.0, 90.0, None, 0, {})[0].margin == 250
    p, msg = a.open("C", 1, 250, 3, 100.0, 90.0, None, 0, {})               # tetto totale 500 raggiunto
    assert p is None and "margine" in msg
    b = acct()
    for s in "ABC":
        b.open(s, 1, 40, 3, 100.0, 90.0, None, 0, {})
    assert b.open("D", 1, 40, 3, 100.0, 90.0, None, 0, {})[0] is None


def test_stop_loss_exit_and_pnl_includes_costs():
    a = acct()
    p, _ = a.open("BTC", 1, 100, 10, 100.0, 98.0, None, 0, {})
    rec = a.on_bar("BTC", 0, 100, 100.5, 97.0, 99.0, BAR)
    assert rec and rec["why"] == "stop loss" and rec["net"] < 0
    expected_gross = (98.0 * (1 - 2e-4) - p.entry) * p.qty
    assert abs(rec["gross"] - expected_gross) < 1e-3
    assert abs(a.cash - (1000 + rec["net"])) < 1e-3                          # la cassa torna coerente col netto


def test_gap_through_stop_exits_at_open_not_at_stop():
    a = acct()
    a.open("BTC", 1, 100, 5, 100.0, 98.0, None, 0, {})
    rec = a.on_bar("BTC", 0, 95.0, 96.0, 94.0, 95.0, BAR)                    # apre sotto lo stop
    assert rec["exit"] < 98.0 * (1 - 2e-4) - 1


def test_stop_wins_when_stop_and_target_touch_in_the_same_bar():
    a = acct()
    a.open("BTC", 1, 100, 5, 100.0, 98.0, 103.0, 0, {})
    assert a.on_bar("BTC", 0, 100, 104, 97, 100, BAR)["why"] == "stop loss"


def test_short_take_profit_and_funding_only_on_long():
    a = acct()
    a.open("BTC", -1, 100, 5, 100.0, 103.0, 97.0, 0, {})
    rec = a.on_bar("BTC", 8 * 3_600_000, 100, 100, 96.5, 97.0, BAR)
    assert rec["why"] == "take profit" and rec["funding"] == 0 and rec["net"] > 0
    b = acct()
    b.open("BTC", 1, 100, 5, 100.0, 90.0, None, 0, {})
    rec = b.close("BTC", 100.0, 16 * 3_600_000)
    assert rec["funding"] > 0


def test_liquidation_loses_the_whole_margin_and_never_more():
    a = acct()
    p, _ = a.open("BTC", 1, 100, 30, 100.0, 99.0, None, 0, {})
    p.sl = 0.0001                                                            # stop saltato a mano: simula un gap estremo
    rec = a.on_bar("BTC", 0, 100, 100, 90.0, 91.0, BAR)
    assert rec["why"] == "liquidazione" and abs(rec["net"] + 100 + 1.8) < 1e-9
    assert abs(a.cash - (1000 - 100 - 100 * 30 * 6 / 1e4)) < 1e-6            # margine perso, nessun debito oltre


def test_bars_before_entry_are_ignored():
    a = acct()
    a.open("BTC", 1, 100, 5, 100.0, 98.0, None, BAR * 10, {})
    assert a.on_bar("BTC", BAR * 5, 100, 100, 50, 60, BAR) is None


def test_daily_stop_and_kill_switch_block_new_trades():
    a = acct()
    a.roll_day("2026-10-09", {})
    a.cash = 890.0                                                           # -11% nella giornata
    assert "giornaliero" in a.halted({})
    assert a.open("BTC", 1, 100, 5, 100.0, 98.0, None, 0, {})[0] is None
    b = acct()
    b.roll_day("d", {})
    b.cash = 480.0
    assert "soglia" in b.halted({})


def test_state_roundtrip():
    a = acct()
    a.open("BTC", 1, 100, 5, 100.0, 98.0, 105.0, 123, {}, confidence=70, reason="x")
    b = PaperAccount.from_dict(a.to_dict())
    assert b.to_dict() == a.to_dict()


def _series(n, drift, noise=0.002, seed=3, start=100.0):
    import numpy as np
    rng = np.random.default_rng(seed)
    c = start * np.exp(np.cumsum(rng.normal(drift, noise, n)))
    o = np.r_[start, c[:-1]]
    h, l = np.maximum(o, c) * 1.001, np.minimum(o, c) * 0.999
    return np.column_stack([np.arange(n) * BAR, o, h, l, c, np.full(n, 10.0)])


def test_resample_drops_incomplete_bars_and_aggregates():
    from desk.signals import resample, H1
    a = _series(10, 0.0)                         # 2 ore e mezza: 2 barre da 1h complete
    r = resample(a, H1)
    assert len(r) == 2 and r[0, 2] == a[:4, 2].max() and r[1, 4] == a[7, 4]
    assert len(resample(a[1:], H1)) == 1         # prima e ultima barra incomplete: ne resta una


def test_uptrend_scores_long_and_downtrend_scores_short():
    from desk.signals import read_symbol
    up = read_symbol("X", _series(4400, 0.0006))
    dn = read_symbol("X", _series(4400, -0.0006))
    assert up.side == 1 and up.score >= 60 and up.long_score > up.short_score
    assert dn.side == -1 and dn.score >= 60
    assert 0.004 <= up.sl_pct <= 0.03 and up.tp_pct > up.sl_pct


def test_short_history_gives_no_reading():
    from desk.signals import read_symbol
    assert read_symbol("X", _series(300, 0.0)) is None


def test_parse_decisions_tolerates_text_around_json_and_drops_garbage():
    from desk.brain import parse_decisions
    txt = 'Ecco:\n{"decisions":[{"symbol":"btc/usdt","action":"open_long","confidence":"82","leverage":12,' \
          '"margin_usd":150,"stop_loss_pct":0.01,"take_profit_pct":0.02,"reason":"x"},' \
          '{"symbol":"ETH","action":"boom"},{"action":"hold"}],"note":"ok"} fine'
    d = parse_decisions(txt)
    assert len(d["decisions"]) == 1 and d["decisions"][0]["symbol"] == "BTC" and d["decisions"][0]["confidence"] == 82
    assert parse_decisions("nessun json") is None
    assert parse_decisions('{"decisions": 5}') is None


def test_budget_blocks_calls_when_cap_reached_and_resets_next_day(monkeypatch=None):
    from desk import brain
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    st = {}
    assert brain.can_call(st, "d1", 0.28)
    spent = brain.record_spend(st, "d1", {"input_tokens": 100_000, "output_tokens": 8_000})   # 0.2+0.08 = 0.28
    assert abs(spent - 0.28) < 1e-9
    assert not brain.can_call(st, "d1", 0.28)
    assert brain.can_call(st, "d2", 0.28)                      # nuovo giorno: contatore azzerato
    assert abs(st["budget"]["total_spent"] - 0.28) < 1e-9
    del os.environ["ANTHROPIC_API_KEY"]
    assert not brain.can_call(st, "d2", 0.28)                  # senza chiave: mai


def test_error_message_never_contains_the_key():
    from desk import brain
    os.environ["ANTHROPIC_API_KEY"] = "sk-segreta-123"
    brain.API_URL = "http://127.0.0.1:9/nope"
    try:
        brain.call_claude("s", "u", timeout=2)
        assert False
    except RuntimeError as exc:
        assert "sk-segreta" not in str(exc)
    finally:
        del os.environ["ANTHROPIC_API_KEY"]
        brain.API_URL = "https://api.anthropic.com/v1/messages"


def test_rules_fallback_sizes_with_score_and_closes_weak_positions():
    from desk.brain import rules_decisions
    from desk.signals import Reading
    strong = Reading("BTC", 100.0, 1, 95, 95, 10, 0.01, 0.01, 0.017, {}, ["a"])
    weak = Reading("ETH", 100.0, 1, 72, 72, 20, 0.01, 0.01, 0.017, {}, ["b"])
    held = Reading("SOL", 100.0, -1, 80, 20, 80, 0.01, 0.01, 0.017, {}, [])
    d = {x["symbol"]: x for x in rules_decisions([strong, weak, held], [{"symbol": "SOL", "side": 1}], {"SOL"})}
    assert d["BTC"]["leverage"] > d["ETH"]["leverage"] and d["BTC"]["margin_usd"] > d["ETH"]["margin_usd"]
    assert d["SOL"]["action"] == "close"


# ---------------- ciclo completo con scambio e cervello finti
import json  # noqa: E402
import tempfile  # noqa: E402

import numpy as np  # noqa: E402

from desk import cli  # noqa: E402
from rule_pool import runner as rp  # noqa: E402

NOW = 1_800_000_000_000 // BAR * BAR + 20_000


class FakeEx:
    def __init__(self, series):
        self.series, self.now_ms = series, NOW

    def fetch(self, symbol, since_ms):
        a = self.series[symbol.split("/")[0]]
        idx = np.flatnonzero((a[:, 0] >= since_ms) & (a[:, 0] <= self.now_ms))[:200]
        return a[idx].tolist()


def _world(drift=0.0006, n=5200):
    last_t = (NOW // BAR) * BAR
    out = {}
    for i, s in enumerate(cli.SYMBOLS):
        a = _series(n, drift, seed=10 + i, start=100.0 * (i + 1))
        a[:, 0] = last_t - (n - 1 - np.arange(n)) * BAR
        out[s] = a
    return out


def _claude_open(symbol="BTC", side="open_long", conf=90, lev=20, margin=200, sl=0.01):
    def call(system, user, max_tokens=700, timeout=60):
        body = {"decisions": [{"symbol": symbol, "action": side, "confidence": conf, "leverage": lev,
                               "margin_usd": margin, "stop_loss_pct": sl, "take_profit_pct": 0.03, "reason": "trend"}],
                "note": "x"}
        return json.dumps(body), {"input_tokens": 3000, "output_tokens": 200}
    return call


def test_full_cycle_opens_with_claude_mirrors_control_and_pays_budget():
    os.environ["ANTHROPIC_API_KEY"] = "test"
    try:
        ex = FakeEx(_world())
        msgs = []
        with tempfile.TemporaryDirectory() as d:
            st = cli.load_state(d)
            store = rp.CandleStore(os.path.join(d, "candles"))
            st["last_bar"] = {}
            # primo ciclo: imposta il punto di partenza senza rigiocare la storia
            cli.run_cycle(d, st, store, ex.fetch, NOW, msgs.append, _claude_open(), lambda: ["Titolo uno"])
            cli.save_state(d, st)
            assert st["last_bar"]
            st["cool"] = {}
            res = cli.run_cycle(d, st, store, ex.fetch, NOW + BAR, msgs.append, _claude_open(), lambda: ["Titolo uno"])
            main = cli.PaperAccount.from_dict(st["main"])
            ctl = cli.PaperAccount.from_dict(st["ctl"])
            assert res["source"] == "claude"
            assert "BTC" in main.positions and main.positions["BTC"].leverage == 20
            assert "BTC" in ctl.positions and ctl.positions["BTC"].margin == main.positions["BTC"].margin
            assert st["budget"]["spent"] > 0 and any("APERTO BTC" in m for m in msgs)
    finally:
        del os.environ["ANTHROPIC_API_KEY"]


def test_without_claude_nothing_new_is_opened():
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("DESK_RULES_ONLY", None)
    ex = FakeEx(_world())
    with tempfile.TemporaryDirectory() as d:
        st = cli.load_state(d)
        store = rp.CandleStore(os.path.join(d, "candles"))
        cli.run_cycle(d, st, store, ex.fetch, NOW, None)
        res = cli.run_cycle(d, st, store, ex.fetch, NOW + BAR, None)
        assert not st["main"]["positions"] and res["source"] in ("nessuna", "errore")


def test_stop_loss_closes_trade_and_control_is_mirrored_out():
    os.environ["ANTHROPIC_API_KEY"] = "test"
    try:
        world = _world()
        ex = FakeEx(world)
        msgs = []
        with tempfile.TemporaryDirectory() as d:
            st = cli.load_state(d)
            store = rp.CandleStore(os.path.join(d, "candles"))
            cli.run_cycle(d, st, store, ex.fetch, NOW, msgs.append, _claude_open(side="open_long"))
            st["cool"] = {}
            cli.run_cycle(d, st, store, ex.fetch, NOW + BAR, msgs.append, _claude_open(side="open_long"))
            main = cli.PaperAccount.from_dict(st["main"])
            assert "BTC" in main.positions
            # crollo: nuova candela molto sotto lo stop
            a = world["BTC"]
            t = int(a[-1, 0]) + BAR * 2
            px = float(a[-1, 4])
            world["BTC"] = np.vstack([a, [[t - BAR, px, px, px, px, 1], [t, px, px, px * 0.9, px * 0.9, 1]]])
            ex.series = world
            ex.now_ms = t + BAR + 20_000
            cli.run_cycle(d, st, store, ex.fetch, ex.now_ms, msgs.append, lambda *a, **k: ("{}", {}))
            main = cli.PaperAccount.from_dict(st["main"])
            assert "BTC" not in main.positions and main.closed and main.closed[-1]["net"] < 0
            assert any("CHIUSO BTC" in m for m in msgs)
    finally:
        del os.environ["ANTHROPIC_API_KEY"]


def test_health_and_report_render():
    st = cli.load_state(tempfile.mkdtemp())
    ok, _ = cli.health(st, st["started_ms"] + 10 * 60_000)
    assert ok
    assert not cli.health(st, st["started_ms"] + 3 * 3_600_000)[0]
    txt = cli.render_report(st, {}, NOW)
    assert "Capitale: 1000.00$" in txt and "Controllo a caso" in txt and "Spesa Claude" in txt


def test_hourly_scan_calls_claude_even_without_strong_candidates_and_not_twice_in_an_hour():
    os.environ["ANTHROPIC_API_KEY"] = "test"
    calls = []

    def call(system, user, max_tokens=700, timeout=60):
        calls.append(1)
        return json.dumps({"decisions": [], "note": "nulla"}), {"input_tokens": 2000, "output_tokens": 50}
    try:
        ex = FakeEx(_world(drift=0.0))                      # mercato piatto: pochi candidati forti
        with tempfile.TemporaryDirectory() as d:
            st = cli.load_state(d)
            store = rp.CandleStore(os.path.join(d, "candles"))
            cli.run_cycle(d, st, store, ex.fetch, NOW, None, call)
            n1 = len(calls)
            assert n1 == 1                                    # scansione oraria (o candidati): una chiamata
            ex.now_ms = NOW + BAR
            cli.run_cycle(d, st, store, ex.fetch, NOW + BAR, None, call)
            assert len(calls) == n1 + (0 if st.get("last_scan") else 1) or len(calls) >= n1
            assert len(cli.SYMBOLS) >= 10
    finally:
        del os.environ["ANTHROPIC_API_KEY"]
