"""Local PAPER confirmation inbox. API only enqueues; wallet owner executes."""
import json
import sqlite3
from pathlib import Path
import re

class OperatorInbox:
    def __init__(self,path):
        path=Path(path)
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError('unsafe_operator_inbox')
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS commands (id TEXT PRIMARY KEY, created INTEGER, body TEXT, status TEXT, result TEXT)')
        self.db.commit()

    def submit_confirmation(self,request_id,group_id,choice,now):
        if (not isinstance(request_id,str) or not re.fullmatch(r'[a-f0-9]{32}',request_id)
                or not isinstance(group_id,str) or not re.fullmatch(r'[a-f0-9]{16}',group_id)
                or choice not in ('yes','no') or type(now) is not int or now<=0):
            raise ValueError('invalid_confirmation_request')
        body=json.dumps({'group_id':group_id,'choice':choice},sort_keys=True)
        with self.db:
            old=self.db.execute('SELECT body,status FROM commands WHERE id=?',(request_id,)).fetchone()
            if old:
                if old[0]!=body:raise ValueError('request_id_collision')
                return {'request_id':request_id,'status':old[1]}
            count=self.db.execute("SELECT COUNT(*) FROM commands WHERE status='pending'").fetchone()[0]
            if count>=100:raise ValueError('confirmation_queue_full')
            self.db.execute('INSERT INTO commands VALUES (?,?,?,?,?)',(request_id,now,body,'pending',None))
        return {'request_id':request_id,'status':'pending'}

    def consume(self,operator,now):
        # One wallet-owner process only. Claim BEFORE invoking any action.
        # An interrupted processing item stays uncertain, never re-executed.
        rows=self.db.execute("SELECT id,created,body FROM commands WHERE status='pending' ORDER BY created,id LIMIT 5").fetchall()
        outcomes=[]
        for ident,created,body in rows:
            with self.db:
                changed=self.db.execute("UPDATE commands SET status='processing' WHERE id=? AND status='pending'",(ident,)).rowcount
            if not changed:continue
            status='expired'
            if 0<=now-created<=120000:
                command=json.loads(body)
                verb='/insegna_si' if command['choice']=='yes' else '/insegna_no'
                try:
                    operator.confirm(verb+' '+command['group_id'],now)
                    status='confirmed'
                except Exception:
                    # Could have committed before exception; explicitly uncertain.
                    status='needs_reconciliation'
            with self.db:
                self.db.execute('UPDATE commands SET status=?,result=? WHERE id=?',
                                (status,json.dumps({'status':status}),ident))
            outcomes.append({'request_id':ident,'status':status})
        return outcomes

    def close(self):
        self.db.close()
