"""Bull, cicli completi (cli.run_cycle) in paper: tetto al rischio SL aperto e veto SHORT mentre BTC rimbalza.
Il mondo di candele di test_desk ha un drift positivo (BTC sale di diversi punti in 24h): e' il caso del rimbalzo.
Un processo per file: il portafoglio si sceglie all'importazione (DESK_PORTFOLIO)."""
import json
import os
import sys
import tempfile

import numpy as np

os.environ["DESK_PORTFOLIO"] = "bull"
os.environ.setdefault("DESK_DATA_DIR", "/tmp/bull_guards_test")
os.environ.setdefault("DESK_MACRO_FETCH", "0")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_desk as td  # noqa: E402
from desk import cli  # noqa: E402

NOW = td.NOW
assert cli.PORTFOLIO.name == "bull"


class Rig:
    def __init__(self, drift=0.0006):
        import desk.brain as _brain
        import desk.market_context as _mc
        self._brain, self._mc = _brain, _mc
        self.d = tempfile.mkdtemp()
        self.world = td._world(drift=drift, n=700)
        self._saved = (cli.fetch_candles, _mc.fetch_all_context, _brain.call_claude, cli.call_claude,
                       cli.STATE_FILE, cli.DATA_DIR)
        world = self.world
        cli.fetch_candles = lambda sym, bar="15m", limit=300: (world.get(sym, np.zeros((0, 6)))[-limit:].tolist())
        _mc.fetch_all_context = lambda syms, now: {"funding": {}, "oi": {}, "news": [], "ts": now}
        cli.STATE_FILE = os.path.join(self.d, "state_v2.json")
        cli.DATA_DIR = self.d
        os.environ["ANTHROPIC_API_KEY"] = "test"
        self.state = cli.load_state(cli.STATE_FILE)

    def claude(self, **kw):
        stub = td._claude_stub(**kw)
        self._brain.call_claude = stub
        cli.call_claude = stub

    def cycle(self, k):
        cli.run_cycle(self.state, NOW + k * cli.HOUR_MS)
        cli.save_state(self.state, cli.STATE_FILE)
        self.state["last_call_ms"] = 0
        self.state["last_open_ms"] = {}

    def positions(self):
        return set(cli.make_account(self.state).positions)

    def candidate_statuses(self):
        out = []
        for name in os.listdir(self.d):
            if name.endswith(".jsonl"):
                for line in open(os.path.join(self.d, name), encoding="utf-8"):
                    if line.strip():
                        try:
                            r = json.loads(line)
                        except ValueError:
                            continue
                        if r.get("ev") == "candidate":
                            out.append(r.get("status"))
        return out

    def close(self):
        (cli.fetch_candles, self._mc.fetch_all_context, self._brain.call_claude, cli.call_claude,
         cli.STATE_FILE, cli.DATA_DIR) = self._saved
        os.environ.pop("ANTHROPIC_API_KEY", None)


def test_the_test_world_is_a_btc_rally():
    rig = Rig()
    try:
        closed = cli.closed_bars(rig.world["BTC"], NOW)
        assert cli._bars_return(closed, 96) > cli.BULL_SHORT_VETO_BTC_24H
    finally:
        rig.close()


def test_short_is_vetoed_while_btc_rallies(capsys):
    rig = Rig()
    try:
        rig.claude(action="open_short", symbol="ETH", sl=0.01)
        rig.cycle(0)
        rig.cycle(1)
        assert "ETH" not in rig.positions()
        out = capsys.readouterr().out
        assert "[SKIP:BULL] ETH open_short" in out and "nessun nuovo SHORT" in out
        assert "rifiutata:veto_short_rimbalzo_btc" in rig.candidate_statuses()
    finally:
        rig.close()


def test_same_short_opens_when_the_veto_is_off():
    """Controllo: senza veto la stessa decisione apre. Prova che e' la guardia a fermarla, non altro."""
    rig = Rig()
    keep = cli.BULL_SHORT_VETO_BTC_24H
    try:
        cli.BULL_SHORT_VETO_BTC_24H = 10.0
        rig.claude(action="open_short", symbol="ETH", sl=0.01)
        rig.cycle(0)
        rig.cycle(1)
        assert "ETH" in rig.positions()
    finally:
        cli.BULL_SHORT_VETO_BTC_24H = keep
        rig.close()


def test_long_is_never_vetoed_by_the_rally():
    rig = Rig()
    try:
        rig.claude(action="open_long", symbol="ETH", sl=0.01)
        rig.cycle(0)
        rig.cycle(1)
        assert "ETH" in rig.positions()
    finally:
        rig.close()


def test_third_position_is_refused_by_the_risk_cap_but_the_first_two_open():
    """Tetto 250$ (utente 26/10): con ~84$ di rischio SL a posizione passano due posizioni, la terza (252$) no."""
    rig = Rig()
    try:
        assert cli.BULL_MAX_OPEN_RISK_USD == 250.0
        # sl 1,6% con TP 2,5% (R:R 1,56) -> con 350$ x 15x il rischio SL e' ~84$ a posizione
        rig.claude(action="open_long", symbol="BTC", sl=0.016, lev=15, margin=350)
        rig.cycle(0)
        rig.cycle(1)
        assert rig.positions() == {"BTC"}, rig.positions()
        risk = cli._open_sl_risk(cli.make_account(rig.state))
        assert 0 < risk < cli.BULL_MAX_OPEN_RISK_USD, risk
        rig.claude(action="open_long", symbol="ETH", sl=0.016, lev=15, margin=350)
        rig.cycle(2)
        assert rig.positions() == {"BTC", "ETH"}, "con 250$ la seconda posizione deve passare"
        rig.claude(action="open_long", symbol="SOL", sl=0.016, lev=15, margin=350)
        rig.cycle(3)
        assert rig.positions() == {"BTC", "ETH"}, "la terza deve essere rifiutata dal tetto di rischio"
        assert "rifiutata:rischio_aperto_bull" in rig.candidate_statuses()
    finally:
        rig.close()


def test_second_position_opens_when_the_cap_is_raised():
    """Controllo del test precedente: con il tetto alzato la seconda apre."""
    rig = Rig()
    keep = cli.BULL_MAX_OPEN_RISK_USD
    try:
        cli.BULL_MAX_OPEN_RISK_USD = 10_000.0
        rig.claude(action="open_long", symbol="BTC", sl=0.016, lev=15, margin=350)
        rig.cycle(0)
        rig.cycle(1)
        rig.claude(action="open_long", symbol="ETH", sl=0.016, lev=15, margin=350)
        rig.cycle(2)
        assert rig.positions() == {"BTC", "ETH"}
    finally:
        cli.BULL_MAX_OPEN_RISK_USD = keep
        rig.close()
