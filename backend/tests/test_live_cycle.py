"""Cicli completi del bot (cli.run_cycle) in modalita' LIVE contro l'exchange finto: lo stesso codice del
bot vero, con il connettore al posto di Bitget. Controlla che aperture, rifiuti, blocchi e riallineamenti
si comportino come previsto end-to-end. Nessuna rete, nessuna chiave, nessun parametro di strategia toccato.
"""
import json
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fake_bitget as fb  # noqa: E402
from fake_bitget import ccxt  # noqa: E402
import test_desk as td  # noqa: E402   (riuso del mondo di candele e dello stub di Claude)
from desk import cli  # noqa: E402
from desk import live_connector as lc  # noqa: E402

NOW = td.NOW


class LiveRig:
    """Prepara un bot in modalita' live: candele finte, Claude finto, exchange finto, cartella dati temporanea."""

    def __init__(self, trading_on=True, pos_mode=fb.ONE_WAY, action="open_long", n=700, scale=1.0):
        import desk.brain as _brain
        import desk.market_context as _mc
        self.d = tempfile.mkdtemp()
        self.world = td._world(n=n)
        last = {s: float(a[-1][4]) for s, a in self.world.items()}
        self.fake = fb.FakeBitget(pos_mode=pos_mode, symbols={s: 0.001 for s in cli.SYMBOLS},
                                  prices={f"{s}/USDT:USDT": p for s, p in last.items()})
        self.conn = lc.LiveConnector(data_dir=self.d, client=self.fake, live=True, sleep=lambda s: None,
                                     scale=scale)
        self._saved = (cli.fetch_candles, _mc.fetch_all_context, _brain.call_claude, cli.call_claude,
                       cli.LIVE, cli.STATE_FILE, cli.DATA_DIR, cli._TRADING_ENABLED_FILE, cli._DAILY_LOSS_LIMIT)
        world = self.world
        cli.fetch_candles = lambda sym, bar="15m", limit=300: (world.get(sym, np.zeros((0, 6)))[-limit:].tolist())
        _mc.fetch_all_context = lambda syms, now: {"funding": {}, "oi": {}, "news": [], "ts": now}
        stub = td._claude_stub(action=action)
        _brain.call_claude = stub
        cli.call_claude = stub
        cli.LIVE = self.conn
        cli.STATE_FILE = os.path.join(self.d, "state_v2.json")
        cli.DATA_DIR = self.d
        cli._TRADING_ENABLED_FILE = os.path.join(self.d, "trading_enabled.json")
        with open(cli._TRADING_ENABLED_FILE, "w") as f:
            json.dump({"enabled": trading_on}, f)
        os.environ["ANTHROPIC_API_KEY"] = "test"
        self.state = cli.load_state(cli.STATE_FILE)

    def cycle(self, k=0):
        cli.run_cycle(self.state, NOW + k * cli.HOUR_MS)
        cli.save_state(self.state, cli.STATE_FILE)
        self.state["last_call_ms"] = 0
        self.state["last_open_ms"] = {}

    def acc(self):
        return cli.make_account(self.state)

    def close(self):
        import desk.brain as _brain
        import desk.market_context as _mc
        (cli.fetch_candles, _mc.fetch_all_context, _brain.call_claude, cli.call_claude, cli.LIVE,
         cli.STATE_FILE, cli.DATA_DIR, cli._TRADING_ENABLED_FILE, cli._DAILY_LOSS_LIMIT) = self._saved
        os.environ.pop("ANTHROPIC_API_KEY", None)

    def events(self, name):
        p = os.path.join(self.d, "learning_log.jsonl")
        rows = []
        if os.path.exists(p):
            rows = [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]
        return [r for r in rows if r.get("ev") == name]


def test_live_cycle_opens_on_the_exchange_with_the_engine_numbers():
    rig = LiveRig()
    try:
        rig.cycle(0)
        rig.cycle(1)
        acc = rig.acc()
        assert "BTC" in acc.positions, list(acc.positions)
        pos = acc.positions["BTC"]
        leg = rig.fake.leg("BTC", 1)
        assert leg is not None and leg["margin_mode"] == "isolated" and leg["leverage"] == pos.leverage
        assert abs(leg["qty"] - pos.qty) <= max(0.03 * pos.qty, 0.002)         # stessa esposizione di quella simulata
        kinds = sorted(p["planType"] for p in rig.fake.plans)
        assert "loss_plan" in kinds                                              # stop sull'exchange dal primo istante
        opened = [e for e in rig.events("open") if e.get("symbol") == "BTC"]
        assert opened and opened[0]["live_fill"]["real_qty"] == leg["qty"]       # esito reale registrato accanto al simulato
        assert rig.conn.open_blocked() is None
    finally:
        rig.close()


