"""Sonda di SOLA LETTURA: come risponde BitGet alle richieste di candele 15m a varie distanze nel passato?

Serve a capire perche' lo scarico dello storico si ferma (pagina vuota) e come paginare in modo completo.
Dati pubblici, nessuna chiave.
"""
from __future__ import annotations

import inspect
import time

import ccxt

M15 = 900_000
DAY = 86_400_000
LINES: list = []


def add(text: str) -> None:
    print(text, flush=True)
    LINES.append(text[:230])


def fmt(ms) -> str:
    return time.strftime("%m-%d %H:%M", time.gmtime(ms / 1000))


def main() -> None:
    ex = ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    add(f"ccxt {ccxt.__version__}")
    src = inspect.getsource(ex.fetch_ohlcv).splitlines()
    keep = [ln.strip() for ln in src if any(k in ln for k in
            ("history", "threshold", "Threshold", "endTime", "startTime", "maxLimit", "limit", "now", "until", "method", "Method"))]
    for ln in keep[:34]:
        add("src| " + ln[:200])
    now = int(time.time() * 1000)
    sym = "BTC/USDT:USDT"
    for d in (51, 49, 45, 40, 36, 33, 31, 30):
        since = now - int(d * DAY)
        for label, kw in (("until", {"until": since + 200 * M15}), ("lim1000", {}), ("until+lim1000", {"until": since + 1000 * M15})):
            lim = 1000 if "1000" in label else 200
            try:
                rows = ex.fetch_ohlcv(sym, "15m", since=since, limit=lim, params=kw)
                add(f"-{d}g {label}: " + (f"{len(rows)} righe {fmt(rows[0][0])} -> {fmt(rows[-1][0])}" if rows else "VUOTO"))
            except Exception as exc:  # noqa: BLE001
                add(f"-{d}g {label}: errore {type(exc).__name__} {str(exc)[:70]}")
            time.sleep(0.2)
    for i in range(0, len(LINES), 14):
        msg = "%0A".join(x.replace("%", "%25") for x in LINES[i:i + 14])
        print(f"::notice title=Sonda candele ({i // 14 + 1})::{msg}")


if __name__ == "__main__":
    main()
