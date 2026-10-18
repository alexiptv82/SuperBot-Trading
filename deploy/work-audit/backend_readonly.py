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
