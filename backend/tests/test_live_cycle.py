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

    def __init__(self, trading_on=True, pos_mode=fb.ONE_WAY, action="open_long", n=700):
        import desk.brain as _brain
        import desk.market_context as _mc
        self.d = tempfile.mkdtemp()
        self.world = td._world(n=n)
        last = {s: float(a[-1][4]) for s, a in self.world.items()}
        self.fake = fb.FakeBitget(pos_mode=pos_mode, symbols={s: 0.001 for s in cli.SYMBOLS},
                                  prices={f"{s}/USDT:USDT": p for s, p in last.items()})
        self.conn = lc.LiveConnector(data_dir=self.d, client=self.fake, live=True, sleep=lambda s: None)
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
