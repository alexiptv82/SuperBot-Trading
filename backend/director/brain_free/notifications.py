"""Durable Telegram outbox; network latency never blocks account protection."""
import json,sqlite3,urllib.request
from concurrent.futures import ThreadPoolExecutor


def event_text(event):
    side='LONG' if event.get('side')==1 else 'SHORT'
    text=f"[BRAIN] {event['kind']} #{event.get('position_id','—')} {event.get('symbol','')} {side} · PAPER"
    if 'margin' in event:text+=f"\nMargine ${event['margin']:.2f} · leva {event.get('leverage',0):.2f}x"
    if 'qty' in event:text+=f" · quantità {event['qty']:.8g}"
    if 'notional' in event:text+=f" · esposizione ${event['notional']:.2f}"
    text+='\nMotivo: '+str(event.get('reason',''))
    if 'net' in event:text+=f"\nLordo ${event['gross']:.2f} · fee ${event['fees']:.2f} · funding ${event['funding']:.2f} · NETTO ${event['net']:.2f}"
    if event.get('adapted'):text+='\nSize/leva adattate ai vincoli fisici; proposta conservata nel registro.'
    return text

def send(token,chat,text,opener=urllib.request.urlopen):
    if not token or not chat:return False
    request=urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage',
       data=json.dumps({'chat_id':chat,'text':text[:4000]}).encode(),headers={'Content-Type':'application/json'})
    try:
        with opener(request,timeout=8) as r:return json.loads(r.read(100000)).get('ok') is True
    except Exception:return False

class Dispatcher:
    def __init__(self,root,token,chat,sender=send):
        self.path=str(root/'brain.sqlite3');self.token=token;self.chat=chat;self.sender=sender
        self.pool=ThreadPoolExecutor(1,thread_name_prefix='brain-free-telegram');self.pending=None;self.next_try=0
    def flush(self):
        # Separate connection, only outbox acknowledgments; never financial state.
        with sqlite3.connect(self.path,timeout=2) as db:
            for ident,body in db.execute('SELECT id,body FROM outbox WHERE sent=0 ORDER BY rowid LIMIT 10').fetchall():
                ok=self.sender(self.token,self.chat,body)
                db.execute('UPDATE outbox SET sent=?,attempts=attempts+1 WHERE id=?',(int(ok),ident));db.commit()
                if not ok:break
    def poll(self,now):
        if self.pending and self.pending.done():
            try:self.pending.result()
            except Exception:pass
            self.pending=None
        if self.pending is None and now>=self.next_try:
            self.next_try=now+10000;self.pending=self.pool.submit(self.flush)
    def close(self):self.pool.shutdown(wait=False,cancel_futures=True)
