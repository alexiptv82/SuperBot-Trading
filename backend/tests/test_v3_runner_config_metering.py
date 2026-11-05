"""A3 - configurazione del runner e contatore di spesa del modello. Nessuna rete, nessuna chiave."""
from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal

import pytest

from backend.v3.brain_f3.providers import ProviderUnavailable, TransportResponse
from backend.v3.budget import BudgetLedger
from backend.v3.runner.config import (
    default_config_path, load_default_config, load_runner_config,
)
from backend.v3.runner.metering import (
    BudgetHalt, MeteredTransport, estimate_units, usage_units,
)

D = Decimal


def _raw(**over):
    d = json.loads(default_config_path().read_bytes())
    d.update(over)
    return json.dumps(d).encode()


# ----------------------------------------------------------------------------- config
def test_default_config_values_are_the_proposals():
    c = load_default_config()
    assert c.symbols == ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT")
    assert (c.initial_equity, c.slippage_bps, c.fee_bps, c.maintenance_fraction) == (D("1000"), 2, D("6"), D("0.005"))
    p = c.risk_policy
    assert (p.max_loss_fraction, p.max_open_risk_fraction, p.max_position_margin_fraction,
            p.max_total_margin_fraction, p.minimum_equity, p.estimated_roundtrip_cost_bp,
            p.liquidation_buffer_fraction) == (D("0.02"), D("0.05"), D("0.1"), D("0.3"), D("450"), D("16"), D("0.5"))
    assert (c.model, c.thinking, c.input_usd_per_million, c.output_usd_per_million) == (
        "deepseek-flash", "enabled", D("0.30"), D("1.20"))
    assert (c.reasoning_effort, c.max_tokens, c.cycle_minutes, c.cycle_ms) == ("high", 6000, 60, 3_600_000)
    assert c.daily_cap_usd == D("0.75") and c.daily_cap_units == 750_000 and type(c.daily_cap_units) is int
    assert c.model_extra_payload == {"thinking": {"type": "enabled"}, "reasoning_effort": "high"}


def test_model_extra_payload_for_each_thinking_mode():
    off = load_runner_config(_raw(thinking="disabled", reasoning_effort="omit", max_tokens=256))
    assert off.model_extra_payload == {"thinking": {"type": "disabled"}}
    omit = load_runner_config(_raw(thinking="omit", reasoning_effort="omit"))
    assert omit.model_extra_payload is None
    on = load_runner_config(_raw(thinking="enabled", reasoning_effort="omit"))
    assert on.model_extra_payload == {"thinking": {"type": "enabled"}}
    for effort in ("low", "high", "max"):
        c = load_runner_config(_raw(thinking="enabled", reasoning_effort=effort))
        assert c.model_extra_payload == {"thinking": {"type": "enabled"}, "reasoning_effort": effort}


def test_loader_needs_exact_bytes():
    for bad in ("x", None, bytearray(b"{}")):
        with pytest.raises(ValueError, match="invalid_config"):
            load_runner_config(bad)


@pytest.mark.parametrize("raw", [
    b"", b"[]", b"{}", b"\xff", b"not json", b'{"a":1,"a":2}',
    _raw().replace(b'"1000"', b"NaN"), _raw().replace(b'"1000"', b"Infinity"),
])
def test_loader_rejects_garbage(raw):
    with pytest.raises(ValueError, match="invalid_config"):
        load_runner_config(raw)


@pytest.mark.parametrize("field,literal", [("slippage_bps", "2"), ("schema_version", "1")])
def test_non_finite_json_constants_are_refused_even_where_a_number_would_fit(field, literal):
    raw = _raw().decode().replace(f'"{field}": {literal}', f'"{field}": NaN')
    assert "NaN" in raw
    with pytest.raises(ValueError, match="invalid_config"):
        load_runner_config(raw.encode())


