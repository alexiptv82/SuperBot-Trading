"""Calendario macro: eventi USA ad alto impatto (CPI, PPI, FOMC, occupazione, discorsi della Fed...) per far
lavorare il bot in modo piu' prudente nei giorni a rischio.

Cosa fa (e SOLO questo):
- scarica il calendario (feed settimanale in formato Forex Factory; ripiego: calendario ufficiale BLS per CPI,
  PPI e occupazione) e lo tiene in cache nella cartella dati del bot (macro_events.json);
- calcola il "regime" del momento: calmo / medio / alto;
- BLOCCA le NUOVE aperture da `block_before_min` minuti prima a `block_after_min` dopo ogni evento ad alto impatto;
- in regime alto alza di `conf_bonus_alto` punti la confidenza richiesta per aprire;
- offre righe di testo per Claude e campi per il registro di apprendimento.

Cosa NON fa: non tocca le posizioni gia' aperte (stop, take profit, DCA, seconda gamba, chiusure), non cambia mai
la strategia, non decide nulla se non c'e' un dato. Se il calendario non e' disponibile, o qualsiasi cosa va
storta, il bot lavora esattamente come prima (regime "nd", nessun blocco, nessun bonus).

Interruttori: variabile DESK_MACRO=0 (spegne tutto), file `macro_off.flag` nella cartella dati (spegne il filtro
senza riavviare), DESK_MACRO_FETCH=0 (niente rete: usa solo la cache; serve ai test).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

CACHE_FILE = "macro_events.json"
OFF_FLAG = "macro_off.flag"

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
BLS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"

MIN_MS = 60_000
HOUR_MS = 3_600_000
FF_REFRESH_MS = 3 * HOUR_MS        # il feed e' aggiornato spesso, ma non serve chiederlo di continuo
BLS_REFRESH_MS = 24 * HOUR_MS      # le date ufficiali cambiano di rado
RETRY_MS = 15 * MIN_MS             # dopo un errore si riprova tra 15 minuti, non a ogni ciclo
STALE_MS = 36 * HOUR_MS            # dati piu' vecchi di cosi' vengono segnalati come "vecchi"
HTTP_TIMEOUT_S = 8
MAX_AHEAD_MS = 30 * 24 * HOUR_MS   # eventi oltre 30 giorni non servono

# titoli BLS (calendario ufficiale) che contano come alto impatto, con il nome mostrato
BLS_KEEP = (("consumer price index", "CPI (BLS)"), ("producer price index", "PPI (BLS)"),
            ("employment situation", "Occupazione/NFP (BLS)"))


@dataclass(frozen=True)
class MacroConfig:
    """PARAMETRI DEL FILTRO. Sono decisioni dell'utente: valori proposti, da approvare prima del riavvio."""
    countries: tuple = ("USD",)        # valute degli eventi che contano
    block_before_min: int = 60         # niente nuove aperture da 60 minuti PRIMA di un evento ad alto impatto...
    block_after_min: int = 120         # ...fino a 120 minuti DOPO
    lookahead_h: int = 12              # regime "alto" se c'e' un evento alto nelle prossime 12 ore...
    lookback_h: int = 3                # ...o c'e' stato nelle ultime 3
    conf_bonus_alto: int = 5           # in regime alto: +5 punti di confidenza richiesta per aprire
    conf_bonus_medio: int = 0          # in regime medio: solo informazione (nessun bonus)


CFG = MacroConfig()


# ---------------------------------------------------------------- ora legale USA (senza librerie di fusi)
def _nth_sunday(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)          # primo giorno di domenica del mese
    return d + timedelta(weeks=n - 1)


def us_eastern_offset_h(day: date) -> int:
    """-4 (ora legale) dalla 2a domenica di marzo alla 1a di novembre, altrimenti -5. Vale per le 08:30 locali
    dei rilasci BLS: nei giorni del cambio l'ora legale e' gia' scattata alle 02:00, quindi niente ambiguita'."""
    start, end = _nth_sunday(day.year, 3, 2), _nth_sunday(day.year, 11, 1)
    return -4 if start <= day < end else -5


