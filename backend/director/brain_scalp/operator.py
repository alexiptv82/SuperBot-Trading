"""Verified operator PAPER closes for a single Brain Scalp account.

ONLY the wallet owner thread may invoke this. No Telegram network, file flags,
orders, Bitget account access, or live position reconciliation. All close-all
entries settle in one SQLite commit or none settle.
"""
from copy import deepcopy
import json

from director.brain_free.execution import close as settle_paper,fresh
from director.manual_teaching import ManualLessons,batches,telegram_review,parse_review_command
from .metrics import build_metrics


class BrainOperator:
    def __init__(self,account):
        if set(account.wallets)!={'brain'}:
            raise ValueError('operator_single_brain_only')
        self.account=account
        self.wallet=account.brain
        self.teaching=ManualLessons(self.wallet.store.root)

    def sync(self):
        """Recover teaching inbox if crash occurs after authoritative close."""
        rows=self.wallet.store.db.execute(
            "SELECT body FROM events WHERE kind='trade_closed' ORDER BY seq").fetchall()
        recovered=0
        for row in rows:
            payload=json.loads(row[0])
            if payload.get('source')=='manual_user' and payload.get('paper') is True:
                recovered+=int(self.teaching.register(payload,verified=True)['new'])
        return recovered

    def close(self,position_ids,markets,now,*,reason='profit_ok_free_slot'):
        """Portfolio explicit; position IDs protect against stale symbol requests.

        Every quote must be fresh within the strict 3-second admission window,
        and every requested position must be present with the matching ID.
        No partial execution when a close-all batch has any stale quote.
        """
        if (type(now)!=int or now<=0 or
            reason not in ('profit_ok_free_slot','manual_other') or
            not isinstance(position_ids,dict) or not position_ids or
            not isinstance(markets,dict) or len(position_ids)>self.wallet.spec.slots):
            raise ValueError('invalid_operator_close_request')
        store=self.wallet.store
        before=store.load()
        if now<before['last_ms']:
            raise ValueError('backward_operator_clock')
        pending=before['positions']
        if any(sym not in pending or
               str(pending[sym]['id'])!=str(ident) or
               type(ident) not in (str,int)
               for sym,ident in position_ids.items()):
            raise ValueError('stale_position_id')
        quotes={}
        for sym in position_ids:
            q=(markets.get(sym) or {}).get('quote')
            if not fresh(q,now,self.wallet.entry_cfg):
                raise ValueError('stale_operator_quote')
            quotes[sym]=q
        updated=deepcopy(before)
        events=[]
        for sym in sorted(position_ids):
            event=settle_paper(updated,sym,quotes[sym]['price'],now,
                               'USER:'+reason,cfg=self.wallet.cfg)
            if event.get('kind')!='trade_closed':
                raise ValueError('not_fully_closed')
            event.update({
                'source':'manual_user','paper':True,'bot':'brain',
                'account_id':self.wallet.spec.account_id,
                'pnl_usd':event['net'],
                'close_price':event['segment']['exit'],
                'user_requested_reason':reason,
            })
            updated['plans'].pop(sym,None)
            events.append(event)
        updated['last_ms']=now
        updated['heartbeat_ms']=now
        # A later protective tick recalculates risk/daily rollover. Until then
        # mark new opening as guarded and publish a consistent closed ledger.
        build_metrics(updated,events,now,self.wallet.spec,quotes,
                      self.wallet.protect_cfg,opening_allowed=False)
        store.commit(updated,now,events)
        # A crash now cannot lose the event: SQLite is authoritative. Replay
        # via sync() will recreate missing prompts without reopening trades.
        teaching_status='recorded'
        try:
            self.sync()
        except Exception:
            # Financial commit is authoritative. Never report a completed
            # close as failed merely because the observational inbox is down.
            # sync() reconstructs it from SQLite after storage is repaired.
            teaching_status='pending_recovery'
        return {'teaching_status':teaching_status,'paper':True,'closed':[e['symbol'] for e in events],
                'net_usd':sum(e['pnl_usd'] for e in events),
                'position_ids':{e['symbol']:str(e['position_id']) for e in events}}

    def pending_reviews(self):
        self.sync()
        return batches(self.teaching.pending())

    def review_messages(self):
        return [telegram_review(g) for g in self.pending_reviews()]

    def confirm(self,message,now):
        self.sync()
        choice,ids=parse_review_command(message,self.teaching.pending())
        return self.teaching.decide(ids,choice,now)

    def expire(self,now):
        self.sync()
        return self.teaching.expire(now)
