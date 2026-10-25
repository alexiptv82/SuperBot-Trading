#!/usr/bin/env python3
"""One-shot secure Tailscale join: auth key only on SSH stdin + RAM-only temporary file.

Does NOT modify bot state, SSH settings, system DNS, default route, firewall
rules, or container configuration. The key is never emitted to output/logs.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

def main():
    key=sys.stdin.readline().strip()
    if not key.startswith("tskey-auth-"):
        print("TAILSCALE_AUTH_SECRET_INVALID")
        return 2
    status=subprocess.run(["tailscale","status","--json"],capture_output=True,text=True,timeout=12)
    if status.returncode==0:
        try:
            state=json.loads(status.stdout)
            if state.get("BackendState")=="Running" and (state.get("Self") or {}).get("Online"):
                print("TAILSCALE_ALREADY_ONLINE")
                return 0
        except ValueError:
            pass
    fd,path=tempfile.mkstemp(prefix=".superbot-ts-auth-",dir="/dev/shm")
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"w") as f:
            f.write(key)
            f.flush()
        key=""
        cmd=["tailscale","up","--auth-key=file:"+path,
             "--accept-dns=false","--accept-routes=false","--advertise-exit-node=false",
             "--ssh=false","--netfilter-mode=off","--hostname=superbot-mcp-sg"]
        try:
            done=subprocess.run(cmd,capture_output=True,text=True,timeout=110)
        except subprocess.TimeoutExpired:
            print("TAILSCALE_JOIN_TIMEOUT")
            return 3
        if done.returncode:
            print("TAILSCALE_JOIN_FAILED_EXIT_"+str(done.returncode))
            return done.returncode
        print("TAILSCALE_ENROLL_SUCCESS")
        return 0
    finally:
        try:Path(path).unlink()
        except FileNotFoundError:pass

if __name__=="__main__":
    raise SystemExit(main())
