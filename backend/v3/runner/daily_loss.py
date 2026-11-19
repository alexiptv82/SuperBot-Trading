"""Freno di perdita giornaliera del Brain PAPER (decisione dell'utente, 5/11: avviso al 35 %, stop al 50 %).

**Definizione (scelta tecnica di Claude, i due numeri sono dell'utente):**
* giorno = giorno UTC (stessa regola del tetto di spesa del modello): riparte a mezzanotte UTC;
* capitale di inizio giornata = capitale iniziale + PnL realizzato delle chiusure PRIMA di mezzanotte;
* perdita di oggi = perdita realizzata oggi + perdita NON realizzata delle posizioni aperte (prezzo dell'ultimo minuto
  chiuso contro il prezzo d'ingresso); un guadagno compensa. Se anche un solo prezzo necessario manca
  o non e' valido, la valutazione fallisce senza produrre una perdita parziale: il Runner blocca
  le nuove aperture (daily_loss_check_failed), mentre il servizio uscite resta indipendente;
* frazione = perdita / capitale di inizio giornata. ``>= warn`` -> ``warn`` (avviso, il Brain continua);
  ``>= halt`` -> ``halt``: nessuna nuova apertura e nessuna chiamata al modello fino a mezzanotte UTC
  (uscite, stop e chiusura manuale proseguono). Lo stop e' **agganciato per il resto del giorno**: anche se
  le posizioni aperte poi recuperano, non si riapre fino al giorno dopo.

``DailyLossGuard`` e' la funzione che il direttore chiama a ogni controllo: valuta al massimo una volta al minuto,
ricorda lo stato nel file ``daily_loss.json`` della cartella dati (cosi' un riavvio non rimanda l'avviso e non
toglie il blocco) e manda l'avviso una sola volta per livello e per giorno. Se lo stato manca, e' corrotto o non
dimostra la continuita' dei controlli, la giornata si ricostruisce da journal e candele (``max_daily_loss_between``);
se non si puo', le nuove aperture restano bloccate (Issue #124). Nessun importo nei file di stato
oltre alle frazioni; nessuna rete se non l'invio dell'avviso e la ricostruzione (entrambi iniettati).
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Callable, Optional

from backend.v3.dashboard import build_summary
from backend.v3.events import EventJournal

DAY_MS = 86_400_000
MINUTE_MS = 60_000
STATE_FILE = "daily_loss.json"
LEVELS = ("ok", "warn", "halt")


@dataclass(frozen=True)
class DailyLoss:
    level: str                  # ok | warn | halt
    loss_fraction: Decimal      # >= 0
    loss_usd: Decimal           # >= 0, PAPER
    day_start_ms: int


def day_start_ms(now_ms: int) -> int:
    return now_ms // DAY_MS * DAY_MS


def pct_text(fraction: Decimal) -> str:
    """Percentuale con un decimale TRONCATO (mai arrotondata in su: 34,99 % non diventa «35,0» mentre il livello e'
    ancora ``ok``), per battito e messaggi (``Decimal`` finito >= 0)."""
    return str((fraction * 100).quantize(Decimal("0.1"), rounding=ROUND_DOWN))


def _check_fractions(warn: object, halt: object) -> None:
    if (type(warn) is not Decimal or type(halt) is not Decimal or not warn.is_finite() or not halt.is_finite()
            or not Decimal("0") < warn < halt <= Decimal("1")):
        raise ValueError("invalid_daily_loss_fractions")


def evaluate_daily_loss(*, journal: EventJournal, portfolio_id: str, run_id: str, initial_equity: Decimal,
                        now_ms: int, price_of: Callable[[str, int], Decimal], warn_fraction: Decimal,
                        halt_fraction: Decimal) -> DailyLoss:
    """Perdita di oggi e livello. Fail-closed sul capitale: se quello di inizio giornata non e' positivo e' ``halt``."""
    if type(now_ms) is not int or now_ms <= 0:
        raise ValueError("invalid_now")
    if type(initial_equity) is not Decimal or not initial_equity.is_finite() or initial_equity <= 0:
        raise ValueError("invalid_initial_equity")
    _check_fractions(warn_fraction, halt_fraction)
    summary = build_summary(journal, portfolio_id, run_id)
    start = day_start_ms(now_ms)
    before = sum((t.realized_pnl for t in summary.closed_trades if t.closed_at_ms < start), Decimal("0"))
    today = sum((t.realized_pnl for t in summary.closed_trades if t.closed_at_ms >= start), Decimal("0"))
    unrealized = Decimal("0")
    for pos in summary.open_positions:
        try:
            price = price_of(pos.symbol, now_ms)
        except Exception:
            # Il caller (Runner.tick) entra in halted:daily_loss_check_failed:
            # continuare con una stima parziale sottostimerebbe il rischio.
            # Non includere dettagli del provider/simbolo nei messaggi operativi.
            raise ValueError("daily_loss_price_unavailable") from None
        if type(price) is not Decimal or not price.is_finite() or price <= 0:
            raise ValueError("daily_loss_price_invalid")
        unrealized += (price - pos.fill_price) * pos.quantity * pos.side
    start_equity = initial_equity + before
    if start_equity <= 0:
        return DailyLoss("halt", Decimal("1"), max(-(today + unrealized), Decimal("0")), start)
    loss = max(-(today + unrealized), Decimal("0"))
    fraction = loss / start_equity
    level = "halt" if fraction >= halt_fraction else ("warn" if fraction >= warn_fraction else "ok")
    return DailyLoss(level, fraction, loss, start)


STATE_VERSION = 2
CONTINUITY_MS = 3 * MINUTE_MS          # buco massimo fra due controlli PERSISTITI senza dover ricostruire la giornata
AUDIT_RETRY_MS = 5 * MINUTE_MS         # un blocco «non verificabile» si riprova al massimo ogni 5 minuti
LATCH_REASONS = ("", "loss", "unverified")
_STATE_KEYS = frozenset({"version", "day_start_ms", "warn_sent", "halt_sent", "unverified_sent", "halt_latched",
                         "latch_reason", "checked_through_ms", "audit_from_ms"})
_LEGACY_KEYS = frozenset({"day_start_ms", "warn_sent", "halt_sent", "halt_latched"})

Audit = Callable[[int, int], Decimal]


def _strict_decimal(value: object) -> Decimal:
    try:
        out = Decimal(str(value))
    except Exception:
        raise ValueError("daily_loss_audit_invalid_journal") from None
    if not out.is_finite():
        raise ValueError("daily_loss_audit_invalid_journal")
    return out


def max_daily_loss_between(*, journal: EventJournal, portfolio_id: str, run_id: str, initial_equity: Decimal,
                           from_ms: int, now_ms: int,
                           closes_of: Callable[[str, int, int], dict]) -> Decimal:
    """Ricostruisce, SOLO dal journal e dalle candele 1m chiuse, la perdita massima che il controllo vivo avrebbe visto
    a ogni minuto ``E`` del giorno UTC di ``now_ms`` con ``from_ms < E <= now_ms`` (Issue #124).

    Stessa formula di ``evaluate_daily_loss`` all'istante ``E``: realizzato del giorno con chiusure ``<= E`` piu' non
    realizzato delle posizioni aperte a ``E`` (aperte ``<= E``, non ancora chiuse) al prezzo di chiusura della barra
    ``[E - 1m, E)``. ``closes_of(simbolo, inizio, fine)`` restituisce ``{apertura_ms: close Decimal}``.
    Fail-closed: payload del journal non interpretabile o una barra necessaria assente -> ``ValueError``.
    Un portafoglio senza eventi non chiede alcun prezzo e restituisce 0 (primo avvio verificabile).
    """
    if type(now_ms) is not int or now_ms <= 0 or type(from_ms) is not int:
        raise ValueError("invalid_now")
    if type(initial_equity) is not Decimal or not initial_equity.is_finite() or initial_equity <= 0:
        raise ValueError("invalid_initial_equity")
    start = day_start_ms(now_ms)
    opens: dict[str, tuple] = {}
    closes: dict[str, tuple] = {}
    for se in journal.list_run(portfolio_id, run_id):
        ev = se.event
        p = ev.payload if isinstance(ev.payload, dict) else None
        if ev.kind not in ("paper_open", "paper_close"):
            continue
        if p is None or not isinstance(p.get("position_id"), str) or not p["position_id"]:
            raise ValueError("daily_loss_audit_invalid_journal")
        pid, ts = p["position_id"], ev.occurred_at_ms
        if ev.kind == "paper_open":
            side = p.get("side")
            if side not in (1, -1) or type(side) is not int or not isinstance(p.get("symbol"), str):
                raise ValueError("daily_loss_audit_invalid_journal")
            fill, qty = _strict_decimal(p.get("fill_price")), _strict_decimal(p.get("quantity"))
            if fill <= 0 or qty <= 0:
                raise ValueError("daily_loss_audit_invalid_journal")
            opens[pid] = (p["symbol"], side, fill, qty, ts)
        else:
            closes[pid] = (ts, _strict_decimal(p.get("realized_pnl")))
    if not opens and not closes:
        return Decimal("0")
    before = sum((pnl for ts, pnl in closes.values() if ts < start), Decimal("0"))
    start_equity = initial_equity + before
    if start_equity <= 0:
        return Decimal("1")
    first = max(from_ms, start) // MINUTE_MS * MINUTE_MS + MINUTE_MS
    last = now_ms // MINUTE_MS * MINUTE_MS
    if first > last:
        return Decimal("0")
    marks = range(first, last + 1, MINUTE_MS)

    def alive(pid: str, e: int) -> bool:
        o, c = opens[pid], closes.get(pid)
        return o[4] <= e and (c is None or c[0] > e)

    need: dict[str, list[int]] = {}
    for pid, o in opens.items():
        ts_open, c = o[4], closes.get(pid)
        lo, hi = max(first, ts_open // MINUTE_MS * MINUTE_MS), last if c is None else min(last, c[0] // MINUTE_MS * MINUTE_MS)
        if lo <= hi:
            span = need.setdefault(o[0], [lo, hi])
            span[0], span[1] = min(span[0], lo), max(span[1], hi)
    prices: dict[str, dict] = {}
    for sym, (lo, hi) in need.items():
        got = closes_of(sym, lo - MINUTE_MS, hi)
        if not isinstance(got, dict):
            raise ValueError("daily_loss_audit_price_missing")
        prices[sym] = got
    peak = Decimal("0")
    for e in marks:
        realized = sum((pnl for ts, pnl in closes.values() if start <= ts <= e), Decimal("0"))
        unrealized = Decimal("0")
        for pid, (sym, side, fill, qty, _ts) in opens.items():
            if not alive(pid, e):
                continue
            price = prices.get(sym, {}).get(e - MINUTE_MS)
            if type(price) is not Decimal or not price.is_finite() or price <= 0:
                raise ValueError("daily_loss_audit_price_missing")
            unrealized += (price - fill) * qty * side
        loss = max(-(realized + unrealized), Decimal("0"))
        peak = max(peak, loss / start_equity)
    return peak


class DailyLossGuard:
    """Valuta una volta al minuto, ricorda warn/halt per il giorno e manda un solo avviso per livello.

    **Continuita' dimostrata (Issue #124).** Lo stato su disco (v2) registra fino a quale istante la perdita e' stata
    controllata (``checked_through_ms``). Il blocco non dipende dal fatto che *ora* la perdita sia sotto soglia:

    * stato del giorno valido e ultimo controllo persistito da non piu' di ``CONTINUITY_MS``: si prosegue;
    * altrimenti (file assente, corrotto, del formato precedente, del giorno prima, buco di controlli, scrittura
      fallita prima di un riavvio) la giornata viene **ricostruita** con ``audit(da, adesso)`` (journal + candele 1m,
      vedi ``max_daily_loss_between``) dall'ultimo istante dimostrato, o dalla mezzanotte UTC;
    * ricostruzione >= soglia di stop -> blocco ``loss`` fino a mezzanotte UTC;
    * ricostruzione impossibile (``audit`` assente o in errore) -> blocco ``unverified``: nessuna nuova apertura
      finche' una ricostruzione successiva non riesce (riprovata al piu' ogni ``AUDIT_RETRY_MS``) o finche' il giorno
      UTC cambia. Un blocco ``loss`` non si toglie mai prima di mezzanotte;
    * orologio tornato indietro rispetto all'ultimo controllo persistito -> blocco ``unverified``.

    ``recheck`` (prima di un'apertura) esige che lo stato appena calcolato sia davvero su disco: se il disco rifiuta
    la scrittura, l'apertura e' negata (``daily_loss_latch_not_persisted`` / ``daily_loss_state_not_persisted``).
    Le uscite non passano da qui: un errore o un blocco ferma solo le nuove aperture.
    """

    def __init__(self, *, data_dir: Path, evaluate: Callable[[int], DailyLoss],
                 send: Optional[Callable[[str], bool]] = None, warn_fraction: Decimal, halt_fraction: Decimal,
                 audit: Optional[Audit] = None):
        _check_fractions(warn_fraction, halt_fraction)
        if not isinstance(data_dir, Path) or not data_dir.is_dir():
            raise ValueError("invalid_data_dir")
        if audit is not None and not callable(audit):
            raise ValueError("invalid_audit")
        self._path = data_dir / STATE_FILE
        self._evaluate, self._send, self._audit = evaluate, send, audit
        self._warn, self._halt = warn_fraction, halt_fraction
        self._minute = -1
        self._last: Optional[DailyLoss] = None
        self._last_audit_try = -1
        self._state, self._trust = self._load()

    @staticmethod
    def _blank(day: int = 0) -> dict:
        return {"version": STATE_VERSION, "day_start_ms": day, "warn_sent": False, "halt_sent": False,
                "unverified_sent": False, "halt_latched": False, "latch_reason": "", "checked_through_ms": 0,
                "audit_from_ms": 0}

    def _load(self) -> tuple[dict, str]:
        """(stato, fiducia) con fiducia ``v2`` | ``legacy`` | ``missing`` | ``invalid``. Mai un'eccezione."""
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self._blank(), "missing"
        except (OSError, ValueError):
            return self._blank(), "invalid"
        bools = ("warn_sent", "halt_sent", "halt_latched")
        if (isinstance(raw, dict) and set(raw) == _LEGACY_KEYS and type(raw["day_start_ms"]) is int
                and raw["day_start_ms"] >= 0 and all(type(raw[k]) is bool for k in bools)):
            st = self._blank(raw["day_start_ms"])
            st.update({k: raw[k] for k in bools})
            st["latch_reason"] = "loss" if raw["halt_latched"] else ""
            return st, "legacy"
        ints = ("day_start_ms", "checked_through_ms", "audit_from_ms")
        ok = (isinstance(raw, dict) and set(raw) == _STATE_KEYS and raw["version"] == STATE_VERSION
              and type(raw["version"]) is int
              and all(type(raw[k]) is int and raw[k] >= 0 for k in ints)
              and all(type(raw[k]) is bool for k in bools + ("unverified_sent",))
              and raw["latch_reason"] in LATCH_REASONS and type(raw["latch_reason"]) is str
              and (raw["latch_reason"] != "") == raw["halt_latched"]
              and raw["day_start_ms"] % DAY_MS == 0)
        return (dict(raw), "v2") if ok else (self._blank(), "invalid")

    def _save(self) -> None:
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".daily_loss.", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._state, f, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path)
            tmp = None
            try:                                                  # rende durevole anche il rename (best-effort)
                dfd = os.open(self._path.parent, os.O_RDONLY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
            except OSError:
                pass
        except OSError:
            pass                                                # lo stato in memoria vale; recheck nega le aperture
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def _notify(self, key: str, text: str) -> None:
        if self._send is None or self._state[key]:
            return
        try:
            sent = self._send(text) is True
        except Exception:
            sent = False
        if sent:
            self._state[key] = True                              # se l'invio fallisce si riprova al minuto dopo
            self._save()

    def recheck(self, now_ms: int) -> DailyLoss:
        """Force a fresh evaluation after an AI wait, bypassing minute cache.

        The state just computed (latch, day, checked-through instant) must be *durably* on disk before any new
        OPEN; if the disk refused the write, fail closed to the caller. Scheduled checks keep the minute cache.
        """
        if type(now_ms) is not int or now_ms <= 0:
            raise ValueError("invalid_now")
        self._last = None
        result = self(now_ms)
        persisted, trust = self._load()
        if trust != "v2" or persisted != self._state:
            raise ValueError("daily_loss_latch_not_persisted" if result.level == "halt"
                             else "daily_loss_state_not_persisted")
        return result

    def _latch(self, reason: str, from_ms: int = 0) -> None:
        if self._state["latch_reason"] == "loss":
            return                                               # un blocco per perdita non si declassa mai
        self._state["halt_latched"] = True
        self._state["latch_reason"] = reason
        if reason == "unverified":
            self._state["audit_from_ms"] = from_ms

    def _reconcile(self, now_ms: int, start: int) -> None:
        """Porta lo stato in memoria al giorno corrente dimostrando la continuita' (vedi docstring di classe)."""
        st, trust = self._state, self._trust
        same_day = trust in ("v2", "legacy") and st["day_start_ms"] == start
        if trust in ("v2", "legacy") and (st["day_start_ms"] > start or (trust == "v2" and st["checked_through_ms"] > now_ms)):
            keep_loss = same_day and st["latch_reason"] == "loss"
            self._state = self._blank(start)                     # orologio indietro: niente prova di continuita'
            self._latch("loss" if keep_loss else "unverified", start)   # un blocco per perdita resta tale
            self._trust = "v2"
            return
        if same_day and st["halt_latched"] and st["latch_reason"] == "loss":
            self._trust = "v2"
            return                                               # gia' bloccato per perdita: nulla da dimostrare
        if (same_day and trust == "v2" and not st["halt_latched"]
                and now_ms - st["checked_through_ms"] <= CONTINUITY_MS):
            return                                               # continuita' dimostrata dal disco o dalla memoria
        if same_day and st["halt_latched"] and st["latch_reason"] == "unverified":
            from_ms = st["audit_from_ms"]
            if now_ms - self._last_audit_try < AUDIT_RETRY_MS and self._last_audit_try >= 0:
                return
        else:
            from_ms = st["checked_through_ms"] if same_day and trust == "v2" else start
            if not same_day:
                self._state = self._blank(start)
        self._trust = "v2"
        self._last_audit_try = now_ms
        try:
            if self._audit is None:
                raise ValueError("daily_loss_audit_unavailable")
            peak = self._audit(from_ms, now_ms)
            if type(peak) is not Decimal or not peak.is_finite() or peak < 0:
                raise ValueError("daily_loss_audit_invalid")
        except Exception:
            self._latch("unverified", from_ms)
            return
        if peak >= self._halt:
            self._state["halt_latched"], self._state["latch_reason"] = False, ""   # consente il passaggio a «loss»
            self._latch("loss")
        elif self._state["latch_reason"] == "unverified":
            self._state["halt_latched"], self._state["latch_reason"] = False, ""   # dimostrato: nessuno stop mancato
            self._state["audit_from_ms"] = 0

    def __call__(self, now_ms: int) -> DailyLoss:
        if type(now_ms) is not int or now_ms <= 0:
            raise ValueError("invalid_now")
        minute = now_ms // MINUTE_MS
        if self._last is not None and minute == self._minute:
            return self._last
        result = self._evaluate(now_ms)                         # se solleva, niente cache: il direttore va in «fermo»
        start = day_start_ms(now_ms)
        self._reconcile(now_ms, start)
        if result.level == "halt":
            self._latch("loss")                                  # anche «unverified» -> «loss»
        self._state["checked_through_ms"] = now_ms
        self._save()
        if self._state["halt_latched"] and result.level != "halt":
            result = DailyLoss("halt", result.loss_fraction, result.loss_usd, result.day_start_ms)
        if result.level == "warn":                               # se salta dritto a halt, un avviso «si ferma al 50 %» sarebbe falso
            self._notify("warn_sent", (
                f"⚠️ Brain PAPER: perdita di oggi al {pct_text(result.loss_fraction)}% del portafoglio "
                f"(avviso al {pct_text(self._warn)}%). Si ferma da solo al {pct_text(self._halt)}%: "
                f"puoi fermarlo tu prima."))
        if result.level == "halt" and self._state["latch_reason"] == "unverified":
            self._notify("unverified_sent", (
                "🛑 Brain PAPER: non riesco a dimostrare che oggi la perdita non abbia raggiunto lo stop "
                "(stato del freno mancante o non verificabile). Nuove aperture sospese finche' la verifica non riesce "
                "o fino a mezzanotte UTC; uscite e stop continuano."))
        elif result.level == "halt":
            self._notify("halt_sent", (
                f"🛑 Brain PAPER: raggiunta la perdita massima di oggi ({pct_text(result.loss_fraction)}%). "
                f"Nessuna nuova apertura fino a mezzanotte UTC. Le posizioni aperte restano protette dai loro stop "
                f"e puoi chiuderle a mano."))
        self._minute, self._last = minute, result
        return result
