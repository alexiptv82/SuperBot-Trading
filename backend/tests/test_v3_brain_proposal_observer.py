"""Osservatorio delle proposte Brain: annota lato/leva/stop delle proposte del modello senza influire su decisioni,
journal, rischio o esecuzione. Solo dati sintetici, nessuna rete."""
from __future__ import annotations

import dataclasses
import json
import os
from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.tests.test_v3_runner_e2e import RUN, G, VIEW, FakeModel, _get_json_factory, mandate_template
from backend.v3.brain_f3.providers import ProviderUnavailable, TransportResponse
from backend.v3.runner import proposal_log as PL
from backend.v3.runner.config import load_runner_config, load_default_config
from backend.v3.runner.wiring import build_runner

NOW = G + 25_000
BRAIN2000 = Path(__file__).resolve().parents[1] / "v3" / "runner" / "runner_config_brain2000_paper.json"


class WideStopModel(FakeModel):
    """BTC LONG e ETH SHORT con stop all'1,5%: con leva minima 20x il rischio li respinge entrambi."""

    def __call__(self, payload):
        self.payloads.append(json.loads(json.dumps(payload)))
        info = json.loads(payload["messages"][1]["content"])
        price, long_ = D(info["price"]), info["symbol"] == "BTCUSDT"
        content = json.dumps({"kind": "OPEN", "side": 1 if long_ else -1, "entry_price": str(price),
                              "stop_price": str(price * (D("0.985") if long_ else D("1.015"))), "leverage": 25,
                              "confidence": 0.71, "strategy_id": "S25", "strategy_origin": "library"})
        return TransportResponse(200, {"choices": [{"finish_reason": "stop", "message": {"content": content}}],
                                       "usage": {"prompt_tokens": 2500, "completion_tokens": 60}})


def _build(tmp_path, model, observer, conf=None):
    conf = conf or dataclasses.replace(load_default_config(), symbols=("BTCUSDT", "ETHUSDT"), cycle_minutes=15,
                                       thinking="disabled", reasoning_effort="omit", max_tokens=256)
    built = build_runner(data_dir=tmp_path, run_id=RUN, config=conf, get_json=_get_json_factory(),
                         inner_transport=model, view_params=VIEW, proposal_observer=observer)
    m = mandate_template(conf.risk_policy, RUN)
    m.update(approved=True, approved_by="test")
    (tmp_path / "mandate.json").write_text(json.dumps(m))
    return built


def _journal(built):
    return [(e.event.kind, {k: v for k, v in e.event.payload.items() if k != "claim"})
            for e in built.journal.list_run("brain", RUN)]


def test_rejected_proposals_keep_their_side_in_the_observer_log_but_not_in_the_journal(tmp_path):
    conf = dataclasses.replace(load_runner_config(BRAIN2000.read_bytes()), symbols=("BTCUSDT", "ETHUSDT"))
    seen = []
    built = _build(tmp_path, WideStopModel(), seen.append, conf)
    t = built.runner.tick(NOW)
    assert [d[1:3] for d in t.cycle.decisions] == [("NO_TRADE", "RISK_REJECTED")] * 2 and t.cycle.opened == ()
    decisions = [p for k, p in _journal(built) if k == "brain_decision"]
    assert all("side" not in p and "leverage" not in p for p in decisions)      # il journal resta com'era
    by_symbol = {r["symbol"]: r for r in seen}
    assert by_symbol["BTCUSDT"]["kind"] == "OPEN" and by_symbol["BTCUSDT"]["side"] == 1
    assert by_symbol["ETHUSDT"]["side"] == -1
    assert by_symbol["BTCUSDT"]["stop_bp"] == 150 and by_symbol["BTCUSDT"]["leverage"] == 25
    assert by_symbol["BTCUSDT"]["confidence"] == 0.71 and by_symbol["BTCUSDT"]["strategy_id"] == "S25"
    assert all(set(r) <= PL.KEYS for r in seen)
    # l'unione con il journal e' per (ts_ms, symbol): stesso istante della decisione
    ts = {e.event.occurred_at_ms for e in built.journal.list_run("brain", RUN) if e.event.kind == "brain_decision"}
    assert {r["ts_ms"] for r in seen} == ts


