"""Regime di mercato e gestione dei trade per le regole di Hawk e Bull. Solo funzioni pure: niente rete, niente file.

Perche' esiste (analisi dello storico 12-26/10/2026): le regole aprivano il lato col punteggio piu' alto simbolo per
simbolo, senza guardare il mercato. Gli short guadagnavano in discesa regolare e perdevano nei rimbalzi; i pochi long
si aprivano sui rimbalzi dentro un ribasso e perdevano quasi tutti. Qui il "mercato" e' letto dai punteggi che il bot
calcola gia' (BTC/ETH, ampiezza su tutti i simboli, momento di BTC) e fa tre cose:

1. entry_gate: nuovi short solo se il mercato non e' rialzista (ne' sta girando al rialzo); nuovi long solo se il
   mercato e' rialzista o sta girando al rialzo. Chi apre non e' piu' "il lato col punteggio piu' alto" ma
   "il lato col punteggio piu' alto TRA QUELLI CONSENTITI dal mercato";
2. ratchet: lo stop si alza fino al pareggio e poi segue il prezzo (mai indietro), cosi' un profitto raggiunto non
   torna perdita;
3. flip_exit: se il mercato gira contro una posizione aperta si esce prima dello stop.

Le soglie sono in RegimeParams. Nessun valore qui e' stato approvato in produzione: vedi il banco di prova storico
(deploy/scripts/desk_backtest.py) per come sono state scelte."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Sequence

COMMODITIES = frozenset({"XAU", "XAG"})   # oro e argento non seguono il ciclo cripto: nessun filtro di regime
LEADERS = ("BTC", "ETH")
HIST_MAX = 48                             # cicli di storia del regime tenuti nello stato del bot


@dataclass(frozen=True)
class RegimeParams:
    # ---- lettura del regime
    w_lead: float = 0.45          # peso di BTC+ETH (punteggio long meno short, diviso 100)
    w_breadth: float = 0.35       # peso dell'ampiezza (quanti simboli sono orientati su/giu')
    w_mom: float = 0.20           # peso del momento a 24h di BTC
    breadth_gap: float = 15.0     # differenza di punteggio per dire che un simbolo e' orientato
    mom_scale: float = 0.03       # BTC a +3% in 24h vale "pieno"
    alpha: float = 0.5            # smorzamento: smooth = alpha*grezzo + (1-alpha)*precedente
    state_thr: float = 0.25       # sopra/sotto questa soglia il mercato e' su/giu'; in mezzo e' laterale
    turn_window: int = 8          # cicli guardati per cercare l'inversione
    turn_delta: float = 0.35      # risalita (o discesa) dal minimo (massimo) recente che vale inversione
    turn_floor: float = -0.10     # l'inversione al rialzo vale solo se si e' almeno qui; al ribasso, il suo opposto
    min_hist: int = 3             # storia minima per dichiarare un'inversione
    # ---- ingressi
    gate: bool = True             # False = nessun filtro sugli ingressi (solo per confronti)
    block_short_in_up: bool = True
    long_needs_up: bool = True
    range_extra: int = 3          # punti in piu' richiesti per aprire quando il mercato e' laterale
    capitulation_roc: Optional[float] = -0.03   # BTC a 24h sotto questo valore: niente nuovi short (rimbalzo)
    # ---- gestione delle posizioni
    ratchet: bool = True
    be_at_r: float = 1.0          # raggiunto questo picco (in R) lo stop va a pareggio
    be_lock_r: float = 0.25       # livello del pareggio in R (copre commissioni e scivolamento)
    trail_at_r: float = 1.4       # raggiunto questo picco lo stop segue il prezzo
    trail_gap_r: float = 0.6      # distanza dello stop dal picco, in R
    flip_exit: bool = True
    flip_min_r: float = -0.5      # esco per inversione se la posizione non e' peggio di questo (in R)


FULL = RegimeParams()          # tutte le funzioni accese: banco di prova storico e test


def _env_on(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "on", "si", "yes")


# Profilo di PRODUZIONE. Scelto con il banco "regime applicato ai trade veri di Hawk" (12-26 ottobre, stessi trade dei bot):
# il solo filtro sugli ingressi migliora, lo stop che segue il profitto (ratchet) PEGGIORA perche' accorcia le vincite
# grosse, l'uscita per inversione non cambia nulla; nel laterale i punti in piu' richiesti all'ingresso bloccano short
# vincenti. Quindi: filtro acceso, ratchet e uscita per inversione SPENTI (si accendono con DESK_REGIME_RATCHET=1 e
# DESK_REGIME_FLIP=1), nessun punto in piu' nel laterale (DESK_REGIME_RANGE_EXTRA).
DEFAULT = RegimeParams(ratchet=_env_on("DESK_REGIME_RATCHET", "0"), flip_exit=_env_on("DESK_REGIME_FLIP", "0"),
                       range_extra=int(os.getenv("DESK_REGIME_RANGE_EXTRA", "0") or 0))


@dataclass(frozen=True)
class Regime:
    smooth: float      # -1 (ribasso netto) .. +1 (rialzo netto), smorzato
    raw: float
    state: str         # "up" | "down" | "range"
    turn: str          # "" | "up" | "down": inversione in corso
    lead: float
    breadth: float
    roc: float         # momento a 24h di BTC (frazione)

    def label(self) -> str:
        t = f" inversione {self.turn}" if self.turn else ""
        return (f"{self.state}{t} (indice {self.smooth:+.2f}: guida {self.lead:+.2f}, ampiezza {self.breadth:+.2f}, "
                f"BTC 24h {self.roc:+.1%})")


def _clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def compute(readings: Sequence, hist: Sequence[float], p: Optional[RegimeParams] = None) -> Regime:
    """Regime dai punteggi dell'ultimo ciclo. `hist` = valori smorzati dei cicli precedenti (piu' recente per ultimo)."""
    p = p or DEFAULT
    by = {r.symbol: r for r in readings}
    lead_vals = [(by[s].long_score - by[s].short_score) / 100.0 for s in LEADERS if s in by]
    lead = sum(lead_vals) / len(lead_vals) if lead_vals else 0.0
    pool = [r for r in readings if r.symbol not in COMMODITIES]
    if pool:
        up = sum(1 for r in pool if r.long_score - r.short_score >= p.breadth_gap)
        dn = sum(1 for r in pool if r.short_score - r.long_score >= p.breadth_gap)
        breadth = (up - dn) / len(pool)
    else:
        breadth = 0.0
    btc = by.get("BTC")
    roc = float((btc.facts or {}).get("roc24h", 0.0)) if btc is not None else 0.0
    mom = _clip(roc / p.mom_scale, -1.0, 1.0)
    raw = p.w_lead * lead + p.w_breadth * breadth + p.w_mom * mom
    past = [float(x) for x in hist][-p.turn_window:]
    smooth = raw if not past else p.alpha * raw + (1.0 - p.alpha) * past[-1]
    state = "up" if smooth >= p.state_thr else "down" if smooth <= -p.state_thr else "range"
    turn = ""
    if len(past) >= p.min_hist:
        window = past + [smooth]
        if smooth - min(window) >= p.turn_delta and smooth >= p.turn_floor:
            turn = "up"
        elif max(window) - smooth >= p.turn_delta and smooth <= -p.turn_floor:
            turn = "down"
    return Regime(smooth=round(smooth, 4), raw=round(raw, 4), state=state, turn=turn,
                  lead=round(lead, 4), breadth=round(breadth, 4), roc=round(roc, 4))


def push_hist(hist: Sequence[float], regime: Regime) -> list:
    return (list(hist) + [regime.smooth])[-HIST_MAX:]


# ---------------------------------------------------------------- ingressi
def entry_gate(side: int, symbol: str, regime: Regime, p: Optional[RegimeParams] = None) -> tuple:
    """(consentito, punti_in_piu_richiesti_al_punteggio). Le materie prime non sono filtrate."""
    p = p or DEFAULT
    if symbol in COMMODITIES or not p.gate:
        return True, 0
    if side == -1:
        if p.block_short_in_up and (regime.state == "up" or regime.turn == "up"):
            return False, 0
        if p.capitulation_roc is not None and regime.roc <= p.capitulation_roc:
            return False, 0
        return True, (p.range_extra if regime.state == "range" else 0)
    if side == 1:
        if regime.state == "up":
            return True, 0
        if regime.turn == "up" and regime.smooth >= p.turn_floor:
            return True, p.range_extra
        if not p.long_needs_up and regime.state == "range" and regime.turn != "down":
            return True, 2 * p.range_extra
        return False, 0
    return False, 0


# ---------------------------------------------------------------- gestione
def against_regime(side: int, regime: Regime) -> bool:
    if side == -1:
        return regime.state == "up" or regime.turn == "up"
    if side == 1:
        return regime.state == "down" or regime.turn == "down"
    return False


def flip_exit(side: int, symbol: str, cur_r: float, regime: Regime, p: Optional[RegimeParams] = None) -> Optional[str]:
    """Motivo di uscita se il mercato e' girato contro la posizione (e la perdita non e' gia' oltre flip_min_r)."""
    p = p or DEFAULT
    if not p.flip_exit or symbol in COMMODITIES:
        return None
    if against_regime(side, regime) and cur_r >= p.flip_min_r:
        return f"mercato girato contro la posizione ({regime.state}{'/' + regime.turn if regime.turn else ''}), {cur_r:+.2f}R"
    return None


