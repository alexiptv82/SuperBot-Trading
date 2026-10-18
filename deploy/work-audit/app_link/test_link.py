import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from gateway import create_app
from proxy import DeskRemoteMiddleware

TOKEN = 'synthetic-gateway-test-token-' * 3


class LinkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dirs = {}
        for i, bot in enumerate(('hawk', 'bull')):
            p = Path(self.tmp.name)/bot
            p.mkdir()
            (p/'heartbeat.json').write_text(json.dumps({'ts':time.time(), 'exec_mode':'paper'}))
            (p/'state_v2.json').write_text(json.dumps({'main':{'positions':{},'equity':1000+i},'run_id':7+i}))
            (p/'trade_history.jsonl').write_text(json.dumps({'symbol':'BTC','net':2+i,'close_ms':1000})+'\n')
            (p/'ai_decisions.jsonl').write_text('{"memory":"preserve"}\n')
            self.dirs[bot]=str(p)
        async def ticker(s):
            return {'price':100,'symbol':s}
        self.gateway=create_app(TOKEN,self.dirs,ticker)
        self.auth_calls=[]
        async def auth(authorization=None):
            self.auth_calls.append(authorization)
            if authorization != 'Bearer synthetic-full-session':
                raise HTTPException(401,'Autenticazione richiesta')
        self.old=FastAPI()
        @self.old.get('/api/health')
        async def health(): return {'old_auth_preserved':True}
        @self.old.get('/api/desk/status')
        async def old_data(): return {'wrong_old_data':True}
        self.old.add_middleware(DeskRemoteMiddleware,base_url='http://172.17.0.1:18002',token=TOKEN,
            authenticate=auth,transport=httpx.ASGITransport(app=self.gateway))
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.old),base_url='http://test',
            headers={'Authorization':'Bearer synthetic-full-session'})

    async def asyncTearDown(self):
        await self.client.aclose()
        self.tmp.cleanup()

    async def test_auth_and_health_boundaries(self):
        c=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.old),base_url='http://test')
        async with c:
            self.assertEqual((await c.get('/api/desk/status')).status_code,401)
            self.assertEqual((await c.get('/api/desk/bull/status')).status_code,401)
            self.assertEqual((await c.post('/api/desk/health')).status_code,401)
            self.assertEqual((await c.get('/api/desk/health')).status_code,200)
            self.assertEqual((await c.get('/api/desk/bull/health')).status_code,200)
        self.assertTrue((await self.client.get('/api/health')).json()['old_auth_preserved'])

    async def test_all_read_routes_preserve_originals(self):
        before={str(p):p.read_bytes() for p in Path(self.tmp.name).rglob('*') if p.is_file()}
        for prefix in ['/api/desk','/api/desk/bull']:
            for route in ['status','trades','performance','diary','runs','logs','hours','health']:
                r=await self.client.get(prefix+'/'+route)
                self.assertEqual(r.status_code,200,(prefix,route,r.text))
                self.assertEqual(r.headers['x-superbot-desk-source'],'singapore')
        for route in ['prices','live/wallet','live/overview']:
            self.assertEqual((await self.client.get('/api/desk/'+route)).status_code,200)
        after={str(p):p.read_bytes() for p in Path(self.tmp.name).rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        self.assertEqual((await self.client.get('/api/desk/live/overview')).json()['mode'],'paper')

    async def test_commands_reach_only_selected_synthetic_directory(self):
        before=(Path(self.dirs['bull'])/'state_v2.json').read_bytes()
        r=await self.client.post('/api/desk/bull/pause')
        self.assertEqual(r.status_code,200)
        self.assertTrue((Path(self.dirs['bull'])/'pause.flag').exists())
        self.assertFalse((Path(self.dirs['hawk'])/'pause.flag').exists())
        self.assertEqual(before,(Path(self.dirs['bull'])/'state_v2.json').read_bytes())
        self.assertEqual((Path(self.dirs['bull'])/'ai_decisions.jsonl').read_text(),'{"memory":"preserve"}\n')

    async def test_offline_or_live_bot_rejects_commands(self):
        p=Path(self.dirs['hawk'])/'heartbeat.json'
        for hb in [{'ts':time.time()-1000,'exec_mode':'paper'},{'ts':time.time(),'exec_mode':'live'}]:
            p.write_text(json.dumps(hb))
            self.assertEqual((await self.client.post('/api/desk/pause')).status_code,409)
            self.assertFalse((p.parent/'pause.flag').exists())

    async def test_gateway_rejects_missing_and_wrong_secrets(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.gateway),base_url='http://test') as c:
            for headers in [{},{'X-Superbot-Gateway-Token':'bad'}]:
                self.assertEqual((await c.get('/api/desk/health',headers=headers)).status_code,401)

    async def test_bearer_not_forwarded_and_query_body_preserved(self):
        seen=[]
        async def target(request):
            seen.append(request)
            return httpx.Response(200,json={'ok':True})
        async def auth(authorization=None): pass
        app=FastAPI()
        app.add_middleware(DeskRemoteMiddleware,base_url='http://172.17.0.1:18002',token=TOKEN,
            authenticate=auth,transport=httpx.MockTransport(target))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            await c.post('/api/desk/close-position?limit=2',json={'symbol':'BTC'},
                headers={'Authorization':'Bearer DO-NOT-FORWARD','Cookie':'DO-NOT-FORWARD',
                         'X-Superbot-Gateway-Token':'ATTACKER'})
        request=seen[0]
        self.assertNotIn('authorization',request.headers)
        self.assertNotIn('cookie',request.headers)
        self.assertEqual(request.headers['x-superbot-gateway-token'],TOKEN)
        self.assertEqual(request.url.params['limit'],'2')
        self.assertEqual(json.loads(request.content),{'symbol':'BTC'})

    async def test_channel_failure_does_not_use_old_data_or_retry(self):
        calls=[]
        async def broken(request):
            calls.append(1)
            raise httpx.ConnectError('synthetic private detail',request=request)
        async def auth(authorization=None): pass
        app=FastAPI()
        @app.get('/api/desk/status')
        async def stale(): return {'old_data':True}
        app.add_middleware(DeskRemoteMiddleware,base_url='http://172.17.0.1:18002',token=TOKEN,
            authenticate=auth,transport=httpx.MockTransport(broken))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
            r=await c.get('/api/desk/status')
        self.assertEqual(r.status_code,503)
        self.assertNotIn('old_data',r.text)
        self.assertNotIn('private detail',r.text)
        self.assertEqual(len(calls),1)

if __name__=='__main__':
    unittest.main(verbosity=2)
