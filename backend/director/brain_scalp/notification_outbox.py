"""Durable owner-thread notification queue; HTTP runs only in a separate worker."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import urllib.error
import urllib.request

CODES={'balance':'credito insufficiente (saldo residuo non disponibile)',
       'auth':'accesso API non autorizzato','rate':'limite richieste raggiunto',
       'network':'rete o risposta non disponibile','http':'errore del provider',
       'truncated':'risposta incompleta','prompt_limit':'contesto oltre il limite',
       'invalid_response':'risposta non valida','unavailable':'provider non disponibile'}

def telegram_sender(token,chat_id,*,opener=urllib.request.urlopen):
    if not isinstance(token,str) or not token or not isinstance(chat_id,str) or not chat_id:
        raise ValueError('explicit_telegram_destination_required')
    def send(text):
        req=urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage',
            data=json.dumps({'chat_id':chat_id,'text':text}).encode(),
            headers={'Content-Type':'application/json'},method='POST')
        try:
            with opener(req,timeout=3) as response:data=json.loads(response.read(100001))
            if data.get('ok') is True and type((data.get('result') or {}).get('message_id'))==int:
                return 'delivered'
            return 'retry' if data.get('error_code')==429 else 'uncertain'
        except urllib.error.HTTPError as exc:
            return 'retry' if exc.code==429 else 'rejected' if exc.code in (400,401,403,404) else 'uncertain'
        except Exception:return 'uncertain'
    return send

class NotificationOutbox:
    def __init__(self,path,sender):
        path=Path(path).absolute()
        if (not path.name.endswith('.notifications.sqlite3') or
                any(p.is_symlink() for p in (path,*path.parents)) or not callable(sender)):
            raise ValueError('invalid_notification_config')
        lock_path=path.with_name(path.name+'.owner')
        if lock_path.is_symlink():raise ValueError('invalid_notification_config')
        self.owner=lock_path.open('a')
        try:
            fcntl.flock(self.owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.db=sqlite3.connect(path,timeout=.1)
            self.db.execute('CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, created INTEGER, text TEXT, status TEXT, tries INTEGER, due INTEGER)')
            # A previous process might have sent before losing the reply. No blind resend.
            self.db.execute("UPDATE notifications SET status='uncertain' WHERE status='inflight'")
            self.db.commit()
        except BaseException:
            if hasattr(self,'db'):self.db.close()
            self.owner.close()
            raise
        self.sender=sender;self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='brain-notify')
        self.future=None;self.current=None;self.closed=False

    def stage(self,attempt):
        if not isinstance(attempt,dict):return False
        provider=attempt.get('provider');code=attempt.get('failure_code');ts=attempt.get('ts_ms')
        if (provider not in ('deepseek','claude') or not isinstance(code,str) or
                code not in CODES or type(ts)!=int or not 0<ts<253402300800000):return False
        # One event per provider/cause/30-minute window, including across restart.
        ident=hashlib.sha256(f'{provider}:{code}:{ts//1800000}'.encode()).hexdigest()
        label='DeepSeek' if provider=='deepseek' else 'Claude'
        when=datetime.fromtimestamp(ts/1000,timezone.utc).strftime('%d/%m/%Y %H:%M UTC')
        text=f'[BRAIN] Analisi del {when}. {label}: {CODES[code]}. NO_TRADE da questa analisi. Le protezioni locali restano indipendenti dall’AI e richiedono dati di mercato aggiornati.'
        with self.db:
            if self.db.execute("SELECT COUNT(*) FROM notifications WHERE status IN ('pending','inflight')").fetchone()[0]>=100:
                return False
            return self.db.execute('INSERT OR IGNORE INTO notifications VALUES (?,?,?,?,?,?)',
                                   (ident,ts,text,'pending',0,ts)).rowcount==1

    def step(self,now):
        if self.closed:raise ValueError('notification_outbox_closed')
        if type(now)!=int or now<=0:raise ValueError('invalid_notification_clock')
        if self.future is not None:
            if not self.future.done():return 'sending'
            try:result=self.future.result()
            except Exception:result='uncertain'
            result=result if result in ('delivered','retry','rejected','uncertain') else 'uncertain'
            ident,tries=self.current
            status='pending' if result=='retry' and tries<3 else 'rejected' if result=='retry' else result
            with self.db:
                self.db.execute('UPDATE notifications SET status=?,due=? WHERE id=?',
                                (status,now+60000*tries,ident))
            self.future=None;self.current=None
            return result
        row=self.db.execute("SELECT id,text,tries FROM notifications WHERE status='pending' AND due<=? ORDER BY created LIMIT 1",(now,)).fetchone()
        if row is None:return 'idle'
        ident,text,tries=row
        with self.db:
            changed=self.db.execute("UPDATE notifications SET status='inflight',tries=tries+1 WHERE id=? AND status='pending'",(ident,)).rowcount
        if not changed:return 'idle'
        self.current=(ident,tries+1)
        try:self.future=self.pool.submit(self.sender,text)
        except Exception:
            with self.db:self.db.execute("UPDATE notifications SET status='uncertain' WHERE id=?",(ident,))
            self.current=None
            return 'uncertain'
        return 'sending'

    def close(self):
        if self.closed:return
        self.closed=True
        self.pool.shutdown(wait=False,cancel_futures=True)
        self.db.close()
        self.owner.close()
