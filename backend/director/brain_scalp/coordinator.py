"""One market shortlist, two independent PAPER wallets. Explicit AI hand-off.

No model requests, API keys, runtime daemons or exchange orders here.
A supervisor must supply the identical market snapshot to both accounts.
"""
from pathlib import Path
import logging
import math
from uuid import uuid4

_LOG=logging.getLogger(__name__)
from .engine import PaperWallet,PlanCostError,PlanGuardError
from .scanner import scan, _closed
from .gap_repair import repair_markets


class BrainPair:
    def __init__(self,base,initialize=False,now_ms=None,candle_backfill=None):
        self.candle_backfill=candle_backfill
        base=Path(base).absolute()
        self.hawk=PaperWallet(base/'hawk','hawk',initialize=initialize,now_ms=now_ms)
        try:
            self.bull=PaperWallet(base/'bull','bull',initialize=initialize,now_ms=now_ms)
        except BaseException:
            self.hawk.close()
            raise

    @property
    def wallets(self):
        return {'hawk':self.hawk,'bull':self.bull}

    def close(self):
        for wallet in self.wallets.values():wallet.close()

    def candidates(self,markets,now,limit=5):
        """Shared scanner. Result also explains each unselected symbol."""
        return scan(markets,now,limit=limit)

    def prepare_ai_request(self,wallet,shortlist,markets,contracts,references,
                           now,deadline_ms,trend_observations=None,regime_v11=None,market_advisory=None,operator_preferences=None):
        """Read one wallet on its owner thread; never merge profile balances."""
        import json
        from .ai_context import build_request
        if wallet not in self.wallets:raise ValueError('unknown_wallet')
        engine=self.wallets[wallet]
        state=engine.store.load()
        recent=[json.loads(row[0]) for row in engine.store.db.execute(
            "SELECT body FROM events WHERE kind='trade_closed' ORDER BY seq DESC LIMIT 10")]
        return build_request(state,engine.spec,markets,contracts,shortlist,
                             references,recent,now,deadline_ms,trend_observations,
                             regime_v11,market_advisory,operator_preferences)

    def accept_ai_analysis(self,wallet,request,analysis,markets,contracts,now):
        """Admit only completed, current analysis; never call an API in a tick."""
        from .ai_context import validate_current,decode
        from .ai_analysis import AIAnalysis,parse_reply,review_reasons
        if wallet not in self.wallets:raise ValueError('unknown_wallet')
        empty={'accepted':[],'rejected':[]}
        if not isinstance(analysis,AIAnalysis):
            return dict(empty,status='analysis_unavailable')
        if analysis.status!='ready':
            status=analysis.status if analysis.status in (
                'primary_failed','review_required','review_failed') else 'analysis_unavailable'
            return dict(empty,status=status)
        try:
            engine=self.wallets[wallet]
            payload=validate_current(request,engine.store.load(),engine.spec,now)
            if analysis.context_id!=request.context_id:raise ValueError('context_id_mismatch')
            first=parse_reply(analysis.primary_json,request)
            final=parse_reply(analysis.final_json,request)
            reasons=review_reasons(request,first)
            if reasons and not analysis.reviewed:
                return dict(empty,status='review_required')
            if tuple(analysis.review_reasons)!=reasons:
                raise ValueError('altered_analysis_review')
            if not analysis.reviewed and final!=first:
                raise ValueError('altered_analysis_selection')
            usage=decode(analysis.usage_json)
            safe_usage={}
            if isinstance(usage,dict):
                for provider in ('deepseek','claude'):
                    values=usage.get(provider)
                    if isinstance(values,dict):
                        safe_usage[provider]={k:v for k,v in values.items()
                            if k in ('prompt_tokens','completion_tokens','input_tokens',
                                     'output_tokens','prompt_cache_hit_tokens',
                                     'prompt_cache_miss_tokens') and type(v)==int and 0<=v<=10000000}
            audit={'context_id':request.context_id,
                   'provider':'claude' if analysis.reviewed else 'deepseek',
                   'reviewed':bool(analysis.reviewed),'created_ms':request.created_ms,
                   'completed_ms':now,'usage':safe_usage}
        except (ValueError,TypeError,KeyError,AttributeError):
            return dict(empty,status='rejected_context')
        result=self.accept_ai_plans(wallet,final,{'candidates':payload['candidates']},
                                    markets,contracts,now,context_audit=audit)
        result.update(status='processed',context_id=request.context_id,
                      reviewed=bool(analysis.reviewed),assessments=final['assessments'])
        return result

    def accept_ai_plans(self,wallet,raw,shortlist,markets,contracts,now,*,context_audit=None):
        """Admit independent AI proposals; mint all IDs and timestamps here.

        Untrusted plans cannot supply identity or clock. Invalid entries are
        rejected individually, without logging the raw model payload.
        Reservation, actual fill and protective exits remain PAPER-only.
        """
        if wallet not in self.wallets: raise ValueError('unknown_wallet')
        if context_audit is not None:
            # Only locally generated, bounded audit metadata may be persisted.
            from .ai_context import encode
            if (not isinstance(context_audit,dict) or
                    set(context_audit)!={'context_id','provider','reviewed','created_ms',
                                        'completed_ms','usage'} or
                    context_audit.get('provider') not in ('deepseek','claude') or
                    not isinstance(context_audit.get('context_id'),str) or
                    len(context_audit['context_id'])!=64 or
                    any(c not in '0123456789abcdef' for c in context_audit['context_id']) or
                    len(encode(context_audit))>2000):
                raise ValueError('invalid_context_audit')
            if (type(context_audit['reviewed'])!=bool or
                    context_audit['provider']!=('claude' if context_audit['reviewed'] else 'deepseek') or
                    type(context_audit['created_ms'])!=int or
                    type(context_audit['completed_ms'])!=int or
                    not 0<context_audit['created_ms']<=context_audit['completed_ms']==now or
                    not isinstance(context_audit['usage'],dict) or
                    any(p not in ('deepseek','claude') for p in context_audit['usage'])):
                raise ValueError('invalid_context_audit')
            for values in context_audit['usage'].values():
                if (not isinstance(values,dict) or any(
                        k not in ('prompt_tokens','completion_tokens','input_tokens','output_tokens',
                                  'prompt_cache_hit_tokens','prompt_cache_miss_tokens') or
                        type(v)!=int or not 0<=v<=10000000 for k,v in values.items())):
                    raise ValueError('invalid_context_audit')
        if not isinstance(raw,dict) or not isinstance(raw.get('plans'),list):
            raise ValueError('model_response_wrong_schema')
        proposals=raw['plans']
        # Bound work per response but keep independent valid prefix plans.
        # An oversized model response must not discard all valid proposals.
        skipped=max(0,len(proposals)-32)
        candidates=shortlist.get('candidates',[]) if isinstance(shortlist,dict) else []
        permitted={c['symbol']:c for c in candidates
                   if isinstance(c,dict) and isinstance(c.get('symbol'),str)
                   and c.get('side') in (-1,1)}
        seen=set()
        result={'accepted':[],'rejected':[]}
        audit=[]
        wallet_engine=self.wallets[wallet]
        quotes={sym:m.get('quote') for sym,m in markets.items()
                if isinstance(sym,str) and isinstance(m,dict)}
        for item in proposals[:32]:
            sym=item.get('symbol') if isinstance(item,dict) else None
            if not isinstance(sym,str):
                sym=None
                why='invalid_symbol_type' if isinstance(item,dict) else 'plan_not_object'
                result['rejected'].append({'symbol':None,'why':why})
                audit.append({'kind':'ai_plan_rejected','wallet':wallet,'why':why})
                continue
            side=item.get('side')
            if sym in seen:
                rejection={'symbol':sym,'why':'duplicate_symbol'}
            elif (isinstance(side,bool) or not isinstance(side,(float,int))
                  or not math.isfinite(side) or side not in (-1,1)
                  or sym not in permitted or side!=permitted[sym]['side']):
                rejection={'symbol':sym,'why':'not_a_matching_fresh_candidate'}
            else:
                try:
                    # The model may propose a TTL, but never an absolute
                    # timestamp, plan_id, or day-long replay of a stale plan.
                    if 'ttl_ms' in item:
                        ttl=item['ttl_ms']
                    elif 'created_ms' in item and 'expires_ms' in item:
                        ttl=item['expires_ms']-item['created_ms']
                    else:
                        ttl=120000
                    if (isinstance(ttl,bool) or not isinstance(ttl,(int,float))
                        or not math.isfinite(ttl) or ttl!=int(ttl)
                        or not 1000<=ttl<=wallet_engine.spec.max_plan_lifetime_ms):
                        raise ValueError('invalid_plan_ttl')
                    normalized=dict(item)
                    normalized['plan_id']=uuid4().hex
                    normalized['created_ms']=int(now)
                    normalized['expires_ms']=int(now)+int(ttl)
                    normalized.pop('ttl_ms',None)
                    plan=wallet_engine.submit(
                        normalized,now,contracts.keys(),quotes)
                    result['accepted'].append({'symbol':sym,'plan_id':plan.plan_id,
                                               'margin':plan.margin,'leverage':plan.leverage})
                    seen.add(sym)
                    continue
                except (ValueError,KeyError,TypeError,OverflowError) as e:
                    rejection={'symbol':sym,'why':str(e)[:100]}
                    if isinstance(e,(PlanCostError,PlanGuardError)):
                        rejection.update(e.details)
            result['rejected'].append(rejection)
            audit.append({'kind':'ai_plan_rejected','wallet':wallet,
                          'symbol':sym,'why':rejection['why']})
        rejected_count=len(result['rejected'])+skipped
        if skipped:
            result['rejected'].append({'symbol':None,
                                       'why':'model_response_plan_limit',
                                       'skipped_count':skipped})
            audit.append({'kind':'ai_plans_truncated','wallet':wallet,
                          'skipped_count':skipped})
        audit.append({'kind':'ai_response_processed','wallet':wallet,
                      'accepted':len(result['accepted']),
                      'rejected':rejected_count,'skipped':skipped})
        # Keep a bounded durable summary, but never journal untrusted raw text.
        state=wallet_engine.store.load()
        if context_audit is not None:
            state['last_ai_context_id']=context_audit['context_id']
            audit.append({'kind':'ai_context_processed',**context_audit,
                          'accepted':len(result['accepted']),
                          'rejected':rejected_count})
        wallet_engine.store.commit(state,max(int(now),state['last_ms']),audit)
        return result

    def tick_with_backfill(self,markets,contracts,now,fetch_missing):
        """Offline injected backfill provider. Never silently clear unresolved gaps."""
        repaired={}
        for symbol,market in markets.items():
            entry=dict(market)
            bars=dict(entry.get('bars') or {})
            series=list(bars.get('1m') or [])
            if series:
                start=min(series,key=lambda x:x[0])[0]
                end=max(series,key=lambda x:x[0])[0]
                by_start={row[0]:row for row in series}
                missing=[ts for ts in range(start,end+60000,60000) if ts not in by_start]
                if missing:
                    try:
                        supplied=fetch_missing(symbol,missing)
                        for row in supplied:
                            if row[0] in missing and len(row)>=6:
                                by_start[row[0]]=row
                        if all(ts in by_start for ts in missing):
                            bars['1m']=[by_start[ts] for ts in sorted(by_start)]
                            entry['bars']=bars
                            _LOG.info('gap_backfilled %s %s',symbol,len(missing))
                        else:
                            _LOG.warning('gap_unresolvable %s',symbol)
                    except Exception:
                        _LOG.exception('gap_backfill_failed %s',symbol)
            repaired[symbol]=entry
        return self.tick(repaired,contracts,now)

    def tick(self,markets,contracts,now):
        """One wallet error must never prevent protections in the other.

        A failed wallet gets a best-effort durable error event. The event
        contains a type, not potentially sensitive exception arguments.
        """
        results={}
        anchors={}
        quarantined=set()
        quarantined_with_positions=set()
        for wallet in self.wallets.values():
            try:
                existing=wallet.store.load()
                quarantined.update(existing.get('coverage_gaps',[]))
                for symbol,position in existing['positions'].items():
                    ts=position['last_bar_ms']
                    anchors[symbol]=min(anchors.get(symbol,ts),ts)
                    if 'scalp_gap_cursor_ms' in position:
                        quarantined.add(symbol)
                        quarantined_with_positions.add(symbol)
            except Exception:
                _LOG.exception('Cannot load cursor for gap repair')
        repaired,gap_events=repair_markets(
            markets,now,fetcher=self.candle_backfill,anchors=anchors)
        # A live feed may already contain all the previously missing candles.
        # Do NOT clear the quarantine here: merely request a replay in each
        # affected wallet. The wallet checks continuous historical coverage
        # AFTER running protect() and only then clears its own gap flag.
        unresolved_symbols={e['symbol'] for e in gap_events
                            if e['kind'] in ('gap_unresolvable','gap_backfill_failed')}
        backfilled_symbols={e['symbol'] for e in gap_events
                            if e['kind']=='gap_backfilled'}
        for symbol in sorted(quarantined-unresolved_symbols-backfilled_symbols):
            data=repaired.get(symbol)
            if not isinstance(data,dict):
                continue
            if symbol in quarantined_with_positions:
                # Position recovery is verified in-engine against its exact
                # cursor; never release it on the supervisor's word alone.
                gap_events.append({'kind':'gap_history_complete','symbol':symbol})
                continue
            # A flat wallet has no stop exposure to old unavailable minutes.
            # Still demand a fully continuous recent scanner window before
            # re-enabling fresh plans; never clear on an empty/partial feed.
            bars=data.get('bars') or {}
            one=_closed(bars.get('1m',[]),now,60000,18)
            five=_closed(bars.get('5m',[]),now,300000,22)
            if (one and five and now-(one[-1][0]+60000)<=90000
                    and now-(five[-1][0]+300000)<=360000):
                gap_events.append({'kind':'gap_history_complete','symbol':symbol})
        # An unresolved historical minute is an unknown stop/target event.
        # Never let the shared protector advance past that minute. Keep only
        # the *contiguous* closed-bar prefix following the stored cursor.
        unresolved={e['symbol'] for e in gap_events
                    if e['kind'] in ('gap_unresolvable','gap_backfill_failed')}
        for symbol in unresolved:
            data=repaired.get(symbol)
            if not isinstance(data,dict):
                continue
            source=(data.get('bars') or {}).get('1m',[])
            anchor=anchors.get(symbol)
            kept=[]
            if anchor is not None:
                expected=anchor+60000
                try:
                    for row in sorted(source,key=lambda row:row[0]):
                        if row[0]<expected:
                            continue
                        if (row[0]!=expected or row[0]+60000>now or
                            len(row)<6):
                            break
                        kept.append(row)
                        expected+=60000
                except (TypeError,ValueError,IndexError,KeyError):
                    kept=[]
            cleaned=dict(data)
            cleaned['bars']=dict(data.get('bars') or {})
            cleaned['bars']['1m']=kept
            repaired[symbol]=cleaned
        for name,wallet in self.wallets.items():
            try:
                results[name]=wallet.tick(repaired,contracts,now,market_events=gap_events)
            except Exception as error:
                _LOG.exception('Brain Scalp wallet tick failed: %s',name)
                event={'kind':'wallet_tick_error','wallet':name,
                       'error_type':type(error).__name__}
                try:
                    state=wallet.store.load()
                    wallet.store.commit(state,max(int(now),state['last_ms']),[event])
                    persisted=True
                except Exception:
                    _LOG.exception('Failed to persist wallet error: %s',name)
                    persisted=False
                results[name]={'status':'error','wallet':name,
                               'error_type':type(error).__name__,
                               'event_persisted':persisted,'events':[event]}
        results['market_events']=gap_events
        return results


class BrainAccount(BrainPair):
    """One isolated PAPER account, reusing all dual coordinator protections.

    Caller must supply its complete mandate. This never imports, sums, resets
    or migrates existing wallets, and cannot start a service by itself.
    """
    def __init__(self,base,*,spec,initialize=False,now_ms=None,candle_backfill=None):
        from .config import validate_spec
        validate_spec(spec)
        if spec.name!='brain' or spec.account_id!='brain-scalp-single-paper':
            raise ValueError('single_account_identity_required')
        self.candle_backfill=candle_backfill
        self.brain=PaperWallet(Path(base).absolute()/'brain','brain',
                               initialize=initialize,now_ms=now_ms,spec=spec)

    @property
    def wallets(self):
        return {'brain':self.brain}

