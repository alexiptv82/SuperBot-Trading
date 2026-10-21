"""Dati di mercato extra: funding rate, open interest, notizie CryptoPanic.

Tutto opzionale: se una fonte fallisce ritorna None/[] silenziosamente.
Nessuna chiave richiesta (CryptoPanic ha endpoint pubblico gratuito).
"""
from __future__ import annotations

import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

BITGET_BASE = "https://api.bitget.com"
CRYPTOPANIC_URL = "https://cryptopanic.com/api/v1/posts/?auth_token=public&kind=news&currencies={sym}&public=true"
COINDESK_RSS = "https://www.coindesk.com/arc/outboundfeeds/rss/"
COINTELEGRAPH_RSS = "https://cointelegraph.com/rss"
TIMEOUT = 8


@dataclass
class FundingInfo:
    symbol: str
    rate: float          # tasso funding corrente (es. 0.0001 = 0.01%)
    predicted: float     # tasso previsto prossimo pagamento
    long_cost_8h_bp: float  # costo in bp per i long ogni 8h (positivo = pagano i long)
    note: str


@dataclass
class OIInfo:
    symbol: str
    oi_usd: float        # open interest in USD
    oi_change_24h: Optional[float]  # variazione % nelle ultime 24h; None finche' non c'e' storico (vedi apply_oi_history)
    note: str


@dataclass
class LSRatioInfo:
    symbol: str
    ratio: float         # long/short ratio (>1 = più long che short)
    note: str


def _get(url: str, timeout: int = TIMEOUT) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def fetch_funding(symbol: str) -> Optional[FundingInfo]:
    """Ritorna funding rate corrente da BitGet (endpoint pubblico)."""
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym = sym + "USDT"
    url = f"{BITGET_BASE}/api/v2/mix/market/current-fund-rate?symbol={sym}&productType=USDT-FUTURES"
    data = _get(url)
    if data is None:
        return None
    try:
        d = json.loads(data)
        if d.get("code") != "00000":
            return None
        row = d["data"][0] if isinstance(d.get("data"), list) and d["data"] else d.get("data", {})
        rate = float(row.get("fundingRate", 0))
        predicted = float(row.get("predictedFundingRate") or row.get("nextSettleFundingRate") or rate)
        cost_bp = rate * 1e4
        note = f"Funding {symbol}: corrente {rate*100:.4f}%, previsto {predicted*100:.4f}%"
        if rate > 0.0005:
            note += " — funding alto, short favoriti"
        elif rate < -0.0002:
            note += " — funding negativo, long favoriti"
        return FundingInfo(symbol, rate, predicted, cost_bp, note)
    except Exception:
        return None


def _usdt_sym(symbol: str) -> str:
    sym = symbol.upper()
    return sym if sym.endswith("USDT") else sym + "USDT"


def fetch_tickers() -> dict:
    """Ultimo prezzo di tutti i futures USDT in UNA chiamata: {'BTCUSDT': 67000.0, ...}. Vuoto se fallisce."""
    data = _get(f"{BITGET_BASE}/api/v2/mix/market/tickers?productType=USDT-FUTURES")
    if data is None:
        return {}
    try:
        d = json.loads(data)
        if d.get("code") != "00000" or not isinstance(d.get("data"), list):
            return {}
        out = {}
        for row in d["data"]:
            px = float(row.get("lastPr") or 0)
            if px > 0 and row.get("symbol"):
                out[str(row["symbol"]).upper()] = px
        return out
    except Exception:
        return {}


def _oi_note(symbol: str, oi: float, change: Optional[float]) -> str:
    if change is None:
        return f"OI {symbol}: {oi/1e6:.1f}M USD, var 24h n.d. (storico in costruzione)"
    note = f"OI {symbol}: {oi/1e6:.1f}M USD, var 24h {change:+.1f}%"
    if change > 10:
        note += " — OI in forte crescita (momentum)"
    elif change < -10:
        note += " — OI in calo (chiusure, cautela)"
    return note