# ---------------------------------------------------------------- lettura delle fonti
def parse_ff(raw: bytes, cfg: MacroConfig = CFG) -> list:
    """Feed Forex Factory: [{title, country, date(ISO con fuso), impact, ...}]. Tiene solo alto/medio impatto."""
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("feed non e' una lista")
    out = []
    for e in data:
        try:
            country, impact = str(e.get("country") or ""), str(e.get("impact") or "")
            if country not in cfg.countries or impact not in ("High", "Medium"):
                continue
            dt = datetime.fromisoformat(str(e["date"]))
            if dt.tzinfo is None:
                continue                                  # senza fuso non si puo' dire quando
            out.append({"ts": int(dt.timestamp() * 1000), "title": str(e.get("title") or "?")[:60],
                        "country": country, "impact": impact, "src": "ff"})
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    return out


def parse_bls_ics(text: str, now_ms: int, cfg: MacroConfig = CFG) -> list:
    """Calendario ufficiale BLS (ICS): CPI, PPI e occupazione, sempre alle 08:30 ora di New York."""
    out = []
    for block in text.split("BEGIN:VEVENT")[1:]:
        ms = re.search(r"^SUMMARY:([^\r\n]*)", block, re.M)
        md = re.search(r"^DTSTART(?:;[^:\r\n]*)?:(\d{8})T(\d{6})(Z?)", block, re.M)
        if not (ms and md):
            continue
        name = next((shown for key, shown in BLS_KEEP if key in ms.group(1).lower()), None)
        if name is None:
            continue
        try:
            d8, t6 = md.group(1), md.group(2)
            local = datetime(int(d8[:4]), int(d8[4:6]), int(d8[6:8]), int(t6[:2]), int(t6[2:4]), int(t6[4:6]))
            offset = 0 if md.group(3) == "Z" else us_eastern_offset_h(local.date())
            ts = int((local.replace(tzinfo=timezone.utc) - timedelta(hours=offset)).timestamp() * 1000)
        except ValueError:
            continue
        if now_ms - 24 * HOUR_MS <= ts <= now_ms + MAX_AHEAD_MS:
            out.append({"ts": ts, "title": name, "country": "USD", "impact": "High", "src": "bls"})
    return out


def _http_get(url: str, timeout: int = HTTP_TIMEOUT_S) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; superbot-desk/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- cache su disco
def _empty_source() -> dict:
    return {"ts": 0, "next_try_ms": 0, "events": [], "error": ""}


def load_cache(data_dir: str) -> dict:
    cache = {"ff": _empty_source(), "bls": _empty_source()}
    try:
        with open(os.path.join(data_dir, CACHE_FILE), encoding="utf-8") as fh:
            raw = json.load(fh)
        for k in ("ff", "bls"):
            s = raw.get(k)
            if isinstance(s, dict) and isinstance(s.get("events"), list):
                cache[k] = {**_empty_source(), **{x: s[x] for x in ("ts", "next_try_ms", "events", "error") if x in s}}
    except (OSError, ValueError, AttributeError):
        pass
    return cache


def save_cache(data_dir: str, cache: dict) -> None:
    try:
        os.makedirs(data_dir, exist_ok=True)
        path = os.path.join(data_dir, CACHE_FILE)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass


def refresh_if_due(data_dir: str, now_ms: int, fetch: Optional[Callable] = None, cfg: MacroConfig = CFG) -> dict:
    """Aggiorna la cache solo se e' ora (e mai a raffica dopo un errore). Non solleva mai."""
    cache = load_cache(data_dir)
    if os.getenv("DESK_MACRO_FETCH", "1") == "0":
        return cache
    fetch = fetch or _http_get
    changed = False
    for key, url, every in (("ff", FF_URL, FF_REFRESH_MS), ("bls", BLS_URL, BLS_REFRESH_MS)):
        src = cache[key]
        if now_ms < src["next_try_ms"]:
            continue
        changed = True
        try:
            raw = fetch(url, HTTP_TIMEOUT_S)
            events = parse_ff(raw, cfg) if key == "ff" else parse_bls_ics(raw.decode("utf-8", "replace"), now_ms, cfg)
            cache[key] = {"ts": now_ms, "next_try_ms": now_ms + every, "events": events, "error": ""}
        except Exception as e:                            # rete, JSON rotto, formato cambiato: si tiene il vecchio
            src["next_try_ms"] = now_ms + RETRY_MS
            src["error"] = f"{type(e).__name__}: {str(e)[:80]}"
    if changed:
        save_cache(data_dir, cache)
    return cache


