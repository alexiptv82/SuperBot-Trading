import ccxt
import asyncio
import time
import uuid
from config import config

# Errori ccxt che vale la pena ritentare con backoff (rate limit, errori di
# rete transitori) -- non si ritenta mai un errore di autenticazione o di
# parametri invalidi, perche' ripetere la stessa richiesta sbagliata non la
# rende giusta e rischia solo di moltiplicare l'effetto di un bug.
_RETRYABLE_ERRORS = (
    ccxt.NetworkError,
    ccxt.RequestTimeout,
    ccxt.ExchangeNotAvailable,
    ccxt.DDoSProtection,
)


class BitGetExchange:
    def __init__(self):
        self.exchange = ccxt.bitget({
            'apiKey': config.BITGET_API_KEY,
            'secret': config.BITGET_SECRET_KEY,
            'password': config.BITGET_PASSPHRASE,
            'options': {'defaultType': 'swap'},
            'sandbox': config.IS_PAPER,
        })

    async def _call(self, fn, *args, **kwargs):
        """Esegue una chiamata ccxt bloccante in un thread, con retry a
        backoff esponenziale sugli errori transitori (rate limit, rete).
        Un errore non transitorio (auth, parametri, fondi insufficienti)
        viene propagato subito, senza ritentare."""
        loop = asyncio.get_event_loop()
        last_err = None
        for attempt in range(config.API_MAX_RETRIES + 1):
            try:
                return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))
            except _RETRYABLE_ERRORS as e:
                last_err = e
                if attempt >= config.API_MAX_RETRIES:
                    break
                delay = config.API_RETRY_BASE_DELAY * (2 ** attempt)
                await asyncio.sleep(delay)
        raise last_err

    @staticmethod
    def _new_client_order_id(symbol: str) -> str:
        # Idempotente per request: se una chiamata va in timeout ed è
        # ritentata (dal nostro backoff o da un retry manuale), l'exchange
        # può riconoscere che è lo stesso ordine invece di aprirne uno
        # duplicato. ccxt mappa 'clientOrderId' nei params sul campo
        # specifico di ciascun exchange (BitGet: clientOid).
        tag = symbol.replace('/', '').replace(':', '')[:10]
        return f"sb-{tag}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"

    async def get_ticker(self, symbol: str) -> dict:
        t = await self._call(self.exchange.fetch_ticker, symbol)
        return {'symbol': symbol, 'price': t['last'], 'bid': t['bid'],
                'ask': t['ask'], 'volume': t['quoteVolume'], 'change_24h': t['percentage']}

    async def get_ohlcv(self, symbol: str, timeframe: str = '1m', limit: int = 100) -> list:
        return await self._call(self.exchange.fetch_ohlcv, symbol, timeframe, limit=limit)

    async def get_balance(self) -> dict:
        if config.IS_PAPER:
            return {'USDT': {'free': config.INITIAL_CAPITAL, 'total': config.INITIAL_CAPITAL}}
        return await self._call(self.exchange.fetch_balance)

    async def create_order(self, symbol, side, quantity, leverage=10,
                           stop_loss=None, take_profit=None) -> dict:
        client_order_id = self._new_client_order_id(symbol)
        if config.IS_PAPER:
            return {'id': f"PAPER_{symbol}_{int(time.time())}", 'symbol': symbol,
                    'side': side, 'amount': quantity, 'status': 'closed', 'paper': True,
                    'client_order_id': client_order_id, 'sl_order_id': None, 'tp_order_id': None}

        await self._call(self.exchange.set_leverage, leverage, symbol)

        # Ordine di apertura con SL/TP condizionali allegati (params unificati
        # ccxt: stopLossPrice/takeProfitPrice -- supportati per i perpetual
        # BitGet). clientOrderId per idempotenza sui retry.
        #
        # ATTENZIONE: i nomi esatti dei parametri per gli ordini condizionali
        # vanno sempre riverificati sulla documentazione ccxt corrente prima
        # di un trade live -- ccxt cambia il mapping per singolo exchange di
        # tanto in tanto. Testare prima in paper/testnet con un trade di
        # importo minimo.
        params = {'clientOrderId': client_order_id}
        if stop_loss is not None:
            params['stopLossPrice'] = stop_loss
        if take_profit is not None:
            params['takeProfitPrice'] = take_profit

        order = await self._call(
            self.exchange.create_order, symbol, 'market', side, quantity, None, params)
        order['client_order_id'] = client_order_id
        # Se l'exchange ha accettato SL/TP come parte dell'ordine di apertura
        # (vedi sopra), non ci sono id separati da tracciare: sono allegati
        # all'ordine/posizione stessa. Li lasciamo None qui; una verifica più
        # granulare (ordini condizionali come entità separate interrogabili)
        # è un miglioramento successivo, non bloccante per l'esecuzione.
        order.setdefault('sl_order_id', None)
        order.setdefault('tp_order_id', None)
        return order

    async def close_position(self, symbol: str, side: str, quantity: float) -> dict:
        """Chiude una posizione aperta con un ordine di mercato reduce-only
        (lato opposto all'apertura). reduce_only impedisce all'exchange di
        aprire accidentalmente una posizione nella direzione sbagliata se la
        quantità non corrisponde esattamente a quella ancora aperta (es. per
        un disallineamento dopo un partial fill)."""
        close_side = 'sell' if side == 'long' else 'buy'
        client_order_id = self._new_client_order_id(symbol)
        if config.IS_PAPER:
            return {'id': f"PAPER_CLOSE_{symbol}_{int(time.time())}", 'symbol': symbol,
                    'side': close_side, 'amount': quantity, 'status': 'closed', 'paper': True,
                    'client_order_id': client_order_id}
        params = {'clientOrderId': client_order_id, 'reduceOnly': True}
        order = await self._call(
            self.exchange.create_order, symbol, 'market', close_side, quantity, None, params)
        order['client_order_id'] = client_order_id
        return order

    async def fetch_open_positions(self, symbols: list | None = None) -> list:
        """Stato reale delle posizioni aperte sull'exchange, per la
        riconciliazione con quanto tracciato localmente. In modalità paper
        non esiste nulla di reale da interrogare: restituisce lista vuota
        (la riconciliazione in paper mode si fida dello stato locale, che è
        l'unica fonte di verità possibile)."""
        if config.IS_PAPER:
            return []
        positions = await self._call(self.exchange.fetch_positions, symbols)
        # Normalizza: teniamo solo le posizioni con size diversa da zero.
        return [p for p in positions if abs(float(p.get('contracts') or p.get('contractSize') or 0)) > 0
                or abs(float((p.get('info') or {}).get('total', 0) or 0)) > 0]

exchange = BitGetExchange()
