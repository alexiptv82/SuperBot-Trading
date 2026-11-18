"""T0 comune della gara: assegnato UNA volta, identico nelle tre run, separato dalla preparazione.

Una run preparata ha ``trial_start_ms: null`` nel manifest: e' in pausa e "non avviata". Il T0 vive in
``arena_t0.json`` (scritto solo dal comando di attivazione autorizzato) e lega le tre run, l'universo dei simboli e
la politica di rischio. Senza T0 valido il runner non parte e la dashboard mostra "non avviato".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

T0_FILE = "arena_t0.json"
T0_SCHEMA = "arena_t0_v1"
MAX_BYTES = 8192
T0_KEYS = {"schema", "trial_start_ms", "run_ids", "symbols_sha256", "risk_policy_hash", "universe_snapshot_sha256",
           "assigned_at_ms", "assigned_by"}


def read_t0(folder: Path, provider: str, run_id: str) -> Optional[dict]:
    """T0 valido per QUESTA run, oppure None (assente, alterato, di un'altra run). Mai eccezioni."""
    path = folder / T0_FILE
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    if (type(raw) is not dict or set(raw) != T0_KEYS or raw.get("schema") != T0_SCHEMA
            or type(raw.get("trial_start_ms")) is not int or raw["trial_start_ms"] <= 0
            or type(raw.get("run_ids")) is not dict or raw["run_ids"].get(provider) != run_id
            or set(raw["run_ids"]) != {"deepseek", "qwen", "minimax"}):
        return None
    return raw


def trial_start(folder: Path, provider: str, run_id: str, manifest_value: object) -> Optional[int]:
    """T0 dal manifest (run preparate prima di questo modulo) oppure dal file T0 comune."""
    if type(manifest_value) is int and manifest_value > 0:
        return manifest_value
    if manifest_value is not None:
        return None
    t0 = read_t0(folder, provider, run_id)
    return None if t0 is None else t0["trial_start_ms"]


def read_t0_agreed(folder: Path, provider: str, run_id: str) -> Optional[dict]:
    """Come ``read_t0`` ma richiede che le TRE run della stessa gara abbiano lo stesso identico file T0
    (stessi byte: stesso T0, run_id, universo, rischio e firma). Altrimenti None: il runner non parte."""
    own = read_t0(folder, provider, run_id)
    if own is None:
        return None
    root = folder.parent.parent
    try:
        body = (folder / T0_FILE).read_bytes()
        for other, other_run in own["run_ids"].items():
            if type(other_run) is not str or other_run != run_id.replace(f"brain-{provider}-", f"brain-{other}-", 1):
                return None
            path = root / other / other_run / T0_FILE
            if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
                return None
            if read_t0(root / other / other_run, other, other_run) is None:
                return None
    except OSError:
        return None
    return own
