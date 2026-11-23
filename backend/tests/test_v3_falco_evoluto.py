"""Falco Evoluto (backend/v3/falco_evoluto.py): regole SHORT/LONG, correzioni dell'originale, AI consulente raro,
integrazione con il RiskManager del profilo aggressivo (leva 15-45x, margine 100-250, rischio percentuale)."""
from __future__ import annotations

import json
import math
from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.v3.brain_f2.contracts import DecisionKind, MarketContext, ProposalStatus
from backend.v3.brain_f2.engine import BrainEngine, BrainPortfolioSnapshot
from backend.v3.brain_f2.reviewer import MockClaudeReviewer
from backend.v3.brain_f3.providers import TransportResponse
from backend.v3.events import EventJournal
from backend.v3.falco_evoluto import (
    NT_AI_DOWN, NT_AI_NO, NT_REGIME, NT_SCORE, ORIGIN, SRC_AI, SRC_LONG, SRC_SHORT, FalcoEvolutoAnalyst,
    daily_from_4h, ema_sma_seeded, evaluate,
)
from backend.v3.features.indicators import Bar
from backend.v3.runner.config import load_runner_config

H1, H4, DAY = 3_600_000, 14_400_000, 86_400_000
T_END = 1_795_000_000_000 // DAY * DAY
CFG = Path(__file__).resolve().parents[1] / "v3" / "runner" / "runner_config_falco_evoluto_paper.json"


def series(n, step, drift, wiggle=0.004, vol_last=1.0, end=T_END):
    rows, px = [], 100.0
    t0 = end - n * step
    for i in range(n):
        o = px
        c = o * (1 + drift + wiggle * math.sin(i * 1.7))
        h, lo = max(o, c) * 1.002, min(o, c) * 0.998
        rows.append(Bar(t0 + i * step, D(str(round(o, 6))), D(str(round(h, 6))), D(str(round(lo, 6))),
                        D(str(round(c, 6))), D(str(1000 * (vol_last if i == n - 1 else 1.0)))))
        px = c
    return rows


DOWN = {"1h": series(120, H1, -0.0015, vol_last=1.4), "4h": series(300, H4, -0.003, 0.003)}
UP = {"1h": series(120, H1, 0.0006, 0.006, vol_last=1.4), "4h": series(300, H4, 0.003, 0.003)}


class FakeAI:
    def __init__(self, answer=None, fail=False):
        self.answer, self.fail, self.calls = answer, fail, 0

    def __call__(self, payload):
        self.calls += 1
        if self.fail:
            raise RuntimeError("down")
        return TransportResponse(200, {"choices": [{"finish_reason": "stop",
                                                    "message": {"content": json.dumps(self.answer)}}]})


def analyst(bars, ai=None, gate=True):
    return FalcoEvolutoAnalyst(bars_source=lambda s: bars, max_leverage=45, transport=ai or FakeAI(fail=True),
                               model="deepseek-flash", spending_gate=lambda p: gate, ai_enabled=True)


def ctx(bars, regime, symbol="BTCUSDT"):
    return MarketContext(symbol, bars["1h"][-1].close, T_END, regime)


def test_short_evoluto_opens_in_a_confirmed_downtrend_without_calling_the_ai():
    ai = FakeAI(fail=True)
    a = analyst(DOWN, ai)
    d = a.analyze(ctx(DOWN, "TREND_DOWN"), [])
    assert d.kind == DecisionKind.OPEN and d.proposal.side == -1 and d.sources == [SRC_SHORT]
    assert d.proposal.originating_ai == ORIGIN and d.proposal.leverage == 45 and ai.calls == 0
    ev = evaluate("BTCUSDT", "TREND_DOWN", float(DOWN["1h"][-1].close), DOWN["1h"], DOWN["4h"])
    assert d.proposal.stop_price > d.proposal.entry_price                       # stop dello short sopra l'ingresso
    assert float(d.proposal.stop_price / d.proposal.entry_price - 1) == pytest.approx(ev.stop_fraction, rel=1e-6)
    assert ev.stop_fraction == pytest.approx(min(0.035, max(0.003, 1.2 * ev.facts["atr_1h_pct"])), rel=1e-3)


def test_long_module_needs_every_confirmation():
    d = analyst(UP).analyze(ctx(UP, "TREND_UP"), [])
    assert d.kind == DecisionKind.OPEN and d.proposal.side == 1 and d.sources == [SRC_LONG]
    # ipercomprato (RSI > 70): nessun LONG anche con trend e punteggio alti
    hot = {"1h": series(120, H1, 0.0012, 0.004, vol_last=1.4), "4h": UP["4h"]}
    assert evaluate("BTCUSDT", "TREND_UP", float(hot["1h"][-1].close), hot["1h"], hot["4h"]).code == NT_SCORE
    # volume sotto la media: nessun LONG
    quiet = {"1h": series(120, H1, 0.0006, 0.006, vol_last=0.8), "4h": UP["4h"]}
    assert analyst(quiet).analyze(ctx(quiet, "TREND_UP"), []).kind == DecisionKind.NO_TRADE


@pytest.mark.parametrize("regime", ["RANGE", "UNCERTAIN", "SHOCK", "UNKNOWN"])
def test_no_forced_opens_in_range_uncertain_or_shock(regime):
    ai = FakeAI(fail=True)
    for bars in (UP, DOWN):
        d = analyst(bars, ai).analyze(ctx(bars, regime), [])
        assert d.kind == DecisionKind.NO_TRADE and d.rationale == NT_REGIME
    assert ai.calls == 0


