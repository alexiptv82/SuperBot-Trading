"""PAPER classic release: verified backup, source hashes and continuity only.

No writes to bot volumes, no start/stop, no trading runtime imports. Private
metadata under /opt/superbot-deploys records the baseline for the postflight.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path('/opt/superbot-desk-data')
PROFILES = ('hawk', 'bull')
SOURCES = ('cli', 'engine', 'signals', 'brain', 'deepseek_collab',
           'market_context', 'seasonal', 'salvadanaio', 'position_card')
PROTECTED = ('trade_history.jsonl', 'learning_log.jsonl', 'lessons.md', 'errors.md')


def command(args):
    return subprocess.check_output(args, text=True, timeout=90)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory():
    names = command(['docker', 'ps', '--format', '{{.Names}}']).splitlines()
    return {n: json.loads(command(['docker', 'inspect', n]))[0] for n in names}


def verify_source(container, revision, extra=()):
    for module in SOURCES + tuple(extra):
        expected = digest(subprocess.check_output(['git', 'show', revision+':backend/desk/'+module+'.py']))
        actual = command(['docker', 'exec', container, 'sha256sum', '/app/backend/desk/'+module+'.py']).split()[0]
        assert expected == actual, 'SOURCE_MISMATCH:'+container+':'+module


def verify_runtime(inv, revision):
    for p in PROFILES:
        n = 'superbot-desk-'+p
        i = inv[n]
        e = dict(x.split('=', 1) for x in i['Config'].get('Env', []) if '=' in x)
        assert i['State']['Running'] and e.get('DESK_MODE') == 'paper', 'NOT_RUNNING_PAPER:'+p
        assert i['Config'].get('Labels', {}).get('superbot.sha') == revision, 'SOURCE_LABEL:'+p
        assert e.get('DESK_CAPITAL_V1') == 'off', 'CAPITAL_MODE_CHANGED:'+p
        assert e.get('DESK_DEEPSEEK_CLASSICS') == 'paper', 'ADVISER_MODE_CHANGED:'+p
        assert e.get('DESK_MACRO_POLICY') == 'observe', 'MACRO_MODE_CHANGED:'+p
        writers = [name for name, obj in inv.items() if any(
            m.get('RW') and m['Source'] == str(ROOT/p) for m in obj.get('Mounts', []))]
        assert writers == [n], 'DUPLICATE_WRITER:'+p


def continuity(before, after):
    assert all(after.get(k) == before.get(k) for k in ('run_no', 'run_started_ms')), 'RUN_RESET'
    previous = before['main'].get('closed', [])
    assert after['main'].get('closed', [])[:len(previous)] == previous, 'CLOSED_HISTORY_CHANGED'
    for budget in ('budget', 'deepseek_budget'):
        assert float(after.get(budget, {}).get('total_spent', 0)) >= float(
            before.get(budget, {}).get('total_spent', 0)), 'BUDGET_RESET'
    for symbol, pos in before['main'].get('positions', {}).items():
        current = after['main'].get('positions', {}).get(symbol)
        identity = lambda p: (p.get('id'), p.get('symbol'), p.get('open_ms'))
        if current and identity(current) == identity(pos):
            continue
        assert any(identity(t) == identity(pos) and not t.get('partial')
                   for t in after['main'].get('closed', [])), 'POSITION_LOST:'+symbol
    assert (after.get('capital') or {}).get('policy') == 'salvadanaio-only-v1', 'VAULT_POLICY_CHANGED'
    assert (after.get('capital') or {}).get('status') == 'READY', 'VAULT_NOT_READY'
    old_balance = float((before.get('capital') or {}).get('vault', {}).get('balance', 0))
    new_balance = float(after['capital'].get('vault', {}).get('balance', 0))
    assert new_balance >= old_balance, 'VAULT_DECREASED'


def check_prefix(path, saved):
    with path.open('rb') as stream:
        data = stream.read(saved['size'])
    assert path.stat().st_size >= saved['size'] and digest(data) == saved['sha256'], 'PROTECTED_PREFIX_CHANGED'


def backup(tag):
    existing = set(Path('/opt/superbot-backups').glob('bots-*-'+tag))
    subprocess.run(['python3', '-I', 'deploy/scripts/backup_brain.py', '--root', str(ROOT),
                    '--dir', '/opt/superbot-backups', '--keep', '10', '--tag', tag], check=True)
    created = set(Path('/opt/superbot-backups').glob('bots-*-'+tag)) - existing
    assert len(created) == 1, 'BACKUP_NOT_UNIQUE'
    directory = created.pop()
    manifest = json.loads((directory/'MANIFEST.json').read_text())
    assert manifest['coerenza']['confine_di_ciclo_verificato'], 'BACKUP_BOUNDARY_NOT_VERIFIED'
    # Independent readback of the manifest after the backup utility's own restore check.
    for item in manifest['file']:
        path = directory/item['file']
        assert digest(path.read_bytes()) == item['sha256'], 'BACKUP_READBACK_FAILED'
    return directory


def main():
    target, base = os.environ['TARGET_SHA'], os.environ['BASE_SHA']
    assert all(re.fullmatch('[0-9a-f]{40}', x) for x in (target, base)), 'INVALID_SHA'
    snapshot = Path('/opt/superbot-deploys')/('classic-scalp-'+target[:12]+'-preflight.json')
    phase = os.environ['PHASE']
    if phase == 'preflight':
        assert not snapshot.exists(), 'PREFLIGHT_ALREADY_EXISTS'
        inv = inventory()
        verify_runtime(inv, base)
        for p in PROFILES:
            n = 'superbot-desk-'+p
            assert inv[n]['State'].get('Health', {}).get('Status') == 'healthy', 'BASE_NOT_HEALTHY'
            verify_source(n, base)
        directory = backup('classic_scalp_preflight')
        profiles = {}
        for p in PROFILES:
            state = json.loads((directory/p/'state_v2.json').read_text())
            protected = {}
            for name in PROTECTED:
                path = directory/p/name
                if not path.exists():
                    assert name == 'errors.md', 'MISSING_HISTORY:'+p+':'+name
                    continue
                data = path.read_bytes()
                protected[name] = {'size': len(data), 'sha256': digest(data)}
            profiles[p] = {'state': state, 'protected': protected}
        saved = {'base': base, 'target': target, 'backup': str(directory), 'profiles': profiles,
                 'containers': {n: {'id': i['Id'], 'started': i['State']['StartedAt']} for n, i in inv.items()}}
        snapshot.parent.mkdir(exist_ok=True)
        fd = os.open(snapshot, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(saved, stream)
            stream.flush()
            os.fsync(stream.fileno())
        print('PREFLIGHT_SOURCE_BACKUP_RESTORE=PASS', directory.name)
        return
    assert phase == 'postflight', 'INVALID_PHASE'
    saved = json.loads(snapshot.read_text())
    assert saved['target'] == target and saved['base'] == base, 'SNAPSHOT_MISMATCH'
    # Let the independent Docker healthcheck and the first actual cycle finish.
    for attempt in range(72):
        inv = inventory()
        ready = all(inv.get('superbot-desk-'+p, {}).get('State', {}).get('Health', {}).get('Status') == 'healthy'
                    for p in PROFILES)
        if ready:
            break
        if attempt % 6 == 0:
            print('WAITING_FOR_CLASSIC_HEALTH', flush=True)
        time.sleep(5)
    verify_runtime(inv, target)
    for name, old in saved['containers'].items():
        if name in ('superbot-desk-hawk', 'superbot-desk-bull'):
            continue
        assert name in inv and inv[name]['Id'] == old['id'] and inv[name]['State']['StartedAt'] == old['started'], 'UNRELATED_RESTART:'+name
    print('BRAINS_APP_AND_OTHER_CONTAINERS_UNCHANGED=PASS')
    for p in PROFILES:
        n = 'superbot-desk-'+p
        assert inv[n]['State'].get('Health', {}).get('Status') == 'healthy', 'NEW_NOT_HEALTHY:'+p
        assert inv[n]['RestartCount'] == 0, 'UNEXPECTED_RESTART:'+p
        verify_source(n, target, ('classic_opportunities',))
        h = json.loads((ROOT/p/'heartbeat.json').read_text())
        assert h['version'] == target[:7] and h.get('last_ok') is True, 'BAD_HEARTBEAT:'+p
        assert time.time()*1000 - h['last_end_ms'] < 600000, 'STALE_CYCLE:'+p
        a = json.loads((ROOT/p/'state_v2.json').read_text())
        continuity(saved['profiles'][p]['state'], a)
        for name, data in saved['profiles'][p]['protected'].items():
            check_prefix(ROOT/p/name, data)
        params = h['params']
        assert params['classic_mechanism'] == 'classics-additive-scalp-v1', 'MECHANISM_NOT_ACTIVE'
        assert params['limits']['min_initial_margin'] == (100 if p == 'hawk' else 150), 'SIZE_FLOOR'
        assert params['limits']['min_initial_leverage'] == 10, 'LEVERAGE_FLOOR'
        assert a.get('last_opportunity_cycle', {}).get('version') == 'classics-additive-scalp-v1', 'NO_NEW_CYCLE'
        print('CLASSIC_POSTFLIGHT=PASS', p, 'run='+str(a.get('run_no')),
              'open='+str(len(a['main'].get('positions', {}))), 'histories=preserved', 'vault=READY')
    directory = backup('classic_scalp_postflight')
    print('POSTFLIGHT_BACKUP_RESTORE=PASS', directory.name)
    print('CLASSICS_SCALP_POSTFLIGHT=PASS')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('CLASSICS_RELEASE_BLOCKED', type(exc).__name__,
              str(exc)[:180] if isinstance(exc, AssertionError) else 'sanitized')
        raise SystemExit(1)
