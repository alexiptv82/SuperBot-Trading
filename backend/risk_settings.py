"""Override dei parametri di rischio modificabili dall'app.

I valori di default arrivano da .env (config.py). Qui si aggiunge un livello
sopra: se l'utente ha salvato un valore dalla pagina Impostazioni, quel
valore vive nel DB (tabella risk_settings, una sola riga) e viene applicato
sopra il singleton `config` -- all'avvio (load_overrides) e subito dopo ogni
salvataggio (save_overrides).

risk_manager.py legge config.MAX_LEVERAGE / MAX_DAILY_LOSS_PERCENT /
MAX_OPEN_POSITIONS a ogni chiamata (non li mette in cache), quindi una
modifica ha effetto dal ciclo successivo del bot, senza riavvio.

Un campo NULL nel DB = nessun override, resta il valore di .env.
"""
from datetime import datetime

from config import config
from database import SessionLocal, RiskSettings

# Limiti di sicurezza accettati dall'API. Servono a impedire che un errore
# di digitazione (es. leva 100 al posto di 10) o un client compromesso
# portino i parametri a valori pericolosi. Non sono limiti dell'exchange.
RISK_BOUNDS = {
    'max_leverage': {'min': 1, 'max': 20, 'type': int},
    'max_daily_loss_percent': {'min': 0.5, 'max': 20.0, 'type': float},
    'max_open_positions': {'min': 1, 'max': 10, 'type': int},
}

# Nome del campo API -> attributo del singleton config
_CONFIG_ATTR = {
    'max_leverage': 'MAX_LEVERAGE',
    'max_daily_loss_percent': 'MAX_DAILY_LOSS_PERCENT',
    'max_open_positions': 'MAX_OPEN_POSITIONS',
}


def validate(values: dict) -> dict:
    """Controlla tipo e limiti. Ritorna i valori normalizzati, oppure alza
    ValueError con un messaggio leggibile dall'utente."""
    clean = {}
    for field, rule in RISK_BOUNDS.items():
        if field not in values or values[field] is None:
            raise ValueError(f'Campo mancante: {field}')
        raw = values[field]
        if isinstance(raw, bool):
            raise ValueError(f'{field}: valore non valido')
        try:
            value = rule['type'](raw)
        except (TypeError, ValueError):
            raise ValueError(f'{field}: valore non valido')
        # Per i campi interi, rifiuta 3.7 invece di troncarlo in silenzio a 3.
        if rule['type'] is int and float(raw) != value:
            raise ValueError(f'{field}: deve essere un numero intero')
        if not (rule['min'] <= value <= rule['max']):
            raise ValueError(f"{field}: deve essere tra {rule['min']} e {rule['max']}")
        clean[field] = value
    return clean


def _apply_to_config(values: dict) -> None:
    for field, value in values.items():
        setattr(config, _CONFIG_ATTR[field], value)


def load_overrides() -> dict:
    """All'avvio: applica sopra config gli override salvati in DB (solo i
    campi non NULL). Se un valore salvato risultasse fuori dai limiti
    (DB modificato a mano), viene ignorato e resta quello di .env.
    Ritorna i valori effettivamente applicati."""
    applied = {}
    db = SessionLocal()
    try:
        row = db.query(RiskSettings).filter(RiskSettings.id == 1).first()
        if row is None:
            return applied
        for field in RISK_BOUNDS:
            stored = getattr(row, field)
            if stored is None:
                continue
            try:
                # Valida il singolo campo usando i valori correnti per gli altri.
                applied[field] = validate({**current_values(), field: stored})[field]
            except ValueError:
                continue  # valore fuori limiti nel DB: si tiene quello di .env
        _apply_to_config(applied)
    finally:
        db.close()
    return applied


def current_values() -> dict:
    return {field: getattr(config, attr) for field, attr in _CONFIG_ATTR.items()}


def save_overrides(values: dict) -> dict:
    """Valida, salva in DB (upsert riga id=1) e applica subito a config.
    Alza ValueError se qualcosa non e' valido -- in quel caso non viene
    scritto nulla ne' in DB ne' in memoria."""
    clean = validate(values)
    db = SessionLocal()
    try:
        row = db.query(RiskSettings).filter(RiskSettings.id == 1).first()
        if row is None:
            row = RiskSettings(id=1)
            db.add(row)
        for field, value in clean.items():
            setattr(row, field, value)
        row.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()
    _apply_to_config(clean)
    return clean
