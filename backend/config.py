import base64
import os
from dotenv import load_dotenv
load_dotenv()


def _bootstrap_password() -> str:
    """Password iniziale (solo per il primo accesso: l'app obbliga a cambiarla).
    Il deploy la passa in base64 (DASHBOARD_PASSWORD_B64) cosi' qualunque
    carattere sopravvive al file .env. Nessun valore di default: se manca,
    il primo accesso con password non e' possibile."""
    b64 = os.getenv('DASHBOARD_PASSWORD_B64', '')
    if b64:
        try:
            return base64.b64decode(b64).decode()
        except Exception:
            return ''
    return os.getenv('DASHBOARD_PASSWORD', '')

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
    DASHBOARD_PASSWORD = _bootstrap_password()
    # La chiave di firma dei token NON e' piu' qui: viene generata a caso e
    # salvata nel DB (vedi auth.py).
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

    # ── Profili di rischio e costi del paper trading ─────────────────────────
    # Modalita' di rischio di default ('conservative' | 'aggressive' | 'both').
    # Il valore scelto dall'app (Impostazioni) vive nel DB e prevale su
    # questo. In modalita' reale vale sempre e solo 'conservative'.
    RISK_MODE = os.getenv('RISK_MODE', 'both')
    # Costi simulati nel paper trading (in punti base = 0,01%): commissione
    # taker BitGet per lato (0,06% = 6 bps) e slippage avverso su ingresso e
    # uscite a mercato. Il paper di prima non li contava.
    PAPER_FEE_BPS = float(os.getenv('PAPER_FEE_BPS', '6'))
    PAPER_SLIPPAGE_BPS = float(os.getenv('PAPER_SLIPPAGE_BPS', '2'))

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
