#!/usr/bin/env python3
"""RC70 no-write Singapore inspection before authorized PAPER dashboard preview."""
from __future__ import annotations
import json, os, pathlib, re, shutil, subprocess, sys, time
def command(argv, timeout=8):
    try:
        p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                         text=True,check=False,timeout=timeout)
        return p.stdout.strip() if p.returncode==0 else None
    except (OSError,subprocess.TimeoutExpired):
        return None
def inspect(name):
    text=command(["docker","inspect",name])
    if not text:return None
    try:return json.loads(text)[0]
    except (ValueError,IndexError):return None
def flag(k,v):
    print("RC70_"+k+"="+str(v))
flag("READ_ONLY",True)
flag("UTC",time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()))
root=pathlib.Path("/opt")
try:
    usage=shutil.disk_usage("/opt")
    flag("FREE_GIB",round(usage.free/1073741824,1))
except OSError:flag("FREE_GIB","UNKNOWN")
app=inspect("superbot")
flag("EXISTING_WEB_RUNNING",app.get("State",{}).get("Running") if app else "UNKNOWN")
flag("EXISTING_WEB_RESTART",app.get("HostConfig",{}).get("RestartPolicy",{}).get("Name") if app else "UNKNOWN")
flag("EXISTING_WEB_IMAGE_PRESENT",bool(app and app.get("Image")))
flags={}
if app:
    env=dict(x.split("=",1) for x in app.get("Config",{}).get("Env",[]) if "=" in x)
    for n in ("TRADING_MODE","DESK_MODE","DESK_DATA_DIR","DESK_DATA_DIR_BULL",
              "V3_JOURNAL_PATH","V3_RUN_ID","V3_RUNNER_CONFIG_PATH",
              "V3_CLOSE_REQUEST_PATH","TELEGRAM_COMMANDS_ENABLED"):
        value=env.get(n)
        flags[n]=value
        flag("WEB_"+n+"_SET",bool(value))
    flag("WEB_TRADING_MODE_IS_PAPER",env.get("TRADING_MODE")=="paper")
    flag("WEB_DESK_MODE_IS_PAPER",env.get("DESK_MODE")=="paper")
    flag("WEB_MOUNT_COUNT",len(app.get("Mounts",[])))
    flag("WEB_PUBLISHED_PORTS", sorted((app.get("NetworkSettings") or {}).get("Ports") or {}))
for name in ("superbot-desk-hawk","superbot-desk-bull"):
    d=inspect(name)
    flag(name.replace("-","_").upper()+"_RUNNING",d.get("State",{}).get("Running") if d else "UNKNOWN")
    flag(name.replace("-","_").upper()+"_RESTART",d.get("HostConfig",{}).get("RestartPolicy",{}).get("Name") if d else "UNKNOWN")
    if d:
        env=dict(x.split("=",1) for x in d.get("Config",{}).get("Env",[]) if "=" in x)
        flag(name.replace("-","_").upper()+"_PAPER",env.get("DESK_MODE")=="paper")
for d in ("/opt/superbot/data/superbot.db","/opt/superbot-web/build/index.html",
          "/etc/nginx/sites-enabled/superbot","/opt/superbot-v3-paper-runs/brain-v3-rc20261106"):
    p=pathlib.Path(d)
    kind = "APP_DATABASE" if d.endswith("superbot.db") else "FRONTEND" if d.endswith("index.html") else "NGINX_SITE" if "sites-enabled" in d else "PREPARED_BRAIN"
    flag(kind+"_EXISTS",p.exists())
for program in ("python3","docker","nginx","git","tar","curl"):
    flag("BIN_"+program.upper(),bool(shutil.which(program)))
for port in (8002,18003,18080,8080,8003):
    out=command(["ss","-H","-ltn",f"( sport = :{port} )"])
    flag(f"PORT_{port}_LISTENING",bool(out))
for service in ("superbot-desk-hawk","superbot-desk-bull","superbot-brain-free","superbot-v3-falco-exit","superbot-v3-toro-exit"):
    s=command(["systemctl","is-active",service+".service"])
    flag("SERVICE_"+service.upper().replace("-","_")+"_ACTIVE",s=="active")
# No code, logs, env values, paths to secrets, or token material printed.
print("RC70_PREDEPLOY_AUDIT_FINISHED=True")
