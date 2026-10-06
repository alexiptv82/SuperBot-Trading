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

config = Config()
