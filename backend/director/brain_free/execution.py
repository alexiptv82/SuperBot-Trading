"""Pure isolated-margin PAPER accounting. No strategy, score or API gates."""
from copy import deepcopy
from decimal import Decimal, ROUND_DOWN
import hashlib,json,math,uuid
from .config import Config,number,max_leverage


def initial(now,digest):
    return {'mode':'paper','account_id':'brain-free-paper','experiment_id':str(uuid.uuid4()),
            'config_hash':digest,'created_ms':now,'verified_start_ms':None,'cash':2000.,
            'positions':{},'next_id':1,'cycles':0,'last_ms':now,'last_full_ms':0,
            'last_manage_ms':0,'last_decision':None,'paused':False,'coverage_gaps':[],
            'metrics':{'empty_ms':0,'slot_ms':0,'observed_ms':0},'last_prices':{},'context':{}}

def fingerprint(state):
    fields=('id','side','entry','qty','margin','leverage','stop','target')
    positions={sym:{k:p.get(k) for k in fields} for sym,p in state['positions'].items()}
    return hashlib.sha256(json.dumps({'cash':state['cash'],'positions':positions,
            'paused':state['paused'],'coverage_gaps':state['coverage_gaps']},sort_keys=True,allow_nan=False).encode()).hexdigest()

def fresh(quote,now,cfg=Config()):
    try:return 0<=now-number(quote['ts_ms'])<=cfg.price_age_ms and number(quote['price'],1e-12)>0
    except (ValueError,KeyError,TypeError):return False

def margin(state):return sum(p['margin'] for p in state['positions'].values())
def equity(state,quotes):
    unrealized=0.;complete=True
    for sym,p in state['positions'].items():
        q=quotes.get(sym)
        if not q:complete=False;continue
        unrealized+=p['side']*(q['price']-p['entry'])*p['qty']
    return state['cash']+margin(state)+unrealized,complete

def rounded(value,step):
    return float((Decimal(str(value))/Decimal(str(step))).to_integral_value(rounding=ROUND_DOWN)*Decimal(str(step)))

def physical(position,contract,cfg):
    lev=position['entry']*position['qty']/position['margin']
    mmr=number(contract.get('maintenance',cfg.maintenance),0,.5)
    distance=1/lev-mmr-2*cfg.fee_rate
    if distance<=0:raise ValueError('no_liquidation_buffer')
    side=position['side'];entry=position['entry'];stop=position['stop']
    if side*(entry-stop)<=0: # A stop in profit is valid, too.
        stop_distance=0
    else:stop_distance=abs(entry-stop)/entry
    if stop_distance>cfg.liquidation_buffer*distance+1e-12:raise ValueError('stop_after_liquidation_buffer')
    position['leverage']=lev
    position['liquidation']=entry*(1-side*distance)