# ---------------------------------------------------------------- valutazione del momento
def _neutral(regime: str, error: str = "") -> dict:
    return {"regime": regime, "blackout": False, "blackout_until_ms": None, "conf_bonus": 0, "next": None,
            "upcoming": [], "recent": [], "n_events": 0, "fetched_ms": 0, "stale": False, "error": error}


def evaluate(events: list, now_ms: int, cfg: MacroConfig = CFG, fetched_ms: int = 0, error: str = "") -> dict:
    high = sorted((e for e in events if e.get("impact") == "High"), key=lambda e: e["ts"])
    medium = [e for e in events if e.get("impact") == "Medium"]
    look = (now_ms - cfg.lookback_h * HOUR_MS, now_ms + cfg.lookahead_h * HOUR_MS)
    inside = [e for e in high if look[0] <= e["ts"] <= look[1]]
    blocking = [e for e in high if e["ts"] - cfg.block_before_min * MIN_MS <= now_ms < e["ts"] + cfg.block_after_min * MIN_MS]
    if inside or blocking:
        regime, bonus = "alto", cfg.conf_bonus_alto
    elif any(look[0] <= e["ts"] <= look[1] for e in medium):
        regime, bonus = "medio", cfg.conf_bonus_medio
    else:
        regime, bonus = "calmo", 0

    def view(e: dict) -> dict:
        return {"title": e["title"], "ts": e["ts"], "min": int(round((e["ts"] - now_ms) / MIN_MS)), "src": e.get("src")}

    upcoming = [view(e) for e in high if e["ts"] >= now_ms][:4]
    recent = [view(e) for e in high if look[0] <= e["ts"] < now_ms][-3:]
    return {"regime": regime, "blackout": bool(blocking),
            "blackout_until_ms": max(e["ts"] + cfg.block_after_min * MIN_MS for e in blocking) if blocking else None,
            "conf_bonus": bonus, "next": upcoming[0] if upcoming else None, "upcoming": upcoming, "recent": recent,
            "n_events": len(events), "fetched_ms": fetched_ms,
            "stale": bool(fetched_ms) and (now_ms - fetched_ms) > STALE_MS, "error": error}


def apply_policy(m: dict, mode: str = "enforce") -> dict:
    """News remain real observations; only an explicitly selected mode governs trade gates.

    - enforce (legacy): preserve the original macro blackout and +5 confidence bonus.
    - observe (operator choice, 28/10/2026): no macro veto or confidence adjustment;
      event title/time, regime, raw impact and would-block diagnostics are preserved.
    No change to daily stop, margin, stop-loss, entry score or other protections.
    """
    if mode not in ("observe", "enforce"):
        raise ValueError("invalid_macro_policy")
    raw_blackout = bool(m.get("blackout"))
    raw_bonus = int(m.get("conf_bonus") or 0)
    return {**m, "enforce": mode == "enforce",
            "raw_blackout": raw_blackout, "raw_conf_bonus": raw_bonus,
            "blackout": raw_blackout if mode == "enforce" else False,
            "conf_bonus": raw_bonus if mode == "enforce" else 0,
            "blackout_until_ms": m.get("blackout_until_ms") if mode == "enforce" else None}


