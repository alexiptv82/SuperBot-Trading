import asyncio
import json
from datetime import datetime, date
from typing import Optional

from sqlalchemy import case, func

from config import config
from database import Trade, AuditLog, SessionLocal
from exchange import exchange
from signal_engine import signal_engine
from risk_manager import risk_manager
import risk_profiles as rp
try:
    from backend.telegram_notifier import notifier
except ImportError:
    from telegram_notifier import notifier


class Portfolio:
    """Un portafoglio virtuale (o, in modalita' reale, l'unico conto).

    Ogni profilo di rischio (Conservativo / Aggressivo) ha il suo: capitale,
    P&L giornaliero e posizioni aperte sono indipendenti, cosi' i due profili
    si confrontano a parita' di mercato. `profile=None` e' il portafoglio
    'legacy': contiene soltanto i trade aperti prima dell'introduzione dei
    profili, che vengono portati a chiusura ma non ne apre di nuovi."""

    def __init__(self, name: str, profile: Optional[rp.Profile]):
        self.name = name
        self.profile = profile
        self.active = False
        self.capital = config.INITIAL_CAPITAL
        self.daily_pnl = 0.0
        self.day: date = datetime.utcnow().date()
        self.halted_day: Optional[date] = None   # giorno in cui ha toccato il limite di perdita
        self.open_trades: dict = {}

    @property
    def label(self) -> str:
        return rp.PROFILE_LABELS.get(self.name, self.name)


