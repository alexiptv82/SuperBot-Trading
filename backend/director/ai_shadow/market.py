"""Candele pubbliche BitGet (nessuna chiave) e cache per tempo grafico. Solo barre chiuse, ordinate e senza duplicati."""
import json
import time
import urllib.request

BASE = "https://api.bitget.com"
TF_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
GRAN = {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}      # come li vuole l'API


def fetch_bars(symbol: str, tf: str, limit: int, now_ms: int, opener=urllib.request.urlopen, base: str = BASE) -> list:
    """Barre CHIUSE (t, o, h, l, c, v). Controllo dell'orologio: l'ultima riga deve essere la barra in formazione o
    quella appena chiusa; altrimenti la serie non si usa."""
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym += "USDT"
    url = ("%s/api/v2/mix/market/candles?symbol=%s&productType=USDT-FUTURES&granularity=%s&limit=%d"
           % (base, sym, GRAN[tf], limit))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with opener(req, timeout=10) as r:
        payload = json.loads(r.read())
    if not isinstance(payload, dict) or payload.get("code") != "00000" or not isinstance(payload.get("data"), list):
        raise ValueError("risposta rifiutata")
    rows = {}
    for r in payload["data"]:
        t = int(float(r[0]))
        rows[t] = (t, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]) if len(r) > 5 else 0.0)
    bars = [rows[t] for t in sorted(rows)]
    if not bars:
        raise ValueError("nessuna barra")
    ms = TF_MS[tf]
    if not (now_ms - 2 * ms < bars[-1][0] <= now_ms):
        raise ValueError("orologio delle candele non coerente")
    closed = [b for b in bars if b[0] + ms <= now_ms]
    for b in closed:
        if not (b[2] >= max(b[1], b[4]) and b[3] <= min(b[1], b[4]) and b[3] > 0):
            raise ValueError("barra incoerente")
    return closed


class BarCache:
    """Tiene in memoria le barre per (simbolo, tempo) e le riscarica solo quando e' chiusa una barra nuova di quel
    tempo: le barre da 15 minuti a ogni ciclo, le altre molto meno spesso."""

    def __init__(self, cfg, fetch=fetch_bars, sleep=time.sleep, pause_s: float = 0.12):
        self.cfg, self.fetch, self.sleep, self.pause_s = cfg, fetch, sleep, pause_s
        self.data: dict = {}        # (sym, tf) -> (barra_di_riferimento, barre)
        self.errors: dict = {}

    def _limit(self, tf: str) -> int:
        return {"15m": self.cfg.bars_15m, "1h": self.cfg.bars_1h, "4h": self.cfg.bars_4h, "1d": self.cfg.bars_1d}[tf]

    def refresh(self, now_ms: int, expect_t: int = None) -> dict:
        """Aggiorna tutto e ritorna {sym: {tf: barre}} per i simboli con almeno le barre da 15 minuti.
        `expect_t`: apertura dell'ultima barra da 15 minuti che dovrebbe esserci; se manca si riscarica anche a parita'
        di barra di riferimento (la barra appena chiusa puo' comparire con qualche secondo di ritardo)."""
        self.errors = {}
        for sym in self.cfg.symbols:
            for tf in ("15m", "1h", "4h", "1d"):
                ref = now_ms // TF_MS[tf]
                have = self.data.get((sym, tf))
                if have and have[0] == ref and not (tf == "15m" and expect_t is not None
                                                    and (not have[1] or have[1][-1][0] != expect_t)):
                    continue
                try:
                    bars = self.fetch(sym, tf, self._limit(tf), now_ms)
                    self.data[(sym, tf)] = (ref, bars)
                except Exception as e:      # un simbolo che non risponde resta indietro e recupera al giro dopo
                    self.errors["%s/%s" % (sym, tf)] = str(e)[:60]
                    if tf == "15m":
                        break
                self.sleep(self.pause_s)
        out = {}
        for sym in self.cfg.symbols:
            h15 = self.data.get((sym, "15m"))
            if not h15 or not h15[1]:
                continue
            out[sym] = {tf: (self.data.get((sym, tf)) or (0, []))[1] for tf in ("15m", "1h", "4h", "1d")}
        return out
