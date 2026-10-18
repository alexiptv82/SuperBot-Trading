import json,pathlib,socket,subprocess
def run(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=15)
 return p.stdout.strip()
out={'host':socket.gethostname()}
for name in ['superbot','superbot-desk-api','superbot-api-tunnel-net']:
 raw=run(['docker','inspect',name])
 rows=json.loads(raw) if raw else []
 if rows:
  c=rows[0]
  out[name]={'running':c['State']['Running'],'status':c['State']['Status'],'restart_count':c['RestartCount'],
             'exit_code':c['State']['ExitCode'],'error':c['State']['Error'],
             'networks':{k:v.get('IPAddress') for k,v in c['NetworkSettings']['Networks'].items()}}
  if name=='superbot-api-tunnel-net' and c['State']['Running']:
   out['namespace_listeners']=run(['nsenter','--target',str(c['State']['Pid']),'--net','ss','-lnt'])
if out['host']=='vps-ed34e4ce':
 out['tunnel_service']=run(['systemctl','show','superbot-api-tunnel.service','-p','ActiveState','-p','SubState','-p','Result'])
 out['tunnel_journal']=run(['journalctl','-u','superbot-api-tunnel.service','-n','12','--no-pager','-o','cat'])
 staging=json.loads(run(['docker','inspect','superbot-staging']) or '[]')
 if staging and staging[0]['State']['Running']:
  s=staging[0]
  env=dict(x.split('=',1) for x in s['Config'].get('Env',[]) if '=' in x)
  source=pathlib.Path('/proc')/str(s['State']['Pid'])/'root/app/backend/server.py'
  text=source.read_text() if source.is_file() else ''
  out['staging']={'poll_commands_referenced':'notifier.poll_commands()' in text,
    'environment_names':sorted(env),'telegram_token_override_present':bool(env.get('TELEGRAM_BOT_TOKEN')),
    'startup_excerpt':text[text.find("@app.on_event('startup')"):text.find("@app.on_event('startup')")+650]}
print(json.dumps(out))
