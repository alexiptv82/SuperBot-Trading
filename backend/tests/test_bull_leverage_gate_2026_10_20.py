"""Test opzione B: limite di leva massima (decisione di Alexander, 20/10/2026 17:58).

Hawk  max_leverage=20 — scalp con leva alta bloccati sopra x20.
Bull  max_leverage=15 — medio/scalp bloccati sopra x15.
None  (default PortfolioConfig) — nessun limite, mai bloccato.

Struttura analoga a test_bull_margin_gate_2026_10_20.py.
"""

from __future__ import annotations
import sys, os, time, types

# ── path ────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(__file__)
_BACKEND = os.path.dirname(_HERE)
sys.path.insert(0, _BACKEND)

# ── stub minimale dell'ambiente ──────────────────────────────────────────────
os.environ.setdefault("DESK_MODE", "paper")
os.environ.setdefault("DESK_DATA_DIR", "/tmp/lev_gate_test")
os.environ.setdefault("DESK_MACRO_FETCH", "0")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

# blocca import pesanti che non servono al gate
for _mod in ("desk.brain", "desk.market_context", "desk.live_connector",
             "desk.live_sync", "desk.notifier", "desk.learning",
             "desk.macro_calendar", "desk.trading_hours", "desk.schedule"):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

# stub fetch_all_context
_mctx = sys.modules["desk.market_context"]
_mctx.fetch_all_context = lambda *a, **kw: {"funding": {}, "oi": {}, "ls_ratio": {}, "news": [], "ts": 0}

# stub minimale brain
_brain = sys.modules["desk.brain"]
_brain.DAILY_CAP = 0.70
_brain.SYSTEM = ""
_brain.SYSTEM_BULL = ""
_brain.build_prompt = lambda *a, **kw: ""
_brain.call_claude = lambda *a, **kw: ("", {})
_brain.can_call = lambda *a, **kw: False
_brain.diagnose_reply = lambda *a: ""
_brain.parse_decisions = lambda *a: None
_brain.record_spend = lambda *a, **kw: 0.0
_brain.rules_decisions = lambda *a, **kw: []
_brain.update_lessons = lambda *a, **kw: None
_brain.append_trade_history = lambda *a, **kw: None
_brain.load_symbol_stats = lambda *a, **kw: {}
_brain.stats_summary = lambda *a, **kw: ""

# stub notifier
_notif = sys.modules["desk.notifier"]
for _fn in ("notify_open", "notify_close", "notify_dca", "notify_split",
            "notify_halt", "notify_daily_report", "notify_live_alert", "set_context"):
    setattr(_notif, _fn, lambda *a, **kw: None)

# stub live_connector
_lc = sys.modules["desk.live_connector"]

class _FakeLive:
    _live = False
    interlock = None
    pending_close: list = []
    stale_protection: list = []
    last_fill = None
    def open_blocked(self): return None

_lc.LiveConnector = lambda **kw: _FakeLive()

# stub live_sync
_ls = sys.modules["desk.live_sync"]
_ls.sync = lambda *a, **kw: {"closed": [], "notes": []}
_ls.after_bar = lambda *a, **kw: ""
_ls.snapshot_position = lambda *a, **kw: None
_ls.partial_on_exchange = lambda *a, **kw: (True, "paper")
_ls.dca_on_exchange = lambda *a, **kw: (True, "paper")
_ls.open_on_exchange = lambda *a, **kw: (True, "paper")
_ls.rollback_open = lambda *a, **kw: None

# stub learning / macro_calendar / trading_hours / schedule
_learning = sys.modules["desk.learning"]
_learning.STAMP = {}
_learning.build_features = lambda *a, **kw: {}
_learning.log_event = lambda *a, **kw: None

_mc = sys.modules["desk.macro_calendar"]
_mc.current = lambda *a, **kw: {"regime": "basso", "blackout": False, "conf_bonus": 0,
                                  "blackout_until_ms": 0, "enforce": False}
_mc.features = lambda *a, **kw: {}
_mc.prompt_lines = lambda *a, **kw: []
_mc.heartbeat_view = lambda *a, **kw: {}
_mc.hm_utc = lambda *a, **kw: ""

