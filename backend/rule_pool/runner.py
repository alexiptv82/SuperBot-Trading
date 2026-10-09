"""Runner in avanti (paper): candele chiuse -> giornale -> valutazione del pool.

Solo dati PUBBLICI: nessuna chiave, nessun ordine, nessun accesso al bot. Ogni giro:
1. aggiorna l'archivio delle candele 15m (solo candele CHIUSE; la serie non si accorcia mai,
   cosi' gli indicatori ricorsivi restano identici nel tempo);
2. allinea il giornale 'paper' (solo trade con ingresso dall'attivazione in poi);
3. valuta il pool e ritorna le transizioni di stato da notificare.
"""
from __future__ import annotations

import os
import time
import urllib.parse
import urllib.request
from typing import Callable, Optional

import numpy as np

import strategy_lab as sl
from rule_pool import evidence as ev
from rule_pool import pool, replay
from rule_pool.journal import Journal

M15 = sl.M15
DAY = 86_400_000
SETTLE_MS = 5_000            # una candela e' "chiusa" solo qualche secondo dopo la sua fine
BACKFILL_DAYS = 365          # storico iniziale: abbastanza perche' EMA200 su 4h sia a regime
MIN_BARS = 15_000            # ~156 giorni di barre da 15m: sotto, niente segnali
MAX_STALE_MS = 3 * 3_600_000


