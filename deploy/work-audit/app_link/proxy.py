"""Authenticated desk forwarding. The original authentication database stays local."""
import httpx
from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

PUBLIC_HEALTH = {'/api/desk/health', '/api/desk/bull/health'}


class DeskRemoteMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, base_url, token, authenticate, transport=None):
        super().__init__(app)
        if not token or len(token) < 32:
            raise ValueError('Missing internal authentication')
        url = httpx.URL(base_url)
        # Deployment uses a numeric, private Docker gateway address, never user input.
        import ipaddress
        if url.scheme != 'http' or not ipaddress.ip_address(url.host).is_private or url.path not in ('', '/'):
            raise ValueError('Invalid private API destination')
        self.base_url = str(url).rstrip('/')
        self.token, self.authenticate, self.transport = token, authenticate, transport

    async def dispatch(self, request, call_next):
        path = request.url.path
        if path != '/api/desk' and not path.startswith('/api/desk/'):
            return await call_next(request)
        if path not in PUBLIC_HEALTH or request.method != 'GET':
            try:
                await self.authenticate(authorization=request.headers.get('authorization'))
            except HTTPException as exc:
                return JSONResponse({'detail': exc.detail}, status_code=exc.status_code, headers=exc.headers)
        headers = {'X-Superbot-Gateway-Token': self.token}
        if request.headers.get('content-type'):
            headers['content-type'] = request.headers['content-type']
        # Never retry commands, forward bearer tokens, follow redirects, or fall back to old files.
        try:
            async with httpx.AsyncClient(transport=self.transport, trust_env=False,
                                        follow_redirects=False, timeout=httpx.Timeout(20, connect=3)) as client:
                reply = await client.request(request.method, self.base_url + path,
                    params=request.query_params.multi_items(), headers=headers, content=await request.body())
            if 300 <= reply.status_code < 400:
                return JSONResponse({'detail': 'Risposta Singapore non valida'}, status_code=502)
            return Response(reply.content, status_code=reply.status_code,
                headers={'content-type': reply.headers.get('content-type', 'application/json'),
                         'cache-control': 'no-store', 'x-superbot-desk-source': 'singapore'})
        except httpx.HTTPError:
            return JSONResponse({'detail': 'Collegamento Singapore temporaneamente non disponibile'},
                                status_code=503, headers={'cache-control': 'no-store'})
