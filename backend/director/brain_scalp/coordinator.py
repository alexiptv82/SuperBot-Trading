"""One market shortlist, two independent PAPER wallets. Explicit AI hand-off.

No model requests, API keys, runtime daemons or exchange orders here.
A supervisor must supply the identical market snapshot to both accounts.
"""
from pathlib import Path
import logging

_LOG=logging.getLogger(__name__)
from .engine import PaperWallet
from .scanner import scan
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

    def close(self):
        self.hawk.close()
        self.bull.close()

    def candidates(self,markets,now,limit=5):
        """Shared scanner. Result also explains each unselected symbol."""
        return scan(markets,now,limit=limit)

    def accept_ai_plans(self,wallet,raw,shortlist,markets,contracts,now):
        """Reject hallucinated or contradictory directions before slot reservation."""
        if wallet not in ('hawk','bull'): raise ValueError('unknown_wallet')
        if not isinstance(raw,dict) or not isinstance(raw.get('plans'),list):
            raise ValueError('model_response_wrong_schema')
        permitted={c['symbol']:c for c in shortlist.get('candidates',[])}
        if len(raw['plans'])>len(permitted): raise ValueError('too_many_model_plans')
        seen=set()
        result={'accepted':[],'rejected':[]}
        for item in raw['plans']:
            if not isinstance(item,dict):
                result['rejected'].append({'symbol':None,'why':'plan_not_object'})
                continue
            sym=item.get('symbol')
            if sym in seen:
                result['rejected'].append({'symbol':sym,'why':'duplicate_symbol'})
                continue
            seen.add(sym)
            candidate=permitted.get(sym)
            if candidate is None or item.get('side')!=candidate['side']:
                result['rejected'].append({'symbol':sym,'why':'not_a_matching_fresh_candidate'})
                continue
            try:
                plan=getattr(self,wallet).submit(item,now,contracts.keys(),
                                   {s:m['quote'] for s,m in markets.items() if m.get('quote')})
                result['accepted'].append({'symbol':sym,'plan_id':plan.plan_id})
            except (ValueError,KeyError,TypeError) as e:
                result['rejected'].append({'symbol':sym,'why':str(e)[:100]})
        return result

    def tick(self,markets,contracts,now):
        """One wallet error must never prevent protections in the other.

        A failed wallet gets a best-effort durable error event. The event
        contains a type, not potentially sensitive exception arguments.
        """
        results={}
        for name,wallet in (('hawk',self.hawk),('bull',self.bull)):
            try:
                results[name]=wallet.tick(markets,contracts,now)
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
        return results
