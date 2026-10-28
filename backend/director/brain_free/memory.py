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
    research=Path(directory)/'research'/'research_seed.json'
    if research.exists():
        if research.is_symlink() or research.stat().st_size>30000:
            raise ValueError('invalid_research_seed')
        library=json.loads(research.read_text())
        if not isinstance(library,dict) or library.get('evidence_grade') is None:
            raise ValueError('research_seed_requires_provenance')
        out.append({'profile':'research-hypotheses',
                    'provenance':'user_supplied_unverified_nonbinding_not_live_trades',
                    'data':library})
    return out