def last_closed_open(now_ms: int) -> int:
    """Apertura dell'ultima candela 15m gia' chiusa (e assestata) a `now_ms`."""
    return ((now_ms - SETTLE_MS) // M15) * M15 - M15


class CandleStore:
    """Archivio npy per simbolo. Si aggiunge in coda; l'inizio non cambia mai."""

    def __init__(self, directory: str):
        self.dir = directory
        os.makedirs(directory, exist_ok=True)

    def path(self, symbol: str) -> str:
        return os.path.join(self.dir, f"{symbol.split('/')[0]}_15m.npy")

    def load(self, symbol: str) -> np.ndarray:
        p = self.path(symbol)
        return np.load(p) if os.path.exists(p) else np.empty((0, 6), dtype=float)

    def _save(self, symbol: str, arr: np.ndarray) -> None:
        tmp = self.path(symbol) + ".tmp.npy"
        np.save(tmp, arr)
        os.replace(tmp, self.path(symbol))      # scrittura atomica

    def update(self, symbol: str, fetch: Callable, now_ms: int, backfill_from_ms: int) -> int:
        """Aggiunge le candele chiuse mancanti. `fetch(symbol, since_ms)` ritorna righe
        [ts, o, h, l, c, v] con ts >= since (come ccxt). Ritorna il numero di barre nuove."""
        arr = self.load(symbol)
        limit = last_closed_open(now_ms)
        since = int(arr[-1, 0]) + M15 if len(arr) else int(backfill_from_ms)
        new: dict = {}
        guard = 0
        while since <= limit and guard < 5000:
            guard += 1
            rows = [r for r in fetch(symbol, since) if since <= int(r[0]) <= limit]
            if not rows:
                break                               # niente di nuovo (o buco): riprova al prossimo giro
            for r in rows:
                new[int(r[0])] = [float(x) for x in r[:6]]
            since = max(int(r[0]) for r in rows) + M15
        if new:
            add = np.array([new[k] for k in sorted(new)], dtype=float)
            self._save(symbol, np.vstack([arr, add]) if len(arr) else add)
        return len(new)


def fetch_bitget(symbol: str, since_ms: int) -> list:
    """Candele 15m pubbliche di BitGet (sola lettura, nessuna chiave). Con retry."""
    import ccxt  # import locale: i test non richiedono ccxt
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    last_exc = None
    for attempt in range(5):
        try:
            return _CLIENT.fetch_ohlcv(symbol, "15m", since=since_ms, limit=200)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(2 + 2 * attempt)
    raise RuntimeError(f"{symbol}: download fallito ({type(last_exc).__name__})")


_CLIENT = None


def telegram_sender() -> Optional[Callable]:
    """Invio Telegram con le stesse variabili del bot. None se non configurato.
    Non stampa mai il token (nemmeno nei messaggi d'errore)."""
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not (token and chat):
        return None

    def send(text: str) -> bool:
        try:
            data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
            req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status == 200
        except Exception as exc:  # noqa: BLE001
            print(f"telegram: invio fallito ({type(exc).__name__})", flush=True)
            return False
    return send


def format_transition(rid: str, old: str, new: str, reasons: list) -> str:
    why = f" ({'; '.join(reasons)})" if reasons else ""
    return f"Pool regole: {rid} {old} -> {new}{why}"


def _init_meta(journal: Journal, now_ms: int) -> tuple:
    """Fissa una volta sola l'inizio dell'archivio e l'attivazione del conteggio in avanti."""
    back = journal.get_meta("backfill_from_ms")
    if back is None:
        back = str((now_ms - BACKFILL_DAYS * DAY) // sl.H4 * sl.H4)
        journal.set_meta("backfill_from_ms", back)
    fwd = journal.get_meta("forward_from_ms")
    if fwd is None:
        fwd = str(-(-now_ms // M15) * M15)               # prossimo multiplo di 15 minuti
        journal.set_meta("forward_from_ms", fwd)
    return int(back), int(fwd)


def run_once(journal: Journal, rules_: list, store: CandleStore, fetch: Callable, now_ms: int,
             gate: ev.Gate = ev.Gate(), notify: Optional[Callable] = None,
             venue: str = "paper") -> dict:
    """Un giro completo. Non solleva per errori di rete su un simbolo: li riporta in `errors`."""
    for r in rules_:
        journal.register_rule(r)                         # solleva ParamsChangedError se cambiate
    back, fwd = _init_meta(journal, now_ms)
    errors: dict = {}
    frames: dict = {}
    fresh: dict = {}
    for sym in sorted({s for r in rules_ for s in r.symbols}):
        try:
            store.update(sym, fetch, now_ms, back)
        except Exception as exc:  # noqa: BLE001
            errors[sym] = f"aggiornamento fallito ({type(exc).__name__})"
        arr = store.load(sym)
        if len(arr) < MIN_BARS:
            errors.setdefault(sym, f"storico insufficiente ({len(arr)} barre)")
            continue
        fresh[sym] = int(arr[-1, 0])
        if last_closed_open(now_ms) - fresh[sym] > MAX_STALE_MS:
            errors.setdefault(sym, "dati vecchi")
            continue
        frames[sym] = replay.frames_for(sl.bars_from_array(arr))
    for r in rules_:
        for sym in r.symbols:
            if sym in frames:
                replay.sync_journal(journal, r, sym, frames[sym], venue=venue, min_entry_t=fwd)
    result = pool.evaluate_pool(journal, rules_, gate, venue)
    result.update(errors=errors, fresh=fresh, forward_from_ms=fwd, backfill_from_ms=back)
    if notify is not None:
        _notify(journal, result, notify)
    return result


def _notify(journal: Journal, result: dict, notify: Callable) -> None:
    msgs = [format_transition(rid, old, new, why)
            for rid, old, new, why in result["transitions"] if old is not None]
    prev = journal.get_meta("alarm")
    now_alarm = "1" if result["alarm"] else "0"
    if (prev is not None and prev != now_alarm) or (prev is None and now_alarm == "1"):
        msgs.append("Pool regole: ALLARME controlli attivo, decisioni congelate: verificare il sistema"
                    if result["alarm"] else "Pool regole: allarme controlli rientrato")
    journal.set_meta("alarm", now_alarm)
    for m in msgs:
        notify(m)


def render_report(journal: Journal, rules_: list, result: Optional[dict] = None,
                  gate: ev.Gate = ev.Gate(), venue: str = "paper") -> str:
    """Riepilogo compatto in italiano (stato, avanzamento verso la soglia, controlli)."""
    from rule_pool.rules import promotable_count
    k = promotable_count(rules_)
    ctrl = {r.base_rule: r for r in rules_ if r.kind == "control"}
    fwd = journal.get_meta("forward_from_ms")
    lines = [f"Pool regole (paper in avanti) - K={k}, soglia t>={ev.bonferroni_z(k, gate.alpha):.2f}, "
             f"min {gate.min_trades} trade e {gate.min_months} mesi"]
    if fwd:
        lines.append("Attivo dal " + time.strftime("%Y-%m-%d %H:%M", time.gmtime(int(fwd) / 1000)) + " UTC")
    for r in (x for x in rules_ if x.kind == "promotable"):
        t, x = journal.closed_arrays(r.rule_id, r.version, venue)
        s = ev.summarize(t, x)
        st = journal.get_state(r.rule_id, r.version) or "CANDIDATA"
        if s is None:
            lines.append(f"- {r.rule_id}: {st}, nessun trade chiuso ancora")
            continue
        openn = sum(1 for tr in journal.all_trades(r.rule_id, r.version, venue) if tr["status"] == "open")
        c = ctrl.get(r.rule_id)
        cm = ""
        if c is not None:
            ct, cx = journal.closed_arrays(c.rule_id, c.version, venue)
            cm = f", controllo {cx.mean():+.1f} bp su {len(cx)}" if len(cx) else ", controllo: nessun dato"
        tg = f"{s.t_gate:+.2f}" if s.t_gate == s.t_gate else "n/d"
        lines.append(f"- {r.rule_id}: {st}, {s.n}/{gate.min_trades} trade chiusi ({openn} aperti), "
                     f"netto {s.mean:+.1f} bp [{s.ci_low:+.0f},{s.ci_high:+.0f}], t={tg}, "
                     f"{s.n_months}/{gate.min_months} mesi{cm}")
    if result is not None:
        lines.append("Allarme controlli: " + ("ATTIVO" if result["alarm"] else "no"))
        for sym, msg in sorted(result.get("errors", {}).items()):
            lines.append(f"! {sym}: {msg}")
    return "\n".join(lines)
