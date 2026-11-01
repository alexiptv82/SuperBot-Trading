"""Reconstruct the unchanged frozen V6.1.1 LONG engine in a TEMP research folder.

This module is never imported by trading workers. The compressed source file
was copied byte-for-byte from user's frozen lab package and MUST match the
published SHA256 before it is imported. Never use it for deploy or orders.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import zlib

from long_shadow_offline_probe import PINNED_ENGINE_SHA256

SOURCE = Path(__file__).with_name('research_frozen_long_v611_engine.zlib.b64')
MAX_ENGINE_BYTES = 20000


def read_frozen_engine_bytes():
    if SOURCE.is_symlink() or not SOURCE.is_file() or SOURCE.stat().st_size > 9000:
        raise ValueError('frozen_research_source_unavailable')
    encoded = SOURCE.read_bytes().strip()
    try:
        compressed = base64.b64decode(encoded, validate=True)
        decompressor = zlib.decompressobj()
        source = decompressor.decompress(compressed, MAX_ENGINE_BYTES+1)
        source += decompressor.flush()
    except (ValueError, zlib.error) as exc:
        raise ValueError('frozen_research_source_corrupted') from exc
    if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
        raise ValueError('frozen_research_source_incomplete')
    if len(source)>MAX_ENGINE_BYTES:
        raise ValueError('frozen_research_source_oversized')
    if hashlib.sha256(source).hexdigest() != PINNED_ENGINE_SHA256:
        raise ValueError('frozen_research_source_sha_mismatch')
    if not source.startswith(b'"""Standalone causal signal engine.'):
        raise ValueError('frozen_research_source_unexpected')
    return source


def materialize_for_research(directory):
    """Research folder must exist and be a real directory; no overwrite."""
    destination=Path(directory)
    if not destination.is_dir() or destination.is_symlink():
        raise ValueError('research_directory_unavailable')
    output=destination/'engine.py'
    if output.exists() or output.is_symlink():
        raise FileExistsError('research_engine_destination_exists')
    # Exclusive create prevents replacement/symlink races in research runner.
    with output.open('xb') as handle:
        handle.write(read_frozen_engine_bytes())
    output.chmod(0o600)
    return output
