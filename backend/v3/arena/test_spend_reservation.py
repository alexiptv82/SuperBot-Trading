"""Prenotazione della spesa AI dell'Arena: nessuna chiamata puo' partire sotto il tetto e chiudersi sopra."""
from __future__ import annotations

import fcntl
import json
import os
from decimal import Decimal

import pytest

from backend.tests.test_v3_runner_e2e import G, VIEW, _get_json_factory
from backend.v3.arena import runner as R
from backend.v3.arena.test_arena_runner import ENV, PolicyModel, _approve_and_unpause, _prepare
from backend.v3.brain_f3.providers import ProviderUnavailable, TransportResponse
from backend.v3.budget import BudgetLedger
from backend.v3.runner.metering import MeteredTransport, worst_case_units

IN, OUT = Decimal("0.32"), Decimal("1.28")             # Qwen al listino
PAYLOAD = {"model": "qwen/qwen3.7-plus", "max_tokens": 6000, "messages": [{"role": "user", "content": "x" * 20000}]}
WORST = worst_case_units(PAYLOAD, IN, OUT)


class Model:
    """Restituisce l'uso massimo plausibile: tutti i max_tokens in uscita (ragionamento compreso)."""

    def __init__(self):
        self.calls = 0

    def __call__(self, payload):
        self.calls += 1
        prompt = len(json.dumps(payload)) // 2
        return TransportResponse(200, {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                                       "usage": {"prompt_tokens": prompt, "completion_tokens": payload["max_tokens"]}})


def _meter(tmp_path, model, daily=2_000_000, total=6_000_000):
    led = BudgetLedger(str(tmp_path / "budget.db"))
    m = MeteredTransport(model, led, "qwen", input_usd_per_million=IN, output_usd_per_million=OUT,
                         reserve={"daily_cap_units": daily, "total_cap_units": total,
                                  "lock_path": tmp_path / ".ai_spend.lock"})
    return led, m


def test_call_is_refused_before_reaching_the_model_when_worst_case_does_not_fit(tmp_path):
    model = Model()
    led, m = _meter(tmp_path, model)
    led.record_spend("qwen", 6_000_000 - WORST + 1, {"basis": "test"})     # manca 1 micro-dollaro al costo massimo
    with pytest.raises(ProviderUnavailable, match="budget_reserve_denied"):
        m(PAYLOAD)
    assert model.calls == 0 and led.total_spend("qwen") == 6_000_000 - WORST + 1


def test_daily_cap_is_also_reserved(tmp_path):
    model = Model()
    led, m = _meter(tmp_path, model, daily=WORST * 2)
    m(PAYLOAD)
    m(PAYLOAD)
    with pytest.raises(ProviderUnavailable, match="budget_reserve_denied"):
        m(PAYLOAD)
    assert model.calls == 2 and led.daily_spend("qwen") <= WORST * 2


def test_seventy_two_hours_over_four_utc_dates_never_exceed_six_usd(tmp_path, monkeypatch):
    """T0 alle 15:00 UTC: 4 date di calendario. Il tetto giornaliero si azzera, quello cumulativo no."""
    import backend.v3.budget as B
    from datetime import datetime, timedelta, timezone
    clock = {"t": datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)}

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["t"]
    monkeypatch.setattr(B, "datetime", FakeDT)
    model = Model()
    led, m = _meter(tmp_path, model)
    spent_ok = 0
    end = clock["t"] + timedelta(hours=72)
    while clock["t"] < end:
        try:
            m(PAYLOAD)
            spent_ok += 1
        except ProviderUnavailable as exc:
            assert str(exc) == "budget_reserve_denied"
        clock["t"] += timedelta(minutes=2)
    assert led.total_spend("qwen") <= 6_000_000                           # mai oltre 6 USD
    assert led.total_spend("qwen") > 6_000_000 - 2 * WORST                 # e il tetto viene davvero usato
    days = {r[0][:10] for r in led._conn.execute("SELECT occurred_at FROM spend_events")}
    assert len(days) >= 3 and model.calls == spent_ok


