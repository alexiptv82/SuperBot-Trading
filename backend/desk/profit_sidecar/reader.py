"""Double read with atomic replacement/race detection; never opens a writer."""
from dataclasses import dataclass
import os
from pathlib import Path
from .common import Freeze, decode, sha, numeric, integer

TOKEN_FIELDS = ("started_ms", "cycles", "last_start_ms", "last_end_ms", "cycle_running", "exec_mode", "portfolio", "last_ok", "open_positions", "version")


def read_bytes(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            raw = stream.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024:
            raise Freeze("source_oversize")
        return raw
    except OSError:
        raise Freeze("source_unavailable") from None


@dataclass(frozen=True)
class Observation:
    state: dict
    heartbeat: dict
    state_hash: str
    cycle_key: str
    run_key: str
    asof_ms: int


def read_consistent(root, portfolio, now_ms, *, max_heartbeat_age_ms=120000, max_cycle_age_ms=2700000, read=read_bytes):
    root = Path(root)
    first = decode(read(root / "heartbeat.json"))
    if not isinstance(first, dict):
        raise Freeze("heartbeat_schema")
    if first.get("exec_mode") != "paper" or first.get("portfolio") != portfolio:
        raise Freeze("paper_identity_unverified")
    if first.get("cycle_running") is not False or first.get("last_ok") is not True:
        raise Freeze("cycle_unfinished_or_failed")
    start = integer(first.get("last_start_ms"), 1)
    end = integer(first.get("last_end_ms"), start)
    integer(first.get("started_ms"), 1)
    integer(first.get("cycles"), 1)
    age = now_ms - numeric(first.get("ts")) * 1000
    if age < -5000 or age > max_heartbeat_age_ms or not 0 <= now_ms-end <= max_cycle_age_ms:
        raise Freeze("stale_heartbeat_or_cycle")
    raw = read(root / "state_v2.json")
    state = decode(raw)
    again = read(root / "state_v2.json")
    second = decode(read(root / "heartbeat.json"))
    if raw != again or any(first.get(k) != second.get(k) for k in TOKEN_FIELDS):
        raise Freeze("source_changed_during_read")
    if not isinstance(state, dict) or not isinstance(state.get("main"), dict):
        raise Freeze("state_schema")
    run = integer(state.get("run_no"), 1)
    run_start = integer(state.get("run_started_ms"), 1)
    if run_start > start:
        raise Freeze("run_changed_after_cycle")
    positions = state["main"].get("positions")
    if not isinstance(positions, dict) or len(positions) != first.get("open_positions"):
        raise Freeze("state_heartbeat_disagree")
    if not isinstance(state["main"].get("closed"), list):
        raise Freeze("closed_schema")
    token = {k: first.get(k) for k in TOKEN_FIELDS}
    run_key = f"{portfolio}:{run}:{run_start}"
    cycle_key = sha([run_key, token])
    # Ignore the frequently refreshed ts in deterministic records; age was checked.
    return Observation(state, token, sha(raw), cycle_key, run_key, end)
