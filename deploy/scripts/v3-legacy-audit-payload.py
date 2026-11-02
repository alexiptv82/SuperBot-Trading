"""Build an ephemeral Python stdin payload for the frozen VPS snapshot audit.

Called only in GitHub Actions checkout. No output files, no secrets on stdout.
"""
from __future__ import annotations

import base64
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
files = [
    ("v3.events", ROOT / "backend/v3/events.py"),
    ("v3.legacy_audit", ROOT / "backend/v3/legacy_audit.py"),
]
print("import base64,sys,types")
print("p=types.ModuleType('v3'); p.__path__=[]; sys.modules['v3']=p")
for name, path in files:
    blob = base64.b64encode(path.read_bytes()).decode("ascii")
    print(f"m=types.ModuleType({name!r});m.__package__='v3';sys.modules[{name!r}]=m")
    print(f"exec(compile(base64.b64decode({blob!r}),{str(path.name)!r},'exec'),m.__dict__)")
remote = ROOT / "deploy/scripts/v3-legacy-readonly-audit-remote.py"
print(remote.read_text())
