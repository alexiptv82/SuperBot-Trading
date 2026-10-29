"""Offline deterministic conditional PAPER execution; no network or LLM inside.

A future supervisor submits vetted AI plans and calls tick with observed data.
This module cannot touch the original Brain or classical portfolios.
"""
from dataclasses import asdict,replace
import math
from director.brain_free.execution import apply,close,fresh,margin,protect
from .config import SPECS,ENTRY_PRICE_AGE_MS,PROTECT_PRICE_AGE_MS
from .plans import Plan,parse_plan,triggered
from .store import WalletStore


def _risk(position,cfg):
    side,qty=position['side'],position['qty']
    return (max(0.,side*(position['entry']-position['stop'])*qty) +
            position['entry']*qty*(2*cfg.fee_rate+2*cfg.slippage))


def _resize_for_budget(plan,fill,state,spec,cfg,risk_used):
    """Reduce margin/leverage only; NEVER exceed the original AI request.

    Estimate one full round-trip including the planned stop, fees/slippage.
    Pending reservations from OTHER plans are preserved. Return None when
    even minimum margin at 1x cannot satisfy all hard constraints.
    """
    cost=2*(cfg.fee_rate+cfg.slippage)
    risk_per_notional=abs(fill-plan.stop)/fill+cost
    allowed_risk=min(spec.risk_trade_usd,spec.risk_portfolio_usd-risk_used)
    other_pending=sum(x['margin'] for sym,x in state['plans'].items()
                      if sym!=plan.symbol)
    capacity=spec.max_margin_total-margin(state)-other_pending
    if allowed_risk<=0 or capacity<spec.min_margin:
        return None
    for lev in range(plan.leverage,0,-1):
        max_by_risk=allowed_risk/(lev*risk_per_notional)
        max_by_cash=state['cash']/(1+lev*cfg.fee_rate)
        candidate=min(plan.margin,capacity,max_by_cash,max_by_risk)
        # Round DOWN to cents to keep estimated loss within risk cap.
        size=math.floor((candidate+1e-10)*100)/100
        if size+1e-9<spec.min_margin:
            continue
        estimated=size*lev*risk_per_notional
        if estimated<=allowed_risk+1e-8:
            return size,lev,estimated
    return None


def _target_cost_guard(side,entry,target,cfg):
    """Require projected net target of at least one full round-trip cost."""
    cost=2*(cfg.fee_rate+cfg.slippage)
    gross=side*(target-entry)/entry
    return gross>=2*cost-1e-12


def _target_cost_feedback(side,entry,target,cfg):
    """Explain the conservative gross target required, without changing it."""
    cost=2*(cfg.fee_rate+cfg.slippage)
    net=side*(target-entry)/entry-cost
    return {'costs_pct':round(cost*100,4),
            'net_at_target_pct':round(net*100,4),
            'min_required_pct':round(cost*100,4),
            'min_target_price':round(entry*(1+side*2*cost),8)}


class PlanCostError(ValueError):
    """A cost-rejected plan also carries safe structured AI feedback."""
    def __init__(self,details):
        super().__init__('target_below_costs')
        self.details=details


def _net_at_quote(position,quote_price,cfg):
    fill=quote_price*(1-position['side']*cfg.slippage)
    return (position['side']*(fill-position['entry'])*position['qty'] -
            position['entry_fees']-position.get('funding',0) -
            position['qty']*fill*cfg.fee_rate)



def _safe_equity(state,quotes):
    """Never value malformed marks, and fail closed to new openings.

    Protective OHLC checks still execute before valuation. Incomplete marking
    reports incomplete=True rather than treating missing unrealized P&L as zero.
    Shared Brain Free execution.py is deliberately unchanged.
    """
    unrealized=0.0
    missing=[]
    for symbol,p in state['positions'].items():
        q=quotes.get(symbol)
        price=q.get('price') if isinstance(q,dict) else None
        if (isinstance(price,bool) or not isinstance(price,(int,float))
                or not math.isfinite(price) or price<=0):
            missing.append(symbol)
            continue
        unrealized+=p['side']*(float(price)-p['entry'])*p['qty']
    return state['cash']+margin(state)+unrealized,not bool(missing),missing


