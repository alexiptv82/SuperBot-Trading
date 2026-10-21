"""Tetto di spesa nel codice: nessuna chiamata parte se, nel caso peggiore, supererebbe il tetto del giorno o del mese.

Il registro `spend.jsonl` e' append-only e si rilegge all'avvio: un riavvio del container non azzera la spesa del
giorno. Giorno e mese sono UTC. Prezzi dal listino ufficiale DeepSeek (letto il 21/10/2026), per milione di token:
  deepseek-flash  cache-hit / cache-miss / output   fuori picco 0,003 / 0,15 / 0,60   picco 0,006 / 0,30 / 1,20
Picco: 01-04 e 06-10 UTC, lunedi-venerdi (nei festivi cinesi e' fuori picco: assumere il picco sovrastima, quindi e'
prudente). Un prezzo cambiato dal fornitore non lo vede nessuno: per questo c'e' `cost_safety` e il registro conserva
i token, non solo i dollari, cosi' si puo' ricalcolare.
"""
import json
import os
import time

PRICES = {
    # modello: {"off": (hit, miss, out), "peak": (hit, miss, out)}  dollari per milione di token
    "deepseek-flash": {"off": (0.003, 0.15, 0.60), "peak": (0.006, 0.30, 1.20)},
}
CHARS_PER_TOKEN = 2.5     # stima PRUDENTE (testo italiano/inglese con molti numeri): piu' token = piu' costo stimato


def is_peak(ts_ms: int) -> bool:
    t = time.gmtime(ts_ms / 1000)
    return t.tm_wday < 5 and (1 <= t.tm_hour < 4 or 6 <= t.tm_hour < 10)


def cost_usd(model: str, ts_ms: int, hit: int, miss: int, out: int) -> float:
    p = PRICES[model]["peak" if is_peak(ts_ms) else "off"]
    return (hit * p[0] + miss * p[1] + out * p[2]) / 1e6


def worst_case_usd(model: str, ts_ms: int, prompt_chars: int, max_out: int, safety: float) -> float:
    """Costo massimo possibile di una chiamata: tutto il prompt senza cache, prezzo di picco, risposta al massimo."""
    p = PRICES[model]["peak"]
    est_in = int(prompt_chars / CHARS_PER_TOKEN) + 1
    return (est_in * p[1] + max_out * p[2]) / 1e6 * safety


def _day(ts_ms: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts_ms / 1000))


class Budget:
    def __init__(self, path: str, daily_cap: float, monthly_cap: float, safety: float = 1.25):
        self.path, self.daily_cap, self.monthly_cap, self.safety = path, float(daily_cap), float(monthly_cap), float(safety)
        self.by_day: dict = {}
        self.n_lines = 0
        self.bad_lines = 0
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path) as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        self.by_day[r["day"]] = self.by_day.get(r["day"], 0.0) + float(r["cost"])
                        self.n_lines += 1
                    except (ValueError, KeyError, TypeError):
                        self.bad_lines += 1     # una riga rovinata non azzera la spesa: si conta e si va avanti
        except FileNotFoundError:
            pass

    def spent_day(self, ts_ms: int) -> float:
        return self.by_day.get(_day(ts_ms), 0.0)

    def spent_month(self, ts_ms: int) -> float:
        m = _day(ts_ms)[:7]
        return sum(v for d, v in self.by_day.items() if d[:7] == m)

    def check(self, model: str, ts_ms: int, prompt_chars: int, max_out: int) -> tuple:
        """(ok, motivo, costo_peggiore). Rifiuta se il caso peggiore sfonda il tetto del giorno o del mese."""
        worst = worst_case_usd(model, ts_ms, prompt_chars, max_out, self.safety)
        if self.spent_day(ts_ms) + worst > self.daily_cap:
            return False, "tetto giornaliero", worst
        if self.spent_month(ts_ms) + worst > self.monthly_cap:
            return False, "tetto mensile", worst
        return True, "", worst

    def record(self, model: str, ts_ms: int, hit: int, miss: int, out: int, ok: bool, note: str = "",
               est_cost: float = None) -> float:
        """Registra una chiamata. Con i token veri il costo e' calcolato; senza (risposta persa) si addebita la stima
        prudente `est_cost`, perche' una chiamata andata a vuoto puo' essere stata fatturata lo stesso."""
        if hit or miss or out:
            c = cost_usd(model, ts_ms, hit, miss, out) * self.safety
        else:
            c = float(est_cost or 0.0)
        c = round(c, 6)       # lo stesso valore che finisce nel file: dopo un riavvio i totali sono identici
        row = {"ts_ms": int(ts_ms), "day": _day(ts_ms), "model": model, "hit": int(hit), "miss": int(miss),
               "out": int(out), "cost": c, "ok": bool(ok), "note": str(note)[:80]}
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self.by_day[row["day"]] = self.by_day.get(row["day"], 0.0) + c
        self.n_lines += 1
        return c
