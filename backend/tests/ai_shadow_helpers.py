"""Mondo finto e modello finto per le prove dell'AI in ombra: nessuna rete, nessuna chiave vera."""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from director.ai_shadow import deepseek  # noqa: E402
from director.ai_shadow.config import Config  # noqa: E402
from director.ai_shadow.market import BarCache  # noqa: E402
from director.ai_shadow.pilot import Pilot  # noqa: E402

BAR = 900_000
T0 = 1_790_812_800_000          # 2026-10-01 00:00 UTC (giovedi), allineato al giorno
N = 3300                        # ~34 giorni di barre da 15 minuti
I0 = 3000                       # indice della barra su cui parte il primo ciclo
KEY = "sk-test-SEGRETO-0123456789abcdef"


def now_for(i: int) -> int:
    """Istante del ciclo che segue la chiusura della barra i (15 s dopo)."""
    return T0 + (i + 1) * BAR + 15_000


class World:
    """Candele finte per tutti i simboli: passeggiata casuale tranquilla (nessuno stop casuale). `fetch` consegna solo
    barre chiuse alla data richiesta, anche per 1h/4h/1d (aggregate dalle 15m)."""

    TF_MS = {"15m": BAR, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}

    def __init__(self, cfg: Config, seed: int = 7):
        rnd = random.Random(seed)
        self.bars = {}
        for k, s in enumerate(cfg.symbols):
            p = 100.0 * (1 + k)
            rows = []
            for i in range(N):
                o = p
                c = p * (1 + rnd.gauss(0, 0.0004))
                h = max(o, c) * (1 + abs(rnd.gauss(0, 0.0003)))
                l = min(o, c) * (1 - abs(rnd.gauss(0, 0.0003)))
                rows.append([T0 + i * BAR, o, h, l, c, 1000.0 + rnd.random() * 100])
                p = c
            self.bars[s] = rows
        self.fail = set()

    def set_bar(self, sym, i, o, h, l, c):
        self.bars[sym][i][1:5] = [o, h, l, c]

    def flat(self, sym, upto, price):
        """Rende piatti (prezzo costante) i dati di un simbolo fino alla barra `upto` compresa."""
        for i in range(upto + 1):
            self.bars[sym][i][1:5] = [price, price * 1.0002, price * 0.9998, price]

    def fetch(self, sym, tf, limit, now_ms):
        if sym in self.fail:
            raise ValueError("simbolo giu'")
        ms = self.TF_MS[tf]
        sub = [tuple(b) for b in self.bars[sym] if b[0] + BAR <= now_ms]
        if tf == "15m":
            return sub[-limit:]
        groups = {}
        for b in sub:
            groups.setdefault(b[0] // ms * ms, []).append(b)
        out = []
        for g in sorted(groups):
            rows = groups[g]
            if g + ms <= now_ms and len(rows) == ms // BAR:
                out.append((g, rows[0][1], max(r[2] for r in rows), min(r[3] for r in rows), rows[-1][4],
                            sum(r[5] for r in rows)))
        return out[-limit:]


class FakeModel:
    """Risposte a copione: ogni elemento e' un dict di decisioni, una stringa, o un'eccezione ModelError da alzare."""

    def __init__(self, script=None, usage=None):
        self.script = list(script or [])
        self.calls = []
        self.usage = usage or {"hit": 3000, "miss": 2000, "out": 400, "reasoning": 0}

    def __call__(self, cfg, key, system, user):
        self.calls.append({"key": key, "system": system, "user": user})
        item = self.script.pop(0) if self.script else {"market_read": "calmo", "decisions": []}
        if isinstance(item, Exception):
            raise item
        text = item if isinstance(item, str) else json.dumps(item)
        return {"content": text, "usage": dict(self.usage), "latency_ms": 12, "finish_reason": "stop",
                "model": "deepseek-flash"}


def opn(sym, side, sl, tp, conv=75, hz=24):
    return {"symbol": sym, "action": "OPEN_LONG" if side == 1 else "OPEN_SHORT", "conviction": conv,
            "stop_loss": sl, "take_profit": tp, "horizon_bars": hz, "thesis": "test", "invalidate_if": "test"}


def make(tmp_path, script=None, cfg=None, key=KEY, world=None, model=None, usage=None, sleeps=None, fetch=None):
    cfg = cfg or Config()
    world = world or World(cfg)
    model = model or FakeModel(script, usage)
    rec = sleeps if sleeps is not None else []
    cache = BarCache(cfg, fetch=fetch or world.fetch, sleep=lambda s: None, pause_s=0)
    pilot = Pilot(cfg, str(tmp_path), key, cache, model_call=model, sleep=lambda s: rec.append(s))
    return pilot, world, model, cfg


def path(world, sym, i_from, rows):
    """Imposta le barre i_from.. del simbolo con (o,h,l,c); le barre dopo restano piatte all'ultima chiusura."""
    last = None
    for k, (o, h, l, c) in enumerate(rows):
        world.set_bar(sym, i_from + k, o, h, l, c)
        last = c
    for i in range(i_from + len(rows), len(world.bars[sym])):
        world.set_bar(sym, i, last, last * 1.0002, last * 0.9998, last)


def read_jsonl(dirpath, prefix):
    import glob
    out = []
    for f in sorted(glob.glob(os.path.join(str(dirpath), prefix + "*.jsonl"))):
        with open(f) as fh:
            out += [json.loads(l) for l in fh if l.strip()]
    return out