def ratchet(side: int, entry: float, sl: float, price: float, peak_price: float, r_unit: float,
            p: Optional[RegimeParams] = None) -> tuple:
    """Stop che si alza (mai si abbassa). Ritorna ("none", 0) | ("sl", nuovo_stop) | ("close", livello).
    `r_unit` = 1R in prezzo (distanza dello stop iniziale); `peak_price` = massimo (long) o minimo (short) toccato."""
    p = p or DEFAULT
    if not p.ratchet or r_unit <= 0 or entry <= 0:
        return "none", 0.0
    peak_r = side * (peak_price - entry) / r_unit
    if peak_r >= p.trail_at_r:
        lock_r = peak_r - p.trail_gap_r
    elif peak_r >= p.be_at_r:
        lock_r = p.be_lock_r
    else:
        return "none", 0.0
    lock = entry + side * lock_r * r_unit
    if not ((lock > sl) if side == 1 else (lock < sl)):
        return "none", 0.0
    if (side == 1 and price <= lock) or (side == -1 and price >= lock):
        return "close", lock          # il prezzo e' gia' tornato oltre il livello da proteggere
    return "sl", lock


def r_metrics(side: int, entry: float, price: float, peak_price: float, r_unit: float) -> tuple:
    """(R attuali, R di picco). 0 se i dati non bastano."""
    if r_unit <= 0 or entry <= 0:
        return 0.0, 0.0
    return side * (price - entry) / r_unit, side * (peak_price - entry) / r_unit


