"""Authenticated classical teaching confirmations; no wallet or trading access."""
import json
import os
from pathlib import Path
import re
import time
from fastapi import Depends,HTTPException,Request
from director.scoped_confirmations import ScopedConfirmations

def register(app,require_session):
    def paths(portfolio):
        if portfolio not in ('hawk','bull'):raise HTTPException(404,'Portafoglio non valido')
        prefix='DESK_'+portfolio.upper()+'_OPERATOR_'
        return os.getenv(prefix+'REVIEWS_PATH'),os.getenv(prefix+'INBOX_PATH')

    def published(portfolio):
        source,_=paths(portfolio)
        if not source:return None
        try:
            path=Path(source)
            if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError()
            with path.open('rb') as f:raw=f.read(100001)
            if len(raw)>100000:raise ValueError()
            data=json.loads(raw);now=int(time.time()*1000)
            if (not isinstance(data,dict) or data.get('paper') is not True or
                not isinstance(data.get('account_id'),str) or
                not re.fullmatch('desk-'+portfolio+r'-paper-run-[1-9][0-9]*',data['account_id']) or
                type(data.get('ts_ms'))!=int or not 0<=now-data['ts_ms']<=120000 or
                not isinstance(data.get('groups'),list) or len(data['groups'])>10):
                raise ValueError()
            for g in data['groups']:
                if (not isinstance(g,dict) or not isinstance(g.get('group_id'),str) or
                    not re.fullmatch(r'[a-f0-9]{16}',g['group_id']) or
                    type(g.get('count'))!=int or not 1<=g['count']<=20 or
                    type(g.get('net_usd')) not in (int,float) or not -1e9<g['net_usd']<1e9 or
                    type(g.get('expires_ms'))!=int or g['expires_ms']<now or
                    not isinstance(g.get('symbols'),list) or len(g['symbols'])!=g['count'] or
                    any(not isinstance(s,str) or not re.fullmatch(r'[A-Z0-9_-]{1,24}',s) for s in g['symbols'])):
                    raise ValueError()
            return data
        except (OSError,ValueError,TypeError,KeyError):return None

    def queue(portfolio):
        _,path=paths(portfolio)
        if not path:raise HTTPException(503,'Conferme non configurate')
        try:return ScopedConfirmations(path)
        except (OSError,ValueError):raise HTTPException(503,'Coda non disponibile')

    @app.get('/api/desk/operator/{portfolio}/reviews')
    def reviews(portfolio:str,session=Depends(require_session)):
        data=published(portfolio)
        if data is None:return {'status':'unavailable','groups':[]}
        return {'status':'available','account_id':data['account_id'],'groups':data['groups']}

    @app.post('/api/desk/operator/{portfolio}/confirm')
    async def confirm(portfolio:str,request:Request,session=Depends(require_session)):
        paths(portfolio)
        origin=os.getenv('DESK_OPERATOR_ALLOWED_ORIGIN')
        if not origin or request.headers.get('origin')!=origin or request.headers.get('x-brain-operator')!='1':
            raise HTTPException(403,'Origine non autorizzata')
        raw=await request.body()
        if len(raw)>512:raise HTTPException(413,'Richiesta troppo grande')
        try:
            obj=json.loads(raw)
            if not isinstance(obj,dict) or set(obj)!={'request_id','account_id','group_id','choice'}:raise ValueError()
            data=published(portfolio)
            if data is None:raise HTTPException(503,'Esempi non disponibili')
            if obj['account_id']!=data['account_id'] or obj['group_id'] not in {g['group_id'] for g in data['groups']}:
                raise ValueError()
            q=queue(portfolio)
            try:return q.submit(obj['request_id'],obj['account_id'],obj['group_id'],obj['choice'],int(time.time()*1000))
            finally:q.close()
        except (ValueError,TypeError,KeyError):raise HTTPException(400,'Conferma non valida')

    @app.get('/api/desk/operator/{portfolio}/result/{request_id}')
    def result(portfolio:str,request_id:str,session=Depends(require_session)):
        q=queue(portfolio)
        try:
            try:row=q.result(request_id)
            except ValueError:raise HTTPException(400,'ID non valido')
            if row is None:raise HTTPException(404,'Richiesta non trovata')
            return row
        finally:q.close()