class BotEngine:
    def __init__(self):
        self.is_running = False
        self.portfolios: dict[str, Portfolio] = {
            name: Portfolio(name, profile) for name, profile in rp.PRESETS.items()
        }
        self.portfolios['legacy'] = Portfolio('legacy', None)
        self._task: Optional[asyncio.Task] = None
        self._cycle_count = 0
        self._sync_active()

    # ── Accesso aggregato (compatibilita' con server.py e paper_test_runner) ──

    def _visible(self) -> list:
        return [pf for pf in self.portfolios.values() if pf.active or pf.open_trades]

    @property
    def open_trades(self) -> dict:
        merged = {}
        for pf in self.portfolios.values():
            merged.update(pf.open_trades)
        return merged

    @property
    def capital(self) -> float:
        return sum(pf.capital for pf in self._visible())

    @property
    def daily_pnl(self) -> float:
        return sum(pf.daily_pnl for pf in self._visible())

    # ── Modalita' di rischio ────────────────────────────────────────────────

    def _effective_mode(self) -> str:
        """In modalita' reale c'e' un solo conto: vale sempre e solo il
        profilo Conservativo, qualunque cosa sia salvata nelle impostazioni."""
        if not config.IS_PAPER:
            return 'conservative'
        return config.RISK_MODE if config.RISK_MODE in rp.RISK_MODES else 'both'

    def _sync_active(self):
        active = set(rp.modes_to_profiles(self._effective_mode()))
        for name, pf in self.portfolios.items():
            pf.active = name in active

    def _fee_frac(self) -> float:
        return config.PAPER_FEE_BPS / 10_000.0

    def _slip_frac(self) -> float:
        return config.PAPER_SLIPPAGE_BPS / 10_000.0

    def _effective_profile(self, pf: Portfolio) -> rp.Profile:
        """Profilo con il tetto di leva dell'utente: in reale la 'Leva
        massima' delle Impostazioni e' un limite assoluto; in simulazione i
        profili usano le proprie leve (Aggressivo fino a 30x)."""
        if config.IS_PAPER:
            return pf.profile
        return rp.with_leverage_ceiling(pf.profile, config.MAX_LEVERAGE)

    # ── Avvio / arresto ─────────────────────────────────────────────────────

    async def start(self):
        if self.is_running: return
        # Ripristina lo stato dal DB (capitale, P&L di oggi, trade aperti: il
        # processo puo' essere stato riavviato con posizioni ancora aperte) e
        # poi riconcilia con la realta' sull'exchange, prima di agire.
        self._sync_active()
        self._reload_state()
        await self._reconcile_positions()
        self.is_running = True
        self._task = asyncio.create_task(self._main_loop())
        self._log('bot_start', message=f'Bot avviato - modalita {config.TRADING_MODE} - rischio {self._effective_mode()}')
        asyncio.create_task(notifier.send("🤖 <b>SuperBot avviato!</b>\nModalità: " + config.TRADING_MODE.upper()
                                          + "\nProfilo: " + self._mode_label()))

    async def stop(self):
        self.is_running = False
        if self._task: self._task.cancel()
        self._log('bot_stop', message='Bot fermato')
        asyncio.create_task(notifier.send("⏹️ <b>SuperBot fermato</b>"))

    def _mode_label(self) -> str:
        mode = self._effective_mode()
        return 'Entrambi' if mode == 'both' else rp.PROFILE_LABELS.get(mode, mode)

    def _reload_state(self):
        """Ricostruisce dal DB, per ogni portafoglio: capitale (iniziale + P&L
        netto dei trade chiusi), P&L di oggi (UTC) e trade ancora aperti.
        Prima il capitale restava in RAM e tornava a INITIAL_CAPITAL a ogni
        riavvio, e il P&L giornaliero non si azzerava mai."""
        db = SessionLocal()
        try:
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            loaded = 0
            for name, pf in self.portfolios.items():
                flt = (Trade.profile == name) if name != 'legacy' else Trade.profile.is_(None)
                pf.open_trades = {}
                pf.day = datetime.utcnow().date()
                pf.halted_day = None
                closed_pnl = db.query(func.coalesce(func.sum(Trade.pnl), 0.0)).filter(
                    flt, Trade.status == 'closed').scalar() or 0.0
                pf.capital = config.INITIAL_CAPITAL + float(closed_pnl)
                today_pnl = db.query(func.coalesce(func.sum(Trade.pnl), 0.0)).filter(
                    flt, Trade.status == 'closed', Trade.close_time >= today).scalar() or 0.0
                pf.daily_pnl = float(today_pnl)
                for t in db.query(Trade).filter(flt, Trade.status == 'open').all():
                    pf.open_trades[t.order_id] = {
                        'order_id': t.order_id, 'symbol': t.symbol, 'side': t.side,
                        'trade_type': t.trade_type, 'entry_price': t.entry_price,
                        'quantity': t.quantity, 'leverage': t.leverage,
                        'stop_loss': t.stop_loss, 'take_profit': t.take_profit,
                        'client_order_id': t.client_order_id,
                        'profile': t.profile, 'margin': t.margin, 'liq_price': t.liq_price,
                    }
                    loaded += 1
            if loaded:
                self._log('reload', message=f'Ricaricati {loaded} trade aperti dal DB')
        finally:
            db.close()

    async def _reconcile_positions(self):
        """Confronta lo stato locale (trade aperti dei portafogli) con le
        posizioni reali sull'exchange. In paper mode non esiste nulla da
        riconciliare (fetch_open_positions ritorna sempre lista vuota): lo
        stato locale è l'unica fonte di verità. In live mode:
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
        local_symbols = {t['symbol'] for pf in self.portfolios.values() for t in pf.open_trades.values()}

        orphan_real = real_symbols - local_symbols
        if orphan_real:
            msg = f"Posizioni aperte sull'exchange non tracciate localmente: {', '.join(orphan_real)}"
            self._log('reconcile_alert', message=msg)
            asyncio.create_task(notifier.send(f"⚠️ <b>Riconciliazione</b>\n{msg}"))

        missing_local = []
        for pf in self.portfolios.values():
            for oid, trade in list(pf.open_trades.items()):
                if trade['symbol'] not in real_symbols:
                    missing_local.append((pf, oid, trade))
        for pf, oid, trade in missing_local:
            try:
                ticker = await exchange.get_ticker(trade['symbol'])
                price = ticker['price']
            except Exception:
                price = trade['entry_price']
            pnl = self._calc_pnl(trade['entry_price'], price, trade['quantity'], trade['side'], trade['leverage'])
            self._close_trade(pf, oid, price, pnl, 'reconciled_missing')
            del pf.open_trades[oid]
            msg = f"{trade['symbol']} risultava aperto localmente ma non sull'exchange: chiuso per riconciliazione (stima PnL {pnl:.2f} USDT)"
            self._log('reconcile_close', symbol=trade['symbol'], message=msg)
            asyncio.create_task(notifier.send(f"⚠️ <b>Riconciliazione</b>\n{msg}"))

    # ── Ciclo principale ────────────────────────────────────────────────────

    def _roll_day(self):
        """A mezzanotte UTC azzera il P&L giornaliero e toglie la pausa per
        limite di perdita (prima il P&L giornaliero non si azzerava mai)."""
        today = datetime.utcnow().date()
        for pf in self.portfolios.values():
            if pf.day != today:
                pf.day = today
                pf.daily_pnl = 0.0
                pf.halted_day = None

    def _check_daily_limits(self) -> bool:
        """Mette in pausa (fino a mezzanotte UTC) i portafogli che hanno
        toccato il limite di perdita giornaliera. Ritorna True se TUTTI i
        portafogli attivi sono in pausa."""
        today = datetime.utcnow().date()
        active = [pf for pf in self.portfolios.values() if pf.active]
        for pf in active:
            if pf.halted_day == today:
                continue
            if not risk_manager.check_daily_loss_limit(pf.daily_pnl, pf.capital):
                pf.halted_day = today
                msg = f'Limite perdita giornaliera raggiunto ({pf.label}): {pf.daily_pnl:.2f} USDT'
                self._log('risk_alert', message=msg)
                asyncio.create_task(notifier.risk_alert(msg))
        return bool(active) and all(pf.halted_day == today for pf in active)

    def _tradable(self) -> list:
        """Portafogli che possono aprire nuove posizioni in questo momento."""
        today = datetime.utcnow().date()
        return [pf for pf in self.portfolios.values()
                if pf.active and pf.profile is not None and pf.halted_day != today
                and risk_manager.can_open_position(len(pf.open_trades))]

    async def _main_loop(self):
        while self.is_running:
            try:
                self._sync_active()
                self._roll_day()
                if self._check_daily_limits() and not config.IS_PAPER:
                    # Reale: un solo conto, il limite giornaliero ferma il bot
                    # (come prima). In simulazione si mette in pausa solo il
                    # portafoglio e si riprende a mezzanotte UTC.
                    await self.stop(); break
                self._cycle_count += 1
                if (not config.IS_PAPER) and self._cycle_count % config.RECONCILE_EVERY_N_CYCLES == 0:
                    await self._reconcile_positions()
                await self._monitor_open_trades()
                if self._tradable():
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
        # Il segnale si calcola UNA volta per simbolo e poi ogni portafoglio
        # decide se e quanto aprire con le regole del proprio profilo.
        candidates = [pf for pf in self._tradable()
                      if not any(t['symbol'] == symbol for t in pf.open_trades.values())]
        if not candidates: return
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
            for pf in candidates:
                await self._open_trade(pf, symbol, analysis, price)
        except Exception as e:
            self._log('error', symbol=symbol, message=f'Errore analisi {symbol}: {e}')

    async def _open_trade(self, pf: Portfolio, symbol: str, analysis: dict, price: float):
        profile = self._effective_profile(pf)
        if analysis['strength'] < profile.min_strength:
            return
        side = analysis['signal']
        slip = self._slip_frac() if config.IS_PAPER else 0.0
        params = rp.size_trade(
            profile, pf.capital, price, analysis['indicators_1m']['atr'], side,
            analysis['trade_type'], analysis['strength'], slip)
        if params is None:
            return
        # Margine disponibile: capitale meno il margine gia' bloccato.
        used = sum((t.get('margin') or 0.0) for t in pf.open_trades.values())
        if params['margin'] > pf.capital - used:
            return
        order = await exchange.create_order(
            symbol=symbol, side='buy' if side == 'long' else 'sell',
            quantity=params['quantity'], leverage=params['leverage'],
            stop_loss=params['stop_loss'], take_profit=params['take_profit'])
        if config.IS_PAPER:
            entry = rp.entry_fill(price, side, slip)
            liq = rp.liquidation_price(side, entry, params['leverage'])
            # Id univoco per portafoglio: due profili possono aprire lo stesso
            # simbolo nello stesso secondo.
            order_id = f"{order['id']}-{pf.name}"
        else:
            entry, liq, order_id = price, None, order['id']
        record = {
            'order_id': order_id, 'symbol': symbol,
            'side': side, 'trade_type': analysis['trade_type'],
            'entry_price': entry, 'quantity': params['quantity'],
            'leverage': params['leverage'], 'stop_loss': params['stop_loss'],
            'take_profit': params['take_profit'],
            'client_order_id': order.get('client_order_id'),
            'sl_order_id': order.get('sl_order_id'),
            'tp_order_id': order.get('tp_order_id'),
            'profile': pf.name, 'margin': params['margin'], 'liq_price': liq,
            'indicators_snapshot': json.dumps({
                'rsi': analysis['indicators_1m']['rsi'],
                'trend': analysis['main_trend'],
                'strength': analysis['strength'],
                'reasons': analysis['reasons']
            }),
        }
        self._save_trade(record)
        pf.open_trades[order_id] = record
        self._log('trade_open', symbol=symbol,
                  message=f"[{pf.label}] {side.upper()} {symbol} @ {entry} | {analysis['trade_type']} | forza:{analysis['strength']} | x{params['leverage']}")
        asyncio.create_task(notifier.trade_opened(
            symbol, side, price, params['leverage'], analysis['trade_type'], analysis['strength'],
            profile_label=pf.label if len(self._visible()) > 1 else None))

    # ── Monitoraggio ────────────────────────────────────────────────────────

    async def _monitor_open_trades(self):
        if config.IS_PAPER:
            await self._monitor_open_trades_paper()
        else:
            await self._monitor_open_trades_live()

    async def _monitor_open_trades_paper(self):
        """Simulazione locale: in paper mode non esistono ordini condizionali
        reali sull'exchange, quindi SL/TP restano soglie di prezzo
        confrontate qui ad ogni ciclo. Per i trade dei profili si simulano
        anche liquidazione, commissioni e slippage (risk_profiles.paper_exit /
        paper_pnl); i trade 'legacy' (aperti prima dei profili) si chiudono
        come prima, senza costi."""
        symbols = sorted({t['symbol'] for pf in self.portfolios.values() for t in pf.open_trades.values()})
        prices = {}
        for sym in symbols:
            try:
                prices[sym] = (await exchange.get_ticker(sym))['price']
            except Exception as e:
                print(f'Errore monitoraggio ({sym}): {e}')
        slip, fee = self._slip_frac(), self._fee_frac()
        for pf in self.portfolios.values():
            closed = []
            for oid, trade in list(pf.open_trades.items()):
                try:
                    price = prices.get(trade['symbol'])
                    if price is None:
                        continue
                    sl, tp = trade['stop_loss'], trade['take_profit']
                    if trade.get('margin') is None:
                        # trade 'legacy': logica di prima (prezzo corrente, nessun costo)
                        reason, exit_price = None, price
                        if trade['side'] == 'long':
                            if price <= sl: reason = 'sl'
                            elif price >= tp: reason = 'tp'
                        else:
                            if price >= sl: reason = 'sl'
                            elif price <= tp: reason = 'tp'
                        if not reason:
                            continue
                        gross = self._calc_pnl(trade['entry_price'], exit_price, trade['quantity'], trade['side'], trade['leverage'])
                        fees, net = 0.0, gross
                    else:
                        res = rp.paper_exit(trade['side'], price, sl, tp, trade.get('liq_price'), slip)
                        if res is None:
                            continue
                        reason, exit_price = res
                        gross, fees, net = rp.paper_pnl(
                            trade['side'], trade['quantity'], trade['entry_price'], exit_price,
                            trade['margin'], reason, fee)
                    self._close_trade(pf, oid, exit_price, net, reason, gross=gross, fees=fees)
                    closed.append(oid)
                    self._log('trade_close', symbol=trade['symbol'],
                              message=f"[{pf.label}] Chiuso {trade['symbol']} PnL:{net:.2f} USDT (lordo {gross:.2f}, comm {fees:.2f}) motivo:{reason}")
                    asyncio.create_task(notifier.trade_closed(
                        trade['symbol'], trade['side'], net, reason,
                        profile_label=pf.label if len(self._visible()) > 1 else None))
                except Exception as e:
                    print(f'Errore monitoraggio: {e}')
            for oid in closed: del pf.open_trades[oid]

    async def _monitor_open_trades_live(self):
        """In live mode gli SL/TP sono ordini condizionali reali piazzati
        sull'exchange al momento dell'apertura (vedi exchange.create_order):
        il bot non deve più confrontare il prezzo corrente con le soglie
        locali per decidere se chiudere -- quella decisione è già presa
        dall'exchange. Qui rileviamo solo che una posizione tracciata
        localmente non esiste più sull'exchange (quindi è stata chiusa, da
        SL, TP o manualmente) e aggiorniamo lo stato locale di conseguenza."""
        if not any(pf.open_trades for pf in self.portfolios.values()):
            return
        try:
            positions = await exchange.fetch_open_positions()
        except Exception as e:
            print(f'Errore monitoraggio (fetch posizioni): {e}')
            return
        real_symbols = {p.get('symbol') for p in positions if p.get('symbol')}
        for pf in self.portfolios.values():
            closed = []
            for oid, trade in pf.open_trades.items():
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
                self._close_trade(pf, oid, price, pnl, close_reason)
                closed.append(oid)
                self._log('trade_close', symbol=trade['symbol'],
                          message=f"Chiuso {trade['symbol']} PnL:{pnl:.2f} USDT motivo:{close_reason} (rilevato da riconciliazione posizioni)")
                asyncio.create_task(notifier.trade_closed(
                    trade['symbol'], trade['side'], pnl, close_reason
                ))
            for oid in closed: del pf.open_trades[oid]

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

    def _close_trade(self, pf: Portfolio, oid, exit_price, pnl, reason, gross=None, fees=None):
        """Chiude il trade nel DB e aggiorna capitale / P&L del portafoglio.
        `pnl` e' il netto (dopo commissioni, se simulate)."""
        db = SessionLocal()
        try:
            t = db.query(Trade).filter(Trade.order_id == oid).first()
            if t:
                t.exit_price = exit_price; t.pnl = pnl
                t.pnl_percent = (pnl / pf.capital) * 100 if pf.capital else 0.0
                t.status = 'closed'; t.close_time = datetime.utcnow(); t.close_reason = reason
                t.gross_pnl = gross if gross is not None else pnl
                t.fees = fees if fees is not None else 0.0
                db.commit()
            pf.daily_pnl += pnl; pf.capital += pnl
        finally:
            db.close()

    async def close_all_positions(self, reason='manual_telegram'):
        """Chiude tutte le posizioni aperte con un ordine reduce-only
        (usato dal kill switch Telegram /closeall). Ritorna la lista dei
        symbol chiusi, per confermare l'esito a chi ha dato il comando."""
        closed_symbols = []
        for pf in self.portfolios.values():
            for oid, trade in list(pf.open_trades.items()):
                try:
                    if not config.IS_PAPER:
                        await exchange.close_position(trade['symbol'], trade['side'], trade['quantity'])
                    ticker = await exchange.get_ticker(trade['symbol'])
                    price = ticker['price']
                    gross = fees = None
                    if config.IS_PAPER and trade.get('margin') is not None:
                        price = rp.market_exit_price(trade['side'], price, self._slip_frac())
                        gross, fees, pnl = rp.paper_pnl(
                            trade['side'], trade['quantity'], trade['entry_price'], price,
                            trade['margin'], reason, self._fee_frac())
                    else:
                        pnl = self._calc_pnl(trade['entry_price'], price, trade['quantity'], trade['side'], trade['leverage'])
                    self._close_trade(pf, oid, price, pnl, reason, gross=gross, fees=fees)
                    del pf.open_trades[oid]
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
            rows = db.query(
                Trade.profile,
                func.count(Trade.id),
                func.coalesce(func.sum(Trade.pnl), 0.0),
                func.coalesce(func.sum(Trade.fees), 0.0),
                func.coalesce(func.sum(case((Trade.pnl > 0, 1), else_=0)), 0),
            ).filter(Trade.status == 'closed').group_by(Trade.profile).all()
            stats = {(r[0] or 'legacy'): r for r in rows}
            visible = self._visible()
            portfolios = []
            for pf in visible:
                s = stats.get(pf.name)
                closed_n = s[1] if s else 0
                portfolios.append({
                    'name': pf.name, 'label': pf.label, 'active': pf.active,
                    'capital': round(pf.capital, 2), 'daily_pnl': round(pf.daily_pnl, 2),
                    'open_positions': len(pf.open_trades),
                    'closed_trades': closed_n,
                    'win_rate': round((s[4] / closed_n * 100) if s and closed_n else 0, 1),
                    'net_pnl': round(s[2], 2) if s else 0.0,
                    'fees_paid': round(s[3], 2) if s else 0.0,
                    'paused': pf.halted_day == datetime.utcnow().date(),
                })
            return {
                'is_running': self.is_running, 'mode': config.TRADING_MODE,
                'risk_mode': self._effective_mode(),
                'capital': round(sum(p['capital'] for p in portfolios), 2),
                'daily_pnl': round(sum(p['daily_pnl'] for p in portfolios), 2),
                'open_positions': sum(p['open_positions'] for p in portfolios),
                'total_trades': total,
                'win_rate': round((winning / total * 100) if total > 0 else 0, 1),
                'portfolios': portfolios,
            }
        finally:
            db.close()


bot = BotEngine()
