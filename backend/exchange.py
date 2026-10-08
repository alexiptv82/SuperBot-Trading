import ccxt
import asyncio
from config import config

class BitGetExchange:
    def __init__(self):
        self.exchange = ccxt.bitget({
            'apiKey': config.BITGET_API_KEY,
            'secret': config.BITGET_SECRET_KEY,
            'password': config.BITGET_PASSPHRASE,
            'options': {'defaultType': 'swap'},
            'sandbox': config.IS_PAPER,
        })

    async def get_ticker(self, symbol: str) -> dict:
        loop = asyncio.get_event_loop()
        t = await loop.run_in_executor(None, self.exchange.fetch_ticker, symbol)
        return {'symbol': symbol, 'price': t['last'], 'bid': t['bid'],
                'ask': t['ask'], 'volume': t['quoteVolume'], 'change_24h': t['percentage']}

    async def get_ohlcv(self, symbol: str, timeframe: str = '1m', limit: int = 100) -> list:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit))

    async def get_funding_rate(self, symbol: str) -> dict | None:
        """Funding rate corrente per un perpetual (BTC/ETH tipicamente; per
        XAU/XAG dipende se BitGet li tratta come swap con funding o no).
        Ritorna None se il simbolo non supporta il funding rate o la
        chiamata fallisce -- mai un'eccezione, visto che questo e' usato
        solo per un filtro informativo in V0.5 (shadow mode), non deve mai
        far fallire il ciclo di analisi."""
        try:
            loop = asyncio.get_event_loop()
            fr = await loop.run_in_executor(None, self.exchange.fetch_funding_rate, symbol)
            return {
                'symbol': symbol,
                'funding_rate': fr.get('fundingRate'),
                'next_funding_time': fr.get('fundingTimestamp'),
            }
        except Exception:
            return None

    async def get_balance(self) -> dict:
        if config.IS_PAPER:
            return {'USDT': {'free': config.INITIAL_CAPITAL, 'total': config.INITIAL_CAPITAL}}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.exchange.fetch_balance)

    async def create_order(self, symbol, side, quantity, leverage=10,
                           stop_loss=None, take_profit=None) -> dict:
        if config.IS_PAPER:
            import time
            return {'id': f"PAPER_{symbol}_{int(time.time())}", 'symbol': symbol,
                    'side': side, 'amount': quantity, 'status': 'closed', 'paper': True}
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self.exchange.set_leverage(leverage, symbol))
        return await loop.run_in_executor(
            None, lambda: self.exchange.create_market_order(symbol, side, quantity))

exchange = BitGetExchange()
