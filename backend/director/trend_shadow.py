"""Bounded asynchronous trend advisor. It never waits for advice or touches wallets.

One worker at most, optional external public 1m loader only for classics.
No trading outcome can be returned: only a cached observational dictionary.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from director.trend_engine_v11 import read_many

INTERVAL_MS=60000
MAX_AGE_MS=180000


class TrendShadow:
    def __init__(self,*,interval_ms=INTERVAL_MS):
        if type(interval_ms)!=int or interval_ms<10000:
            raise ValueError('invalid_trend_interval')
        self.interval=interval_ms
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='trend-v11-shadow')
        self.future=None;self.last_started=None;self.cache={};self.closed=False
        self._lock=Lock()

    def _poll(self,now_ms):
        if self.future is not None and self.future.done():
            try:
                observations=self.future.result()
                if isinstance(observations,dict):
                    self.cache.update(observations)
            except Exception:
                pass
            self.future=None
        # Unknown/old observations cannot be represented as actionable opinions.
        fresh={}
        for sym,data in self.cache.items():
            if (isinstance(data,dict) and type(data.get('observed_ms'))==int
                and 0<=now_ms-data['observed_ms']<=MAX_AGE_MS and
                data.get('quality')=='OK' and data.get('ready') is True):
                fresh[sym]=data
        return fresh

    def poll(self,now_ms,series):
        """For Brain: existing 1m bars, no new network requests."""
        if self.closed or type(now_ms)!=int or now_ms<=0:return {}
        with self._lock:
            observations=self._poll(now_ms)
            if (self.future is None and
                (self.last_started is None or now_ms-self.last_started>=self.interval) and
                isinstance(series,dict)):
                # Worker operates on independent bounded copies, not bot state.
                frozen={sym:list(bars)[-300:] for sym,bars in list(series.items())[:50]
                        if isinstance(bars,(list,tuple))}
                self.last_started=now_ms
                self.future=self.pool.submit(read_many,frozen,now_ms)
            return observations

    def poll_public(self,now_ms,symbols,loader):
        """For classics: launch bounded public fetch OFF the wallet/strategy thread.

        A slow/broken URL cannot delay stop processing or veto a candidate.
        Missing symbols stay absent, never inferred SHORT or HOLD.
        """
        if self.closed or type(now_ms)!=int or now_ms<=0:return {}
        with self._lock:
            observations=self._poll(now_ms)
            if (self.future is None and
                (self.last_started is None or now_ms-self.last_started>=self.interval)
                and callable(loader) and isinstance(symbols,(list,tuple))):
                targets=tuple(dict.fromkeys(
                    s for s in symbols[:40] if isinstance(s,str) and s.isascii() and s.isalnum()))
                def task():
                    result={}
                    for sym in targets:
                        try:
                            rows=loader(sym)
                            if isinstance(rows,(list,tuple)) and rows:
                                result[sym]=read_many({sym:list(rows)[-300:]},now_ms)[sym]
                        except Exception:
                            continue
                    return result
                self.last_started=now_ms
                self.future=self.pool.submit(task)
            return observations

    def close(self):
        self.closed=True
        self.pool.shutdown(wait=False,cancel_futures=True)
