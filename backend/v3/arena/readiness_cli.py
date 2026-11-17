"""Command-line, offline-only report for the prepared Arena trial.

Run: python -m backend.v3.arena.readiness_cli
Exit status 2 means that evidence is incomplete and the trial must NOT start.
This reads repository config JSON only; it cannot contact AI providers, VPS,
or exchanges, approve mandates, or change any file.
"""
from __future__ import annotations

import json
import sys

from backend.v3.arena.readiness import audit_trial_configs


def main() -> int:
    try:
        result = audit_trial_configs()
    except (ValueError, OSError):
        print(json.dumps({"schema": "arena_trial_readiness_preflight_v1",
                          "trial_ready": False, "code": "CONFIG_READ_REFUSED"}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["trial_ready"] is True else 2


if __name__ == "__main__":
    sys.exit(main())
