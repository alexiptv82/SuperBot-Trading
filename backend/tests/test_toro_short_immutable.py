"""Protect the existing SHORT engine against accidental edits in the LONG-only study.

Git blob hashes are pinned to the approved Fase-3 baseline f8332c92.
Changing any of these source files requires a separate, reviewed approval:
the 15m LONG experiment must live exclusively in new isolated modules.
"""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[2]
FROZEN_BLOBS = {
    "backend/desk/brain.py": "6a8fc76448e486f7db86edb4bdfb9dbbbf249fcf",
    "backend/desk/signals.py": "5dca1e58db4bce70c170e60e343d10cf7336bde9",
    "backend/desk/cli.py": "17dd1091c57054d7bfb47a7844a73ffdb180ed35",
    "backend/desk/engine.py": "6e2110a55ef39ee49439ff9b085782376224e601",
}


def test_original_short_strategy_sources_are_byte_identical():
    for path, frozen_blob in FROZEN_BLOBS.items():
        data = (ROOT / path).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        assert blob == frozen_blob, f"{path} modified: the protected SHORT baseline must remain unchanged"