def _valid_quote(q):
    """Reject invalid prices before persisting snapshots as strict JSON."""
    if not isinstance(q,dict):
        return False
    price=q.get('price')
    return (not isinstance(price,bool) and isinstance(price,(int,float))
            and math.isfinite(price) and price>0)



def _price_tick(price,step,side):
    """Tighten a protective stop to the next conservative exchange tick."""
    from decimal import Decimal,ROUND_CEILING,ROUND_FLOOR
    p=Decimal(str(price))
    tick=Decimal(str(step))
    if not (p.is_finite() and tick.is_finite() and p>0 and tick>0):
        raise ValueError('invalid_protection_price_tick')
    mode=ROUND_CEILING if side==1 else ROUND_FLOOR
    return float((p/tick).to_integral_value(rounding=mode)*tick)


def _breakeven_observed_quote(position,cfg):
    """Quote that would cover modeled entry/exit fee, slippage and funding.

    Assumes fill at observed quote +/- modeled exit slippage. A real future
    gap can still fill worse; this is not a guaranteed floor on realized P&L.
    """
    side=position['side']
    qty=position['qty']
    if qty<=0: raise ValueError('invalid_position_quantity')
    numerator=side*position['entry']+(
        position['entry_fees']+position.get('funding',0))/qty
    denominator=side-cfg.fee_rate
    if abs(denominator)<1e-9: raise ValueError('invalid_fee_model')
    return numerator/denominator/(1-side*cfg.slippage)


def _invalidation_hit(side,price,invalidate_price):
    return invalidate_price is not None and side*(price-invalidate_price)<=0


def _protect_stop_with_quote(position,symbol,quote,candidate,now,contracts,events,kind):
    """Only tighten stops at a valid tick; never loosen protective risk."""
    side=position['side']
    c=contracts.get(symbol,position.get('contract',{}))
    step=c.get('price_step')
    if not isinstance(step,(int,float)) or isinstance(step,bool) or step<=0:
        events.append({'kind':'protection_deferred','symbol':symbol,
                       'reason':'missing_price_step'})
        return False
    desired=_price_tick(candidate,step,side)
    if side*(desired-position['stop'])<=1e-9:
        return False
    if side*(quote-desired)<=1e-9:
        # The candidate is already reached: caller must close at observed quote.
        return 'crossed'
    position['stop']=desired
    position['levels_ms']=now
    events.append({'kind':kind,'symbol':symbol,'stop_price':desired,
                   'observed_price':quote})
    return True


