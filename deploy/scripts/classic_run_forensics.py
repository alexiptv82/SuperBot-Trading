"""Read-only, PAPER-only forensic export. No imports of the trading runtime.
Only fixed, allowlisted fields leave the server; raw prompts/keys/text never do.
Protected source files opened O_RDONLY/O_NOFOLLOW; running bot may append.
"""
import base64,collections,gzip,hashlib,json,math,os,re,subprocess,time
from pathlib import Path
ROOT=Path('/opt/superbot-desk-data')
NUMS=('id','run_no','ts','logged_ms','open_ms','close_ms','side','entry','exit','qty','margin','leverage','net','gross','fees','funding','confidence','dca_count','risk_plan_usd','net_r','mfe_r','mae_r','hold_ms','fraction','code_version')
FEATURES=('sig_side','sig_score','sig_long','sig_short','atr_pct','sig_sl_pct','sig_tp_pct','rsi1h','roc24h','vol_ratio','ema20_50_1h','ema50_200_4h','daily_trend','price','funding_rate','btc_roc24h','btc_score','btc_side','hour_utc','dow','conf','dec_lev','dec_margin','dec_sl_pct','dec_tp_pct','dec_rr','bars_4h','slow_4h_period','proposed_margin','proposed_lev')
LIMITS=('start_equity','max_margin_trade','max_margin_total','max_open','max_dca','kill_equity','daily_stop','fee_bp_side','slip_bp_side','funding_bp_8h_long')
PARAMS=('portfolio','code_version','entry_score_base','entry_score_tier_ab','entry_score_tier_c','daily_cap_usd','max_open','daily_loss_pct')

def finite(v):return type(v) in (int,float) and math.isfinite(v)
def version(v):return v if isinstance(v,str) and re.fullmatch('[a-f0-9]{7,40}',v) else None

def command(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=45)
 if p.returncode:raise ValueError('READONLY_COMMAND_FAILED')
 return p.stdout

def stat(path):
 s=path.stat();return {'size':s.st_size,'mtime_ns':s.st_mtime_ns}

def read(path):
 if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('SYMLINK_SOURCE')
 before=stat(path)
 if before['size']>300*1024*1024:raise ValueError('SOURCE_TOO_LARGE')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:raw=f.read(before['size'])
 return raw,{'path':str(path.relative_to(ROOT)),'before':before,'after':stat(path),'snapshot_sha256':hashlib.sha256(raw).hexdigest(),'read_bytes':len(raw)}

def exit_kind(value):
 text=str(value or '').lower()
 if 'liquid' in text:return 'liquidation'
 if 'trailing' in text or 'traino' in text:return 'trailing'
 if 'manual' in text or 'richiesta' in text or 'utente' in text or 'chiudi tutto' in text:return 'manual'
 if 'timeout' in text or 'scadenz' in text:return 'timeout'
 if 'take profit' in text or text in ('tp','tp1','tp2') or text.startswith('tp '):return 'TP'
 if 'stop' in text or text=='sl':return 'SL'
 if 'claude' in text:return 'model_or_rule_close_labeled_claude'
 if 'segnale' in text:return 'signal_close'
 if 'reset' in text:return 'reset'
 return 'other'

