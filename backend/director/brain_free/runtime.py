"""One financial writer; independent public feed, model and Telegram workers."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import argparse,hashlib,json,os,time,uuid
from pathlib import Path
from .config import Config
from .execution import apply,protect,fingerprint,fresh
from .store import Store,dumps
from .memory import seeds,recent
from .prompt_builder import build
from .provider import call,validate
from .spend import price,view
from .notifications import Dispatcher,event_text
from .reports import schedule

class Runtime:
    def __init__(self,root,initialize=False,cfg=Config(),model_call=call,api_key=None,seed_dir=None):
        if os.getenv('DESK_MODE','paper')!='paper':raise ValueError('paper_only')
        self.cfg=cfg;self.seeds=seeds(seed_dir or Path(__file__).parent/'seeds')
        from .mandate import SYSTEM
        self.digest=cfg.digest(SYSTEM+dumps(self.seeds))
        self.store=Store(root,initialize,self.digest);self.key=api_key if api_key is not None else os.getenv('DEEPSEEK_API_KEY','')
        build_sha=os.getenv('BRAIN_FREE_CODE_SHA','unreleased-offline')
        stored=self.store.load()
        if initialize:
            stored['build_sha']=build_sha;self.store.commit(stored)
        elif stored.get('build_sha')!=build_sha:
            self.store.close();raise ValueError('explicit_bug_upgrade_required')
        self.pool=ThreadPoolExecutor(1,thread_name_prefix='brain-free-model')
        self.model_call=model_call;self.pending=None;self.retry_at=0;self.failures=0
    def close(self):
        self.pool.shutdown(wait=False,cancel_futures=True);self.store.close()
    def activate(self,now,markets):
        state=self.store.load()
        if state['verified_start_ms'] is not None:return
        if not self.key or not any(fresh(m.get('quote'),now,self.cfg) for m in markets.values()):raise ValueError('verification_requires_key_and_fresh_quotes')
        state['verified_start_ms']=now
        self.store.commit(state,[('experiment-start','experiment_started',now,{'config_hash':self.digest,'start_ms':now})],
             [('experiment-start',f'[BRAIN] Avvio verificato: PAPER {self.cfg.start_cash:.0f}$, {self.cfg.max_slots} slot, margine massimo {self.cfg.max_margin:.0f}$. Inizio test 168 ore.')])
    def record_events(self,state,events,now,prefix):
        rows=[];messages=[]
        for i,e in enumerate(events):
            ident=prefix+':'+str(i)
            rows.append((ident,e['kind'],now,e));messages.append((ident,event_text(e)))
        self.store.commit(state,rows,messages)
    def receive(self,markets,contracts,now):
        if not self.pending or not self.pending['future'].done():return
        job=self.pending;self.pending=None
        try:result=job['future'].result()
        except Exception:result={'error':'provider_failed','usage':None}
        body={'model':result.get('model',self.cfg.model),'billing':None,'error':result.get('error')}
        try:
            if result.get('usage') is not None:body['billing']=price(result['usage'],job['ts'])
        except (ValueError,TypeError,KeyError):body['usage_status']='unreadable_unknown_cost'
        if result.get('error')=='missing_key':body['billing']={'cost':0.,'status':'not_sent'}
        self.store.finish_request(job['id'],'complete' if body['billing'] else 'unknown_cost',body)
        state=self.store.load();error=result.get('error')
        try:
            if error:raise ValueError(error)
            if result.get('finish_reason')!='stop':raise ValueError('incomplete_response')
            data=validate(result['content'].replace(self.key,'[redacted]') if self.key else result['content'],self.cfg.symbols)
            if fingerprint(state)!=job['fingerprint']:raise ValueError('account_changed_during_request')
            if now-job['ts']>self.cfg.timeout_s*1000+30000:raise ValueError('expired_response')
            state['last_decision']={'ts_ms':now,'summary':str(data.get('summary',''))[:4000],
                                    'assessments':data.get('assessments',[]),'decisions':data['decisions'],
                'unassessed_symbols':sorted(set(self.cfg.symbols)-{a['symbol'] for a in data.get('assessments',[])})}
            # Commit the explicit reason BEFORE any corresponding PAPER trade.
            self.store.commit(state,[(job['id']+':thesis','ai_decision',now,state['last_decision'])])
            quotes={s:m['quote'] for s,m in markets.items() if m.get('quote')}
            for i,decision in enumerate(data['decisions']):
                state=self.store.load()
                try:
                    if decision['action'] in ('open_long','open_short','dca'):
                        bars=markets.get(decision['symbol'],{}).get('bars',{}).get('1m',[])
                        closed=[b for b in bars if b[0]+60000<=now]
                        if not closed or not 0<=now-(closed[-1][0]+60000)<=self.cfg.bar_age_ms:raise ValueError('stale_closed_bars')
                    decision=dict(decision,reason='AI: '+decision['reason'])
                    updated,events=apply(state,decision,quotes,contracts,now,self.cfg)
                    self.record_events(updated,events,now,job['id']+':execution:'+str(i))
                except (ValueError,KeyError,TypeError) as exc:
                    code=str(exc) if isinstance(exc,ValueError) else 'invalid_execution_fields'
                    self.store.commit(state,[(job['id']+':reject:'+str(i),'execution_rejected',now,
                        {'symbol':decision['symbol'],'code':code,'requested':decision})])
            self.failures=0
            state=self.store.load();state['provider_status']='ai_decision_received'
            self.store.commit(state)
        except (ValueError,TypeError,KeyError) as exc:
            self.failures+=1;self.retry_at=now+min(300000,30000*2**min(self.failures-1,4))
            state=self.store.load();state['last_full_ms']=0;state['last_manage_ms']=0
            state['provider_status']=str(exc) if isinstance(exc,ValueError) else 'invalid_response'
            self.store.commit(state,[(job['id']+':failed','ai_unavailable',now,{'code':state['provider_status']})],
                [('ai-error:'+state['provider_status']+':'+str(now//3600000),'[BRAIN] AI non disponibile: '+state['provider_status']+'. Stop locali attivi, nessun fallback alle regole.')])
    def step(self,markets,contracts,context,now):
        try:json.dumps(context,allow_nan=False)
        except (ValueError,TypeError):context={'status':'unavailable_invalid_context','binding':False}
        state=self.store.load()
        if now<state['last_ms']:raise ValueError('backward_clock')
        dt=min(now-state['last_ms'],60000) if state['verified_start_ms'] is not None else 0;state['last_ms']=now
        state['metrics']['observed_ms']+=dt
        if state['verified_start_ms'] is not None:
            state['metrics']['unobserved_ms']=state['metrics'].get('unobserved_ms',0)+max(0,now-state.get('last_observed_ms',now)-60000)
        state['last_observed_ms']=now
        state['metrics']['slot_ms']+=dt*len(state['positions'])
        if not state['positions']:state['metrics']['empty_ms']+=dt
        was_paused=state['paused'];state['paused']=(self.store.root/'pause.flag').exists()
        control_events=[];control_messages=[]
        if was_paused!=state['paused']:
            ident='pause:'+str(now);control_events.append((ident,'operator_pause',now,{'paused':state['paused']}))
            control_messages.append((ident,'[BRAIN] '+('Nuove esposizioni in pausa; stop locali attivi.' if state['paused'] else 'Nuove esposizioni riabilitate.')))
        stale=sorted(sym for sym,p in state['positions'].items() if not fresh(markets.get(sym,{}).get('quote'),now,self.cfg))
        if stale!=state.get('stale_positions',[]):
            ident='feed:'+str(now);control_events.append((ident,'feed_status',now,{'stale_positions':stale}))
            control_messages.append((ident,'[BRAIN] '+('Dati prezzo non aggiornati: '+', '.join(stale) if stale else 'Feed posizioni nuovamente aggiornato.')))
        state['stale_positions']=stale
        self.store.commit(state,control_events,control_messages)
        state['last_prices']={s:m['quote'] for s,m in markets.items() if m.get('quote')}
        state['context']=context
        updated,events=protect(state,markets,contracts,now,self.cfg)
        updated['cycles']+=1;updated['heartbeat_ms']=now
        updated['runtime_capacity']={'max_slots':self.cfg.max_slots,'max_margin':self.cfg.max_margin}
        updated['instrument_count']=len(contracts)
        updated['fresh_quote_count']=sum(fresh(m.get('quote'),now,self.cfg) for m in markets.values())
        self.record_events(updated,events,now,'protection:'+str(now))
        self.receive(markets,contracts,now)
        state=self.store.load()
        if now-state.get('last_comparison_ms',0)>=900000:
            from .reports import classical_comparison
            state['classic_comparison']=classical_comparison(os.getenv('BRAIN_CLASSICS_RO','/classics'),now)
            state['last_comparison_ms']=now
        events,messages=schedule(self.store,state,now,self.cfg)
        self.store.commit(state,events,messages)
        state=self.store.load()
        full=now-state['last_full_ms']>=self.cfg.analysis_ms
        manage=bool(state['positions']) and now-state['last_manage_ms']>=self.cfg.management_ms
        if not self.pending and not state['paused'] and state['verified_start_ms'] is not None and now>=self.retry_at and (full or manage):
            kind='full' if full else 'management';ident=str(uuid.uuid4())
            system,user=build(state,markets,contracts,context,recent(self.store),self.seeds,kind,now,self.cfg)
            self.store.record_request(ident,now,{'kind':kind,'prompt_hash':hashlib.sha256((system+user).encode()).hexdigest()})
            self.store.commit(state,[(ident+':input','ai_input',now,{'kind':kind,'system':system,'user':json.loads(user)})])
            self.pending={'id':ident,'ts':now,'fingerprint':fingerprint(state),'kind':kind,
                         'future':self.pool.submit(self.model_call,self.key,system,user,self.cfg)}
            state['last_full_ms' if full else 'last_manage_ms']=now
            state['provider_status']='model_pending';self.store.commit(state)
        return self.store.load()

def main():
    ap=argparse.ArgumentParser(description='Isolated AI-only PAPER Brain; no account is created implicitly.')
    ap.add_argument('--root',default='/out');ap.add_argument('--initialize',action='store_true')
    ap.add_argument('--healthcheck',action='store_true');ap.add_argument('--activate',action='store_true')
    args=ap.parse_args();os.umask(0o077)
    if args.healthcheck:
        import sqlite3
        path=Path(args.root)/'brain.sqlite3'
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
            state=json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
        if state['mode']!='paper' or not 0<=time.time()*1000-state.get('heartbeat_ms',0)<60000:raise SystemExit(1)
        return
    if args.initialize:
        runtime=Runtime(args.root,True);runtime.close();return
    from .feeds import Feeds
    runtime=Runtime(args.root);feeds=Feeds();dispatcher=Dispatcher(runtime.store.root,os.getenv('TELEGRAM_BOT_TOKEN',''),os.getenv('TELEGRAM_CHAT_ID',''))
    try:
        while True:
            now=int(time.time()*1000)
            markets,constraints,context=feeds.poll(runtime.store.load()['positions'],now)
            activation=runtime.store.root/'activate.flag'
            requested=args.activate or activation.exists() and activation.read_text().strip()==runtime.digest
            if requested and constraints and runtime.store.load()['verified_start_ms'] is None:
                try:runtime.activate(now,markets)
                except ValueError:pass
            runtime.step(markets,constraints,context,now);dispatcher.poll(now)
            time.sleep(runtime.cfg.poll_s)
    finally:dispatcher.close();feeds.close();runtime.close()

if __name__=='__main__':main()
