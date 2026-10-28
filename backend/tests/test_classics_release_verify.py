"""Negative tests of release continuity barriers, never a VPS connection."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import pytest

path = Path(__file__).resolve().parents[2]/'deploy/scripts/classics_scalp_verify.py'
spec = importlib.util.spec_from_file_location('classic_release_check', path)
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def state():
    return {'run_no':7, 'run_started_ms':123,
            'main': {'positions': {'BTC': {'id':4, 'symbol':'BTC', 'open_ms':50}},
                     'closed': [{'id':1, 'net':3}]},
            'capital': {'policy':'salvadanaio-only-v1','status':'READY','vault':{'balance':'10'}},
            'budget': {'total_spent':.4}, 'deepseek_budget': {'total_spent':.03}}


@pytest.mark.parametrize('change', ['reset','lost_position','history','budget','vault'])
def test_continuity_rejects_destructive_changes(change):
    before = state(); after = deepcopy(before)
    if change == 'reset': after['run_no'] += 1
    if change == 'lost_position': after['main']['positions'] = {}
    if change == 'history': after['main']['closed'] = []
    if change == 'budget': after['deepseek_budget']['total_spent'] = 0
    if change == 'vault': after['capital']['vault']['balance'] = '9'
    with pytest.raises(AssertionError): verify.continuity(before, after)


def test_protective_final_close_preserves_position_identity():
    before = state(); after = deepcopy(before)
    pos = after['main']['positions'].pop('BTC')
    after['main']['closed'].append(dict(pos, net=2))
    verify.continuity(before, after)
    after['main']['closed'][-1]['partial'] = True
    with pytest.raises(AssertionError, match='POSITION_LOST'):
        verify.continuity(before, after)


def test_historical_prefix_accepts_append_but_refuses_rewrite(tmp_path):
    path = tmp_path/'learning_log.jsonl'
    original = b'{"old":1}\n'
    saved = {'size':len(original), 'sha256':verify.digest(original)}
    path.write_bytes(original+b'{"new":2}\n')
    verify.check_prefix(path, saved)
    path.write_bytes(b'{"old":2}\n'+b'{"new":2}\n')
    with pytest.raises(AssertionError, match='PROTECTED_PREFIX_CHANGED'):
        verify.check_prefix(path, saved)