def test_live_cycle_with_the_switch_off_sends_nothing():
    rig = LiveRig(trading_on=False)
    try:
        rig.cycle(0)
        rig.cycle(1)
        assert rig.acc().positions == {} and rig.fake.orders == [] and rig.fake.legs == {}
    finally:
        rig.close()


def test_live_cycle_rejected_by_the_exchange_leaves_no_trace_in_the_engine():
    rig = LiveRig()
    try:
        rig.fake.sticky["create_order"] = ccxt.InsufficientFunds("saldo insufficiente")
        rig.cycle(0)
        rig.cycle(1)
        acc = rig.acc()
        assert acc.positions == {} and rig.fake.legs == {}
        assert abs(acc.cash - cli.PORTFOLIO.limits.start_equity) < 1e-6          # nessun margine rimasto bloccato
    finally:
        rig.close()


def test_live_cycle_with_a_foreign_position_blocks_openings_and_touches_nothing():
    rig = LiveRig()
    try:
        rig.fake.put_position("ETH", -1, 2.0, entry=100.0)                       # aperta a mano / dall'altro bot
        rig.cycle(0)
        rig.cycle(1)
        assert rig.acc().positions == {} and rig.fake.orders == []
        assert rig.conn.open_blocked() and "ETH" in rig.conn.open_blocked()
        assert rig.fake.leg("ETH", -1)["qty"] == 2.0
        hb = json.load(open(os.path.join(rig.d, "heartbeat.json")))
        assert hb["exec_mode"] == "live" and "ETH" in hb["live_interlock"]       # l'app lo vede
    finally:
        rig.close()


def test_live_cycle_aligns_the_engine_when_the_exchange_closed_the_position():
    rig = LiveRig()
    try:
        rig.cycle(0)
        rig.cycle(1)
        assert "BTC" in rig.acc().positions
        rig.fake.legs.clear()                                                    # stop scattato sull'exchange
        rig.fake.plans.clear()
        rig.conn._opened_at.clear()
        rig.state["last_call_ms"] = NOW + 10 * cli.HOUR_MS                       # niente nuove decisioni di Claude
        cli.run_cycle(rig.state, NOW + 2 * cli.HOUR_MS)
        acc = rig.acc()
        closes = [c for c in acc.closed if c["symbol"] == "BTC"]
        assert "BTC" not in acc.positions and closes, "il motore deve allinearsi all'exchange piatto"
        assert closes[-1]["why"] in ("chiusa su Bitget", "stop loss", "take profit", "liquidazione")
    finally:
        rig.close()


def test_live_cycle_with_half_scale_opens_half_of_the_engine_and_stays_aligned():
    """Capitale assegnato 500$ su un motore da 1000$: stesse decisioni, ordini veri al 50%, nessun blocco."""
    rig = LiveRig(scale=0.5)
    try:
        rig.cycle(0)
        rig.cycle(1)
        pos = rig.acc().positions["BTC"]
        leg = rig.fake.leg("BTC", 1)
        assert leg is not None and leg["leverage"] == pos.leverage and leg["margin_mode"] == "isolated"
        assert abs(leg["qty"] - pos.qty * 0.5) <= max(0.03 * pos.qty * 0.5, 0.002)    # meta' dell'esposizione
        assert "loss_plan" in sorted(p["planType"] for p in rig.fake.plans)
        assert rig.conn.open_blocked() is None                                        # il confronto e' in scala
        opened = [e for e in rig.events("open") if e.get("symbol") == "BTC"]
        assert opened and opened[0]["live_fill"]["engine_qty"] == pos.qty and opened[0]["live_fill"]["scale"] == 0.5
    finally:
        rig.close()


class _Acc:                                                   # conto del motore, quanto basta per il limite giornaliero
    def __init__(self, closed):
        self.closed = closed