def test_loader_rejects_duplicate_keys_and_unknown_or_missing_keys():
    base = _raw().decode()
    with pytest.raises(ValueError, match="invalid_config"):
        load_runner_config(base.replace('"model"', '"model": "x", "model"', 1).encode())
    d = json.loads(base)
    d["extra"] = 1
    with pytest.raises(ValueError, match="invalid_config"):
        load_runner_config(json.dumps(d).encode())
    del d["extra"], d["model"]
    with pytest.raises(ValueError, match="invalid_config"):
        load_runner_config(json.dumps(d).encode())
    for key in ("reasoning_effort", "max_tokens", "cycle_minutes"):                  # le chiavi nuove sono obbligatorie
        d2 = json.loads(base)
        del d2[key]
        with pytest.raises(ValueError, match="invalid_config"):
            load_runner_config(json.dumps(d2).encode())


@pytest.mark.parametrize("over", [
    {"schema_version": 2}, {"schema_version": True}, {"schema_version": "1"},
    {"symbols": []}, {"symbols": "BTCUSDT"}, {"symbols": ["BTCUSDT", "BTCUSDT"]}, {"symbols": ["btcusdt"]},
    {"symbols": ["BTCUSD"]}, {"symbols": ["btcUSDT"]}, {"symbols": ["BTC/USDT"]}, {"symbols": [5]}, {"symbols": ["A" * 30 + "USDT"]},
    {"symbols": [f"S{i}USDT" for i in range(41)]},
    {"slippage_bps": 501}, {"slippage_bps": -1}, {"slippage_bps": True}, {"slippage_bps": 1.5}, {"slippage_bps": "2"},
    {"initial_equity": "1000.0000000000000000000000"}, {"initial_equity": "450"}, {"initial_equity": "449"}, {"initial_equity": 1000}, {"initial_equity": "abc"},
    {"initial_equity": "NaN"}, {"initial_equity": ""}, {"initial_equity": "1000000.1"},
    {"fee_bps": "101"}, {"fee_bps": "-1"}, {"fee_bps": 6},
    {"maintenance_fraction": "1"}, {"maintenance_fraction": "-0.1"}, {"maintenance_fraction": 0.005},
    {"model": ""}, {"model": " deepseek-flash"}, {"model": "Deep Seek"}, {"model": "deepseek flash"}, {"model": 5}, {"model": "x" * 65}, {"model": "-x"},
    {"thinking": "on"}, {"thinking": None}, {"thinking": True}, {"thinking": "ENABLED"},
    {"reasoning_effort": "medium"}, {"reasoning_effort": None}, {"reasoning_effort": True}, {"reasoning_effort": "HIGH"},
    {"thinking": "disabled", "reasoning_effort": "high"}, {"thinking": "omit", "reasoning_effort": "low"},   # sforzo senza ragionamento
    {"max_tokens": 0}, {"max_tokens": -1}, {"max_tokens": 65537}, {"max_tokens": True}, {"max_tokens": 6000.0},
    {"max_tokens": "6000"}, {"max_tokens": 1023},                                                          # < minimo con il ragionamento
    {"thinking": "disabled", "reasoning_effort": "omit", "max_tokens": 0},                                # limiti validi anche senza ragionamento
    {"thinking": "omit", "reasoning_effort": "omit", "max_tokens": -5},
    {"thinking": "disabled", "reasoning_effort": "omit", "max_tokens": 65537},
    {"cycle_minutes": 0}, {"cycle_minutes": 14}, {"cycle_minutes": 16}, {"cycle_minutes": 1455}, {"cycle_minutes": 1441},
    {"cycle_minutes": True}, {"cycle_minutes": 60.0}, {"cycle_minutes": "60"}, {"cycle_minutes": -15},
    {"input_usd_per_million_tokens": "-0.1"}, {"input_usd_per_million_tokens": 0.3},
    {"output_usd_per_million_tokens": "1001"}, {"output_usd_per_million_tokens": "x"},
    {"daily_cap_usd": "0"}, {"daily_cap_usd": "-1"}, {"daily_cap_usd": "1001"}, {"daily_cap_usd": "0.0000001"},
    {"daily_cap_usd": 0.6},
])
def test_loader_rejects_bad_values_with_a_message_that_leaks_nothing(over):
    with pytest.raises(ValueError) as e:
        load_runner_config(_raw(**over))
    assert str(e.value) == "invalid_config"


