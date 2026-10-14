"""Sonda di sola lettura: dove si trova uno storico lungo del funding?

Controlla (endpoint pubblici, nessuna chiave): archivio pubblico di Binance
(data.binance.vision), API Binance, OKX e Gate via ccxt. Stampa una riga per prova.
"""
from __future__ import annotations

import io
import time
import urllib.request
import zipfile
from datetime import datetime, timezone

LINES: list = []


def add(text: str) -> None:
    print(text, flush=True)
    LINES.append(text[:230])


def http(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "code", None)
        return code, str(e)[:80]


def probe_vision() -> None:
    base = "https://data.binance.vision/data/futures/um/monthly/fundingRate"
    for sym, ym in (("BTCUSDT", "2020-01"), ("BTCUSDT", "2022-06"), ("ETHUSDT", "2021-03"),
                    ("ADAUSDT", "2021-01"), ("DOGEUSDT", "2021-05"), ("SOLUSDT", "2021-01")):
        status, body = http(f"{base}/{sym}/{sym}-fundingRate-{ym}.zip")
        if status == 200 and isinstance(body, bytes):
            try:
                z = zipfile.ZipFile(io.BytesIO(body))
                text = z.read(z.namelist()[0]).decode().splitlines()
                add(f"vision {sym} {ym}: OK, {len(text) - 1} righe, intestazione='{text[0]}', prima='{text[1]}'")
            except Exception as e:  # noqa: BLE001
                add(f"vision {sym} {ym}: scaricato ma non leggibile ({str(e)[:60]})")
        else:
            add(f"vision {sym} {ym}: stato={status} {body if not isinstance(body, bytes) else ''}")
        time.sleep(0.3)
    status, body = http("https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=3")
    add(f"fapi.binance.com fundingRate: stato={status} {body[:60] if not isinstance(body, bytes) else 'OK'}")


def probe_ccxt() -> None:
    import ccxt
    for name in ("okx", "gate", "bybit", "kucoinfutures", "krakenfutures", "hyperliquid"):
        try:
            ex = getattr(ccxt, name)({"enableRateLimit": True, "options": {"defaultType": "swap"}, "timeout": 20000})
            ex.load_markets()
        except Exception as e:  # noqa: BLE001
            add(f"{name}: non raggiungibile ({type(e).__name__} {str(e)[:50]})")
            continue
        sym = "BTC/USDT:USDT" if "BTC/USDT:USDT" in ex.markets else next(
            (s for s in ex.markets if s.startswith("BTC/") and ex.markets[s].get("swap")), None)
        if not sym:
            add(f"{name}: nessun perpetual BTC trovato")
            continue
        for since_year in (2019, 2021, 2024):
            since = int(datetime(since_year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
            try:
                h = ex.fetch_funding_rate_history(sym, since=since, limit=100)
                if h:
                    add(f"{name} {sym} since {since_year}: {len(h)} record, primo {datetime.fromtimestamp(h[0]['timestamp'] / 1000, timezone.utc):%Y-%m-%d}")
                else:
                    add(f"{name} {sym} since {since_year}: vuoto")
            except Exception as e:  # noqa: BLE001
                add(f"{name} {sym} since {since_year}: errore {type(e).__name__} {str(e)[:50]}")
            time.sleep(0.3)


def main() -> None:
    probe_vision()
    probe_ccxt()
    for i in range(0, len(LINES), 14):
        msg = "%0A".join(x.replace("%", "%25") for x in LINES[i:i + 14])
        print(f"::notice title=Sonda funding ({i // 14 + 1})::{msg}")


if __name__ == "__main__":
    main()
