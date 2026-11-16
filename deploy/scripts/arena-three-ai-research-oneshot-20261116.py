#!/usr/bin/env python3
"""Research-only three-model one-shot comparison on a pinned Arena snapshot.

Default mode is OFFLINE. --selftest and --preflight do not call ANY API.
--run + explicit token + interactive confirmation: THREE maximum paid model
POSTs (one per model), no retries. OpenRouter Qwen key is reused for the
DeepSeek research call, so DeepSeek here is NOT asserted identical to the
already-running direct DeepSeek model in Brain. Absolutely NO trades, writes
or bot/service changes. Responses are NOT execution instructions.
"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
import os
import re
import ssl
import stat
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.v3.arena.compact_market import build_compact_market
from backend.v3.arena.comparison_packet import (
    build_common_packet, parse_research_choice, SCHEMA,
)
from backend.v3.arena.incremental_cache import load_research_cache
from backend.v3.arena.openrouter_transport import _read_key, MODELS, BASE
from backend.v3.brain_market.params import load_default_params

CACHE = Path("/var/lib/superbot-arena-research/arena-market-research-cache.json")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
MODEL_IDS = {
    "qwen": MODELS["qwen"],
    "minimax": MODELS["minimax"],
    "deepseek": "deepseek/deepseek-v4.1-flash-1017",
}
ORDER = ("deepseek", "qwen", "minimax")
KEY_OWNER = {"deepseek": "qwen", "qwen": "qwen", "minimax": "minimax"}
MAX_COMPLETION_TOKENS = 512
MAX_REQUEST_BYTES = 30000
MAX_RESPONSE_BYTES = 40000
MAX_KEY_LIMIT_USD = Decimal("2")
MIN_KEY_REMAINING_USD = Decimal("0.15")
MAX_REQUESTS = 3
COMPARE_SCHEMA_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "arena_three_ai_candidate_v1",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["action", "symbol", "side", "confidence", "reason_code"],
            "properties": {
                "action": {"type": "string", "enum": ["CANDIDATE", "NO_TRADE"]},
                "symbol": {"type": "string"},
                "side": {"type": "string", "enum": ["LONG", "SHORT", "NONE"]},
                "confidence": {"type": "number"},
                "reason_code": {"type": "string"},
            },
        },
    },
}


def _money(value):
    if type(value) not in (str, int, float):
        raise ValueError("COST_DATA_MISSING")
    try:
        amount = Decimal(str(value))
    except (ValueError, InvalidOperation):
        raise ValueError("COST_DATA_INVALID") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError("COST_DATA_INVALID")
    return amount


def _http(path, key, payload):
    if path not in ("/key", "/chat/completions"):
        raise ValueError("PROVIDER_PATH_FORBIDDEN")
    if (path == "/key") != (payload is None):
        raise ValueError("PROVIDER_BODY_FORBIDDEN")
    data = None
    if payload is not None:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode()
        if len(data) > MAX_REQUEST_BYTES:
            raise ValueError("PROVIDER_PAYLOAD_TOO_LARGE")
    request = urllib.request.Request(
        BASE + path, method="GET" if payload is None else "POST", data=data,
        headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            "User-Agent": "SuperBot-Arena-Research-OneShot/1.0",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=50, context=ssl.create_default_context()
        ) as response:
            if response.getcode() != 200:
                raise ValueError("PROVIDER_STATUS_NOT_OK")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("PROVIDER_RESPONSE_TOO_LARGE")
        doc = json.loads(raw)
        if type(doc) is not dict:
            raise ValueError("PROVIDER_RESPONSE_NOT_JSON_OBJECT")
        return doc
    except (urllib.error.HTTPError, urllib.error.URLError, OSError,
            UnicodeError, ValueError, TimeoutError):
        # No provider error bodies, request headers or secrets printed.
        raise ValueError("PROVIDER_REQUEST_FAILED") from None


def _budget_gate(body):
    data = body.get("data")
    if type(data) is not dict or data.get("is_management_key"):
        raise ValueError("KEY_BUDGET_UNVERIFIED")
    limit = _money(data.get("limit"))
    remaining = _money(data.get("limit_remaining"))
    if limit > MAX_KEY_LIMIT_USD or remaining < MIN_KEY_REMAINING_USD:
        raise ValueError("KEY_BUDGET_DENIED")
    return limit, remaining


def _packet(expected_sha):
    if type(expected_sha) is not str or not DIGEST.fullmatch(expected_sha):
        raise ValueError("SNAPSHOT_SHA_REQUIRED")
    snap = load_research_cache(CACHE)
    if snap.sha256_hex != expected_sha or len(snap.symbols) != 25:
        raise ValueError("SNAPSHOT_SHA_OR_SCOPE_CHANGED")
    compact = build_compact_market(snap, load_default_params())
    common = build_common_packet(compact)
    if any(common.identical_messages(p) != common.identical_messages("qwen")
           for p in ORDER):
        raise ValueError("MODEL_INPUT_DIFFERS")
    return snap, common


def _body(lane, common):
    if lane not in ORDER:
        raise ValueError("UNRECOGNIZED_LANE")
    messages = list(common.identical_messages(lane))
    payload = {
        "model": MODEL_IDS[lane],
        "messages": messages,
        "stream": False,
        "max_tokens": MAX_COMPLETION_TOKENS,
        "response_format": (COMPARE_SCHEMA_FORMAT if lane == "qwen"
                            else {"type": "json_object"}),
    }
    if lane == "qwen":
        payload["provider"] = {"require_parameters": True}
        payload["reasoning"] = {"enabled": False}
    else:
        payload["temperature"] = 0
    if (payload["model"] != MODEL_IDS[lane]
            or len(json.dumps(payload, ensure_ascii=True).encode()) > MAX_REQUEST_BYTES):
        raise ValueError("MODEL_PAYLOAD_TOO_LARGE")
    return payload


def _read_choice(lane, packet, body):
    if (type(body) is not dict or type(body.get("choices")) is not list
            or len(body["choices"]) != 1
            or type(body["choices"][0]) is not dict):
        raise ValueError("MODEL_CHOICES_INVALID")
    item = body["choices"][0]
    if item.get("finish_reason") != "stop":
        raise ValueError("MODEL_NOT_COMPLETED")
    msg = item.get("message")
    if type(msg) is not dict:
        raise ValueError("MODEL_MESSAGE_MISSING")
    choice = parse_research_choice(packet, msg.get("content"))
    usage = body.get("usage")
    if type(usage) is not dict:
        usage = {}
    prompt_tokens, completion_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
    for val in (prompt_tokens, completion_tokens):
        if val is not None and (type(val) is not int or val < 0):
            raise ValueError("MODEL_USAGE_INVALID")
    return {
        "provider": lane,
        "model_requested": MODEL_IDS[lane],
        "action": choice.action,
        "symbol": choice.symbol,
        "side": choice.side,
        "confidence": str(choice.confidence),
        "reason_code": choice.reason_code,
        "input_tokens": prompt_tokens,
        "output_tokens": completion_tokens,
        "response_classification": choice.classification,
    }


def selftest():
    # No network / no cache / no secrets. Test identical fixed syntax and gate.
    assert len(ORDER) == MAX_REQUESTS
    assert MODEL_IDS["qwen"] == MODELS["qwen"]
    assert MODEL_IDS["minimax"] == MODELS["minimax"]
    for lane in ORDER:
        fake = type("Packet", (), {
            "identical_messages": lambda self, _p: (
                {"role": "system", "content": "NO_ORDERS"},
                {"role": "user", "content": "SNAPSHOT"},
            ),
        })()
        payload = _body(lane, fake)
        assert payload["model"] == MODEL_IDS[lane]
        assert payload["stream"] is False
        assert payload["messages"] == list(fake.identical_messages(lane))
        assert "tools" not in payload and "tool_choice" not in payload
    assert _budget_gate({"data": {"limit": 2, "limit_remaining": 1}}) == (
        Decimal("2"), Decimal("1"),
    )
    for bad in [
        {"data": {"limit": 50, "limit_remaining": 10}},
        {"data": {"limit": 2, "limit_remaining": 0.01}},
        {"data": {"is_management_key": True, "limit": 2, "limit_remaining": 2}},
    ]:
        try:
            _budget_gate(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("BUDGET_GATE_FAILED_OPEN")
    print("ARENA_TRIO SELFTEST=PASS_OFFLINE")
    print("ARENA_TRIO modes=NO_TRADE_OR_CANDIDATE_ONLY")
    print("ARENA_TRIO baseline=DEEPSEEK_OPENROUTER_RESEARCH_NOT_BRAIN_RUNTIME")
    print("ARENA_TRIO actual_paid_POSTs=0 key_reads=0 orders=0")
    return 0


def preflight(sha):
    snap, packet = _packet(sha)
    print("ARENA_TRIO mode=READ_ONLY_PREFLIGHT")
    print("ARENA_TRIO markets=" + str(len(packet.symbols)))
    print("ARENA_TRIO source_SHA256=" + snap.sha256_hex)
    print("ARENA_TRIO common_SHA256=" + packet.packet_sha256)
    print("ARENA_TRIO common_bytes=" + str(len(packet.canonical_market_bytes)))
    print("ARENA_TRIO classification=RESEARCH_ONLY_NOT_TRADE_APPROVED")
    print("ARENA_TRIO DEEPSEEK_MODEL=" + MODEL_IDS["deepseek"])
    print("ARENA_TRIO NOTE=DEEPSEEK_RESEARCH_VERSION_MAY_DIFFER_FROM_BRAIN")
    print("ARENA_TRIO QWEN_MODEL=" + MODEL_IDS["qwen"])
    print("ARENA_TRIO MINIMAX_MODEL=" + MODEL_IDS["minimax"])
    print("ARENA_TRIO max_paid_POSTs=" + str(MAX_REQUESTS))
    print("ARENA_TRIO public_GETs=0 paid_POSTs=0 key_reads=0 orders=0")
    print("ARENA_TRIO RESULT=READY_FOR_SEPARATE_EXPLICIT_PAID_PROBE")
    return 0


def run_once(sha):
    if os.geteuid() != 0:
        raise ValueError("ROOT_REQUIRED")
    snap, common = _packet(sha)
    print("ARENA_TRIO mode=ONE_SHOT_HISTORICAL_RESEARCH")
    print("ARENA_TRIO source_SHA256=" + snap.sha256_hex)
    print("ARENA_TRIO shared_input_SHA256=" + common.packet_sha256)
    print("ARENA_TRIO max_paid_POSTs=" + str(MAX_REQUESTS))
    print("ARENA_TRIO DEEPSEEK_note=OPENROUTER_FLASH_1017_NOT_EXISTING_BRAIN")
    if input("Autorizzi TRE chiamate a pagamento (non ordini)? Scrivi SI: ").strip() != "SI":
        raise ValueError("USER_CANCELLED")
    key_cache = {}   # never printed or stored to disk
    results = []
    for lane in ORDER:
        # Reuse already configured provider keys. DeepSeek research uses the
        # Qwen OpenRouter key; no production Brain secret is accessed.
        owner = KEY_OWNER[lane]
        if owner not in key_cache:
            key_cache[owner] = _read_key(owner)
        key = key_cache[owner]
        try:
            lim, remaining = _budget_gate(_http("/key", key, None))
            print("ARENA_TRIO " + lane.upper() + "_key_limit_usd=" + str(lim)
                  + " remaining_before_usd=" + str(remaining), flush=True)
            # Exactly one paid POST; never retry even on timeout.
            body = _http("/chat/completions", key, _body(lane, common))
            result = _read_choice(lane, common, body)
            results.append(result)
            print("ARENA_TRIO " + lane.upper() + "_RESULT=" + json.dumps(
                result, sort_keys=True, ensure_ascii=True), flush=True)
        except Exception as e:
            # Only fixed error codes, never log model content or credentials.
            safe = str(e)
            if re.fullmatch(r"[A-Z0-9_]{3,64}", safe) is None:
                safe = "RESPONSE_OR_PROVIDER_FAILED"
            print("ARENA_TRIO " + lane.upper() + "_FAILED=" + safe, flush=True)
            # Fail closed for the whole comparison to avoid selection bias.
            print("ARENA_TRIO RESULT=INCOMPLETE_COMPARISON_NO_RETRY_NO_DEPLOY")
            return 2
    print("ARENA_TRIO results=" + str(len(results)) + "/3")
    print("ARENA_TRIO orders=0 files_written=0 services_changed=0")
    print("ARENA_TRIO RESULT=THREE_HISTORICAL_MODEL_CHOICES_RECORDED_NO_DEPLOY")
    return 0


def main():
    if sys.argv[1:] == ["--selftest"]:
        return selftest()
    if len(sys.argv) == 3 and sys.argv[1] == "--preflight":
        return preflight(sys.argv[2])
    if (len(sys.argv) == 4 and sys.argv[1] == "--run"
            and sys.argv[3] == "--confirm-three-paid=YES"):
        return run_once(sys.argv[2])
    print("ARENA_TRIO RESULT=EXPLICIT_SELFTEST_PREFLIGHT_OR_PAID_RUN_REQUIRED")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, TypeError, KeyError, UnicodeError) as e:
        safe = str(e)
        if re.fullmatch(r"[A-Z0-9_]{3,64}", safe) is None:
            safe = "RESEARCH_PREFLIGHT_FAILED"
        print("ARENA_TRIO RESULT=FAILED_" + safe)
        sys.exit(2)
