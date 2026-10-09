"""Profili di rischio del bot (Conservativo / Aggressivo) e regole di costo
del paper trading.

Modulo PURO (nessun accesso a DB, rete o exchange): usato sia dal bot
(bot_engine.py) sia dal simulatore storico (risk_profile_sim.py), cosi' i
numeri che si studiano nel simulatore sono prodotti dallo stesso codice che
dimensiona i trade nel bot.

Come funziona il dimensionamento (vedi `size_trade`)
----------------------------------------------------
1. Lo stop e' a `sl_scale` x ATR(1m) x (1 scalp | 2 medium); il take profit a
   1.5x (scalp) / 3x (medium) la distanza dello stop.
2. La LEVA parte dalla forza del segnale (piu' forte = piu' leva, tra min_lev
   e max_lev) e viene ABBASSATA in automatico se lo stop e' troppo vicino al
   prezzo di liquidazione (`liq_safety`): e' la parte "autoconservativa".
3. "Piu' leva = meno budget": il margine usato scala come (ref_lev/leva)^k,
   cioe' il nozionale (esposizione) cresce come leva^(1-k). Con k=1 la leva
   non cambia l'esposizione (solo il margine bloccato); con k=0.5 la
   esposizione cresce come la radice della leva.
4. La size e' il minimo tra il rischio fisso (risk_pct del capitale fino allo
   stop) e il tetto di esposizione (cap_ref_pct del capitale alla leva ref).

Costi simulati nel paper trading (il paper di prima NON li contava):
commissione taker per lato, slippage avverso su ingresso e uscite "a mercato"
(stop), liquidazione a margine isolato.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

MMR = 0.005                  # maintenance margin rate approssimato (0,5%)
SCALP_TP_RATIO = 1.5         # come risk_manager
MEDIUM_TP_RATIO = 3.0

PROFILE_LABELS = {
    'conservative': 'Conservativo',
    'aggressive': 'Aggressivo',
    'legacy': 'Precedente',
}


@dataclass(frozen=True)
class Profile:
    name: str
    max_lev: int = 10
    min_lev: int = 2
    lev_mode: str = "legacy"       # 'legacy' = int(forza/10) come il vecchio bot; 'scaled' = interpolata
    risk_pct: float = 1.0          # % del capitale perso se lo stop viene colpito
    cap_ref_pct: float = 20.0      # tetto sul nozionale (% capitale) alla leva ref_lev
    ref_lev: int = 10
    margin_exp: float = 1.0        # k: margine ∝ (ref_lev/leva)^k
    liq_safety: float = 0.0        # 0 = disattivato; >0: lo stop sta entro 1/liq_safety della liquidazione
    sl_scale: float = 1.0          # moltiplicatore della distanza di stop
    min_strength: int = 50         # forza minima del segnale per operare


# Valori scelti dai test storici su 2 periodi di mercato (vedi
# risk_profile_sim.py). Entrambi: stop 8x e solo segnali con forza >= 70
# (meno operazioni => meno commissioni). Differiscono per leva ed esposizione.
PRESETS: dict[str, Profile] = {
    'conservative': Profile(
        name='conservative', max_lev=10, min_lev=2, lev_mode='scaled',
        risk_pct=1.0, cap_ref_pct=20.0, ref_lev=10, margin_exp=1.0,
        liq_safety=3.0, sl_scale=8.0, min_strength=70),
    'aggressive': Profile(
        name='aggressive', max_lev=30, min_lev=2, lev_mode='scaled',
        risk_pct=1.0, cap_ref_pct=50.0, ref_lev=10, margin_exp=0.5,
        liq_safety=3.0, sl_scale=8.0, min_strength=70),
}

RISK_MODES = ('conservative', 'aggressive', 'both')


def modes_to_profiles(mode: str) -> list[str]:
    """Modalita' scelta nell'app -> elenco dei profili attivi."""
    if mode == 'both':
        return ['conservative', 'aggressive']
    if mode in PRESETS:
        return [mode]
    return ['conservative']


def with_leverage_ceiling(profile: Profile, ceiling: Optional[int]) -> Profile:
    """Applica un tetto di leva esterno (es. la 'Leva massima' impostata
    dall'utente per il trading reale) senza mai alzarla."""
    if ceiling is None or ceiling >= profile.max_lev:
        return profile
    ceiling = max(1, int(ceiling))
    return replace(profile, max_lev=ceiling, min_lev=min(profile.min_lev, ceiling))


def lev_target(profile: Profile, strength: float) -> int:
    if profile.lev_mode == "legacy":
        # identico a risk_manager: max(min(int(forza/10), MAX), 2)
        return max(min(int(strength / 10), profile.max_lev), profile.min_lev)
    lo = float(max(profile.min_strength, 50))   # forza del segnale: soglia del profilo .. 110 (max)
    t = (strength - lo) / (110.0 - lo) if 110.0 > lo else 1.0
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    lev = int(round(profile.min_lev + t * (profile.max_lev - profile.min_lev)))
    return max(profile.min_lev, min(profile.max_lev, lev))


def size_trade(
    profile: Profile,
    capital: float,
    price: float,
    atr: float,
    side: str,
    trade_type: str,
    strength: float,
    slip_frac: float = 0.0,
) -> Optional[dict]:
    """Calcola leva, quantita', SL, TP per un profilo. None = trade saltato.

    Con `Profile(lev_mode='legacy', margin_exp=1, liq_safety=0, sl_scale=1)`
    riproduce esattamente risk_manager.calculate_trade_params (verificato da
    un test)."""
    if not (price > 0) or not (capital > 0) or not (atr > 0):
        return None
    sl_mult = (1.0 if trade_type == "scalp" else 2.0) * profile.sl_scale
    sl_distance = atr * sl_mult
    if not (sl_distance > 0):
        return None
    tp_ratio = SCALP_TP_RATIO if trade_type == "scalp" else MEDIUM_TP_RATIO
    if side == "long":
        stop_loss = price - sl_distance
        take_profit = price + sl_distance * tp_ratio
    else:
        stop_loss = price + sl_distance
        take_profit = price - sl_distance * tp_ratio
    if stop_loss <= 0 or take_profit <= 0:
        return None
    sl_pct = sl_distance / price

    lev = lev_target(profile, strength)
    if profile.liq_safety > 0:
        # La distanza di liquidazione (~1/leva - MMR) deve essere almeno
        # liq_safety volte la distanza di stop (+ slippage): altrimenti si
        # abbassa la leva. Se nemmeno 1x basta, il trade si salta.
        denom = profile.liq_safety * (sl_pct + slip_frac) + MMR
        lev_cap = int(1.0 / denom)
        if lev_cap < 1:
            return None
        lev = min(lev, lev_cap)
    lev = max(min(lev, profile.max_lev), 1)

    cap_pct = profile.cap_ref_pct * (lev / profile.ref_lev) ** (1.0 - profile.margin_exp)
    max_notional = capital * cap_pct / 100.0
    risk_notional = capital * (profile.risk_pct / 100.0) / sl_pct
    notional = min(risk_notional, max_notional)
    quantity = round(notional / price, 6)
    if quantity <= 0:
        return None
    notional = quantity * price
    return {
        "leverage": lev,
        "quantity": quantity,
        "notional": notional,
        "margin": notional / lev,
        "stop_loss": round(stop_loss, 4),
        "take_profit": round(take_profit, 4),
    }


def liquidation_price(side: str, entry: float, lev: int) -> float:
    """Prezzo di liquidazione approssimato (margine isolato)."""
    dist = 1.0 / lev - MMR
    if dist <= 0:           # leva cosi' alta che il margine non copre nemmeno la manutenzione
        return entry
    return entry * (1.0 - dist) if side == "long" else entry * (1.0 + dist)


# ─────────────────────────────────────────────────────────────────────────────
# Costi del paper trading
# ─────────────────────────────────────────────────────────────────────────────

def entry_fill(price: float, side: str, slip_frac: float) -> float:
    """Prezzo di ingresso con slippage avverso (compri piu' caro, vendi piu' basso)."""
    return price * (1.0 + slip_frac) if side == 'long' else price * (1.0 - slip_frac)


def paper_exit(side: str, price: float, sl: float, tp: float,
               liq: Optional[float], slip_frac: float) -> Optional[tuple[str, float]]:
    """Decide se una posizione paper va chiusa guardando il prezzo corrente.

    Ritorna (motivo, prezzo_di_uscita) con motivo in {'sl','tp','liq'}, o None.
    Ipotesi prudenti: lo stop si riempie al peggiore tra stop e prezzo
    corrente, con slippage avverso; il take profit (ordine limite) al prezzo
    del TP; se il riempimento dello stop supera la liquidazione, e' liquidata
    (perdita del margine)."""
    if side == 'long':
        stop_level = max(sl, liq) if liq else sl
        if price <= stop_level:
            if liq and liq > sl:
                return 'liq', liq
            fill = min(sl, price) * (1.0 - slip_frac)
            if liq and fill <= liq:
                return 'liq', liq
            return 'sl', fill
        if price >= tp:
            return 'tp', tp
    else:
        stop_level = min(sl, liq) if liq else sl
        if price >= stop_level:
            if liq and liq < sl:
                return 'liq', liq
            fill = max(sl, price) * (1.0 + slip_frac)
            if liq and fill >= liq:
                return 'liq', liq
            return 'sl', fill
        if price <= tp:
            return 'tp', tp
    return None


def market_exit_price(side: str, price: float, slip_frac: float) -> float:
    """Uscita 'a mercato' (chiusura manuale) con slippage avverso."""
    return price * (1.0 - slip_frac) if side == 'long' else price * (1.0 + slip_frac)


def paper_pnl(side: str, quantity: float, entry: float, exit_price: float,
              margin: float, reason: str, fee_frac: float) -> tuple[float, float, float]:
    """(lordo, commissioni, netto) di un trade paper chiuso.

    Liquidazione: si perde l'intero margine (margine isolato) piu' la
    commissione d'ingresso."""
    entry_fee = quantity * entry * fee_frac
    if reason == 'liq':
        gross, fees = -margin, entry_fee
    else:
        sgn = 1.0 if side == 'long' else -1.0
        gross = sgn * quantity * (exit_price - entry)
        fees = entry_fee + quantity * exit_price * fee_frac
    return round(gross, 4), round(fees, 4), round(gross - fees, 4)