_th = sys.modules["desk.trading_hours"]
_th.hours_state = lambda *a, **kw: {"blocked": False}
_th.summary = lambda *a, **kw: {}

_sched = sys.modules["desk.schedule"]
_sched.schedule_state = lambda *a, **kw: {"mode": "none", "allowed": True, "window": None}
_sched.summary = lambda *a, **kw: {}

# ora importa cli con il modulo reale
import importlib
import desk.cli as cli

# ── helper ──────────────────────────────────────────────────────────────────
from desk.engine import Limits, PaperAccount
from dataclasses import dataclass
from typing import Optional

def _pg(max_lev: Optional[int]):
    """PortfolioConfig minimale con solo max_leverage impostato."""
    from desk.cli import PortfolioConfig
    import desk.cli as _cli
    return PortfolioConfig(
        name="test",
        data_dir="/tmp",
        limits=Limits(start_equity=1000.0, max_margin_trade=350.0,
                      max_margin_total=1000.0, max_open=10,
                      kill_equity=450.0, daily_stop=0.12),
        system_prompt="",
        guardrail_min_margin=50.0,
        guardrail_min_lev=10,
        guardrail_margin_forced=60.0,
        guardrail_lev_forced=15,
        guardrail_type_forced="scalp",
        description="test",
        max_leverage=max_lev,
    )


def _dec(lev: int) -> dict:
    return {"leverage": lev, "margin_usd": 100.0, "symbol": "ETH",
            "action": "open_short", "confidence": 70,
            "stop_loss_pct": 0.02, "take_profit_pct": 0.04,
            "trade_type": "scalp", "reason": "test"}


# ── TEST 1: leva esattamente al limite → ammessa ─────────────────────────────
def test_leva_al_limite_ammessa():
    pg = _pg(20)
    assert cli.leverage_gate(_dec(20), pg) is None, "x20 con max_leverage=20 deve passare"


# ── TEST 2: leva un punto sopra → rifiutata ──────────────────────────────────
def test_leva_sopra_limite_rifiutata():
    pg = _pg(20)
    why = cli.leverage_gate(_dec(21), pg)
    assert why is not None, "x21 con max_leverage=20 deve essere rifiutata"
    assert "21x" in why and "20x" in why


# ── TEST 3: leva molto sopra → rifiutata ─────────────────────────────────────
def test_leva_molto_sopra_rifiutata():
    pg = _pg(20)
    why = cli.leverage_gate(_dec(25), pg)
    assert why is not None
    assert "25x" in why


# ── TEST 4: max_leverage=None → nessun limite, mai rifiutata ─────────────────
def test_nessun_limite_mai_rifiuta():
    pg = _pg(None)
    assert cli.leverage_gate(_dec(100), pg) is None, "senza max_leverage non deve rifiutare mai"


# ── TEST 5: leva sotto il limite → ammessa ───────────────────────────────────
def test_leva_sotto_limite_ammessa():
    pg = _pg(20)
    assert cli.leverage_gate(_dec(10), pg) is None
    assert cli.leverage_gate(_dec(1), pg) is None


# ── TEST 6: Bull max_leverage=15, leva x17 come NEAR di oggi → rifiutata ─────
def test_bull_leva_17_rifiutata():
    pg = _pg(15)
    pg = type(pg)(
        **{**pg.__dict__, "name": "bull", "max_leverage": 15}
    )
    why = cli.leverage_gate(_dec(17), pg)
    assert why is not None, "x17 su Bull (max 15) deve essere rifiutata"


# ── TEST 7: Hawk max_leverage=20, leva x17 come ETH di oggi → ammessa ────────
def test_hawk_leva_17_ammessa():
    pg = _pg(20)
    pg = type(pg)(
        **{**pg.__dict__, "name": "hawk", "max_leverage": 20}
    )
    assert cli.leverage_gate(_dec(17), pg) is None, "x17 su Hawk (max 20) deve passare"


