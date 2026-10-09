import httpx
import asyncio
import os
from config import config

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        self.enabled = bool(self.token and self.chat_id)
        # Sovrascrivibile solo per i test (un finto server Telegram locale).
        self.api_base = os.getenv('TELEGRAM_API_BASE', 'https://api.telegram.org').rstrip('/')
        # Kill switch bidirezionale: comandi registrati da server.py (per
        # evitare un import circolare telegram_notifier -> bot_engine ->
        # telegram_notifier). Ogni handler è una callable async che
        # restituisce la stringa di risposta da rimandare su Telegram.
        self._command_handlers: dict = {}
        self._offset: int | None = None
        self._polling = False

    def register_command(self, name: str, handler):
        """Registra un comando (senza lo slash iniziale, es. 'halt') con un
        handler `async def handler() -> str`."""
        self._command_handlers[name.lower()] = handler

    async def send(self, message: str) -> bool:
        """Manda un messaggio sul chat configurato. True solo se Telegram lo
        ha accettato (serve a chi deve sapere se e' arrivato, es. il codice
        di recupero password); gli altri chiamanti possono ignorare il valore."""
        if not self.enabled:
            return False
        try:
            url = f"{self.api_base}/bot{self.token}/sendMessage"
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                }, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            print(f"Telegram error: {e}")
            return False

    async def trade_opened(self, symbol, side, price, leverage, trade_type, strength, profile_label=None):
        emoji = "🟢" if side == "long" else "🔴"
        direction = "LONG" if side == "long" else "SHORT"
        msg = (
            f"{emoji} <b>TRADE APERTO</b>\n"
            f"📊 {symbol} — {direction} x{leverage}\n"
            f"💰 Prezzo: ${price:,.2f}\n"
            f"⚡ Tipo: {trade_type.upper()}\n"
            f"💪 Forza segnale: {strength}/100"
        )
        if profile_label:
            msg += f"\n🎯 Profilo: {profile_label}"
        await self.send(msg)

    async def trade_closed(self, symbol, side, pnl, reason, profile_label=None):
        if pnl > 0:
            emoji = "✅"
            pnl_str = f"+${pnl:.2f}"
        else:
            emoji = "❌"
            pnl_str = f"-${abs(pnl):.2f}"
        reason_map = {"tp": "Take Profit 🎯", "sl": "Stop Loss 🛑", "manual": "Manuale",
                      "liq": "Liquidazione 💥"}
        msg = (
            f"{emoji} <b>TRADE CHIUSO</b>\n"
            f"📊 {symbol}\n"
            f"💵 P&L: <b>{pnl_str}</b>\n"
            f"📋 Motivo: {reason_map.get(reason, reason)}"
        )
        if profile_label:
            msg += f"\n🎯 Profilo: {profile_label}"
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

    async def poll_commands(self):
        """Long-polling su getUpdates per i comandi in ingresso (kill
        switch). Gira indipendentemente dallo stato is_running del bot, così
        /resume può sempre arrivare anche a bot fermo. Accetta comandi solo
        dal chat_id configurato: un messaggio da chiunque altro viene
        ignorato silenziosamente (niente eco che confermi al mittente che il
        bot esiste e reagisce ai suoi messaggi)."""
        if not self.enabled or not config.TELEGRAM_COMMANDS_ENABLED:
            return
        self._polling = True
        url = f"{self.api_base}/bot{self.token}/getUpdates"
        async with httpx.AsyncClient() as client:
            while self._polling:
                try:
                    params = {'timeout': 25}
                    if self._offset is not None:
                        params['offset'] = self._offset
                    resp = await client.get(url, params=params, timeout=30)
                    data = resp.json()
                    for update in data.get('result', []):
                        self._offset = update['update_id'] + 1
                        await self._handle_update(update)
                except Exception as e:
                    print(f"Telegram poll_commands error: {e}")
                    await asyncio.sleep(5)

    def stop_polling(self):
        self._polling = False

    async def _handle_update(self, update: dict):
        msg = update.get('message') or {}
        text = (msg.get('text') or '').strip()
        from_chat = str((msg.get('chat') or {}).get('id', ''))
        if not text.startswith('/'):
            return
        if from_chat != str(self.chat_id):
            print(f"Comando Telegram ignorato da chat_id non autorizzato: {from_chat}")
            return
        command = text[1:].split()[0].lower()
        handler = self._command_handlers.get(command)
        if not handler:
            await self.send(f"❓ Comando non riconosciuto: /{command}")
            return
        try:
            reply = await handler()
        except Exception as e:
            reply = f"⚠️ Errore eseguendo /{command}: {e}"
        if reply:
            await self.send(reply)

notifier = TelegramNotifier()
