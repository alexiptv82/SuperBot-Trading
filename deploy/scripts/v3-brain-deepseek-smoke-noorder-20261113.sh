#!/usr/bin/env bash
# Brain PAPER follow-up: inspect installed stage + ONE DeepSeek JSON inference, NO orders.
# Designed for VPS Singapore. Never writes run/mandate/pause/journal/budget or changes services.
# Requires root only to read root-owned /etc/superbot-v3-paper/brain-ai.env.
set -euo pipefail
umask 077
STAGE=/opt/superbot-v3-rc84-stage
RUN=/opt/superbot-v3-paper-runs/brain-v3-paper20261111
ENVFILE=/etc/superbot-v3-paper/brain-ai.env
PYTHON=/usr/bin/python3
printf 'BRAIN_SMOKE stage_sha='
git -C "$STAGE" rev-parse HEAD || exit 2
printf 'BRAIN_SMOKE stage_dirty_count='
git -C "$STAGE" status --porcelain | wc -l
printf 'BRAIN_SMOKE src_contract_rule='
grep -n 'lever <= ' "$STAGE/backend/v3/runner/contracts.py" | head -1 || true
printf 'BRAIN_SMOKE paused='
if test -f "$RUN/pause.flag"; then echo 1; else echo 0; fi
printf 'BRAIN_SMOKE exit_unit='
systemctl is-active superbot-v3-paper-brain-exit.service || true
printf 'BRAIN_SMOKE runner_unit='
systemctl is-active superbot-v3-paper-brain-runner.service || true
"$PYTHON" - "$RUN" "$ENVFILE" <<'PY'
import json
import ssl
import sys
import time
from pathlib import Path
from urllib import request, error

run, envfile = Path(sys.argv[1]), Path(sys.argv[2])
def report(**kwargs):
    print("BRAIN_SMOKE " + " ".join(f"{k}={v}" for k, v in kwargs.items()), flush=True)

try:
    cfg = json.loads((run / "runner_config.json").read_text(encoding="utf-8"))
    model = cfg["model"]
    thinking = cfg["thinking"]
    effort = cfg["reasoning_effort"]
    tokens = cfg["max_tokens"]
    report(config_model=model, thinking=thinking, effort=effort, max_tokens=tokens)
    if cfg["initial_equity"] != "2000":
        report(result="BLOCK", reason="unexpected_brain_equity")
        sys.exit(2)
    if not (run / "pause.flag").is_file():
        report(result="BLOCK", reason="run_not_paused")
        sys.exit(2)
except (OSError, KeyError, TypeError, ValueError):
    report(result="BLOCK", reason="invalid_config_or_run")
    sys.exit(2)

try:
    # Parse only the single EnvironmentFile key. Never evaluate it as shell code.
    lines = envfile.read_text(encoding="utf-8").splitlines()
    vals = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("DEEPSEEK_API_KEY="):
            v = line.split("=", 1)[1].strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                v = v[1:-1]
            vals.append(v)
    api_key = vals[-1] if len(vals) == 1 else ""
    report(key_present=int(bool(api_key)))
    if not api_key:
        report(result="BLOCK", reason="key_unavailable_or_ambiguous")
        sys.exit(2)
except (OSError, UnicodeError):
    report(result="BLOCK", reason="envfile_unavailable")
    sys.exit(2)

# A single NO_ORDER inference, same model, JSON mode, thinking flags, token cap and 30s timeout
# as V3 production. This verifies provider access, not the full Bitget->Brain cycle.
payload = {
    "model": model,
    "stream": False,
    "max_tokens": tokens,
    "response_format": {"type": "json_object"},
    "messages": [
        {"role": "system",
         "content": 'JSON diagnostic. Return a JSON object with exactly one key: "kind", value "NO_TRADE". No trading proposal.'},
        {"role": "user", "content": 'Return the requested JSON object. This is a diagnostic, not a trading instruction.'}
    ],
}
if thinking == "enabled":
    payload["thinking"] = {"type": "enabled"}
    if effort != "omit":
        payload["reasoning_effort"] = effort
elif thinking == "disabled":
    payload["thinking"] = {"type": "disabled"}

data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
req = request.Request(
    "https://api.deepseek.com/v1/chat/completions",
    data=data,
    headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
    method="POST",
)
api_key = ""
start = time.monotonic()
try:
    with request.urlopen(req, timeout=30, context=ssl.create_default_context()) as resp:
        status = resp.status
        raw = resp.read(65_537)
except error.HTTPError as exc:
    report(result="FAIL", reason="http_error", http=exc.code, elapsed_s=round(time.monotonic()-start,1))
    sys.exit(1)
except (error.URLError, TimeoutError, OSError) as exc:
    report(result="FAIL", reason=type(exc).__name__, elapsed_s=round(time.monotonic()-start,1))
    sys.exit(1)

duration = round(time.monotonic() - start, 1)
if len(raw) > 65_536:
    report(result="FAIL", reason="response_over_64k", elapsed_s=duration)
    sys.exit(1)
try:
    body = json.loads(raw)
    choices = body["choices"]
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("choices")
    choice = choices[0]
    finish = choice["finish_reason"]
    content = choice["message"]["content"]
    obj = json.loads(content)
    kind = obj.get("kind")
    valid = (finish == "stop" and obj == {"kind": "NO_TRADE"})
    usage = body.get("usage") or {}
    report(http=status, elapsed_s=duration, finish_reason=finish,
           json_valid=int(isinstance(obj, dict)), kind=kind,
           response_accepted=int(valid),
           prompt_tokens=usage.get("prompt_tokens", "?"),
           completion_tokens=usage.get("completion_tokens", "?"),
           total_tokens=usage.get("total_tokens", "?"))
    report(result="PASS" if valid else "FAIL",
           meaning="provider_JSON_NO_TRADE_only" if valid else "invalid_or_truncated_response")
    if not valid:
        sys.exit(1)
except (TypeError, KeyError, ValueError, IndexError):
    report(result="FAIL", reason="invalid_provider_json", elapsed_s=duration)
    sys.exit(1)
PY
