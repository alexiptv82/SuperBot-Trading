"""Controllo di sola lettura sui dati pubblici disponibili per i nuovi test.

Risponde a: quanta storia c'e' davvero (per timeframe) su BitGet per BTC, ETH,
oro e argento? Su quali altre borse pubbliche esiste una storia piu' lunga di
BTC/ETH? Com'e' il funding (intervallo, tasso medio)? Quali commissioni
standard riporta ccxt per i mercati BitGet?

Usa solo endpoint pubblici (nessuna chiave, nessun ordine). Ogni chiamata e'
protetta da try/except: un errore diventa una riga del report, mai un crash.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timedelta, timezone

import ccxt

BITGET_SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "XAU/USDT:USDT", "XAG/USDT:USDT"]
LADDER_YEARS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
OTHER_EXCHANGES = ["binanceusdm", "bybit", "okx", "gate", "kucoinfutures"]
NOTICE_LINES: dict[str, list[str]] = {}


def day(ms) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def short_err(e: Exception) -> str:
    return (type(e).__name__ + ": " + str(e).replace("\n", " "))[:90]


def make(name: str):
    cls = getattr(ccxt, name)
    return cls({"enableRateLimit": True, "timeout": 20000, "options": {"defaultType": "swap"}})


def first_candle(ex, symbol: str, tf: str) -> str:
    """Prima candela restituita partendo dagli anni piu' vecchi: la prima scala
    che restituisce dati indica da quando la storia esiste (approssimato)."""
    last_err = ""
    for year in LADDER_YEARS:
        since = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        try:
            data = ex.fetch_ohlcv(symbol, tf, since=since, limit=50)
        except Exception as e:  # noqa: BLE001
            last_err = short_err(e)
            continue
        if data:
            return f"{day(data[0][0])} (richiesta da {year})"
    return f"nessun dato ({last_err})" if last_err else "nessun dato"


def depth_1m(ex, symbol: str) -> str:
    """Quanti giorni indietro risponde il timeframe 1m (profondita' massima)."""
    out = []
    for days in (30, 90, 180, 365, 730):
        since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
        try:
            data = ex.fetch_ohlcv(symbol, "1m", since=since, limit=5)
            ok = bool(data) and data[0][0] - since < 3 * 86_400_000
            out.append(f"{days}g:{'si' if ok else 'no'}")
        except Exception as e:  # noqa: BLE001
            out.append(f"{days}g:err({short_err(e)[:30]})")
    return " ".join(out)


def funding_info(ex, symbol: str) -> str:
    parts = []
    try:
        fr = ex.fetch_funding_rate(symbol)
        interval = fr.get("interval")
        parts.append(f"intervallo dichiarato={interval}")
        if fr.get("fundingRate") is not None:
            parts.append(f"tasso attuale={fr['fundingRate'] * 1e4:+.2f}bp")
    except Exception as e:  # noqa: BLE001
        parts.append(f"fetch_funding_rate: {short_err(e)}")
    try:
        hist = ex.fetch_funding_rate_history(symbol, limit=200)
        stamps = [h["timestamp"] for h in hist if h.get("timestamp")]
        rates = [h["fundingRate"] for h in hist if h.get("fundingRate") is not None]
        if len(stamps) > 2:
            gaps = [(b - a) / 3_600_000 for a, b in zip(stamps, stamps[1:])]
            parts.append(f"intervallo reale mediano={statistics.median(gaps):.1f}h")
        if rates:
            parts.append(f"n={len(rates)} medio={statistics.mean(rates) * 1e4:+.2f}bp "
                         f"medio_assoluto={statistics.mean(abs(r) for r in rates) * 1e4:.2f}bp "
                         f"max={max(rates) * 1e4:+.1f}bp min={min(rates) * 1e4:+.1f}bp")
    except Exception as e:  # noqa: BLE001
        parts.append(f"storico funding: {short_err(e)}")
    return " | ".join(parts)


def add(title: str, line: str) -> None:
    print(line, flush=True)
    NOTICE_LINES.setdefault(title, []).append(line[:230])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--annotate", action="store_true")
    ap.add_argument("--out", default="data_check_results.json")
    args = ap.parse_args()
    t0 = time.time()

    # 1) BitGet: storia per timeframe, fee standard, funding
    bg = make("bitget")
    try:
        bg.load_markets()
    except Exception as e:  # noqa: BLE001
        add("BitGet", f"load_markets fallito: {short_err(e)}")
    for sym in BITGET_SYMBOLS:
        m = bg.markets.get(sym) if bg.markets else None
        if not m:
            add("BitGet mercati", f"{sym}: mercato non trovato")
            continue
        add("BitGet mercati", f"{sym}: maker={m.get('maker')} taker={m.get('taker')} "
                              f"contractSize={m.get('contractSize')} attivo={m.get('active')}")
        for tf in ("1d", "4h", "1h", "15m"):
            add("BitGet storia", f"{sym} {tf}: prima candela {first_candle(bg, sym, tf)}")
        if sym in ("BTC/USDT:USDT", "XAU/USDT:USDT"):
            add("BitGet storia 1m", f"{sym} 1m profondita': {depth_1m(bg, sym)}")
        add("BitGet funding", f"{sym}: {funding_info(bg, sym)}")

    # 2) Altre borse pubbliche: storia lunga per BTC/ETH e presenza dei metalli
    for name in OTHER_EXCHANGES:
        if time.time() - t0 > 14 * 60:
            add("Altre borse", f"{name}: saltata (tempo)")
            continue
        try:
            ex = make(name)
            ex.load_markets()
        except Exception as e:  # noqa: BLE001
            add("Altre borse", f"{name}: non raggiungibile ({short_err(e)})")
            continue
        for sym in BITGET_SYMBOLS:
            if sym not in ex.markets:
                if sym.startswith(("XAU", "XAG")):
                    add("Altre borse", f"{name} {sym}: non presente")
                continue
            pieces = [f"{tf}: {first_candle(ex, sym, tf)}" for tf in ("1d", "1h")]
            add("Altre borse", f"{name} {sym} -> " + " | ".join(pieces))

    add("Esito", f"durata {time.time() - t0:.0f}s")
    with open(args.out, "w") as f:
        json.dump(NOTICE_LINES, f, indent=1)
    if args.annotate:
        for title, lines in NOTICE_LINES.items():
            for i in range(0, len(lines), 14):
                msg = "%0A".join(l.replace("%", "%25") for l in lines[i:i + 14])
                suffix = f" ({i // 14 + 1})" if len(lines) > 14 else ""
                print(f"::notice title=Dati - {title}{suffix}::{msg}")


if __name__ == "__main__":
    main()
