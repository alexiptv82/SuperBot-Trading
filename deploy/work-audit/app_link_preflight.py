import json
import pathlib
import socket
import subprocess

def run(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)

host = socket.gethostname()
names = ['superbot'] if host == 'vps-ed34e4ce' else ['superbot-desk-hawk', 'superbot-desk-bull']
out = {'host': host, 'containers': []}
for name in names:
    c = json.loads(run(['docker', 'inspect', name]))[0]
    env = dict(x.split('=', 1) for x in c['Config']['Env'] if '=' in x)
    info = {'name': name, 'image': c['Image'], 'running': c['State']['Running'],
            'network_mode': c['HostConfig']['NetworkMode'],
            'networks': {n: {k: x.get(k) for k in ['Gateway', 'IPAddress', 'NetworkID']} for n, x in c['NetworkSettings']['Networks'].items()},
            'restart': c['HostConfig']['RestartPolicy'], 'ports': c['HostConfig']['PortBindings'],
            'mode': {k: env.get(k) for k in ['DESK_MODE', 'TRADING_MODE']}}
    if host != 'vps-ed34e4ce':
        info['python_packages'] = json.loads(run(['docker', 'exec', name, 'python', '-c',
            'import importlib.util,json;print(json.dumps({x:bool(importlib.util.find_spec(x)) for x in ["fastapi","httpx","starlette","uvicorn","ccxt"]}))']))
    out['containers'].append(info)
if host == 'vps-ed34e4ce':
    for p in [18002]:
        s=socket.socket()
        try:
            s.bind(('127.0.0.1',p)); free=True
        except OSError: free=False
        finally: s.close()
        out['loopback_port_free']=free
else:
    lines=run(['/usr/sbin/sshd','-T']).splitlines()
    out['sshd_forwarding']=[x for x in lines if x.startswith(('allowtcpforwarding ', 'disableforwarding ', 'gatewayports ', 'permitopen '))]
print(json.dumps(out))
