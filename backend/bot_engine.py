import asyncio
import json
from datetime import datetime
from typing import Optional
from config import config
from database import Trade, AuditLog, SessionLocal
from exchange import exchange
from signal_engine import signal_engine
from risk_manager import risk_manager

class BotEngine:
    def __init__(self):
        self.is_running = False
        self.capital = config.INITIAL_CAPITAL
        self.daily_pnl = 0.0
        self.open_trades: dict = {}
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self.is_running: return
        self.is_running = True
        self._task = asyncio.create_task(self._main_loop())
        self._log('bot_start', message=f'Bot avviato - modalita {config.TRADING_MODE}')

    async def stop(self):
        self.is_running = False
        if self._task: self._task.cancel()
        self._log('bot_stop', message='Bot fermato')

    async def _main_loop(self):
        while self.is_running:
            try:
                if not risk_manager.check_daily_loss_limit(self.daily_pnl, self.capital):
                    self._log('risk_alert', message=f'Limite perdita giornaliera raggiunto: {self.daily_pnl:.2f} USDT')
                    await self.stop(); break
                await self._monitor_open_trades()
                if risk_manager.can_open_position(len(self.open_trades)):
                    for symbol in config.TRADING_PAIRS:
                        await self._analyze_and_trade(symbol)
                        await asyncio.sleep(2)
                await asyncio.sleep(config.SCALPING_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log('error', message=f'Errore loop: {e}')
                await asyncio.sleep(10)

    async def _analyze_and_trade(self, symbol: str):
        for t in self.open_trades.values():
            if t['symbol'] == symbol: return
        try:
            ohlcv_1m = await exchange.get_ohlcv(symbol, '1m', 100)
            ohlcv_15m = await exchange.get_ohlcv(symbol, '15m', 100)
            ohlcv_1h = await exchange.get_ohlcv(symbol, '1h', 100)
            analysis = signal_engine.analyze(ohlcv_1m, ohlcv_15m, ohlcv_1h)
            if analysis.get('error') or analysis['signal'] == 'hold': return
            ticker = await exchange.get_ticker(symbol)
            price = ticker['price']
            params = risk_manager.calculate_trade_params(
                capital=self.capital, price=price,
                atr=analysis['indicators_1m']['atr'],
                direction=analysis['signal'],
                trade_type=analysis['trade_type'],
                signal_strength=analysis['strength']
            )
            side = 'buy' if analysis['signal'] == 'long' else 'sell'
            order = await exchange.create_order(symbol=symbol, side=side,
                quantity=params['quantity'], leverage=params['leverage'],
                stop_loss=params['stop_loss'], take_profit=params['take_profit'])
            record = {
                'order_id': order['id'], 'symbol': symbol,
                'side': analysis['signal'], 'trade_type': analysis['trade_type'],
                'entry_price': price, 'quantity': params['quantity'],
                'leverage': params['leverage'], 'stop_loss': params['stop_loss'],
                'take_profit': params['take_profit'],
                'indicators_snapshot': json.dumps({
                    'rsi': analysis['indicators_1m']['rsi'],
                    'trend': analysis['main_trend'],
                    'strength': analysis['strength'],
                    'reasons': analysis['reasons']
                }),
            }
            self._save_trade(record)
            self.open_trades[order['id']] = record
            self._log('trade_open', symbol=symbol,
                      message=f"{analysis['signal'].upper()} {symbol} @ {price} | {analysis['trade_type']} | forza:{analysis['strength']}")
        except Exception as e:
            self._log('error', symbol=symbol, message=f'Errore analisi {symbol}: {e}')

    async def _monitor_open_trades(self):
        closed = []
        for oid, trade in self.open_trades.items():
            try:
                ticker = await exchange.get_ticker(trade['symbol'])
                price, sl, tp = ticker['price'], trade['stop_loss'], trade['take_profit']
                close_reason = None
                if trade['side'] == 'long':
                    if price <= sl: close_reason = 'sl'
                    elif price >= tp: close_reason = 'tp'
                else:
                    if price >= sl: close_reason = 'sl'
                    elif price <= tp: close_reason = 'tp'
                if close_reason:
                    pnl = self._calc_pnl(trade['entry_price'], price, trade['quantity'], trade['side'], trade['leverage'])
                    self._close_trade(oid, price, pnl, close_reason)
                    closed.append(oid)
                    self._log('trade_close', symbol=trade['symbol'],
                              message=f"Chiuso {trade['symbol']} PnL:{pnl:.2f} USDT motivo:{close_reason}")
            except Exception as e:
                print(f'Errore monitoraggio: {e}')
        for oid in closed: del self.open_trades[oid]

    def _calc_pnl(self, entry, exit_p, qty, side, leverage) -> float:
        return round(((exit_p - entry) if side == 'long' else (entry - exit_p)) * qty * leverage, 4)

    def _save_trade(self, data: dict):
        db = SessionLocal()
        try:
            db.add(Trade(**{k: v for k, v in data.items() if hasattr(Trade, k)}))
            db.commit()
        finally:
            db.close()

    def _close_trade(self, oid, exit_price, pnl, reason):
        db = SessionLocal()
        try:
            t = db.query(Trade).filter(Trade.order_id == oid).first()
            if t:
                t.exit_price = exit_price; t.pnl = pnl
                t.pnl_percent = (pnl / self.capital) * 100
                t.status = 'closed'; t.close_time = datetime.utcnow(); t.close_reason = reason
                db.commit()
            self.daily_pnl += pnl; self.capital += pnl
        finally:
            db.close()

    def _log(self, event_type, symbol=None, message=''):
        db = SessionLocal()
        try:
            db.add(AuditLog(event_type=event_type, symbol=symbol, message=message))
            db.commit()
        finally:
            db.close()

    def get_status(self) -> dict:
        db = SessionLocal()
        try:
            total = db.query(Trade).count()
            winning = db.query(Trade).filter(Trade.pnl > 0).count()
            return {
                'is_running': self.is_running, 'mode': config.TRADING_MODE,
                'capital': round(self.capital, 2), 'daily_pnl': round(self.daily_pnl, 2),
                'open_positions': len(self.open_trades), 'total_trades': total,
                'win_rate': round((winning / total * 100) if total > 0 else 0, 1),
            }
        finally:
            db.close()

bot = BotEngine()
