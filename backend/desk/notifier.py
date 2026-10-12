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


def notify_open(symbol: str, side: int, price: float, leverage: int,
                margin: float, trade_type: str, confidence: int,
                source: str, reason: str) -> None:
    emoji = "🟢" if side == 1 else "🔴"
    dir_str = "LONG" if side == 1 else "SHORT"
    src_tag = "🤖 Claude" if source == "claude" else "📐 Regole"
    _send(
        f"{emoji} <b>APERTO {symbol}</b> — {dir_str} x{leverage}\n"
        f"💰 Prezzo: {price:.5g}  Margine: {margin:.0f}$\n"
        f"⚡ Tipo: {trade_type.upper()}  Conf: {confidence}/100\n"
        f"🔎 {src_tag} — {reason[:120]}"
    )


def notify_close(symbol: str, net: float, reason: str, why: str) -> None:
    emoji = "✅" if net >= 0 else "❌"
    sign = "+" if net >= 0 else ""
    why_map = {
        "stop loss": "Stop Loss 🛑",
        "take profit": "Take Profit 🎯",
        "liquidazione": "Liquidazione 💥",
        "chiusura Claude": "Claude 🤖",
    }
    why_label = why_map.get(why, why)
    _send(
        f"{emoji} <b>CHIUSO {symbol}</b>\n"
        f"💵 P&L netto: <b>{sign}{net:.2f}$</b>\n"
        f"📋 {why_label} — {reason[:100]}"
    )


def notify_dca(symbol: str, dca_count: int, price: float,
               new_entry: float, total_margin: float) -> None:
    _send(
        f"➕ <b>DCA #{dca_count} {symbol}</b>\n"
        f"📍 @{price:.5g}  Entry media: {new_entry:.5g}\n"
        f"💰 Margine totale: {total_margin:.0f}$"
    )


def notify_halt(reason: str) -> None:
    _send(f"⛔ <b>HALT</b> — {reason}")


def notify_daily_report(equity: float, cash: float, day_pnl: float,
                        n_open: int, n_closed_today: int,
                        pnl_closed_today: float, budget_spent: float) -> None:
    emoji = "📈" if day_pnl >= 0 else "📉"
    _send(
        f"{emoji} <b>REPORT GIORNALIERO</b>\n"
        f"💰 Equity: {equity:.2f}$  Cash: {cash:.2f}$\n"
        f"📊 P&L oggi: {day_pnl:+.2f}$  (chiusi: {n_closed_today}, netto: {pnl_closed_today:+.2f}$)\n"
        f"📂 Posizioni aperte: {n_open}\n"
        f"🤖 Budget Claude usato: {budget_spent:.3f}$"
    )
