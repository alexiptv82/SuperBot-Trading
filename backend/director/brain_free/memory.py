"""Causal episodic memory; completed positions, not partial-close rows."""
import json
from pathlib import Path

def recent(store):return store.recent(10)

def seeds(directory):
    out=[]
    for profile in ('hawk','bull'):
        path=Path(directory)/profile/'backtest_seed.json'
        if not path.exists():continue
        if path.is_symlink() or path.stat().st_size>100000:raise ValueError('invalid_seed')
        out.append({'profile':profile,'provenance':'historical_backtest_synthetic_unverified_not_current_run',
                    'data':json.loads(path.read_text())})
    return out