def fetch_open_interest(symbol: str, price: Optional[float] = None) -> Optional[OIInfo]:
    """Open interest corrente in USD da BitGet. La risposta ha la forma
    {"data": {"openInterestList": [{"symbol": "BTCUSDT", "size": "34041.8"}], "ts": "..."}} con `size` in MONETE
    (non in dollari): il valore in USD e' size x ultimo prezzo (`price`, o dal ticker se non e' dato).
    Non esiste uno storico dell'OI su questo endpoint: la variazione 24h resta None e la calcola
    `apply_oi_history` dalle letture del bot. Dato non valido -> None (mai un numero inventato)."""
    sym = _usdt_sym(symbol)
    data = _get(f"{BITGET_BASE}/api/v2/mix/market/open-interest?symbol={sym}&productType=USDT-FUTURES")
    if data is None:
        return None
    try:
        d = json.loads(data)
        if d.get("code") != "00000":
            return None
        lst = (d.get("data") or {}).get("openInterestList") or []
        row = next((r for r in lst if str(r.get("symbol", "")).upper() == sym), None) or (lst[0] if lst else None)
        if not row:
            return None
        size = float(row.get("size") or 0)
        if price is None:
            price = fetch_tickers().get(sym)
        if size <= 0 or not price or price <= 0:
            return None
        oi = size * float(price)
        return OIInfo(symbol, oi, None, _oi_note(symbol, oi, None))
    except Exception:
        return None


OI_HIST_KEEP_MS = 26 * 3_600_000      # le letture dell'OI si tengono 26 ore
OI_MIN_SPAN_MS = 20 * 3_600_000       # con meno di 20 ore di storico la variazione 24h non si dichiara
OI_HIST_MAX_POINTS = 80


def apply_oi_history(oi_rows: dict, hist: dict, now_ms: int) -> None:
    """Calcola la variazione 24h dell'OI dalle letture del bot (BitGet non da' lo storico).
    `oi_rows`: simbolo -> dict serializzato di OIInfo (modificato). `hist`: simbolo -> [[ts_ms, oi_usd], ...]
    (modificato, va nello stato del bot). Riferimento = la lettura piu' vicina a 24 ore fa fra quelle vecchie di
    almeno 20 ore; senza, la variazione resta None."""
    for sym in list(hist):
        if sym not in oi_rows:
            hist.pop(sym, None)
    for sym, row in oi_rows.items():
        try:
            oi = float(row.get("oi_usd") or 0)
        except (TypeError, ValueError):
            continue
        if oi <= 0:
            continue
        pts = [p for p in hist.get(sym, []) if isinstance(p, (list, tuple)) and len(p) == 2
               and 0 < now_ms - p[0] <= OI_HIST_KEEP_MS and p[1] > 0]
        old = [p for p in pts if now_ms - p[0] >= OI_MIN_SPAN_MS]
        change = None
        if old:
            ref = min(old, key=lambda p: abs((now_ms - p[0]) - 24 * 3_600_000))
            change = round((oi - ref[1]) / ref[1] * 100, 2)
        pts.append([int(now_ms), oi])
        hist[sym] = pts[-OI_HIST_MAX_POINTS:]
        row["oi_change_24h"] = change
        row["note"] = _oi_note(sym, oi, change)