def test_concurrent_process_and_broken_ledger_fail_closed(tmp_path):
    model = Model()
    led, m = _meter(tmp_path, model)
    fd = os.open(tmp_path / ".ai_spend.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)                                        # un secondo runner sulla stessa AI
    try:
        with pytest.raises(ProviderUnavailable, match="budget_reserve_busy"):
            m(PAYLOAD)
    finally:
        os.close(fd)
    led.close()                                                           # registro inutilizzabile
    with pytest.raises(ProviderUnavailable, match="budget_reserve_unavailable"):
        m(PAYLOAD)
    assert model.calls == 0
    with pytest.raises(ValueError):
        MeteredTransport(model, BudgetLedger(str(tmp_path / "b2.db")), "qwen", input_usd_per_million=IN,
                         output_usd_per_million=OUT, reserve={"daily_cap_units": 1, "total_cap_units": 0,
                                                              "lock_path": tmp_path / "x"})


def test_deadline_reached_mid_cycle_stops_the_remaining_ai_calls(tmp_path):
    root = tmp_path / "arena"
    root.mkdir()
    plan = _prepare(root, "qwen")
    _approve_and_unpause(plan)
    t0 = json.loads((plan.folder / "arena_manifest.json").read_text())["trial_start_ms"]
    expiry = t0 + R.TRIAL_DAYS * 86_400_000
    clock = {"now": G + 25_000}

    class LastCallBeforeDeadline(PolicyModel):
        def __call__(self, payload):
            out = super().__call__(payload)
            clock["now"] = expiry + 1                                     # la risposta arriva dopo la scadenza
            return out
    from backend.v3.runner.config import load_runner_config
    from backend.v3.runner.exit_worker import build_exit_worker
    model = LastCallBeforeDeadline()
    gj = _get_json_factory()
    built = R.build_arena_runner(plan, environ=ENV, clock_ms=lambda: clock["now"], inner_transport=model,
                                 get_json=gj, view_params=VIEW)
    cfg = load_runner_config((plan.folder / "runner_config.json").read_bytes())
    with build_exit_worker(data_dir=plan.folder, run_id=plan.run_id, config=cfg, get_json=gj) as exits:
        exits.tick(G + 25_000)
        built.runner.tick(G + 25_000)
    assert len(model.payloads) == 1                                       # il 2o simbolo non chiama l'AI


def test_worst_case_is_a_true_upper_bound_even_for_dense_non_ascii_text():
    """Il costo massimo non puo' essere sotto la spesa reale nemmeno con testo che il tokenizer spezza al massimo."""
    for text in ("x" * 20_000, "価格は上昇している。" * 2000, "😀" * 5000, "0123456789" * 2000):
        p = {"model": "m", "max_tokens": 6000, "messages": [{"role": "user", "content": text}]}
        worst = worst_case_units(p, IN, OUT)
        real_if_one_token_per_byte = len(json.dumps(p, sort_keys=True, ensure_ascii=False).encode()) * IN + 6000 * OUT
        assert worst >= int(real_if_one_token_per_byte)
    no_cap = {"model": "m", "messages": [{"role": "user", "content": "x"}]}
    assert worst_case_units(no_cap, IN, OUT) >= 65_536 * OUT                  # niente max_tokens: massimo accettato


def test_failed_call_on_arena_is_counted_at_the_upper_bound(tmp_path):
    def boom(_p):
        raise ProviderUnavailable("timeout")
    led, m = _meter(tmp_path, boom)
    with pytest.raises(ProviderUnavailable):
        m(PAYLOAD)
    assert led.total_spend("qwen") == WORST                                   # forse fatturata: mai sotto-contare


def test_inspect_reports_ai_spend_and_alerts_above_five_usd(tmp_path):
    from backend.v3.arena import trial_setup as TS
    from backend.v3.arena.test_trial_setup import DAY, NOW, _key_limit, _prepare  # noqa: F401
    root = tmp_path / "arena"
    root.mkdir(mode=0o700)
    _prepare(root)
    plan = TS._plans(root, DAY)["qwen"]
    led = BudgetLedger(str(plan.folder / "budget.db"))
    led.record_spend("qwen", 4_990_000, {"basis": "test"})
    led.close()
    rep = TS.inspect(root, DAY, NOW)
    assert rep["providers"]["qwen"]["ai_spend_total_usd"] == "4.99" and rep["alerts"] == []
    led = BudgetLedger(str(plan.folder / "budget.db"))
    led.record_spend("qwen", 20_000, {"basis": "test"})
    led.close()
    rep = TS.inspect(root, DAY, NOW)
    assert rep["alerts"] == ["qwen:AI_SPEND_ABOVE_5.00_USD"] and rep["blockers"] == []
    assert rep["providers"]["deepseek"]["ai_spend_total_usd"] == "0"
