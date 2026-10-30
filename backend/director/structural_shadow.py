"""One bounded public-history worker. No wallet, orders or strategy inputs."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from director.structural_advisory import observe_structure, MAX_AGE_MS


class StructuralShadow:
    def __init__(self, *, include_methodology=False):
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='structure-advice')
        self.future = None
        self.last_started = None
        self.cache = {}
        self.rotation = 0
        self.closed = False
        self.include_methodology = include_methodology

    def poll(self, now_ms, symbols, loader):
        if self.closed or type(now_ms) is not int or now_ms <= 0:
            return {}
        if self.future is not None and self.future.done():
            try:
                for symbol, item in self.future.result().items():
                    if item is None:
                        self.cache.pop(symbol, None)
                    else:
                        self.cache[symbol] = item
            except Exception:
                pass
            self.future = None
        self.cache = {s: item for s, item in self.cache.items()
                      if 0 <= now_ms-item['observed_ms'] <= MAX_AGE_MS}
        if (self.future is None and callable(loader)
                and (self.last_started is None or now_ms-self.last_started >= 60000)):
            targets = sorted({s for s in symbols if isinstance(s, str)
                              and s.isascii() and s.isalnum() and len(s) <= 20})[:50]
            if targets:
                start = self.rotation % len(targets)
                selection = (targets[start:]+targets[:start])[:3]
                self.rotation += len(selection)
                self.last_started = now_ms
                def work():
                    out = {}
                    for symbol in selection:
                        out[symbol] = None
                        try:
                            rows = loader(symbol)
                            item = observe_structure(symbol, rows, now_ms)
                            if item is not None:
                                if self.include_methodology:
                                    # Failure of optional scorer cannot hide structural advice.
                                    try:
                                        from director.classical_methodology import observe_methodology
                                        item['classical_methodology'] = observe_methodology(symbol, rows, now_ms)
                                    except Exception:
                                        item['classical_methodology'] = {'status': 'unavailable'}
                                out[symbol] = item
                        except Exception:
                            pass
                    return out
                self.future = self.pool.submit(work)
        return deepcopy(self.cache)

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)
