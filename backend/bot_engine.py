import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from config import config
from database import Trade, AuditLog, SessionLocal
from exchange import exchange
from signal_engine import signal_engine
from risk_manager import risk_manager
from indicators import TechnicalIndicators
from regime_detector import detect_regime
try:
    from backend.telegram_notifier import notifier
except ImportError:
    from telegram_notifier import notifier

# ── V0.5 Strategy Engine ──────────────────────────────────────────────────────
# Loaded with try/except so the bot can start even if the strategies package
# is temporarily missing (e.g. during a hot-swap deploy). When unavailable,
# _v05_enabled=False and every _analyze_v05 call is a no-op.
_v05_state_loaded = False
_v05_state_path_used: Optional[str] = None
try:
    from strategies import (
        TrendFollowingStrategy,
        MeanReversionStrategy,
        MomentumStrategy,
        StrategyContext,
    )
    from strategy_selector import StrategySelector

    _v05_strategies = [
        TrendFollowingStrategy(),
        MeanReversionStrategy(),
        MomentumStrategy(),
    ]
    _v05_selector = StrategySelector(
        strategy_ids=[s.strategy_id for s in _v05_strategies]
    )
    _v05_enabled = True

    # Optional warm-start: load a selector state produced offline by
    # backtest_harness.py. Disabled by default (V05_STATE_PATH=''), so this
    # is a no-op unless a human explicitly points to a reviewed state file
    # on the VPS. Never touches signal_engine or trade execution either way.
    _v05_state_path_cfg = getattr(config, "V05_STATE_PATH", "")
    if _v05_state_path_cfg:
        _state_file = Path(_v05_state_path_cfg)
        if _state_file.exists():
            try:
                _v05_selector.load_state(json.loads(_state_file.read_text()))
                _v05_state_loaded = True
                _v05_state_path_used = str(_state_file)
                print(f"[V0.5] Loaded warmed-up selector state from {_state_file}")
            except Exception as _state_err:  # noqa: BLE001
                print(f"[V0.5] Failed to load state from {_state_file}: {_state_err}")
        else:
            print(f"[V0.5] V05_STATE_PATH set but file not found: {_state_file}")
except Exception as _v05_import_err:  # noqa: BLE001
    _v05_strategies = []
    _v05_selector = None
    _v05_enabled = False
    print(f"[V0.5] Strategy engine non disponibile: {_v05_import_err}")
