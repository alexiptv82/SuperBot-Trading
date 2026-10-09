"""Sala segnali: ciclo di paper trading ogni 15 minuti.

`python -m desk.cli once|loop|report|health --data-dir DIR`
Solo dati pubblici e paper: nessun ordine reale. La chiave Anthropic (se c'e') serve solo per le decisioni.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

import numpy as np

from desk import brain, signals
from desk.engine import Limits, PaperAccount
from rule_pool import runner as rp

SYMBOLS = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "LINK", "AVAX", "LTC", "ADA"]
PAIR = "{}/USDT:USDT"
M15, HOUR, DAY = rp.M15, 3_600_000, 86_400_000
BACKFILL_DAYS = 45
ENTRY_SCORE = 50                     # sotto questo punteggio un candidato non merita nemmeno la chiamata
RULES_ENTRY = 70                     # soglia d'ingresso della modalita' a sole regole
COOLDOWN_MS = HOUR
REVIEW_MS = HOUR
REPORT_HOUR_UTC = 21
RUN_OFFSET_MS = 30_000


# ---------------- stato su disco
def load_state(d: str) -> dict:
    p = os.path.join(d, "state.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {"main": PaperAccount(Limits(), "main").to_dict(), "ctl": PaperAccount(Limits(), "control").to_dict(),
            "last_bar": {}, "cool": {}, "headlines": {"t": 0, "items": []}, "budget": {}, "rng_n": 0,
            "report_day": "", "lessons_day": "", "started_ms": int(time.time() * 1000), "stats": {}}


def save_state(d: str, st: dict) -> None:
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, "state.json.tmp")
    with open(tmp, "w") as f:
        json.dump(st, f)
    os.replace(tmp, os.path.join(d, "state.json"))


def log(d: str, name: str, rec: dict) -> None:
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def utc_day(ms: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))


def hhmm(ms: int) -> str:
    return time.strftime("%d/%m %H:%M", time.gmtime(ms / 1000))


# ---------------- ciclo
def fmt_close(rec: dict) -> str:
    side = "LONG" if rec["side"] == 1 else "SHORT"
    return (f"CHIUSO {rec['symbol']} {side} {rec['leverage']}x: {rec['net']:+.2f}$ ({rec['why']}). "
            f"{rec['reason'][:100]}")


def snapshot(main: PaperAccount, prices: dict) -> dict:
    return {"equity": main.equity(prices), "cash": main.cash, "margin": main.margin_in_use(),
            "n_open": len(main.positions), "day_pnl": main.equity(prices) - main.day_start_equity,
            "halt": main.halted(prices)}


def run_cycle(d: str, st: dict, store, fetch, now_ms: int, notify=None, call=brain.call_claude,
              news=brain.fetch_headlines) -> dict:
    main, ctl = PaperAccount.from_dict(st["main"]), PaperAccount.from_dict(st["ctl"])
    notes = []
    say = (lambda m: (notes.append(m), notify(m) if notify else None))
    back = (now_ms - BACKFILL_DAYS * DAY) // signals.H4 * signals.H4
    limit = rp.last_closed_open(now_ms)
    arrays, prices, errors = {}, {}, {}
    for s in SYMBOLS:
        sym = PAIR.format(s)
        try:
            store.update(sym, fetch, now_ms, back)
        except Exception as exc:  # noqa: BLE001
            errors[s] = f"aggiornamento fallito ({type(exc).__name__})"
        arr = store.load(sym)
        if len(arr) < 1500 or limit - int(arr[-1, 0]) > rp.MAX_STALE_MS:
            errors.setdefault(s, "dati insufficienti o vecchi")
            continue
        arrays[s], prices[s] = arr, float(arr[-1, 4])
    # 1) candele nuove sulle posizioni (stop, obiettivi, liquidazioni)
    for s, arr in arrays.items():
        last = st["last_bar"].get(s)
        if last is None:
            st["last_bar"][s] = int(arr[-1, 0])               # primo avvio: niente storia da rigiocare
            continue
        for row in arr[arr[:, 0] > last]:
            t = int(row[0])
            for acc in (main, ctl):
                rec = acc.on_bar(s, t, row[1], row[2], row[3], row[4], M15)
                if rec:
                    log(d, "trades.jsonl", rec)
                    if acc is main:
                        say(fmt_close(rec))
                        st["cool"][s] = rec["close_ms"] + COOLDOWN_MS
                        ctl.close(s, float(row[4]), rec["close_ms"], "specchio del bot")
        st["last_bar"][s] = int(arr[-1, 0])
    day = utc_day(now_ms)
    main.roll_day(day, prices)
    ctl.roll_day(day, prices)
    # 2) letture tecniche
    readings = [r for s in SYMBOLS if s in arrays for r in [signals.read_symbol(s, arrays[s])] if r]
    by = {r.symbol: r for r in readings}
    positions = []
    for s, p in main.positions.items():
        r = by.get(s)
        px = prices.get(s, p.entry)
        positions.append({"symbol": s, "side": p.side, "leverage": p.leverage, "margin": p.margin, "entry": p.entry,
                          "price": px, "pnl": p.side * (px - p.entry) * p.qty, "sl": p.sl,
                          "hours": (now_ms - p.open_ms) / HOUR, "reason": p.reason,
                          "score_now": (r.long_score if p.side == 1 else r.short_score) if r else 0})
    snap = snapshot(main, prices)
    # 3) serve decidere?
    due = []
    for p in main.positions.values():
        r = by.get(p.symbol)
        moved = abs(prices.get(p.symbol, p.entry) / (p.review_price or p.entry) - 1)
        if now_ms - p.last_review_ms >= REVIEW_MS or (r and moved >= 1.5 * r.atr_pct):
            due.append(p.symbol)
    slots = main.limits.max_open - len(main.positions)
    cands = [r for r in readings if r.symbol not in main.positions and r.side != 0 and r.score >= ENTRY_SCORE
             and st["cool"].get(r.symbol, 0) <= now_ms] if slots > 0 and not snap["halt"] else []
    # scansione oraria: se ci sono posti liberi ma nessun candidato forte, Claude guarda comunque le 4 coppie migliori
    scan = []
    if slots > 0 and not cands and not snap["halt"] and now_ms - st.get("last_scan", 0) >= HOUR:
        scan = sorted([r for r in readings if r.symbol not in main.positions and st["cool"].get(r.symbol, 0) <= now_ms],
                      key=lambda r: -r.score)[:4]
    decisions, source, cost = [], "nessuna", 0.0
    if due or cands or scan:
        if scan:
            st["last_scan"] = now_ms
        view = [r for r in readings if r.symbol in due or r in cands or r in scan]
        if brain.can_call(st, day):
            if now_ms - st["headlines"]["t"] > HOUR:
                items = news()
                st["headlines"] = {"t": now_ms, "items": items or st["headlines"]["items"]}
            lessons = open(os.path.join(d, "lessons.md")).read() if os.path.exists(os.path.join(d, "lessons.md")) else ""
            prompt = brain.build_prompt(snap, view, positions, st["headlines"]["items"], lessons)
            try:
                text, usage = call(brain.SYSTEM, prompt)
                cost = brain.record_spend(st, day, usage)
                parsed = brain.parse_decisions(text)
                if parsed is None:
                    raise RuntimeError("risposta illeggibile")
                decisions, source = parsed["decisions"], "claude"
                log(d, "decisions.jsonl", {"t": now_ms, "source": source, "cost": round(cost, 5),
                                           "note": parsed["note"], "decisions": decisions})
            except Exception as exc:  # noqa: BLE001
                log(d, "decisions.jsonl", {"t": now_ms, "source": "errore", "error": str(exc)[:120]})
                source = "errore"
        if source != "claude" and os.getenv("DESK_RULES_ONLY") == "1":
            decisions = brain.rules_decisions(view, positions, set(main.positions), RULES_ENTRY)
            source = "regole"
        elif source != "claude":
            # senza Claude (chiave assente, tetto finito, errore): solo gestione del rischio, nessun nuovo ingresso
            decisions = [x for x in brain.rules_decisions(view, positions, set(main.positions), 999)
                         if x["action"] == "close"]
    # 4) applica le decisioni
    rng = random.Random(f"{st.get('rng_n', 0)}-{now_ms}")
    for dec in decisions:
        s, act = dec["symbol"], dec["action"]
        if s not in prices:
            continue
        px = prices[s]
        if act == "close" and s in main.positions:
            rec = main.close(s, px, now_ms, "chiusura decisa")
            if rec:
                rec["reason"] = f"{rec['reason'][:120]} -> chiusura: {dec['reason']}"[:300]
                log(d, "trades.jsonl", rec)
                say(fmt_close(rec))
                ctl.close(s, px, now_ms, "specchio del bot")
                st["cool"][s] = now_ms + COOLDOWN_MS
        elif act in ("open_long", "open_short") and s not in main.positions:
            r = by.get(s)
            side = 1 if act == "open_long" else -1
            sl_pct = dec["stop_loss_pct"] if 0.003 <= dec["stop_loss_pct"] <= 0.05 else (r.sl_pct if r else 0.01)
            tp_pct = dec["take_profit_pct"] if dec["take_profit_pct"] >= sl_pct else (r.tp_pct if r else sl_pct * 1.7)
            pos, msg = main.open(s, side, dec["margin_usd"], dec["leverage"], px, px * (1 - side * sl_pct),
                                 px * (1 + side * tp_pct), now_ms, prices, dec["confidence"], dec["reason"], source)
            log(d, "decisions.jsonl", {"t": now_ms, "apply": act, "symbol": s, "ok": pos is not None, "msg": msg})
            st["cool"][s] = now_ms + (COOLDOWN_MS if pos is None else 0)
            if pos:
                st["rng_n"] = st.get("rng_n", 0) + 1
                cside = rng.choice([1, -1])
                ctl.open(s, cside, pos.margin, pos.leverage, px, px * (1 - cside * sl_pct), px * (1 + cside * tp_pct),
                         now_ms, prices, 0, "controllo casuale", "caso")
                say(f"APERTO {s} {'LONG' if side == 1 else 'SHORT'} {pos.leverage}x margine {pos.margin:.0f}$ "
                    f"a {px:.5g}, stop {pos.sl:.5g}, confidenza {pos.confidence} [{source}]: {dec['reason'][:110]}")
        elif act in ("skip", "hold"):
            if s in main.positions:
                p = main.positions[s]
                p.last_review_ms, p.review_price = now_ms, px
            else:
                st["cool"][s] = now_ms + COOLDOWN_MS
    for p in main.positions.values():
        if p.symbol in due:
            p.last_review_ms, p.review_price = now_ms, prices.get(p.symbol, p.entry)
    st["main"], st["ctl"] = main.to_dict(), ctl.to_dict()
    st["stats"] = {"last_cycle_ms": now_ms, "source": source, "errors": errors}
    # 5) riepilogo serale + appunti
    if (time.gmtime(now_ms / 1000).tm_hour >= REPORT_HOUR_UTC and st.get("report_day") != day):
        st["report_day"] = day
        if notify:
            notify(render_report(st, prices, now_ms))
        maybe_lessons(d, st, day, call)
    st["last_ok_ms"] = now_ms
    return {"notes": notes, "errors": errors, "decisions": decisions, "source": source, "cost": cost}


def maybe_lessons(d: str, st: dict, day: str, call=brain.call_claude) -> None:
    if st.get("lessons_day") == day or not brain.can_call(st, day, brain.DAILY_CAP + 0.0):
        return
    today = [t for t in st["main"]["closed"] if utc_day(t["close_ms"]) == day]
    if not today:
        return
    st["lessons_day"] = day
    brief = "\n".join(f"{t['symbol']} {'L' if t['side'] == 1 else 'S'} {t['leverage']}x conf {t['confidence']} "
                      f"{t['net']:+.2f}$ ({t['why']}): {t['reason'][:90]}" for t in today[-12:])
    try:
        text, usage = call("Sei un trader che rilegge i propri trade paper per migliorare. Scrivi al massimo 4 appunti "
                           "brevi e concreti (una riga ciascuno) su cosa ripetere o evitare. Niente premesse.",
                           f"Trade chiusi oggi:\n{brief}", 300)
        brain.record_spend(st, day, usage)
        with open(os.path.join(d, "lessons.md"), "a") as f:
            f.write(f"\n[{day}]\n{text.strip()[:700]}\n")
    except Exception:  # noqa: BLE001
        pass


def stats_of(closed: list) -> str:
    if not closed:
        return "0 trade"
    w = sum(1 for t in closed if t["net"] > 0)
    return f"{len(closed)} trade, {w} in profitto, netto {sum(t['net'] for t in closed):+.2f}$"


def render_report(st: dict, prices: dict, now_ms: int) -> str:
    main, ctl = PaperAccount.from_dict(st["main"]), PaperAccount.from_dict(st["ctl"])
    day = utc_day(now_ms)
    eq, ceq = main.equity(prices), ctl.equity(prices)
    today = [t for t in main.closed if utc_day(t["close_ms"]) == day]
    b = st.get("budget", {})
    lines = [f"Sala segnali - riepilogo {day}",
             f"Capitale: {eq:.2f}$ ({eq - main.limits.start_equity:+.2f}$ dall'inizio, oggi {eq - main.day_start_equity:+.2f}$)",
             f"Controllo a caso (stesse dimensioni, lato casuale): {ceq:.2f}$ ({ceq - ctl.limits.start_equity:+.2f}$)",
             f"Oggi: {stats_of(today)}. In totale: {stats_of(main.closed)}",
             f"Posizioni aperte: " + (", ".join(f"{p.symbol} {'L' if p.side == 1 else 'S'} {p.leverage}x" for p in main.positions.values()) or "nessuna")]
    h = main.halted(prices)
    if h:
        lines.append(f"ATTENZIONE: {h}")
    lines.append(f"Spesa Claude oggi {b.get('spent', 0):.3f}$ su tetto {brain.DAILY_CAP:.2f}$ ({b.get('calls', 0)} chiamate); "
                 f"totale {b.get('total_spent', 0):.2f}$")
    return "\n".join(lines)


# ---------------- loop e salute
def next_run_ms(now_ms: int) -> int:
    return (now_ms // M15 + 1) * M15 + RUN_OFFSET_MS


def health(st: dict | None, now_ms: int) -> tuple:
    if st is None:
        return False, "nessuno stato"
    last = st.get("last_ok_ms")
    if last is not None:
        age = now_ms - int(last)
        return age <= 45 * 60_000, f"ultimo ciclo riuscito {age // 60_000} minuti fa"
    if now_ms - st.get("started_ms", 0) <= 60 * 60_000:
        return True, "avvio in corso"
    return False, "nessun ciclo riuscito"


def iteration(d: str, notify, fetch=rp.fetch_bitget, now_ms: int | None = None, call=brain.call_claude) -> dict | None:
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    try:
        st = load_state(d)
        store = rp.CandleStore(os.path.join(d, "candles"))
        res = run_cycle(d, st, store, fetch, now_ms, notify, call)
        save_state(d, st)
        m = PaperAccount.from_dict(st["main"])
        px = {s: float(store.load(PAIR.format(s))[-1, 4]) for s in SYMBOLS if len(store.load(PAIR.format(s)))}
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now_ms / 1000))}Z] ciclo ok; capitale "
              f"{m.equity(px):.2f}$; aperte {len(m.positions)}; fonte={res['source']}; spesa oggi "
              f"{st['budget'].get('spent', 0):.3f}$; errori={res['errors'] or 'no'}", flush=True)
        return res
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE ciclo fallito: {type(exc).__name__}: {str(exc)[:150]}", flush=True)
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["once", "loop", "report", "health"])
    ap.add_argument("--data-dir", default=os.getenv("DESK_DATA_DIR", "data/desk"))
    ap.add_argument("--no-telegram", action="store_true")
    a = ap.parse_args(argv)
    d = a.data_dir
    now = int(time.time() * 1000)
    if a.command == "health":
        p = os.path.join(d, "state.json")
        ok, msg = health(json.load(open(p)) if os.path.exists(p) else None, now)
        print(("SANO: " if ok else "NON SANO: ") + msg)
        return 0 if ok else 1
    if a.command == "report":
        st = load_state(d)
        store = rp.CandleStore(os.path.join(d, "candles"))
        px = {s: float(store.load(PAIR.format(s))[-1, 4]) for s in SYMBOLS if len(store.load(PAIR.format(s)))}
        print(render_report(st, px, now))
        return 0
    notify = None if a.no_telegram else rp.telegram_sender()
    print(f"sala segnali avviata; telegram={'si' if notify else 'no'}; claude={'si' if os.getenv('ANTHROPIC_API_KEY') else 'NO (solo gestione rischio)'}; "
          f"dati in {d}", flush=True)
    if a.command == "once":
        return 0 if iteration(d, notify) is not None else 1
    while True:
        iteration(d, notify)
        n = int(time.time() * 1000)
        time.sleep(max(1.0, (next_run_ms(n) - n) / 1000.0))


if __name__ == "__main__":
    sys.exit(main())
