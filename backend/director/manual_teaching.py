"""Append-only operator teaching for *verified* PAPER manual closes.

No Telegram polling, no exchange reconciliation and absolutely no trade execution.
The engine must first persist a real PAPER close and then pass an attested event.
Disappearance from an external exchange is not proof of a PAPER close.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path

WINDOW_MS=5*60*1000
REPLY_MS=2*60*60*1000
VALID_BOTS={'hawk','bull','brain'}
VALID_DECISIONS={'yes','no','no_response'}


def _stamp(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _numeric(value,minimum=None):
    if type(value) not in (float,int) or not math.isfinite(value):
        raise ValueError('invalid_close_number')
    if minimum is not None and value < minimum:
        raise ValueError('invalid_close_number')
    return float(value)


def normalize_closed(event,verified=False):
    """Accept only events attested by a wallet AFTER a completed close.

    Never infer a user's intention from a disappeared position or a stop.
    """
    if verified is not True or not isinstance(event,dict):
        raise ValueError('unverified_manual_close')
    if (event.get('source')!='manual_user' or
        event.get('kind')!='trade_closed' or event.get('paper') is not True or
        event.get('bot') not in VALID_BOTS or
        type(event.get('position_id')) not in (int,str) or
        str(event['position_id']).strip()=='' or len(str(event['position_id']))>80):
        raise ValueError('not_manual_paper_close')
    sym=event.get('symbol')
    if not isinstance(sym,str) or not 1<=len(sym)<=24 or not sym.isascii() or not all(
        c.isupper() or c.isdigit() or c in '_-' for c in sym
    ):raise ValueError('invalid_symbol')
    if event.get('side') not in (1,-1) or type(event.get('side'))==bool:
        raise ValueError('invalid_side')
    entry=_numeric(event.get('entry'),1e-12)
    close_price=_numeric(event.get('close_price'),1e-12)
    leverage=_numeric(event.get('leverage'),1e-12)
    margin=_numeric(event.get('margin'),1e-12)
    net=_numeric(event.get('pnl_usd'))
    opened=event.get('open_ms')
    closed=event.get('close_ms')
    if type(opened)!=int or type(closed)!=int or opened<=0 or closed<opened:
        raise ValueError('invalid_close_time')
    account=str(event.get('account_id',''))
    if not account or len(account)>80:
        raise ValueError('invalid_close_account')
    unique=json.dumps([account,event['bot'],str(event['position_id']),closed,sym],
                      separators=(',',':'),allow_nan=False)
    eid=hashlib.sha256(unique.encode()).hexdigest()
    return {'event_id':eid,'ts':_stamp(closed),'bot':event['bot'],'account_id':account,
            'position_id':str(event['position_id']),'symbol':sym,
            'side':'LONG' if event['side']==1 else 'SHORT','leverage':leverage,
            'entry':entry,'close_price':close_price,'pnl_usd':net,
            'margin':margin,'pnl_pct_margin':round(net/margin*100,2),
            'duration_min':round((closed-opened)/60000,2),
            'open_ms':opened,'close_ms':closed,'source':'manual_user',
            'paper':True,'price_kind':'executed_paper'}


def batches(pending):
    """Group nearby pending closes; a group is *never* cross-acknowledged by mistake."""
    groups=[]
    for item in sorted(pending,key=lambda e:(e['close_ms'],e['bot'],e['event_id'])):
        if not groups or (item['close_ms']-groups[-1][0]['close_ms']>WINDOW_MS or
                          len(groups[-1])>=20):
            groups.append([])
        groups[-1].append(item)
    result=[]
    for group in groups:
        ids=[e['event_id'] for e in group]
        gid=hashlib.sha256(('|'.join(ids)).encode()).hexdigest()[:16]
        result.append({'group_id':gid,'ids':ids,'items':group})
    return result


def telegram_review(group):
    rows=group['items'];total=sum(x['pnl_usd'] for x in rows)
    labels='+'.join(sorted(set(x['bot'].upper() for x in rows)))
    if len(rows)==1:
        x=rows[0]
        content=f"{x['symbol']} {x['side']} {x['pnl_usd']:+.2f}$ ({x['pnl_pct_margin']:+.2f}% sul margine)"
    else:
        content='\n'.join(
            f"  {x['bot'].upper()} {x['symbol']} {x['side']} {x['pnl_usd']:+.2f}$"
            for x in rows
        )+f"\nTotale PAPER: {total:+.2f}$"
    return (f"[{labels}] 📋 {len(rows)} chiusure manuali PAPER verificate:\n"
            +content+f"\nConferma insegnamento: /insegna_si {group['group_id']}"
            +f" oppure /insegna_no {group['group_id']}")


class ManualLessons:
    """One writer per bot data directory. Every existing journal grows only."""
    def __init__(self,root):
        self.root=Path(root).absolute()
        if self.root.is_symlink():
            raise ValueError('unsafe_root')
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.journal=self.root/'manual_close_reviews.jsonl'
        self.learning=self.root/'learning_log.jsonl'
        self.lessons=self.root/'lessons.md'
        self.lock=self.root/'.manual_teaching.lock'

    @contextmanager
    def _locked(self):
        if any(p.is_symlink() for p in (self.journal,self.learning,self.lessons,self.lock)):
            raise ValueError('unsafe_file')
        with self.lock.open('a') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(f,fcntl.LOCK_UN)

    @staticmethod
    def _rows(path):
        if not path.exists():return []
        with path.open(encoding='utf-8') as f:
            return [json.loads(line) for line in f if line.strip()]

    @staticmethod
    def _append(path,obj):
        payload=json.dumps(obj,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n'
        if len(payload)>6000:raise ValueError('manual_event_too_large')
        fd=os.open(str(path),os.O_APPEND|os.O_CREAT|os.O_WRONLY,0o600)
        try:
            with os.fdopen(fd,'a',encoding='utf-8') as file:
                file.write(payload);file.flush();os.fsync(file.fileno())
        except Exception:raise

    def _state(self):
        pending={};resolved={}
        for r in self._rows(self.journal):
            if r.get('event')=='pending':
                pending[r['event_id']]=r['data']
            elif r.get('event')=='resolved':
                resolved[r['event_id']]=r['choice']
        return pending,resolved

    def register(self,event,*,verified=False):
        data=normalize_closed(event,verified)
        with self._locked():
            pending,resolved=self._state()
            if data['event_id'] in pending or data['event_id'] in resolved:
                return {'new':False,'event_id':data['event_id']}
            self._append(self.journal,{'event':'pending','event_id':data['event_id'],'data':data})
            return {'new':True,'event_id':data['event_id']}

    def pending(self):
        with self._locked():
            self._sync_exports()
            all_pending,resolved=self._state()
            return [e for eid,e in all_pending.items() if eid not in resolved]

    def _sync_exports(self):
        pending,resolved=self._state()
        existing={x.get('event_id') for x in self._rows(self.learning)}
        lesson_text=self.lessons.read_text(encoding='utf-8') if self.lessons.exists() else ''
        for eid,choice in resolved.items():
            if eid not in pending:raise ValueError('orphan_manual_resolution')
            data=pending[eid]
            intent=('profit_ok_free_slot' if choice=='yes' and data['pnl_usd']>0
                    else 'manual_close_other' if choice=='yes' else
                    'unknown' if choice=='no' else 'no_response')
            if eid not in existing:
                self._append(self.learning,{'schema':1,'ev':'manual_close',
                    **data,'user_intent':intent,'confirmed':choice=='yes',
                    'training_applied':False})
                existing.add(eid)
            marker='[manual-id:'+eid+']'
            if choice=='yes' and intent=='profit_ok_free_slot' and marker not in lesson_text:
                lesson=(f"\n{marker} [{data['ts'][:10]}] Chiusura manuale confermata "
                        f"{data['symbol']} {data['side']} {data['pnl_pct_margin']:+.1f}% "
                        f"sul margine ({data['duration_min']:.0f} min). "
                        "Intento dichiarato: incassare profitto e liberare slot. "
                        "Osservazione, non regola operativa.\n")
                fd=os.open(str(self.lessons),os.O_APPEND|os.O_CREAT|os.O_WRONLY,0o600)
                with os.fdopen(fd,'a',encoding='utf-8') as f:
                    f.write(lesson);f.flush();os.fsync(f.fileno())
                lesson_text+=lesson

    def decide(self,event_ids,choice,now_ms):
        if choice not in ('yes','no') or type(now_ms)!=int or now_ms<=0:
            raise ValueError('invalid_manual_decision')
        if not isinstance(event_ids,list) or not 1<=len(event_ids)<=20 or len(set(event_ids))!=len(event_ids):
            raise ValueError('invalid_manual_batch')
        with self._locked():
            pending,resolved=self._state()
            for eid in event_ids:
                if eid not in pending or eid in resolved:
                    raise ValueError('unavailable_manual_event')
                t=pending[eid]['close_ms']
                if not t<=now_ms<=t+REPLY_MS:
                    raise ValueError('manual_response_expired')
            for eid in event_ids:
                self._append(self.journal,{'event':'resolved','event_id':eid,
                                           'choice':choice,'at_ms':now_ms})
            self._sync_exports()
            return len(event_ids)

    def expire(self,now_ms):
        if type(now_ms)!=int or now_ms<=0:raise ValueError('invalid_time')
        with self._locked():
            pending,resolved=self._state()
            expired=[eid for eid,e in pending.items()
                     if eid not in resolved and now_ms>e['close_ms']+REPLY_MS]
            for eid in expired:
                self._append(self.journal,{'event':'resolved','event_id':eid,
                                           'choice':'no_response','at_ms':now_ms})
            self._sync_exports()
            return len(expired)


def parse_review_command(text,pending):
    """A no-ID /insegna_si is allowed only with exactly one pending group."""
    parts=str(text or '').strip().split()
    if not parts or parts[0] not in ('/insegna_si','/insegna_no') or len(parts)>2:
        raise ValueError('invalid_review_command')
    groups=batches(pending)
    matching=[g for g in groups if len(parts)==1 or g['group_id']==parts[1]]
    if len(matching)!=1:
        raise ValueError('ambiguous_or_missing_review')
    return ('yes' if parts[0]=='/insegna_si' else 'no'),matching[0]['ids']
