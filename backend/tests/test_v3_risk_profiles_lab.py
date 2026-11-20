"""Profili di rischio proposti (ops/brain-unico/risk/profiles.py): i numeri del documento coincidono con il RiskManager
reale (`quote_paper_risk`) sugli stessi input. Nessun parametro operativo viene letto o modificato."""
from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.v3.risk import RiskPolicy, RiskRequest, quote_paper_risk

_P = Path(__file__).resolve().parents[2] / "ops" / "brain-unico" / "risk" / "profiles.py"
_spec = importlib.util.spec_from_file_location("risk_profiles_lab", _P)
PR = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = PR
_spec.loader.exec_module(PR)


def _policy(p):
    return RiskPolicy(max_loss_fraction=D(str(p.risk)), max_open_risk_fraction=D(str(p.open_risk)),
                      max_position_margin_fraction=D(str(p.pos_margin)),
                      max_total_margin_fraction=D(str(p.total_margin)), minimum_equity=D(str(p.floor)),
                      estimated_roundtrip_cost_bp=D("16"), liquidation_buffer_fraction=D("0.5"),
                      max_loss_margin_fraction=D(str(p.loss_margin)) if p.loss_margin is not None else None,
                      min_leverage=p.min_lev, max_leverage=p.max_lev)


def _real(p, stop, lev):
    price = D("100")
    req = RiskRequest(equity=D("2000"), available_cash=D("2000"), margin_used=D("0"), existing_open_risk=D("0"),
                      entry_price=price, stop_price=price * (1 - D(str(stop))), side=1, requested_leverage=lev,
                      exchange_leverage_limit=125, quantity_step=D("0.000001"), minimum_notional=D("5"),
                      maintenance_fraction=D("0.005"), market_data_fresh=True, paused=False, daily_loss_latched=False)
    return quote_paper_risk(_policy(p), req)


@pytest.mark.parametrize("p", (PR.HISTORICAL,) + PR.PROFILES, ids=lambda p: p.name)
@pytest.mark.parametrize("stop", (0.003, 0.005, 0.01, 0.02))
def test_the_table_matches_the_real_risk_manager(p, stop):
    q = PR.quote(p, stop)
    if not q["allowed"] and q["reasons"] == ["costi (filtro proposto)"]:
        return                                                    # filtro proposto: non esiste nel runtime
    if not q["allowed"]:
        real = _real(p, stop, p.min_lev)
        assert not real.allowed and real.reason in ("margin_loss_ratio_exceeded", "stop_near_liquidation")
        return
    real = _real(p, stop, q["leverage"])
    assert real.allowed, real.reason
    assert float(real.notional) == pytest.approx(q["notional"], rel=1e-4)
    assert float(real.margin) == pytest.approx(q["margin"], rel=1e-4)
    assert float(real.notional) * (stop + PR.COST) == pytest.approx(q["eff_risk"], rel=1e-4)


def test_loss_at_stop_equals_the_chosen_risk_whatever_the_leverage():
    p = PR.PROFILES[1]
    for lev in (8, 10, 20, 30):                                   # da 8x il tetto di margine non limita
        r = _real(p, 0.005, lev)
        assert r.allowed and float(r.notional) * (0.005 + PR.COST) == pytest.approx(20.0, rel=1e-4)
    low = _real(p, 0.005, 5)                                      # a 5x il margine riduce la size: rischio < 20
    assert low.allowed and float(low.notional) * (0.005 + PR.COST) == pytest.approx(13.2, rel=1e-4)


def test_the_proposals_are_only_proposals():
    s = _P.read_text()
    assert "open(" not in s and "import os" not in s              # nessuna lettura/scrittura di file
    assert all(p.min_lev == 1 and p.loss_margin is None for p in PR.PROFILES)
    assert [round(PR.summary(p)["day_halt_r"], 6) for p in PR.PROFILES] == [4.0, 4.0, 4.0]
