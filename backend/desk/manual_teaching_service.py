"""Owner-only classical PAPER teaching; recover solely from saved close receipts."""
import json
import os
from numbers import Real
from pathlib import Path
from director.manual_teaching import ManualLessons,batches,normalize_closed,parse_review_command
from director.scoped_confirmations import ScopedConfirmations

def queue_close(state,record,portfolio):
    if record.get('closed_by')!='utente' or record.get('why')!='chiusura manuale' or record.get('partial') is True:
        return
    from desk.manual_teaching_bridge import to_attested_close
    event=to_attested_close(record,portfolio,int(state.get('run_no',1)),persisted=True,remaining={})
    for key in ('entry','close_price','leverage','margin','pnl_usd'):
        if isinstance(event[key],Real) and not isinstance(event[key],bool):event[key]=float(event[key])
    normalized=normalize_closed(event,verified=True)
    rows=state.setdefault('manual_teaching_outbox',[])
    if not any(row.get('event_id')==normalized['event_id'] for row in rows):
        rows.append({'event_id':normalized['event_id'],'close':event})

def preferences(root,portfolio,account,now):
    store=ManualLessons(root)
    pending={};confirmed={}
    for row in store._rows(store.journal):
        if row.get('event')=='pending':pending[row['event_id']]=row['data']
        elif row.get('event')=='resolved':
            confirmed[row['event_id']]=(row.get('choice'),row.get('at_ms'))
    found=[]
    for eid,(choice,at) in confirmed.items():
        data=pending.get(eid,{})
        if (choice!='yes' or type(at)!=int or not 0<at<=now or
            data.get('bot')!=portfolio or data.get('account_id')!=account or
            data.get('pnl_usd',0)<=0 or not 0<data.get('close_ms',0)<=at):
            continue
        found.append({'event_id':eid,'symbol':data['symbol'],'side':data['side'],
            'net_usd':data['pnl_usd'],'margin':data['margin'],'duration_min':data['duration_min'],
            'closed_ms':data['close_ms'],'confirmed_ms':at,'account_id':account,
            'scope':'operator_observation_only','training_applied':False})
    return sorted(found,key=lambda x:(x['confirmed_ms'],x['event_id']))[-5:]

def _publish(path,data):
    path=Path(path)
    if path.is_symlink() or path.parent.is_symlink():raise ValueError('unsafe_reviews_path')
    temp=path.with_name(path.name+'.tmp')
    if temp.is_symlink():raise ValueError('unsafe_reviews_path')
    with temp.open('w',encoding='utf-8') as f:
        json.dump(data,f,allow_nan=False)
        f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

def poll(root,portfolio,state_path,current,now,*,inbox_path=None):
    if portfolio not in ('hawk','bull'):raise ValueError('unknown_portfolio')
    # Never recover from a close that exists only in memory or from history
    # appended before a failed wallet save.
    disk=json.loads(Path(state_path).read_text(encoding='utf-8'))
    run=disk.get('run_no',1)
    if type(run)!=int or run<=0:raise ValueError('invalid_run')
    account=f'desk-{portfolio}-paper-run-{run}'
    remaining=(disk.get('main') or {}).get('positions')
    if not isinstance(remaining,dict):raise ValueError('missing_saved_wallet')
    store=ManualLessons(root);delivered=set()
    for row in disk.get('manual_teaching_outbox',[])[:50]:
        event=row.get('close',{})
        clean=normalize_closed(event,verified=True)
        if clean['event_id']!=row.get('event_id') or clean['bot']!=portfolio:
            raise ValueError('invalid_saved_receipt')
        if clean['close_ms']>now:continue
        active=remaining.get(clean['symbol'])
        if active is not None and str(active.get('id'))==clean['position_id']:
            continue
        store.register(event,verified=True)
        delivered.add(clean['event_id'])
    # Acknowledgement is only in memory; normal wallet saves persist it later.
    # A crash before that save just replays idempotent registration.
    current['manual_teaching_outbox']=[r for r in current.get('manual_teaching_outbox',[])
                                       if r.get('event_id') not in delivered]
    store.expire(now)
    queue=ScopedConfirmations(inbox_path or Path(root)/'manual.confirmations.sqlite3')
    def confirm(text,at):
        matching=[e for e in store.pending() if e['account_id']==account]
        choice,ids=parse_review_command(text,matching)
        return store.decide(ids,choice,at)
    try:outcomes=queue.consume(account,confirm,now)
    finally:queue.close()
    pending=[e for e in store.pending() if e['account_id']==account and e['close_ms']<=now]
    groups=batches(pending)
    published=[{'group_id':g['group_id'],'count':len(g['items']),
                'net_usd':round(sum(e['pnl_usd'] for e in g['items']),4),
                'symbols':[e['symbol'] for e in g['items']],
                'expires_ms':min(e['close_ms'] for e in g['items'])+7200000}
               for g in groups][-10:]
    result={'paper':True,'account_id':account,'ts_ms':now,'groups':published}
    _publish(Path(root)/'manual_operator_reviews.json',result)
    return {'status':'ready','confirmations':outcomes,
            'preferences':preferences(root,portfolio,account,now)}

