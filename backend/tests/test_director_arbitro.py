"""Test Arbitro v1.

Usa stub locali per i contratti v1_1 (che risiedono in work/director-chatgpt
e si risolveranno dopo il merge). In questo modo i test girano senza dipendenze
da quel branch e rimangono validi anche dopo il merge.

Comando: PYTHONPATH=backend PYTHONDONTWRITEBYTECODE=1 python -B -m unittest
         backend/tests/test_director_arbitro.py -v
"""
import sys
import types
import unittest
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import patch


# ── Stub contracts module ─────────────────────────────────────────────────────
# Minimal dataclasses that replicate only the fields the Arbitro reads.
# Validation is intentionally absent: that is contracts' job, tested separately.

@dataclass
class _PositionView:
    position_key: str
    symbol: str
    side: str
    trade_type: str = "scalp"
    entry_price: float = 1.0
    stop: float = 0.9
    margin_usd: float = 100.0
    open_ms: int = 1_000_000


@dataclass
class _PortfolioSnapshot:
    portfolio_id: str
    run_key: str = "test"
    asof_ms: int = 2_000_000
    start_equity_usd: float = 1000.0
    equity_usd: float = 1000.0
    cash_usd: float = 900.0
    margin_used_usd: float = 100.0
    max_margin_total_usd: float = 500.0
    max_margin_trade_usd: float = 300.0
    max_open: int = 4
    positions: tuple = field(default_factory=tuple)
    halted: bool = False
    schema_version: int = 1
    contract_version: str = "1.1"


@dataclass
class _Candidate:
    candidate_id: str
    frame_id: str = "f1"
    symbol: str = "BTC"
    strategy_id: str = "s1"
    strategy_version: str = "1"
    params_hash: str = "abc"
    side: str = "LONG"
    signal_bar_open_ms: int = 1_000_000
    bar_ms: int = 900_000
    earliest_entry_ms: int = 1_900_000
    proposed_entry: float = 30000.0
    stop: float = 29400.0  # 2% below
    target: float = 31200.0  # 4% above → RR=2
    time_exit_bars: int = 10
    cost_bp_roundtrip: float = 5.0
    evidence_ids: tuple = ("e1",)
    regime_match: bool = True
    schema_version: int = 1
    contract_version: str = "1.1"


@dataclass
class _DirectorAdvice:
    advice_id: str
    frame_id: str = "f1"
    portfolio_id: str = "hawk"
    asof_ms: int = 2_000_000
    provider_id: str = "shadow"
    model_id: str = "test"
    prompt_version: str = "v1"
    action: str = "NO_TRADE"
    thesis: str = "test thesis"
    counterthesis: str = "counter"
    invalidate_if: str = "invalidate"
    uncertainty_0_1: float = 0.3
    evaluated_candidate_ids: tuple = ()
    selected_candidate_id: Optional[str] = None
    position_key: Optional[str] = None
    hold_conviction_0_100: Optional[int] = None
    review_after_bars: Optional[int] = None
    review_timeframe_ms: Optional[int] = None
    no_trade_reason: Optional[str] = "no setup"
    open_conviction_0_100: Optional[int] = None
    close_fraction: Optional[float] = None
    schema_version: int = 1
    contract_version: str = "1.1"


# Inject stub contracts module so the Arbitro import resolves locally
_stub_v1_1 = types.ModuleType("backend.director.contracts.v1_1")
_stub_v1_1.DirectorAdvice = _DirectorAdvice
_stub_v1_1.PortfolioSnapshot = _PortfolioSnapshot
_stub_v1_1.Candidate = _Candidate
_stub_v1_1.PositionView = _PositionView

_stub_contracts = types.ModuleType("backend.director.contracts")

sys.modules.setdefault("backend", types.ModuleType("backend"))
sys.modules.setdefault("backend.director", types.ModuleType("backend.director"))
sys.modules.setdefault("backend.director.contracts", _stub_contracts)
sys.modules["backend.director.contracts.v1_1"] = _stub_v1_1

