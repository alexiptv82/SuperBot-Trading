"""Non-destructive topology audit; never import application modules or output secrets."""
import ast, hashlib, json, os, pathlib, re, subprocess, urllib.parse
P=pathlib.Path

def emit(v): print(json.dumps(v,ensure_ascii=True))
def inspect(name):
 p=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
 return json.loads(p.stdout)[0] if p.returncode==0 else None

for name in ('superbot','superbot-staging','superbot-pool','hitv-backend','superbot-desk','superbot-desk-hawk','superbot-desk-bull'):
 c=inspect(name)
 if not c: continue
 cfg=c.get('Config',{}); st=c.get('State',{}); pid=st.get('Pid',0)
 emit({'container':name,'running':st.get('Running'),'image_id':c.get('Image'),
       'working_dir':cfg.get('WorkingDir'),'ports':c.get('NetworkSettings',{}).get('Ports'),
       'restart':c.get('HostConfig',{}).get('RestartPolicy',{}).get('Name')})
 if not pid: continue
 root=P('/proc')/str(pid)/'root'
 if name=='superbot':
  for rel in ('app/backend/server.py','app/backend/desk_api.py','app/backend/desk_view.py','app/backend/auth.py','app/backend/config.py','app/backend/telegram_notifier.py','app/backend/bot_engine.py','app/backend/exchange.py','app/backend/requirements.txt'):
   p=root/rel
   if not p.is_file(): continue
   raw=p.read_bytes(); data={'container':name,'source':rel,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
   if rel.endswith('server.py'):
    tree=ast.parse(raw)
    data['route_count']=sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and any(isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr in ('get','post','put','delete') for d in n.decorator_list) for n in ast.walk(tree))
    data['startup_functions']=[n.name for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and any(isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr=='on_event' for d in n.decorator_list)]
    data['desk_router_factory_used']=b'desk_api.make_router' in raw
   emit(data)
  env=dict(x.split('=',1) for x in cfg.get('Env',[]) if '=' in x)
  emit({'backend_env_presence':{k:bool(env.get(k)) for k in ('TELEGRAM_BOT_TOKEN','DASHBOARD_PASSWORD_B64','DASHBOARD_PASSWORD','WEBAUTHN_RP_ID','WEBAUTHN_ORIGIN')},
        'backend_runtime_safe_modes':{k:env.get(k) if env.get(k) in ('paper','live','true','false') else 'unset_or_other' for k in ('TRADING_MODE','DESK_MODE','TELEGRAM_COMMANDS_ENABLED')}})
  ini=root/'app/backend/.env'
  if ini.is_file():
   # Only flags; do not echo .env values or raw parse errors.
   text=ini.read_text()
   get=lambda key: next((line.split('=',1)[1].strip().strip('\"\'') for line in text.splitlines() if line.strip().startswith(key+'=')),None)
   emit({'mounted_env_exists':True,'configured_trading_simulated':get('TRADING_MODE')=='paper',
         'webauthn_expected_domain':get('WEBAUTHN_RP_ID')=='superbot-trading.duckdns.org',
         'webauthn_expected_origin':get('WEBAUTHN_ORIGIN')=='https://superbot-trading.duckdns.org'})
  image=subprocess.run(['docker','image','inspect',c['Image']],capture_output=True,text=True)
  if not image.returncode:emit({'backend_image_bytes':json.loads(image.stdout)[0].get('Size')})
 if name=='hitv-backend':
  urls=[]
  for token in cfg.get('Healthcheck',{}).get('Test',[]):
   for s in re.findall(r'https?://[A-Za-z0-9.:/_-]+',token):
    u=urllib.parse.urlsplit(s)
    if u.hostname in ('localhost','127.0.0.1'): urls.append({'scheme':u.scheme,'port':u.port,'path':u.path})
  emit({'hitv_local_health_urls':urls})

# Restricted nginx directives only; never print config bodies or key contents.
for p in P('/etc/nginx/sites-enabled').glob('*'):
 if not p.is_file():continue
 text=p.read_text();servers=re.findall(r'(?m)^\s*server_name\s+([^;]+);',text)
 upstreams=[]
 for raw in re.findall(r'(?m)^\s*proxy_pass\s+([^;]+);',text):
  u=urllib.parse.urlsplit(raw)
  if u.scheme in ('http','https'):
   upstreams.append({'scheme':u.scheme,'host':u.hostname,'port':u.port})
 emit({'nginx_site':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'server_names':servers,'upstreams':upstreams})

# Classify command lines without exposing argument values.
for p in P('/proc').glob('[0-9]*/cmdline'):
 try:
  args=p.read_bytes().replace(b'\x00',b' ').decode(errors='replace')
  if re.search(r'(?:backend\.)?desk[./]cli(?:\.py)?',args) and not 'python3 - ' in args:
   cg=(p.parent/'cgroup').read_text()
   emit({'desk_engine_process_pid':int(p.parent.name),'docker_cgroup':('docker' in cg),'hawk_arg':bool(re.search(r'\bhawk\b',args)),'bull_arg':bool(re.search(r'\bbull\b',args))})
 except OSError:pass

for k in ('/opt/superbot','/opt/superbot-desk'):
 if not (P(k)/'.git').is_dir():continue
 proc=subprocess.run(['git','-c','safe.directory='+k,'-C',k,'rev-parse','HEAD'],capture_output=True,text=True)
 if not proc.returncode:emit({'checkout':k,'commit':proc.stdout.strip()})

emit({'available_ram_kb':next((line.split()[1] for line in P('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')),None),
      'disk_available_bytes':os.statvfs('/opt').f_bavail*os.statvfs('/opt').f_frsize})
