"""Laboratorio costi LLM: solo mock e fixture sintetiche."""
import json
import logging
from pathlib import Path

import pytest

from backend.v3.llm_cost_lab.benchmark import summarize
from backend.v3.llm_cost_lab.models import CANDIDATES, forbid_auto_model
from backend.v3.llm_cost_lab.shadow import (
    LabResponse, LiveCallsDisabled, MarketSample, ShadowSession, post_once,
)
from backend.v3.llm_cost_lab.store import ShadowStore

NOW = 1_700_000_000_000
KEY = "freellmapi-test-key-should-not-leak"


def sample(symbol="BTCUSDT", asof=NOW - 60_000, received=NOW - 30_000, now=NOW, price="100",
           regime="RANGE", sample_id="s1"):
    return MarketSample(sample_id, symbol, price, regime, asof, received, now)


def chat(content, status=200, latency=20, prompt=11, completion=7):
    return LabResponse(status, {
        "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
    }, latency)


def open_body(side, latency=20):
    return chat(json.dumps({
        "kind": "OPEN", "side": side, "entry_price": "100", "stop_price": "99",
        "leverage": 2, "confidence": 0.7,
    }), latency=latency)


class Script:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, model_id, payload):
        self.calls.append(model_id)
        assert "Authorization" not in json.dumps(payload)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def session(tmp_path, poster, models=CANDIDATES, **kwargs):
    store = ShadowStore(tmp_path)
    return ShadowSession(models=models, store=store, poster=poster, **kwargs), store


def test_schema_long_short_and_valid_no_trade(tmp_path):
    poster = Script([
        open_body(1, 10),
        chat(json.dumps({"kind": "NO_TRADE"}), latency=30),
        open_body(-1, 40),
    ])
    lab, store = session(tmp_path, poster, max_micro_usd=10_000_000)
    rows = lab.evaluate(sample())
    assert [row["action"] for row in rows] == ["LONG", "NO_TRADE", "SHORT"]
    assert rows[0]["direction"] == "LONG" and rows[2]["direction"] == "SHORT"
    assert all(row["may_open"] is False and row["shadow"] is True and row["promoted"] is False
               and row["fallback"] is False for row in rows)
    assert rows[1]["valid"] is True and rows[1]["reason"] == "schema_no_trade"
    assert all(row["confidence"] is None and row["confidence_verified"] is False for row in rows)
    assert rows[0]["freshness_ms"] == 60_000
    assert rows[0]["prompt_tokens"] == 11 and rows[0]["cost_origin"] == "simulated_usage"
    assert poster.calls == [item.model_id for item in CANDIDATES]
    assert store.read() == rows


def test_incomplete_http_malformed_and_timeout_are_not_signals(tmp_path):
    poster = Script([
        chat(json.dumps({"kind": "OPEN", "side": 1})),
        LabResponse(500, {"error": "upstream"}, 5),
        LabResponse(200, None, 5),
        TimeoutError(),
        LabResponse(429, {}, 5),
        chat(json.dumps({"kind": "NO_TRADE"})),
    ])
    lab, _store = session(tmp_path, poster, max_requests_per_model=5, max_micro_usd=10_000_000)
    first = lab.evaluate(sample(sample_id="bad-schema"))
    second = lab.evaluate(sample(sample_id="http", asof=NOW - 1_000, received=NOW - 500))
    assert first[0]["failure"] == "invalid_schema" and first[0]["action"] == "NO_TRADE"
    assert first[0]["valid"] is False and first[0]["may_open"] is False
    assert first[1]["failure"] == "http_error"
    assert first[2]["failure"] == "malformed"
    assert second[0]["failure"] == "timeout" and second[0]["attempts"] == 1
    assert second[1]["failure"] == "rate_limit" and second[1]["attempts"] == 1
    assert second[2]["valid"] is True and second[2]["action"] == "NO_TRADE"
    assert poster.calls.count("deepseek-flash") == 2


def test_timeout_does_not_retry(tmp_path):
    poster = Script([TimeoutError(), chat(json.dumps({"kind": "NO_TRADE"}))])
    lab, _store = session(tmp_path, poster, models=CANDIDATES[:2], max_micro_usd=10_000_000)
    rows = lab.evaluate(sample())
    assert rows[0]["failure"] == "timeout"
    assert poster.calls == ["deepseek-flash", "google/gemini-2.5-flash"]


def test_budget_and_local_rate_limit_skip_the_call(tmp_path):
    poster = Script([chat(json.dumps({"kind": "NO_TRADE"}))])
    lab, _store = session(tmp_path, poster, models=CANDIDATES[:1], max_micro_usd=0)
    blocked = lab.evaluate(sample())
    assert blocked[0]["failure"] == "budget" and blocked[0]["attempts"] == 0
    assert poster.calls == []
    lab2, _store2 = session(tmp_path / "rate", poster, models=CANDIDATES[1:2],
                            max_requests_per_model=1, max_micro_usd=10_000_000)
    first = lab2.evaluate(sample(sample_id="one"))
    second = lab2.evaluate(sample(sample_id="two", asof=NOW - 1_000, received=NOW - 500))
    assert first[0]["valid"] is True
    assert second[0]["failure"] == "rate_limit" and second[0]["attempts"] == 0
    assert poster.calls == ["google/gemini-2.5-flash"]