def apply(state,decision,quotes,contracts,now,cfg=Config()):
    """Returns (new account, audit events). Caller must persist the thesis first."""
    s=deepcopy(state);d=deepcopy(decision);sym=d['symbol'];act=d['action']
    if sym not in cfg.symbols:raise ValueError('unknown_symbol')
    if not fresh(quotes.get(sym),now,cfg):raise ValueError('stale_price')
    quote=quotes[sym];px=number(quote['price'],1e-12);reason=d['reason'];events=[]
    if not isinstance(reason,str) or not reason.strip():raise ValueError('missing_reason')
    p=s['positions'].get(sym)
    if act=='hold':return s,[]
    if act in ('open_long','open_short','dca'):
        if s['paused'] or s['verified_start_ms'] is None:raise ValueError('operator_not_active')
        if sym in s['coverage_gaps']:raise ValueError('unresolved_market_gap')
        if act=='dca' and not p:raise ValueError('missing_position')
        if act!='dca' and p:raise ValueError('symbol_already_open')
        if act!='dca' and len(s['positions'])>=cfg.max_slots:raise ValueError('slots_full')
        if not isinstance(d.get('invalidation'),str) or not d['invalidation'].strip():raise ValueError('missing_invalidation')
        c=contracts.get(sym)
        if not c or c.get('status')!='normal':raise ValueError('instrument_not_tradable')
        side=p['side'] if p else 1 if act=='open_long' else -1
        fill=px*(1+side*cfg.slippage)
        stop=number(d.get('stop',p['stop'] if p else None),1e-12)
        if side*(fill-stop)<=0:raise ValueError('stop_wrong_side_of_price')
        step=number(c['price_step'],1e-15)
        # Exchange tick normalization is explicit in the event, never a strategic stop move.
        requested_stop=stop
        stop=math.ceil(stop/step-1e-10)*step if side==1 else rounded(stop,step)
        if side*(fill-stop)<=0:raise ValueError('stop_tick_too_close')
        target=d.get('target',p.get('target') if p else None)
        if target is not None:
            target=number(target,1e-12)
            target=rounded(target,step) if side==1 else math.ceil(target/step-1e-10)*step
            if side*(target-fill)<=0:raise ValueError('target_wrong_side')
        requested_lev=number(d['leverage'],1)
        maximum=min(max_leverage(sym),number(c['max_leverage'],1))
        mmr=number(c.get('maintenance',cfg.maintenance),0,.5)
        distance=abs(fill-stop)/fill
        feasible=math.floor(1/(distance/cfg.liquidation_buffer+mmr+2*cfg.fee_rate))
        lev=min(math.floor(requested_lev),math.floor(maximum),feasible)
        if lev<1:raise ValueError('no_feasible_leverage')
        requested_margin=number(d['margin'],1e-9)
        allowed=min(requested_margin,max(0,cfg.max_margin-margin(s)),s['cash']/(1+lev*cfg.fee_rate))
        qty=rounded(allowed*lev/fill,number(c['qty_step'],1e-15))
        if qty<number(c['min_qty'],0) or qty*fill<number(c['min_notional'],0) or qty<=0:raise ValueError('below_exchange_minimum')
        actual_margin=qty*fill/lev;fee=qty*fill*cfg.fee_rate
        if actual_margin+fee>s['cash']+1e-8:raise ValueError('insufficient_cash')
        if p:
            total_qty=p['qty']+qty
            p['entry']=(p['entry']*p['qty']+fill*qty)/total_qty
            p['qty']=total_qty;p['margin']+=actual_margin;p['entry_fees']+=fee
            p['stop']=stop;p['target']=target;p['dca_count']+=1
            p['levels_ms']=now
        else:
            ident=s['next_id'];s['next_id']+=1
            p={'id':ident,'symbol':sym,'side':side,'entry':fill,'qty':qty,'margin':actual_margin,
               'stop':stop,'target':target,'open_ms':now,'levels_ms':now,'last_bar_ms':(now//60000)*60000,
               'entry_fees':fee,'funding':0.,'funding_seen':[], 'dca_count':0,'reason':reason,
               'invalidation':d['invalidation'],'source':'deepseek','partial_segments':[],
               'coverage_complete':True,'requested':d,'contract':deepcopy(c)}
            s['positions'][sym]=p
        physical(p,c,cfg)
        s['cash']-=actual_margin+fee
        if s['cash']<0 and s['cash']>-1e-8:s['cash']=0.
        event={'kind':'dca' if act=='dca' else 'open','symbol':sym,'position_id':p['id'],'side':side,
               'margin_added':actual_margin,'margin':p['margin'],'leverage':p['leverage'],'qty':p['qty'],
               'notional':p['entry']*p['qty'],'fee_paid':fee,'reason':reason,'invalidation':d['invalidation'],
               'requested_margin':requested_margin,'requested_leverage':requested_lev,'stop':stop,'target':target,
               'requested_stop':requested_stop,'adapted':abs(lev-requested_lev)>1e-9 or abs(actual_margin-requested_margin)>1e-6 or abs(stop-requested_stop)>1e-8}
        events.append(event)
    elif act in ('close','partial_close'):
        if not p:raise ValueError('missing_position')
        fraction=1. if act=='close' else number(d['fraction'],1e-9,1-1e-9)
        requested_fraction=fraction
        if act=='partial_close':
            c=contracts.get(sym,p['contract']);qty=rounded(p['qty']*fraction,c['qty_step'])
            if qty<c['min_qty'] or qty*px<c['min_notional']:raise ValueError('partial_below_exchange_minimum')
            remainder=p['qty']-qty
            fraction=1. if remainder<c['min_qty'] or remainder*px<c['min_notional'] else qty/p['qty']
        event=close(s,sym,px,now,reason,fraction,cfg)
        event['requested_fraction']=requested_fraction;event['executed_fraction']=fraction
        events.append(event)
    elif act in ('move_stop','move_target'):
        if not p:raise ValueError('missing_position')
        key='stop' if act=='move_stop' else 'target';value=number(d[key],1e-12)
        if (p['side']*(px-value)<=0 if key=='stop' else p['side']*(value-px)<=0):raise ValueError('level_wrong_side')
        step=number(contracts[sym]['price_step'],1e-15)
        if abs(value/step-round(value/step))>1e-6:raise ValueError('level_not_on_exchange_tick')
        p[key]=value;p['levels_ms']=now
        physical(p,contracts[sym],cfg)
        events.append({'kind':act,'symbol':sym,'position_id':p['id'],key:value,'reason':reason,'side':p['side']})
    else:raise ValueError('unknown_action')
    assert s['cash']>=-1e-8 and margin(s)<=cfg.max_margin+1e-8
    return s,events

def close(state,sym,px,now,reason,fraction=1.,cfg=Config()):
    p=state['positions'][sym];qty=p['qty']*fraction;released=p['margin']*fraction
    fill=px*(1-p['side']*cfg.slippage)
    fee=qty*fill*cfg.fee_rate;gross=p['side']*(fill-p['entry'])*qty
    liquidated=released+gross-fee<0
    if liquidated:gross=fee-released # Isolated-margin PAPER liability, no imaginary negative cash.
    entry_fee=p['entry_fees']*fraction;funding=p['funding']*fraction
    state['cash']+=released+gross-fee
    segment={'gross':gross,'fees':entry_fee+fee,'funding':funding,'net':gross-entry_fee-fee-funding,
             'qty':qty,'exit':fill,'close_ms':now,'reason':reason}
    segments=p['partial_segments']+[segment]
    done=fraction==1
    event={'kind':'trade_closed' if done else 'partial_trade','symbol':sym,'position_id':p['id'],
           'side':p['side'],'source':'deepseek' if reason.startswith('AI:') else 'physical_protection',
           'open_ms':p['open_ms'],'close_ms':now,'duration_minutes':(now-p['open_ms'])/60000,
           'reason':reason,'entry_reason':p['reason'],'entry':p['entry'],'leverage':p['leverage'],
           'margin':p['margin'],'invalidation':p['invalidation'],'liquidated':liquidated,
           'coverage_complete':p['coverage_complete'],'segment':dict(segment),'fee_paid':fee,**segment}
    if done:
        event.update({k:sum(x[k] for x in segments) for k in ('gross','fees','funding','net','qty')})
        event['outcome']='win' if event['net']>0 else 'loss' if event['net']<0 else 'flat'
        del state['positions'][sym]
    else:
        p['qty']*=1-fraction;p['margin']*=1-fraction;p['entry_fees']*=1-fraction;p['funding']*=1-fraction
        p['partial_segments']=segments
    return event

def _funding(state,sym,funding,market,contracts,now,cfg,events):
    p=state['positions'][sym];ts=funding['ts_ms']
    if not p['open_ms']<ts<=now or ts in p['funding_seen']:return
    amount=p['side']*p['qty']*funding['mark']*funding['rate']
    q=market.get('quote')
    if amount>=state['cash']+p['margin'] and not fresh(q,now,cfg):
        p['coverage_complete']=False;p['funding_pending']=True;return
    if amount>0:
        cash_part=min(amount,state['cash']);state['cash']-=cash_part
        collateral_part=amount-cash_part
        if collateral_part>=p['margin']:
            remaining=p['margin'];p['margin']=0.;p['funding']+=cash_part+remaining
            events.append(close(state,sym,q['price'],now,'funding_liquidation',cfg=cfg));return
        p['margin']-=collateral_part
    else:state['cash']-=amount
    p['funding']+=amount;p['funding_seen'].append(ts);p['funding_pending']=False
    try:physical(p,contracts.get(sym,p['contract']),cfg)
    except ValueError:
        if fresh(q,now,cfg):events.append(close(state,sym,q['price'],now,'funding_collateral_liquidation',cfg=cfg))
        else:p['coverage_complete']=False


def protect(state,markets,contracts,now,cfg=Config()):
    """Causal closed bars/funding, then fresh observed quotes; no profit heuristic."""
    s=deepcopy(state);events=[]
    for sym in list(s['positions']):
        p=s['positions'][sym];data=markets.get(sym,{})
        bars=data.get('bars',{}).get('1m',[])
        closed=[b for b in bars if b[0]+60000<=now and b[0]>p['last_bar_ms']]
        if closed and closed[0][0]>p['last_bar_ms']+60000:
            if sym not in s['coverage_gaps']:s['coverage_gaps'].append(sym)
            p['coverage_complete']=False
        timeline=[(b[0]+60000,0,b) for b in closed]
        timeline += [(f['ts_ms'],1,f) for f in data.get('funding',[]) if p['open_ms']<f['ts_ms']<=now and f['ts_ms'] not in p['funding_seen']]
        for ts,kind,item in sorted(timeline,key=lambda x:(x[0],x[1])):
            if sym not in s['positions']:break
            if kind:
                _funding(s,sym,item,data,contracts,now,cfg,events);continue
            p=s['positions'][sym];b=item;start,op,hi,lo,cl,_=b;p['last_bar_ms']=start
            if start<p['levels_ms']:continue
            stop_hit=lo<=p['stop'] if p['side']==1 else hi>=p['stop']
            target_hit=p['target'] is not None and (hi>=p['target'] if p['side']==1 else lo<=p['target'])
            if stop_hit:
                fill=min(op,p['stop']) if p['side']==1 else max(op,p['stop'])
                events.append(close(s,sym,fill,ts,'stop_closed_bar',cfg=cfg))
            elif target_hit:
                fill=max(op,p['target']) if p['side']==1 else min(op,p['target'])
                events.append(close(s,sym,fill,ts,'target_closed_bar',cfg=cfg))
        if sym not in s['positions']:continue
        p=s['positions'][sym];q=data.get('quote')
        if fresh(q,now,cfg):
            px=q['price']
            if p['side']*(px-p['stop'])<=0:events.append(close(s,sym,px,now,'stop_observed_quote',cfg=cfg))
            elif p['target'] is not None and p['side']*(px-p['target'])>=0:events.append(close(s,sym,px,now,'target_observed_quote',cfg=cfg))
    return s,events
