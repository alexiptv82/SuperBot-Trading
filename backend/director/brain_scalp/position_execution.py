"""Owner-thread, atomic, opt-in reduce-only actions for reviewed PAPER positions.

No network, order API, background thread, Telegram control or account startup.
All preconditions have been checked in position_review.record_position_review.
This unit additionally validates action-specific risk and commits the complete
financial ledger and the AI receipt in one SQLite transaction.
"""
from copy import deepcopy
import math

from director.brain_free.execution import close as settle_paper,rounded
from .engine import _protect_stop_with_quote
from .metrics import build_metrics


def apply_paper_review(wallet,state,request,result,findings,markets,contracts,now):
    if wallet.spec.name!='brain' or state.get('mode')!='paper':
        raise ValueError('paper_brain_only')
    if not isinstance(contracts,dict):
        raise ValueError('missing_contracts')
    approved=result.approved_symbols
    if not isinstance(approved,tuple) or any(
            not isinstance(sym,str) for sym in approved):
        raise ValueError('invalid_reviewer_authority')
    known={f['symbol'] for f in findings if f['action']!='HOLD'}
    if set(approved)-known or len(set(approved))!=len(approved):
        raise ValueError('reviewer_authority_mismatch')
    updated=deepcopy(state)
    events=[]
    actions=[];deferred=[]
    for review in findings:
        action=review['action']
        if action=='HOLD':
            continue
        sym=review['symbol']
        if (not result.reviewed or sym not in approved):
            deferred.append({'symbol':sym,'why':'reviewer_agreement_required'})
            continue
        position=updated['positions'].get(sym)
        if (position is None or str(position.get('id'))!=review['position_id'] or
                not position.get('coverage_complete',True) or
                sym in updated.get('coverage_gaps',[])):
            raise ValueError('position_not_safe_for_ai_action')
        market=markets.get(sym)
        quote=market.get('quote') if isinstance(market,dict) else None
        if not isinstance(quote,dict):
            raise ValueError('action_quote_missing')
        px=quote.get('price')
        if type(px) not in (int,float) or not math.isfinite(px) or px<=0:
            raise ValueError('invalid_action_price')
        if action in ('SUGGEST_CLOSE','SUGGEST_REDUCE'):
            fraction=1.
            old_qty=position['qty']
            if action=='SUGGEST_REDUCE':
                contract=contracts.get(sym)
                if not isinstance(contract,dict) or contract.get('status')!='normal':
                    raise ValueError('action_contract_unavailable')
                requested=review['fraction']
                step=contract['qty_step']
                minimum=contract['min_qty'];notional=contract['min_notional']
                if (any(type(v) not in (int,float) or not math.isfinite(v)
                        for v in (step,minimum,notional)) or step<=0 or minimum<0 or notional<0):
                    raise ValueError('invalid_action_contract')
                qty=rounded(old_qty*requested,step)
                remainder=old_qty-qty
                fill=px*(1-position['side']*wallet.cfg.slippage)
                if (qty<=0 or qty>=old_qty or qty<minimum or qty*fill<notional or
                        remainder<minimum or remainder*px<notional):
                    # Never silently promote a partial proposal to a full close.
                    raise ValueError('partial_or_residual_below_minimum')
                fraction=qty/old_qty
            financial=settle_paper(updated,sym,px,now,
                                   'AI:position_review',fraction=fraction,cfg=wallet.cfg)
            expected='partial_trade' if action=='SUGGEST_REDUCE' else 'trade_closed'
            if financial['kind']!=expected:
                raise ValueError('incomplete_ai_close')
            if action=='SUGGEST_REDUCE':
                residual=updated['positions'][sym]
                policy=residual.get('scalp_policy')
                if isinstance(policy,dict):
                    policy['peak_net']=max(0.,policy.get('peak_net',0.)*residual['qty']/old_qty)
                financial.update(requested_fraction=requested,executed_fraction=fraction)
            financial.update({'paper':True,'bot':'brain',
                              'account_id':wallet.spec.account_id,
                              'ai_context_id':request.context_id,
                              'ai_reviewer_agreed':True})
            updated['plans'].pop(sym,None)
            events.append(financial)
            actions.append({'symbol':sym,'action':'reduced' if action=='SUGGEST_REDUCE' else 'closed',
                            'position_id':review['position_id']})
        elif action=='SUGGEST_TIGHTEN':
            contract=contracts.get(sym)
            if (not isinstance(contract,dict) or
                    contract.get('status')!='normal'):
                raise ValueError('action_contract_unavailable')
            proposed=review.get('stop_price')
            if type(proposed) not in (int,float) or not math.isfinite(proposed) or proposed<=0:
                raise ValueError('invalid_ai_stop')
            prior_stop=position['stop']
            changed=_protect_stop_with_quote(position,sym,px,proposed,
                                             now,contracts,events,
                                             'ai_review_stop_tightened')
            if changed is not True:
                # No-op and a crossed stop are rejected, not converted to a
                # discretionary close or a fake successful stop change.
                raise ValueError('ai_stop_not_valid_tightening')
            if position['side']*(position['stop']-prior_stop)<=1e-9:
                raise ValueError('ai_stop_widening')
            if position['side']*(px-position['stop'])<=1e-9:
                raise ValueError('ai_stop_crosses_quote')
            actions.append({'symbol':sym,'action':'stop_tightened',
                            'position_id':review['position_id'],
                            'stop':position['stop']})
        else:
            raise ValueError('unrecognized_ai_action')
    updated['last_position_review_context_id']=request.context_id
    updated['last_ms']=now
    updated['heartbeat_ms']=now
    receipt={'kind':'ai_position_review_observed','paper':True,
             'authority':'paper_reduce_only_opt_in',
             'context_id':request.context_id,'reviewed':result.reviewed,
             'created_ms':request.created_ms,'recorded_ms':now,
             'reviews':findings,'approved_symbols':list(approved),
             'automatic_actions':len(actions),
             'executed':actions,'deferred':deferred}
    events.append(receipt)
    quotes={sym:data.get('quote') for sym,data in markets.items()
            if isinstance(data,dict)}
    build_metrics(updated,events,now,wallet.spec,quotes,
                  wallet.protect_cfg,opening_allowed=False)
    # Critical: no side effects before this atomic ledger transaction.
    wallet.store.commit(updated,now,events)
    return {'status':'applied' if actions else 'observed',
            'reviews':findings,'automatic_actions':len(actions),
            'executed':actions,'deferred':deferred}