# ─────────────────────────────────────────────────────────────────────────────


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
        if _v05_enabled:
            v05_status = "ON (warmed-up)" if _v05_state_loaded else "ON (cold)"
        else:
            v05_status = "OFF (import error)"
        self._log('bot_start', message=f'Bot avviato - modalita {config.TRADING_MODE} | V0.5 engine: {v05_status}')
        asyncio.create_task(notifier.send("🤖 <b>SuperBot avviato!</b>\nModalità: " + config.TRADING_MODE.upper()))

    async def stop(self):
        self.is_running = False
        if self._task: self._task.cancel()
        self._log('bot_stop', message='Bot fermato')
        asyncio.create_task(notifier.send("⏹️ <b>SuperBot fermato</b>"))

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

    # ── V0.5: parallel shadow run ─────────────────────────────────────────────
    def _analyze_v05(self, symbol: str, ohlcv_1m, ohlcv_15m, ohlcv_1h, regime: str = "unknown"):
        """Run the V0.5 strategy engine in shadow mode (no trade execution).

        Reads the StrategyContext, queries all three strategies, calls the
        selector, and logs the result. Never raises — any exception is caught
        and logged so the V1 signal_engine path is never affected.
        """
        if not _v05_enabled:
            return

        try:
            context = StrategyContext.from_ohlcv(
                symbol=symbol,
                ohlcv_1m=ohlcv_1m,
                ohlcv_15m=ohlcv_15m,
                ohlcv_1h=ohlcv_1h,
                regime=regime,
            )

            decisions = [s.analyze(context) for s in _v05_strategies]

            # Bucket di statistiche/champion separato per (simbolo, regime):
            # BTC/ETH (cripto) e XAU/XAG (metalli) non devono influenzarsi a
            # vicenda solo perche' si trovano nello stesso regime di mercato.
            context_key = StrategySelector.make_context_key(symbol, regime)
            result = _v05_selector.select(decisions, regime=context_key)

            # Build compact summary for the audit log
            selected = result.selected
            if selected is not None:
                summary = (
                    f"V0.5 [{result.selected_role}] {result.selected_strategy_id}"
                    f" → {selected.direction.value.upper()}"
                    f" strength={selected.strength:.1f}"
                    f" conf={selected.confidence:.2f}"
                    f" reasons={','.join(selected.reasons[:3])}"
                    f" regime={result.regime}"
                )
            else:
                # All strategies held or below threshold
                summary = (
                    f"V0.5 [NO_SIGNAL] regime={result.regime}"
                    f" rankings={[r['strategy_id']+':'+str(round(r['strength'],1)) for r in result.rankings]}"
                )

            if result.promotion:
                summary += f" | PROMOTION={json.dumps(result.promotion)}"

            self._log('v05_shadow', symbol=symbol, message=summary)

        except Exception as exc:  # noqa: BLE001
            self._log('v05_error', symbol=symbol, message=f'V0.5 errore shadow: {exc}')

    # ─────────────────────────────────────────────────────────────────────────

    async def _analyze_and_trade(self, symbol: str):
        for t in self.open_trades.values():
            if t['symbol'] == symbol: return
        try:
            ohlcv_1m = await exchange.get_ohlcv(symbol, '1m', 100)
            ohlcv_15m = await exchange.get_ohlcv(symbol, '15m', 100)
            ohlcv_1h = await exchange.get_ohlcv(symbol, '1h', 100)

            # ── V1 signal engine (production path — unchanged) ───────────────
            analysis = signal_engine.analyze(ohlcv_1m, ohlcv_15m, ohlcv_1h)

            # ── V0.5 shadow run (parallel, no trade execution) ───────────────
            # Regime di mercato (forza del trend via ADX 1h + direzione via
            # EMA, con isteresi 20/25 -- vedi regime_detector.py) invece del
            # precedente placeholder che riusava main_trend del motore V1
            # (solo direzione, nessuna misura di "quanto" c'è davvero un
            # trend in corso).
            try:
                ind_1h = TechnicalIndicators(ohlcv_1h).compute_all()
                regime_info = detect_regime(
                    symbol, adx=ind_1h['adx'], trend_direction=ind_1h['trend'], bbw=ind_1h['bbw'])
                regime = regime_info['regime']
            except Exception as regime_exc:  # noqa: BLE001
                self._log('v05_error', symbol=symbol, message=f'Regime detector errore: {regime_exc}')
                regime = str(analysis.get('main_trend', 'unknown')).lower()
            self._analyze_v05(symbol, ohlcv_1m, ohlcv_15m, ohlcv_1h, regime=regime)
            # ─────────────────────────────────────────────────────────────────

            # Production gate: only signal_engine controls trade execution
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
            asyncio.create_task(notifier.trade_opened(
                symbol, analysis['signal'], price,
                params['leverage'], analysis['trade_type'], analysis['strength']
            ))
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
                    asyncio.create_task(notifier.trade_closed(
                        trade['symbol'], trade['side'], pnl, close_reason
                    ))
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
            if _v05_enabled:
                v05_engine_status = 'warmed-up' if _v05_state_loaded else 'cold'
            else:
                v05_engine_status = 'unavailable'
            return {
                'is_running': self.is_running, 'mode': config.TRADING_MODE,
                'capital': round(self.capital, 2), 'daily_pnl': round(self.daily_pnl, 2),
                'open_positions': len(self.open_trades), 'total_trades': total,
                'win_rate': round((winning / total * 100) if total > 0 else 0, 1),
                'v05_engine': v05_engine_status,
            }
        finally:
            db.close()

bot = BotEngine()
