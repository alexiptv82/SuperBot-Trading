"""Exchange Bitget FINTO per i test del connettore live.

Non e' un mock "che dice sempre di si": le richieste ordine vengono costruite dal VERO ccxt (la stessa
versione del bot, 4.2.95) con `create_order_request`, cioe' quello che davvero partirebbe verso Bitget.
Il finto exchange le legge come le leggerebbe Bitget (margine, one-way / hedge, tradeSide, reduceOnly,
stop preset, piani stop/take profit) e rifiuta cio' che Bitget rifiuterebbe. Cosi' un errore nei
parametri (es. due trigger insieme, margine non isolato, lato sbagliato in hedge) fa fallire il test.

Si possono simulare i guasti: errori in una chiamata, ordine eseguito ma risposta in timeout, exchange
che ignora il margine isolato o la leva, lettura posizioni che fallisce, ecc.
"""
import os
import sys

try:
    import ccxt
except ImportError:                       # in locale ccxt puo' non essere installato: sorgente clonato
    sys.path.insert(0, "/home/claude/ccxt/ccxt/python")
    import ccxt

ONE_WAY, HEDGE = "one_way_mode", "hedge_mode"


def make_market(base: str, step: float = 0.0001, min_cost: float = 5.0) -> dict:
    return {
        "id": f"{base}USDT", "symbol": f"{base}/USDT:USDT", "base": base, "quote": "USDT", "settle": "USDT",
        "baseId": base, "quoteId": "USDT", "settleId": "USDT", "type": "swap", "spot": False,
        "margin": False, "swap": True, "future": False, "option": False, "active": True, "contract": True,
        "linear": True, "inverse": False, "contractSize": 1.0,
        "precision": {"amount": step, "price": 0.1},
        "limits": {"amount": {"min": step, "max": None}, "cost": {"min": min_cost, "max": None},
                   "leverage": {"min": 1, "max": 125}, "price": {"min": None, "max": None}},
        "info": {},
    }


