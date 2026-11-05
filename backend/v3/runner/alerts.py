"""Invio degli avvisi del Brain PAPER su Telegram (stesso canale e stesse variabili d'ambiente dei bot classici).

Le chiavi ``TELEGRAM_BOT_TOKEN`` e ``TELEGRAM_CHAT_ID`` stanno SOLO nell'ambiente del container (regola 5 di
CLAUDE.md: mai nel codice). Se mancano, ``telegram_sender`` restituisce una funzione che non invia nulla e risponde
``False``: nessuna rete, nessun errore. L'invio e' best-effort: ``True`` solo se Telegram risponde 200; qualsiasi
eccezione diventa ``False`` e non ferma mai il Brain. Il testo e' scelto dal chiamante (solo percentuali e parole).
"""
from __future__ import annotations

import json
import urllib.request
from typing import Callable, Mapping, Optional

TIMEOUT_S = 8


def telegram_sender(env: Mapping[str, str], *, opener: Optional[Callable] = None) -> Callable[[str], bool]:
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    open_url = opener if opener is not None else urllib.request.urlopen
    if not token or not chat_id or type(token) is not str or type(chat_id) is not str:
        return lambda text: False

    def send(text: str) -> bool:
        if type(text) is not str or not text:
            return False
        try:
            body = json.dumps({"chat_id": chat_id, "text": text[:1000]}).encode("utf-8")
            req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body,
                                         headers={"Content-Type": "application/json"})
            with open_url(req, timeout=TIMEOUT_S) as resp:
                return getattr(resp, "status", None) == 200
        except Exception:
            return False

    return send
