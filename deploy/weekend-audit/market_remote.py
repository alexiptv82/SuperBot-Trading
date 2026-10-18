"""Public GET market evidence only. No engine import or trading endpoints."""
import base64,concurrent.futures,datetime,hashlib,io,json,os,pathlib,secrets,sys,tarfile,time,urllib.parse,urllib.request
req=json.load(sys.stdin)
START=1792108800000  # 2026-10-16 00:00 UTC
END15=1792339200000 # 2026-10-18 16:00 UTC
END1=1792314000000  # 2026-10-18 09:00 UTC
SYMS='BTC ETH BNB XRP SOL ADA DOGE AVAX DOT LINK UNI ATOM LTC BCH APT ARB OP NEAR FIL INJ SUI TIA RUNE STX XAU XAG'.split()
MINUTE='BTC ETH BNB XRP SOL ADA DOGE AVAX LINK ATOM LTC BCH NEAR RUNE SUI XAU XAG'.split()
members={};meta={'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':'https://api.bitget.com/api/v2/mix/market/history-candles','requests':[],'coverage':{},'errors':{}}

def task(symbol,tf):
 rows={};pages=[];end=END1 if tf=='1m' else END15;step=60000 if tf=='1m' else 900000
 for page in range(25):
  params={'symbol':symbol+'USDT','productType':'USDT-FUTURES','granularity':tf,'limit':200,'endTime':end}
  url=meta['source']+'?'+urllib.parse.urlencode(params)
  for retry in range(3):
   try:
    r=urllib.request.Request(url,headers={'User-Agent':'SuperBot-ReadOnly-Audit/1.0'})
    with urllib.request.urlopen(r,timeout=15) as res:raw=res.read()
    obj=json.loads(raw)
    if obj.get('code')!='00000':raise RuntimeError('Public API returned code '+str(obj.get('code')))
    data=obj.get('data',[]);break
   except Exception:
    if retry==2:raise
    time.sleep(.5*(retry+1))
  pages.append((url,raw))
  if not data:break
  for row in data:
   ts=int(row[0])
   if START<=ts<(END1 if tf=='1m' else END15):rows[ts]=[float(v) for v in row[:7]]
  first=min(int(x[0]) for x in data)
  if first<=START:break
  if first>=end:raise RuntimeError('Historical pagination did not advance')
  # Bitget rounds endTime to the granularity boundary. Subtracting 1 ms skips a bar.
  end=first
  time.sleep(.2)
 values=[rows[k] for k in sorted(rows)]
 return symbol,tf,values,pages

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 tasks={pool.submit(task,s,tf):(s,tf) for tf,syms in [('15m',SYMS),('1m',MINUTE)] for s in syms}
 for future in concurrent.futures.as_completed(tasks):
  sym,tf=tasks[future]
  try:
   _,_,rows,pages=future.result()
   members['market/'+sym+'_'+tf+'.json']=json.dumps(rows,separators=(',',':')).encode()
   for i,(url,raw) in enumerate(pages):
    name='responses/'+sym+'_'+tf+'_'+str(i)+'.json';members[name]=raw
    meta['requests'].append({'url':url,'file':name,'sha256':hashlib.sha256(raw).hexdigest()})
   meta['coverage'][sym+'_'+tf]={'rows':len(rows),'first':rows[0][0] if rows else None,'last':rows[-1][0] if rows else None,
      'gaps':sum(1 for a,b in zip(rows,rows[1:]) if b[0]-a[0]!=(60000 if tf=='1m' else 900000))}
  except Exception as e:meta['errors'][sym+'_'+tf]=str(e)

members['metadata.json']=json.dumps(meta,indent=2).encode()
manifest={k:{'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for k,v in members.items()}
members['manifest.json']=json.dumps(manifest,indent=2).encode()
buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w:gz') as tf:
 for name,data in sorted(members.items()):
  info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o600;tf.addfile(info,io.BytesIO(data))
data=buf.getvalue();root=pathlib.Path('/root/superbot-weekend-market-evidence')
root.mkdir(mode=0o700,exist_ok=True)
target=root/('market-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(3)+'.tar.gz')
with target.open('xb') as f:f.write(data)
target.chmod(0o600)
print(json.dumps({'tar_b64':base64.b64encode(data).decode(),'sha256':hashlib.sha256(data).hexdigest(),
 'bytes':len(data),'host':'market-bitget','evidence_path':str(target),'restore_verified':False,
 'coverage_count':len(meta['coverage']),'error_count':len(meta['errors'])}))
