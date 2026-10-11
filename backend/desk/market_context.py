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
    oi_change_24h: float # variazione % nelle ultime 24h
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
    url = f"{BITGET_BASE}/api/v2/mix/market/current-fund-rate?symbol={sym}PERP&productType=USDT-FUTURES"
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


def fetch_open_interest(symbol: str) -> Optional[OIInfo]:
    """Ritorna open interest corrente e variazione 24h da BitGet."""
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym = sym + "USDT"
    url = f"{BITGET_BASE}/api/v2/mix/market/open-interest?symbol={sym}PERP&productType=USDT-FUTURES"
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
        row = rows[0]
        oi = float(row.get("openInterestValue") or row.get("amount") or 0)
        # variazione: confronto tra i primi due punti se disponibili
        change = 0.0
        if len(rows) >= 2:
            prev = float(rows[-1].get("openInterestValue") or rows[-1].get("amount") or oi)
            change = (oi - prev) / max(prev, 1) * 100
        note = f"OI {symbol}: {oi/1e6:.1f}M USD, var 24h {change:+.1f}%"
        if change > 10:
            note += " — OI in forte crescita (momentum)"
        elif change < -10:
            note += " — OI in calo (chiusure, cautela)"
        return OIInfo(symbol, oi, change, note)
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
    """Raccoglie funding + OI per tutti i simboli + notizie. Ritorna dict pronto per il prompt."""
    funding, oi = {}, {}
    for s in symbols:
        f = fetch_funding(s)
        if f:
            funding[s] = f
        o = fetch_open_interest(s)
        if o:
            oi[s] = o
    news = fetch_cryptopanic(symbols[:6])
    return {"funding": funding, "oi": oi, "news": news, "ts": now_ms or int(time.time() * 1000)}


def context_lines(ctx: dict, symbol: str) -> list:
    """Righe di testo sul contesto di mercato per un simbolo (per il prompt)."""
    lines = []
    f = ctx["funding"].get(symbol)
    if f:
        lines.append(f.note)
    o = ctx["oi"].get(symbol)
    if o:
        lines.append(o.note)
    return lines
