"""Calendario macro: eventi USA ad alto impatto (CPI, PPI, FOMC, occupazione, discorsi della Fed...) per far
lavorare il bot in modo piu' prudente nei giorni a rischio.

Cosa fa (e SOLO questo):
- scarica il calendario (feed settimanale in formato Forex Factory; ripiego: calendario ufficiale BLS per CPI,
  PPI e occupazione) e lo tiene in cache nella cartella dati del bot (macro_events.json);
- calcola il "regime" del momento: calmo / medio / alto;
- distingue gli eventi ad alto impatto in due livelli: GRANDI (CPI, PPI, occupazione/NFP, FOMC, PCE) e SECONDARI
  (discorsi, vendite al dettaglio, PIL...);
- BLOCCA le NUOVE aperture: attorno a un evento GRANDE da `block_before_min` minuti prima a `block_after_min` dopo,
  attorno a un SECONDARIO solo da `minor_block_before_min` a `minor_block_after_min` (finestra corta);
- in regime alto (solo per gli eventi GRANDI) alza di `conf_bonus_alto` punti la confidenza richiesta per aprire;
  i secondari non alzano mai la soglia;
- offre righe di testo per Claude e campi per il registro di apprendimento.

Cosa NON fa: non tocca le posizioni gia' aperte (stop, take profit, DCA, seconda gamba, chiusure), non cambia mai
la strategia, non decide nulla se non c'e' un dato. Se il calendario non e' disponibile, o qualsiasi cosa va
storta, il bot lavora esattamente come prima (regime "nd", nessun blocco, nessun bonus).

MODALITA' OSSERVAZIONE (predefinita, scelta dell'utente del 16 ottobre): il calendario viene letto e REGISTRATO
(regime, blocco che ci sarebbe stato, bonus che ci sarebbe stato) ma NON frena il bot: nessun blocco, nessun +confidenza.
Serve a confrontare con i dati "con calendario" e "senza" prima di decidere. Per far FRENARE davvero il bot (blocco e
bonus applicati) basta creare il file `macro_enforce.flag` nella cartella dati (nessun riavvio) oppure DESK_MACRO_ENFORCE=1.

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
ENFORCE_FLAG = "macro_enforce.flag"      # presente = il calendario FRENA (blocco e bonus); assente = solo osservazione

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


# Classificazione dei titoli: sono "grandi" le uscite che muovono davvero il mercato. Tutto il resto ad alto impatto
# e' "secondario". I dati del calendario ufficiale BLS (CPI, PPI, occupazione) sono sempre grandi.
_GRANDE_RE = re.compile(r"\b(cpi|ppi|pce|fomc)\b|non-?farm|federal funds|unemployment rate", re.I)


_DISCORSO_RE = re.compile(r"speaks|speech|testif|remarks", re.I)


def event_tier(e: dict) -> str:
    """'grande' | 'secondario' per un evento ad alto impatto."""
    if e.get("src") == "bls":
        return "grande"
    title = str(e.get("title") or "")
    if title.lower().startswith("adp"):          # ADP anticipa l'occupazione ma non e' l'uscita ufficiale
        return "secondario"
    if _DISCORSO_RE.search(title):                # discorsi e audizioni (anche dei membri FOMC): secondari
        return "secondario"
    return "grande" if _GRANDE_RE.search(title) else "secondario"


@dataclass(frozen=True)
class MacroConfig:
    """PARAMETRI DEL FILTRO. Sono decisioni dell'utente: valori proposti, da approvare prima del riavvio."""
    countries: tuple = ("USD",)        # valute degli eventi che contano
    # --- eventi GRANDI (CPI, PPI, occupazione, FOMC, PCE)
    block_before_min: int = 60         # niente nuove aperture da 60 minuti PRIMA di un evento grande...
    block_after_min: int = 120         # ...fino a 120 minuti DOPO
    lookahead_h: int = 6               # regime "alto" se c'e' un evento grande nelle prossime 6 ore (era 12)...
    lookback_h: int = 3                # ...o c'e' stato nelle ultime 3
    conf_bonus_alto: int = 3           # in regime alto: +3 punti di confidenza richiesta per aprire (era +5)
    conf_bonus_medio: int = 0          # in regime medio: solo informazione (nessun bonus)
    # --- eventi SECONDARI (gli altri ad alto impatto: discorsi, vendite al dettaglio, PIL...)
    minor_block_before_min: int = 15   # blocco corto: da 15 minuti prima...
    minor_block_after_min: int = 30    # ...a 30 minuti dopo; nessun aumento di soglia


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
    big = [e for e in high if event_tier(e) == "grande"]
    minor = [e for e in high if event_tier(e) != "grande"]
    medium = [e for e in events if e.get("impact") == "Medium"]
    look = (now_ms - cfg.lookback_h * HOUR_MS, now_ms + cfg.lookahead_h * HOUR_MS)
    inside = [e for e in big if look[0] <= e["ts"] <= look[1]]
    blocking_big = [e for e in big
                    if e["ts"] - cfg.block_before_min * MIN_MS <= now_ms < e["ts"] + cfg.block_after_min * MIN_MS]
    blocking_minor = [e for e in minor
                      if e["ts"] - cfg.minor_block_before_min * MIN_MS <= now_ms < e["ts"] + cfg.minor_block_after_min * MIN_MS]
    ends = [e["ts"] + cfg.block_after_min * MIN_MS for e in blocking_big] + \
           [e["ts"] + cfg.minor_block_after_min * MIN_MS for e in blocking_minor]
    if inside or blocking_big:
        regime, bonus = "alto", cfg.conf_bonus_alto
    elif blocking_minor or any(look[0] <= e["ts"] <= look[1] for e in medium + minor):
        regime, bonus = "medio", cfg.conf_bonus_medio     # solo informazione (i secondari non alzano la soglia)
    else:
        regime, bonus = "calmo", 0

    def view(e: dict) -> dict:
        return {"title": e["title"], "ts": e["ts"], "min": int(round((e["ts"] - now_ms) / MIN_MS)), "src": e.get("src"),
                "tier": event_tier(e)}

    upcoming = [view(e) for e in high if e["ts"] >= now_ms][:4]
    recent = [view(e) for e in high if look[0] <= e["ts"] < now_ms][-3:]
    return {"regime": regime, "blackout": bool(ends),
            "blackout_until_ms": max(ends) if ends else None,
            "conf_bonus": bonus, "next": upcoming[0] if upcoming else None, "upcoming": upcoming, "recent": recent,
            "n_events": len(events), "fetched_ms": fetched_ms,
            "stale": bool(fetched_ms) and (now_ms - fetched_ms) > STALE_MS, "error": error}


