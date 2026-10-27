"""Read-only public market IO outside the sole financial-state writer.

Fast protection has its own worker, so slow macro/history downloads cannot
block account management. Snapshots expire; no invented prices on failures.
"""
from concurrent.futures import ThreadPoolExecutor
import time


class Feeds:
    def __init__(self,fetch,daily,four,context,clock=time.time):
        self.fetch,self.daily,self.four,self.context,self.clock=fetch,daily,four,context,clock
        self.pools={kind:ThreadPoolExecutor(max_workers=1,thread_name_prefix="brain-"+kind) for kind in ("fast","entry")}
        self.pending={};self.latest={"fast":{},"entry":{}}

    def close(self):
        for pool in self.pools.values():pool.shutdown(wait=True,cancel_futures=True)

    def fast(self,symbols):
        out={}
        for s in symbols:
            try:out[s]={"rows":self.fetch(s,"1m",1000),"received_ms":int(self.clock()*1000)}
            except Exception:pass
        return out

    def entry(self,symbols,now_ms):
        out={"markets":{},"context":None}
        for s in symbols:
            try:
                rows=self.fetch(s,"15m",1000)
                out["markets"][s]={"rows":rows,"received_ms":int(self.clock()*1000),
                                    "daily":self.daily(s,now_ms),"four":self.four(s,now_ms)}
            except Exception:pass
        try:out["context"]=self.context(symbols,now_ms)
        except Exception:pass
        return out

    def poll(self,symbols,required,now_ms):
        for kind,args in (("fast",(tuple(sorted(required)),)),("entry",(tuple(symbols),now_ms))):
            future=self.pending.get(kind)
            if future and future.done():
                try:self.latest[kind]=future.result()
                except Exception:pass
                self.pending.pop(kind,None)
            if kind not in self.pending:
                self.pending[kind]=self.pools[kind].submit(getattr(self,kind),*args)
        return self.latest["fast"],self.latest["entry"]

    @staticmethod
    def fresh(item,now_ms):
        return bool(item and 0<=now_ms-item.get("received_ms",0)<=120000)
