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


def reset_state(symbol: str | None = None) -> None:
    """Azzera lo stato di isteresi (tutto, o solo per un symbol) -- usato
    principalmente nei test."""
    if symbol is None:
        _last_regime.clear()
    else:
        _last_regime.pop(symbol, None)
