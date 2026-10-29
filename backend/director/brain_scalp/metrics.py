"""Deterministic PAPER observability from one committed wallet tick.

Never infer closed P&L from running equity, never count aggregate close twice.
No network, DB queries, global clock or changes to trading decisions.
"""
from director.brain_free.execution import margin
from .engine import _safe_equity, _valid_quote


def build_metrics(state, events, now, spec, quotes, price_cfg, opening_allowed,
                  backward_clock_ms=0):
    previous=state.get('metrics') or {}
    counters=state.get('scalp_metrics_counters') or {}
    prev_ms=counters.get('ts_ms',state.get('verified_start_ms',now))
    elapsed=max(0,now-prev_ms)
    if counters.get('slots_used',0)==0:
        counters['zero_position_ms']=counters.get('zero_position_ms',0)+elapsed
    counters['ts_ms']=now
    counters['slots_used']=len(state['positions'])

    todays=int(state['daily']['utc'])
    if counters.get('trades_day_utc')!=todays:
        counters['trades_day_utc']=todays
        counters['trades_today']=0
    for ev in events:
        kind=ev.get('kind')
        if kind=='open':
            counters['trades_opened']=counters.get('trades_opened',0)+1
            counters['trades_today']+=1
            counters['fee_paid_usd']=counters.get('fee_paid_usd',0.)+ev.get('fee_paid',0.)
        elif kind in ('partial_trade','trade_closed'):
            # 'trade_closed' aggregate net includes earlier partial segments:
            # use this event's single settlement segment to avoid duplication.
            segment=ev.get('segment') or {}
            counters['pnl_realized_usd']=(
                counters.get('pnl_realized_usd',0.)+segment.get('net',0.))
            counters['fee_paid_usd']=(
                counters.get('fee_paid_usd',0.)+ev.get('fee_paid',0.))
            if kind=='trade_closed':
                counters['trades_closed']=counters.get('trades_closed',0)+1
                counters['closed_minutes_total']=(
                    counters.get('closed_minutes_total',0.)+
                    ev.get('duration_minutes',0.))
    state['scalp_metrics_counters']=counters

    equity,complete,_=_safe_equity(state,quotes)
    from director.brain_free.execution import fresh
    complete=(complete and all(fresh(quotes.get(sym),now,price_cfg)
                               for sym in state['positions']))
    m=margin(state)
    n=len(state['positions'])
    pending=sum(p['margin'] for p in state['plans'].values())
    # This is the gate for new admissions, not the answer to "can a slot be
    # filled right now" (cash, correlation, plan eligibility still apply).
    if state.get('paused'):
        reason='paused'
    elif state.get('daily_stop_triggered'):
        reason='daily_stop_latched'
    elif now//86400000!=state['daily']['utc']:
        reason='rollover_pending'
    elif not complete:
        reason='mark_missing_or_stale'
    elif equity<=spec.kill_equity:
        reason='kill_equity'
    elif backward_clock_ms>500:
        reason='backward_clock'
    elif not opening_allowed:
        reason='risk_or_market_gate'
    elif n>=spec.slots:
        reason='slots_full'
    else:
        reason=None
    result={
        'ts_ms':now,'opening_allowed':bool(opening_allowed and not state.get('paused')),
        'block_reason':reason,
        'slots_used':n,'slots_free':max(0,spec.slots-n),
        'pending_plans':len(state['plans']),
        'margin_used':m,
        'margin_available':max(0.,spec.max_margin_total-m-pending),
        'equity':equity if complete else None,
        'equity_complete':bool(complete),
        'pnl_realized_usd':counters.get('pnl_realized_usd',0.),
        'fee_paid_usd':counters.get('fee_paid_usd',0.),
        'trades_today':counters.get('trades_today',0),
        'trades_opened':counters.get('trades_opened',0),
        'trades_closed':counters.get('trades_closed',0),
        'long_count':sum(p['side']==1 for p in state['positions'].values()),
        'short_count':sum(p['side']==-1 for p in state['positions'].values()),
        'avg_duration_min':(
            counters.get('closed_minutes_total',0.)/counters['trades_closed']
            if counters.get('trades_closed',0) else 0.),
        'minutes_at_zero_positions':counters.get('zero_position_ms',0)/60000.,
        'daily_stop_triggered':bool(state.get('daily_stop_triggered')),
        'daily_day_utc':todays,
    }
    state['metrics']=result
    return result