# Also stub decisions so size_position is importable
_stub_decisions = types.ModuleType("backend.director.ai_shadow.decisions")

def _size_position_stub(cfg, equity, side, fill, sl, tier_cap, slip_bp, maint, sl_liq_frac):
    dist = abs(fill - sl) / fill
    if dist <= 0:
        return None, "stop_non_valido", 0.0
    risk = equity * cfg.risk_pct / 100.0
    margin = min(risk / dist, cfg.max_margin_trade)
    if margin < 10.0:
        return None, "margine_troppo_basso", 0.0
    lev = max(1, round((risk / dist) / margin))
    return round(margin, 2), lev, round(margin * lev * dist, 4)

_stub_decisions.size_position = _size_position_stub

sys.modules.setdefault("backend.director.ai_shadow", types.ModuleType("backend.director.ai_shadow"))
sys.modules["backend.director.ai_shadow.decisions"] = _stub_decisions

# Now import the module under test
from backend.director.arbitro import Arbitro, ArbitroConfig  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _portfolio(portfolio_id="hawk", halted=False, positions=()):
    return _PortfolioSnapshot(portfolio_id=portfolio_id, halted=halted, positions=tuple(positions))


def _advice(**kw):
    defaults = dict(
        advice_id="adv1", portfolio_id="hawk",
        action="NO_TRADE", no_trade_reason="no setup",
        evaluated_candidate_ids=(),
    )
    defaults.update(kw)
    return _DirectorAdvice(**defaults)


def _candidate(**kw):
    defaults = dict(candidate_id="cand1")
    defaults.update(kw)
    return _Candidate(**defaults)


def _position(**kw):
    defaults = dict(position_key="BTC-001", symbol="BTC", side="LONG")
    defaults.update(kw)
    return _PositionView(**defaults)


BAR_T = 2_100_000
PX = {"BTC": 30000.0, "ETH": 2000.0}
CFG = ArbitroConfig()
ARB = Arbitro(CFG)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestArbitroNoTrade(unittest.TestCase):
    def test_no_trade_accepted(self):
        adv = _advice(action="NO_TRADE", no_trade_reason="flat market")
        r = ARB.arbitrate(adv, _portfolio(), {}, PX, BAR_T)
        self.assertTrue(r.accepted)
        self.assertEqual(r.reason, "no_trade")
        self.assertIsNone(r.order)

    def test_halted_portfolio_rejected(self):
        adv = _advice(action="NO_TRADE", no_trade_reason="flat")
        r = ARB.arbitrate(adv, _portfolio(halted=True), {}, PX, BAR_T)
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "portfolio_halted")

    def test_portfolio_id_mismatch(self):
        adv = _advice(portfolio_id="bull")
        r = ARB.arbitrate(adv, _portfolio(portfolio_id="hawk"), {}, PX, BAR_T)
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "portfolio_id_mismatch")


class TestArbitroHold(unittest.TestCase):
    def test_hold_accepted(self):
        pos = _position(position_key="BTC-001", symbol="BTC")
        adv = _advice(action="HOLD", position_key="BTC-001",
                      no_trade_reason=None, hold_conviction_0_100=70,
                      evaluated_candidate_ids=())
        r = ARB.arbitrate(adv, _portfolio(positions=[pos]), {}, PX, BAR_T)
        self.assertTrue(r.accepted)
        self.assertEqual(r.order["kind"], "hold")
        self.assertEqual(r.order["symbol"], "BTC")

    def test_hold_position_not_found(self):
        adv = _advice(action="HOLD", position_key="ETH-999",
                      no_trade_reason=None, hold_conviction_0_100=70)
        r = ARB.arbitrate(adv, _portfolio(), {}, PX, BAR_T)
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "position_not_found")