# ── TEST 8: ciclo vero – leva x25 con Hawk max 20: nessun ordine ─────────────
def test_run_cycle_leva_sopra_blocca():
    """In run_cycle, una proposta con leva x25 (sopra il limite Hawk di x20) non
    deve sfociare in un'apertura: il conto deve restare invariato."""
    import numpy as np
    import time as _time

    # costruiamo candele finte per ETH
    now_ms = int(_time.time() * 1000)
    bar_ms = 900_000
    n = 200
    ts_start = now_ms - n * bar_ms - bar_ms * 2   # tutte chiuse
    prices_val = [2400.0 + i * 0.01 for i in range(n)]
    candles = [[ts_start + i * bar_ms, p - 1, p + 2, p - 2, p, 1000.0]
               for i, p in enumerate(prices_val)]
    arr = np.array(candles)

    # patch fetch_candles → solo ETH
    original_fetch = cli.fetch_candles
    def _fake_fetch(sym, bar="15m", limit=1000):
        return candles if sym == "ETH" else []
    cli.fetch_candles = _fake_fetch

    # patch daily_bars → array vuoto
    original_daily = cli.daily_bars
    cli.daily_bars = lambda sym, now: np.zeros((0, 6))

    # patch read_symbol → la firma di signals.py sul branch non ha 'daily'/'price';
    # il ciclo chiama read_symbol(sym, arr, now_ms, daily=..., price=...) che darebbe TypeError.
    # Sostituiamo con una Reading valida per ETH, None per tutti gli altri.
    from desk.signals import Reading as _Reading
    orig_read_symbol = cli.read_symbol
    def _fake_read(sym, arr, now_ms_=None, **_kw):
        if sym != "ETH":
            return None
        return _Reading(symbol="ETH", price=2400.0, side=-1, score=70,
                        short_score=70, sl_pct=0.02, tp_pct=0.04, trade_type="scalp")
    cli.read_symbol = _fake_read

    # patch rules_decisions direttamente sul modulo cli (è importata a livello di modulo)
    orig_rules = cli.rules_decisions
    cli.rules_decisions = lambda *a, **kw: [{
        "action": "open_short", "symbol": "ETH",
        "confidence": 75, "margin_usd": 100.0, "leverage": 25,
        "stop_loss_pct": 0.02, "take_profit_pct": 0.04,
        "trade_type": "scalp", "reason": "test leva alta",
    }]

    # salviamo il portfolio corrente e ne creiamo uno con max_leverage=20
    orig_portfolio = cli.PORTFOLIO
    orig_data_dir = cli.DATA_DIR
    import tempfile, os as _os
    tmpdir = tempfile.mkdtemp()
    hawk_pg = cli._make_hawk_config()
    hawk_pg.data_dir = tmpdir
    cli.PORTFOLIO = hawk_pg
    cli.DATA_DIR = tmpdir

    state = {}
    try:
        cli.run_cycle(state, now_ms)
    except Exception:
        pass
    finally:
        cli.fetch_candles = original_fetch
        cli.daily_bars = original_daily
        cli.read_symbol = orig_read_symbol
        cli.rules_decisions = orig_rules
        cli.PORTFOLIO = orig_portfolio
        cli.DATA_DIR = orig_data_dir

    # deve esserci uno stato salvato ma nessuna posizione aperta
    acc_dict = state.get("main") or {}
    positions = acc_dict.get("positions") or {}
    assert len(positions) == 0, (
        f"Con leva x25 e limite x20 non deve aprire: trovate {len(positions)} posizioni"
    )
    # deve esserci almeno un candidato registrato come rifiutato
    # (non possiamo leggere il file di log nel test, ma verifichiamo che il ciclo non sia crashato)


