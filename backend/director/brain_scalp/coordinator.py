"""One market shortlist, two independent PAPER wallets. Explicit AI hand-off.

No model requests, API keys, runtime daemons or exchange orders here.
A supervisor must supply the identical market snapshot to both accounts.
"""
from pathlib import Path
import logging

_LOG=logging.getLogger(__name__)
from .engine import PaperWallet,PlanCostError
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
                rejected={'symbol':sym,'why':str(e)[:100]}
                if isinstance(e,PlanCostError):
                    rejected.update(e.details)
                result['rejected'].append(rejected)
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
        for wallet in (self.hawk,self.bull):
            try:
                for symbol,position in wallet.store.load()['positions'].items():
                    ts=position['last_bar_ms']
                    anchors[symbol]=min(anchors.get(symbol,ts),ts)
                    if 'scalp_gap_cursor_ms' in position:
                        quarantined.add(symbol)
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
            if symbol in repaired:
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
        for name,wallet in (('hawk',self.hawk),('bull',self.bull)):
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
