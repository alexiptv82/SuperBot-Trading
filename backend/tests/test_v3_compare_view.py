"""Confronto PAPER (backend/v3/compare_view.py): metriche dal journal di ogni run, sola lettura, fail-closed."""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path

from backend.v3.compare_view import compare, runs_from_env
from backend.v3.events import Event, EventJournal

RUNNER = Path(__file__).resolve().parents[1] / "v3" / "runner"
T = 1_800_000_000_000


def _run(tmp, name, cfg_file, trades, guardian=None, spend=()):
    d = tmp / name
    d.mkdir()
    shutil.copy(RUNNER / cfg_file, d / "runner_config.json")
    j = EventJournal(str(d / "journal.db"))
    j.init_schema()
    for i, (side, pnl, reason, kind) in enumerate(trades):
        pid = f"{name}-{i}"
        j.append(Event(f"paper_open.{pid}", "brain", name, "paper_open", T + i * 1000, "t",
                       {"position_id": pid, "symbol": "BTCUSDT", "side": side, "fill_price": "100", "quantity": "1",
                        "margin_used": "100", "leverage": 20, "stop_price": "99" if side == 1 else "101"}))
        if pnl is not None:
            payload = {"position_id": pid, "symbol": "BTCUSDT", "side": side, "realized_pnl": pnl, "fees": "0.12",
                       "reason": reason}
            if kind:
                payload["stop_kind"] = kind
            j.append(Event(f"paper_close.{pid}", "brain", name, "paper_close", T + i * 1000 + 500, "t", payload))
    if guardian:
        j.append(Event("guardian_state.1", "brain", name, "guardian_state", T + 99_000, "t", guardian))
    j.append(Event("dec.1", "brain", name, "brain_decision", T + 99_500, "t",
                   {"kind": "NO_TRADE", "status": "REJECTED", "rationale": "falco_no_trade_regime", "symbol": "ETHUSDT",
                    "sources": ["falco_evoluto:short_rules", "bad source!"]}))
    if spend:
        with sqlite3.connect(d / "budget.db") as db:
            db.execute("CREATE TABLE spend_events (id INTEGER PRIMARY KEY, provider TEXT, occurred_at TEXT, units INT,"
                       " metadata TEXT)")
            for t, u in spend:
                db.execute("INSERT INTO spend_events(provider,occurred_at,units,metadata) VALUES('deepseek',?,?,'{}')",
                           (t, u))
    return d


def _env(*runs):
    return {"V3_COMPARE_RUNS": json.dumps([{"name": n, "label": l, "dir": str(d), "run_id": n} for n, l, d in runs])}


def test_side_by_side_metrics_from_each_journal(tmp_path):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT10:00:00+00:00")
    f = _run(tmp_path, "falco_evoluto", "runner_config_falco_evoluto_paper.json",
             [(-1, "30", "take_profit", None), (-1, "-10", "stop", None), (1, "5", "stop", "trailing"),
              (1, "-20", "manual", None), (-1, None, None, None)],
             guardian={"state": "SELECTIVE", "reasons": ["floor_armed"], "budget": "40", "risk_cap": "20"},
             spend=[(today, 150_000), ("2026-01-01T00:00:00+00:00", 50_000)])
    b = _run(tmp_path, "brain_scalp", "runner_config_brain_scalp_paper.json", [(1, "100", "take_profit", None)])
    out = compare(_env(("falco_evoluto", "Falco Evoluto", f), ("brain_scalp", "Brain Scalp", b)), T)
    assert out["available"] and [r["name"] for r in out["runs"]] == ["falco_evoluto", "brain_scalp"]
    fe, bs = out["runs"]
    assert fe["initial_equity"] == "1000" and fe["net_pnl"] == "5" and fe["return_pct"] == "0.50"
    # curva contabilizzata 1000 -> 1030 -> 1020 -> 1025 -> 1005: drawdown massimo 25 dal picco 1030
    assert fe["max_drawdown"] == "25" and fe["max_drawdown_pct"] == "2.43"
    assert fe["profit_factor"] == "1.17" and (fe["wins"], fe["losses"]) == (2, 2) and fe["win_rate"] == "50.0"
    assert fe["by_side"]["short"] == {"trades": 2, "wins": 1, "losses": 1, "net_pnl": "20"}
    assert fe["by_side"]["long"] == {"trades": 2, "wins": 1, "losses": 1, "net_pnl": "-15"}
    assert fe["manual_closes"] == 1 and fe["protected_stops"] == 1 and len(fe["open_positions"]) == 1
    assert fe["guardian"]["state"] == "SELECTIVE" and fe["ai_spend"] == {"day": "0.15", "total": "0.2", "by_provider": {"deepseek": {"day": "0.15", "total": "0.2"}}}
    assert fe["config"]["leverage"] == [15, 45] and fe["config"]["margin"] == ["100", "250"]
    assert fe["decisions"][0]["rationale"] == "falco_no_trade_regime"
    assert fe["decisions"][0]["sources"] == ["falco_evoluto:short_rules"]          # testo non valido scartato
    assert bs["return_pct"] == "5.00" and bs["profit_factor"] is None and bs["config"]["cycle_minutes"] == 30
    assert bs["ai_spend"] == {"day": None, "total": None} and bs["guardian"] is None