def record(r):
 if r.get('mode')=='live' or r.get('exec_mode')=='live' or r.get('live') or r.get('live_executed') or r.get('live_order_id') not in (None,'','paper'):
  raise ValueError('LIVE_RECORD_REFUSED')
 out={k:r[k] for k in NUMS if k in r and finite(r[k])}
 if version(r.get('code_version')):out['code_version']=version(r['code_version'])
 if isinstance(r.get('symbol'),str) and re.fullmatch('[A-Z0-9]{1,20}',r['symbol']):out['symbol']=r['symbol']
 if r.get('ev') in ('open','close','candidate','split_fill','split_cancel'):out['ev']=r['ev']
 if r.get('source') in ('rules','claude','fallback','brain','manual'):out['source']=r['source']
 if r.get('trade_type') in ('scalp','medio'):out['trade_type']=r['trade_type']
 if isinstance(r.get('partial'),bool):out['partial']=r['partial']
 if 'why' in r:out['exit_kind']=exit_kind(r['why'])
 f=r.get('features') or {};out['features']={k:f[k] for k in FEATURES if k in f and finite(f[k])}
 if f.get('tier') in ('A','B','C','TIER_A','TIER_B','TIER_C'):out['features']['tier']=f['tier']
 components={}
 for why in f.get('why',[]) if isinstance(f.get('why'),list) else []:
  match=re.search(r'\(\+([0-9]+)\)',str(why));label=next((k for k in ('trend 4h','trend 1h','trend 1d','prezzo vs EMA50','momento 24h','rottura massimi','rottura minimi','RSI','volumi','hammer','bullish engulfing','shooting star','bearish engulfing','stagionalit','rimbalzo RSI') if str(why).startswith(k)),None)
  if match and label:components[label]=int(match[1])
 if components:out['components']=components
 return out

def params(r):
 out={k:r[k] for k in PARAMS if k in r and finite(r[k])}
 if version(r.get('code_version')):out['code_version']=version(r['code_version'])
 if r.get('portfolio') in ('hawk','bull'):out['portfolio']=r['portfolio']
 for section in ('limits','guardrail','split'):
  if isinstance(r.get(section),dict):out[section]={k:v for k,v in r[section].items() if finite(v) or isinstance(v,bool)}
 return out

