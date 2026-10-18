"""Read-only migration metadata audit. Run with python3, never import bot modules.
No restart, exec inside containers, network request, database open, or file write.
Output only selected non-secret fields; Docker environment is never printed.
"""
import json
import os
import pathlib
import subprocess
import time


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def main():
    for name in ('superbot', 'superbot-staging', 'superbot-pool',
                 'superbot-desk-hawk', 'superbot-desk-bull', 'hitv-backend'):
        proc = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True)
        if proc.returncode:
            print(json.dumps({'container': name, 'inspect_available': False}))
            continue
        c = json.loads(proc.stdout)[0]
        st = c.get('State', {})
        env = dict(v.split('=', 1) for v in c.get('Config', {}).get('Env', []) if '=' in v)
        allowed = ('DESK_MODE', 'DESK_PORTFOLIO', 'DESK_DATA_DIR', 'DESK_DATA_DIR_BULL')
        # Values are validated rather than echoing arbitrary environment content.
        modes = {k: env.get(k) if env.get(k) in ('paper', 'live', 'hawk', 'bull') else 'unset_or_other'
                 for k in ('DESK_MODE', 'DESK_PORTFOLIO')}
        dirs = {k: env.get(k) for k in allowed[2:]
                if env.get(k, '').startswith(('/opt/superbot', '/app/data/desk'))
                and '\n' not in env[k] and len(env[k]) < 200}
        print(json.dumps({'container': name, 'running': st.get('Running'),
            'health': st.get('Health', {}).get('Status'), 'restarts': c.get('RestartCount'),
            'restart_policy': c.get('HostConfig', {}).get('RestartPolicy', {}).get('Name'),
            'mode': modes, 'data_dirs': dirs,
            'mounts': [{'source': m.get('Source'), 'destination': m.get('Destination'),
                        'rw': m.get('RW')} for m in c.get('Mounts', [])
                       if 'superbot' in m.get('Source', '') or '/data/desk' in m.get('Destination', '')]}))
    for portfolio in ('hawk', 'bull'):
        root = pathlib.Path('/opt/superbot-desk-data') / portfolio
        hb = read_json(root / 'heartbeat.json') or {}
        state = read_json(root / 'state_v2.json') or {}
        try:
            age = round(time.time() - float(hb['ts']), 1)
        except (KeyError, TypeError, ValueError):
            age = None
        acc = state.get('main') or {}
        rows = []
        for filename in ('state_v2.json', 'heartbeat.json', 'trade_history.jsonl', 'learning_log.jsonl'):
            p = root / filename
            try:
                st = p.stat()
                rows.append({'name': filename, 'bytes': st.st_size, 'mtime': st.st_mtime})
            except OSError:
                rows.append({'name': filename, 'readable_metadata': False})
        pending = [n for n in ('pause.flag', 'reset.flag', 'budget_reset.flag',
                   'reset_portfolio.flag', 'close_all.flag', 'close_position.flag') if (root / n).exists()]
        print(json.dumps({'portfolio': portfolio, 'heartbeat_age_s': age,
            'exec_mode': hb.get('exec_mode') if hb.get('exec_mode') in ('paper', 'live') else None,
            'state_readable': bool(state), 'open_positions': len(acc.get('positions') or {}),
            'pending_known_flags': pending, 'files': rows}))
    # Process names only: arguments and environment may contain credentials.
    proc = subprocess.run(['ps', '-eo', 'comm='], capture_output=True, text=True)
    names = proc.stdout.splitlines()
    print(json.dumps({'process_names': {n: names.count(n) for n in sorted(set(names))
                      if any(x in n.lower() for x in ('python', 'uvicorn', 'cron', 'superbot'))}}))
    print('READ_ONLY_METADATA_AUDIT_COMPLETE')


if __name__ == '__main__':
    main()

# Additional checks use only the already authenticated host and read-only files.
def extended_audit():
    import hashlib
    for name in ('superbot-desk-hawk', 'superbot-desk-bull'):
        p = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True)
        if p.returncode:
            continue
        c = json.loads(p.stdout)[0]
        env = dict(v.split('=', 1) for v in c.get('Config', {}).get('Env', []) if '=' in v)
        print(json.dumps({'container': name, 'paper_mode_confirmed': env.get('DESK_MODE', '').strip().lower() == 'paper',
                         'live_mode_detected': env.get('DESK_MODE', '').strip().lower() == 'live'}))
        pid = c.get('State', {}).get('Pid', 0)
        for rel in ('app/backend/desk/cli.py', 'app/backend/desk/engine.py', 'app/desk/cli.py', 'app/desk/engine.py'):
            path = pathlib.Path('/proc') / str(pid) / 'root' / rel
            if path.is_file():
                print(json.dumps({'container': name, 'code_path': rel, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}))
    for portfolio in ('hawk', 'bull'):
        root = pathlib.Path('/opt/superbot-desk-data') / portfolio
        state = read_json(root / 'state_v2.json') or {}
        acc = state.get('main') or {}
        lim = acc.get('limits') or {}
        print(json.dumps({'portfolio': portfolio, 'state_day': acc.get('day'),
             'day_start_equity': acc.get('day_start_equity'), 'daily_stop_fraction': lim.get('daily_stop'),
             'halt_recorded': bool(state.get('halt')), 'run_no': state.get('run_no')}))
        for filename in ('trade_history.jsonl', 'learning_log.jsonl'):
            p = root / filename
            if not p.is_file():
                continue
            before = p.stat()
            lines = p.read_bytes().splitlines(keepends=True)
            invalid = 0
            objects = 0
            incomplete_tail = False
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    objects += isinstance(obj, dict)
                except (ValueError, UnicodeError):
                    if i == len(lines)-1 and not line.endswith(b'\n'):
                        incomplete_tail = True
                    else:
                        invalid += 1
            after = p.stat()
            print(json.dumps({'portfolio': portfolio, 'file': filename, 'lines': len(lines),
                 'json_objects': objects, 'invalid_complete_lines': invalid, 'incomplete_tail': incomplete_tail,
                 'stable_during_read': (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)}))
    # Existing trust records only. These are PUBLIC host keys, never private keys.
    # Do not connect to the old host or learn a new key from the network.
    for home in ('/home/ubuntu', '/root'):
        path = pathlib.Path(home) / '.ssh/known_hosts'
        if path.is_file():
            p = subprocess.run(['ssh-keygen', '-F', '51.91.109.45', '-f', str(path)], capture_output=True, text=True)
            entries = [line for line in p.stdout.splitlines() if line and not line.startswith('#')]
            print(json.dumps({'old_host_existing_trust_file': str(path), 'known_host_entries': entries}))


if __name__ == '__main__':
    extended_audit()
