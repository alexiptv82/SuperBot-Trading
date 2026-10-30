"""Authenticated operator confirmations; never opens a wallet or runs trading."""
import json
import os
from pathlib import Path
import time
from fastapi import Depends,HTTPException,Request
from director.brain_scalp.operator_inbox import OperatorInbox

def register(app,require_session):
    def path():
        value=os.getenv('BRAIN_OPERATOR_INBOX_PATH')
        if not value:raise HTTPException(503,'Conferme non configurate')
        return value

    @app.get('/api/brain/operator/reviews')
    def reviews(session=Depends(require_session)):
        source=os.getenv('BRAIN_OPERATOR_REVIEWS_PATH')
        if not source:return {'status':'unavailable','groups':[]}
        try:
            p=Path(source)
            if p.is_symlink() or p.parent.is_symlink():raise ValueError()
            with p.open('rb') as f:raw=f.read(100001)
            if len(raw)>100000:raise ValueError()
            data=json.loads(raw)
            if not isinstance(data,dict):raise ValueError()
            now=int(time.time()*1000)
            if (data.get('paper') is not True or data.get('account_id')!='brain-scalp-single-paper'
                    or type(data.get('ts_ms')) is not int or not 0<=now-data['ts_ms']<=120000
                    or not isinstance(data.get('groups'),list) or len(data['groups'])>10):raise ValueError()
            return {'status':'available','groups':data['groups']}
        except (OSError,ValueError,TypeError,KeyError):
            return {'status':'unavailable','groups':[]}

    @app.post('/api/brain/operator/confirm')
    async def confirm(request:Request,session=Depends(require_session)):
        # Explicit same-origin policy, in addition to normal session auth.
        origin=os.getenv('BRAIN_OPERATOR_ALLOWED_ORIGIN')
        if (not origin or request.headers.get('origin')!=origin
                or request.headers.get('x-brain-operator')!='1'):
            raise HTTPException(403,'Origine non autorizzata')
        raw=await request.body()
        if len(raw)>512:raise HTTPException(413,'Richiesta troppo grande')
        try:
            obj=json.loads(raw)
            if not isinstance(obj,dict) or set(obj)!={'request_id','group_id','choice'}:
                raise ValueError()
            queue=OperatorInbox(path())
            try:
                return queue.submit_confirmation(obj['request_id'],obj['group_id'],
                    obj['choice'],int(time.time()*1000))
            finally:queue.close()
        except (ValueError,TypeError,KeyError):
            raise HTTPException(400,'Conferma non valida')

    @app.get('/api/brain/operator/result/{request_id}')
    def result(request_id:str,session=Depends(require_session)):
        import re
        if not re.fullmatch(r'[a-f0-9]{32}',request_id):raise HTTPException(400,'ID non valido')
        queue=OperatorInbox(path())
        try:
            row=queue.db.execute('SELECT status FROM commands WHERE id=?',(request_id,)).fetchone()
            if row is None:raise HTTPException(404,'Richiesta non trovata')
            return {'request_id':request_id,'status':row[0]}
        finally:queue.close()
