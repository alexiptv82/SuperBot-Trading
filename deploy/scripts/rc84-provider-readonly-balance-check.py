#!/usr/bin/env python3
"""One-shot READ-ONLY AI provider metadata/balance check on Singapore VPS.

No trading mutation, no model inference, no credit purchase. Outputs only
fixed tokens, HTTP status and booleans; does not print API keys, errors,
bodies, model lists, raw balance or URLs with account identifiers.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import stat
import sys
import urllib.error
import urllib.request

ROOT = Path("/opt/superbot-v3-paper-runs")
FILES = Path("/etc/superbot-v3-paper")
RUNS = {
    "FALCO": ROOT / "classic-hawk-paper20261111",
    "TORO": ROOT / "classic-bull-paper20261111",
    "BRAIN": ROOT / "brain-v3-paper20261111",
}

def refuse(reason: str) -> None:
    print("RC84_PROVIDER_READONLY_REFUSED=" + reason)
    raise SystemExit(2)

def read_key(filename: str, name: str) -> str:
    path = FILES / filename
    if path.is_symlink() or not path.is_file():
        refuse("PRIVATE_ENV_MISSING")
    st=path.stat()
    if st.st_uid != 0 or not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o600 or st.st_size > 8192:
        refuse("PRIVATE_ENV_PERMISSIONS")
    records=[]
    try:
        records=path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError):
        refuse("PRIVATE_ENV_FORMAT")
    parsed={}
    for row in records:
        if row and not row.startswith("#"):
            if "=" not in row: refuse("PRIVATE_ENV_FORMAT")
            k,v=row.split("=",1)
            if not re.fullmatch(r"[A-Z_][A-Z0-9_]*",k):refuse("PRIVATE_ENV_KEY_NAME")
            parsed[k]=v
    value=parsed.get(name,"")
    if not re.fullmatch(r"[A-Za-z0-9_.=-]{20,1024}",value):
        refuse("PROVIDER_KEY_UNAVAILABLE")
    return value

def get_json(url: str, headers: dict) -> tuple[int, dict | None]:
    # Force direct TLS to the provider. No proxy; default system CA verification.
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req=urllib.request.Request(url,headers=headers,method="GET")
    try:
        with op.open(req,timeout=12) as resp:
            status=resp.status
            if status != 200: return status,None
            raw=resp.read(16384)
    except urllib.error.HTTPError as e:
        return int(e.code),None
    except (OSError, ValueError, TimeoutError):
        return 0,None
    try:
        x=json.loads(raw)
    except (ValueError, UnicodeError):
        return 200,None
    return 200,x if isinstance(x,dict) else None

def main() -> None:
    for label,p in RUNS.items():
        if (not p.is_dir() or p.is_symlink()
                or not (p/"pause.flag").is_file()
                or (p/"pause.flag").is_symlink()):
            refuse(label+"_NOT_PAUSED")
    try:
        mandate=json.loads((RUNS["BRAIN"]/"mandate.json").read_text())
        if mandate.get("approved") is not False: refuse("BRAIN_MANDATE_APPROVED")
    except (OSError,ValueError):
        refuse("BRAIN_MANDATE_UNKNOWN")

    falco=read_key("falco-ai.env","ANTHROPIC_API_KEY")
    toro=read_key("toro-ai.env","ANTHROPIC_API_KEY")
    brain=read_key("brain-ai.env","DEEPSEEK_API_KEY")
    print("RC84_PROVIDER_THREE_PAUSED_KEYS_PRESENT=PASS",flush=True)
    # GET /v1/models is model metadata, NOT a billable inference call.
    # When both classics share one key, request it only once.
    seen={}
    for label,key in (("FALCO",falco),("TORO",toro)):
        if key not in seen:
            status,data=get_json(
                "https://api.anthropic.com/v1/models?limit=1",
                {"x-api-key":key,"anthropic-version":"2023-06-01","accept":"application/json"})
            seen[key]=(status, isinstance(data,dict) and isinstance(data.get("data"),list))
        status,valid=seen[key]
        print("RC84_CLAUDE_"+label+"_MODELS_HTTP="+str(status),flush=True)
        print("RC84_CLAUDE_"+label+"_KEY_ACCESSIBLE="+str(status==200 and valid),flush=True)
    # Official DeepSeek GET balance API, no token generation.
    status,data=get_json("https://api.deepseek.com/user/balance",
                         {"Authorization":"Bearer "+brain,"accept":"application/json"})
    available=(data.get("is_available") if isinstance(data,dict) else None)
    print("RC84_DEEPSEEK_BALANCE_HTTP="+str(status),flush=True)
    print("RC84_DEEPSEEK_BALANCE_AVAILABLE="+str(available if type(available) is bool else "UNKNOWN"),flush=True)
    print("RC84_PROVIDER_NO_INFERENCE_NO_TRADES_NO_CREDIT_PURCHASE=True",flush=True)
    print("RC84_PROVIDER_NO_KEYS_OR_BALANCE_VALUES_LOGGED=True",flush=True)
    print("RC84_CLAUDE_PREPAID_CREDIT_NOT_MEASURABLE_WITH_MODELS_GET=True",flush=True)

if __name__=="__main__":
    main()
