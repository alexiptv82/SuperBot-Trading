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
    # Session tokens
    JWT_EXPIRE_HOURS = int(os.getenv('JWT_EXPIRE_HOURS', '720'))  # 30 giorni di default
    # WebAuthn (login biometrico) -- RP_ID deve essere un dominio reale, non un IP;
    # finché non è impostato un dominio con HTTPS, gli endpoint WebAuthn restano
    # presenti ma il browser rifiuterà la richiesta per contesto non sicuro.
    WEBAUTHN_RP_ID = os.getenv('WEBAUTHN_RP_ID', 'localhost')
    WEBAUTHN_RP_NAME = os.getenv('WEBAUTHN_RP_NAME', 'SuperBot')
    WEBAUTHN_ORIGIN = os.getenv('WEBAUTHN_ORIGIN', 'http://localhost:3000')
    SCALPING_INTERVAL = 30
    DATA_FETCH_INTERVAL = 10

config = Config()
