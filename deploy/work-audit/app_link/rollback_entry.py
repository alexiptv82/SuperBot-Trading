"""Fallback: original authentication/API with desk endpoints explicitly unavailable."""
from backend.server import app
from starlette.responses import JSONResponse

@app.middleware('http')
async def unavailable_desk(request, call_next):
    if request.url.path == '/api/desk' or request.url.path.startswith('/api/desk/'):
        return JSONResponse({'detail': 'Collegamento Singapore in manutenzione'}, status_code=503,
                            headers={'cache-control': 'no-store'})
    return await call_next(request)
