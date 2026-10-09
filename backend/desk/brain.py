"""Cervello: decisioni di Claude (via API) con tetto di spesa, piu' un ripiego a sole regole.

Regole d'oro:
- Claude PROPONE, il codice DECIDE: ogni valore viene validato e ridotto ai tetti dal conto.
- Se la chiave manca, il tetto di spesa e' finito o la risposta e' illeggibile, si usa il ripiego a regole.
- La chiave arriva solo da variabile d'ambiente e non viene mai stampata.
"""
from __future__ import annotations

import json
import os
import urllib.request
import xml.etree.ElementTree as ET

MODEL = os.getenv("DESK_MODEL", "claude-sonnet-5-5")
PRICE_IN, PRICE_OUT = 2.0 / 1e6, 10.0 / 1e6        # $/token (da riverificare sul listino ufficiale)
DAILY_CAP = float(os.getenv("DESK_DAILY_CAP_USD", "0.28"))
CALL_RESERVE = 0.03                               # non si chiama se resta meno di cosi'
API_URL = "https://api.anthropic.com/v1/messages"
FEEDS = ["https://www.coindesk.com/arc/outboundfeeds/rss/", "https://cointelegraph.com/rss"]

SYSTEM = """Sei il cervello di un trader di futures crypto in PAPER TRADING (soldi finti, 1000$). Decidi come un trader professionista prudente.
Ricevi: stato del conto, punteggi tecnici (0-100) per coppia, posizioni aperte, notizie recenti, appunti dei giorni scorsi.
Regole dure (il codice le applica comunque): leva max 30, margine max 250$ per trade, margine totale max 500$, max 3 posizioni, STOP LOSS obbligatorio.
Principio: piu' sei sicuro, piu' margine e leva; segnale incerto = poco margine e leva bassa; nel dubbio non aprire. Leva alta (oltre 15) solo con confidenza >= 85 e stop stretto.
Rispondi SOLO con JSON: {"decisions":[{"symbol":"BTC","action":"open_long|open_short|hold|close|skip","confidence":0-100,"leverage":int,"margin_usd":number,"stop_loss_pct":number,"take_profit_pct":number,"reason":"max 25 parole"}],"note":"max 20 parole"}
stop_loss_pct e take_profit_pct sono frazioni del prezzo (0.01 = 1%). Per le posizioni aperte usa hold o close. Per le altre coppie solo se c'e' un candidato."""


# ---------------- spesa
def cost_of(usage: dict) -> float:
    return usage.get("input_tokens", 0) * PRICE_IN + usage.get("output_tokens", 0) * PRICE_OUT


def budget_left(state: dict, day: str, cap: float = DAILY_CAP) -> float:
    b = state.setdefault("budget", {})
    if b.get("day") != day:
        b.update(day=day, spent=0.0, calls=0)
    return cap - b["spent"]


def can_call(state: dict, day: str, cap: float = DAILY_CAP) -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY")) and budget_left(state, day, cap) >= CALL_RESERVE


def record_spend(state: dict, day: str, usage: dict) -> float:
    c = cost_of(usage)
    budget_left(state, day)
    state["budget"]["spent"] += c
    state["budget"]["calls"] += 1
    state["budget"]["total_spent"] = state["budget"].get("total_spent", 0.0) + c
    return c