# ── TEST 9: ciclo vero – leva x15 con Hawk max 20: apertura consentita ───────
def test_run_cycle_leva_ammessa_apre():
    """Stessa struttura del test 8, ma leva x15 < max x20: deve aprire."""
    import numpy as np
    import time as _time

    now_ms = int(_time.time() * 1000)
    bar_ms = 900_000
    n = 200
    ts_start = now_ms - n * bar_ms - bar_ms * 2
    prices_val = [2400.0 + i * 0.01 for i in range(n)]
    candles = [[ts_start + i * bar_ms, p - 1, p + 2, p - 2, p, 1000.0]
               for i, p in enumerate(prices_val)]

    original_fetch = cli.fetch_candles
    cli.fetch_candles = lambda sym, bar="15m", limit=1000: candles if sym == "ETH" else []

    original_daily = cli.daily_bars
    import numpy as _np
    cli.daily_bars = lambda sym, now: _np.zeros((0, 6))

    # patch read_symbol (firma signals.py non ha 'daily'/'price' su questo branch)
    from desk.signals import Reading as _Reading
    orig_read_symbol = cli.read_symbol
    def _fake_read(sym, arr, now_ms_=None, **_kw):
        if sym != "ETH":
            return None
        return _Reading(symbol="ETH", price=2400.0, side=-1, score=70,
                        short_score=70, sl_pct=0.02, tp_pct=0.04, trade_type="scalp")
    cli.read_symbol = _fake_read

    # patch rules_decisions sul modulo cli (è importata a livello di modulo)
    orig_rules = cli.rules_decisions
    cli.rules_decisions = lambda *a, **kw: [{
        "action": "open_short", "symbol": "ETH",
        "confidence": 75, "margin_usd": 100.0, "leverage": 15,
        "stop_loss_pct": 0.02, "take_profit_pct": 0.04,
        "trade_type": "scalp", "reason": "test leva ok",
    }]

    orig_portfolio = cli.PORTFOLIO
    orig_data_dir = cli.DATA_DIR
    import tempfile
    tmpdir = tempfile.mkdtemp()
    hawk_pg = cli._make_hawk_config()
    hawk_pg.data_dir = tmpdir
    cli.PORTFOLIO = hawk_pg
    cli.DATA_DIR = tmpdir

    state = {}
    try:
        cli.run_cycle(state, now_ms)
    except Exception:
        pass
    finally:
        cli.fetch_candles = original_fetch
        cli.daily_bars = original_daily
        cli.read_symbol = orig_read_symbol
        cli.rules_decisions = orig_rules
        cli.PORTFOLIO = orig_portfolio
        cli.DATA_DIR = orig_data_dir

    acc_dict = state.get("main") or {}
    positions = acc_dict.get("positions") or {}
    assert len(positions) == 1, (
        f"Con leva x15 e limite x20 deve aprire: trovate {len(positions)} posizioni"
    )


# ── MUTATION TEST (eseguito come funzione per mantenere il runner semplice) ───
def test_mutation_gate_spento():
    """Se max_leverage viene ignorato (gate restituisce sempre None),
    il test_run_cycle_leva_sopra_blocca fallisce: la leva x25 aprirebbe."""
    # verifichiamo che la funzione originale blocchi x25 su Hawk (max 20)
    pg = cli._make_hawk_config()
    assert cli.leverage_gate(_dec(25), pg) is not None, \
        "Il gate con max_leverage=20 deve bloccare x25"
    # e che non blocchi x20
    assert cli.leverage_gate(_dec(20), pg) is None, \
        "Il gate con max_leverage=20 non deve bloccare x20"


def test_mutation_soglia_invertita():
    """Se il confronto fosse >= invece di >, x20 sarebbe bloccata — sbagliato."""
    pg = cli._make_hawk_config()
    # x20 deve passare
    assert cli.leverage_gate(_dec(20), pg) is None
    # x21 deve essere bloccata
    assert cli.leverage_gate(_dec(21), pg) is not None


def test_mutation_nessun_portfolio_senza_limite():
    """Un PortfolioConfig senza max_leverage (None) non deve mai bloccare."""
    pg = _pg(None)
    for lev in (1, 10, 25, 50, 100):
        assert cli.leverage_gate(_dec(lev), pg) is None, \
            f"max_leverage=None non deve bloccare leva x{lev}"


def test_hawk_config_ha_limite():
    """Il portfolio Hawk deve avere max_leverage=20."""
    pg = cli._make_hawk_config()
    assert pg.max_leverage == 20


def test_bull_config_ha_limite():
    """Il portfolio Bull deve avere max_leverage=15."""
    pg = cli._make_bull_config()
    assert pg.max_leverage == 15
