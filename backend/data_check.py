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
OTHER_EXCHANGES = ["okx", "gate"]
NOTICE_LINES: dict[str, list[str]] = {}


def day(ms) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


def short_err(e: Exception) -> str:
    return (type(e).__name__ + ": " + str(e).replace("\n", " "))[:90]


def make(name: str):
    cls = getattr(ccxt, name)
    return cls({"enableRateLimit": True, "timeout": 20000, "options": {"defaultType": "swap"}})


def probe(ex, symbol: str, tf: str, since_ms: int):
    """Prima candela restituita partendo da since_ms (None se vuoto/errore).
    Riprova sui 429. Un since precedente alla quotazione restituisce spesso
    vuoto, quindi 'ha dati' e' monotono in since (ipotesi della bisezione)."""
    for attempt in range(5):
        try:
            time.sleep(0.25)
            data = ex.fetch_ohlcv(symbol, tf, since=since_ms, limit=50)
            return data[0][0] if data else None
        except (ccxt.DDoSProtection, ccxt.RateLimitExceeded, ccxt.RequestTimeout):
            time.sleep(2 + attempt * 2)
        except Exception:  # noqa: BLE001
            return None
    return None


def first_candle(ex, symbol: str, tf: str) -> str:
    """Bisezione sul parametro since: trova la prima data da cui l'API restituisce
    candele (risoluzione ~1 giorno) e riporta la prima candela effettiva."""
    now = int(time.time() * 1000)
    lo = int(datetime(2018, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    hi = now - 2 * 86_400_000
    if probe(ex, symbol, tf, hi) is None:
        return "nessun dato recente"
    first = probe(ex, symbol, tf, lo)
    if first is None:
        while hi - lo > 86_400_000:
            mid = (lo + hi) // 2
            if probe(ex, symbol, tf, mid) is not None:
                hi = mid
            else:
                lo = mid
        first = probe(ex, symbol, tf, hi)
    if first is None:
        return "indeterminato"
    months = (now - first) / (30.44 * 86_400_000)
    return f"{day(first)} (~{months:.1f} mesi)"


def quality_1h(ex, symbol: str, days: int = 90) -> str:
    """Completezza e candele piatte (o=h=l=c) sulle ultime `days` giornate di 1h."""
    now = int(time.time() * 1000)
    cur = now - days * 86_400_000
    rows = []
    for _ in range(60):
        try:
            time.sleep(0.25)
            data = ex.fetch_ohlcv(symbol, "1h", since=cur, limit=200)
        except (ccxt.DDoSProtection, ccxt.RateLimitExceeded):
            time.sleep(3)
            continue
        except Exception as e:  # noqa: BLE001
            return f"errore {short_err(e)}"
        if not data:
            break
        rows.extend(data)
        nxt = data[-1][0] + 3_600_000
        if nxt <= cur or nxt >= now:
            break
        cur = nxt
    if not rows:
        return "nessun dato"
    uniq = {r[0]: r for r in rows}
    expected = (max(uniq) - min(uniq)) // 3_600_000 + 1
    flat_days = {}
    flat = 0
    for t, r in uniq.items():
        if r[1] == r[2] == r[3] == r[4]:
            flat += 1
            wd = datetime.fromtimestamp(t / 1000, timezone.utc).weekday()
            flat_days[wd] = flat_days.get(wd, 0) + 1
    wd_txt = ",".join(f"{'LMMGVSD'[k]}{v}" for k, v in sorted(flat_days.items()))
    return (f"{len(uniq)}/{expected} candele ({100 * len(uniq) / expected:.1f}%), "
            f"piatte={flat} [per giorno: {wd_txt or '-'}]")


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
        for tf in ("1d", "4h", "1h", "15m", "5m", "1m"):
            add(f"BitGet storia {sym[:3]}", f"{sym} {tf}: da {first_candle(bg, sym, tf)}")
        add("BitGet qualita 1h", f"{sym} ultimi 90g: {quality_1h(bg, sym)}")

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
            if sym.startswith(("BTC", "ETH")):
                continue  # gia' noto dal primo giro: qui interessano i metalli
            pieces = [f"{tf}: {first_candle(ex, sym, tf)}" for tf in ("1d", "1h", "15m")]
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
