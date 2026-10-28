"""Offline deterministic conditional PAPER execution; no network or LLM inside.

A future supervisor submits vetted AI plans and calls tick with observed data.
This module cannot touch the original Brain or classical portfolios.
"""
from dataclasses import asdict
from director.brain_free.execution import apply,close,equity,fresh,margin,protect
from .config import SPECS
from .plans import Plan,parse_plan,triggered
from .store import WalletStore


def _risk(position,cfg):
    side,qty=position['side'],position['qty']
    return (max(0.,side*(position['entry']-position['stop'])*qty) +
            position['entry']*qty*(2*cfg.fee_rate+2*cfg.slippage))


def _net_at_quote(position,quote_price,cfg):
    fill=quote_price*(1-position['side']*cfg.slippage)
    return (position['side']*(fill-position['entry'])*position['qty'] -
            position['entry_fees']-position.get('funding',0) -
            position['qty']*fill*cfg.fee_rate)


class PaperWallet:
    def __init__(self,root,name,initialize=False,now_ms=None):
        self.spec=SPECS[name]
        self.cfg=self.spec.brain_config()
        self.store=WalletStore(root,name,initialize=initialize,now_ms=now_ms)

    def close(self): self.store.close()

    def submit(self,raw,now,whitelist,quotes):
        """Reserve one slot and requested margin. NEVER execute in submit."""
        plan=parse_plan(raw,self.spec,now,whitelist)
        state=self.store.load()
        q=quotes.get(plan.symbol)
        if not fresh(q,now,self.cfg): raise ValueError('stale_plan_quote')
        if plan.plan_id in state['plan_ids']: raise ValueError('duplicate_plan_id')
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

    def tick(self,markets,contracts,now):
        """Protect open positions first, then close/expire, then execute pending."""
        state=self.store.load()
        if now<state['last_ms']: raise ValueError('backward_clock')
        state['last_ms']=now
        state,events=protect(state,markets,contracts,now,self.cfg)
        quotes={sym:m['quote'] for sym,m in markets.items() if m.get('quote')}
        for symbol,d in list(state['plans'].items()):
            if now>=d['expires_ms']:
                del state['plans'][symbol]
                events.append({'kind':'plan_expired','symbol':symbol,'plan_id':d['plan_id']})
        capital,complete=equity(state,quotes)
        opening_allowed=complete and all(fresh(quotes.get(sym),now,self.cfg) for sym in state['positions'])
        today=now//86400000
        if today!=state['daily']['utc'] and opening_allowed:
            state['daily']={'utc':today,'start_equity':capital}
        if today!=state['daily']['utc']:
            opening_allowed=False
        if capital<=self.spec.kill_equity or capital<=state['daily']['start_equity']*(1-self.spec.daily_stop_pct):
            opening_allowed=False
        # Observe profits from fresh quotes, never from historical bar extremes.
        for symbol,p in list(state['positions'].items()):
            q=quotes.get(symbol)
            if not fresh(q,now,self.cfg): continue
            policy=p.get('scalp_policy') or {}
            net=_net_at_quote(p,q['price'],self.cfg)
            peak=max(policy.get('peak_net',0),net)
            policy['peak_net']=peak
            p['scalp_policy']=policy
            reason=None
            if policy.get('take_net_usd',0)>0 and net>=policy['take_net_usd']:
                reason='scalp_net_target_observed'
            elif (policy.get('protect_after_usd',0)>0 and peak>=policy['protect_after_usd']
                  and net>0 and net<=peak*.65):
                reason='scalp_net_giveback_observed'
            elif policy.get('hold_max_ms') and now-p['open_ms']>=policy['hold_max_ms']:
                reason='scalp_time_limit_observed'
            if reason:
                events.append(close(state,symbol,q['price'],now,reason,cfg=self.cfg))
        risk_used=sum(_risk(p,self.cfg) for p in state['positions'].values())
        for symbol,raw in list(state['plans'].items()):
            if not opening_allowed or state.get('paused'): break
            p=Plan(**raw)
            q=quotes.get(symbol)
            if not triggered(p,q,now): continue
            if symbol in state['positions']:
                del state['plans'][symbol]
                events.append({'kind':'plan_rejected','symbol':symbol,'why':'already_open'})
                continue
            px=q['price'];fill=px*(1+p.side*self.cfg.slippage)
            if p.side*(fill-p.stop)<=0 or p.side*(p.target-fill)<=0:
                del state['plans'][symbol]
                events.append({'kind':'plan_rejected','symbol':symbol,'why':'levels_invalid_at_trigger'})
                continue
            estimated=p.margin*p.leverage*(abs(fill-p.stop)/fill+2*(self.cfg.fee_rate+self.cfg.slippage))
            if estimated>self.spec.risk_trade_usd or estimated+risk_used>self.spec.risk_portfolio_usd:
                del state['plans'][symbol]
                events.append({'kind':'plan_rejected','symbol':symbol,'why':'stop_risk_budget'})
                continue
            decision={'symbol':symbol,'action':'open_long' if p.side==1 else 'open_short',
                      'reason':'AI: '+p.reason,'invalidation':p.invalidation,'stop':p.stop,
                      'target':p.target,'margin':p.margin,'leverage':p.leverage}
            try:
                state2,opened=apply(state,decision,quotes,contracts,now,self.cfg)
            except (ValueError,KeyError,TypeError) as ex:
                del state['plans'][symbol]
                events.append({'kind':'plan_rejected','symbol':symbol,'why':str(ex)[:100]})
                continue
            state=state2;del state['plans'][symbol]
            state['positions'][symbol]['scalp_policy']={'hold_max_ms':p.hold_max_ms,
                        'protect_after_usd':p.protect_after_usd,
                        'take_net_usd':p.take_net_usd,'peak_net':0.,'plan_id':p.plan_id}
            events.extend(opened);risk_used+=estimated
        self.store.commit(state,now,events)
        return {'account_id':self.spec.account_id,'positions':len(state['positions']),
                'pending':len(state['plans']),'cash':state['cash'],
                'opening_allowed':opening_allowed,'events':events}
