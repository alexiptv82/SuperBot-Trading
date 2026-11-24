"""App PAPER (Trade, Performance, Archivio) di Falco Evoluto e Brain Scalp: rotte GET autenticate, sola lettura.

Run preparate con il vero ``prepare_new_paper_run``, aperture e chiusure con il vero executor PAPER: ogni numero
mostrato viene dal journal della SUA run, l'archivio del reset non si mescola alle run attive, nulla viene scritto.
"""
from __future__ import annotations

import json
import sqlite3
import time
from decimal import Decimal as D
from pathlib import Path

from fastapi.testclient import TestClient

from backend.tests.test_brain_f7_outcomes import _hand
from backend.tests.test_v3_dashboard_unified import _app, _paths
from backend.v3 import paper_app_view as pav
from backend.v3.events import Event, EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.executor.paper_close import close_paper
from backend.v3.runner.prepare_paper_run import prepare_new_paper_run

RUNNER = Path(__file__).resolve().parents[1] / "v3" / "runner"
WALLETS = {"falco_evoluto": ("brain-v3-falco-evoluto-p1", "falco-evoluto-paper-p1",
                             "runner_config_falco_evoluto_paper.json", "1000"),
           "brain_scalp": ("brain-v3-brain-scalp-p1", "brain-scalp-paper-p1",
                           "runner_config_brain_scalp_paper.json", "2000")}
DAY = 86_400_000


def _prepare(parent: Path, folder, run_id, cfg, equity, now):
    return prepare_new_paper_run(parent=parent, run_name=folder, run_id=run_id,
                                 config_bytes=(RUNNER / cfg).read_bytes(), desk_mode="paper", now_ms=now,
                                 expected_initial_equity=equity)


def _trade(j, run_id, *, side, entry, stop, exit_price, reason, at, stop_kind=None):
    pid = execute_paper(_hand(side=side, entry=entry, stop=stop, qty="1", margin="100", lev=20, symbol="BTCUSDT"),
                        portfolio_id="brain", run_id=run_id, journal=j, now_ms=at).position_id
    if exit_price is not None:
        close_paper(portfolio_id="brain", run_id=run_id, position_id=pid, exit_price=D(exit_price), reason=reason,
                    fee_bps=6, journal=j, now_ms=at + 3_600_000, stop_kind=stop_kind)
    return pid


def _setup(tmp_path, monkeypatch, now):
    runs = tmp_path / "runs"
    runs.mkdir()
    out = {}
    for name, (folder, run_id, cfg, eq) in WALLETS.items():
        out[name] = (_prepare(runs, folder, run_id, cfg, eq, now - 3 * DAY), run_id)
    monkeypatch.setenv("V3_COMPARE_RUNS", json.dumps(
        [{"name": n, "label": n.replace("_", " ").title(), "dir": str(r), "run_id": rid}
         for n, (r, rid) in out.items()]))
    rc1 = tmp_path / "rc1"
    rc1.mkdir()
    return out, rc1


def _ticker(symbol):
    return {"price": "103"}


def test_trades_of_the_current_run_with_stop_take_profit_price_and_learning(tmp_path, monkeypatch):
    now = int(time.time() * 1000)
    runs, rc1 = _setup(tmp_path, monkeypatch, now)
    root, rid = runs["falco_evoluto"]
    j = EventJournal(root / "journal.db")
    _trade(j, rid, side=1, entry="100", stop="98", exit_price="106", reason="take_profit", at=now - 2 * DAY)
    _trade(j, rid, side=-1, entry="100", stop="102", exit_price="101", reason="manual", at=now - DAY)
    _trade(j, rid, side=1, entry="100", stop="98", exit_price="100.5", reason="stop", at=now - DAY + 10,
           stop_kind="break_even")
    open_id = _trade(j, rid, side=1, entry="100", stop="98", exit_price=None, reason=None, at=now - 60_000)
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    c = TestClient(_app(_paths(rc1), _ticker)[0])
    r = c.get("/api/v3/compare/falco_evoluto/trades")
    assert r.status_code == 200
    d = r.json()
    assert d["run_id"] == rid and d["take_profit_r"] == "3" and d["fee_bps"] == "6"
    [o] = d["open_positions"]
    # take-profit = ingresso + 3 R (politica d'uscita della run); prezzo dal ticker, P&L lordo della posizione
    assert o["position_id"] == open_id and D(o["take_profit"]) == D("106") and D(o["stop"]) == D("98")
    assert o["price"] == "103" and D(o["unrealized_pnl"]) == D("3") and o["leverage"] == 20
    closed = d["closed_trades"]
    assert [t["exit_reason"] for t in closed] == ["stop", "manual", "take_profit"]          # piu' recente prima
    be, manual, tp = closed
    assert be["stop_kind"] == "break_even" and D(be["stop"]) == D("98")
    assert manual["manual_learning"] == "loss_reduction_example" and D(manual["take_profit"]) == D("94")
    assert D(tp["gross_pnl"]) == D("6") and D(tp["realized_pnl"]) == D("6") - D(tp["fees"]) and D(tp["fees"]) > 0
    assert d["total_closed"] == 3 and d["win_count"] == 2
    # l'altra run non vede nulla di questa
    other = c.get("/api/v3/compare/brain_scalp/trades").json()
    assert other["open_positions"] == [] and other["closed_trades"] == [] and other["run_id"] == "brain-scalp-paper-p1"
    assert c.get("/api/v3/compare/rc1/trades").status_code == 404
    after = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    assert before == after                                                       # sola lettura