class TestArbitroClose(unittest.TestCase):
    def test_close_accepted(self):
        pos = _position(position_key="BTC-001", symbol="BTC")
        adv = _advice(action="CLOSE", position_key="BTC-001", no_trade_reason=None)
        r = ARB.arbitrate(adv, _portfolio(positions=[pos]), {}, PX, BAR_T)
        self.assertTrue(r.accepted)
        self.assertEqual(r.order["kind"], "close")


class TestArbitroPartialClose(unittest.TestCase):
    def test_partial_close_accepted(self):
        pos = _position(position_key="BTC-001", symbol="BTC")
        adv = _advice(action="PARTIAL_CLOSE", position_key="BTC-001",
                      no_trade_reason=None, close_fraction=0.5)
        r = ARB.arbitrate(adv, _portfolio(positions=[pos]), {}, PX, BAR_T)
        self.assertTrue(r.accepted)
        self.assertEqual(r.order["kind"], "partial")
        self.assertAlmostEqual(r.order["fraction"], 0.5)

    def test_partial_close_fraction_too_small(self):
        pos = _position(position_key="BTC-001", symbol="BTC")
        adv = _advice(action="PARTIAL_CLOSE", position_key="BTC-001",
                      no_trade_reason=None, close_fraction=0.05)
        r = ARB.arbitrate(adv, _portfolio(positions=[pos]), {}, PX, BAR_T)
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "frazione_non_valida")


class TestArbitroOpen(unittest.TestCase):
    def _open_advice(self, cand_id="cand1", conviction=70, **kw):
        return _advice(
            action="OPEN", no_trade_reason=None,
            evaluated_candidate_ids=(cand_id,),
            selected_candidate_id=cand_id,
            open_conviction_0_100=conviction,
            **kw,
        )

    def test_open_accepted(self):
        # BTC at 30000, stop 29400 (2%), target 31200 (4%) → RR=2 ✓
        cand = _candidate(candidate_id="cand1", symbol="BTC",
                          stop=29400.0, target=31200.0, side="LONG")
        adv = self._open_advice()
        r = ARB.arbitrate(adv, _portfolio(), {"cand1": cand}, PX, BAR_T)
        self.assertTrue(r.accepted, r.reason)
        self.assertEqual(r.order["kind"], "open")
        self.assertEqual(r.order["symbol"], "BTC")
        self.assertIsNotNone(r.margin_usd)
        self.assertGreater(r.margin_usd, 0)

    def test_open_conviction_too_low(self):
        cand = _candidate(candidate_id="cand1", symbol="BTC",
                          stop=29400.0, target=31200.0)
        adv = self._open_advice(conviction=30)
        r = ARB.arbitrate(adv, _portfolio(), {"cand1": cand}, PX, BAR_T)
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "convinzione_bassa")

    def test_open_rr_too_low(self):
        # target only 0.5% above → RR < 1.5
        cand = _candidate(candidate_id="cand1", symbol="BTC",
                          stop=29400.0, target=30150.0)  # RR=0.25
        adv = self._open_advice()
        r = ARB.arbitrate(adv, _portfolio(), {"cand1": cand}, PX, BAR_T)
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "rr_basso")

    def test_open_slot_pieni(self):
        positions = [_position(position_key=f"POS-{i:03d}", symbol=f"COIN{i}")
                     for i in range(CFG.max_open)]
        cand = _candidate(candidate_id="cand1", symbol="BTC",
                          stop=29400.0, target=31200.0)
        adv = self._open_advice()
        r = ARB.arbitrate(adv, _portfolio(positions=positions), {"cand1": cand}, PX, BAR_T)
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "slot_pieni")

    def test_open_candidate_not_found(self):
        adv = self._open_advice(cand_id="missing")
        r = ARB.arbitrate(adv, _portfolio(), {}, PX, BAR_T)
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "candidate_not_found")


if __name__ == "__main__":
    unittest.main()