def current(data_dir: str, now_ms: int, fetch: Optional[Callable] = None, cfg: MacroConfig = CFG) -> dict:
    """Stato macro del momento. NON SOLLEVA MAI: in caso di problemi ritorna uno stato neutro (nessun effetto)."""
    try:
        if os.getenv("DESK_MACRO", "1") == "0":
            return _neutral("off")
        if os.path.exists(os.path.join(data_dir, OFF_FLAG)):
            return _neutral("off")
        cache = refresh_if_due(data_dir, now_ms, fetch, cfg)
        have = [s for s in (cache["ff"], cache["bls"]) if s["ts"] > 0]
        if not have:
            err = cache["ff"]["error"] or cache["bls"]["error"] or "nessun dato ancora"
            return _neutral("nd", err)
        events = cache["ff"]["events"] + cache["bls"]["events"]
        err = "; ".join(f"{k}: {cache[k]['error']}" for k in ("ff", "bls") if cache[k]["error"])
        result = evaluate(events, now_ms, cfg, fetched_ms=max(s["ts"] for s in have), error=err)
        mode = os.getenv("DESK_MACRO_POLICY", "enforce").strip().lower()
        return apply_policy(result, mode)
    except Exception as e:                                # qualunque imprevisto: il bot lavora come prima
        return _neutral("nd", f"errore interno: {type(e).__name__}")


# ---------------------------------------------------------------- uscite: testo per Claude, registro, battito
def hm_utc(ts_ms: int) -> str:
    return time.strftime("%H:%M", time.gmtime(ts_ms / 1000))


def _fmt_min(m: int) -> str:
    """Durata positiva in forma breve: 45 -> '45m', 130 -> '2h10m' (per un valore negativo si usa il modulo)."""
    a = abs(int(m))
    return f"{a}m" if a < 60 else f"{a // 60}h{a % 60:02d}m"


def prompt_lines(m: dict, cfg: MacroConfig = CFG) -> list:
    """Righe per il prompt di Claude. Vuote quando non c'e' nulla da dire (regime calmo e nessun evento vicino)."""
    if m.get("regime") in ("off", "nd"):
        return []
    near = [u for u in m.get("upcoming", []) if u["min"] <= 24 * 60]
    recent = m.get("recent", [])
    if m["regime"] == "calmo" and not near and not recent:
        return []
    ev = "; ".join(f"{hm_utc(u['ts'])} UTC {u['title']} (tra {_fmt_min(u['min'])})" for u in near) or "nessuno nelle prossime 24h"
    head = f"CALENDARIO MACRO (USA, impatto alto): regime {m['regime'].upper()}. Prossimi: {ev}."
    if recent:
        head += " Usciti da poco: " + "; ".join(f"{hm_utc(u['ts'])} UTC {u['title']} ({_fmt_min(u['min'])} fa)" for u in recent) + "."
    rule = (f"Il codice blocca le NUOVE aperture da {cfg.block_before_min} min prima a {cfg.block_after_min} min dopo "
            f"ogni evento")
    if m.get("enforce") is False:
        return [head, "EVENTI MACRO SOLO INFORMATIVI: l'evento e il regime di volatilita' "
                "NON bloccano aperture e NON aggiungono punti alla soglia di ingresso. "
                "Valuta autonomamente liquidita', spread, slippage, rischio e direzione; "
                "non trattare la notizia come un ordine di entrare o restare fuori."]
    if m["blackout"]:
        rule += f" (ORA ATTIVO fino alle {hm_utc(m['blackout_until_ms'])} UTC)"
    if m["conf_bonus"]:
        rule += f" e in regime alto richiede +{m['conf_bonus']} di confidenza per aprire"
    return [head, rule + ". Le posizioni gia' aperte non vengono toccate dal filtro."]


def features(m: dict) -> dict:
    """Campi per il registro di apprendimento (feature d'ingresso): servono all'analista per misurare l'effetto."""
    nxt = m.get("next")
    return {"macro_regime": m.get("regime"), "macro_blackout": bool(m.get("blackout")),
            "macro_bonus": int(m.get("conf_bonus") or 0), "macro_min_next": nxt["min"] if nxt else None,
            "macro_enforce": m.get("enforce", True),
            "macro_would_blackout": bool(m.get("raw_blackout", m.get("blackout"))),
            "macro_would_bonus": int(m.get("raw_conf_bonus",m.get("conf_bonus") or 0))}


def heartbeat_view(m: dict) -> dict:
    return {k: m.get(k) for k in ("regime", "enforce", "blackout", "raw_blackout", "blackout_until_ms",
                                  "conf_bonus", "raw_conf_bonus", "next", "upcoming",
                                  "recent", "n_events", "fetched_ms", "stale", "error")}