def test_no_ticker_means_no_price_never_the_entry(tmp_path, monkeypatch):
    now = int(time.time() * 1000)
    runs, rc1 = _setup(tmp_path, monkeypatch, now)
    root, rid = runs["brain_scalp"]
    _trade(EventJournal(root / "journal.db"), rid, side=-1, entry="100", stop="101", exit_price=None, reason=None,
           at=now - 60_000)

    def broken(_s):
        raise RuntimeError("rete")
    [o] = TestClient(_app(_paths(rc1), broken)[0]).get("/api/v3/compare/brain_scalp/trades").json()["open_positions"]
    assert o["price"] is None and o["unrealized_pnl"] is None and D(o["take_profit"]) == D("97")


def test_performance_daily_curve_stats_and_decision_reasons(tmp_path, monkeypatch):
    now = int(time.time() * 1000)
    runs, rc1 = _setup(tmp_path, monkeypatch, now)
    root, rid = runs["falco_evoluto"]
    j = EventJournal(root / "journal.db")
    _trade(j, rid, side=1, entry="100", stop="98", exit_price="106", reason="take_profit", at=now - 2 * DAY)
    _trade(j, rid, side=-1, entry="100", stop="102", exit_price="102", reason="stop", at=now - DAY)
    for i, (code, regime, status, rr) in enumerate([("falco_no_trade_regime", "RANGE", "REJECTED", None),
                                                    ("falco_no_trade_regime", "RANGE", "REJECTED", None),
                                                    ("falco_short_signal", "TREND_DOWN", "RISK_REJECTED",
                                                     "margin_below_minimum"),
                                                    ("Testo libero!", "RANGE", "REJECTED", None)]):
        j.append(Event(f"dec.{i}", "brain", rid, "brain_decision", now - 30_000 + i, "t",
                       {"kind": "NO_TRADE", "status": status, "rationale": code, "regime": regime,
                        "symbol": "ETHUSDT", **({"risk_reason": rr} if rr else {})}))
    j.append(Event("g.1", "brain", rid, "guardian_state", now - 20_000, "t",
                   {"state": "NORMAL", "reasons": [], "equity": "1003.5", "as_of_ms": now - 20_000}))
    j.append(Event("g.2", "brain", rid, "guardian_state", now - 10_000, "t",
                   {"state": "LOCKED", "reasons": ["data_fault"], "equity": "1", "as_of_ms": now - 10_000}))
    with sqlite3.connect(root / "budget.db") as db:
        db.execute("INSERT INTO spend_events(occurred_at, provider, units, metadata) VALUES(?, 'deepseek', ?, '{}')",
                   (time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now / 1000 - 2 * 86400)), 250_000))
    c = TestClient(_app(_paths(rc1))[0])
    p = c.get("/api/v3/compare/falco_evoluto/performance").json()
    assert p["available"] and p["run_id"] == rid and p["day_tz"] in ("Europe/Rome", "UTC")
    assert len(p["daily"]) in (4, 5) and p["daily"][0]["trades"] == 0                       # dal giorno di preparazione
    traded = [d for d in p["daily"] if d["trades"]]
    assert [(d["wins"], d["losses"]) for d in traded] == [(1, 0), (0, 1)]
    first = traded[0]
    # TP 100 -> 106, 1 unita': lordo 6, commissioni (100 + 106) * 6 bp, netto = lordo - commissioni
    assert D(first["gross"]) == D(6) and D(first["fees"]) == D("0.1236") and D(first["net"]) == D("5.8764")
    assert D(traded[1]["net"]) < 0
    assert first["ai_cost"] == "0.25" and D(first["net_after_ai"]) == D(first["net"]) - D("0.25")
    assert D(p["daily"][-1]["equity_end"]) == D(1000) + sum(D(d["net"]) for d in traded)
    assert [D(x["equity"]) for x in p["curve_settled"]][0] == D(1000) and len(p["curve_settled"]) == 3
    assert [x["equity"] for x in p["curve_market"]] == ["1003.5"]                          # campione con data_fault escluso
    assert p["stats"]["best"] is not None and p["stats"]["avg_hold_ms"] == 3_600_000 and p["stats"]["payoff"]
    dec = p["decisions"]
    assert dec["by_reason"] == {"falco_no_trade_regime": 2, "falco_short_signal": 1, "—": 1}
    assert dec["by_risk_reason"] == {"margin_below_minimum": 1} and dec["by_regime"]["RANGE"] == 3
    assert dec["last"][0]["rationale"] is None and dec["last"][1]["risk_reason"] == "margin_below_minimum"
    assert c.get("/api/v3/compare/nessuno/performance").status_code == 404


