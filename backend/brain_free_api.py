"""Only a session-authenticated GET; no account control or reset endpoint."""
import os

def register(app,require_session):
    from fastapi import Depends,Response
    from brain_free_view import read
    @app.get('/api/brain/free')
    def brain_free(response:Response,session=Depends(require_session)):
        response.headers['Cache-Control']='no-store'
        return read(os.getenv('BRAIN_FREE_DATA_DIR','/opt/superbot-brain-free'))