def enforcing(data_dir: str) -> bool:
    """True se il calendario deve frenare davvero il bot. Predefinito: NO (osservazione, solo registro)."""
    if os.getenv("DESK_MACRO_ENFORCE", "") == "1":
        return True
    return os.path.exists(os.path.join(data_dir, ENFORCE_FLAG))


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
        m = evaluate(events, now_ms, cfg, fetched_ms=max(s["ts"] for s in have), error=err)
        m["enforce"] = enforcing(data_dir)
        return m
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
    ev = "; ".join(f"{hm_utc(u['ts'])} UTC {u['title']} [{u.get('tier', 'grande')}] (tra {_fmt_min(u['min'])})"
                   for u in near) or "nessuno nelle prossime 24h"
    head = f"CALENDARIO MACRO (USA, impatto alto): regime {m['regime'].upper()}. Prossimi: {ev}."
    if recent:
        head += (" Usciti da poco: " + "; ".join(f"{hm_utc(u['ts'])} UTC {u['title']} [{u.get('tier', 'grande')}] "
                                                 f"({_fmt_min(u['min'])} fa)" for u in recent) + ".")
    if not m.get("enforce", True):
        rule = ("MODALITA' OSSERVAZIONE: il codice NON blocca nulla e NON alza la soglia di confidenza per il calendario; "
                "usalo solo come informazione per giudicare il rischio di volatilita'")
        if m["blackout"]:
            rule += f" (siamo dentro una finestra a rischio, fino alle {hm_utc(m['blackout_until_ms'])} UTC)"
        return [head, rule + "."]
    rule = (f"Il codice blocca le NUOVE aperture da {cfg.block_before_min} min prima a {cfg.block_after_min} min dopo "
            f"ogni evento [grande] (CPI, PPI, occupazione, FOMC, PCE) e da {cfg.minor_block_before_min} min prima a "
            f"{cfg.minor_block_after_min} min dopo ogni evento [secondario]")
    if m["blackout"]:
        rule += f" (ORA ATTIVO fino alle {hm_utc(m['blackout_until_ms'])} UTC)"
    if m["conf_bonus"]:
        rule += f"; in regime alto (eventi grandi) richiede +{m['conf_bonus']} di confidenza per aprire"
    return [head, rule + ". Le posizioni gia' aperte non vengono toccate dal filtro."]


def features(m: dict) -> dict:
    """Campi per il registro di apprendimento (feature d'ingresso): servono all'analista per misurare l'effetto."""
    nxt = m.get("next")
    return {"macro_regime": m.get("regime"), "macro_blackout": bool(m.get("blackout")),
            "macro_bonus": int(m.get("conf_bonus") or 0), "macro_min_next": nxt["min"] if nxt else None,
            "macro_tier_next": nxt.get("tier") if nxt else None,
            "macro_enforced": bool(m.get("enforce", True))}


def heartbeat_view(m: dict) -> dict:
    v = {k: m.get(k) for k in ("regime", "blackout", "blackout_until_ms", "conf_bonus", "next", "upcoming",
                               "recent", "n_events", "fetched_ms", "stale", "error")}
    v["enforce"] = bool(m.get("enforce", True))
    if not v["enforce"]:
        # in osservazione il bot NON frena: l'app non deve mostrare «aperture sospese». La lettura vera resta in `observed`.
        v["observed"] = {k: v[k] for k in ("regime", "blackout", "blackout_until_ms", "conf_bonus")}
        v.update(regime="osservazione" if v["regime"] in ("medio", "alto") else v["regime"],
                 blackout=False, blackout_until_ms=None, conf_bonus=0)
    return v
