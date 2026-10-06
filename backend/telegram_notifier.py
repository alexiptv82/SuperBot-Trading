import httpx
import asyncio
import os

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        self.enabled = bool(self.token and self.chat_id)

    async def send(self, message: str):
        if not self.enabled:
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            async with httpx.AsyncClient() as client:
                await client.post(url, json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                }, timeout=10)
        except Exception as e:
            print(f"Telegram error: {e}")

    async def trade_opened(self, symbol, side, price, leverage, trade_type, strength):
        emoji = "🟢" if side == "long" else "🔴"
        direction = "LONG" if side == "long" else "SHORT"
        msg = (
            f"{emoji} <b>TRADE APERTO</b>\n"
            f"📊 {symbol} — {direction} x{leverage}\n"
            f"💰 Prezzo: ${price:,.2f}\n"
            f"⚡ Tipo: {trade_type.upper()}\n"
            f"💪 Forza segnale: {strength}/100"
        )
        await self.send(msg)

    async def trade_closed(self, symbol, side, pnl, reason):
        if pnl > 0:
            emoji = "✅"
            pnl_str = f"+${pnl:.2f}"
        else:
            emoji = "❌"
            pnl_str = f"-${abs(pnl):.2f}"
        reason_map = {"tp": "Take Profit 🎯", "sl": "Stop Loss 🛑", "manual": "Manuale"}
        msg = (
            f"{emoji} <b>TRADE CHIUSO</b>\n"
            f"📊 {symbol}\n"
            f"💵 P&L: <b>{pnl_str}</b>\n"
            f"📋 Motivo: {reason_map.get(reason, reason)}"
        )
        await self.send(msg)

    async def daily_report(self, capital, daily_pnl, total_trades, win_rate):
        emoji = "📈" if daily_pnl >= 0 else "📉"
        msg = (
            f"{emoji} <b>REPORT GIORNALIERO</b>\n"
            f"💰 Capitale: ${capital:,.2f}\n"
            f"📊 P&L oggi: ${daily_pnl:+.2f}\n"
            f"🔢 Trade totali: {total_trades}\n"
            f"🏆 Win rate: {win_rate:.1f}%"
        )
        await self.send(msg)

    async def risk_alert(self, message: str):
        await self.send(f"⚠️ <b>ALERT RISCHIO</b>\n{message}")

notifier = TelegramNotifier()
