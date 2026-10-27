"""DeepSeek transport. Never exposes keys/errors or creates a fallback trade."""
import json,urllib.request,urllib.error
from .config import Config,number

ACTIONS={'open_long','open_short','close','partial_close','dca','move_stop','move_target','hold'}
def validate(text,symbols):
    d=json.loads(text,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite_json')))
    if not isinstance(d,dict) or not isinstance(d.get('decisions'),list) or len(d['decisions'])>3*len(symbols):raise ValueError('invalid_schema')
    if not isinstance(d.get('summary',''),str) or len(d.get('summary',''))>4000:raise ValueError('invalid_summary')
    assessments=d.get('assessments',[])
    if not isinstance(assessments,list) or len(assessments)>len(symbols):raise ValueError('invalid_assessments')
    assessment_symbols=set()
    for item in assessments:
        if not isinstance(item,dict) or item.get('symbol') not in symbols or item['symbol'] in assessment_symbols:raise ValueError('invalid_assessment_symbol')
        assessment_symbols.add(item['symbol'])
        for key in ('long_case','short_case','decision'):
            if not isinstance(item.get(key),str) or len(item[key])>2000:raise ValueError('invalid_assessment')
    seen=set()
    for row in d['decisions']:
        if not isinstance(row,dict) or row.get('symbol') not in symbols or (row['symbol'],row.get('action')) in seen or row.get('action') not in ACTIONS:raise ValueError('invalid_decision')
        seen.add((row['symbol'],row['action']))
        if not isinstance(row.get('reason'),str) or not 1<=len(row['reason'].strip())<=4000:raise ValueError('missing_reason')
        if row['action'] in ('open_long','open_short','dca'):
            for key in ('margin','leverage'):number(row.get(key),1e-12)
            if not isinstance(row.get('invalidation'),str) or not row['invalidation'].strip():raise ValueError('missing_invalidation')
            if row['action']!='dca':number(row.get('stop'),1e-12)
        for key in ('stop','target','margin','leverage','fraction'):
            if key in row and row[key] is not None:number(row[key],1e-12)
    allowed={'symbol','action','margin','leverage','stop','target','reason','invalidation','fraction'}
    return {'summary':d.get('summary',''),'assessments':[{k:a[k] for k in ('symbol','long_case','short_case','decision')} for a in assessments],
            'decisions':[{k:v for k,v in row.items() if k in allowed} for row in d['decisions']]}

def call(api_key,system,user,cfg=Config(),opener=urllib.request.urlopen):
    if not api_key:return {'error':'missing_key','usage':None}
    body={'model':cfg.model,'messages':[{'role':'system','content':system},{'role':'user','content':user}],
          'thinking':{'type':'enabled'},'reasoning_effort':cfg.thinking,
          'max_tokens':cfg.max_tokens,'response_format':{'type':'json_object'},'stream':False}
    request=urllib.request.Request('https://api.deepseek.com/chat/completions',data=json.dumps(body).encode(),
              headers={'Authorization':'Bearer '+api_key,'Content-Type':'application/json'},method='POST')
    try:
        with opener(request,timeout=cfg.timeout_s) as r:
            payload=json.loads(r.read(2_000_001))
        choice=payload['choices'][0]
        return {'content':choice['message'].get('content',''),'usage':payload.get('usage'),
                'model':str(payload.get('model',cfg.model))[:100],'finish_reason':choice.get('finish_reason')}
    except urllib.error.HTTPError as e:return {'error':{401:'auth',402:'balance',403:'auth',429:'rate'}.get(e.code,'provider_http'),'usage':None}
    except Exception:return {'error':'provider_network_or_format','usage':None}
