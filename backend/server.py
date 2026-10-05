from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from backend.config import config
from backend.database import init_db, get_db, Trade, AuditLog
from backend.bot_engine import bot
from backend.exchange import exchange

init_db()

app = FastAPI(title='SuperBot Trading API', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True,
                   allow_methods=['*'], allow_headers=['*'])

class LoginRequest(BaseModel):
    password: str

@app.post('/api/auth/login')
async def login(req: LoginRequest):
    if req.password != config.DASHBOARD_PASSWORD:
        raise HTTPException(status_code=401, detail='Password errata')
    return {'success': True}

@app.post('/api/bot/start')
async def start_bot():
    await bot.start(); return {'success': True, 'message': 'Bot avviato'}

@app.post('/api/bot/stop')
async def stop_bot():
    await bot.stop(); return {'success': True, 'message': 'Bot fermato'}

@app.get('/api/bot/status')
async def get_status():
    return bot.get_status()

@app.get('/api/market/prices')
async def get_prices():
    prices = {}
    for symbol in config.TRADING_PAIRS:
        try: prices[symbol] = await exchange.get_ticker(symbol)
        except Exception as e: prices[symbol] = {'error': str(e)}
    return prices

@app.get('/api/market/indicators/{symbol}')
async def get_indicators(symbol: str):
    try:
        ohlcv = await exchange.get_ohlcv(symbol, '1m', 100)
        from backend.indicators import TechnicalIndicators
        return TechnicalIndicators(ohlcv).compute_all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/api/trades')
async def get_trades(db: Session = Depends(get_db), limit: int = 50):
    trades = db.query(Trade).order_by(Trade.open_time.desc()).limit(limit).all()
    return [{'id': t.id, 'order_id': t.order_id, 'symbol': t.symbol, 'side': t.side,
             'trade_type': t.trade_type, 'entry_price': t.entry_price,
             'exit_price': t.exit_price, 'quantity': t.quantity, 'leverage': t.leverage,
             'pnl': t.pnl, 'pnl_percent': t.pnl_percent, 'status': t.status,
             'open_time': t.open_time.isoformat() if t.open_time else None,
             'close_time': t.close_time.isoformat() if t.close_time else None,
             'close_reason': t.close_reason} for t in trades]

@app.get('/api/trades/open')
async def get_open_trades():
    return list(bot.open_trades.values())

@app.get('/api/performance')
async def get_performance(db: Session = Depends(get_db)):
    trades = db.query(Trade).filter(Trade.status == 'closed').all()
    total = len(trades)
    if total == 0: return {'total_trades': 0, 'win_rate': 0, 'total_pnl': 0}
    winners = [t for t in trades if t.pnl and t.pnl > 0]
    total_pnl = sum(t.pnl for t in trades if t.pnl)
    return {'total_trades': total, 'winning_trades': len(winners),
            'losing_trades': total - len(winners),
            'win_rate': round(len(winners) / total * 100, 1),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl_per_trade': round(total_pnl / total, 2)}

@app.get('/api/logs')
async def get_logs(db: Session = Depends(get_db), limit: int = 100):
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [{'id': l.id, 'timestamp': l.timestamp.isoformat(),
             'event_type': l.event_type, 'symbol': l.symbol, 'message': l.message} for l in logs]

@app.get('/api/health')
async def health():
    return {'status': 'ok', 'mode': config.TRADING_MODE, 'version': '1.0.0'}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('backend.server:app', host='0.0.0.0', port=config.BACKEND_PORT, reload=True)