def test_ema200_4h_and_daily_trend_need_enough_data():
    short4h = {"1h": UP["1h"], "4h": UP["4h"][-150:]}            # 150 candele 4h: EMA200 non definibile
    ev = evaluate("BTCUSDT", "TREND_UP", float(UP["1h"][-1].close), short4h["1h"], short4h["4h"])
    assert ev.facts["trend_4h"] is None and ev.side == 0          # il LONG richiede il trend 4h: niente apertura
    full = evaluate("BTCUSDT", "TREND_UP", float(UP["1h"][-1].close), UP["1h"], UP["4h"])
    assert full.long_score - ev.long_score >= 20                   # i 20 punti del trend 4h solo con dati veri
    assert ema_sma_seeded([1.0] * 10, 20) == [None] * 10
    e = ema_sma_seeded([float(i) for i in range(1, 31)], 20)
    assert e[18] is None and e[19] == pytest.approx(10.5)
    # giorni UTC: tiene solo quelli con 6 candele 4h contigue
    bars = series(21, H4, 0.001, end=T_END + 2 * H4)              # 1 candela + 3 giorni completi + 2 candele
    assert len({b.open_time_ms // DAY for b in bars}) == 5 and len(daily_from_4h(bars)) == 3


def test_short_against_an_up_market_on_4h_and_1d_is_vetoed():
    mixed = {"1h": DOWN["1h"], "4h": UP["4h"]}
    ev = evaluate("BTCUSDT", "TREND_DOWN", float(mixed["1h"][-1].close), mixed["1h"], mixed["4h"])
    assert ev.facts["trend_4h"] == 1 and ev.facts["trend_1d"] == 1 and ev.side == 0


def test_ai_is_only_a_rare_consultant_that_can_confirm_or_refuse():
    # regime EXPANSION: consulto. CONFIRM -> apertura con la conferma registrata
    ok = FakeAI({"decision": "CONFIRM"})
    d = analyst(DOWN, ok).analyze(ctx(DOWN, "EXPANSION"), [])
    assert d.kind == DecisionKind.OPEN and d.sources == [SRC_SHORT, SRC_AI] and ok.calls == 1
    no = FakeAI({"decision": "NO_TRADE"})
    d = analyst(DOWN, no).analyze(ctx(DOWN, "EXPANSION"), [])
    assert d.kind == DecisionKind.NO_TRADE and d.rationale == NT_AI_NO
    # AI giu', budget esaurito, risposta che tenta di cambiare il lato: NO_TRADE, mai un'apertura
    for ai, gate in ((FakeAI(fail=True), True), (FakeAI({"decision": "CONFIRM"}), False),
                     (FakeAI({"decision": "CONFIRM", "side": "LONG"}), True), (FakeAI({"decision": "MAYBE"}), True)):
        d = analyst(DOWN, ai, gate).analyze(ctx(DOWN, "EXPANSION"), [])
        assert d.kind == DecisionKind.NO_TRADE and d.rationale == NT_AI_DOWN
    assert FakeAI({"decision": "CONFIRM"}).calls == 0


def _engine(tmp_path, equity="1000"):
    j = EventJournal(str(tmp_path / "journal.db"))
    j.init_schema()
    policy = load_runner_config(CFG.read_bytes()).risk_policy
    return BrainEngine(analyst(DOWN), MockClaudeReviewer(), risk_policy=policy,
                       portfolio_snapshot=BrainPortfolioSnapshot(D(equity), D(equity), D(0), D(0)),
                       market_params={"exchange_leverage_limit": 50, "quantity_step": D("0.0001"),
                                      "minimum_notional": D(5), "maintenance_fraction": D("0.005"),
                                      "market_data_fresh": True, "paused": False, "daily_loss_latched": False},
                       journal=j, run_id="falco-evoluto-test"), policy


def test_risk_manager_turns_the_rules_proposal_into_an_aggressive_but_bounded_trade(tmp_path):
    eng, policy = _engine(tmp_path)
    d = analyst(DOWN).analyze(ctx(DOWN, "TREND_DOWN"), [])
    out = eng._apply_risk_gate(d, ctx(DOWN, "TREND_DOWN"))
    q = out.risk_quote
    assert out.status == ProposalStatus.APPROVED and 15 <= out.proposal.leverage <= 45
    assert q.worst_case_loss_estimate <= D("1000") * policy.max_loss_fraction          # <= 4 % dell'equity
    assert q.worst_case_loss_estimate <= q.margin * policy.max_loss_margin_fraction    # <= 20 % del margine
    assert D("100") <= q.margin <= D("250")
    # stop largo (3 %): nessuna leva >= 15x rispetta il 20 % sul margine -> NO_TRADE, lo stop NON viene stretto
    wide = analyst(DOWN).analyze(ctx(DOWN, "TREND_DOWN"), [])
    from dataclasses import replace
    wide.proposal = replace(wide.proposal, stop_price=wide.proposal.entry_price * D("1.03"))
    out = eng._apply_risk_gate(wide, ctx(DOWN, "TREND_DOWN"))
    assert out.kind == DecisionKind.NO_TRADE and out.status == ProposalStatus.RISK_REJECTED
