"""Scoped PAPER confirmations, physically separate from financial wallets."""
import json
from pathlib import Path
import re
import sqlite3

ACCOUNT=re.compile(r'desk-(hawk|bull)-paper-run-[1-9][0-9]*')
class ScopedConfirmations:
    def __init__(self,path):
        path=Path(path).absolute()
        if (not path.name.endswith('.confirmations.sqlite3') or
                any(p.is_symlink() for p in (path,*path.parents))):
            raise ValueError('unsafe_confirmation_path')
        self.db=sqlite3.connect(path,timeout=.1)
        self.db.execute('CREATE TABLE IF NOT EXISTS confirmations (id TEXT PRIMARY KEY, account TEXT, created INTEGER, body TEXT, status TEXT)')
        self.db.commit()

    def submit(self,ident,account,group,choice,now):
        if (not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{32}',ident)
            or not isinstance(account,str) or not ACCOUNT.fullmatch(account)
            or not isinstance(group,str) or not re.fullmatch(r'[a-f0-9]{16}',group)
            or choice not in ('yes','no') or type(now)!=int or now<=0):
            raise ValueError('invalid_confirmation')
        body=json.dumps({'group_id':group,'choice':choice},sort_keys=True)
        with self.db:
            old=self.db.execute('SELECT account,body,status FROM confirmations WHERE id=?',(ident,)).fetchone()
            if old:
                if old[:2]!=(account,body):raise ValueError('request_collision')
                return {'request_id':ident,'status':old[2]}
            if self.db.execute("SELECT COUNT(*) FROM confirmations WHERE status='pending'").fetchone()[0]>=100:
                raise ValueError('queue_full')
            self.db.execute('INSERT INTO confirmations VALUES (?,?,?,?,?)',(ident,account,now,body,'pending'))
        return {'request_id':ident,'status':'pending'}

    def consume(self,account,confirm,now):
        if not isinstance(account,str) or not ACCOUNT.fullmatch(account) or type(now)!=int or now<=0:
            raise ValueError('invalid_owner')
        outcomes=[]
        rows=self.db.execute("SELECT id,account,created,body FROM confirmations WHERE status='pending' ORDER BY created,id LIMIT 5").fetchall()
        for ident,scope,created,raw in rows:
            with self.db:
                claimed=self.db.execute("UPDATE confirmations SET status='processing' WHERE id=? AND status='pending'",(ident,)).rowcount
            if not claimed:continue
            status='expired'
            if scope!=account:status='rejected_account'
            elif 0<=now-created<=120000:
                try:
                    body=json.loads(raw)
                    confirm(('/insegna_si' if body['choice']=='yes' else '/insegna_no')+' '+body['group_id'],now)
                    status='confirmed'
                except Exception:
                    # Confirmation may have committed. Never replay automatically.
                    status='needs_reconciliation'
            with self.db:
                self.db.execute('UPDATE confirmations SET status=? WHERE id=?',(status,ident))
            outcomes.append({'request_id':ident,'status':status})
        return outcomes

    def result(self,ident):
        if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{32}',ident):
            raise ValueError('invalid_request_id')
        row=self.db.execute('SELECT status FROM confirmations WHERE id=?',(ident,)).fetchone()
        return None if row is None else {'request_id':ident,'status':row[0]}

    def close(self):self.db.close()