# ---------------------------------------------------------------- collegamento con le posizioni del motore
# (usati dal ciclo dei bot E dal banco di prova storico: una sola implementazione)
def r_unit(pos) -> float:
    """1R in prezzo: distanza dello stop iniziale."""
    return float(pos.entry0 * pos.r_dist) if pos.entry0 > 0 and pos.r_dist > 0 else 0.0


def peak_price(pos) -> float:
    """Massimo (long) o minimo (short) toccato dall'apertura."""
    best = pos.px_hi if pos.side == 1 else pos.px_lo
    return float(best) if best and best > 0 else float(pos.entry)


def apply_ratchet(positions: dict, prices: dict, p: Optional[RegimeParams] = None, log=None) -> dict:
    """Alza lo stop delle posizioni (mai indietro). Ritorna {simbolo: livello} per quelle da chiudere subito
    perche' il prezzo e' gia' tornato oltre il livello da proteggere."""
    p = p or DEFAULT
    protect_closes: dict = {}
    for sym, pos in list(positions.items()):
        try:
            kind, lvl = ratchet(pos.side, pos.entry, pos.sl, prices.get(sym, pos.entry), peak_price(pos), r_unit(pos), p)
        except Exception:
            continue
        if kind == "sl":
            if log:
                log(f"[PROTEZIONE] {sym} stop {pos.sl:.5g} -> {lvl:.5g}")
            pos.sl = float(lvl)
        elif kind == "close":
            protect_closes[sym] = lvl
    return protect_closes


def management_closes(pos_info: Sequence, decisions: Sequence, regime: Regime, protect_closes: dict,
                      p: Optional[RegimeParams] = None) -> list:
    """Chiusure da AGGIUNGERE alle decisioni (di Claude o delle regole): profitto protetto e mercato girato,
    solo per le posizioni su cui non c'e' gia' una chiusura, un parziale o un DCA."""
    p = p or DEFAULT
    targeted = {d.get("symbol") for d in decisions if d.get("action") in ("close", "partial_close", "dca")}
    out = []
    for pi in pos_info:
        sym = pi["symbol"]
        if sym in targeted:
            continue
        if sym in protect_closes:
            msg, cw = "profitto protetto: il prezzo e' tornato sotto il livello da difendere", "chiusura profitto protetto"
        else:
            msg, cw = flip_exit(pi["side"], sym, float(pi.get("cur_r") or 0.0), regime, p), "chiusura regime"
        if msg:
            out.append({"symbol": sym, "action": "close", "trade_type": pi.get("trade_type", "medio"),
                        "confidence": 0, "leverage": 1, "margin_usd": 0, "stop_loss_pct": 0, "take_profit_pct": 0,
                        "reason": msg, "close_why": cw, "dca_sl_pct": 0, "dca_tp_pct": 0})
            targeted.add(sym)
    return out
