"""Registro del laboratorio. Non scrive il journal operativo e non riscrive la memoria del Brain."""
from __future__ import annotations

import json
import os
from pathlib import Path


def _refuse_operational_dir(directory: Path) -> None:
    resolved = directory.resolve()
    parts = set(resolved.parts)
    if "superbot-desk-data" in parts or resolved.name in {"journal.db", "budget.db"}:
        raise ValueError("operational_store_refused")
    if (resolved / "journal.db").exists() or (resolved / "budget.db").exists():
        raise ValueError("operational_store_refused")
    for parent in (resolved, *resolved.parents):
        if parent.name == "superbot-desk-data":
            raise ValueError("operational_store_refused")


class ShadowStore:
    """JSONL append-only in una cartella scelta dal chiamante."""

    def __init__(self, directory: Path):
        if not isinstance(directory, Path):
            raise ValueError("invalid_store")
        _refuse_operational_dir(directory)
        directory.mkdir(parents=True, exist_ok=True)
        _refuse_operational_dir(directory)
        self.path = directory / "shadow_decisions.jsonl"
        if self.path.exists() and not self.path.is_file():
            raise ValueError("invalid_store")

    def append(self, record: dict) -> None:
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if "Bearer " in line or "sk-" in line or "freellmapi-" in line:
            raise ValueError("secret_in_record")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line:
                rows.append(json.loads(line))
        return rows
