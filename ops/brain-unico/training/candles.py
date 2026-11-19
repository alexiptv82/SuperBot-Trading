"""Archivio locale di candele CHIUSE (sola lettura, nessuna rete). Formato: una directory con `<SIMBOLO>.jsonl`,
una riga per candela: {"t": open_ms, "o":..., "h":..., "l":..., "c":..., "v":...}.

Il dataset builder NON scarica nulla: le candele si preparano a parte (fonte pubblica) e si danno in input.
Una candela con open_ms = t e intervallo i e' CHIUSA all'istante t + i: e' usabile solo da decisioni con ts >= t + i.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from typing import Optional

INTERVAL_MS = 900_000          # 15 minuti


@dataclass(frozen=True)
class Candle:
    t: int
    o: float
    h: float
    l: float
    c: float
    v: float


class CandleStore:
    def __init__(self, root: str, interval_ms: int = INTERVAL_MS):
        self.root, self.interval = os.path.abspath(root), interval_ms
        self._cache: dict[str, list] = {}
        self.stats = {"files": 0, "bad_rows": 0, "duplicates": 0, "unsorted_fixed": 0}

    def symbols(self) -> list:
        return sorted(n[:-6] for n in os.listdir(self.root) if n.endswith(".jsonl"))

    def _load(self, symbol: str) -> list:
        if symbol in self._cache:
            return self._cache[symbol]
        path = os.path.join(self.root, symbol + ".jsonl")
        out: dict[int, Candle] = {}
        try:
            st = os.lstat(path)
            if not stat.S_ISREG(st.st_mode):
                raise OSError("not_regular")
            with open(path, encoding="utf-8") as fh:
                self.stats["files"] += 1
                last = -1
                for line in fh:
                    try:
                        d = json.loads(line)
                        c = Candle(int(d["t"]), float(d["o"]), float(d["h"]), float(d["l"]), float(d["c"]), float(d.get("v", 0)))
                    except (ValueError, KeyError, TypeError):
                        self.stats["bad_rows"] += 1
                        continue
                    if not (c.l <= min(c.o, c.c) and c.h >= max(c.o, c.c) and c.l > 0 and c.t > 0 and c.t % self.interval == 0):
                        self.stats["bad_rows"] += 1
                        continue
                    if c.t in out:
                        self.stats["duplicates"] += 1
                    if c.t < last:
                        self.stats["unsorted_fixed"] += 1
                    last = max(last, c.t)
                    out[c.t] = c
        except OSError:
            pass
        self._cache[symbol] = [out[k] for k in sorted(out)]
        return self._cache[symbol]

    def has(self, symbol: str) -> bool:
        return bool(self._load(symbol))

    def closed_before(self, symbol: str, ts: int, n: int) -> list:
        """Le ultime `n` candele CHIUSE entro `ts` (t + intervallo <= ts), in ordine crescente. Mai una candela aperta."""
        cs = self._load(symbol)
        lo, hi = 0, len(cs)
        while lo < hi:                                   # primo indice con t + interval > ts
            mid = (lo + hi) // 2
            if cs[mid].t + self.interval <= ts:
                lo = mid + 1
            else:
                hi = mid
        return cs[max(0, lo - n):lo]

    def window(self, symbol: str, start_ms: int, end_ms: int) -> list:
        """Candele con open in [start_ms, end_ms)."""
        return [c for c in self._load(symbol) if start_ms <= c.t < end_ms]

    def contiguous(self, cs: list) -> bool:
        return all(b.t - a.t == self.interval for a, b in zip(cs, cs[1:]))


def first_bar_start(ts: int, interval: int) -> int:
    """Prima candela il cui open e' >= ts: la candela che CONTIENE la decisione e' esclusa (non si sa nulla del suo
    percorso prima della decisione)."""
    return -(-ts // interval) * interval