def test_reading_never_writes_or_creates_files(tmp_path):
    f = _run(tmp_path, "falco_evoluto", "runner_config_falco_evoluto_paper.json", [(-1, "30", "take_profit", None)])
    before = {p.name: p.read_bytes() for p in f.iterdir()}
    compare(_env(("falco_evoluto", "Falco Evoluto", f)), T)
    after = {p.name: p.read_bytes() for p in f.iterdir()}
    assert before == after


def test_fail_closed_without_or_with_invalid_configuration(tmp_path):
    assert compare({}, T) == {"available": False, "generated_at_ms": T, "runs": []}
    for raw in ("[]", "not json", json.dumps([{"name": "x"}]),
                json.dumps([{"name": "a1", "label": "A", "dir": "relative", "run_id": "abc"}]),
                json.dumps([{"name": "a1", "label": "A", "dir": "/x/../etc", "run_id": "abc"}]),
                json.dumps([{"name": "a1", "label": "A", "dir": "/x", "run_id": "abc"}] * 2)):
        assert runs_from_env({"V3_COMPARE_RUNS": raw}) is None
    missing = tmp_path / "missing"
    missing.mkdir()
    out = compare(_env(("brain_scalp", "Brain Scalp", missing)), T)
    assert out["runs"][0] == {"name": "brain_scalp", "label": "Brain Scalp", "run_id": "brain_scalp",
                              "available": False, "reason": "not_prepared"}
    shutil.copy(RUNNER / "runner_config_brain_scalp_paper.json", missing / "runner_config.json")
    assert compare(_env(("brain_scalp", "Brain Scalp", missing)), T)["runs"][0]["reason"] == "not_started"
    assert not (missing / "journal.db").exists()


def test_trading_pnl_ai_cost_and_result_after_ai_are_separate(tmp_path):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT10:00:00+00:00")
    f = _run(tmp_path, "falco_evoluto", "runner_config_falco_evoluto_paper.json",
             [(-1, "30", "take_profit", None), (-1, "-10", "stop", None)], spend=[(today, 150_000), (today, 50_000)])
    r = compare(_env(("falco_evoluto", "Falco Evoluto", f)), T)["runs"][0]
    assert r["net_pnl"] == "20" and r["ai_cost_total"] == "0.2"             # trading (commissioni incluse) e AI
    assert r["net_after_ai"] == "19.8" and r["return_after_ai_pct"] == "1.98"  # AI sottratta una sola volta
    assert r["settled_equity"] == "1020"                                     # l'equity contabile non include l'AI
    b = _run(tmp_path, "brain_scalp", "runner_config_brain_scalp_paper.json", [(1, "5", "stop", None)])
    r = compare(_env(("brain_scalp", "Brain Scalp", b)), T)["runs"][0]
    assert r["ai_cost_total"] is None and r["net_after_ai"] is None          # registro assente: mai "0"


def test_closed_trade_and_mark_to_market_drawdown_are_distinct(tmp_path):
    d = _run(tmp_path, "brain_scalp", "runner_config_brain_scalp_paper.json", [(1, "40", "take_profit", None)])
    j = EventJournal(str(d / "journal.db"))
    for i, (eq, reasons) in enumerate([("2100", ["floor_armed"]), ("1995", ["floor_armed"]), ("2050", ["test"])]):
        j.append(Event(f"guardian_state.m{i}", "brain", "brain_scalp", "guardian_state", T + 200_000 + i, "t",
                       {"state": "SELECTIVE", "reasons": reasons, "equity": eq}))
    r = compare(_env(("brain_scalp", "Brain Scalp", d)), T)["runs"][0]
    assert r["max_drawdown"] == "0" and r["max_drawdown_pct"] == "0.00"      # sui chiusi: nessuna perdita
    assert r["mtm_drawdown"] == "105" and r["mtm_drawdown_pct"] == "5.00"    # a mercato: 2100 -> 1995
    assert r["mtm_samples"] == 3 and r["mtm_incomplete"] is False
    j.append(Event("guardian_state.m9", "brain", "brain_scalp", "guardian_state", T + 300_000, "t",
                   {"state": "LOCKED", "reasons": ["data_fault"], "equity": None}))
    r = compare(_env(("brain_scalp", "Brain Scalp", d)), T)["runs"][0]
    assert r["mtm_samples"] == 3 and r["mtm_incomplete"] is True and r["mtm_drawdown"] == "105"
    plain = _run(tmp_path, "falco_evoluto", "runner_config_falco_evoluto_paper.json", [(1, "5", "stop", None)])
    r = compare(_env(("falco_evoluto", "Falco Evoluto", plain)), T)["runs"][0]
    assert r["mtm_drawdown"] is None and r["mtm_samples"] == 0               # nessun campione: nessun valore
