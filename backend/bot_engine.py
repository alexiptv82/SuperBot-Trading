import asyncio
import json
from datetime import datetime
from typing import Optional
from config import config
from database import Trade, AuditLog, SessionLocal
from exchange import exchange
from signal_engine import signal_engine
from risk_manager import risk_manager
try:
    from backend.telegram_notifier import notifier
except ImportError:
    from telegram_notifier import notifier

class BotEngine:
    def __init__(self):
        self.is_running = False
        self.capital = config.INITIAL_CAPITAL
        self.daily_pnl = 0.0
        self.open_trades: dict = {}
        self._task: Optional[asyncio.Task] = None
        self._cycle_count = 0

    async def start(self):
        if self.is_running: return
        # Ripristina lo stato dei trade aperti dal DB (il processo può essere
        # stato riavviato con posizioni ancora aperte sull'exchange) e poi
        # riconcilia con la realtà sull'exchange, prima di iniziare ad agire.
        self._reload_open_trades()
        await self._reconcile_positions()
        self.is_running = True
        self._task = asyncio.create_task(self._main_loop())
        self._log('bot_start', message=f'Bot avviato - modalita {config.TRADING_MODE}')
        asyncio.create_task(notifier.send("🤖 <b>SuperBot avviato!</b>\nModalità: " + config.TRADING_MODE.upper()))

    async def stop(self):
        self.is_running = False
        if self._task: self._task.cancel()
        self._log('bot_stop', message='Bot fermato')
        asyncio.create_task(notifier.send("⏹️ <b>SuperBot fermato</b>"))

    def _reload_open_trades(self):
        """Ricarica in memoria i trade con status='open' dal DB. Necessario
        perché self.open_trades vive solo in RAM: senza questo, un riavvio
        del processo con posizioni ancora aperte le farebbe "sparire" dal
        punto di vista del bot (continuerebbe a tracciarle come chiuse/mai
        esistite), pur restando aperte e a rischio sull'exchange."""
        db = SessionLocal()
        try:
            rows = db.query(Trade).filter(Trade.status == 'open').all()
            for t in rows:
                self.open_trades[t.order_id] = {
                    'order_id': t.order_id, 'symbol': t.symbol, 'side': t.side,
                    'trade_type': t.trade_type, 'entry_price': t.entry_price,
                    'quantity': t.quantity, 'leverage': t.leverage,
                    'stop_loss': t.stop_loss, 'take_profit': t.take_profit,
                    'client_order_id': t.client_order_id,
                }
            if rows:
                self._log('reload', message=f'Ricaricati {len(rows)} trade aperti dal DB')
        finally:
            db.close()

    async def _reconcile_positions(self):
        """Confronta lo stato locale (self.open_trades) con le posizioni
        reali sull'exchange. In paper mode non esiste nulla da riconciliare
        (fetch_open_positions ritorna sempre lista vuota): lo stato locale è
        l'unica fonte di verità. In live mode:
        - una posizione reale per un symbol che non abbiamo tracciato
          localmente viene segnalata (non la chiudiamo né la adottiamo
          automaticamente: può essere stata aperta manualmente, meglio un
          alert che un'azione automatica su qualcosa che non abbiamo aperto
          noi);
        - un trade tracciato come aperto localmente ma senza controparte
          reale sull'exchange viene considerato chiuso (probabilmente da
          SL/TP condizionale) e marcato come tale nel DB con il prezzo
          corrente come stima del prezzo di uscita."""
        if config.IS_PAPER:
            return
        try:
            positions = await exchange.fetch_open_positions()
        except Exception as e:
            self._log('error', message=f'Riconciliazione fallita (fetch posizioni): {e}')
            return
        real_symbols = {p.get('symbol') for p in positions if p.get('symbol')}
        local_symbols = {t['symbol'] for t in self.open_trades.values()}

        orphan_real = real_symbols - local_symbols
        if orphan_real:
            msg = f"Posizioni aperte sull'exchange non tracciate localmente: {', '.join(orphan_real)}"
            self._log('reconcile_alert', message=msg)
            asyncio.create_task(notifier.send(f"⚠️ <b>Riconciliazione</b>\n{msg}"))

        missing_local = []
        for oid, trade in list(self.open_trades.items()):
            if trade['symbol'] not in real_symbols:
                missing_local.append((oid, trade))
        for oid, trade in missing_local:
            try:
                ticker = await exchange.get_ticker(trade['symbol'])
                price = ticker['price']
            except Exception:
                price = trade['entry_price']
            pnl = self._calc_pnl(trade['entry_price'], price, trade['quantity'], trade['side'], trade['leverage'])
            self._close_trade(oid, price, pnl, 'reconciled_missing')
            del self.open_trades[oid]
            msg = f"{trade['symbol']} risultava aperto localmente ma non sull'exchange: chiuso per riconciliazione (stima PnL {pnl:.2f} USDT)"
            self._log('reconcile_close', symbol=trade['symbol'], message=msg)
            asyncio.create_task(notifier.send(f"⚠️ <b>Riconciliazione</b>\n{msg}"))

    async def _main_loop(self):
        while self.is_running:
            try:
                if not risk_manager.check_daily_loss_limit(self.daily_pnl, self.capital):
                    self._log('risk_alert', message=f'Limite perdita giornaliera raggiunto: {self.daily_pnl:.2f} USDT')
                    await self.stop(); break
                self._cycle_count += 1
                if (not config.IS_PAPER) and self._cycle_count % config.RECONCILE_EVERY_N_CYCLES == 0:
                    await self._reconcile_positions()
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

    def _sanity_check_ohlcv(self, symbol: str, ohlcv: list, timeframe: str) -> Optional[str]:
        """Controlli minimi di qualità sui dati OHLCV prima di darli in pasto
        al signal engine: un bug/outage a monte (candele vuote, prezzi NaN,
        volume a zero, timestamp fermo o fuori ordine) non deve tradursi in
        un segnale di trading calcolato su dati spazzatura. Ritorna una
        stringa col motivo se i dati non sono affidabili, altrimenti None."""
        if not ohlcv or len(ohlcv) < 20:
            return f'{timeframe}: solo {len(ohlcv) if ohlcv else 0} candele (minimo 20)'
        last = ohlcv[-1]
        if len(last) < 6:
            return f'{timeframe}: candela malformata'
        ts, o, h, l, c, v = last[:6]
        for name, val in (('open', o), ('high', h), ('low', l), ('close', c)):
            if val is None or val != val or val <= 0:  # val != val -> NaN
                return f'{timeframe}: {name} non valido ({val})'
        if v is None or v != v or v < 0:
            return f'{timeframe}: volume non valido ({v})'
        if h < l or c > h or c < l or o > h or o < l:
            return f'{timeframe}: range OHLC incoerente (o={o} h={h} l={l} c={c})'
        tf_minutes = {'1m': 1, '15m': 15, '1h': 60}.get(timeframe, 1)
        now_ms = datetime.utcnow().timestamp() * 1000
        if ts is None or (now_ms - ts) > tf_minutes * 60 * 1000 * 5:
            return f'{timeframe}: ultima candela troppo vecchia (età ~{(now_ms - ts) / 60000:.1f} min)'
        timestamps = [row[0] for row in ohlcv if row and row[0] is not None]
        if any(t2 <= t1 for t1, t2 in zip(timestamps, timestamps[1:])):
            return f'{timeframe}: timestamp non monotoni'
        return None

    async def _analyze_and_trade(self, symbol: str):
        for t in self.open_trades.values():
            if t['symbol'] == symbol: return
        try:
            ohlcv_1m = await exchange.get_ohlcv(symbol, '1m', 100)
            ohlcv_15m = await exchange.get_ohlcv(symbol, '15m', 100)
            ohlcv_1h = await exchange.get_ohlcv(symbol, '1h', 100)
            for tf, data in (('1m', ohlcv_1m), ('15m', ohlcv_15m), ('1h', ohlcv_1h)):
                reason = self._sanity_check_ohlcv(symbol, data, tf)
                if reason:
                    self._log('data_sanity_fail', symbol=symbol, message=f'Dati scartati per {symbol}: {reason}')
                    return
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
                'client_order_id': order.get('client_order_id'),
                'sl_order_id': order.get('sl_order_id'),
                'tp_order_id': order.get('tp_order_id'),
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
            asyncio.create_task(notifier.trade_opened(
                symbol, analysis['signal'], price,
                params['leverage'], analysis['trade_type'], analysis['strength']
            ))
        except Exception as e:
            self._log('error', symbol=symbol, message=f'Errore analisi {symbol}: {e}')

    async def _monitor_open_trades(self):
        if config.IS_PAPER:
            await self._monitor_open_trades_paper()
        else:
            await self._monitor_open_trades_live()

    async def _monitor_open_trades_paper(self):
        """Simulazione locale: in paper mode non esistono ordini condizionali
        reali sull'exchange, quindi SL/TP restano soglie di prezzo
        confrontate qui ad ogni ciclo (comportamento inalterato)."""
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
                    asyncio.create_task(notifier.trade_closed(
                        trade['symbol'], trade['side'], pnl, close_reason
                    ))
            except Exception as e:
                print(f'Errore monitoraggio: {e}')
        for oid in closed: del self.open_trades[oid]

    async def _monitor_open_trades_live(self):
        """In live mode gli SL/TP sono ordini condizionali reali piazzati
        sull'exchange al momento dell'apertura (vedi exchange.create_order):
        il bot non deve più confrontare il prezzo corrente con le soglie
        locali per decidere se chiudere -- quella decisione è già presa
        dall'exchange. Qui rileviamo solo che una posizione tracciata
        localmente non esiste più sull'exchange (quindi è stata chiusa, da
        SL, TP o manualmente) e aggiorniamo lo stato locale di conseguenza."""
        if not self.open_trades:
            return
        try:
            positions = await exchange.fetch_open_positions()
        except Exception as e:
            print(f'Errore monitoraggio (fetch posizioni): {e}')
            return
        real_symbols = {p.get('symbol') for p in positions if p.get('symbol')}
        closed = []
        for oid, trade in self.open_trades.items():
            if trade['symbol'] in real_symbols:
                continue
            try:
                ticker = await exchange.get_ticker(trade['symbol'])
                price = ticker['price']
            except Exception:
                price = trade.get('take_profit', trade['entry_price'])
            # Non sappiamo con certezza se la chiusura è stata causata da SL
            # o da TP (l'ordine condizionale scattato non ci è ancora
            # riportato come evento separato) -- stimiamo dal lato più vicino
            # al prezzo corrente rispetto a entry, a scopo di sola etichetta;
            # il PnL è comunque calcolato sul prezzo corrente reale.
            close_reason = 'sl_or_tp'
            pnl = self._calc_pnl(trade['entry_price'], price, trade['quantity'], trade['side'], trade['leverage'])
            self._close_trade(oid, price, pnl, close_reason)
            closed.append(oid)
            self._log('trade_close', symbol=trade['symbol'],
                      message=f"Chiuso {trade['symbol']} PnL:{pnl:.2f} USDT motivo:{close_reason} (rilevato da riconciliazione posizioni)")
            asyncio.create_task(notifier.trade_closed(
                trade['symbol'], trade['side'], pnl, close_reason
            ))
        for oid in closed: del self.open_trades[oid]

    def _calc_pnl(self, entry, exit_p, qty, side, leverage) -> float:
        # `qty` e' gia' la size reale della posizione mandata all'exchange
        # (exchange.create_order invia `quantity` cosi' com'e', la leva viene
        # impostata separatamente con set_leverage e incide solo sul margine
        # richiesto, non sul PnL per movimento di prezzo). Moltiplicare di
        # nuovo per `leverage` qui gonfiava il PnL (e quindi capitale e
        # daily_pnl) di un fattore leva rispetto a quello che accadrebbe
        # davvero sull'exchange. `leverage` resta nella firma per i chiamanti
        # esistenti e per eventuale logging, ma non entra piu' nel calcolo.
        return round(((exit_p - entry) if side == 'long' else (entry - exit_p)) * qty, 4)

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

    async def close_all_positions(self, reason='manual_telegram'):
        """Chiude tutte le posizioni aperte con un ordine reduce-only
        (usato dal kill switch Telegram /closeall). Ritorna la lista dei
        symbol chiusi, per confermare l'esito a chi ha dato il comando."""
        closed_symbols = []
        for oid, trade in list(self.open_trades.items()):
            try:
                if not config.IS_PAPER:
                    await exchange.close_position(trade['symbol'], trade['side'], trade['quantity'])
                ticker = await exchange.get_ticker(trade['symbol'])
                price = ticker['price']
                pnl = self._calc_pnl(trade['entry_price'], price, trade['quantity'], trade['side'], trade['leverage'])
                self._close_trade(oid, price, pnl, reason)
                del self.open_trades[oid]
                closed_symbols.append(trade['symbol'])
                asyncio.create_task(notifier.trade_closed(trade['symbol'], trade['side'], pnl, reason))
            except Exception as e:
                self._log('error', symbol=trade['symbol'], message=f"Errore chiusura manuale {trade['symbol']}: {e}")
        return closed_symbols

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
