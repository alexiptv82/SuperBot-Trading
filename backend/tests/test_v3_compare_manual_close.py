"""Chiusura manuale SINGOLA PAPER di Falco Evoluto e Brain Scalp, end-to-end offline:
pagina -> rotta web autenticata -> bridge host (socket UNIX reale) -> servizio uscite della STESSA run -> journal.

Run preparate con il vero ``prepare_new_paper_run`` (in pausa, mandato approved:false). Nessuna chiusura globale,
nessun incrocio fra run, RC1 e classici non toccati. Solo dati sintetici, nessuna VPS.
"""
from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from backend.tests.test_v3_brain_single_manual_close_gate import _bridge
from backend.tests.test_v3_dashboard_unified import _app, _paths
from backend.tests.test_v3_runner_feed_monitor import _hand
from backend.v3 import close_bridge as bridge_client
from backend.v3 import close_bridge_server as bridge_host
from backend.v3 import cutover_gate
from backend.v3.events import EventJournal
from backend.v3.executor.paper import execute_paper
from backend.v3.outcomes import extract_outcomes
from backend.v3.runner.exit_service import ExitService
from backend.v3.runner.manual_close import run_manual_close
from backend.v3.runner.monitor import MonitorReport
from backend.v3.runner.prepare_paper_run import prepare_new_paper_run

RUNNER = Path(__file__).resolve().parents[1] / "v3" / "runner"
WALLETS = {"falco_evoluto": ("brain-v3-falco-evoluto-t1", "runner_config_falco_evoluto_paper.json", "1000"),
           "brain_scalp": ("brain-v3-brain-scalp-t1", "runner_config_brain_scalp_paper.json", "2000")}


def _setup(tmp_path, monkeypatch, *, extra=True):
    runs = tmp_path / "runs"
    runs.mkdir()
    now = int(time.time() * 1000)
    out = {}
    for name, (folder, cfg, equity) in WALLETS.items():
        root = prepare_new_paper_run(parent=runs, run_name=folder, run_id=folder,
                                     config_bytes=(RUNNER / cfg).read_bytes(), desk_mode="paper", now_ms=now - 120_000,
                                     expected_initial_equity=equity)
        j = EventJournal(root / "journal.db")
        pid = execute_paper(_hand(side=1, entry="100", stop="98", symbol="BTCUSDT"), portfolio_id="brain",
                            run_id=folder, journal=j, now_ms=now - 60_000).position_id
        out[name] = (root, folder, pid)
    for key, val in (("V3_CUTOVER_READONLY", "1"), ("V3_ALLOW_BRAIN_SINGLE_CLOSE", "1"), ("TRADING_MODE", "paper"),
                     ("DESK_MODE", "paper"), ("V3_CLOSE_BRIDGE_ONLY", "1")):
        monkeypatch.setenv(key, val)
    sock = str(tmp_path / "close.sock")
    monkeypatch.setenv("V3_CLOSE_BRIDGE_SOCKET", sock)
    monkeypatch.setattr(bridge_client, "SOCKET_PATH", sock)
    monkeypatch.setattr(bridge_host, "SOCKET_PATH", sock)
    monkeypatch.setattr(cutover_gate, "_CLOSE_BRIDGE_SOCKET", sock)
    monkeypatch.setattr(bridge_host, "EXTRA", {n: (r, rid) for n, (r, rid, _) in out.items()} if extra else {})
    monkeypatch.setenv("V3_COMPARE_RUNS", json.dumps(
        [{"name": n, "label": n.replace("_", " ").title(), "dir": str(r), "run_id": rid} for n, (r, rid, _) in out.items()]))
    rc1 = tmp_path / "rc1"
    rc1.mkdir()
    return out, now, _app(_paths(rc1))[0]


def _sidecar(root, run_id):
    journal = EventJournal(root / "journal.db")
    return ExitService(run_id=run_id, data_dir=root,
                       run_commands=lambda t: run_manual_close(journal=journal, portfolio_id="brain", run_id=run_id,
                                                               data_dir=root, price_of=lambda s, t: Decimal("101"),
                                                               fee_bps=Decimal("6"), now_ms=t),
                       run_monitor=lambda _: MonitorReport(0, (), ()))


def _closes(root, run_id):
    return [r.event for r in EventJournal(root / "journal.db").list_run("brain", run_id) if r.event.kind == "paper_close"]


