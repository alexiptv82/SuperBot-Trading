import json,pathlib,socket,subprocess
def run(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=15)
 return p.stdout.strip()
out={'host':socket.gethostname()}
for name in ['superbot','superbot-desk-api','superbot-api-tunnel-net']:
 raw=run(['docker','inspect',name])
 if raw:
  c=json.loads(raw)[0]
  out[name]={'running':c['State']['Running'],'status':c['State']['Status'],'restart_count':c['RestartCount'],
             'exit_code':c['State']['ExitCode'],'error':c['State']['Error'],
             'networks':{k:v.get('IPAddress') for k,v in c['NetworkSettings']['Networks'].items()}}
  if name=='superbot-api-tunnel-net' and c['State']['Running']:
   out['namespace_listeners']=run(['nsenter','--target',str(c['State']['Pid']),'--net','ss','-lnt'])
if out['host']=='vps-ed34e4ce':
 out['tunnel_service']=run(['systemctl','show','superbot-api-tunnel.service','-p','ActiveState','-p','SubState','-p','Result'])
 out['tunnel_journal']=run(['journalctl','-u','superbot-api-tunnel.service','-n','12','--no-pager','-o','cat'])
print(json.dumps(out))
