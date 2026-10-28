"""GET-only authenticated Brain Scalp dashboard API. No wallet mutations."""
import os


def register(app,require_session):
    from fastapi import Depends,Response
    from brain_scalp_view import read_all

    @app.get('/api/brain/scalp')
    def scalp_status(response:Response,session=Depends(require_session)):
        response.headers['Cache-Control']='no-store'
        return read_all(os.getenv('BRAIN_SCALP_DATA_DIR','/opt/superbot-brain-scalp'))
