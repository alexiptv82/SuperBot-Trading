"""Notifiche Telegram per la sala segnali V2.

Usa solo stdlib (urllib.request) — nessuna dipendenza esterna.
Se le variabili d'ambiente non sono impostate, ogni chiamata è no-op silenzioso.
"""
from __future__ import annotations

import json
import os
import urllib.request


def _send(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        body = json.dumps({"chat_id": chat_id, "text": text,
                           "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass   # Telegram non blocca mai il bot


# ── Contesto: chi sta scrivendo (Hawk/Bull) e se e' live o non reale ─────────────────────────────
# Impostato una volta da cli.py all'avvio. Senza contesto (es. prova di collegamento) i messaggi restano
# come prima, senza intestazione.
_CTX: dict = {"portfolio": None, "live": False, "scale": 1.0}
_BOT_EMOJI = {"hawk": "🦅", "bull": "🐂"}


def set_context(portfolio: str, live: bool, scale: float = 1.0) -> None:
    """portfolio: "hawk"/"bull". live: il bot manda ordini veri. scale: capitale assegnato / conto di
    riferimento del motore (1000$): in live gli importi mostrati sono quelli REALI (importo del motore x scala)."""
    try:
        sc = float(scale)
    except (TypeError, ValueError):
        sc = 1.0
    _CTX.update(portfolio=(portfolio or "").strip().lower() or None, live=bool(live),
                scale=sc if sc > 0 else 1.0)


def _k() -> float:
    """Fattore per gli importi in dollari mostrati: la scala in live, 1 in paper (li' non c'e' nulla di reale)."""
    return _CTX["scale"] if _CTX["live"] else 1.0


def _header() -> str:
    name = _CTX["portfolio"]
    if not name:
        return ""
    bot = f"{_BOT_EMOJI.get(name, '🤖')} {name.capitalize()}"
    if _CTX["live"]:
        sc = _CTX["scale"]
        tail = f" · ordini al {sc * 100:.0f}%" if abs(sc - 1.0) > 1e-9 else ""
        return f"🔴 <b>LIVE</b> · {bot}{tail}"
    return f"⚪ <b>NON REALE</b> · {bot}"


def _tag(text: str) -> str:
    h = _header()
    return f"{h}\n{text}" if h else text


def notify_open(symbol: str, side: int, price: float, leverage: int,
                margin: float, trade_type: str, confidence: int,
                source: str, reason: str) -> None:
    emoji = "🟢" if side == 1 else "🔴"
    dir_str = "LONG" if side == 1 else "SHORT"
    src_tag = "🤖 Claude" if source == "claude" else "📐 Regole"
    _send(_tag(
        f"{emoji} <b>APERTO {symbol}</b> — {dir_str} x{leverage}\n"
        f"💰 Prezzo: {price:.5g}  Margine: {margin * _k():.0f}$\n"
        f"⚡ Tipo: {trade_type.upper()}  Conf: {confidence}/100\n"
        f"🔎 {src_tag} — {reason[:120]}"
    ))


def notify_close(symbol: str, net: float, reason: str, why: str) -> None:
    net = net * _k()
    emoji = "✅" if net >= 0 else "❌"
    sign = "+" if net >= 0 else ""
    why_map = {
        "stop loss": "Stop Loss 🛑",
        "take profit": "Take Profit 🎯",
        "liquidazione": "Liquidazione 💥",
        "chiusura Claude": "Claude 🤖",
        "chiusura manuale": "Chiusa da te ✋",
    }
    why_label = why_map.get(why, why)
    _send(_tag(
        f"{emoji} <b>CHIUSO {symbol}</b>\n"
        f"💵 P&L netto: <b>{sign}{net:.2f}$</b>\n"
        f"📋 {why_label} — {reason[:100]}"
    ))


def notify_dca(symbol: str, dca_count: int, price: float,
               new_entry: float, total_margin: float) -> None:
    _send(_tag(
        f"➕ <b>DCA #{dca_count} {symbol}</b>\n"
        f"📍 @{price:.5g}  Entry media: {new_entry:.5g}\n"
        f"💰 Margine totale: {total_margin * _k():.0f}$"
    ))


def notify_split(symbol: str, side: int, price: float, new_entry: float, total_margin: float) -> None:
    dir_str = "LONG" if side == 1 else "SHORT"
    _send(_tag(
        f"🧩 <b>2ª GAMBA {symbol}</b> — {dir_str}\n"
        f"📍 @{price:.5g}  Entry medio: {new_entry:.5g}\n"
        f"💰 Margine totale: {total_margin * _k():.0f}$"
    ))


def notify_halt(reason: str) -> None:
    _send(_tag(f"⛔ <b>HALT</b> — {reason}"))


def notify_daily_report(equity: float, cash: float, day_pnl: float,
                        n_open: int, n_closed_today: int,
                        pnl_closed_today: float, budget_spent: float) -> None:
    k = _k()
    equity, cash, day_pnl, pnl_closed_today = equity * k, cash * k, day_pnl * k, pnl_closed_today * k
    emoji = "📈" if day_pnl >= 0 else "📉"
    _send(_tag(
        f"{emoji} <b>REPORT GIORNALIERO</b>\n"
        f"💰 Equity: {equity:.2f}$  Cash: {cash:.2f}$\n"
        f"📊 P&L oggi: {day_pnl:+.2f}$  (chiusi: {n_closed_today}, netto: {pnl_closed_today:+.2f}$)\n"
        f"📂 Posizioni aperte: {n_open}\n"
        f"🤖 Budget Claude usato: {budget_spent:.3f}$"
    ))


def notify_live_alert(text: str) -> None:
    """Avviso sul collegamento con l'exchange (blocco aperture, chiusura non riuscita, ecc.)."""
    _send(_tag("⚠️ <b>AVVISO</b>\n" + str(text)[:900]))