def test_decisions_and_journal_are_identical_with_and_without_the_observer(tmp_path):
    a = _build(tmp_path / "a", FakeModel(), None) if (tmp_path / "a").mkdir() is None else None
    b = _build(tmp_path / "b", FakeModel(), [].append) if (tmp_path / "b").mkdir() is None else None
    ta, tb = a.runner.tick(NOW), b.runner.tick(NOW)
    assert ta.cycle.decisions == tb.cycle.decisions and len(ta.cycle.opened) == len(tb.cycle.opened) == 2
    strip = lambda rows: [(k, {x: y for x, y in p.items() if x not in ("position_id", "decision_event_id")})  # noqa: E731
                          for k, p in rows]
    assert strip(_journal(a)) == strip(_journal(b))


def test_a_failing_observer_never_changes_the_decision(tmp_path):
    def boom(_record):
        raise RuntimeError("disco pieno")
    built = _build(tmp_path, FakeModel(), boom)
    t = built.runner.tick(NOW)
    assert len(t.cycle.opened) == 2 and t.cycle.errors == ()


def test_provider_errors_are_recorded_and_still_fail_closed(tmp_path):
    def down(_payload):
        raise ProviderUnavailable("provider_unavailable")
    seen = []
    built = _build(tmp_path, down, seen.append)
    t = built.runner.tick(NOW)
    assert t.cycle.opened == () and {r["kind"] for r in seen} == {"ERROR"}
    assert all(r["error"] == "provider_unavailable" and "side" not in r for r in seen)


def test_file_observer_writes_only_whitelisted_numeric_fields(tmp_path):
    obs = PL.file_observer(tmp_path)
    built = _build(tmp_path, FakeModel(), obs)
    built.runner.tick(NOW)
    path = tmp_path / PL.LOG_FILE
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    assert len(rows) == 2 and all(set(r) <= PL.KEYS and r["kind"] == "OPEN" for r in rows)
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    obs({"ts_ms": 1, "symbol": "BTCUSDT", "testo_del_modello": "non deve mai essere scritto"})
    assert len(path.read_text().splitlines()) == 2


def test_file_observer_refuses_symlinks_and_respects_the_size_cap(tmp_path, monkeypatch):
    target = tmp_path / "altrove.txt"
    target.write_text("intatto")
    os.symlink(target, tmp_path / PL.LOG_FILE)
    PL.file_observer(tmp_path)({"ts_ms": 1, "symbol": "BTCUSDT", "kind": "NO_TRADE"})
    assert target.read_text() == "intatto"
    os.unlink(tmp_path / PL.LOG_FILE)
    monkeypatch.setattr(PL, "MAX_BYTES", 10)
    PL.file_observer(tmp_path)({"ts_ms": 1, "symbol": "BTCUSDT", "kind": "NO_TRADE"})
    assert (tmp_path / PL.LOG_FILE).read_text() == ""


def test_record_never_raises_and_drops_unsafe_values():
    class Ctx:
        symbol, timestamp_ms, regime, price = "BTCUSDT", 5, "TREND_UP; DROP", "100"
    assert PL.proposal_record(object()) is None
    rec = PL.proposal_record(Ctx(), error=RuntimeError("Testo libero con spazi e chiave sk-123"))
    assert rec == {"ts_ms": 5, "symbol": "BTCUSDT", "regime": None, "price": "100", "kind": "ERROR", "error": "errore"}


def test_the_observer_is_off_unless_explicitly_enabled(tmp_path, monkeypatch):
    from backend.v3.runner import wiring
    captured = {}
    real = wiring.build_runner

    def spy(**kw):
        captured.update(observer=kw.get("proposal_observer"))
        return real(**kw)
    monkeypatch.setattr(wiring, "build_runner", spy)
    cfg = tmp_path / "c.json"
    cfg.write_bytes(BRAIN2000.read_bytes())
    for env, expected in (({"DESK_MODE": "paper"}, False), ({"DESK_MODE": "paper", "V3_BRAIN_PROPOSAL_LOG": "1"}, True),
                          ({"DESK_MODE": "paper", "V3_BRAIN_PROPOSAL_LOG": "true"}, False)):
        d = tmp_path / ("on" if expected else "off") / str(len(env))
        d.mkdir(parents=True)
        assert wiring.main(["--data-dir", str(d), "--run-id", RUN, "--config", str(cfg), "--once"], env=env,
                           get_json=_get_json_factory(), inner_transport=FakeModel(), now_fn=lambda: NOW) == 0
        assert (captured["observer"] is not None) is expected
