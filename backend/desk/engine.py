"""Conto di paper trading V2: DCA su 3 ingressi, leva per asset class, chiusura dinamica.

Nessuna rete, nessuna chiave: solo contabilita'. Tutte le cifre sono in dollari finti.

Classi di asset e leva massima:
  TIER_A (BTC, XAU, XAG): leva max 45x
  TIER_B (ETH):            leva max 30x
  TIER_C (altri top-30):   leva max 25x
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os
import math
from typing import Optional

# ---- asset tier (leva massima)
TIER_A = {"BTC", "XAU", "XAG", "XAUUSDT", "XAGUSDT"}   # 45x
TIER_B = {"ETH"}                                          # 30x
# tutto il resto: 25x


def max_leverage_for(symbol: str) -> int:
    base = symbol.upper().replace("USDT", "").replace("PERP", "").strip("/:")
    if base in TIER_A:
        return 45
    if base in TIER_B:
        return 30
    return 25


@dataclass
class Limits:
    start_equity: float = 1000.0
    max_leverage: int = 45            # tetto globale (ignorato se il tier è più basso)
    max_margin_trade: float = 400.0   # V2: aumentato da 250 a 400
    max_margin_total: float = 2000.0  # V2: alzato per supportare fino a 10 posizioni (10×200$)
    max_open: int = 10                # V2: fino a 10 posizioni contemporanee
    max_dca_total: float = 700.0      # DCA: mai più di 700$ su un singolo asset (tutti gli ingressi)
    min_margin: float = 30.0    # minimo per paper test; cli.py GUARDRAIL forza 150$ live
    fee_bp_side: float = 6.0
    slip_bp_side: float = 2.0
    funding_bp_8h_long: float = 1.0
    maint: float = 0.005
    sl_liq_frac: float = 0.75        # V2: leggermente più morbido (era 0.8)
    daily_stop: float = 0.12         # Approved rollback: historical 5818 daily stop, vault-only policy.
    kill_equity: float = 450.0       # V2: abbassato da 500 a 450
    # Restrict NEW entries only; never upscale AI margin/leverage to satisfy the floor.
    # Existing positions, closures and ordinary DCA management retain their semantics.
    min_initial_margin: float = 0.0
    min_initial_leverage: int = 1


@dataclass
class DcaLevel:
    """Un ingresso DCA aggiuntivo su una posizione esistente."""
    margin: float
    entry: float      # prezzo d'ingresso con slippage
    qty: float
    fee: float
    added_ms: int
    trigger_pct: float   # quanto doveva scendere/salire dal precedente per scattare


@dataclass
class Position:
    id: int
    symbol: str
    side: int                  # +1 long, -1 short
    margin: float              # margine dell'ingresso principale
    leverage: int
    entry: float               # prezzo medio ponderato di tutti gli ingressi
    qty: float                 # quantità totale
    sl: float                  # stop loss attuale (aggiornato ad ogni DCA)
    tp: Optional[float]
    open_ms: int
    liq: float
    confidence: int = 0
    reason: str = ""
    source: str = "rules"
    fee_open: float = 0.0      # fee totale apertura (incluse DCA)
    last_review_ms: int = 0
    review_price: float = 0.0
    dca_levels: list = field(default_factory=list)   # lista di DcaLevel serializzati
    total_margin: float = 0.0  # margine totale (principale + DCA)
    trade_type: str = "medio"  # "scalp" | "medio"
    dca_count: int = 0         # quanti DCA eseguiti
    # ---- registrazione per l'apprendimento (tutti con valore predefinito: gli stati vecchi si caricano)
    features: dict = field(default_factory=dict)   # valori su cui si e' deciso l'ingresso
    risk_plan_usd: float = 0.0   # 1R in dollari: margine pianificato x leva x distanza dello stop
    r_dist: float = 0.0          # distanza dello stop iniziale come frazione del prezzo (1R in prezzo)
    entry0: float = 0.0          # primo prezzo di ingresso (riferimento per MAE/MFE)
    px_hi: float = 0.0           # massimo toccato dall'apertura
    px_lo: float = 0.0           # minimo toccato dall'apertura
    legs: int = 1                # ingressi principali effettivamente eseguiti (2 con entrata diversificata)
    # ---- entrata diversificata: seconda gamba in attesa (None = nessuna)
    pending_split: Optional[dict] = None
    # ---- barre gia' giudicate (orario di APERTURA dell'ultima barra elaborata; 0 = nessuna). Ogni barra si
    # giudica UNA volta sola, con gli stop/TP in vigore in quel momento: un livello cambiato dopo (DCA,
    # chiusura parziale) vale solo per le barre successive, mai per quelle gia' passate (difetto A). -1 = nessuna.
    last_bar_ms: int = -1


LEGACY_BAR_MS = 900_000         # barra dei bot (15m): serve solo a caricare posizioni salvate prima di last_bar_ms
SPLIT_FIRST_FRAC = 0.5         # quota di margine della prima gamba
SPLIT_MIN_RETRACE = 0.0015      # sotto lo 0,15% la seconda gamba non ha senso: ingresso unico
SPLIT_STOP_FRAC = 0.6           # il ritracciamento non supera il 60% della distanza dello stop
SPLIT_TTL_MS = {"scalp": 3 * 3_600_000, "medio": 12 * 3_600_000}


def liq_price(side: int, entry: float, lev: int, maint: float) -> float:
    return entry * (1 - side * (1 / lev - maint))


def weighted_entry(old_entry: float, old_qty: float, new_fill: float, new_qty: float) -> float:
    total = old_qty + new_qty
    return (old_entry * old_qty + new_fill * new_qty) / total if total > 0 else old_entry


class PaperAccount:
    def __init__(self, limits: Limits = Limits(), name: str = "main"):
        self.limits, self.name = limits, name
        self.cash = limits.start_equity
        self.positions: dict = {}
        self.closed: list = []
        self.next_id = 1
        self.day = ""
        self.day_start_equity = limits.start_equity
        # eventi prodotti dal motore (seconda gamba eseguita/annullata): li legge e svuota cli.py.
        # Non fanno parte dello stato salvato.
        self.events: list = []
        # V1 percentage policies are opt-in: legacy accounts behave identically until
        # a validated PAPER capital-day snapshot enables them.
        self._capital_bot = None
        self._capital_day_budget = None
        self._capital_reference = None

    def set_capital_policy(self, bot: str, day_budget, reference=None) -> None:
        # Hard fail-closed: Capital Management V1 is intentionally PAPER-only.
        if os.getenv("DESK_MODE", "paper").strip().lower() != "paper":
            raise ValueError("Capital V1 policy must never run in live mode")
        from .position_sizer import cap_for
        self._capital_day_budget = float(day_budget)
        cap_for(bot, self._capital_day_budget)  # checks bot, finite, 0..1000
        self._capital_bot = bot
        self._capital_reference = reference

    def _capital_size(self, symbol: str, proposed: float, lev: int,
                      *, new_position: bool, release_split: bool = False):
        if self._capital_day_budget is None:
            return None
        from .position_sizer import size_request
        total = 0.0
        for k, p in self.positions.items():
            total += p.total_margin
            if p.pending_split and not (k == symbol and release_split):
                total += float(p.pending_split.get("margin", 0))
        own = self.positions.get(symbol)
        own_margin = own.total_margin if own else 0.0
        own_pending = (float(own.pending_split.get("margin", 0)) if own and own.pending_split
                       and not release_split else 0.0)
        # A DCA or second leg is new risk: never bypass a latched daily stop.
        blocked = bool(self._capital_reference and self._capital_reference.stop_latched)
        if self._capital_reference is not None and self.positions:
            quote_map=getattr(self,"_capital_latest_prices",{})
            if not all(sym in quote_map for sym in self.positions):
                blocked=True  # no new exposure from incomplete marks
            else:
                from .capital_manager import risk_view
                blocked=blocked or risk_view(self._capital_reference,
                                            self.equity(quote_map),
                                            kill_equity=self.limits.kill_equity).reason!=""
        return size_request(bot=self._capital_bot, day_budget=self._capital_day_budget,
                            already_in_position=own_margin,
                            pending_same_position=own_pending,
                            total_committed_margin=total, available_cash=self.cash,
                            reserved_cash=0, request=proposed,
                            minimum_executable=self.limits.min_margin,
                            fee_fraction=lev * self.limits.fee_bp_side / 10000,
                            n_open=len(self.positions), is_new=new_position,
                            risk_reason="daily_stop" if blocked else "")

    def margin_in_use(self) -> float:
        return sum(p.total_margin for p in self.positions.values())

    def unrealized(self, prices: dict) -> float:
        return sum(p.side * (prices.get(p.symbol, p.entry) - p.entry) * p.qty for p in self.positions.values())

    def equity(self, prices: dict) -> float:
        return self.cash + self.margin_in_use() + self.unrealized(prices)

    def roll_day(self, day: str, prices: dict) -> None:
        if day != self.day:
            self.day, self.day_start_equity = day, self.equity(prices)

    def halted(self, prices: dict) -> str:
        eq = self.equity(prices)
        if self._capital_reference is not None:
            if any(sym not in prices for sym in self.positions):
                return "prezzi di mercato incompleti"
            from .capital_manager import risk_view
            view = risk_view(self._capital_reference, eq, kill_equity=self.limits.kill_equity)
            if view.reason == "kill_equity":
                return "capitale sotto la soglia minima"
            if view.stop_latched:
                return "stop giornaliero raggiunto"
            return ""
        if eq <= self.limits.kill_equity:
            return "capitale sotto la soglia minima"
        if eq <= self.day_start_equity * (1 - self.limits.daily_stop):
            return "stop giornaliero raggiunto"
        return ""

    # ---- apertura
    def open(self, symbol: str, side: int, margin: float, leverage: int, price: float, sl: float,
             tp: Optional[float], now_ms: int, prices: dict, confidence: int = 0, reason: str = "",
             source: str = "rules", trade_type: str = "medio",
             features: Optional[dict] = None, split: Optional[dict] = None) -> tuple:
        """Apre una posizione. Con `split` ({"retrace_pct", "first_frac", "ttl_ms"}) apre solo la prima
        gamba (50% del margine) e lascia in attesa la seconda al ritracciamento indicato. Se la seconda
        gamba non avrebbe senso (stop troppo vicino, margini sotto il minimo) apre tutto subito."""
        L = self.limits
        if side not in (1, -1):
            return None, "lato non valido"
        if symbol in self.positions:
            return None, "posizione gia' aperta su questa coppia"
        if len(self.positions) >= L.max_open:
            return None, "troppe posizioni aperte"
        h = self.halted(prices)
        if h:
            return None, h
        if not (price > 0 and sl and sl > 0):
            return None, "stop loss obbligatorio"
        if (side == 1 and sl >= price) or (side == -1 and sl <= price):
            return None, "stop dal lato sbagliato"
        # Refuse invalid proposals before min/max can hide NaN or infinity.
        try:
            values = [margin, leverage, price, sl]
            if tp is not None:
                values.append(tp)
            if not all(math.isfinite(float(v)) for v in values):
                return None, "parametri apertura non finiti"
        except (TypeError, ValueError, OverflowError):
            return None, "parametri apertura non validi"
        if tp is not None and ((side == 1 and tp <= price) or (side == -1 and tp >= price)):
            tp = None
        # Both configured ceiling and asset tier are physical limits.
        tier_max = min(L.max_leverage, max_leverage_for(symbol))
        lev = int(max(1, min(int(leverage), tier_max)))
        if lev < L.min_initial_leverage:
            return None, (f"leva eseguibile {lev}x sotto il minimo per nuova posizione "
                          f"{L.min_initial_leverage}x (cap strumento {tier_max}x)")
        room = min(L.max_margin_trade, L.max_margin_total - self.margin_in_use(), self.cash * 0.95)
        mar = min(float(margin), room)
        gate = self._capital_size(symbol, mar, lev, new_position=True)
        if gate is not None:
            if not gate.approved:
                return None, "capitale percentuale: " + gate.reason
            mar = float(gate.amount)
        if mar < max(L.min_margin, L.min_initial_margin) - 1e-8:
            return None, ("margine disponibile sotto il minimo per nuova posizione "
                          f"{L.min_initial_margin:.0f}$; non aumentare la size proposta")
        fill = price * (1 + side * L.slip_bp_side / 1e4)
        dist = abs(fill - sl) / fill
        if dist > L.sl_liq_frac * (1 / lev - L.maint):
            return None, "stop troppo lontano (liquidazione verrebbe prima)"
        plan_margin = mar            # margine pianificato per l'intero ingresso (entrambe le gambe)
        pending = None
        if split:
            retr = min(float(split.get("retrace_pct") or 0.0), SPLIT_STOP_FRAC * dist)
            first = round(mar * float(split.get("first_frac", SPLIT_FIRST_FRAC)), 2)
            second = round(mar - first, 2)
            if retr >= SPLIT_MIN_RETRACE and first >= L.min_margin and second >= L.min_margin:
                if first < L.min_initial_margin - 1e-8:
                    return None, ("prima gamba split sotto il minimo per nuova posizione "
                                  f"{L.min_initial_margin:.0f}$")
                mar = first
                ttl = int(split.get("ttl_ms") or SPLIT_TTL_MS.get(trade_type, SPLIT_TTL_MS["medio"]))
                pending = {"trigger": price * (1 - side * retr), "margin": second,
                           "retrace_pct": round(retr, 5), "created_ms": now_ms, "expire_ms": now_ms + ttl}
        notional = mar * lev
        fee = notional * L.fee_bp_side / 1e4
        if mar + fee > self.cash:
            return None, "cassa insufficiente"
        pos = Position(
            id=self.next_id, symbol=symbol, side=side, margin=mar, leverage=lev,
            entry=fill, qty=notional / fill,
            sl=float(sl), tp=None if tp is None else float(tp),
            open_ms=now_ms, liq=liq_price(side, fill, lev, L.maint),
            confidence=int(confidence), reason=reason[:300], source=source,
            fee_open=fee, last_review_ms=now_ms, review_price=price,
            dca_levels=[], total_margin=mar, trade_type=trade_type, dca_count=0,
            features=dict(features or {}), risk_plan_usd=round(plan_margin * lev * dist, 4),
            r_dist=dist, entry0=fill, px_hi=fill, px_lo=fill, legs=1, pending_split=pending,
        )
        self.next_id += 1
        self.cash -= mar + fee
        self.positions[symbol] = pos
        return pos, "ok"

    # ---- DCA: aggiunge un ingresso a una posizione esistente
    def add_dca(self, symbol: str, new_sl: float, new_tp: Optional[float],
                now_ms: int, prices: dict, reason: str = "") -> tuple:
        """Aggiunge un secondo/terzo ingresso DCA se le condizioni lo permettono.
        Il margine del DCA è proporzionale a quello già investito (50% primo, 30% secondo, 20% terzo).
        """
        L = self.limits
        halt = self.halted(prices)
        if halt:
            return None, halt + ": DCA bloccato"
        pos = self.positions.get(symbol)
        if pos is None:
            return None, "nessuna posizione"
        if pos.dca_count >= 2:
            return None, "max 2 DCA aggiuntivi raggiunti (3 ingressi totali)"
        # scalp: DCA non consentito (solo medio)
        if pos.trade_type == "scalp":
            return None, "DCA non consentito su scalp: chiudi e riapri"
        px = prices.get(symbol)
        if px is None:
            return None, "prezzo non disponibile"
        # verifica che il prezzo sia sfavorevole (DCA ha senso)
        if pos.side == 1 and px >= pos.entry:
            return None, "prezzo non ancora sceso per DCA long"
        if pos.side == -1 and px <= pos.entry:
            return None, "prezzo non ancora salito per DCA short"
        # lo stop non si allarga mai (difetto D): il DCA puo' solo tenerlo uguale o avvicinarlo
        tight_sl = max(pos.sl, float(new_sl)) if pos.side == 1 else min(pos.sl, float(new_sl))
        if (pos.side == 1 and tight_sl >= px) or (pos.side == -1 and tight_sl <= px):
            return None, "stop gia' raggiunto: niente DCA"
        # calcola margine DCA
        fracs = [0.40, 0.25]  # frazioni del margine principale per DCA 1/2 (max 2 ingressi extra)
        dca_mar = round(pos.margin * fracs[pos.dca_count], 2)
        if dca_mar < L.min_margin:
            dca_mar = L.min_margin
        # Added exposure must also fit the portfolio's aggregate margin cap.
        dca_mar = min(dca_mar, L.max_margin_total - self.margin_in_use())
        if dca_mar < L.min_margin:
            return None, "tetto margine totale: DCA bloccato"
        # verifica tetto DCA totale
        if pos.total_margin + dca_mar > L.max_dca_total:
            dca_mar = L.max_dca_total - pos.total_margin
        if dca_mar < L.min_margin:
            return None, "tetto DCA raggiunto"
        gate = self._capital_size(symbol, dca_mar, pos.leverage,
                                  new_position=False, release_split=True)
        if gate is not None:
            if not gate.approved:
                return None, "capitale percentuale DCA: " + gate.reason
            dca_mar = float(gate.amount)
        if dca_mar > self.cash * 0.95:
            return None, "cassa insufficiente per DCA"
        fill = px * (1 + pos.side * L.slip_bp_side / 1e4)
        notional = dca_mar * pos.leverage
        fee = notional * L.fee_bp_side / 1e4
        if dca_mar + fee > self.cash:
            return None, "cassa insufficiente per DCA"
        new_qty = notional / fill
        # aggiorna entry media ponderata
        old_entry, old_qty = pos.entry, pos.qty
        pos.entry = weighted_entry(old_entry, old_qty, fill, new_qty)
        pos.qty += new_qty
        pos.total_margin += dca_mar
        pos.fee_open += fee
        widened = tight_sl != float(new_sl)
        pos.sl = tight_sl
        if new_tp is not None:
            pos.tp = float(new_tp)
        # ricalcola liquidazione sul nuovo entry medio
        pos.liq = liq_price(pos.side, pos.entry, pos.leverage, L.maint)
        trigger_pct = abs(fill - old_entry) / old_entry
        pos.dca_levels.append({"margin": dca_mar, "entry": fill, "qty": new_qty,
                                "fee": fee, "added_ms": now_ms, "trigger_pct": round(trigger_pct, 4)})
        pos.dca_count += 1
        pos.reason = (pos.reason[:200] + f" | DCA{pos.dca_count} @{fill:.5g}"
                      + (" (stop non allargato)" if widened else "") + f": {reason[:80]}")[:300]
        self.cash -= dca_mar + fee
        self._cancel_split(pos, "DCA eseguito", now_ms)   # un DCA sostituisce la seconda gamba
        return pos, "ok"

    # ---- entrata diversificata: seconda gamba
    def _cancel_split(self, pos: Position, reason: str, now_ms: int) -> None:
        """Annulla la seconda gamba in attesa (se c'e') e lascia traccia nell'elenco eventi."""
        ps = pos.pending_split
        if not ps:
            return
        pos.pending_split = None
        self.events.append({"ev": "split_cancel", "id": pos.id, "symbol": pos.symbol, "ts": now_ms,
                            "reason": reason, "margin": ps.get("margin"), "trigger": ps.get("trigger")})

    def cancel_split(self, symbol: str, reason: str, now_ms: int) -> bool:
        pos = self.positions.get(symbol)
        if pos is None or not pos.pending_split:
            return False
        self._cancel_split(pos, reason, now_ms)
        return True

    def _fill_split(self, pos: Position, now_ms: int) -> Optional[dict]:
        """Esegue la seconda gamba al prezzo limite indicato (con slippage e commissioni come ogni
        altro ingresso). Rispetta tetti di margine e cassa: se non c'e' spazio la annulla."""
        ps = pos.pending_split
        if not ps:
            return None
        L = self.limits
        marks = dict(getattr(self, "_capital_latest_prices", {}))
        marks[pos.symbol] = float(ps["trigger"])
        halt = self.halted(marks)
        if halt:
            self._cancel_split(pos, halt + ": seconda gamba bloccata", now_ms)
            return None
        pos.pending_split = None     # consumata in ogni caso: o eseguita o annullata
        room = min(L.max_margin_trade - pos.total_margin, L.max_margin_total - self.margin_in_use(),
                   self.cash * 0.95)
        mar = min(float(ps["margin"]), room)
        gate = self._capital_size(pos.symbol, mar, pos.leverage, new_position=False)
        if gate is not None:
            if not gate.approved:
                self.events.append({"ev": "split_cancel", "id": pos.id, "symbol": pos.symbol,
                                    "ts": now_ms, "reason": "capitale percentuale: " + gate.reason})
                return None
            mar = float(gate.amount)
        trig = float(ps["trigger"])
        fill = trig * (1 + pos.side * L.slip_bp_side / 1e4)
        notional = mar * pos.leverage
        fee = notional * L.fee_bp_side / 1e4
        if mar < L.min_margin or mar + fee > self.cash:
            self.events.append({"ev": "split_cancel", "id": pos.id, "symbol": pos.symbol, "ts": now_ms,
                                "reason": "margine non disponibile", "margin": ps.get("margin"),
                                "trigger": trig})
            return None
        new_qty = notional / fill
        pos.entry = weighted_entry(pos.entry, pos.qty, fill, new_qty)
        pos.qty += new_qty
        pos.total_margin += mar
        pos.margin += mar            # il "margine principale" (base dei DCA) comprende entrambe le gambe
        pos.fee_open += fee
        pos.liq = liq_price(pos.side, pos.entry, pos.leverage, L.maint)
        pos.legs = 2
        pos.reason = (pos.reason[:230] + f" | 2a gamba @{fill:.5g}")[:300]
        self.cash -= mar + fee
        ev = {"ev": "split_fill", "id": pos.id, "symbol": pos.symbol, "side": pos.side, "ts": now_ms,
              "price": fill, "margin": round(mar, 2), "entry_avg": pos.entry,
              "total_margin": pos.total_margin}
        self.events.append(ev)
        return ev

    def _learn_fields(self, pos: Position, net: float, now_ms: int) -> dict:
        """Valori per l'apprendimento che accompagnano ogni record di chiusura (finale o parziale):
        net_r e' additivo, quindi la somma dei record con lo stesso id e' il risultato in R del trade."""
        risk = pos.risk_plan_usd
        out = {"risk_plan_usd": round(risk, 4), "legs": pos.legs, "r_dist": round(pos.r_dist, 5),
               "net_r": round(net / risk, 4) if risk > 0 else None,
               "hold_min": round(max(0, now_ms - pos.open_ms) / 60_000, 1)}
        if pos.entry0 > 0 and pos.r_dist > 0 and pos.px_hi > 0 and pos.px_lo > 0:
            d = pos.entry0 * pos.r_dist
            best = pos.px_hi if pos.side == 1 else pos.px_lo
            worst = pos.px_lo if pos.side == 1 else pos.px_hi
            out["mfe_r"] = round(max(0.0, pos.side * (best - pos.entry0)) / d, 3)
            out["mae_r"] = round(max(0.0, pos.side * (pos.entry0 - worst)) / d, 3)
        return out

    # ---- chiusura
    def _close(self, pos: Position, exit_price: float, now_ms: int, why: str) -> dict:
        L = self.limits
        exit_fill = exit_price * (1 - pos.side * L.slip_bp_side / 1e4) if why != "liquidazione" else exit_price
        gross = pos.side * (exit_fill - pos.entry) * pos.qty
        fee_close = pos.qty * exit_fill * L.fee_bp_side / 1e4
        hours = max(0.0, (now_ms - pos.open_ms) / 3_600_000)
        funding = (pos.qty * pos.entry * L.funding_bp_8h_long / 1e4 * hours / 8) if pos.side == 1 else 0.0
        net = gross - pos.fee_open - fee_close - funding
        back = max(0.0, pos.total_margin + gross - fee_close - funding)
        if why == "liquidazione":
            back = 0.0
        self.cash += back
        del self.positions[pos.symbol]
        rec = {"id": pos.id, "symbol": pos.symbol, "side": pos.side, "margin": pos.total_margin,
               "leverage": pos.leverage, "entry": pos.entry, "exit": exit_fill, "open_ms": pos.open_ms,
               "close_ms": now_ms, "net": round(net, 4), "gross": round(gross, 4),
               "fees": round(pos.fee_open + fee_close, 4), "funding": round(funding, 4),
               "why": why, "confidence": pos.confidence, "reason": pos.reason, "source": pos.source,
               "account": self.name, "trade_type": pos.trade_type, "dca_count": pos.dca_count}
        if why == "liquidazione":
            rec["net"] = round(-pos.total_margin - pos.fee_open, 4)
        rec.update(self._learn_fields(pos, rec["net"], now_ms))
        if pos.pending_split:     # posizione chiusa con la seconda gamba ancora in attesa: svanisce
            self._cancel_split(pos, f"posizione chiusa ({why})", now_ms)
        self.closed.append(rec)
        return rec

    def close(self, symbol: str, price: float, now_ms: int, why: str = "chiusura decisa") -> Optional[dict]:
        pos = self.positions.get(symbol)
        return None if pos is None else self._close(pos, price, now_ms, why)

    def partial_close(self, symbol: str, price: float, now_ms: int, fraction: float,
                      new_tp: Optional[float] = None, why: str = "TP parziale") -> Optional[dict]:
        """Chiude una frazione della posizione (es. 0.35 = 35%) e lascia il resto aperto.

        Restituisce un record-trade per la parte chiusa (tagged partial=True).
        La posizione viene ridotta proporzionalmente (qty, margin, fee_open).
        """
        pos = self.positions.get(symbol)
        if pos is None:
            return None
        fraction = max(0.05, min(0.95, fraction))  # tra 5% e 95%
        L = self.limits
        exit_fill = price * (1 - pos.side * L.slip_bp_side / 1e4)

        close_qty = pos.qty * fraction
        close_margin = pos.total_margin * fraction
        close_fee_open = pos.fee_open * fraction
        fee_close = close_qty * exit_fill * L.fee_bp_side / 1e4
        gross = pos.side * (exit_fill - pos.entry) * close_qty
        hours = max(0.0, (now_ms - pos.open_ms) / 3_600_000)
        funding = (close_qty * pos.entry * L.funding_bp_8h_long / 1e4 * hours / 8) if pos.side == 1 else 0.0
        net = gross - close_fee_open - fee_close - funding
        back = max(0.0, close_margin + gross - fee_close - funding)
        self.cash += back

        # riduce la posizione
        pos.qty -= close_qty
        pos.total_margin -= close_margin
        pos.fee_open -= close_fee_open
        if new_tp is not None:
            pos.tp = float(new_tp)

        rec = {"id": pos.id, "symbol": symbol, "side": pos.side,
               "margin": round(close_margin, 4), "leverage": pos.leverage,
               "entry": pos.entry, "exit": exit_fill, "open_ms": pos.open_ms,
               "close_ms": now_ms, "net": round(net, 4), "gross": round(gross, 4),
               "fees": round(close_fee_open + fee_close, 4), "funding": round(funding, 4),
               "why": why, "confidence": pos.confidence, "reason": pos.reason,
               "source": pos.source, "account": self.name,
               "trade_type": pos.trade_type, "dca_count": pos.dca_count,
               "partial": True, "fraction": round(fraction, 3)}
        rec.update(self._learn_fields(pos, net, now_ms))
        self._cancel_split(pos, "chiusura parziale", now_ms)   # ridurre il rischio esclude di aumentarlo
        self.closed.append(rec)
        return rec

    @staticmethod
    def _exit_touched(pos: Position, h: float, l: float) -> bool:
        """La barra tocca liquidazione, stop o TP con i livelli ATTUALI della posizione (prima gamba)."""
        if pos.side == 1:
            return l <= pos.liq or l <= pos.sl or (pos.tp is not None and h >= pos.tp)
        return h >= pos.liq or h >= pos.sl or (pos.tp is not None and l <= pos.tp)

    def on_bar(self, symbol: str, t: int, o: float, h: float, l: float, c: float, bar_ms: int,
               exit_first: bool = False) -> Optional[dict]:
        """Giudica una barra chiusa. `exit_first=True` e' solo per il LIVE: la seconda gamba parte sull'exchange
        DOPO la candela (ordine a mercato), quindi se la candela chiude comunque la posizione quella gamba non e'
        mai esistita e non si contabilizza. Con il valore predefinito (paper) l'ipotesi resta quella di sempre."""
        pos = self.positions.get(symbol)
        # Si giudicano le barre che FINISCONO dopo l'apertura, compresa quella in cui la posizione e' nata
        # (prima veniva saltata: per i primi minuti stop e TP non esistevano). Ogni barra una volta sola.
        # APPROSSIMAZIONE DICHIARATA: la barra d'apertura contiene anche prezzi precedenti all'ingresso (la candela
        # non dice quando) e il suo massimo/minimo puo' far scattare stop o TP per movimenti avvenuti prima
        # dell'apertura; lo stop prevale sempre sul TP. Una chiusura su quella barra si riconosce dal record:
        # hold_min <= durata della barra (15 min). Quanto pesa si misura sui trade, non si stima.
        if pos is None or t + bar_ms <= pos.open_ms or t <= pos.last_bar_ms:
            return None
        pos.last_bar_ms = t
        end = t + bar_ms
        # estremi toccati dall'apertura (per MAE/MFE): prima dei controlli, cosi' includono la barra di uscita
        if pos.px_hi > 0 and pos.px_lo > 0:
            pos.px_hi, pos.px_lo = max(pos.px_hi, h), min(pos.px_lo, l)
        # seconda gamba dell'entrata diversificata. Se nella stessa barra tocca anche lo stop, il prezzo
        # ha attraversato prima il livello del ritracciamento (piu' vicino): la gamba si esegue e poi
        # scatta lo stop. E' l'ipotesi piu' sfavorevole, quella corretta per un test onesto.
        # (Questo vale in PAPER. In LIVE, con exit_first, vale l'opposto: la gamba parte sull'exchange dopo la candela.)
        ps = pos.pending_split
        if ps:
            if t >= ps["expire_ms"]:
                self._cancel_split(pos, "scaduta senza ritracciamento", end)
            elif (pos.side == 1 and l <= ps["trigger"]) or (pos.side == -1 and h >= ps["trigger"]):
                # LIVE (exit_first): l'uscita si valuta sui livelli della prima gamba, prima della mediazione;
                # la gamba pendente la annulla _close con l'evento "posizione chiusa".
                if not (exit_first and self._exit_touched(pos, h, l)):
                    self._fill_split(pos, end)
        if pos.side == 1:
            if l <= pos.liq:
                return self._close(pos, pos.liq, end, "liquidazione")
            if l <= pos.sl:
                return self._close(pos, min(pos.sl, o), end, "stop loss")
            if pos.tp is not None and h >= pos.tp:
                return self._close(pos, pos.tp, end, "take profit")
        else:
            if h >= pos.liq:
                return self._close(pos, pos.liq, end, "liquidazione")
            if h >= pos.sl:
                return self._close(pos, max(pos.sl, o), end, "stop loss")
            if pos.tp is not None and l <= pos.tp:
                return self._close(pos, pos.tp, end, "take profit")
        return None

    # ---- persistenza
    def to_dict(self) -> dict:
        return {"name": self.name, "cash": self.cash,
                "positions": {k: asdict(v) for k, v in self.positions.items()},
                "closed": self.closed, "next_id": self.next_id, "day": self.day,
                "day_start_equity": self.day_start_equity, "limits": asdict(self.limits)}

    @classmethod
    def from_dict(cls, d: dict) -> "PaperAccount":
        a = cls(Limits(**d["limits"]), d.get("name", "main"))
        a.cash, a.closed, a.next_id = d["cash"], d["closed"], d["next_id"]
        a.day, a.day_start_equity = d["day"], d["day_start_equity"]
        a.positions = {}
        for k, v in d["positions"].items():
            # compatibilità con posizioni V1 (senza i nuovi campi)
            v.setdefault("dca_levels", [])
            v.setdefault("total_margin", v.get("margin", 0))
            v.setdefault("trade_type", "medio")
            v.setdefault("dca_count", 0)
            # posizione salvata da una versione precedente: la barra d'apertura conta come gia' giudicata,
            # cosi' al primo ciclo dopo l'aggiornamento non si riesamina nulla che prima veniva saltato
            v.setdefault("last_bar_ms", int(v.get("open_ms", 0)) // LEGACY_BAR_MS * LEGACY_BAR_MS)
            a.positions[k] = Position(**v)
        return a
