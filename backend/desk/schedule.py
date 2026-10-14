"""Calendario di Claude: decide SOLO il QUANDO Claude viene consultato, mai il COSA.

Il file claude_schedule.json (nella cartella dati del bot) elenca le finestre in cui Claude puo' essere
chiamato. Il bot lo rilegge da solo quando cambia: per modificare il calendario non serve riavviare nulla.

    {"version": 1, "windows": [
        {"start": "2026-10-13T12:30:00Z", "end": "2026-10-13T16:30:00Z", "label": "mar 13 14:30-18:30 (ora svizzera)"}
    ]}

Regole:
- file assente  -> nessun calendario: vale il comportamento di sempre (budget giornaliero, Claude quando serve);
- file valido   -> Claude e' consultato solo dentro le finestre (inizio compreso, fine esclusa);
                   fuori dalle finestre decidono le regole, come quando il budget e' finito;
- file rovinato -> si tiene l'ultimo calendario valido letto; se non ce n'e' uno, Claude resta spento.
Gli orari sono sempre assoluti (UTC o con scostamento esplicito): il cambio d'ora non puo' spostarli.
"""
import json
import os
from datetime import datetime
from typing import Optional

SCHEDULE_FILE = "claude_schedule.json"
MAX_WINDOWS = 500

_CACHE: dict = {"path": None, "sig": None, "mode": "none", "windows": [], "error": ""}


def reset_cache() -> None:
    """Per i test: dimentica il calendario letto."""
    _CACHE.update(path=None, sig=None, mode="none", windows=[], error="")


def _to_ms(value) -> int:
    if not isinstance(value, str):
        raise ValueError("orario non e' un testo")
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("orario senza fuso (serve Z o +hh:mm)")
    return int(dt.timestamp() * 1000)


def parse_windows(obj) -> tuple:
    """Controlla il contenuto del file. Ritorna (finestre, errore): o tutto valido, o errore e nessuna finestra."""
    raw = obj.get("windows") if isinstance(obj, dict) else obj
    if not isinstance(raw, list):
        return [], "manca l'elenco 'windows'"
    if len(raw) > MAX_WINDOWS:
        return [], f"troppe finestre ({len(raw)} > {MAX_WINDOWS})"
    out = []
    for i, w in enumerate(raw, 1):
        if not isinstance(w, dict):
            return [], f"finestra {i}: non e' un oggetto"
        try:
            s, e = _to_ms(w.get("start")), _to_ms(w.get("end"))
        except (ValueError, TypeError, OverflowError) as ex:
            return [], f"finestra {i}: {ex}"
        if e <= s:
            return [], f"finestra {i}: la fine non e' dopo l'inizio"
        out.append({"id": str(s), "start_ms": s, "end_ms": e, "label": str(w.get("label") or "")[:80]})
    out.sort(key=lambda x: x["start_ms"])
    for a, b in zip(out, out[1:]):
        if b["start_ms"] < a["end_ms"]:
            return [], f"finestre sovrapposte (la finestra che inizia {b['start_ms']} parte prima che l'altra finisca)"
    return out, ""


def _load(data_dir: str) -> None:
    path = os.path.join(data_dir, SCHEDULE_FILE)
    try:
        st = os.stat(path)
    except OSError:
        _CACHE.update(path=path, sig=None, mode="none", windows=[], error="")
        return
    sig = (st.st_mtime_ns, st.st_size)
    if _CACHE["path"] == path and _CACHE["sig"] == sig:
        return
    try:
        with open(path, encoding="utf-8") as fh:
            wins, err = parse_windows(json.load(fh))
    except (OSError, ValueError) as ex:
        wins, err = [], f"file illeggibile ({type(ex).__name__})"
    if err:
        # file rovinato: resta valido l'ultimo calendario letto; se non ce n'e', Claude resta spento
        keep = _CACHE["path"] == path and _CACHE["mode"] == "calendar"
        _CACHE.update(path=path, sig=sig, error=err, mode="calendar" if keep else "invalid",
                      windows=_CACHE["windows"] if keep else [])
        return
    _CACHE.update(path=path, sig=sig, mode="calendar", windows=wins, error="")


def schedule_state(data_dir: str, now_ms: int) -> dict:
    """Situazione adesso. 'allowed' = Claude puo' essere consultato in questo momento.
    mode: none (nessun calendario) | calendar | invalid (file rovinato e nessun calendario valido)."""
    try:
        _load(data_dir)
    except Exception as ex:   # il calendario non deve mai fermare il bot
        _CACHE.update(mode="invalid", windows=[], error=f"errore interno ({type(ex).__name__})")
    mode = _CACHE["mode"]
    out = {"mode": mode, "allowed": mode == "none", "window": None, "next_start_ms": None,
           "n_future": 0, "error": _CACHE["error"]}
    if mode == "calendar":
        for w in _CACHE["windows"]:
            if w["start_ms"] <= now_ms < w["end_ms"]:
                out["allowed"], out["window"] = True, w
                break
        fut = [w for w in _CACHE["windows"] if w["start_ms"] > now_ms]
        out["n_future"] = len(fut)
        out["next_start_ms"] = fut[0]["start_ms"] if fut else None
    return out


def summary(s: dict) -> dict:
    """Versione corta per heartbeat.json (la leggono l'app e la diagnosi)."""
    w: Optional[dict] = s.get("window")
    return {"mode": s["mode"], "allowed": s["allowed"], "window_end_ms": w["end_ms"] if w else None,
            "next_start_ms": s.get("next_start_ms"), "n_future": s.get("n_future", 0), "error": s.get("error", "")}
