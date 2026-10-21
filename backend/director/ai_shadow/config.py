"""Configurazione dell'AI in ombra. Tutti i valori sono ipotesi di questo braccio di prova, NON parametri dei bot.

Cambiare un valore cambia `config_hash`; il registro lo annota (evento `config_cambiata`), il conto non si azzera.
"""
import hashlib
import json
from dataclasses import asdict, dataclass

# Stesso universo dei bot (cli.SYMBOLS); un test in CI controlla che non si allontani.
SYMBOLS = (
    "BTC", "ETH", "BNB", "XRP", "SOL", "ADA", "DOGE", "AVAX",
    "DOT", "LINK", "UNI", "ATOM", "LTC", "BCH",
    "APT", "ARB", "OP", "NEAR", "FIL", "INJ", "SUI", "TIA",
    "RUNE", "STX", "XAU", "XAG",
)


@dataclass(frozen=True)
class Config:
    name: str = "ai-deepseek"
    symbols: tuple = SYMBOLS
    # ---- ritmo: si decide a ogni chiusura di barra da 15 minuti (+15 s, come il Turbo)
    bar_ms: int = 900_000
    delay_ms: int = 15_000
    # ---- modello
    model: str = "deepseek-flash"
    base_url: str = "https://api.deepseek.com"
    thinking: bool = False            # ragionamento esteso spento: costo prevedibile (si puo' provare in A/B piu' avanti)
    temperature: float = 0.3
    max_tokens: int = 2200
    timeout_s: int = 90
    # ---- spesa (decisione dell'utente 21/10/2026: 0,50 $ al giorno; tetto mensile proposto 12 $)
    daily_cap_usd: float = 0.50
    monthly_cap_usd: float = 12.0
    cost_safety: float = 1.25         # margine sul costo calcolato dal listino
    # ---- conto virtuale: gli stessi limiti di Hawk, cosi' i confronti sono alla pari
    start_equity: float = 1000.0
    max_margin_trade: float = 100.0
    max_margin_total: float = 1000.0
    max_open: int = 10
    kill_equity: float = 450.0
    daily_stop: float = 0.12
    # ---- dimensionamento deciso dal CODICE (l'AI non sceglie importi): rischio fisso per trade sul capitale
    risk_pct: float = 1.0
    # ---- filtri del controllore (arbitro): dichiarati prima, mai scelti dall'AI
    min_conviction: int = 60
    min_rr: float = 1.5               # rapporto rendimento/rischio sul prezzo di riferimento
    min_fill_rr: float = 1.2          # ricontrollato sul prezzo reale di ingresso (apertura della barra dopo)
    min_sl_pct: float = 0.25          # stop piu' vicino di cosi' e' rumore
    max_sl_pct: float = 8.0
    max_new_per_cycle: int = 3
    prompt_version: str = "p1"
    # ---- dati
    bars_15m: int = 300
    bars_1h: int = 200
    bars_4h: int = 120
    bars_1d: int = 60
    min_symbols_ok: int = 20          # sotto questa soglia di simboli con dati non si chiama il modello


def config_hash(cfg: Config) -> str:
    raw = json.dumps(asdict(cfg), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
