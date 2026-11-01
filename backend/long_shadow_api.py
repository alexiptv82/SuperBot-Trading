"""Authenticated read-only LONG shadow endpoint. No broker/writer imports."""
import os

def register(app, require_session):
    from fastapi import Depends
    from fastapi.responses import JSONResponse
    from long_shadow_readonly import read_dashboard

    @app.get('/api/long/shadow')
    def long_shadow_status(session=Depends(require_session)):
        roots={
            'hawk':os.getenv('DESK_DATA_DIR','/opt/superbot-desk-data/hawk'),
            'bull':os.getenv('DESK_DATA_DIR_BULL','/opt/superbot-desk-data/bull'),
            'brain':os.getenv('LONG_SHADOW_BRAIN_DATA_DIR',
                              '/opt/superbot-desk-data/brain'),
        }
        return JSONResponse(read_dashboard(
            roots=roots,
            shadow_dir=os.getenv('LONG_SHADOW_OUTPUT_DIR',
                                 '/opt/superbot-long-shadow'),
            brain_source=os.getenv('LONG_SHADOW_BRAIN_SOURCE') or None,
        ), headers={'Cache-Control':'no-store'})