class FakeBitget:
    def __init__(self, pos_mode: str = ONE_WAY, symbols=None, prices=None):
        self.ex = ccxt.bitget({"apiKey": "k", "secret": "s", "password": "p",
                               "options": {"defaultType": "swap"}})
        symbols = symbols or {"BTC": 0.0001, "ETH": 0.001, "DOGE": 1.0}
        self.ex.set_markets([make_market(b, st) for b, st in symbols.items()])
        self.pos_mode = pos_mode
        self.reported_pos_mode = pos_mode        # None = Bitget non dice la modalita'
        self.prices = prices or {"BTC/USDT:USDT": 60000.0, "ETH/USDT:USDT": 3000.0, "DOGE/USDT:USDT": 0.1}
        self.margin: dict = {}                   # simbolo ccxt -> 'crossed' | 'isolated' (default crossed)
        self.lev: dict = {}                      # simbolo ccxt -> {1: lev_long, -1: lev_short}
        self.legs: dict = {}                     # (simbolo ccxt, lato) -> {qty, entry, margin_mode, leverage}
        self.orders: list = []                   # richieste vere costruite da ccxt
        self.plans: list = []                    # piani stop/take profit sull'exchange
        self.calls: list = []
        self.errors: dict = {}                   # nome -> [eccezioni da sollevare, una per chiamata]
        self.sticky: dict = {}                   # nome -> eccezione sollevata SEMPRE
        self.ignore_margin_mode = False          # set_margin_mode non fa nulla
        self.ignore_leverage = False             # set_leverage non fa nulla
        self.force_order_margin = None           # l'exchange apre in questo margine, qualunque cosa si chieda
        self.fill_after_error = False            # ordine eseguito anche se la risposta e' un errore
        self.partial_close = 1.0                 # frazione davvero chiusa da un ordine di chiusura
        self._id = 1000
        self._oids: set = set()
        self.fills: dict = {}

    # ---- strumenti di test -------------------------------------------------
    def names(self):
        return [c for c in self.calls]

    def count(self, name: str) -> int:
        return sum(1 for c in self.calls if c == name)

    def leg(self, base: str, side: int):
        return self.legs.get((f"{base}/USDT:USDT", side))

    def put_position(self, base: str, side: int, qty: float, entry: float = 60000.0, margin_mode="isolated",
                     leverage=10):
        sym = f"{base}/USDT:USDT"
        self.legs[(sym, side)] = {"qty": qty, "entry": entry, "margin_mode": margin_mode, "leverage": leverage}
        self.margin[sym] = "isolated" if margin_mode == "isolated" else "crossed"   # il simbolo e' in quel margine

    def _enter(self, name: str):
        self.calls.append(name)
        if name in self.sticky:
            raise self.sticky[name]
        q = self.errors.get(name)
        if q:
            raise q.pop(0)

    # ---- API ccxt usate dal connettore -------------------------------------
    @property
    def markets(self):
        return self.ex.markets

    def load_markets(self):
        return self.ex.markets

    def fetch_balance(self, params=None):
        self._enter("fetch_balance")
        return {"USDT": {"free": 100.0, "used": 0.0, "total": 100.0}}

    def fetch_ticker(self, symbol, params=None):
        self._enter("fetch_ticker")
        return {"symbol": symbol, "last": self.prices[symbol]}

    def market(self, symbol):
        return self.ex.market(symbol)

    def amount_to_precision(self, symbol, amount):
        return self.ex.amount_to_precision(symbol, amount)

    def fetch_positions(self, symbols=None, params=None):
        self._enter("fetch_positions")
        out = []
        for (sym, side), leg in self.legs.items():
            out.append({
                "symbol": sym, "contracts": leg["qty"], "side": "long" if side == 1 else "short",
                "entryPrice": leg["entry"], "markPrice": self.prices.get(sym, leg["entry"]),
                "liquidationPrice": 1.0, "leverage": leg["leverage"],
                "marginMode": "isolated" if leg["margin_mode"] == "isolated" else "cross",
                "info": {"posMode": self.reported_pos_mode, "marginMode": leg["margin_mode"],
                         "holdSide": "long" if side == 1 else "short", "total": str(leg["qty"])},
            })
        return out

    def fetch_leverage(self, symbol, params=None):
        self._enter("fetch_leverage")
        lev = self.lev.get(symbol, {1: 20, -1: 20})
        info = {"marginMode": self.margin.get(symbol, "crossed"),
                "isolatedLongLever": lev[1], "isolatedShortLever": lev[-1]}
        if self.reported_pos_mode is not None:
            info["posMode"] = self.reported_pos_mode
        return {"info": info, "symbol": symbol}

    def set_margin_mode(self, margin_mode, symbol=None, params=None):
        self._enter("set_margin_mode")
        if any(s == symbol for (s, _) in self.legs):
            raise ccxt.ExchangeError("bitget: impossibile cambiare il margine con posizioni aperte")
        if not self.ignore_margin_mode:
            self.margin[symbol] = "isolated" if margin_mode == "isolated" else "crossed"
        return {}

    def set_leverage(self, leverage, symbol=None, params=None):
        self._enter("set_leverage")
        params = params or {}
        if self.ignore_leverage:
            return {}
        cur = self.lev.setdefault(symbol, {1: 20, -1: 20})
        hold = params.get("holdSide")
        if hold == "long":
            cur[1] = leverage
        elif hold == "short":
            cur[-1] = leverage
        else:
            cur[1] = cur[-1] = leverage
        return {}

    def fetch_order(self, order_id, symbol=None, params=None):
        self._enter("fetch_order")
        f = self.fills.get(order_id)
        if not f:
            raise ccxt.OrderNotFound("ordine non trovato")
        return {"id": order_id, "average": f["price"], "filled": f["qty"], "status": "closed",
                "fee": {"cost": f["fee"], "currency": "USDT"}}

    def fetch_open_orders(self, symbol=None, since=None, limit=None, params=None):
        self._enter("fetch_open_orders")
        return [{"id": p["id"], "triggerPrice": p["triggerPrice"],
                 "info": {"planType": p["planType"], "holdSide": p["holdSide"]}}
                for p in self.plans if p["symbol"] == symbol]

    def cancel_order(self, order_id, symbol=None, params=None):
        self._enter("cancel_order")
        before = len(self.plans)
        self.plans = [p for p in self.plans if p["id"] != order_id]
        if len(self.plans) == before:
            raise ccxt.OrderNotFound("piano non trovato")
        return {"id": order_id}

    def create_order(self, symbol, type, side, amount, price=None, params=None):
        self.calls.append("create_order")
        params = dict(params or {})
        req = self.ex.create_order_request(symbol, type, side, amount, price, params)   # VERO ccxt
        self.orders.append(req)
        err = None
        if "create_order" in self.sticky:
            err = self.sticky["create_order"]
        elif self.errors.get("create_order"):
            err = self.errors["create_order"].pop(0)
        if err is not None and not self.fill_after_error:
            raise err
        oid = req.get("clientOid")
        if oid:
            if oid in self._oids:
                raise ccxt.ExchangeError("bitget: Duplicate clientOid")
            self._oids.add(oid)
        order_id = self._apply(symbol, req)
        if err is not None:
            raise err
        return {"id": order_id, "info": req}

    # ---- come Bitget interpreta la richiesta --------------------------------
    def _new_id(self) -> str:
        self._id += 1
        return str(self._id)

    def _apply(self, sym: str, req: dict) -> str:
        size = float(req["size"])
        oid = self._new_id()
        if "planType" in req:                                       # stop / take profit a posizione
            hold = req["holdSide"]
            allowed = ("buy", "sell") if self.pos_mode == ONE_WAY else ("long", "short")
            if hold not in allowed:
                raise ccxt.ExchangeError(f"bitget: holdSide {hold!r} non valido in {self.pos_mode}")
            side = 1 if hold in ("buy", "long") else -1
            if (sym, side) not in self.legs:
                raise ccxt.ExchangeError("bitget: nessuna posizione a cui agganciare il piano")
            self.plans.append({"id": oid, "symbol": sym, "planType": req["planType"], "holdSide": hold,
                               "triggerPrice": float(req["triggerPrice"]), "side": side})
            return oid
        if req.get("marginMode") not in ("isolated", "crossed"):
            raise ccxt.ExchangeError("bitget: marginMode mancante")
        if req["marginMode"] != self.margin.get(sym, "crossed"):
            raise ccxt.ExchangeError("bitget: il margine dell'ordine non coincide con quello del simbolo")
        px = self.prices[sym]
        bside = 1 if req["side"] == "buy" else -1
        if self.pos_mode == ONE_WAY:
            if "tradeSide" in req:
                raise ccxt.ExchangeError("bitget: tradeSide non ammesso in one-way")
            reduce = req.get("reduceOnly") == "YES"
            cur = next(((k, v) for k, v in self.legs.items() if k[0] == sym), None)
            if reduce:
                if not cur or cur[0][1] == bside:
                    raise ccxt.ExchangeError("bitget: reduceOnly senza posizione da ridurre")
                self._reduce(cur[0], size)
            else:
                if cur and cur[0][1] != bside:
                    self._reduce(cur[0], size)          # in one-way l'ordine opposto riduce / gira la posizione
                else:
                    self._open(sym, bside, size, px, req)
        else:
            ts = req.get("tradeSide")
            if ts not in ("Open", "Close"):
                raise ccxt.ExchangeError("bitget: tradeSide obbligatorio in hedge")
            if ts == "Open":
                self._open(sym, bside, size, px, req)
            else:                                        # in hedge 'side' e' la direzione della posizione
                if (sym, bside) not in self.legs:
                    raise ccxt.ExchangeError("bitget: nessuna posizione da chiudere su questo lato")
                self._reduce((sym, bside), size)
        self.fills[oid] = {"price": px, "qty": size, "fee": round(size * px * 0.0006, 6)}
        return oid

    def _open(self, sym, side, size, px, req):
        mm = self.force_order_margin or ("isolated" if req["marginMode"] == "isolated" else "crossed")
        if self.force_order_margin:
            self.margin[sym] = self.force_order_margin       # il simbolo e' DAVVERO in quel margine
        leg = self.legs.get((sym, side))
        lev = self.lev.get(sym, {1: 20, -1: 20})[side]
        if leg:
            tot = leg["qty"] + size
            leg["entry"] = (leg["entry"] * leg["qty"] + px * size) / tot
            leg["qty"] = tot
        else:
            self.legs[(sym, side)] = {"qty": size, "entry": px, "margin_mode": mm, "leverage": lev}
        if "presetStopLossPrice" in req:
            self.plans.append({"id": self._new_id(), "symbol": sym, "planType": "loss_plan",
                               "holdSide": "long" if side == 1 else "short",
                               "triggerPrice": float(req["presetStopLossPrice"]), "side": side})
        if "presetStopSurplusPrice" in req:
            self.plans.append({"id": self._new_id(), "symbol": sym, "planType": "profit_plan",
                               "holdSide": "long" if side == 1 else "short",
                               "triggerPrice": float(req["presetStopSurplusPrice"]), "side": side})

    def _reduce(self, key, size):
        leg = self.legs[key]
        q = min(size * self.partial_close, leg["qty"])
        leg["qty"] = round(leg["qty"] - q, 12)
        if leg["qty"] <= 1e-12:
            del self.legs[key]
            self.plans = [p for p in self.plans if not (p["symbol"] == key[0] and p["side"] == key[1])]
