"""Configurazione e mandato del profilo B (decisione del proprietario 21/11/2026), DA ESAMINARE prima dell'attivazione.
Il modello di mandato NON e' approvato; nessun file operativo viene letto o scritto fuori dalla cartella di test."""
from __future__ import annotations

import json
from decimal import Decimal as D
from pathlib import Path

from backend.v3.brain_f2.engine import _policy_hash
from backend.v3.risk import RiskRequest, quote_paper_risk
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.wiring import MandateFile

HERE = Path(__file__).resolve().parents[1] / "v3" / "runner"
CFG = HERE / "runner_config_brain_unico_paper_b.json"
TPL = HERE / "mandate_brain_unico_paper_b.TEMPLATE.json"
RUN = "brain-unico-paper-rc1"


def _cfg():
    return load_runner_config(CFG.read_bytes())


def test_the_config_holds_exactly_the_approved_profile_b():
    c, p = _cfg(), _cfg().risk_policy
    assert (p.max_loss_fraction, p.max_open_risk_fraction, p.max_position_margin_fraction,
            p.max_total_margin_fraction, p.minimum_equity) == (D("0.01"), D("0.04"), D("0.20"), D("0.50"), D("1600"))
    assert (p.min_leverage, p.max_leverage, p.max_loss_margin_fraction) == (1, 30, D("1"))
    assert (p.estimated_roundtrip_cost_bp, p.liquidation_buffer_fraction) == (D("16"), D("0.5"))
    assert (c.daily_loss_warn, c.daily_loss_halt) == (D("0.03"), D("0.04"))
    assert c.initial_equity == D("2000")


def test_only_the_profile_fields_differ_from_the_2000_paper_config():
    old = json.loads((HERE / "runner_config_brain2000_paper.json").read_text())
    new = json.loads(CFG.read_text())
    changed = {k for k in new if k != "risk_policy" and new[k] != old[k]}
    changed |= {"risk_policy." + k for k in new["risk_policy"] if new["risk_policy"][k] != old["risk_policy"][k]}
    assert changed == {"daily_loss_warn_fraction", "daily_loss_halt_fraction", "risk_policy.max_loss_fraction",
                       "risk_policy.max_open_risk_fraction", "risk_policy.max_total_margin_fraction",
                       "risk_policy.minimum_equity", "risk_policy.max_loss_margin_fraction",
                       "risk_policy.min_leverage", "risk_policy.max_leverage"}
    assert old["risk_policy"]["max_loss_fraction"] == "0.042857142857142857"     # configurazione attiva intatta


def test_the_mandate_template_is_bound_to_the_policy_and_not_approved(tmp_path):
    tpl = json.loads(TPL.read_text())
    assert tpl["approved"] is False and tpl["approved_by"] == ""
    assert (tpl["portfolio_id"], tpl["run_id"]) == ("brain", RUN)
    assert tpl["policy_hash"] == _policy_hash(_cfg().risk_policy) == "ba5c074ec2ecfe34"
    text = " ".join(tpl["avvertenze"])
    assert "STIMATA" in text and "non una perdita massima garantita" in text
    assert "non garantisce che l'equity non scenda oltre" in text
    path = tmp_path / "mandate.json"
    path.write_text(json.dumps(tpl))
    assert MandateFile(path, _cfg().risk_policy, RUN).problem() == "mandate_not_approved"


def test_an_approved_copy_for_this_run_is_accepted_and_any_other_is_refused(tmp_path):
    tpl = json.loads(TPL.read_text())
    path = tmp_path / "mandate.json"
    path.write_text(json.dumps(dict(tpl, approved=True, approved_by="proprietario")))
    policy = _cfg().risk_policy
    assert MandateFile(path, policy, RUN).problem() is None
    assert MandateFile(path, policy, "un-altra-run").problem() == "mandate_mismatch"
    old = load_runner_config((HERE / "runner_config_brain2000_paper.json").read_bytes()).risk_policy
    assert MandateFile(path, old, RUN).problem() == "mandate_mismatch"           # limiti diversi: rifiutato


def test_with_profile_b_the_estimated_loss_at_stop_is_one_percent():
    q = quote_paper_risk(_cfg().risk_policy, RiskRequest(
        equity=D("2000"), available_cash=D("2000"), margin_used=D("0"), existing_open_risk=D("0"),
        entry_price=D("100"), stop_price=D("99"), side=1, requested_leverage=10, exchange_leverage_limit=125,
        quantity_step=D("0.000001"), minimum_notional=D("5"), maintenance_fraction=D("0.005"),
        market_data_fresh=True, paused=False, daily_loss_latched=False))
    assert q.allowed and abs(q.worst_case_loss_estimate - D("20")) < D("0.01")   # STIMA, non garanzia