class PaperWallet:
    def __init__(self,root,name,initialize=False,now_ms=None):
        self.spec=SPECS[name]
        self.cfg=self.spec.brain_config()
        self.entry_cfg=replace(self.cfg,price_age_ms=ENTRY_PRICE_AGE_MS)
        self.protect_cfg=replace(self.cfg,price_age_ms=PROTECT_PRICE_AGE_MS)
        self.store=WalletStore(root,name,initialize=initialize,now_ms=now_ms)

    def close(self): self.store.close()

    def submit(self,raw,now,whitelist,quotes):
        """Reserve one slot and requested margin. NEVER execute in submit."""
        plan=parse_plan(raw,self.spec,now,whitelist)
        state=self.store.load()
        # Reservations are risk commitments too. Never accept a plan while a
        # daily latch is active or before an accurate UTC rollover tick.
        if now//86400000!=state['daily']['utc']:
            raise ValueError('daily_rollover_tick_required')
        if state['daily_stop_triggered']:
            raise ValueError('daily_stop_latched')
        if not _target_cost_guard(plan.side,plan.trigger_price,plan.target,self.cfg):
            raise PlanCostError(_target_cost_feedback(
                plan.side,plan.trigger_price,plan.target,self.cfg))
        q=quotes.get(plan.symbol)
        if not fresh(q,now,self.entry_cfg):
            if fresh(q,now,self.cfg):
                raise ValueError('quote_too_stale_for_entry')
            raise ValueError('stale_plan_quote')
        if plan.plan_id in state['plan_ids']: raise ValueError('duplicate_plan_id')
        if plan.symbol in state.get('coverage_gaps',[]):
            raise ValueError('symbol_coverage_gap_unresolved')
        if plan.symbol in state['positions'] or plan.symbol in state['plans']:
            raise ValueError('symbol_already_reserved')
        if len(state['positions'])+len(state['plans'])>=self.spec.slots:
            raise ValueError('all_slots_reserved')
        if margin(state)+sum(p['margin'] for p in state['plans'].values())+plan.margin>self.spec.max_margin_total:
            raise ValueError('reserved_margin_exceeded')
        if state['cash']<plan.margin*(1+plan.leverage*self.cfg.fee_rate):
            raise ValueError('cash_not_available')
        state['plans'][plan.symbol]=asdict(plan)
        state['plan_ids'].append(plan.plan_id)
        self.store.commit(state,now,[{'kind':'plan_reserved','symbol':plan.symbol,
                                     'plan_id':plan.plan_id,'side':plan.side,
                                     'expires_ms':plan.expires_ms}])
        return plan

    def tick(self,markets,contracts,now,market_events=()):
        """Repair audit first, then protect, expire, and execute pending plans."""
        state=self.store.load()
        # Gaps not filled before this tick cannot be silently ignored.
        # Once an OPEN position was exposed to an unknown historical minute,
        # its coverage remains flagged until explicit audited reconciliation.
        recoverable_gaps=set()
        for event in market_events:
            if event['kind'] in ('gap_unresolvable','gap_backfill_failed'):
                symbol=event['symbol']
                if symbol not in state['coverage_gaps']:
                    state['coverage_gaps'].append(symbol)
                if symbol in state['positions']:
                    position=state['positions'][symbol]
                    # Preserve the last fully checked closed bar. Never
                    # reclassify pre-patch unknown gaps as automatically safe.
                    position.setdefault('scalp_gap_cursor_ms',position['last_bar_ms'])
                    position['coverage_complete']=False
            elif event['kind'] in ('gap_backfilled','gap_history_complete'):
                symbol=event['symbol']
                if symbol not in state['positions']:
                    if symbol in state['coverage_gaps']:
                        state['coverage_gaps'].remove(symbol)
                elif 'scalp_gap_cursor_ms' in state['positions'][symbol]:
                    recoverable_gaps.add(symbol)
        original_now=now
        delta_ms=max(0,state['last_ms']-now)
        if delta_ms:
            now=state['last_ms']
        state['last_ms']=now
        state['heartbeat_ms']=now
        state['last_prices']={s:m['quote'] for s,m in markets.items() if _valid_quote(m.get('quote'))}
        state,events=protect(state,markets,contracts,now,self.protect_cfg)
        events=list(market_events)+events
        # A quarantined position can be restored only after the actual
        # missing candles have been validated and replayed by protect().
        for symbol in recoverable_gaps:
            position=state['positions'].get(symbol)
            if position is None:
                if symbol in state['coverage_gaps']:
                    state['coverage_gaps'].remove(symbol)
                events.append({'kind':'gap_recovered_verified','symbol':symbol,
                               'result':'position_closed_on_replay'})
                continue
            original=position.get('scalp_gap_cursor_ms')
            latest=position.get('last_bar_ms')
            candles=(markets.get(symbol,{}).get('bars') or {}).get('1m',[])
            observed={row[0] for row in candles if isinstance(row,(list,tuple))
                      and len(row)>=6 and isinstance(row[0],int)}
            if (isinstance(original,int) and isinstance(latest,int)
                    and latest>original and all(
                        t in observed for t in range(
                            original+60000,latest+60000,60000))):
                position['coverage_complete']=True
                del position['scalp_gap_cursor_ms']
                if symbol in state['coverage_gaps']:
                    state['coverage_gaps'].remove(symbol)
                events.append({'kind':'gap_recovered_verified','symbol':symbol,
                               'result':'continuous_replay'})
        if delta_ms:
            events.insert(0,{'kind':'clock_adjusted','delta_ms':delta_ms,
                             'original_now_ms':original_now})
        quotes={sym:m['quote'] for sym,m in markets.items() if m.get('quote')}
        for symbol,d in list(state['plans'].items()):
            if now>=d['expires_ms']:
                del state['plans'][symbol]
                events.append({'kind':'plan_expired','symbol':symbol,'plan_id':d['plan_id']})
        capital,complete,unmarked=_safe_equity(state,quotes)
        for symbol in unmarked:
            events.append({'kind':'equity_unavailable','symbol':symbol,
                           'reason':'invalid_or_missing_mark'})
        opening_allowed=(delta_ms<=500 and complete and
                         all(fresh(quotes.get(sym),now,self.entry_cfg) for sym in state['positions']))
        today=now//86400000
        fully_marked=(complete and all(
            fresh(quotes.get(sym),now,self.protect_cfg)
            for sym in state['positions']))
        if today!=state['daily']['utc']:
            if fully_marked:
                # Rollover is only safe when every open position is valued
                # from a recent, valid quote; never use partial equity.
                state['daily']={'utc':today,'start_equity':capital}
                state['daily_stop_day']=today
                state['daily_stop_triggered']=False
                events.append({'kind':'daily_stop_reset_utc','day_utc':today,
                               'reference_equity':capital})
            else:
                opening_allowed=False
        if fully_marked and today==state['daily']['utc']:
            baseline=state['daily']['start_equity']
            if capital<=baseline*(1-self.spec.daily_stop_pct):
                if not state['daily_stop_triggered']:
                    state['daily_stop_triggered']=True
                    state['daily_stop_day']=today
                    events.append({'kind':'daily_stop_latched','day_utc':today,
                                   'drawdown_pct':round(100*(1-capital/baseline),4),
                                   'limit_pct':100*self.spec.daily_stop_pct})
        if state['daily_stop_triggered'] or today!=state['daily']['utc']:
            opening_allowed=False
        if capital<=self.spec.kill_equity:
            opening_allowed=False
        # Profit policy is based on observed fresh quotes, not future extrema.
        # The shared physical protector has already checked closed candles.
        for symbol,p in list(state['positions'].items()):
            q=quotes.get(symbol)
            if not fresh(q,now,self.protect_cfg): continue
            if symbol in state['coverage_gaps'] or not p.get('coverage_complete',True):
                continue
            policy=p.get('scalp_policy') or {}
            px=q['price']
            net=_net_at_quote(p,px,self.cfg)
            peak=max(policy.get('peak_net',0.),net)
            policy['peak_net']=peak
            best=policy.get('best_observed_quote',px)
            best=max(best,px) if p['side']==1 else min(best,px)
            policy['best_observed_quote']=best
            p['scalp_policy']=policy
            if _invalidation_hit(p['side'],px,policy.get('invalidate_price')):
                events.append(close(state,symbol,px,now,
                                    'scalp_invalidation_observed',cfg=self.cfg))
                continue
            if policy.get('take_net_usd',0)>0 and net>=policy['take_net_usd']:
                events.append(close(state,symbol,px,now,
                                    'scalp_net_target_observed',cfg=self.cfg))
                continue
            if (policy.get('protect_after_usd',0)>0 and
                    peak>=policy['protect_after_usd'] and net<=peak*.65):
                events.append(close(state,symbol,px,now,
                                    'scalp_net_giveback_observed',cfg=self.cfg))
                continue
            if policy.get('hold_max_ms') and now-p['open_ms']>=policy['hold_max_ms']:
                events.append(close(state,symbol,px,now,
                                    'scalp_time_limit_observed',cfg=self.cfg))
                continue
            steps=policy.get('scale_out') or []
            done=policy.setdefault('scale_out_done',[])
            for index,step in enumerate(steps):
                if index in done or net<step['net_usd']: continue
                fraction=step['fraction']
                c=contracts.get(symbol,p.get('contract',{}))
                qty_step=c.get('qty_step',0)
                min_qty=c.get('min_qty',0)
                min_notional=c.get('min_notional',0)
                qty=p['qty']*fraction
                remainder=p['qty']-qty
                if (qty_step<=0 or qty<min_qty or qty*px<min_notional or
                        (fraction<1 and (remainder<min_qty or
                         remainder*px<min_notional))):
                    events.append({'kind':'scale_out_deferred','symbol':symbol,
                                   'index':index,'reason':'contract_minimum'})
                    break
                events.append(close(state,symbol,px,now,
                                    'scalp_scale_out_observed',fraction=1. if
                                    fraction>=1 else fraction,cfg=self.cfg))
                done.append(index)
                events.append({'kind':'scale_out_executed','symbol':symbol,
                               'index':index,'fraction_of_remaining':fraction})
                if symbol in state['positions']:
                    p=state['positions'][symbol]
                    policy=p['scalp_policy']
                    # Absolute USD peak changes with quantity after partial.
                    policy['peak_net']=max(0.,peak*(1-fraction))
                    net=_net_at_quote(p,px,self.cfg)
                    peak=policy['peak_net']
                break
            if symbol not in state['positions']: continue
            p=state['positions'][symbol]
            policy=p['scalp_policy']
            threshold=policy.get('breakeven_after_usd')
            if threshold is None:
                threshold=policy.get('protect_after_usd',0)
            if threshold>0 and (peak>=threshold or policy.get('breakeven_set')):
                # Funding can accrue after the initial activation. Recompute
                # the required quote each tick and tighten monotonically.
                threshold_quote=_breakeven_observed_quote(p,self.cfg)
                status=_protect_stop_with_quote(
                    p,symbol,px,threshold_quote,now,contracts,
                    events,'breakeven_set')
                if status=='crossed':
                    events.append(close(state,symbol,px,now,
                                        'scalp_breakeven_crossed',cfg=self.cfg))
                    continue
                if status or p['side']*(p['stop']-threshold_quote)>=0:
                    policy['breakeven_set']=True
            trail=policy.get('trail_bps')
            if trail is not None and peak>0 and peak>=threshold:
                # Best is an actual observed quote, not a look-ahead bar high.
                trail_price=policy['best_observed_quote']*(
                    1-p['side']*trail/10000)
                status=_protect_stop_with_quote(
                    p,symbol,px,trail_price,now,contracts,
                    events,'scalp_trail_tightened')
                if status=='crossed':
                    events.append(close(state,symbol,px,now,
                                        'scalp_trail_crossed',cfg=self.cfg))
        # Invalidation must also be checked when opening is disabled or paused.
        for symbol,raw in list(state['plans'].items()):
            p=Plan(**raw)
            q=quotes.get(symbol)
            if (fresh(q,now,self.protect_cfg) and
                    _invalidation_hit(p.side,q['price'],p.invalidate_price)):
                del state['plans'][symbol]
                events.append({'kind':'plan_invalidated','symbol':symbol,
                               'plan_id':p.plan_id,'observed_price':q['price']})
        # Physical and scalp exits can realize more costs than the mark-price
        # estimate. Re-evaluate risk AFTER all exits and BEFORE opening plans.
        end_capital,end_complete,_=_safe_equity(state,quotes)
        end_fresh=(end_complete and all(
            fresh(quotes.get(sym),now,self.protect_cfg)
            for sym in state['positions']))
        if not end_fresh:
            opening_allowed=False
        elif today==state['daily']['utc']:
            end_baseline=state['daily']['start_equity']
            if end_capital<=end_baseline*(1-self.spec.daily_stop_pct):
                if not state['daily_stop_triggered']:
                    state['daily_stop_triggered']=True
                    state['daily_stop_day']=today
                    events.append({'kind':'daily_stop_latched','day_utc':today,
                                   'drawdown_pct':round(
                                       100*(1-end_capital/end_baseline),4),
                                   'limit_pct':100*self.spec.daily_stop_pct})
                opening_allowed=False
            if end_capital<=self.spec.kill_equity:
                opening_allowed=False
        risk_used=sum(_risk(p,self.cfg) for p in state['positions'].values())
        for symbol,raw in list(state['plans'].items()):
            if not opening_allowed or state.get('paused'): break
            p=Plan(**raw)
            if symbol in state.get('coverage_gaps',[]):
                # Keep the reservation (until it expires) but NEVER open a
                # symbol whose historical stop/target coverage is unknown.
                events.append({'kind':'plan_deferred','symbol':symbol,
                               'plan_id':p.plan_id,
                               'why':'symbol_coverage_gap_unresolved'})
                continue
            q=quotes.get(symbol)
            if not triggered(p,q,now): continue
            if symbol in state['positions']:
                del state['plans'][symbol]
                events.append({'kind':'plan_rejected','symbol':symbol,'why':'already_open'})
                continue
            px=q['price'];fill=px*(1+p.side*self.cfg.slippage)
            if not _target_cost_guard(p.side,fill,p.target,self.cfg):
                del state['plans'][symbol]
                events.append({'kind':'plan_rejected','symbol':symbol,
                               'why':'target_below_costs',
                               **_target_cost_feedback(p.side,fill,p.target,self.cfg)})
                continue
            if p.side*(fill-p.stop)<=0 or p.side*(p.target-fill)<=0:
                del state['plans'][symbol]
                events.append({'kind':'plan_rejected','symbol':symbol,'why':'levels_invalid_at_trigger'})
                continue
            sizing=_resize_for_budget(p,fill,state,self.spec,self.cfg,risk_used)
            if sizing is None:
                del state['plans'][symbol]
                events.append({'kind':'plan_rejected','symbol':symbol,
                               'why':'below_min_margin_after_resize',
                               'remaining_risk_usd':max(0.,min(
                                   self.spec.risk_trade_usd,
                                   self.spec.risk_portfolio_usd-risk_used))})
                continue
            sized_margin,sized_leverage,estimated=sizing
            decision={'symbol':symbol,'action':'open_long' if p.side==1 else 'open_short',
                      'reason':'AI: '+p.reason,'invalidation':p.invalidation,'stop':p.stop,
                      'target':p.target,'margin':sized_margin,'leverage':sized_leverage}
            try:
                state2,opened=apply(state,decision,quotes,contracts,now,self.entry_cfg)
            except (ValueError,KeyError,TypeError) as ex:
                del state['plans'][symbol]
                events.append({'kind':'plan_rejected','symbol':symbol,'why':str(ex)[:100]})
                continue
            # Applying the contract may only REDUCE size/leverage. Verify
            # actual post-normalization risk, not just the plan estimate.
            actual_risk=_risk(state2['positions'][symbol],self.cfg)
            if actual_risk>self.spec.risk_trade_usd+1e-7 or (
                    actual_risk+risk_used>self.spec.risk_portfolio_usd+1e-7):
                del state['plans'][symbol]
                events.append({'kind':'plan_rejected','symbol':symbol,
                               'why':'risk_after_execution_normalization'})
                continue
            state=state2;del state['plans'][symbol]
            if sized_margin<p.margin-1e-8 or sized_leverage<p.leverage:
                events.append({'kind':'plan_resized','symbol':symbol,
                               'plan_id':p.plan_id,'original_margin':p.margin,
                               'new_margin':sized_margin,
                               'original_leverage':p.leverage,
                               'new_leverage':sized_leverage,
                               'risk_budget_usd':max(0.,min(
                                   self.spec.risk_trade_usd,
                                   self.spec.risk_portfolio_usd-risk_used))})
            state['positions'][symbol]['scalp_policy']={'hold_max_ms':p.hold_max_ms,
                        'protect_after_usd':p.protect_after_usd,
                        'take_net_usd':p.take_net_usd,'peak_net':0.,'plan_id':p.plan_id,
                        'breakeven_after_usd':p.breakeven_after_usd,
                        'breakeven_set':False,'trail_bps':p.trail_bps,
                        'scale_out':p.scale_out or [],'scale_out_done':[],
                        'invalidate_price':p.invalidate_price,
                        'best_observed_quote':px}
            events.extend(opened)
            actual_fill=state['positions'][symbol]['entry']
            events.append({'kind':'entry_fill','symbol':symbol,'plan_id':p.plan_id,
                           'trigger_price':p.trigger_price,'observed_price':px,
                           'fill_price':actual_fill,
                           'slippage_pct':abs(actual_fill-p.trigger_price)/p.trigger_price*100,
                           'execution_slippage_pct':abs(actual_fill-px)/px*100,
                           'quote_age_ms':now-q['ts_ms']})
            risk_used+=estimated
        self.store.commit(state,now,events)
        return {'account_id':self.spec.account_id,'positions':len(state['positions']),
                'pending':len(state['plans']),'cash':state['cash'],
                'opening_allowed':opening_allowed,'events':events}
