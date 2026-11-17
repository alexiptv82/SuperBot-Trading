"""Universo comune dell'Arena: istantanea datata e verificabile (top crypto per capitalizzazione + oro/argento).

Regole (deterministiche, tutte registrate nell'istantanea):
1. classifica per capitalizzazione da una fonte pubblica (CoinGecko ``/coins/markets``) letta a ``as_of_ms``;
2. esclusioni ESPLICITE: stablecoin, asset tokenizzati (credito, oro tokenizzato: l'oro entra come XAU), token di
   exchange senza contratto; nessuna esclusione dedotta dal prezzo;
3. una crypto entra solo se esiste il perpetuo Bitget ``<SIMBOLO>USDT`` con stato ``normal``, il cui ultimo prezzo
   coincide (entro ``PRICE_TOLERANCE``) con quello della classifica (stesso ticker non basta: token omonimi), leva massima >= la leva
   minima del mandato e candele chiuse contigue sufficienti per la vista (15m/1h/4h) e recenti;
4. si prendono le prime ``crypto_target`` crypto idonee nell'ordine della classifica;
5. oro e argento (``XAUUSDT``, ``XAGUSDT``) entrano solo con le stesse verifiche; mai per supposizione.

Il risultato e' UNO solo per le tre AI. Nessun ordine, nessuna chiave: solo dati pubblici in lettura.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Callable, Iterable, Optional

SCHEMA = "arena_universe_snapshot_v1"
METALS = ("XAUUSDT", "XAGUSDT")
PRICE_TOLERANCE = Decimal("0.03")
# Esclusioni esplicite (simbolo CoinGecko in maiuscolo -> motivo). Aggiornabili solo con revisione.
EXCLUDED = {
    **{s: "stablecoin" for s in ("USDT", "USDC", "USDS", "USDE", "DAI", "USD1", "RLUSD", "USDG", "PYUSD", "FDUSD",
                                 "TUSD", "USDD", "USDY", "USYC", "BUIDL", "USDTB", "USD0", "GHO", "FRAX", "EURC",
                                 "EURSAFO", "SUSDE", "SUSDS", "USDF", "USDX", "BFUSD", "USTB", "OUSG")},
    **{s: "tokenized_asset" for s in ("FIGR_HELOC", "XAUT", "PAXG", "WBTC", "WETH", "STETH", "WSTETH", "WEETH",
                                      "CBBTC", "RETH", "METH", "LBTC", "SOLVBTC", "JITOSOL", "BSOL", "WBETH",
                                      "EZETH", "RSETH", "BNSOL", "CLBTC")},
}


def ranking_digest(ranking: list[dict]) -> str:
    slim = [{"id": r.get("id"), "symbol": r.get("symbol"), "market_cap": r.get("market_cap")} for r in ranking]
    return hashlib.sha256(json.dumps(slim, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _contract_ok(row: Optional[dict], min_leverage: int) -> Optional[str]:
    if row is None:
        return "no_bitget_usdt_perpetual"
    if row.get("symbolStatus") != "normal" or row.get("symbolType") != "perpetual":
        return "contract_not_normal"
    try:
        if Decimal(str(row.get("maxLever"))) < min_leverage:
            return "max_leverage_below_mandate"
    except ArithmeticError:
        return "contract_rules_invalid"
    return None


def _same_asset(coin: dict, ticker: Optional[dict]) -> Optional[str]:
    try:
        ref = Decimal(str(coin.get("current_price")))
        last = Decimal(str((ticker or {}).get("lastPr")))
    except ArithmeticError:
        return "identity_price_missing"
    if not ref.is_finite() or not last.is_finite() or ref <= 0 or last <= 0:
        return "identity_price_missing"
    return None if abs(last / ref - 1) <= PRICE_TOLERANCE else "identity_price_mismatch"


def build_snapshot(ranking: list[dict], contracts: Iterable[dict], probe: Callable[[str], dict], *,
                   tickers: Iterable[dict], as_of_ms: int, min_leverage: int, crypto_target: int = 25,
                   metals: tuple[str, ...] = METALS, ranking_source: str = "coingecko_coins_markets_usd") -> dict:
    """``probe(symbol)`` -> ``{"ok": bool, "code": str, ...}`` sulle candele chiuse (iniettabile nei test)."""
    if type(ranking) is not list or not ranking or type(as_of_ms) is not int or as_of_ms <= 0:
        raise ValueError("universe_invalid_input")
    table = {r.get("symbol"): r for r in contracts if type(r) is dict}
    prices = {r.get("symbol"): r for r in tickers if type(r) is dict}
    included, excluded, evidence = [], [], {}
    seen = set()
    for rank, coin in enumerate(ranking, start=1):
        if len(included) >= crypto_target:
            break
        sym = str(coin.get("symbol", "")).upper()
        entry = {"rank": rank, "coingecko_id": coin.get("id"), "symbol": sym}
        if sym in seen:
            excluded.append({**entry, "reason": "duplicate_symbol"})
            continue
        seen.add(sym)
        if sym in EXCLUDED:
            excluded.append({**entry, "reason": EXCLUDED[sym]})
            continue
        pair = sym + "USDT"
        code = _contract_ok(table.get(pair), min_leverage) or _same_asset(coin, prices.get(pair))
        if code is None:
            p = probe(pair)
            evidence[pair] = p
            code = None if p.get("ok") is True else ("feed_" + str(p.get("code", "failed")))
        if code is not None:
            excluded.append({**entry, "pair": pair, "reason": code})
            continue
        included.append({**entry, "pair": pair, "reference_price": str(coin.get("current_price")),
                         "bitget_last_price": str(prices[pair].get("lastPr"))})
    metal_rows = []
    for pair in metals:
        code = _contract_ok(table.get(pair), min_leverage)
        if code is None:
            p = probe(pair)
            evidence[pair] = p
            code = None if p.get("ok") is True else ("feed_" + str(p.get("code", "failed")))
        metal_rows.append({"pair": pair, "included": code is None, "reason": code})
    symbols = [c["pair"] for c in included] + [m["pair"] for m in metal_rows if m["included"]]
    return {
        "schema": SCHEMA,
        "as_of_ms": as_of_ms,
        "ranking_source": ranking_source,
        "ranking_sha256": ranking_digest(ranking),
        "ranking_size": len(ranking),
        "crypto_target": crypto_target,
        "crypto_included": included,
        "crypto_target_met": len(included) == crypto_target,
        "excluded_before_target": excluded,
        "metals": metal_rows,
        "symbols": symbols,
        "symbols_sha256": hashlib.sha256(",".join(symbols).encode()).hexdigest(),
        "min_leverage_checked": min_leverage,
        "identity_price_tolerance": str(PRICE_TOLERANCE),
        "feed_evidence": evidence,
        "same_for_all_providers": True,
        "note": "Istantanea point-in-time; non si aggiorna da sola durante la prova di 14 giorni.",
    }


def candle_probe(get_json, *, now_ms: int, requirements: dict, fresh_candles: int = 2) -> Callable[[str], dict]:
    """Verifica reale sul feed: per ogni timeframe ``{nome: (candle_ms, barre_minime)}`` servono barre chiuse contigue
    sufficienti e l'ultima barra non piu' vecchia di ``fresh_candles`` candele."""
    from backend.v3.runner.feed import contiguous_tail, fetch_closed_bars

    def probe(symbol: str) -> dict:
        out = {"ok": True, "code": "ok", "timeframes": {}}
        for name, (ms, need) in requirements.items():
            end = now_ms // ms * ms
            try:
                bars = fetch_closed_bars(symbol, end - (need + 24) * ms, end, candle_ms=ms, get_json=get_json)
            except Exception:                                    # rete o risposta non valida: escluso, non presunto
                return {"ok": False, "code": "fetch_failed", "timeframe": name}
            tail = contiguous_tail(bars, ms)
            zero = sum(1 for b in tail if b.volume == 0)
            info = {"bars": len(bars), "contiguous": len(tail), "required": need,
                    "zero_volume_share": round(zero / len(tail), 4) if tail else None}
            out["timeframes"][name] = info
            if len(tail) < need:
                return {**out, "ok": False, "code": "history_gap_or_short", "timeframe": name}
            if end - tail[-1].open_time_ms > (fresh_candles + 1) * ms:
                return {**out, "ok": False, "code": "stale", "timeframe": name}
        return out
    return probe
