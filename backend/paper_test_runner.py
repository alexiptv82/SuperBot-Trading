"""Driver standalone per testare il BotEngine (ramo main-phase1-safety) in
paper mode per una durata delimitata, senza passare dal server FastAPI (che
richiederebbe webauthn/sessioni) -- stesso schema usato per i test del
motore V0.5 (backtest_harness.py / live_monitor.py): uno script a riga di
comando pensato per girare dentro una GitHub Actions workflow_dispatch,
con un tetto massimo di sicurezza sulla durata e un file di stato
periodico caricato come artifact per l'analisi successiva.

Usa SEMPRE TRADING_MODE=paper (lo script si rifiuta di partire altrimenti):
l'obiettivo e' validare su mercato reale la logica di sizing, i sanity
check sui dati, la riconciliazione e il loop in generale -- non piazzare
ordini veri.
"""
import argparse
import asyncio
import json
import time
from datetime import datetime

from config import config
from database import init_db, SessionLocal, Trade, AuditLog
from bot_engine import bot


def dump_state(path: str):
    db = SessionLocal()
    try:
        trades = db.query(Trade).order_by(Trade.open_time).all()
        logs = db.query(AuditLog).order_by(AuditLog.timestamp).all()
        closed = [t for t in trades if t.status == 'closed']
        state = {
            'generated_at': datetime.utcnow().isoformat(),
            'bot_status': bot.get_status(),
            'open_trades': list(bot.open_trades.values()),
            'summary': {
                'total_trades': len(trades),
                'closed_trades': len(closed),
                'total_pnl': round(sum(t.pnl or 0 for t in closed), 2),
                'close_reasons': {
                    r: sum(1 for t in closed if t.close_reason == r)
                    for r in set(t.close_reason for t in closed if t.close_reason)
                },
            },
            'trades': [{
                'order_id': t.order_id, 'symbol': t.symbol, 'side': t.side,
                'trade_type': t.trade_type, 'entry_price': t.entry_price,
                'exit_price': t.exit_price, 'quantity': t.quantity,
                'leverage': t.leverage, 'stop_loss': t.stop_loss,
                'take_profit': t.take_profit, 'pnl': t.pnl,
                'pnl_percent': t.pnl_percent, 'status': t.status,
                'open_time': t.open_time.isoformat() if t.open_time else None,
                'close_time': t.close_time.isoformat() if t.close_time else None,
                'close_reason': t.close_reason,
                'client_order_id': t.client_order_id,
            } for t in trades],
            'logs_tail': [{
                'timestamp': l.timestamp.isoformat(), 'event_type': l.event_type,
                'symbol': l.symbol, 'message': l.message,
            } for l in logs[-1000:]],
        }
    finally:
        db.close()
    with open(path, 'w') as f:
        json.dump(state, f, indent=2)


async def main(max_hours: float, state_out: str, dump_every_seconds: int):
    assert config.IS_PAPER, (
        "paper_test_runner.py e' pensato SOLO per TRADING_MODE=paper. "
        "Imposta TRADING_MODE=paper nell'ambiente prima di lanciarlo."
    )
    init_db()
    print(f"Avvio test paper-mode (main-phase1-safety) per max {max_hours}h")
    print(f"Coppie: {config.TRADING_PAIRS} | Capitale iniziale: {config.INITIAL_CAPITAL} USDT")
    await bot.start()
    deadline = time.monotonic() + max_hours * 3600
    try:
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            await asyncio.sleep(min(dump_every_seconds, max(remaining, 0)))
            dump_state(state_out)
            s = bot.get_status()
            print(
                f"[{datetime.utcnow().isoformat()}] capital={s['capital']} "
                f"daily_pnl={s['daily_pnl']} open={s['open_positions']} "
                f"trades={s['total_trades']} win_rate={s['win_rate']}%"
            )
    finally:
        await bot.stop()
        dump_state(state_out)
        print("Test terminato, stato finale salvato in", state_out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-hours', type=float, default=5.0)
    parser.add_argument('--state-out', type=str, default='paper_test_state.json')
    parser.add_argument('--dump-every-seconds', type=int, default=300)
    args = parser.parse_args()
    asyncio.run(main(args.max_hours, args.state_out, args.dump_every_seconds))
