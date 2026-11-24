"""Notifiche Telegram del Brain unico PAPER (24/11/2026): solo informative, lette dal journal.

Stesso bot e stesse variabili dei vecchi Falco e Toro (``TELEGRAM_BOT_TOKEN``, ``TELEGRAM_CHAT_ID`` nell'ambiente del
runner; invio con ``alerts.telegram_sender``). Si notifica SOLO cio' che e' registrato nel journal della run:
aperture, chiusure totali e parziali, stop (iniziale, a pareggio, trailing, stretto dal Brain), chiusure manuali e del
Brain, cambi di modalita' del Guardian, report giornaliero con salvadanaio a mezzanotte (ora italiana).

Le due quote di un'apertura producono UN messaggio di apertura; le chiusure dello stesso trade con lo stesso motivo nello
stesso giro di lettura producono UN messaggio (parziale se resta aperta un'altra quota). Nessun comando remoto: questo
modulo non scrive nel journal e non apre ne' chiude nulla. Gira in un thread proprio: un errore o un Telegram lento non
ferma mai il runner ne' le uscite. Lo stato (ultimo evento letto, ultimo report, ultima modalita') sta in
``telegram_state.json`` nella cartella della run: un riavvio non ripete i messaggi; al primo avvio non si recupera lo
storico (si parte dall'ultimo evento).
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

STATE_FILE = "telegram_state.json"
MODES = {"NORMAL": "ATTIVO", "SELECTIVE": "SELETTIVO", "PROTECTED": "PROTEZIONE", "LOCKED": "BLOCCATO"}
REASONS = {"take_profit": "take profit", "manual": "chiusura manuale (operatore)", "brain_close": "chiusura decisa dal Brain",
           "timeout": "durata massima", "liquidation": "liquidazione"}
STOPS = {None: "stop loss", "initial": "stop loss", "break_even": "stop a pareggio", "trailing": "trailing stop",
         "protect": "protezione profitti", "brain": "stop stretto dal Brain"}


def _d(v) -> Optional[Decimal]:
    try:
        x = Decimal(str(v))
        return x if x.is_finite() else None
    except Exception:
        return None


def _usd(v) -> str:
    x = _d(v)
    return "—" if x is None else f"{x:+.2f} USDT" if x != 0 else "0.00 USDT"


def _px(v) -> str:
    x = _d(v)
    return "—" if x is None else f"{x.normalize():f}"


def _side(s) -> str:
    return "LONG" if s == 1 else "SHORT" if s == -1 else "?"


class JournalNotifier:
    def __init__(self, *, journal, run_id: str, data_dir: Path, send: Callable[[str], bool], initial_equity: Decimal,
                 piggy_policy=None, tz: str = "Europe/Rome", default_tp_r: Optional[Decimal] = None):
        self.journal, self.run_id, self.data_dir, self.send = journal, run_id, Path(data_dir), send
        self.default_tp_r = default_tp_r                 # TP della politica della run (quota senza TP proprio)
        self.initial_equity, self.piggy, self.tz = initial_equity, piggy_policy, ZoneInfo(tz)

    # ------------------------------------------------------------------ stato
    def _load(self) -> Optional[dict]:
        try:
            st = json.loads((self.data_dir / STATE_FILE).read_text())
            return st if isinstance(st, dict) and type(st.get("seq")) is int else None
        except (OSError, ValueError):
            return None

    def _save(self, st: dict) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.data_dir, prefix=".telegram_state.")
        with os.fdopen(fd, "w") as f:
            json.dump(st, f)
        os.replace(tmp, self.data_dir / STATE_FILE)

    # ------------------------------------------------------------------ messaggi
    def poll(self, now_ms: int) -> list[str]:
        """Legge gli eventi nuovi, invia i messaggi, salva lo stato. Restituisce i testi (per i test)."""
        rows = self.journal.list_run("brain", self.run_id)
        top = max((r.seq for r in rows), default=0)
        st = self._load()
        today = datetime.fromtimestamp(now_ms / 1000, self.tz).date().isoformat()
        if st is None:                                   # primo avvio: niente storico, un solo messaggio
            st = {"seq": top, "report_day": today, "guardian": None}
            self._save(st)
            msgs = ["🧠 Brain unico PAPER: notifiche Telegram attive (solo informative, nessun comando)."]
            for m in msgs:
                self.send(m)
            return msgs
        new = [r.event for r in rows if r.seq > st["seq"]]
        all_events = [r.event for r in rows]
        msgs = (self._strategy(new) + self._late(new) + self._opens(new) + self._scaling(new) + self._closes(new, all_events)
                + self._guardian(new, st))
        if today > st.get("report_day", today):
            msgs.append(self._report(st["report_day"], all_events, now_ms))
            st["report_day"] = today
        st["seq"] = top
        self._save(st)                                   # prima di inviare: un errore di rete non ripete i messaggi
        for m in msgs:
            try:
                self.send(m)
            except Exception:
                pass
        return msgs

    def _opens(self, new) -> list[str]:
        groups: dict = {}
        for e in new:
            if e.kind == "paper_open":
                p = e.payload
                groups.setdefault(p.get("decision_event_id") or p.get("position_id"), []).append(p)
        out = []
        for legs in groups.values():
            p = legs[0]
            margin = sum((_d(x.get("margin_used")) or Decimal(0) for x in legs), Decimal(0))
            fill, stop = _d(p.get("fill_price")), _d(p.get("stop_price"))
            tps = []
            if fill is not None and stop is not None:
                for x in legs:
                    r = _d(x.get("take_profit_r")) if x.get("take_profit_r") is not None else self.default_tp_r
                    if r is not None:
                        tp = fill + (fill - stop).copy_abs() * r * (1 if p.get("side") == 1 else -1)
                        tps.append(f"TP {r.normalize():f}R a {tp.normalize():f}")
            out.append(f"🟢 Apertura {_side(p.get('side'))} {str(p.get('symbol', '?')).replace('USDT', '')} · "
                       + (f"{len(legs)} quote · " if len(legs) > 1 else "") + f"entrata {_px(p.get('fill_price'))} · "
                       f"stop {_px(p.get('stop_price'))} · leva {p.get('leverage')}× · margine {margin:.2f} USDT"
                       + (f" · {', '.join(tps)}" if tps else ""))
        return out

    @staticmethod
    def _late(new) -> list[str]:
        """Uscita rilevata in ritardo (riavvio o candela corretta dopo): anomalia sempre segnalata."""
        out = []
        for e in new:
            p = e.payload if isinstance(e.payload, dict) else {}
            if e.kind == "exit_late":
                bar = datetime.fromtimestamp(int(p.get("signal_bar_ms", 0)) / 1000, timezone.utc).strftime("%H:%M")
                out.append(f"⚠️ Uscita rilevata in ritardo: {str(p.get('symbol', '?')).replace('USDT', '')} · "
                           f"{REASONS.get(p.get('reason'), str(p.get('reason')))} toccato alle {bar} UTC, elaborato "
                           f"{int(p.get('delay_ms', 0)) // 60_000} min dopo · prezzo teorico {_px(p.get('theoretical_price'))}"
                           f" · ultimo prezzo {_px(p.get('market_price'))}")
        return out

    @staticmethod
    def _strategy(new) -> list[str]:
        """Brain Live Evolution: un messaggio per ogni cambio di strategia approvato (vale per le nuove aperture)."""
        out = []
        for e in new:
            p = e.payload if isinstance(e.payload, dict) else {}
            if e.kind == "strategy_switch":
                out.append(f"🧬 Strategia {p.get('from')} → {p.get('to')}" + (" (rollback)" if p.get("rollback") else "")
                           + " per le NUOVE aperture dal prossimo giro; le posizioni aperte completano la loro versione."
                           + (f" Motivo: {str(p.get('reason'))[:200]}" if p.get("reason") else ""))
        return out

    def _scaling(self, new) -> list[str]:
        """Posizione unica (24/11): secondo ingresso e chiusure parziali, un messaggio per evento registrato."""
        out = []
        for e in new:
            p = e.payload if isinstance(e.payload, dict) else {}
            sym = str(p.get("symbol", "?")).replace("USDT", "")
            if e.kind == "paper_add":
                out.append(f"➕ Secondo ingresso {_side(p.get('side'))} {sym} a {_px(p.get('fill_price'))} · "
                           f"prezzo medio {_px(p.get('new_avg_price'))} · stop invariato {_px(p.get('stop_price'))}")
            elif e.kind == "paper_reduce":
                what = REASONS.get(p.get("reason"), str(p.get("reason")))
                out.append(f"✂️ Chiusura parziale {_side(p.get('side'))} {sym} · {what} · uscita {_px(p.get('exit_price'))}"
                           f" · P&L netto {_usd(p.get('realized_pnl'))} · resta aperta la parte residua")
        return out

    def _closes(self, new, all_events) -> list[str]:
        open_by_group: dict = {}
        closed_ids = {e.payload.get("position_id") for e in all_events if e.kind == "paper_close"}
        for e in all_events:
            if e.kind == "paper_open" and e.payload.get("position_id") not in closed_ids:
                g = e.payload.get("decision_event_id") or e.payload.get("position_id")
                open_by_group[g] = open_by_group.get(g, 0) + 1
        groups: dict = {}
        for e in new:
            if e.kind == "paper_close":
                p = e.payload
                key = (p.get("decision_event_id") or p.get("position_id"), p.get("reason"), p.get("stop_kind"))
                groups.setdefault(key, []).append(p)
        out = []
        for (g, reason, kind), legs in groups.items():
            p = legs[0]
            pnl = sum((_d(x.get("realized_pnl")) or Decimal(0) for x in legs), Decimal(0))
            what = STOPS.get(kind, "stop loss") if reason == "stop" else REASONS.get(reason, str(reason))
            partial = open_by_group.get(g, 0) > 0
            rest = any(e.kind == "paper_reduce" and e.payload.get("position_id") == p.get("position_id")
                       for e in all_events)
            icon = "✅" if pnl > 0 else "🛑" if reason == "stop" else "⚪"
            label = "parziale" if partial else "del residuo" if rest else "totale"
            out.append(f"{icon} Chiusura {label} {_side(p.get('side'))} "
                       f"{str(p.get('symbol', '?')).replace('USDT', '')} · {what} · uscita {_px(p.get('exit_price'))} · "
                       f"P&L netto {_usd(pnl)}" + (" · resta aperta l'altra quota" if partial else ""))
        return out

    def _guardian(self, new, st) -> list[str]:
        out = []
        for e in new:
            if e.kind != "guardian_state":
                continue
            state = e.payload.get("state")
            if state in MODES and state != st.get("guardian"):
                if st.get("guardian") is not None:
                    reasons = ", ".join(str(r) for r in (e.payload.get("reasons") or [])[:3])
                    out.append(f"🛡️ Guardian: modalità {MODES[state]}" + (f" ({reasons})" if reasons else ""))
                st["guardian"] = state
        return out

    def _report(self, day: str, all_events, now_ms: int) -> str:
        start = datetime.fromisoformat(day).replace(tzinfo=self.tz)
        lo, hi = int(start.timestamp() * 1000), int((start + timedelta(days=1)).timestamp() * 1000)
        closes = [e for e in all_events if e.kind == "paper_close"]
        day_pnl = sum((_d(e.payload.get("realized_pnl")) or Decimal(0) for e in closes if lo <= e.occurred_at_ms < hi),
                      Decimal(0))
        trades = len({e.payload.get("decision_event_id") or e.payload.get("position_id") for e in closes
                      if lo <= e.occurred_at_ms < hi})
        realized = sum((_d(e.payload.get("realized_pnl")) or Decimal(0) for e in closes), Decimal(0))
        line = (f"📊 Report {day}: P&L netto del giorno {_usd(day_pnl)} · trade chiusi {trades} · "
                f"equity contabile {self.initial_equity + realized:.2f} USDT")
        if self.piggy is not None:
            from backend.v3.dashboard import build_summary
            from backend.v3.unico import piggy_from_closed
            pg = piggy_from_closed(build_summary(self.journal, "brain", self.run_id).closed_trades,
                                   initial_equity=self.initial_equity, now_ms=now_ms, policy=self.piggy)
            line += f" · salvadanaio {pg.total:.2f} USDT · capitale operativo {pg.operating_equity:.2f} USDT"
        return line


def start_thread(make_notifier: Callable[[], JournalNotifier], clock: Callable[[], int], *, every_s: float = 20.0,
                 stop: Optional[threading.Event] = None) -> threading.Thread:
    """Thread demone: legge e invia ogni ``every_s`` secondi. Qualunque errore viene ignorato (solo informativo)."""
    stop = stop or threading.Event()

    def loop():
        try:
            notifier = make_notifier()                   # journal aperto nel thread (connessione propria)
        except Exception:
            return
        while not stop.is_set():
            try:
                notifier.poll(clock())
            except Exception:
                pass
            stop.wait(every_s)
    t = threading.Thread(target=loop, name="telegram-feed", daemon=True)
    t.start()
    return t