def fetch_ls_ratio(symbol: str) -> Optional[LSRatioInfo]:
    """Ritorna long/short ratio da BitGet (endpoint pubblico).
    ratio > 1 = più long che short; ratio < 1 = più short.
    """
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym = sym + "USDT"
    # XAU/XAG non hanno L/S ratio su BitGet futures
    if symbol.upper() in ("XAU", "XAG"):
        return None
    # Endpoint vero: /account-long-short (il vecchio /account-long-short-ratio non esiste: HTTP 404).
    # Risposta: {"data": [{"longAccountRatio": "0.68", "shortAccountRatio": "0.32",
    #                      "longShortAccountRatio": "2.13", "ts": "..."}, ...]} in ordine di tempo crescente.
    url = f"{BITGET_BASE}/api/v2/mix/market/account-long-short?symbol={sym}&period=1h"
    data = _get(url)
    if data is None:
        return None
    try:
        d = json.loads(data)
        if d.get("code") != "00000":
            return None
        rows = d.get("data", [])
        if not rows:
            return None
        row = max(rows, key=lambda r: int(float(r.get("ts") or 0))) if isinstance(rows, list) else rows
        ratio = float(row.get("longShortAccountRatio") or 0)
        if ratio <= 0:
            return None
        note = f"L/S ratio {symbol}: {ratio:.2f}"
        if ratio > 1.5:
            note += " — molti più long (attenzione: crowd long, considera short)"
        elif ratio < 0.7:
            note += " — molti più short (crowd short, considera long contrarian)"
        else:
            note += " — ratio neutro"
        return LSRatioInfo(symbol, ratio, note)
    except Exception:
        return None


def fetch_cryptopanic(symbols: list, limit: int = 6) -> list:
    """Notizie recenti da CryptoPanic (API pubblica gratuita, no autenticazione)."""
    sym_str = ",".join(s[:10] for s in symbols[:5])
    data = _get(CRYPTOPANIC_URL.format(sym=sym_str), timeout=10)
    if data is None:
        return _fetch_rss_headlines(limit)
    try:
        d = json.loads(data)
        results = d.get("results", [])
        out = []
        for item in results[:limit]:
            title = (item.get("title") or "").strip()
            if title:
                votes = item.get("votes", {})
                bull = votes.get("positive", 0)
                bear = votes.get("negative", 0)
                sentiment = ""
                if bull > bear + 2:
                    sentiment = " [bullish]"
                elif bear > bull + 2:
                    sentiment = " [bearish]"
                out.append(f"{title[:130]}{sentiment}")
        return out if out else _fetch_rss_headlines(limit)
    except Exception:
        return _fetch_rss_headlines(limit)


def _fetch_rss_headlines(limit: int = 8) -> list:
    """Fallback: titoli RSS da CoinDesk e CoinTelegraph."""
    out = []
    for url in [COINDESK_RSS, COINTELEGRAPH_RSS]:
        data = _get(url)
        if data is None:
            continue
        try:
            root = ET.fromstring(data)
            for it in root.iter("item"):
                t = (it.findtext("title") or "").strip()
                if t:
                    out.append(t[:140])
        except Exception:
            continue
    seen, uniq = set(), []
    for t in out:
        if t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)
    return uniq[:limit]


def fetch_all_context(symbols: list, now_ms: int | None = None) -> dict:
    """Raccoglie funding + OI + L/S ratio per tutti i simboli + notizie."""
    funding, oi, ls_ratio = {}, {}, {}
    prices = fetch_tickers()          # una chiamata sola per tutti i prezzi: servono a portare l'OI da monete a USD
    for s in symbols:
        f = fetch_funding(s)
        if f:
            funding[s] = f
        o = fetch_open_interest(s, prices.get(_usdt_sym(s)))
        if o:
            oi[s] = o
        ls = fetch_ls_ratio(s)
        if ls:
            ls_ratio[s] = ls
    news = fetch_cryptopanic(symbols[:6])
    return {"funding": funding, "oi": oi, "ls_ratio": ls_ratio,
            "news": news, "ts": now_ms or int(time.time() * 1000)}


def _note(obj) -> Optional[str]:
    """Restituisce il campo 'note' da dataclass o dict."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get("note")
    return getattr(obj, "note", None)


def context_lines(ctx: dict, symbol: str) -> list:
    """Righe di testo sul contesto di mercato per un simbolo (per il prompt).
    Funziona sia con dataclass che con dict (dopo deserializzazione JSON).
    """
    lines = []
    note = _note(ctx.get("funding", {}).get(symbol))
    if note:
        lines.append(note)
    note = _note(ctx.get("oi", {}).get(symbol))
    if note:
        lines.append(note)
    note = _note(ctx.get("ls_ratio", {}).get(symbol))
    if note:
        lines.append(note)
    return lines