# ---------------- chiamata API
def call_claude(system: str, user: str, max_tokens: int = 700, timeout: int = 60) -> tuple:
    """(testo, usage). Solleva eccezione in caso di errore (mai con la chiave dentro il messaggio)."""
    key = os.getenv("ANTHROPIC_API_KEY", "")
    body = json.dumps({"model": MODEL, "max_tokens": max_tokens, "system": system,
                       "messages": [{"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"chiamata Claude fallita ({type(exc).__name__})") from None
    text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    return text, d.get("usage", {})


def parse_decisions(text: str) -> dict | None:
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(text[i:j + 1])
    except ValueError:
        return None
    if not isinstance(d, dict) or not isinstance(d.get("decisions"), list):
        return None
    out = []
    for x in d["decisions"]:
        try:
            act = str(x["action"])
            if act not in ("open_long", "open_short", "hold", "close", "skip"):
                continue
            out.append({"symbol": str(x["symbol"]).upper().split("/")[0], "action": act,
                        "confidence": int(max(0, min(100, float(x.get("confidence", 0))))),
                        "leverage": int(float(x.get("leverage", 1))),
                        "margin_usd": float(x.get("margin_usd", 0)),
                        "stop_loss_pct": float(x.get("stop_loss_pct", 0)),
                        "take_profit_pct": float(x.get("take_profit_pct", 0)),
                        "reason": str(x.get("reason", ""))[:300]})
        except (KeyError, TypeError, ValueError):
            continue
    return {"decisions": out, "note": str(d.get("note", ""))[:200]}


# ---------------- notizie (gratis, con ripiego silenzioso)
def fetch_headlines(limit: int = 8, timeout: int = 8) -> list:
    out = []
    for url in FEEDS:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                        timeout=timeout) as r:
                root = ET.fromstring(r.read())
            for it in root.iter("item"):
                t = (it.findtext("title") or "").strip()
                if t:
                    out.append(t[:140])
        except Exception:  # noqa: BLE001
            continue
    seen, uniq = set(), []
    for t in out:
        if t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)
    return uniq[:limit]


# ---------------- prompt
def build_prompt(snapshot: dict, readings: list, positions: list, headlines: list, lessons: str) -> str:
    lines = [f"CONTO: capitale {snapshot['equity']:.0f}$, cassa {snapshot['cash']:.0f}$, margine in uso "
             f"{snapshot['margin']:.0f}/500$, posizioni {snapshot['n_open']}/3, P&L oggi {snapshot['day_pnl']:+.1f}$"
             + (f", ATTENZIONE: {snapshot['halt']}" if snapshot.get("halt") else "")]
    if positions:
        lines.append("POSIZIONI APERTE:")
        for p in positions:
            lines.append(f"- {p['symbol']} {'LONG' if p['side'] == 1 else 'SHORT'} lev {p['leverage']}x margine "
                         f"{p['margin']:.0f}$ ingresso {p['entry']:.4g} ora {p['price']:.4g} P&L {p['pnl']:+.1f}$ "
                         f"stop {p['sl']:.4g} da {p['hours']:.1f}h. Motivo apertura: {p['reason'][:120]}. "
                         f"Punteggio attuale lato posizione {p['score_now']}")
    lines.append("COPPIE (punteggio tecnico 0-100 per il lato indicato):")
    for r in readings:
        side = "LONG" if r.side == 1 else "SHORT" if r.side == -1 else "-"
        lines.append(f"- {r.symbol}: prezzo {r.price:.5g}, {side} {r.score}/100 (long {r.long_score}, short {r.short_score}), "
                     f"ATR1h {r.atr_pct:.2%}, RSI1h {r.facts.get('rsi1h')}, trend4h {r.facts.get('ema50_200_4h')}, "
                     f"stop suggerito {r.sl_pct:.2%}")
    if headlines:
        lines.append("NOTIZIE RECENTI: " + " | ".join(headlines))
    if lessons.strip():
        lines.append("APPUNTI DEI GIORNI SCORSI:\n" + lessons.strip()[-1200:])
    return "\n".join(lines)


# ---------------- ripiego a sole regole
def rules_decisions(readings: list, positions: list, open_symbols: set, entry_score: int = 70) -> list:
    """Stessa forma delle decisioni di Claude, ma con formule: nessun ragionamento, nessuna notizia."""
    out = []
    by = {r.symbol: r for r in readings}
    for p in positions:
        r = by.get(p["symbol"])
        if r is None:
            continue
        mine = r.long_score if p["side"] == 1 else r.short_score
        theirs = r.short_score if p["side"] == 1 else r.long_score
        if mine < 35 or theirs >= 60:
            out.append({"symbol": p["symbol"], "action": "close", "confidence": 0, "leverage": 1, "margin_usd": 0,
                        "stop_loss_pct": 0, "take_profit_pct": 0, "reason": f"segnale sceso a {mine}"})
    for r in readings:
        if r.symbol in open_symbols or r.side == 0 or r.score < entry_score:
            continue
        frac = min(1.0, (r.score - 60) / 40)
        out.append({"symbol": r.symbol, "action": "open_long" if r.side == 1 else "open_short",
                    "confidence": r.score, "leverage": int(round(3 + frac * 12)),
                    "margin_usd": round(60 + frac * 140, 0), "stop_loss_pct": r.sl_pct,
                    "take_profit_pct": r.tp_pct, "reason": "; ".join(r.why[:3])})
    return out
