"""Candele chiuse dal feed pubblico Bitget, con cache incrementale (sola lettura).

* Nessuna chiave, nessun ordine, nessuna scrittura: solo ``GET`` di dati pubblici tramite
  ``lab_tools.fetch_candles.fetch_rows`` (gia' provata: scarta righe incoerenti e la barra in formazione).
* ``get_json`` e' iniettabile: i test non toccano la rete; da questa macchina Bitget non e' raggiungibile.
* ``CandleStore`` tiene per (simbolo, timeframe) le ultime ``keep`` barre e a ogni giro scarica solo quelle
  nuove. Se la cache ha un buco la ricarica da zero. ``bars`` restituisce SEMPRE una serie contigua (la coda
  contigua piu' recente): la vista di mercato rifiuta le serie con buchi, quindi un buco dentro la storia
  non deve bloccare per sempre un simbolo.
* Un errore di rete solleva: chi chiama decide (il runner registra l'errore e lascia che la vista segnali
  ``stale``). I prezzi restano stringhe fino a ``Decimal``: nessun ``float``.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable, Optional

from backend.v3.features.indicators import Bar
from backend.v3.lab_tools.fetch_candles import fetch_rows, http_json

GetJson = Callable[[str], object]


def rows_to_bars(rows: dict) -> list[Bar]:
    """``{apertura_ms: (o, h, l, c, v)}`` (stringhe) -> ``Bar`` in ordine di tempo."""
    return [Bar(ts, *(Decimal(x) for x in rows[ts])) for ts in sorted(rows)]


def contiguous_tail(bars: list[Bar], candle_ms: int) -> list[Bar]:
    """La coda piu' recente senza buchi (una serie vuota resta vuota)."""
    start = len(bars)
    while start > 0 and (start == len(bars) or bars[start].open_time_ms - bars[start - 1].open_time_ms == candle_ms):
        start -= 1
    return bars[start:]


def contiguous_runs(bars: list[Bar], candle_ms: int) -> list[list[Bar]]:
    """Spezza in tratti contigui, in ordine di tempo (per non perdere informazione se manca una barra)."""
    runs: list[list[Bar]] = []
    for b in bars:
        if runs and b.open_time_ms - runs[-1][-1].open_time_ms == candle_ms:
            runs[-1].append(b)
        else:
            runs.append([b])
    return runs


def fetch_closed_bars(symbol: str, start_ms: int, end_ms: int, *, candle_ms: int,
                      get_json: GetJson = http_json) -> list[Bar]:
    """Barre chiuse con ``start_ms <= apertura < end_ms``; ``end_ms`` va allineato alla griglia del timeframe."""
    return rows_to_bars(fetch_rows(symbol, start_ms, end_ms, candle_ms=candle_ms, get_json=get_json))


class CandleStore:
    """Cache incrementale delle ultime ``keep`` candele chiuse per simbolo e timeframe.

    La cache conserva anche i buchi (``bars`` restituisce la coda contigua). Un buco nella storia viene
    riprovato con un ricaricamento completo al massimo una volta ogni ``reload_gap_ms`` (di default 1 ora):
    se la mancanza e' dell'exchange resta e il simbolo lavora sulla coda contigua, se era passeggera si ripara.
    """

    def __init__(self, get_json: GetJson = http_json, *, keep: Optional[dict] = None,
                 reload_gap_ms: int = 3_600_000):
        # keep: {"15m": (900000, 2960), "1h": (3600000, 760), "4h": (14400000, 200)}
        if not isinstance(keep, dict) or not keep or type(reload_gap_ms) is not int or reload_gap_ms < 0:
            raise ValueError("invalid_keep")
        for tf, spec in keep.items():
            if (type(tf) is not str or type(spec) is not tuple or len(spec) != 2
                    or type(spec[0]) is not int or spec[0] < 60_000 or spec[0] % 60_000
                    or type(spec[1]) is not int or spec[1] < 1):
                raise ValueError("invalid_keep")
        self._get, self._keep, self._gap = get_json, dict(keep), reload_gap_ms
        self._cache: dict[tuple[str, str], list[Bar]] = {}
        self._retry_at: dict[tuple[str, str], int] = {}

    def refresh(self, symbol: str, tf: str, now_ms: int) -> list[Bar]:
        """Aggiorna e restituisce la coda contigua. Solleva se la rete fallisce (la cache resta com'era)."""
        if tf not in self._keep or type(now_ms) is not int or now_ms <= 0:
            raise ValueError("invalid_request")
        step, keep = self._keep[tf]
        end = now_ms // step * step                       # la barra in formazione (apertura == end) e' esclusa
        key = (symbol, tf)
        raw = self._cache.get(key, [])
        hole = len(contiguous_tail(raw, step)) < len(raw)
        retry_at = self._retry_at.get(key)
        if not raw or (hole and now_ms >= (retry_at or 0)):
            raw = fetch_closed_bars(symbol, end - keep * step, end, candle_ms=step, get_json=self._get)
            retry_at = (now_ms + self._gap) if len(contiguous_tail(raw, step)) < len(raw) else None
        elif raw[-1].open_time_ms + step < end:
            raw = raw + fetch_closed_bars(symbol, raw[-1].open_time_ms + step, end, candle_ms=step,
                                          get_json=self._get)
        raw = raw[-keep:]
        self._cache[key] = raw
        if retry_at is None:
            self._retry_at.pop(key, None)
        else:
            self._retry_at[key] = retry_at
        return contiguous_tail(raw, step)
