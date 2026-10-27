"""Cicli completi (cli.run_cycle) con il regime di mercato: in un mercato in discesa le regole aprono solo short, in uno
in salita solo long; il regime si salva nello stato; con DESK_REGIME_V1 spento tutto torna come prima.
Si forniscono barre a 4 ore coerenti con le 15m (senza, i segnali non nascono)."""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DESK_MACRO_FETCH", "0")

import test_desk as td  # noqa: E402
from desk import cli  # noqa: E402

H4 = 14_400_000


def agg4(a15, now_ms):
    key = (a15[:, 0] // H4).astype(np.int64)
    out = []
    for k in np.unique(key):
        g = a15[key == k]
        if len(g) == H4 // 900_000 and (k + 1) * H4 <= now_ms:
            out.append([k * H4, g[0, 1], g[:, 2].max(), g[:, 3].min(), g[-1, 4], g[:, 5].sum()])
    return np.array(out, dtype=float)


class Rig:
    def __init__(self, drift, regime_on=True):
        import desk.market_context as _mc
        self._mc = _mc
        self.world = td._world(drift=drift, n=4500)
        self.d = tempfile.mkdtemp()
        self._saved = (cli.fetch_candles, _mc.fetch_all_context, cli.four_hour_bars, cli.daily_bars,
                       cli.STATE_FILE, cli.DATA_DIR, cli.REGIME_ON)
        world = self.world
        cli.fetch_candles = lambda sym, bar="15m", limit=300: (world.get(sym, np.zeros((0, 6)))[-limit:].tolist())
        _mc.fetch_all_context = lambda syms, now: {"funding": {}, "oi": {}, "news": [], "ts": now}
        cli.four_hour_bars = lambda sym, now_ms: agg4(world[sym], now_ms)
        cli.daily_bars = lambda sym, now_ms, budget=True: np.empty((0, 6))
        cli.STATE_FILE = os.path.join(self.d, "state_v2.json")
        cli.DATA_DIR = self.d
        cli.REGIME_ON = regime_on
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.state = cli.load_state(cli.STATE_FILE)

    def cycle(self, k):
        cli.run_cycle(self.state, td.NOW + k * cli.HOUR_MS)
        cli.save_state(self.state, cli.STATE_FILE)
        self.state["last_open_ms"] = {}

    def sides(self):
        return {p.symbol: p.side for p in cli.make_account(self.state).positions.values()}

    def close(self):
        (cli.fetch_candles, self._mc.fetch_all_context, cli.four_hour_bars, cli.daily_bars,
         cli.STATE_FILE, cli.DATA_DIR, cli.REGIME_ON) = self._saved


def test_downtrend_opens_only_shorts_and_saves_regime(capsys):
    rig = Rig(drift=-0.0002)
    try:
        for k in range(3):
            rig.cycle(k)
        out = capsys.readouterr().out
        assert "[REGIME] down" in out, out[-1500:]
        hist = rig.state.get("regime_hist")
        assert isinstance(hist, list) and len(hist) == 3 and all(isinstance(x, float) for x in hist)
        sides = rig.sides()
        assert sides, "in un ribasso netto le regole devono aprire qualcosa"
        assert set(sides.values()) == {-1}, sides
    finally:
        rig.close()


def test_uptrend_opens_only_longs():
    rig = Rig(drift=0.0002)
    try:
        for k in range(3):
            rig.cycle(k)
        sides = rig.sides()
        assert sides, "in un rialzo netto le regole devono aprire qualcosa"
        assert set(sides.values()) == {1}, sides
    finally:
        rig.close()


def test_regime_off_keeps_the_old_behaviour(capsys):
    rig = Rig(drift=-0.0002, regime_on=False)
    try:
        rig.cycle(0)
        out = capsys.readouterr().out
        assert "[REGIME]" not in out
        assert "regime_hist" not in rig.state or not rig.state["regime_hist"]
        assert rig.sides(), "senza regime le regole aprono come sempre"
    finally:
        rig.close()
