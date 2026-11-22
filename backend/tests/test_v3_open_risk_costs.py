"""Rischio aperto ricostruito dal journal = perdita STIMATA allo stop del RiskManager (costi inclusi), stessa formula.
Profilo B reale (runner_config_brain_unico_paper_b.json): 1 % per operazione, 4 % aperto, pavimento 1.600, max 4.
Solo PAPER, journal sintetico; lo storico non viene mai riscritto."""
from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.tests.test_brain_f7_outcomes import _hand
from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.executor.paper_close import close_paper
from backend.v3.risk import RiskRequest, estimated_loss_per_unit, quote_paper_risk
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.cycle import snapshot_from_summary
from backend.v3.runner.post_ai_guard import MAX_OPEN_POSITIONS

CFG = Path(__file__).resolve().parents[1] / "v3" / "runner" / "runner_config_brain_unico_paper_b.json"
POL = load_runner_config(CFG.read_bytes()).risk_policy
RUN = "r-costi"
T = 1_800_000_000_000
EQ0 = D("2000")


def _snap(j):
    return snapshot_from_summary(build_summary(j, "brain", RUN), EQ0, POL.estimated_roundtrip_cost_bp)


def _try_open(j, symbol, stop_frac, ts, lev=30):
    """Come il ciclo: istantanea dal journal -> RiskManager -> esecuzione PAPER con la quotazione approvata."""
    snap = _snap(j)
    stop = D("100") * (1 - stop_frac)
    q = quote_paper_risk(POL, RiskRequest(snap.equity, snap.available_cash, snap.margin_used, snap.existing_open_risk,
                                          D("100"), stop, 1, lev, 125, D("0.000001"), D("5"), D("0.005"),
                                          True, False, False))
    if not q.allowed:
        return None
    d = _hand(side=1, entry="100", stop=str(stop), qty=str(q.quantity), margin=str(q.margin), lev=lev, symbol=symbol)
    execute_paper(d, portfolio_id="brain", run_id=RUN, journal=j, now_ms=ts)
    return q


def _journal(tmp_path, name="j.db"):
    j = EventJournal(tmp_path / name)
    j.init_schema()
    return j


def test_one_formula_for_new_and_open_positions():
    assert estimated_loss_per_unit(D("100"), D("99"), D("16")) == D("1.16")
    assert estimated_loss_per_unit(D("100"), D("101"), D("16")) == D("1.16")          # short: distanza assoluta


@pytest.mark.parametrize("stop_frac", (D("0.005"), D("0.003"), D("0.01")))
def test_open_risk_from_the_journal_equals_the_risk_manager_estimate(tmp_path, stop_frac):
    j = _journal(tmp_path)
    total = D("0")
    for k in range(3):
        q = _try_open(j, "S%dUSDT" % k, stop_frac, T + k)
        total += q.worst_case_loss_estimate
        assert abs(_snap(j).existing_open_risk - total) < D("0.0001")               # parita' dopo ogni apertura


@pytest.mark.parametrize("stop_frac", (D("0.005"), D("0.003")))
def test_after_four_openings_the_total_estimate_stays_within_four_percent(tmp_path, stop_frac):
    """Prima della correzione: con 8 simboli si aprivano 8 posizioni e la stima arrivava al 5,3-6,1 %."""
    j = _journal(tmp_path)
    opened = [q for k in range(8) if (q := _try_open(j, "S%dUSDT" % k, stop_frac, T + k)) is not None]
    est = sum(q.worst_case_loss_estimate for q in opened)
    assert est <= EQ0 * POL.max_open_risk_fraction + D("0.01")                     # <= 80 USDT
    assert len(opened) <= MAX_OPEN_POSITIONS                                        # anche senza il tetto numerico
    assert all(q.worst_case_loss_estimate <= EQ0 * POL.max_loss_fraction + D("0.01") for q in opened)


def test_with_a_changed_equity_the_residual_budget_is_respected(tmp_path):
    j = _journal(tmp_path)
    # perdita realizzata: l'equity scende a circa 1.900
    d = _hand(side=1, entry="100", stop="50", qty="10", margin="100", lev=10, symbol="LOSSUSDT")
    pid = execute_paper(d, portfolio_id="brain", run_id=RUN, journal=j, now_ms=T).position_id
    close_paper(portfolio_id="brain", run_id=RUN, position_id=pid, exit_price=D("90"), reason="manual",
                fee_bps=6, journal=j, now_ms=T + 1)
    eq = _snap(j).equity
    assert D("1890") < eq < D("1900")
    opened = [q for k in range(8) if (q := _try_open(j, "S%dUSDT" % k, D("0.005"), T + 10 + k)) is not None]
    est = sum(q.worst_case_loss_estimate for q in opened)
    assert est <= eq * POL.max_open_risk_fraction + D("0.01")                       # 4 % dell'equity ATTUALE
    assert abs(_snap(j).existing_open_risk - est) < D("0.0001")


def test_near_the_floor_the_estimate_cannot_cross_1600(tmp_path):
    j = _journal(tmp_path)
    d = _hand(side=1, entry="100", stop="50", qty="10", margin="100", lev=10, symbol="LOSSUSDT")
    pid = execute_paper(d, portfolio_id="brain", run_id=RUN, journal=j, now_ms=T).position_id
    close_paper(portfolio_id="brain", run_id=RUN, position_id=pid, exit_price=D("63"), reason="manual",
                fee_bps=6, journal=j, now_ms=T + 1)
    eq = _snap(j).equity
    assert D("1620") < eq < D("1640")                                               # 20-40 USDT sopra il pavimento
    opened = [q for k in range(8) if (q := _try_open(j, "S%dUSDT" % k, D("0.003"), T + 10 + k)) is not None]
    est = sum(q.worst_case_loss_estimate for q in opened)
    assert opened and est <= eq - POL.minimum_equity + D("0.01")                    # la STIMA non scavalca 1.600


def test_the_journal_is_not_rewritten(tmp_path):
    j = _journal(tmp_path)
    _try_open(j, "AUSDT", D("0.005"), T)
    before = [(e.event.event_id, e.event.payload) for e in j.list_run("brain", RUN)]
    for _ in range(3):
        _snap(j)
    assert [(e.event.event_id, e.event.payload) for e in j.list_run("brain", RUN)] == before


def test_an_invalid_cost_is_refused():
    with pytest.raises(ValueError):
        snapshot_from_summary(None, EQ0, 16)                                       # int, non Decimal
