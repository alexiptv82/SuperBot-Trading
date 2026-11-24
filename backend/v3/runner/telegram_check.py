"""Telegram per il Brain unico (procedura root): credenziali dei vecchi Falco/Toro e UNA notifica di prova.

1. ``TELEGRAM_BOT_TOKEN`` e ``TELEGRAM_CHAT_ID`` nel file d'ambiente del runner (``brain-ai.env``, letto da systemd).
2. Se mancano, si cercano nell'ambiente dei container gia' presenti sulla VPS (la web ``superbot`` e i vecchi desk
   ``superbot-desk-hawk`` / ``superbot-desk-bull``, dove le metteva il deploy dai Secret di GitHub) e si aggiungono al
   file, dopo una copia di riserva. Nessun valore viene MAI stampato o scritto altrove.
3. Una notifica di prova con lo stesso invio del Brain (``alerts.telegram_sender``): ``True`` solo se Telegram risponde 200.

Stampa solo ``TELEGRAM=...`` (ACCETTATO, NON_CONFIGURATO, NON_ACCETTATO) e la fonte. Uscita sempre 0: Telegram e' solo
informativo e non ferma la ripartenza.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
CONTAINERS = ("superbot", "superbot-desk-hawk", "superbot-desk-bull")
TEST_TEXT = "🧠 SuperBot · Brain unico PAPER: prova delle notifiche (solo informative, nessun comando)."


def read_env(path: Path) -> dict:
    out = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and k.strip() in KEYS:
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return {k: v for k, v in out.items() if v}


def from_container(name: str, docker: str = "docker") -> dict:
    try:
        p = subprocess.run([docker, "inspect", "--format", "{{json .Config.Env}}", name], capture_output=True,
                           text=True, timeout=20)
        env = json.loads(p.stdout) if p.returncode == 0 else []
    except Exception:
        return {}
    out = {}
    for item in env if isinstance(env, list) else []:
        k, sep, v = str(item).partition("=")
        if sep and k in KEYS and v:
            out[k] = v
    return out


def ensure(env_file: Path, *, docker: str = "docker") -> tuple[dict, str]:
    """(credenziali, fonte). Se il file non le ha ma un container si', le aggiunge al file (copia di riserva prima)."""
    found = read_env(env_file)
    if all(k in found for k in KEYS):
        return found, "file"
    for name in CONTAINERS:
        cand = from_container(name, docker)
        if all(k in cand for k in KEYS):
            if env_file.is_file():
                shutil.copy2(env_file, env_file.with_name(env_file.name + ".prima-telegram-"
                                                          + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())))
            text = env_file.read_text(encoding="utf-8") if env_file.is_file() else ""
            lines = [x for x in text.splitlines() if x.partition("=")[0].strip() not in KEYS]
            lines += [f"{k}={cand[k]}" for k in KEYS]
            with open(env_file, "w", encoding="utf-8") as f:     # stesso file: proprietario e permessi invariati
                f.write("\n".join(lines) + "\n")
            return cand, name
    return {}, "nessuna"


def main(argv=None, *, opener=None) -> int:
    ap = argparse.ArgumentParser(description="Telegram del Brain unico: credenziali e notifica di prova")
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--docker", default="docker")
    a = ap.parse_args(argv)
    from backend.v3.runner.alerts import telegram_sender
    creds, source = ensure(Path(a.env_file), docker=a.docker)
    if not creds:
        print("TELEGRAM=NON_CONFIGURATO fonte=nessuna")
        return 0
    ok = telegram_sender(creds, opener=opener)(TEST_TEXT)
    print(f"TELEGRAM={'ACCETTATO' if ok else 'NON_ACCETTATO'} fonte={source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
