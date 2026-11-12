"""Configurazione comune dei test backend.

Barriera FAIL-CLOSED per i test di integrazione (marker ``integration``): parlano con un server vero, possono
inviare richieste operative (es. avvio del bot) e non fanno parte della suite offline. Vengono SALTATI salvo
opt-in esplicito verso un server EFFIMERO in locale:
    SUPERBOT_ALLOW_INTEGRATION=1  e  REACT_APP_BACKEND_URL con host 127.0.0.1 / localhost / ::1.
Una variabile ereditata per sbaglio (staging, VPS, qualunque host non locale) non puo' farli partire.
"""
import os
from urllib.parse import urlparse

import pytest

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def integration_allowed(environ=os.environ) -> tuple[bool, str]:
    """(consentito, motivo). Pura e senza rete: usata anche dal modulo di integrazione."""
    if environ.get("SUPERBOT_ALLOW_INTEGRATION") != "1":
        return False, "integrazione disabilitata (serve SUPERBOT_ALLOW_INTEGRATION=1 e un server locale effimero)"
    url = (environ.get("REACT_APP_BACKEND_URL") or "").strip()
    try:
        parsed = urlparse(url)
        host = parsed.hostname
    except ValueError:
        return False, "REACT_APP_BACKEND_URL non valido"
    if parsed.scheme not in ("http", "https") or host not in LOOPBACK_HOSTS:
        return False, "integrazione consentita solo verso un server locale (127.0.0.1/localhost): host rifiutato"
    return True, ""


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: richiede un server in esecuzione; fuori dalla suite offline, mai verso host non locali")


def pytest_collection_modifyitems(config, items):
    allowed, reason = integration_allowed()
    if allowed:
        return
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _desk_htf_isolation(monkeypatch):
    """RC84 fase 2: nessuna prova tocca la rete Bitget per le barre 4h/1d, e la cache delle barre native non passa da una
    prova all'altra. Lo storico paginato risponde "errore" (trend 1d UNKNOWN, che non blocca nulla) salvo che la prova
    lo sostituisca; le barre 4H arrivano da fetch_candles, che le prove gia' sostituiscono."""
    import sys
    cli = sys.modules.get("desk.cli")
    if cli is None or not hasattr(cli, "_HTF_CACHE"):
        yield
        return
    cli._HTF_CACHE.clear()
    cli.htf_budget_reset()
    monkeypatch.setattr(cli, "_bitget_rows", lambda *a, **k: None)    # history-candles: sempre "errore" offline
    yield
    cli._HTF_CACHE.clear()