def test_each_bot_closes_one_position_in_its_own_run_from_its_dashboard(tmp_path, monkeypatch):
    runs, now, app = _setup(tmp_path, monkeypatch)
    (fr, fid, fpid), (br, bid, bpid) = runs["falco_evoluto"], runs["brain_scalp"]
    assert json.loads((fr / "mandate.json").read_text())["approved"] is False and (fr / "pause.flag").exists()
    with TestClient(app) as client, _bridge(), _sidecar(fr, fid) as falco, _sidecar(br, bid) as scalp:
        # senza servizio uscite sano nessuna chiusura (fail-closed)
        assert client.post("/api/v3/compare/falco_evoluto/close", json={"position_id": fpid}).status_code == 409
        assert falco.tick(now).state == "healthy" and scalp.tick(now).state == "healthy"
        view = {r["name"]: r for r in client.get("/api/v3/compare").json()["runs"]}
        assert view["falco_evoluto"]["manual_close_allowed"] is True and view["brain_scalp"]["manual_close_allowed"]
        # identita' della run: la posizione di Brain Scalp non esiste in Falco Evoluto
        assert client.post("/api/v3/compare/falco_evoluto/close", json={"position_id": bpid}).status_code == 404
        assert client.post("/api/v3/compare/falco_evoluto/close", json={"all": True}).status_code == 423
        assert client.post("/api/v3/compare/brain_rc1/close", json={"position_id": fpid}).status_code == 404
        r = client.post("/api/v3/compare/falco_evoluto/close", json={"position_id": fpid})
        assert r.status_code == 200, r.text
        assert (fr / "close_request.json").exists() and not (br / "close_request.json").exists()
        assert client.post("/api/v3/compare/falco_evoluto/close", json={"position_id": fpid}).status_code == 409
        assert falco.tick(now + 3000).state == "healthy"
        res = client.get("/api/v3/compare/falco_evoluto/close-result").json()
        assert res["pending"] is False and res["result"]["closed"] == [fpid]
        # Brain Scalp: stesso percorso, nella sua run
        assert client.post("/api/v3/compare/brain_scalp/close", json={"position_id": bpid}).status_code == 200
        assert scalp.tick(now + 4000).state == "healthy"
        assert client.get("/api/v3/compare/brain_scalp/close-result").json()["result"]["closed"] == [bpid]
        view = {r["name"]: r for r in client.get("/api/v3/compare").json()["runs"]}
        assert view["falco_evoluto"]["manual_closes"] == 1 and view["falco_evoluto"]["open_positions"] == []
        assert view["brain_scalp"]["manual_closes"] == 1 and view["brain_scalp"]["open_positions"] == []
    for root, rid in ((fr, fid), (br, bid)):
        closes = _closes(root, rid)
        assert len(closes) == 1 and closes[0].payload["reason"] == "manual"
        outcomes = extract_outcomes(EventJournal(root / "journal.db"), "brain", rid).outcomes
        assert len(outcomes) == 1 and outcomes[0].exit_reason == "manual"     # feedback: chiusura dell'operatore


def test_bridge_refuses_wallets_that_are_not_configured_or_do_not_match(tmp_path, monkeypatch):
    runs, now, app = _setup(tmp_path, monkeypatch, extra=False)
    (fr, fid, fpid) = runs["falco_evoluto"]
    with TestClient(app) as client, _bridge(), _sidecar(fr, fid) as falco:
        assert falco.tick(now).state == "healthy"
        assert client.post("/api/v3/compare/falco_evoluto/close", json={"position_id": fpid}).status_code == 409
    assert not (fr / "close_request.json").exists()
    # marcatore di un'altra run: rifiuto anche se la cartella e' quella configurata
    monkeypatch.setattr(bridge_host, "EXTRA", {"falco_evoluto": (fr, "another-run")})
    assert bridge_host.process_single_close({"wallet": "falco_evoluto", "position_id": fpid})[0] == 409
    # solo position_id; niente simboli, niente "all", niente campi in piu'
    for body in ({"wallet": "falco_evoluto", "symbol": "BTC"}, {"wallet": "falco_evoluto", "all": True},
                 {"wallet": "falco_evoluto", "position_id": fpid, "all": True}):
        assert bridge_host.process_single_close(body)[0] == 423


def test_extra_runs_from_the_unit_environment_are_strict():
    ok = "falco_evoluto=brain-v3-falco-evoluto-t1:falco-evoluto-t1,brain_scalp=brain-v3-brain-scalp-t1:brain-scalp-t1"
    got = bridge_host._extra_from_env({"V3_BRIDGE_EXTRA_RUNS": ok})
    assert got == {"falco_evoluto": (bridge_host.RUN_ROOT / "brain-v3-falco-evoluto-t1", "falco-evoluto-t1"),
                   "brain_scalp": (bridge_host.RUN_ROOT / "brain-v3-brain-scalp-t1", "brain-scalp-t1")}
    for bad in ("", "x", "toro=brain-v3-xxx:abc", "falco_evoluto=../etc:abc", "falco_evoluto=brain-v3-aaa",
                "falco_evoluto=brain-v3-same:abc,brain_scalp=brain-v3-same:abd",
                "falco_evoluto=brain-v3-aaa:abc,falco_evoluto=brain-v3-bbb:abd",
                "falco_evoluto=brain-v3-paper20261111:abc",                    # = run del Brain servita dal bridge
                'falco_evoluto=brain-v3-aaa:a"b', "falco_evoluto=brain-v3-aaa:abc extra"):
        assert bridge_host._extra_from_env({"V3_BRIDGE_EXTRA_RUNS": bad}) == {}