def test_missing_stale_and_future_data_do_not_call(tmp_path):
    poster = Script([])
    lab, _store = session(tmp_path, poster, models=CANDIDATES[:1])
    missing = lab.evaluate(sample(price=""))
    stale = lab.evaluate(sample(sample_id="old", asof=NOW - 60 * 60 * 1000, received=NOW - 1_000))
    future = lab.evaluate(sample(sample_id="future", asof=NOW + 1, received=NOW + 1, now=NOW))
    assert missing[0]["failure"] == "data_missing"
    assert stale[0]["failure"] == "data_stale"
    assert future[0]["failure"] == "data_future"
    assert poster.calls == []


def test_valid_no_trade_is_not_a_fallback(tmp_path):
    poster = Script([chat(json.dumps({"kind": "NO_TRADE"})) for _ in range(3)])
    lab, _store = session(tmp_path, poster, max_micro_usd=10_000_000)
    rows = lab.evaluate(sample())
    assert [row["action"] for row in rows] == ["NO_TRADE", "NO_TRADE", "NO_TRADE"]
    assert all(row["valid"] and row["fallback"] is False and row["attempts"] == 1 for row in rows)
    assert len(poster.calls) == 3


def test_store_refuses_operational_directories(tmp_path):
    blocked = tmp_path / "superbot-desk-data"
    blocked.mkdir()
    with pytest.raises(ValueError, match="operational_store_refused"):
        ShadowStore(blocked)
    mixed = tmp_path / "mixed"
    mixed.mkdir()
    (mixed / "journal.db").write_text("synthetic", encoding="utf-8")
    with pytest.raises(ValueError, match="operational_store_refused"):
        ShadowStore(mixed)


def test_persistence_and_reproducible_rerun(tmp_path):
    def make(folder):
        poster = Script([
            open_body(1, 15),
            chat(json.dumps({"kind": "NO_TRADE"}), latency=25),
            open_body(-1, 35),
        ])
        lab, store = session(folder, poster, max_micro_usd=10_000_000)
        lab.evaluate(sample())
        return store.read()

    first = make(tmp_path / "a")
    second = make(tmp_path / "b")
    assert first == second
    assert json.loads(Path(tmp_path / "a" / "shadow_decisions.jsonl").read_text().splitlines()[0])["symbol"] == "BTCUSDT"


def test_auto_models_are_rejected():
    with pytest.raises(ValueError, match="unpinned_model"):
        forbid_auto_model("auto:smart")
    with pytest.raises(ValueError, match="unpinned_model"):
        forbid_auto_model("auto")
    with pytest.raises(ValueError, match="unpinned_model"):
        forbid_auto_model("fusion")
    assert forbid_auto_model("groq/llama-3.3-70b").version == "llama-3.3-70b"


def test_live_client_cannot_open_a_socket():
    with pytest.raises(LiveCallsDisabled):
        post_once("http://127.0.0.1:3001/v1", "local-key", {})


def test_secrets_are_absent_from_records_and_logs(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    poster = Script([chat(json.dumps({"kind": "NO_TRADE"}))])
    lab, store = session(tmp_path, poster, models=CANDIDATES[:1], max_micro_usd=10_000_000)
    lab.evaluate(sample())
    text = caplog.text + store.path.read_text(encoding="utf-8")
    assert KEY not in text
    assert "Bearer " not in text


def test_benchmark_keeps_agreement_separate_from_outcomes(tmp_path):
    poster = Script([
        open_body(1, 10), open_body(1, 20), open_body(1, 100),
    ])
    lab, _store = session(tmp_path, poster, max_micro_usd=10_000_000)
    rows = lab.evaluate(sample())
    bare = summarize(rows)
    assert bare["agreement_is_correctness"] is False
    assert bare["live_provider_measured"] is False
    assert bare["arms"][0]["quality_vs_outcomes"]["status"] == "incomplete"
    assert bare["arms"][0]["daily_consumption"] == "not_measured"
    labelled = summarize(rows, outcomes=[{
        "sample_id": "s1", "label": "NO_TRADE", "known": True, "unfavorable": True,
    }])
    agreement = labelled["agreement_with_baseline"]["google/gemini-2.5-flash"]
    assert agreement["rate"] == 1 and agreement["means_correct"] is False
    quality = next(arm["quality_vs_outcomes"] for arm in labelled["arms"]
                   if arm["model_id"] == "deepseek-flash")
    assert quality["matched_label"] == 0 and quality["avoided_unfavorable"] == 0
    assert quality["live_market_verified"] is False
    arm = next(item for item in labelled["arms"] if item["model_id"] == "deepseek-flash")
    assert arm["latency_median_ms"] == 10
    assert arm["cost_per_1000_micro_usd"] is not None
    assert arm["may_open_any"] is False


def test_lab_sources_do_not_name_brain_writers():
    root = Path("backend/v3/llm_cost_lab")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for banned in ("EventJournal", "BrainEngine", "ExitService", "daily_loss", "RiskManager"):
        assert banned not in text
