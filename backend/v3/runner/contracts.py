"""Regole dei contratti futures USDT-M di Bitget per il risk gate: passo della quantita', notional minimo, leva massima.

Fonte: ``GET /api/v2/mix/market/contracts?productType=USDT-FUTURES`` (dato pubblico, sola lettura).
**Nomi dei campi presi dalla documentazione Bitget e NON verificati da questa macchina (Bitget non e'
raggiungibile da qui)**: il parser e' rigido e fail-closed (un campo mancante o strano toglie quel simbolo,
non lo riempie con un valore di comodo) e la prima prova sulla VPS dira' se i nomi sono giusti.

* ``quantity_step`` = ``sizeMultiplier``; ``minimum_notional`` = ``minTradeUSDT``; ``exchange_leverage_limit``
  = ``maxLever``; solo ``symbolStatus == "normal"``. ``minTradeNum`` (quantita' minima) non e' usata: per i
  contratti normali coincide con il passo.
* ``maintenance_fraction`` NON viene dall'exchange (qui non c'e' la tabella dei livelli): e' un valore di
  configurazione prudente, deciso dall'utente.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable, Mapping, Optional

from backend.v3.lab_tools.fetch_candles import BASE, http_json

CONTRACTS_URL = f"{BASE}/api/v2/mix/market/contracts?productType=USDT-FUTURES"
GetJson = Callable[[str], object]


def _dec(value) -> Optional[Decimal]:
    if type(value) is not str:
        return None
    try:
        d = Decimal(value)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def parse_contract_rules(payload: object, *, maintenance_fraction: Decimal) -> dict[str, dict]:
    """Risposta di Bitget -> ``{simbolo: regole}``. Solleva ``ValueError("invalid_contracts")`` se la risposta
    non e' nel formato atteso; i singoli contratti malformati o non ``normal`` vengono scartati."""
    if (type(maintenance_fraction) is not Decimal or not maintenance_fraction.is_finite()
            or not Decimal("0") <= maintenance_fraction < Decimal("1")):
        raise ValueError("invalid_maintenance_fraction")
    if not isinstance(payload, dict) or payload.get("code") != "00000" or type(payload.get("data")) is not list:
        raise ValueError("invalid_contracts")
    out: dict[str, dict] = {}
    for item in payload["data"]:
        if not isinstance(item, dict) or item.get("symbolStatus") != "normal":
            continue
        symbol = item.get("symbol")
        step, notional, lever = _dec(item.get("sizeMultiplier")), _dec(item.get("minTradeUSDT")), _dec(item.get("maxLever"))
        if (type(symbol) is not str or not symbol or step is None or step <= 0 or notional is None or notional < 0
                or lever is None or lever != lever.to_integral_value() or not 1 <= lever <= 125 or symbol in out):
            continue
        out[symbol] = {"exchange_leverage_limit": int(lever), "quantity_step": step,
                       "minimum_notional": notional, "maintenance_fraction": maintenance_fraction}
    if not out:
        raise ValueError("invalid_contracts")
    return out


class ContractRules:
    """Tabella delle regole, ricaricata al massimo ogni ``refresh_ms``. Se la rete fallisce tiene l'ultima tabella
    buona (se non ce n'e' nessuna, ``__call__`` restituisce ``None`` e il ciclo salta il simbolo)."""

    def __init__(self, get_json: GetJson = http_json, *, maintenance_fraction: Decimal,
                 refresh_ms: int = 6 * 3_600_000):
        if type(refresh_ms) is not int or refresh_ms < 60_000:
            raise ValueError("invalid_refresh")
        parse_contract_rules({"code": "00000", "data": [{"symbolStatus": "normal", "symbol": "X", "sizeMultiplier": "1",
                                                          "minTradeUSDT": "5", "maxLever": "10"}]},
                             maintenance_fraction=maintenance_fraction)       # valida la frazione subito
        self._get, self._maint, self._every = get_json, maintenance_fraction, refresh_ms
        self._table: dict[str, dict] = {}
        self._loaded_at: Optional[int] = None

    def load(self, now_ms: int) -> bool:
        """Ricarica se e' dovuto; ``True`` se la tabella e' aggiornata, ``False`` se si usa quella vecchia/vuota."""
        if type(now_ms) is not int or now_ms <= 0:
            raise ValueError("invalid_now")
        if self._loaded_at is not None and now_ms - self._loaded_at < self._every:
            return True
        try:
            self._table = parse_contract_rules(self._get(CONTRACTS_URL), maintenance_fraction=self._maint)
        except Exception:
            return False
        self._loaded_at = now_ms
        return True

    def __call__(self, symbol: str) -> Optional[Mapping]:
        rules = self._table.get(symbol)
        return dict(rules) if rules is not None else None
