"""Rilevatore di regime di mercato (trend / range / transizionale) per il
motore V0.5 (shadow mode), basato su ADX e Bollinger Band Width.

Prima di questo modulo, bot_engine.py derivava il "regime" passato al
StrategySelector semplicemente dal main_trend del motore V1 (bullish /
bearish / sideways in base alle EMA) -- un segnale di direzione, non di
FORZA del trend, quindi uno strumento spuntato per decidere se un mercato
è davvero in trend o solo laterale con un piccolo bias direzionale.

Qui invece:
- l'ADX misura la forza del trend indipendentemente dalla direzione
- la direzione (bull/bear) arriva separatamente dal trend EMA
- la BBW (Bollinger Band Width) è una conferma indipendente: un mercato
  compresso (BBW bassa) è coerente con un ADX basso

Soglie e isteresi (dal report di revisione di Qwen):
- ADX >= 25           -> si ENTRA in trend
- ADX <  20           -> si È FUORI dal trend (range)
- 20 <= ADX < 25       -> zona grigia ("TRANSITIONAL"): se si era già in
  trend, ci si resta (isteresi: si esce solo sotto 20); altrimenti si
  resta in attesa di confermare un vero trend, con un tetto di confidenza
  ridotto sui segnali di breakout/momentum
"""
from __future__ import annotations

from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    _LONDON_TZ = ZoneInfo("Europe/London")
except Exception:  # pragma: no cover - tzdata assente in alcune immagini minimali
    _LONDON_TZ = None

ADX_TREND_IN = 25.0
ADX_TREND_OUT = 20.0

# Tetto di confidenza (0-100) applicato quando il regime è nella zona
# grigia: un segnale può comunque emergere, ma non ci si fida come se il
# trend fosse confermato.
TRANSITIONAL_CONFIDENCE_CAP = 70.0

# Stato per simbolo, in memoria di processo. Il motore V0.5 gira in shadow
# mode (nessun impatto sull'esecuzione live): perdere questo stato a un
# riavvio del processo significa solo ripartire con un ciclo di "warm-up"
# dell'isteresi, non un problema di sicurezza.
_last_regime: dict[str, str] = {}


def detect_regime(symbol: str, adx: float, trend_direction: str, bbw: float | None = None) -> dict:
    """Determina il regime per `symbol` dato l'ADX corrente (1h) e la
    direzione del trend EMA. Mantiene uno stato di isteresi per simbolo in
    modo che il regime non cambi a ogni singolo ciclo quando l'ADX oscilla
    intorno alle soglie.

    Ritorna un dict con:
    - regime: "TREND_BULL" | "TREND_BEAR" | "TREND_FLAT" | "TRANSITIONAL" | "RANGE"
    - confidence_cap: float|None -- tetto di confidenza da applicare ai
      segnali quando il regime è "TRANSITIONAL", altrimenti None
    - adx, bbw: gli input usati (utile per il logging/debug)
    """
    prev = _last_regime.get(symbol)
    was_trending = bool(prev and prev.startswith("TREND"))

    if adx >= ADX_TREND_IN:
        is_trending = True
    elif adx < ADX_TREND_OUT:
        is_trending = False
    else:
        # Zona grigia 20-25: isteresi -- resta nello stato precedente
        # invece di decidere da zero ogni volta.
        is_trending = was_trending

    if is_trending:
        if trend_direction == 'bullish':
            regime = "TREND_BULL"
        elif trend_direction == 'bearish':
            regime = "TREND_BEAR"
        else:
            regime = "TREND_FLAT"
        confidence_cap = None
    elif ADX_TREND_OUT <= adx < ADX_TREND_IN:
        regime = "TRANSITIONAL"
        confidence_cap = TRANSITIONAL_CONFIDENCE_CAP
    else:
        regime = "RANGE"
        confidence_cap = None

    _last_regime[symbol] = regime
    return {"regime": regime, "confidence_cap": confidence_cap, "adx": round(adx, 2),
            "bbw": round(bbw, 4) if bbw is not None else None}


# ── Guardia di sessione LBMA per XAU/XAG (trovato Qwen) ───────────────────────
# Intorno agli orari di fixing del London Bullion Market (oro: ~10:30 e
# ~15:00 ora di Londra; argento: ~12:00), il prezzo spot di oro/argento
# puo' avere un salto di volatilita' legato al meccanismo di fixing in se'
# piuttosto che a un vero movimento di mercato -- un classico falso
# segnale per strategie momentum/breakout. Come per TRANSITIONAL_CONFIDENCE_CAP
# sopra, questo e' per ora solo calcolato e loggato, non ancora applicato
# alla confidence reale delle strategie.
LBMA_GOLD_FIXING_TIMES_LONDON = [(10, 30), (15, 0)]
LBMA_SILVER_FIXING_TIME_LONDON = (12, 0)
LBMA_GUARD_WINDOW_MINUTES = 10.0
LBMA_GUARD_CONFIDENCE_CAP = 60.0


def _metal_of(symbol: str) -> str | None:
    sym = str(symbol or "").upper()
    if "XAU" in sym:
        return "gold"
    if "XAG" in sym:
        return "silver"
    return None


def lbma_fixing_guard(symbol: str, now_utc: datetime | None = None) -> dict:
    """Guardia di sessione per i fixing LBMA su oro/argento.

    Non e' un veto duro: ritorna solo un tetto di confidenza quando `now_utc`
    (default: adesso) cade dentro +/- LBMA_GUARD_WINDOW_MINUTES minuti da un
    orario di fixing. Nessun effetto su simboli diversi da XAU/XAG
    (ritorna active=False, confidence_cap=None).
    """
    metal = _metal_of(symbol)
    if metal is None:
        return {"active": False, "confidence_cap": None, "metal": None, "minutes_to_fixing": None}

    now_utc = now_utc or datetime.now(timezone.utc)
    if _LONDON_TZ is not None:
        now_london = now_utc.astimezone(_LONDON_TZ)
    else:
        # Fallback senza tzdata disponibile: approssima Londra come UTC
        # (errore di massimo un'ora durante l'ora legale britannica) --
        # non ideale, ma e' un dato puramente informativo e non deve mai
        # far fallire il bot per questo.
        now_london = now_utc

    fixing_times = LBMA_GOLD_FIXING_TIMES_LONDON if metal == "gold" else [LBMA_SILVER_FIXING_TIME_LONDON]
    best_delta = min(
        abs((now_london - now_london.replace(hour=hh, minute=mm, second=0, microsecond=0)).total_seconds()) / 60.0
        for hh, mm in fixing_times
    )
    active = best_delta <= LBMA_GUARD_WINDOW_MINUTES
    return {
        "active": active,
        "confidence_cap": LBMA_GUARD_CONFIDENCE_CAP if active else None,
        "metal": metal,
        "minutes_to_fixing": round(best_delta, 1),
    }


def reset_state(symbol: str | None = None) -> None:
    """Azzera lo stato di isteresi (tutto, o solo per un symbol) -- usato
    principalmente nei test."""
    if symbol is None:
        _last_regime.clear()
    else:
        _last_regime.pop(symbol, None)
