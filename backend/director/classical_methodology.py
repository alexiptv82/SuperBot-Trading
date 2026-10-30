"""Execute the hash-pinned classical scorer as evidence, never a Brain strategy.

Frozen files remain byte-identical. Only dependency binding is redirected to
the equally frozen seasonal function; operational desk imports are untouched.
"""
import hashlib
from dataclasses import asdict
from pathlib import Path
import sys
from threading import Lock
from types import ModuleType

from director.brain_scalp.legacy_reference import SOURCE_HASHES, REFERENCE_SOURCE_SHA, build_reference
from director.structural_advisory import closed_rows, MAX_AGE_MS

_lock = Lock()
_reader = None


def frozen_reader():
    global _reader
    with _lock:
        if _reader is not None:
            return _reader
        root = Path(__file__).with_name('frozen_classics')
        sources = {}
        for name, digest in SOURCE_HASHES.items():
            source = (root/name).read_bytes()
            if hashlib.sha256(source).hexdigest() != digest:
                raise ValueError('classical_source_hash_mismatch')
            sources[name] = source.decode('utf-8')
        seasonal = ModuleType('_superbot_frozen_seasonal')
        signals = ModuleType('_superbot_frozen_signals')
        sys.modules[seasonal.__name__] = seasonal
        sys.modules[signals.__name__] = signals
        exec(compile(sources['seasonal.py'], str(root/'seasonal.py'), 'exec'), seasonal.__dict__)
        dependency = 'from desk.seasonal import get_seasonal'
        if sources['signals.py'].count(dependency) != 1:
            raise ValueError('unexpected_frozen_dependency')
        signals.get_seasonal = seasonal.get_seasonal
        exec(compile(sources['signals.py'].replace(dependency, ''),
                     str(root/'signals.py'), 'exec'), signals.__dict__)
        _reader = signals.read_symbol
        return _reader


def observe_methodology(symbol, rows, now_ms):
    rows = closed_rows(rows, now_ms)
    # The original really needs >=60 complete 4h bars. No invented history.
    import numpy as np
    reading = frozen_reader()(symbol, np.array(rows, dtype=float), now_ms)
    if reading is None:
        return {'status': 'insufficient_classical_history'}
    # Original numpy computations can expose numpy scalars. Normalize only
    # representation, never scores/values, before strict JSON projection.
    obj = asdict(reading)
    obj['facts'] = {k: v.item() if isinstance(v, np.generic) else v
                    for k, v in obj['facts'].items()}
    value = build_reference(obj, source_sha=REFERENCE_SOURCE_SHA,
        source_hashes=SOURCE_HASHES, observed_ms=int(rows[-1][0])+900000,
        now_ms=now_ms, max_age_ms=MAX_AGE_MS)
    return {'status': 'available', 'value': value}


def project_methodology(raw, symbol, now_ms):
    """Revalidate/allowlist; intentionally NOT the mandatory-review reference."""
    try:
        if not isinstance(raw, dict) or raw.get('status') != 'available':
            return {'status': 'unavailable'}
        value = raw['value']
        if value.get('symbol') != symbol or value.get('authority') != 'advisory_only':
            raise ValueError('invalid_methodology')
        scores = value['direction_scores']
        side = {'LONG': 1, 'SHORT': -1, 'NEUTRAL': 0}[value['legacy_preferred_side']]
        projection = build_reference({'symbol': symbol, 'price': value['observed_price'],
            'long_score': scores['LONG'], 'short_score': scores['SHORT'], 'side': side,
            'facts': value['features'], 'why': value['selected_side_reasons']},
            source_sha=value['source_sha'], source_hashes=value['source_hashes'],
            observed_ms=value['observed_ms'], now_ms=now_ms, max_age_ms=MAX_AGE_MS)
        return {'status': 'available', 'value': projection}
    except (ValueError, KeyError, TypeError):
        return {'status': 'unavailable'}
