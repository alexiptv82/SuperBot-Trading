from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from config import config

os.makedirs('data', exist_ok=True)
DATABASE_URL = f"sqlite:///{config.DB_PATH}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, unique=True, index=True)
    symbol = Column(String, index=True)
    side = Column(String)
    trade_type = Column(String)
    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float)
    leverage = Column(Integer)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    pnl = Column(Float, nullable=True)
    pnl_percent = Column(Float, nullable=True)
    status = Column(String, default='open')
    open_time = Column(DateTime, default=datetime.utcnow)
    close_time = Column(DateTime, nullable=True)
    close_reason = Column(String, nullable=True)
    indicators_snapshot = Column(Text, nullable=True)
    # clientOrderId mandato all'exchange insieme all'ordine di apertura --
    # permette di riconoscere un retry della stessa richiesta come lo stesso
    # ordine invece di aprirne uno duplicato (idempotenza).
    client_order_id = Column(String, nullable=True, index=True)
    # Id degli ordini condizionali di stop loss / take profit piazzati
    # sull'exchange insieme all'apertura (se il bot gira in modalita' live).
    # Nessuno dei due in modalita' paper, dove SL/TP restano soglie locali.
    sl_order_id = Column(String, nullable=True)
    tp_order_id = Column(String, nullable=True)

class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    price = Column(Float)
    rsi_14 = Column(Float, nullable=True)
    macd = Column(Float, nullable=True)
    macd_signal = Column(Float, nullable=True)
    ema_9 = Column(Float, nullable=True)
    ema_21 = Column(Float, nullable=True)
    ema_50 = Column(Float, nullable=True)
    bb_upper = Column(Float, nullable=True)
    bb_lower = Column(Float, nullable=True)
    atr = Column(Float, nullable=True)
    trend = Column(String, nullable=True)
    signal = Column(String, nullable=True)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String)
    symbol = Column(String, nullable=True)
    message = Column(Text)
    data = Column(Text, nullable=True)

class RiskSettings(Base):
    """Override dei parametri di rischio impostati dall'app (pagina
    Impostazioni). Una sola riga (id=1). Un campo NULL significa "nessun
    override, usa il valore di .env" -- vedi risk_settings.py.

    Vive nel DB (non in .env) perche' deve sopravvivere sia ai riavvii del
    bot sia ai redeploy da GitHub, che riscrivono .env dai secret."""
    __tablename__ = "risk_settings"
    id = Column(Integer, primary_key=True)
    max_leverage = Column(Integer, nullable=True)
    max_daily_loss_percent = Column(Float, nullable=True)
    max_open_positions = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

def _migrate_add_missing_columns():
    """Micro-migrazione per SQLite: create_all() crea solo le tabelle mancanti,
    non le colonne nuove su una tabella che esiste gia' (es. il DB di
    produzione sul VPS, creato prima dei campi di idempotenza/SL-TP qui
    sotto). Aggiunge con ALTER TABLE solo le colonne che mancano davvero,
    non tocca nessun dato esistente."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if 'trades' not in inspector.get_table_names():
        return  # tabella nuova, create_all() l'ha gia' creata con tutte le colonne
    existing_cols = {c['name'] for c in inspector.get_columns('trades')}
    needed = {
        'client_order_id': 'VARCHAR',
        'sl_order_id': 'VARCHAR',
        'tp_order_id': 'VARCHAR',
    }
    with engine.connect() as conn:
        for col, col_type in needed.items():
            if col not in existing_cols:
                conn.execute(text(f'ALTER TABLE trades ADD COLUMN {col} {col_type}'))
        conn.commit()


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_add_missing_columns()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
