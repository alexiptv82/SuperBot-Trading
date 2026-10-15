"""Orari di trading: il bot apre nuove posizioni SOLO nelle fasce scelte dall'utente.

Funziona come il tasto Pausa, ma da solo e a orario:
- FUORI dalle fasce: nessuna nuova apertura, nessun DCA, nessuna seconda gamba. Le posizioni gia' aperte
  continuano a essere gestite (stop, take profit, uscite) e si chiudono da sole, come in pausa. Senza posizioni
  il bot sta fermo (nessuna chiamata a Claude, nessun costo).
- DENTRO le fasce: lavora come sempre.
- Puo' solo RESTRINGERE: se l'utente ha premuto Pausa, la pausa vince anche dentro le fasce. Non accende mai nulla.
- SPENTO DI DEFAULT: senza il file `trading_hours.json` (o con "enabled": false) non cambia nulla. Lo attiva solo
  l'utente, dall'app (Impostazioni).

File `trading_hours.json` nella cartella dati del bot:
  {"enabled": true, "tz": "Europe/Rome",
   "windows": [{"days": [0,1,2,3,4], "start": "08:00", "end": "22:00"}, {"start": "22:00", "end": "02:00"}]}
- tz: "Europe/Rome" (ora italiana/svizzera, con ora legale) oppure "UTC";
- days: giorni in cui la fascia INIZIA (0=lunedi ... 6=domenica); se manca vale tutti i giorni;
- se `end` e' uguale o prima di `start` la fascia finisce il giorno dopo; "24:00" = fine giornata.

File rovinato: se c'e' un orario valido letto prima resta quello (e l'errore e' segnalato); se non c'e', per
prudenza le NUOVE aperture restano sospese (mai il contrario: un errore non deve far operare fuori orario).
Il bot non ha tzdata: l'ora legale europea e' calcolata a mano.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

HOURS_FILE = "trading_hours.json"
TZ_OPTIONS = ("Europe/Rome", "UTC")
MAX_WINDOWS = 14
DAY_MIN = 1440
_HM = re.compile(r"^(\d{2}):(\d{2})$")

_CACHE: dict = {"path": None, "cfg": None, "error": ""}   # ultimo orario valido letto (per i file rovinati)


# ---------------------------------------------------------------- ora legale europea (senza librerie di fusi)
def _last_sunday(year: int, month: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def rome_offset_min(utc_dt: datetime) -> int:
    """+120 (CEST) dall'ultima domenica di marzo alle 01:00 UTC all'ultima di ottobre alle 01:00 UTC, altrimenti +60."""
    y = utc_dt.year
    start = datetime(y, 3, _last_sunday(y, 3).day, 1, 0, tzinfo=timezone.utc)
    end = datetime(y, 10, _last_sunday(y, 10).day, 1, 0, tzinfo=timezone.utc)
    return 120 if start <= utc_dt < end else 60


def _offset_min(tz: str, utc_dt: datetime) -> int:
    return rome_offset_min(utc_dt) if tz == "Europe/Rome" else 0


# ---------------------------------------------------------------- lettura e controllo del file
def _hm_to_min(s, allow_24: bool = False) -> int:
    m = _HM.match(str(s or ""))
    if not m:
        raise ValueError(f"orario non valido: {s!r} (formato HH:MM)")
    h, mi = int(m.group(1)), int(m.group(2))
    if (h == 24 and mi == 0 and allow_24) or (0 <= h <= 23 and 0 <= mi <= 59):
        return h * 60 + mi
    raise ValueError(f"orario non valido: {s!r}")


def parse(obj) -> tuple:
    """-> (config, errore). config = {"enabled", "tz", "windows":[{"days":[..],"start":min,"end":min,"start_hm","end_hm"}]}.
    Con "enabled": false il resto non si controlla (e' spento)."""
    if not isinstance(obj, dict):
        return None, "il file non e' un oggetto JSON"
    enabled = obj.get("enabled") is True
    if not enabled:
        return {"enabled": False, "tz": "Europe/Rome", "windows": []}, ""
    tz = obj.get("tz", "Europe/Rome")
    if tz not in TZ_OPTIONS:
        return None, f"fuso non valido: {tz!r} (ammessi: {', '.join(TZ_OPTIONS)})"
    raw = obj.get("windows")
    if not isinstance(raw, list) or not raw:
        return None, "attivo ma senza nessuna fascia oraria"
    if len(raw) > MAX_WINDOWS:
        return None, f"troppe fasce (massimo {MAX_WINDOWS})"
    wins = []
    for i, w in enumerate(raw, 1):
        try:
            if not isinstance(w, dict):
                raise ValueError("la fascia non e' un oggetto")
            s, e = _hm_to_min(w.get("start")), _hm_to_min(w.get("end"), allow_24=True)
            if s == e:
                raise ValueError("inizio e fine uguali (per tutto il giorno usa 00:00 - 24:00)")
            days = w.get("days", list(range(7)))
            if (not isinstance(days, list) or not days
                    or any(isinstance(d, bool) or not isinstance(d, int) or not 0 <= d <= 6 for d in days)):
                raise ValueError("giorni non validi (numeri da 0=lunedi a 6=domenica)")
            wins.append({"days": sorted(set(days)), "start": s, "end": e,
                         "start_hm": f"{s // 60:02d}:{s % 60:02d}", "end_hm": f"{e // 60:02d}:{e % 60:02d}"})
        except ValueError as ex:
            return None, f"fascia {i}: {ex}"
    return {"enabled": True, "tz": tz, "windows": wins}, ""


def _load(data_dir: str) -> None:
    """Rilegge il file a ogni chiamata (e' di poche righe: costa nulla ed e' impossibile restare con un valore
    vecchio, anche se l'app lo riscrive due volte nello stesso istante)."""
    path = os.path.join(data_dir, HOURS_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            cfg, err = parse(json.load(fh))
    except FileNotFoundError:
        _CACHE.update(path=path, cfg=None, error="")                 # nessun file = spento
        return
    except (OSError, ValueError) as ex:
        cfg, err = None, f"file illeggibile ({type(ex).__name__})"
    if err:
        keep = _CACHE["path"] == path and _CACHE["cfg"] is not None  # resta l'ultimo orario valido, se c'e'
        _CACHE.update(path=path, error=err, cfg=_CACHE["cfg"] if keep else None)
        return
    _CACHE.update(path=path, cfg=cfg, error="")


# ---------------------------------------------------------------- calcolo del momento
def _allowed_at(cfg: dict, utc_dt: datetime) -> bool:
    off = _offset_min(cfg["tz"], utc_dt)
    local = utc_dt + timedelta(minutes=off)
    minute = local.hour * 60 + local.minute
    for w in cfg["windows"]:
        end_eff = w["end"] if w["end"] > w["start"] else w["end"] + DAY_MIN
        for back in (0, 1):                      # la fascia di oggi e quella iniziata ieri che passa la mezzanotte
            if (local.weekday() - back) % 7 in w["days"] and w["start"] <= minute + back * DAY_MIN < end_eff:
                return True
    return False


def _boundaries(cfg: dict, now_ms: int) -> list:
    """Istanti (UTC, ms) di inizio e fine fascia dei prossimi giorni, in ordine."""
    out = []
    now = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
    base = (now + timedelta(minutes=_offset_min(cfg["tz"], now))).date()
    for d in range(-1, 9):
        day = base + timedelta(days=d)
        for w in cfg["windows"]:
            if day.weekday() not in w["days"]:
                continue
            for mins in (w["start"], w["end"] if w["end"] > w["start"] else w["end"] + DAY_MIN):
                local = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(minutes=mins)
                guess = local - timedelta(minutes=_offset_min(cfg["tz"], local - timedelta(minutes=60)))
                out.append(int(guess.timestamp() * 1000))
    return sorted(set(out))


def hours_state(data_dir: str, now_ms: int) -> dict:
    """Situazione adesso. NON SOLLEVA MAI.
    mode: off (spento o nessun file) | on (attivo, file valido) | invalid (file rovinato e nessun orario valido: sospeso)
    blocked = True quando in questo momento NON si aprono nuove posizioni."""
    out = {"mode": "off", "enabled": False, "allowed": True, "blocked": False, "tz": None, "windows": [],
           "next_change_ms": None, "error": ""}
    try:
        _load(data_dir)
        out["error"] = _CACHE["error"]
        cfg = _CACHE["cfg"]
        if cfg is None:
            if _CACHE["error"]:            # il file c'e' ma non si capisce: per prudenza niente nuove aperture
                out.update(mode="invalid", enabled=True, allowed=False, blocked=True)
            return out
        if not cfg["enabled"]:
            return out
        now = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
        allowed = _allowed_at(cfg, now)
        nxt = None
        for t in _boundaries(cfg, now_ms):
            if t > now_ms and _allowed_at(cfg, datetime.fromtimestamp(t / 1000, tz=timezone.utc)) != allowed:
                nxt = t
                break
        out.update(mode="on", enabled=True, allowed=allowed, blocked=not allowed, tz=cfg["tz"], next_change_ms=nxt,
                   windows=[{k: w[k] for k in ("days", "start_hm", "end_hm")} for w in cfg["windows"]])
    except Exception as ex:                # un errore qui non deve mai fermare il bot ne' farlo operare fuori orario
        out.update(error=f"errore interno ({type(ex).__name__})")
        if _CACHE.get("cfg") and _CACHE["cfg"].get("enabled"):
            out.update(mode="invalid", enabled=True, allowed=False, blocked=True)
    return out


def summary(s: dict) -> dict:
    """Versione per heartbeat.json (la legge l'app)."""
    return {k: s.get(k) for k in ("mode", "enabled", "allowed", "blocked", "tz", "windows", "next_change_ms", "error")}
