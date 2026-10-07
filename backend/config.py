import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    BITGET_API_KEY = os.getenv('BITGET_API_KEY', '')
    BITGET_SECRET_KEY = os.getenv('BITGET_SECRET_KEY', '')
    BITGET_PASSPHRASE = os.getenv('BITGET_PASSPHRASE', '')
    TRADING_MODE = os.getenv('TRADING_MODE', 'paper')
    IS_PAPER = TRADING_MODE == 'paper'
    INITIAL_CAPITAL = float(os.getenv('INITIAL_CAPITAL', '1000'))
    MAX_LEVERAGE = int(os.getenv('MAX_LEVERAGE', '10'))
    MAX_DAILY_LOSS_PERCENT = float(os.getenv('MAX_DAILY_LOSS_PERCENT', '5'))
    MAX_OPEN_POSITIONS = int(os.getenv('MAX_OPEN_POSITIONS', '3'))
    TRADING_PAIRS_RAW = os.getenv('TRADING_PAIRS', 'BTCUSDT,ETHUSDT,XAUUSDT,XAGUSDT')
    TRADING_PAIRS = [p.strip() for p in TRADING_PAIRS_RAW.split(',')]
    BACKEND_PORT = int(os.getenv('BACKEND_PORT', '8002'))
    DASHBOARD_PASSWORD = os.getenv('DASHBOARD_PASSWORD', 'superbot2024')
    SECRET_KEY = os.getenv('SECRET_KEY', 'superbot-secret-key')
    DB_PATH = os.getenv('DB_PATH', './data/superbot.db')
    SCALPING_INTERVAL = 30
    DATA_FETCH_INTERVAL = 10

    # V0.5 Strategy Engine — optional warm-start for the StrategySelector.
    # Empty by default (= cold start, no behavior change). Set this env var
    # on the VPS to the path of a state file produced by backtest_harness.py
    # ONLY after reviewing its leaderboard output — bot_engine.py loads it
    # once at import time if present, as a read-only warm-up for the V0.5
    # shadow run. It never affects which trades signal_engine executes.
    V05_STATE_PATH = os.getenv('V05_STATE_PATH', '')

config = Config()