def _archive(tmp_path, now):
    """Archivio come lo scrive reset_paper.py: <radice>/reset-<data>/<cartella> + <cartella>.RISULTATI.json."""
    arch = tmp_path / "runs" / ".archivio"
    base = arch / "reset-20261123T203000Z"
    base.mkdir(parents=True)
    root = _prepare(base, "brain-v3-brain-scalp-p1", "brain-scalp-paper-p1", "runner_config_brain_scalp_paper.json",
                    "2000", now - 5 * DAY)
    _trade(EventJournal(root / "journal.db"), "brain-scalp-paper-p1", side=1, entry="100", stop="98",
           exit_price="96", reason="stop", at=now - 4 * DAY)
    (base / "brain-v3-brain-scalp-p1.RISULTATI.json").write_text(json.dumps(
        {"run_id": "brain-scalp-paper-p1", "closed_at_ms": now - 3 * DAY, "closed_trades": 1}))
    incomplete = _prepare(base, "brain-v3-falco-evoluto-p1", "falco-evoluto-paper-p1",
                          "runner_config_falco_evoluto_paper.json", "1000", now - 5 * DAY)   # senza RISULTATI: escluso
    (arch / "reset-20261123T203000Z-run-nuove-scartate").mkdir()
    return arch, root, incomplete


def test_archive_lists_only_complete_reset_archives_never_mixed_with_live(tmp_path, monkeypatch):
    now = int(time.time() * 1000)
    runs, rc1 = _setup(tmp_path, monkeypatch, now)
    arch, root, _incomplete = _archive(tmp_path, now)
    c = TestClient(_app(_paths(rc1))[0])
    assert c.get("/api/v3/paper-archive").json()["available"] is False                    # senza variabile: niente
    monkeypatch.setenv(pav.ARCHIVE_ENV, str(arch))
    idx = c.get("/api/v3/paper-archive").json()
    assert idx["available"] and [r["name"] for r in idx["runs"]] == ["reset-20261123T203000Z~brain-v3-brain-scalp-p1"]
    [row] = idx["runs"]
    assert row["label"] == "Brain Scalp" and row["closed"] == 1 and row["initial_equity"] == "2000"
    assert D(row["net_pnl"]) < 0 and "manual_close_allowed" not in row and "paused" not in row
    det = c.get("/api/v3/paper-archive/" + row["name"]).json()
    assert [t["exit_reason"] for t in det["closed_trades"]] == ["stop"] and det["performance"]["available"]
    # le run attive restano pulite: nessun trade archiviato nella run corrente con lo stesso run_id
    live = c.get("/api/v3/compare/brain_scalp/trades").json()
    assert live["closed_trades"] == []
    for bad in ("..~x", "reset-20261123T203000Z~..", "reset-20261123T203000Z~brain-v3-falco-evoluto-p1"):
        assert c.get("/api/v3/paper-archive/" + bad).status_code == 404


def test_take_profit_uses_the_exit_policy_of_the_run(tmp_path):
    cfg = pav.load_config(Path(RUNNER / "x").parent / "nonexistent")
    assert cfg is None and pav.take_profit(None, 1, "100", "98") is None
    d = tmp_path / "r"
    d.mkdir()
    (d / "runner_config.json").write_bytes((RUNNER / "runner_config_brain_scalp_paper.json").read_bytes())
    cfg = pav.load_config(d)
    r = cfg.exit_policy.take_profit_r
    assert D(pav.take_profit(cfg, -1, "200", "202")) == D(200) - r * 2
    assert pav.take_profit(cfg, 1, "100", "101") is None                                  # stop dal lato sbagliato
