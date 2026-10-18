"""Only the existing API is imported: no additional engine or Telegram listener."""
import os
from pathlib import Path

if os.environ.get('DESK_MODE') != 'paper':
    raise RuntimeError('App link requires PAPER')

from backend.server import app, require_session
from .proxy import DeskRemoteMiddleware

app.add_middleware(DeskRemoteMiddleware,
    base_url=os.environ['DESK_REMOTE_BASE_URL'],
    token=Path('/app/app_link/gateway.token').read_text().strip(),
    authenticate=require_session)