def _risk(**over):
    r = dict(json.loads(default_config_path().read_bytes())["risk_policy"])
    r.update(over)
    return {"risk_policy": r}


@pytest.mark.parametrize("over", [
    _risk(max_loss_fraction="0"), _risk(max_loss_fraction="1.01"), _risk(max_loss_fraction="0.06"),   # > rischio totale
    _risk(max_open_risk_fraction="0"), _risk(max_position_margin_fraction="0"),
    _risk(max_position_margin_fraction="0.31"),                                                      # > margine totale
    _risk(max_total_margin_fraction="1.1"), _risk(minimum_equity="449"), _risk(minimum_equity="1000"),  # = equity
    _risk(estimated_roundtrip_cost_bp="-1"), _risk(liquidation_buffer_fraction="0"),
    _risk(liquidation_buffer_fraction="1.1"), {"risk_policy": []}, {"risk_policy": {}},
    _risk(extra="1"),
])
def test_loader_rejects_bad_risk_policy(over):
    with pytest.raises(ValueError, match="invalid_config"):
        load_runner_config(_raw(**over))


def test_loader_accepts_boundaries():
    c = load_runner_config(_raw(slippage_bps=500, fee_bps="100", maintenance_fraction="0", thinking="omit",
                                reasoning_effort="omit", max_tokens=1, cycle_minutes=15, daily_cap_usd="0.000001"))
    assert c.slippage_bps == 500 and c.fee_bps == D("100") and c.maintenance_fraction == D("0")
    assert c.thinking == "omit" and c.daily_cap_units == 1 and c.max_tokens == 1 and c.cycle_ms == 900_000
    top = load_runner_config(_raw(thinking="enabled", reasoning_effort="max", max_tokens=65536, cycle_minutes=1440))
    assert top.max_tokens == 65536 and top.cycle_ms == 86_400_000
    low = load_runner_config(_raw(thinking="enabled", max_tokens=1024))
    assert low.max_tokens == 1024
    assert load_runner_config(_raw(thinking="enabled", max_tokens=65536)).max_tokens == 65536
    assert load_runner_config(_raw(daily_cap_usd="12.5")).daily_cap_units == 12_500_000
    c2 = load_runner_config(_raw(**_risk(max_loss_fraction="0.05", max_position_margin_fraction="0.3")))
    assert c2.risk_policy.max_loss_fraction == c2.risk_policy.max_open_risk_fraction == D("0.05")


# ----------------------------------------------------------------------------- usage / estimate
def test_usage_units_uses_exact_prices_and_rounds_up():
    body = {"usage": {"prompt_tokens": 2500, "completion_tokens": 80}}
    assert usage_units(body, D("0.30"), D("1.20")) == 750 + 96                      # 846 micro-dollari
    assert usage_units({"usage": {"prompt_tokens": 1, "completion_tokens": 1}}, D("0.30"), D("0.25")) == 1   # 0.55 -> 1
    assert usage_units({"usage": {"prompt_tokens": 0, "completion_tokens": 0}}, D("0.30"), D("1.20")) == 0
    assert usage_units({"usage": {"prompt_tokens": 10, "completion_tokens": 0}}, D("0.30"), D("1.20")) == 3


@pytest.mark.parametrize("body", [None, {}, {"usage": None}, {"usage": {}}, {"usage": {"prompt_tokens": 5}},
                                  {"usage": {"prompt_tokens": 5, "completion_tokens": -1}},
                                  {"usage": {"prompt_tokens": True, "completion_tokens": 1}},
                                  {"usage": {"prompt_tokens": 1.5, "completion_tokens": 1}},
                                  {"usage": {"prompt_tokens": "5", "completion_tokens": 1}},
                                  {"usage": {"prompt_tokens": 10_000_001, "completion_tokens": 1}}, "x", []])
def test_usage_units_refuses_missing_or_incoherent_usage(body):
    assert usage_units(body, D("0.30"), D("1.20")) is None


