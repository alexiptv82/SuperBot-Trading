"""Authenticated read-only LONG shadow endpoint. No broker/writer imports."""
import os

def register(app, require_session):
    from fastapi import Depends
    from fastapi.responses import JSONResponse
    from long_shadow_readonly import read_dashboard

    @app.get('/api/long/shadow')
    def long_shadow_status(session=Depends(require_session)):
        brain_source=os.getenv('LONG_SHADOW_BRAIN_SOURCE') or None
        # Match the distinct authoritative readers already used by the app.
        # A missing source is NOT guessed: the wallet reader fails closed.
        if brain_source=='free':
            brain_root=os.getenv('BRAIN_FREE_DATA_DIR','/opt/superbot-brain-free')
        elif brain_source=='pilot':
            brain_root=os.getenv('BRAIN_DATA_DIR','/opt/superbot-desk-data/brain')
        else:
            brain_root='/nonexistent/long-shadow-brain-source-not-selected'
        roots={
            'hawk':os.getenv('DESK_DATA_DIR','/opt/superbot-desk-data/hawk'),
            'bull':os.getenv('DESK_DATA_DIR_BULL','/opt/superbot-desk-data/bull'),
            'brain':os.getenv('LONG_SHADOW_BRAIN_DATA_DIR',brain_root),
        }
        return JSONResponse(read_dashboard(
            roots=roots,
            shadow_dir=os.getenv('LONG_SHADOW_OUTPUT_DIR',
                                 '/opt/superbot-long-shadow'),
            brain_source=brain_source,
        ), headers={'Cache-Control':'no-store'})
