"""Conto di paper trading con regole realistiche: costi, funding, stop, liquidazione, tetti di rischio.

Nessuna rete, nessuna chiave: solo contabilita'. Tutte le cifre sono in dollari finti.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Limits:
    start_equity: float = 1000.0
    max_leverage: int = 30           # richiesto dall'utente
    max_margin_trade: float = 250.0  # richiesto dall'utente
    max_margin_total: float = 500.0  # tetto aggiunto: margine totale in uso
    max_open: int = 3
    min_margin: float = 10.0
    fee_bp_side: float = 6.0         # commissioni taker per lato
    slip_bp_side: float = 2.0        # slippage per lato (somma a giro = 16 bp come il pool)
    funding_bp_8h_long: float = 1.0  # funding pagato dai long
    maint: float = 0.005             # margine di mantenimento
    sl_liq_frac: float = 0.8         # lo stop deve stare entro l'80% della distanza di liquidazione
    daily_stop: float = 0.10         # perdita giornaliera che ferma i nuovi ingressi
    kill_equity: float = 500.0       # sotto questo capitale il conto smette di aprire


@dataclass
class Position:
    id: int
    symbol: str
    side: int                        # +1 long, -1 short
    margin: float
    leverage: int
    entry: float                     # prezzo di carico (gia' con slippage)
    qty: float
    sl: float
    tp: Optional[float]
    open_ms: int
    liq: float
    confidence: int = 0
    reason: str = ""
    source: str = "rules"
    fee_open: float = 0.0
    last_review_ms: int = 0
    review_price: float = 0.0


def liq_price(side: int, entry: float, lev: int, maint: float) -> float:
    return entry * (1 - side * (1 / lev - maint))


class PaperAccount:
    def __init__(self, limits: Limits = Limits(), name: str = "main"):
        self.limits, self.name = limits, name
        self.cash = limits.start_equity
        self.positions: dict = {}
        self.closed: list = []
        self.next_id = 1
        self.day = ""
        self.day_start_equity = limits.start_equity

    # ---- stato derivato
    def margin_in_use(self) -> float:
        return sum(p.margin for p in self.positions.values())

    def unrealized(self, prices: dict) -> float:
        return sum(p.side * (prices.get(p.symbol, p.entry) - p.entry) * p.qty for p in self.positions.values())

    def equity(self, prices: dict) -> float:
        return self.cash + self.margin_in_use() + self.unrealized(prices)

    def roll_day(self, day: str, prices: dict) -> None:
        if day != self.day:
            self.day, self.day_start_equity = day, self.equity(prices)

    def halted(self, prices: dict) -> str:
        eq = self.equity(prices)
        if eq <= self.limits.kill_equity:
            return "capitale sotto la soglia minima"
        if eq <= self.day_start_equity * (1 - self.limits.daily_stop):
            return "stop giornaliero raggiunto"
        return ""

    # ---- apertura
    def open(self, symbol: str, side: int, margin: float, leverage: int, price: float, sl: float,
             tp: Optional[float], now_ms: int, prices: dict, confidence: int = 0, reason: str = "",
             source: str = "rules") -> tuple:
        """Apre una posizione se rispetta i tetti. Ritorna (Position|None, messaggio). I valori
        eccessivi (leva, margine) vengono RIDOTTI ai tetti; stop mancante o incoerente = rifiuto."""
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
        if tp is not None and ((side == 1 and tp <= price) or (side == -1 and tp >= price)):
            tp = None
        lev = int(max(1, min(int(leverage), L.max_leverage)))
        room = min(L.max_margin_trade, L.max_margin_total - self.margin_in_use(), self.cash * 0.98)
        mar = min(float(margin), room)
        if mar < L.min_margin:
            return None, "margine disponibile troppo basso"
        fill = price * (1 + side * L.slip_bp_side / 1e4)
        dist = abs(fill - sl) / fill
        if dist > L.sl_liq_frac * (1 / lev - L.maint):
            return None, "stop troppo lontano per questa leva (la liquidazione verrebbe prima)"
        notional = mar * lev
        fee = notional * L.fee_bp_side / 1e4
        if mar + fee > self.cash:
            return None, "cassa insufficiente"
        pos = Position(self.next_id, symbol, side, mar, lev, fill, notional / fill, float(sl),
                       None if tp is None else float(tp), now_ms, liq_price(side, fill, lev, L.maint),
                       int(confidence), reason[:300], source, fee, now_ms, price)
        self.next_id += 1
        self.cash -= mar + fee
        self.positions[symbol] = pos
        return pos, "ok"

    # ---- chiusura
    def _close(self, pos: Position, exit_price: float, now_ms: int, why: str) -> dict:
        L = self.limits
        exit_fill = exit_price * (1 - pos.side * L.slip_bp_side / 1e4) if why not in ("liquidazione",) else exit_price
        gross = pos.side * (exit_fill - pos.entry) * pos.qty
        fee_close = pos.qty * exit_fill * L.fee_bp_side / 1e4
        hours = max(0.0, (now_ms - pos.open_ms) / 3_600_000)
        funding = (pos.qty * pos.entry * L.funding_bp_8h_long / 1e4 * hours / 8) if pos.side == 1 else 0.0
        net = gross - pos.fee_open - fee_close - funding
        back = max(0.0, pos.margin + gross - fee_close - funding)      # non si perde piu' del margine
        if why == "liquidazione":
            back = 0.0
        self.cash += back
        del self.positions[pos.symbol]
        rec = {"id": pos.id, "symbol": pos.symbol, "side": pos.side, "margin": pos.margin,
               "leverage": pos.leverage, "entry": pos.entry, "exit": exit_fill, "open_ms": pos.open_ms,
               "close_ms": now_ms, "net": round(net, 4), "gross": round(gross, 4),
               "fees": round(pos.fee_open + fee_close, 4), "funding": round(funding, 4),
               "why": why, "confidence": pos.confidence, "reason": pos.reason, "source": pos.source,
               "account": self.name}
        if why == "liquidazione":
            rec["net"] = round(-pos.margin - pos.fee_open, 4)
        self.closed.append(rec)
        return rec

    def close(self, symbol: str, price: float, now_ms: int, why: str = "chiusura decisa") -> Optional[dict]:
        pos = self.positions.get(symbol)
        return None if pos is None else self._close(pos, price, now_ms, why)

    def on_bar(self, symbol: str, t: int, o: float, h: float, l: float, c: float, bar_ms: int) -> Optional[dict]:
        """Applica una candela CHIUSA (apertura t). Prima lo stop (scelta prudente se nella stessa
        candela toccano sia stop sia obiettivo), poi l'obiettivo. Solo candele successive all'ingresso."""
        pos = self.positions.get(symbol)
        if pos is None or t < pos.open_ms:
            return None
        end = t + bar_ms
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
        return {"name": self.name, "cash": self.cash, "positions": {k: asdict(v) for k, v in self.positions.items()},
                "closed": self.closed, "next_id": self.next_id, "day": self.day,
                "day_start_equity": self.day_start_equity, "limits": asdict(self.limits)}

    @classmethod
    def from_dict(cls, d: dict) -> "PaperAccount":
        a = cls(Limits(**d["limits"]), d.get("name", "main"))
        a.cash, a.closed, a.next_id = d["cash"], d["closed"], d["next_id"]
        a.day, a.day_start_equity = d["day"], d["day_start_equity"]
        a.positions = {k: Position(**v) for k, v in d["positions"].items()}
        return a
