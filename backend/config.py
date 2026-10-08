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

    # ── Risk management (Fase 1 della roadmap di hardening) ─────────────────
    # Rischio fisso per trade, come % del capitale corrente. La size viene
    # derivata da questo e dalla distanza dello stop loss (non piu' una
    # frazione fissa del capitale) -- vedi risk_manager.py.
    RISK_PER_TRADE_PERCENT = float(os.getenv('RISK_PER_TRADE_PERCENT', '1.0'))
    # Tetto assoluto sul nozionale di una singola posizione, come % del
    # capitale: anche con uno stop molto stretto (che implicherebbe una size
    # enorme per rispettare il rischio fisso) non si supera mai questo.
    MAX_POSITION_PERCENT = float(os.getenv('MAX_POSITION_PERCENT', '20'))

    # ── Esecuzione reale (SL/TP, retry, riconciliazione) ─────────────────────
    API_MAX_RETRIES = int(os.getenv('API_MAX_RETRIES', '3'))
    API_RETRY_BASE_DELAY = float(os.getenv('API_RETRY_BASE_DELAY', '1.0'))
    # Ogni quanti cicli del loop principale (ognuno ~SCALPING_INTERVAL
    # secondi) riconciliare lo stato locale delle posizioni con quello reale
    # sull'exchange, oltre alla riconciliazione gia' fatta all'avvio.
    RECONCILE_EVERY_N_CYCLES = int(os.getenv('RECONCILE_EVERY_N_CYCLES', '10'))

    # ── Kill switch Telegram (comandi in ingresso) ───────────────────────────
    TELEGRAM_COMMANDS_ENABLED = os.getenv('TELEGRAM_COMMANDS_ENABLED', 'true').lower() == 'true'
    # Se impostato, solo messaggi da questo chat_id vengono trattati come
    # comandi validi (lo stesso chat_id usato per le notifiche in uscita,
    # di default -- vedi telegram_notifier.py).

config = Config()