def _with_cli(live, scale, limit, since, fn):
    keep = (cli.LIVE, cli.CAPITAL_SCALE, cli._DAILY_LOSS_LIMIT, cli.LIVE_SINCE_MS)
    try:
        cli.LIVE = lc.LiveConnector(data_dir=tempfile.mkdtemp(), client=fb.FakeBitget() if live else None,
                                    live=live, sleep=lambda s: None, scale=scale)
        cli.CAPITAL_SCALE, cli._DAILY_LOSS_LIMIT, cli.LIVE_SINCE_MS = scale, limit, since
        return fn()
    finally:
        cli.LIVE, cli.CAPITAL_SCALE, cli._DAILY_LOSS_LIMIT, cli.LIVE_SINCE_MS = keep


def _today_ms():
    import time as _t
    return int(_t.time() // 86400 * 86400 * 1000) + 60_000


def test_daily_loss_limit_compares_the_real_scaled_loss():
    now = _today_ms()
    # capitale 500$ (scala 0,5), limite 25% = 125$ reali: una perdita del motore di -250 sono -125 veri
    at_limit = _Acc([{"net": -250.0, "open_ms": now - 5000, "close_ms": now}])
    below = _Acc([{"net": -249.0, "open_ms": now - 5000, "close_ms": now}])
    assert _with_cli(True, 0.5, 125.0, 1, lambda: cli._daily_loss_exceeded(at_limit)) is True
    assert _with_cli(True, 0.5, 125.0, 1, lambda: cli._daily_loss_exceeded(below)) is False
    # con scala 1 (capitale 1000, limite 250) e' come prima
    assert _with_cli(True, 1.0, 250.0, 1, lambda: cli._daily_loss_exceeded(_Acc(
        [{"net": -250.0, "open_ms": now - 5000, "close_ms": now}]))) is True


def test_daily_loss_ignores_simulator_positions_closed_after_the_live_start():
    """Le posizioni finte aperte PRIMA del live si chiudono al primo allineamento con un'uscita stimata:
    non sono perdite vere e non devono bloccare le aperture della giornata."""
    now = _today_ms()
    acc = _Acc([{"net": -900.0, "open_ms": now - 86_400_000, "close_ms": now},     # finta, aperta ieri
                {"net": -10.0, "open_ms": now - 1000, "close_ms": now}])           # vera
    assert _with_cli(True, 1.0, 250.0, now - 3_600_000, lambda: cli._daily_loss_exceeded(acc)) is False
    assert _with_cli(True, 1.0, 250.0, None, lambda: cli._daily_loss_exceeded(acc)) is True   # senza partenza nota: tutto conta


def test_daily_loss_limit_never_blocks_in_paper():
    now = _today_ms()
    acc = _Acc([{"net": -99999.0, "open_ms": now - 5000, "close_ms": now}])
    assert _with_cli(False, 0.5, 125.0, None, lambda: cli._daily_loss_exceeded(acc)) is False


def test_live_since_is_written_once_and_survives_restarts():
    d = tempfile.mkdtemp()
    keep = (cli.LIVE, cli._LIVE_SINCE_FILE, cli.DATA_DIR, cli.LIVE_SINCE_MS)
    try:
        cli.DATA_DIR = d
        cli._LIVE_SINCE_FILE = os.path.join(d, "live_since.json")
        cli.LIVE = lc.LiveConnector(data_dir=d, live=False)
        assert cli.ensure_live_since(1234) is None and not os.path.exists(cli._LIVE_SINCE_FILE)   # paper: niente
        cli.LIVE = lc.LiveConnector(data_dir=d, client=fb.FakeBitget(), live=True, sleep=lambda s: None)
        assert cli.ensure_live_since(1_700_000_000_000) == 1_700_000_000_000
        assert json.load(open(cli._LIVE_SINCE_FILE)) == {"since_ms": 1_700_000_000_000}
        assert cli.ensure_live_since(1_800_000_000_000) == 1_700_000_000_000                       # riavvio: resta la prima
        assert cli.LIVE_SINCE_MS == 1_700_000_000_000
        with open(cli._LIVE_SINCE_FILE, "w") as f:
            f.write("{rotto")                                                                       # file rovinato: si riparte da ora
        assert cli.ensure_live_since(1_900_000_000_000) == 1_900_000_000_000
    finally:
        cli.LIVE, cli._LIVE_SINCE_FILE, cli.DATA_DIR, cli.LIVE_SINCE_MS = keep


def test_heartbeat_tells_the_app_the_scale_and_when_live_started():
    d = tempfile.mkdtemp()
    keep = (cli.LIVE, cli.DATA_DIR, cli.CAPITAL_SCALE, cli._PORTFOLIO_CAPITAL, cli.LIVE_SINCE_MS)
    try:
        cli.DATA_DIR = d
        cli.LIVE = lc.LiveConnector(data_dir=d, client=fb.FakeBitget(), live=True, sleep=lambda s: None, scale=0.5)
        cli.CAPITAL_SCALE, cli._PORTFOLIO_CAPITAL, cli.LIVE_SINCE_MS = 0.5, 500.0, 1_700_000_000_000
        cli.write_heartbeat(None, force=True)
        hb = json.load(open(os.path.join(d, "heartbeat.json")))
        assert hb["exec_mode"] == "live" and hb["capital_scale"] == 0.5 and hb["capital_usd"] == 500.0
        assert hb["live_since_ms"] == 1_700_000_000_000
        assert hb["reset_keeps_brain"] is True, "l'app sblocca l'azzeramento solo con questo campo"
        cli.LIVE = lc.LiveConnector(data_dir=d, live=False)
        cli.write_heartbeat(None, force=True)
        hb = json.load(open(os.path.join(d, "heartbeat.json")))
        assert hb["exec_mode"] == "paper" and hb["capital_scale"] == 0.5
    finally:
        cli.LIVE, cli.DATA_DIR, cli.CAPITAL_SCALE, cli._PORTFOLIO_CAPITAL, cli.LIVE_SINCE_MS = keep


def _request_close(rig, symbols):
    with open(os.path.join(rig.d, "close_position.flag"), "w") as f:
        json.dump({"symbols": symbols, "ts": int(__import__("time").time() * 1000)}, f)


def test_manual_close_in_live_closes_on_the_exchange_first_and_keeps_the_real_fill():
    rig = LiveRig()
    try:
        rig.cycle(0)
        rig.cycle(1)
        assert "BTC" in rig.acc().positions and rig.fake.legs, "prima c'e' una posizione vera"
        _request_close(rig, ["BTC"])
        assert cli._check_close_position_flag(rig.state) is True
        acc = rig.acc()
        assert "BTC" not in acc.positions and not rig.fake.legs, "chiusa sia nel motore sia sull'exchange"
        rec = [c for c in acc.closed if c["symbol"] == "BTC"][-1]
        assert rec["closed_by"] == "utente" and rec["why"] == "chiusura manuale"
        assert rec.get("live"), "accanto ai numeri del motore c'e' il fill vero di Bitget"
        assert rig.state["last_action"]["ok"] is True
        assert [e for e in rig.events("close") if e.get("closed_by") == "utente"]
    finally:
        rig.close()


def test_manual_close_in_live_when_the_exchange_refuses_keeps_the_position_open_everywhere():
    rig = LiveRig()
    try:
        rig.cycle(0)
        rig.cycle(1)
        assert "BTC" in rig.acc().positions
        rig.fake.sticky["create_order"] = ccxt.ExchangeError("bitget: ordine rifiutato")
        _request_close(rig, ["BTC"])
        cli._check_close_position_flag(rig.state)
        assert "BTC" in rig.acc().positions and rig.fake.legs, "se Bitget non chiude, il motore non chiude"
        assert rig.state["last_action"]["ok"] is False and "BTC" in rig.state["last_action"]["skipped"]
        assert not [c for c in rig.acc().closed if c["symbol"] == "BTC"]
    finally:
        rig.close()


def test_manual_close_works_with_the_trading_switch_off():
    """L'interruttore spento ferma le APERTURE, non le chiusure: chiudere una posizione resta sempre possibile."""
    rig = LiveRig()
    try:
        rig.cycle(0)
        rig.cycle(1)
        assert "BTC" in rig.acc().positions
        with open(cli._TRADING_ENABLED_FILE, "w") as f:
            json.dump({"enabled": False}, f)
        _request_close(rig, ["BTC"])
        cli._check_close_position_flag(rig.state)
        assert "BTC" not in rig.acc().positions and not rig.fake.legs
    finally:
        rig.close()