def test_estimate_is_prudent_and_uses_max_tokens():
    payload = {"model": "m", "max_tokens": 256, "messages": [{"role": "user", "content": "x" * 1000}]}
    chars = len(json.dumps(payload, sort_keys=True))
    from fractions import Fraction
    from math import ceil
    assert estimate_units(payload, D("0.30"), D("1.20")) == ceil((chars // 2 + 1) * Fraction(3, 10) + 256 * Fraction(6, 5)) == 470
    assert estimate_units({"messages": []}, D("0.30"), D("1.20")) > 4096 * 1               # senza max_tokens: 4096 in uscita
    assert estimate_units({"max_tokens": True}, D("0"), D("1")) == 4096
    assert estimate_units({"max_tokens": 10**9}, D("0"), D("1")) == 4096
    assert estimate_units({"max_tokens": -1}, D("0"), D("1")) == 4096
    assert estimate_units({"max_tokens": 0}, D("0"), D("1")) == 0


# ----------------------------------------------------------------------------- MeteredTransport
def _ledger():
    return BudgetLedger(os.path.join(tempfile.mkdtemp(), "budget.db"))


class Inner:
    def __init__(self, body=None, exc=None):
        self.body, self.exc, self.sent = body, exc, []

    def __call__(self, payload):
        self.sent.append(dict(payload))
        if self.exc:
            raise self.exc
        return TransportResponse(200, self.body)


def _mt(inner, ledger=None, **kw):
    led = ledger or _ledger()
    return MeteredTransport(inner, led, "deepseek", input_usd_per_million=D("0.30"),
                            output_usd_per_million=D("1.20"), **kw), led


def test_successful_call_records_the_exact_spend_and_returns_the_response_untouched():
    body = {"choices": [], "usage": {"prompt_tokens": 2500, "completion_tokens": 80}}
    inner = Inner(body)
    mt, led = _mt(inner)
    resp = mt({"model": "m", "max_tokens": 256})
    assert resp.status_code == 200 and resp.body is body
    assert led.daily_spend("deepseek") == 846
    assert led.all_spend("deepseek")[0]["metadata"] == {"basis": "usage"}
    assert mt.accounting_failed is False


def test_response_without_usage_is_charged_a_prudent_estimate():
    payload = {"model": "m", "max_tokens": 256, "messages": [{"role": "user", "content": "y" * 400}]}
    mt, led = _mt(Inner({"choices": []}))
    mt(payload)
    assert led.daily_spend("deepseek") == estimate_units(payload, D("0.30"), D("1.20"))
    assert led.all_spend("deepseek")[0]["metadata"] == {"basis": "estimate_no_usage"}


def test_failed_call_is_charged_an_estimate_and_the_error_propagates():
    err = ProviderUnavailable("provider_unavailable")
    mt, led = _mt(Inner(exc=err))
    with pytest.raises(ProviderUnavailable) as e:
        mt({"max_tokens": 256})
    assert e.value is err
    assert led.daily_spend("deepseek") == estimate_units({"max_tokens": 256}, D("0.30"), D("1.20")) > 0
    assert led.all_spend("deepseek")[0]["metadata"] == {"basis": "estimate_failed_call"}


def test_extra_payload_is_added_only_where_absent():
    inner = Inner({"usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    mt, _ = _mt(inner, extra_payload={"thinking": {"type": "disabled"}, "stream": True})
    mt({"model": "m", "stream": False})
    assert inner.sent[0] == {"model": "m", "stream": False, "thinking": {"type": "disabled"}}
    mt2, _ = _mt(inner)
    mt2({"model": "m"})
    assert inner.sent[1] == {"model": "m"}


def test_the_callers_payload_is_not_mutated():
    payload = {"model": "m"}
    mt, _ = _mt(Inner({"usage": {"prompt_tokens": 1, "completion_tokens": 1}}), extra_payload={"thinking": 1})
    mt(payload)
    assert payload == {"model": "m"}


def test_ledger_failure_discards_the_response_and_marks_accounting_failed():
    class Broken(BudgetLedger):
        def record_spend(self, *a, **k):
            raise RuntimeError("disk")
    led = Broken(os.path.join(tempfile.mkdtemp(), "b.db"))
    mt = MeteredTransport(Inner({"usage": {"prompt_tokens": 1, "completion_tokens": 1}}), led, "deepseek",
                          input_usd_per_million=D("0.3"), output_usd_per_million=D("1.2"))
    with pytest.raises(ProviderUnavailable) as e:
        mt({"model": "m"})
    assert str(e.value) == "provider_unavailable" and mt.accounting_failed is True


def test_ledger_failure_on_a_failed_call_still_raises_the_original_error():
    class Broken(BudgetLedger):
        def record_spend(self, *a, **k):
            raise RuntimeError("disk")
    led = Broken(os.path.join(tempfile.mkdtemp(), "b.db"))
    err = ProviderUnavailable("provider_unavailable")
    mt = MeteredTransport(Inner(exc=err), led, "deepseek", input_usd_per_million=D("0.3"),
                          output_usd_per_million=D("1.2"))
    with pytest.raises(ProviderUnavailable) as e:
        mt({"model": "m"})
    assert e.value is err and mt.accounting_failed is True


@pytest.mark.parametrize("kw", [{"inner": None}, {"ledger": object()}, {"provider": ""}, {"provider": 5},
                                {"i": 0.3}, {"i": D("-1")}, {"i": D("NaN")}, {"o": "1"}, {"o": D("Infinity")}])
def test_metered_transport_rejects_bad_setup(kw):
    args = dict(inner=Inner({}), ledger=_ledger(), provider="deepseek", i=D("0.3"), o=D("1.2"))
    args.update(kw)
    with pytest.raises(ValueError, match="invalid_meter"):
        MeteredTransport(args["inner"], args["ledger"], args["provider"], input_usd_per_million=args["i"],
                         output_usd_per_million=args["o"])


# ----------------------------------------------------------------------------- BudgetHalt + gate end to end
def test_gate_denies_after_the_cap_is_really_reached_and_halt_reports_it():
    led = _ledger()
    cap = 1_000
    gate = led.spending_gate(daily_limits={"deepseek": cap})
    mt = MeteredTransport(Inner({"usage": {"prompt_tokens": 1000, "completion_tokens": 0}}), led, "deepseek",
                          input_usd_per_million=D("0.30"), output_usd_per_million=D("1.20"))   # 300 per chiamata
    halt = BudgetHalt(led, "deepseek", cap, mt)
    seen = []
    for _ in range(6):
        allowed = gate("deepseek")
        seen.append((allowed, halt()))
        if allowed:
            mt({"model": "m"})
    assert seen == [(True, None), (True, None), (True, None), (True, None), (False, "budget"), (False, "budget")]
    assert led.daily_spend("deepseek") == 1_200                                                   # sfora di una chiamata al massimo


def test_halt_at_exactly_the_cap_and_below():
    led = _ledger()
    mt, _ = _mt(Inner({}), ledger=led)
    halt = BudgetHalt(led, "deepseek", 500, mt)
    led.record_spend("deepseek", 499)
    assert halt() is None
    led.record_spend("deepseek", 1)
    assert halt() == "budget"


def test_halt_reports_ledger_error_and_ignores_other_providers():
    led = _ledger()
    mt, _ = _mt(Inner({}), ledger=led)
    halt = BudgetHalt(led, "deepseek", 100, mt)
    led.record_spend("claude", 10_000)
    assert halt() is None
    mt.accounting_failed = True
    assert halt() == "ledger_error"


@pytest.mark.parametrize("kw", [{"provider": ""}, {"cap": 0}, {"cap": -5}, {"cap": True}, {"cap": 1.5},
                                {"metered": object()}, {"ledger": object()}])
def test_halt_rejects_bad_setup(kw):
    led = _ledger()
    mt, _ = _mt(Inner({}), ledger=led)
    a = dict(ledger=led, provider="deepseek", cap=10, metered=mt)
    a.update(kw)
    with pytest.raises(ValueError, match="invalid_halt"):
        BudgetHalt(a["ledger"], a["provider"], a["cap"], a["metered"])