def main():
 result={'captured_ms':int(time.time()*1000),'mode':'paper','source_read_only':True,'bots':{},'deploy_manifests':[],'protected_files':[]}
 for bot in ('hawk','bull'):
  d=json.loads(command(['docker','inspect','superbot-desk-'+bot]))[0]
  env=dict(v.split('=',1) for v in d['Config'].get('Env',[]) if '=' in v)
  if env.get('DESK_MODE')!='paper':raise ValueError('PAPER_RUNTIME_REQUIRED')
  data={'runtime':{'sha':d['Config'].get('Labels',{}).get('superbot.sha'),'started_at':d['State']['StartedAt'],'running':d['State']['Running']},'summaries':[],'states':[],'history':[],'opens':[],'closes':[],'candidates':[],'version_ranges':[],'files':[],'parse_errors':[],'schema_keys':{}}
  root=ROOT/bot;paths=[p for p in root.rglob('*') if p.is_file() and p.name in ('trade_history.jsonl','learning_log.jsonl','state_v2.json','summary.json') and (p.parent==root or 'archive' in p.relative_to(root).parts)]
  versions={};candidates=collections.Counter()
  for path in sorted(paths):
   raw,manifest=read(path);data['files'].append(manifest)
   if path.suffix=='.jsonl':
    malformed=0
    for line in raw.splitlines(keepends=True):
     if not line.endswith(b'\n'):malformed+=1;continue
     try:r=json.loads(line)
     except ValueError:malformed+=1;continue
     if not isinstance(r,dict):malformed+=1;continue
     ev=r.get('ev');clean=record(r);clean['file']=manifest['path']
     if path.name=='trade_history.jsonl':data['history'].append(clean)
     elif ev in ('open','close'):
      data['opens' if ev=='open' else 'closes'].append(clean)
     if ev and ev not in data['schema_keys']:data['schema_keys'][ev]={'fields':sorted(r.keys()),'features':sorted((r.get('features') or {}).keys())}
     code=version(r.get('code_version'));stamp=r.get('ts') or r.get('logged_ms') or r.get('close_ms')
     if code and finite(stamp):
      key=(r.get('run_no'),code);v=versions.setdefault(key,{'run_no':r.get('run_no'),'code_version':code,'first_ms':stamp,'last_ms':stamp,'events':0,'opens':0,'closes':0});v['first_ms']=min(v['first_ms'],stamp);v['last_ms']=max(v['last_ms'],stamp);v['events']+=1;v['opens']+=ev=='open';v['closes']+=ev=='close'
     if ev=='candidate':
      status=str(r.get('status') or 'unknown')
      allowed=('conf_bassa','conf_bassa_macro','rr_basso','macro_blocco','cooldown','troppe posizioni aperte','margine sotto minimo','rischio_aperto_bull','veto_short_rimbalzo_btc','stop troppo lontano','stop giornaliero','aperta','rifiutata')
      status=next((x for x in allowed if x in status),'other')
      candidates[(r.get('run_no'),code,r.get('source') if r.get('source') in ('rules','claude') else 'unknown',status)]+=1
    if malformed:data['parse_errors'].append({'file':manifest['path'],'malformed_or_torn_lines':malformed})
   else:
    try:r=json.loads(raw)
    except ValueError:data['parse_errors'].append({'file':manifest['path'],'invalid_json':True});continue
    if path.name=='summary.json':
     summary={k:r[k] for k in ('run_no','started_ms','ended_ms','start_equity','end_equity','pnl','trades','wins','losses','win_rate','net_total','fees_total') if k in r and finite(r[k])};summary['params']=params(r.get('params') or {});summary['file']=manifest['path'];data['summaries'].append(summary)
    else:
     main=r.get('main') or {};state={k:r[k] for k in ('run_no','run_started_ms','live_since_ms') if k in r and finite(r[k])};state['file']=manifest['path'];state['limits']={k:v for k,v in (main.get('limits') or {}).items() if k in LIMITS and finite(v)};state['closed']=[record(x) for x in main.get('closed',[])];state['positions']=[record(x) for x in (main.get('positions') or {}).values()];data['states'].append(state)
  data['version_ranges']=list(versions.values());data['candidates']=[{'run_no':k[0],'code_version':k[1],'source':k[2],'status':k[3],'n':n} for k,n in candidates.items()]
  for name in ('trade_history.jsonl','learning_log.jsonl','lessons.md','errors.md'):
   p=root/name
   if p.is_file():
    _,f=read(p);result['protected_files'].append(f)
  result['bots'][bot]=data
 # Only timestamp/SHA/mode fields from deployment manifests; never arbitrary values.
 for path in sorted(Path('/opt/superbot-deploys').glob('bot-*.json')):
  try:r=json.loads(path.read_bytes())
  except (OSError,ValueError):continue
  fields=[]
  def walk(x):
   if isinstance(x,dict):
    for k,v in x.items():
     if k in ('sha','approved_sha','code_version','runtime_sha','target_sha') and version(v):fields.append({'key':k,'value':v})
     elif k in ('started_at','finished_at','ts','timestamp','completed_at','deployed_at','created_at','ts_ms') and ((finite(v)) or isinstance(v,str) and re.fullmatch('[0-9T:.+Z-]{10,40}',v)):fields.append({'key':k,'value':v})
     elif k in ('mode','desk_mode') and v in ('paper','live'):fields.append({'key':k,'value':v})
     if isinstance(v,(dict,list)):walk(v)
   elif isinstance(x,list):
    for v in x:walk(v)
  walk(r);result['deploy_manifests'].append({'file':path.name,'fields':fields})
 payload=json.dumps(result,allow_nan=False,separators=(',',':')).encode();encoded=base64.b64encode(gzip.compress(payload)).decode()
 print('AUDIT_META='+json.dumps({'mode':'paper','read_only':True,'payload_bytes':len(payload),'gzip_base64_bytes':len(encoded),'sha256':hashlib.sha256(payload).hexdigest(),'counts':{p:{k:len(d[k]) for k in ('history','opens','closes','summaries','version_ranges')} for p,d in result['bots'].items()}}))
 for i in range(0,len(encoded),12000):print('AUDIT_CHUNK='+encoded[i:i+12000])
 print('AUDIT_EXPORT=PASS')

if __name__=='__main__':
 try:main()
 except Exception as exc:print('AUDIT_FAILED='+type(exc).__name__);raise SystemExit(1)
