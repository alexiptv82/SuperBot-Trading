"""Lettura dei portafogli desk (Hawk / Bull) per l'app: stato, trade, performance, diario, run archiviate.

Solo libreria standard, nessuna dipendenza da FastAPI: cosi' si puo' testare da sola.
Il bot (container superbot-desk-*) scrive nella sua cartella dati; qui si LEGGE e basta, tranne
i piccoli file-comando (pause.flag, reset.flag, budget_reset.flag, reset_portfolio.flag) con cui
l'app parla al bot.

File letti dalla cartella dati:
  state_v2.json        conto (main), budget Claude, ultimi prezzi, ultimo comando eseguito
  heartbeat.json       battito del bot: vivo?, ultimo/prossimo ciclo, versione, errori
  trade_history.jsonl  un trade chiuso per riga. E' lo storico PERMANENTE, cioe' il cervello del bot: il reset del
                       portafoglio non lo cancella. L'app mostra solo i trade della run attuale (dopo run_started_ms)
  archive/*/summary.json  run precedenti archiviate dal reset
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

HEARTBEAT_FRESH_S = 300        # battito piu' vecchio di 5 minuti = bot offline
STATE_FRESH_S = 75 * 60        # ripiego per bot vecchi senza heartbeat
DEFAULT_START_EQUITY = 1000.0


# ── lettura file ─────────────────────────────────────────────────────────────
def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def read_state(data_dir: str) -> dict:
    return _read_json(os.path.join(data_dir, "state_v2.json"))


def read_heartbeat(data_dir: str, now: Optional[float] = None) -> Optional[dict]:
    hb = _read_json(os.path.join(data_dir, "heartbeat.json"))
    if not hb or "ts" not in hb:
        return None
    now = time.time() if now is None else now
    try:
        hb["age_s"] = max(0.0, now - float(hb["ts"]))
    except (TypeError, ValueError):
        return None
    return hb


def read_history(data_dir: str, last_n: Optional[int] = None) -> list:
    """Trade chiusi dallo storico JSONL. Le righe che non sono un oggetto (formati vecchi) o non
    sono JSON valido si saltano: una riga rovinata non deve far sparire tutto lo storico."""
    try:
        with open(os.path.join(data_dir, "trade_history.jsonl")) as f:
            lines = f.readlines()
    except Exception:
        return []
    if last_n:
        lines = lines[-last_n:]
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict) and rec.get("net") is not None:
            out.append(rec)
    return out


def _ms(value) -> int:
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return 0
    return v if v > 0 else 0


def closed_records(data_dir: str, state: Optional[dict] = None, last_n: Optional[int] = None) -> list:
    """Trade chiusi della run ATTUALE.

    Lo storico su disco e' permanente (e' il cervello del bot, il reset del portafoglio non lo cancella):
    dopo un reset contiene anche le run vecchie, quindi qui si tengono solo i trade chiusi dal momento in cui
    e' partita la run attuale (run_started_ms nello stato). Senza quel campo (bot mai azzerato) vale tutto.
    Se lo storico manca, si ripiega sui trade chiusi tenuti nello stato del conto."""
    state = read_state(data_dir) if state is None else state
    started = _ms(state.get("run_started_ms"))
    if started:
        recs = [r for r in read_history(data_dir) if _ms(r.get("close_ms")) >= started]
        if last_n:
            recs = recs[-last_n:]
    else:
        recs = read_history(data_dir, last_n)
    if recs:
        return recs
    closed = (state.get("main") or {}).get("closed")
    if isinstance(closed, list):
        recs = [c for c in closed if isinstance(c, dict) and c.get("net") is not None]
        return recs[-last_n:] if last_n else recs
    return []


def read_lessons(data_dir: str) -> str:
    for fname in ("lessons.md", "errors.md"):
        try:
            with open(os.path.join(data_dir, fname)) as f:
                return f.read()
        except Exception:
            pass
    return ""


def pause_requested(data_dir: str) -> bool:
    return os.path.exists(os.path.join(data_dir, "pause.flag"))


def derive_mode(paused: bool, n_open: int) -> str:
    """running = lavora; draining = in pausa ma sta finendo le posizioni; paused = fermo e senza posizioni."""
    if not paused:
        return "running"
    return "draining" if n_open > 0 else "paused"


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _utc_day(ms) -> str:
    try:
        return datetime.fromtimestamp(float(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return "?"


# ── stato live ───────────────────────────────────────────────────────────────
def open_symbols(data_dir: str) -> list:
    """Simboli con posizione aperta (per sapere di quali prezzi live c'e' bisogno)."""
    return list(((read_state(data_dir).get("main") or {}).get("positions") or {}).keys())


def build_status(data_dir: str, portfolio: str, prices: Optional[dict] = None,
                 now: Optional[float] = None, daily_cap: Optional[float] = None) -> dict:
    now = time.time() if now is None else now
    prices = prices or {}
    state = read_state(data_dir)
    hb = read_heartbeat(data_dir, now)
    if not state:
        return {"available": False, "portfolio": portfolio,
                "bot_online": bool(hb and hb["age_s"] < HEARTBEAT_FRESH_S),
                "message": "Il bot non ha ancora salvato dati: appena parte il primo ciclo compaiono qui."}

    acc = state.get("main") or {}
    limits = acc.get("limits") or {}
    positions = acc.get("positions") or {}
    last_prices = state.get("last_prices") or {}
    start_equity = _f(limits.get("start_equity"), DEFAULT_START_EQUITY)
    cash = _f(acc.get("cash"))

    pos_list, margin_used, unrealized = [], 0.0, 0.0
    for sym, p in positions.items():
        entry, qty, side = _f(p.get("entry")), _f(p.get("qty")), int(p.get("side") or 0)
        margin = _f(p.get("total_margin", p.get("margin")))
        if prices.get(sym):
            price, src = _f(prices[sym]), "live"
        elif last_prices.get(sym):
            price, src = _f(last_prices[sym]), "bot"
        else:
            price, src = entry, "entry"
        pnl = side * (price - entry) * qty
        margin_used += margin
        unrealized += pnl
        pos_list.append({
            "symbol": sym, "side": side, "leverage": p.get("leverage"),
            "entry": entry, "entry_price": entry, "price": price, "price_source": src,
            "qty": qty, "quantity": qty, "margin": round(margin, 2),
            "pnl": round(pnl, 2), "pnl_pct": round(pnl / margin * 100, 2) if margin else 0.0,
            "sl": p.get("sl"), "tp": p.get("tp"), "liq": p.get("liq"),
            "trade_type": p.get("trade_type") or "medio", "dca_count": p.get("dca_count", 0),
            "dca_levels": p.get("dca_levels") or [], "open_ms": p.get("open_ms"),
            "confidence": p.get("confidence"), "source": p.get("source"),
            "reason": (p.get("reason") or "")[:200],
        })
    pos_list.sort(key=lambda x: x.get("open_ms") or 0)

    equity = cash + margin_used + unrealized
    day_start = _f(acc.get("day_start_equity"), start_equity)
    halt = ""
    if limits and equity <= _f(limits.get("kill_equity"), 0.0):
        halt = "capitale sotto la soglia minima"
    elif limits and day_start and equity <= day_start * (1 - _f(limits.get("daily_stop"), 0.0)):
        halt = "stop giornaliero raggiunto"

    paused = pause_requested(data_dir)
    n_open = len(positions)
    mode = derive_mode(paused, n_open)

    # il bot e' vivo? battito recente; per i bot vecchi senza battito, stato salvato di recente
    if hb is not None:
        online = hb["age_s"] < HEARTBEAT_FRESH_S
    else:
        try:
            online = now - os.path.getmtime(os.path.join(data_dir, "state_v2.json")) < STATE_FRESH_S
        except OSError:
            online = False

    # il budget e' giornaliero: se il giorno salvato non e' oggi, oggi non e' stato speso nulla
    budget = state.get("budget") or {}
    today = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")
    spent = _f(budget.get("spent")) if budget.get("day") == today else 0.0
    cap = daily_cap or _f((hb or {}).get("daily_cap_usd"), 0.0) or float(os.getenv("DESK_DAILY_CAP_USD", "0.70"))

    can_reset, reset_reason = True, ""
    if not paused:
        can_reset, reset_reason = False, "Metti prima il bot in pausa."
    elif n_open > 0:
        can_reset, reset_reason = False, f"Ci sono {n_open} posizioni ancora aperte: aspetta che si chiudano oppure usa Chiudi tutto."
    elif not reset_keeps_brain(hb):
        can_reset, reset_reason = False, RESET_OLD_BOT_MESSAGE

    from salvadanaio_view import build_view
    vault = build_view(state, hb, now)
    vault_balance = float(vault["balance"]) if vault.get("available") else 0.0
    total_equity = equity + vault_balance
    if vault.get("available") and not (hb and hb.get("reset_with_vault") is True):
        can_reset, reset_reason = False, "Aggiorna prima il bot: reset Salvadanaio manuale non ancora supportato."
    run_started = state.get("run_started_ms")
    return {
        "available": True, "portfolio": portfolio, "mode": "paper",
        "bot_mode": mode, "paused": paused, "draining": mode == "draining",
        "bot_online": online, "heartbeat_age_s": round(hb["age_s"]) if hb else None,
        "version": (hb or {}).get("version"), "params": (hb or {}).get("params"),
        "cycle": {
            "count": (hb or {}).get("cycles"), "running": bool((hb or {}).get("cycle_running")),
            "last_start_ms": (hb or {}).get("last_start_ms") or None,
            "last_end_ms": (hb or {}).get("last_end_ms") or None,
            "last_ok": (hb or {}).get("last_ok"), "last_error": (hb or {}).get("last_error") or "",
            "next_cycle_ms": (hb or {}).get("next_cycle_ms") or None,
        },
        "salvadanaio": vault, "total_equity": round(total_equity, 2),
        "cash": round(cash, 2), "margin_used": round(margin_used, 2),
        "unrealized_pnl": round(unrealized, 2), "equity": round(equity, 2),
        "start_equity": start_equity, "pnl_total": round(total_equity - start_equity, 2),
        "pnl_total_pct": round((total_equity - start_equity) / start_equity * 100, 2) if start_equity else 0.0,
        "day_pnl": round(equity - day_start, 2), "day": acc.get("day", ""),
        "open_positions": n_open, "positions": pos_list,
        "max_open": limits.get("max_open"), "max_margin_trade": limits.get("max_margin_trade"),
        "total_closed": len(closed_records(data_dir, state)),
        "halt": halt or None,
        "budget_spent_usd": round(spent, 4), "budget_daily_cap_usd": cap,
        "last_report_day": state.get("last_report_day", ""),
        "last_prices_ms": state.get("last_prices_ms"),
        "run_no": state.get("run_no", 1), "run_started_ms": run_started,
        "last_action": state.get("last_action"),
        "can_reset": can_reset, "reset_blocked_reason": reset_reason,
        "reset_pending": os.path.exists(os.path.join(data_dir, "reset_portfolio.flag")),
        "close_all_pending": os.path.exists(os.path.join(data_dir, "reset.flag")),
        "close_position_pending": close_pending(data_dir),
        "exec_mode": (hb or {}).get("exec_mode"),
        "can_close_position": can_close_position(read_heartbeat(data_dir)),
        # orari di trading e calendario macro: li calcola il bot, l'app mostra soltanto (assenti nei bot vecchi)
        "hours": (hb or {}).get("hours"),
        "macro": (hb or {}).get("macro"),
    }


# ── trade chiusi ─────────────────────────────────────────────────────────────
def normalize_trade(t: dict) -> dict:
    """Un record dello storico nel formato che l'app mostra. Gestisce i nomi dei campi di
    entrambe le versioni del bot (leverage/lev, trade_type/type)."""
    why = t.get("why")
    return {
        "id": t.get("id"), "symbol": t.get("symbol"), "side": t.get("side"),
        "entry_price": t.get("entry"), "exit_price": t.get("exit"),
        "leverage": t.get("leverage", t.get("lev")), "margin": t.get("margin"),
        "gross_pnl": t.get("gross"), "pnl": t.get("net"), "fees": t.get("fees"),
        "funding": t.get("funding"),
        "trade_type": t.get("trade_type", t.get("type")) or "medio",
        # perche' e' stato chiuso (stop loss, take profit, chiusura...) e perche' era stato aperto
        "close_reason": why or t.get("reason") or "",
        "entry_reason": (t.get("reason") or "") if why else "",
        "open_ms": t.get("open_ms"), "close_ms": t.get("close_ms"),
        "dca_count": t.get("dca_count", 0), "partial": bool(t.get("partial")),
        "fraction": t.get("fraction"), "confidence": t.get("confidence"), "source": t.get("source"),
        # "utente" se l'ha chiuso l'utente a mano (Chiudi / Chiudi tutto); altrimenti decide il bot
        "closed_by": t.get("closed_by"),
    }


def build_trades(data_dir: str, limit: int = 100) -> list:
    recs = closed_records(data_dir, None, last_n=max(1, min(int(limit), 5000)))
    recs.sort(key=lambda t: t.get("close_ms") or 0, reverse=True)   # piu' recenti prima
    return [normalize_trade(t) for t in recs]


# ── performance ──────────────────────────────────────────────────────────────
def _bucket(records: list, keyfn) -> dict:
    out: dict = {}
    for t in records:
        d = out.setdefault(keyfn(t), {"trades": 0, "wins": 0, "net_pnl": 0.0})
        net = _f(t.get("net"))
        d["trades"] += 1
        d["wins"] += 1 if net > 0 else 0
        d["net_pnl"] += net
    for d in out.values():
        d["win_rate"] = round(d["wins"] / d["trades"] * 100, 1) if d["trades"] else 0
        d["net_pnl"] = round(d["net_pnl"], 2)
    return out


def build_performance(data_dir: str, portfolio: str = "") -> dict:
    state = read_state(data_dir)
    start_equity = _f(((state.get("main") or {}).get("limits") or {}).get("start_equity"), DEFAULT_START_EQUITY)
    closed = closed_records(data_dir, state)
    empty = {"available": False, "portfolio": portfolio, "total_trades": 0, "winning_trades": 0,
             "losing_trades": 0, "win_rate": 0, "total_pnl": 0, "total_fees": 0, "avg_pnl_per_trade": 0,
             "profit_factor": None, "equity_curve": [], "by_symbol": {}, "by_type": {},
             "by_reason": {}, "by_side": {}, "start_equity": start_equity}
    if not closed:
        return empty
    nets = [_f(t.get("net")) for t in closed]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n < 0]
    total = len(closed)
    total_pnl = sum(nets)

    ordered = sorted(closed, key=lambda t: t.get("close_ms") or 0)
    running, peak, max_dd = 0.0, 0.0, 0.0
    curve = []
    for t in ordered:
        running += _f(t.get("net"))
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)
        curve.append({"time": t.get("close_ms"), "equity": round(start_equity + running, 2)})

    holds = [(_f(t.get("close_ms")) - _f(t.get("open_ms"))) / 3_600_000
             for t in closed if t.get("open_ms") and t.get("close_ms")]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    return {
        **empty,
        "available": True, "total_trades": total,
        "partial_closes": sum(1 for t in closed if t.get("partial")),
        "winning_trades": len(wins), "losing_trades": total - len(wins),
        "win_rate": round(len(wins) / total * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "total_fees": round(sum(_f(t.get("fees")) for t in closed), 2),
        "avg_pnl_per_trade": round(total_pnl / total, 2),
        "avg_win": round(gross_profit / len(wins), 2) if wins else 0.0,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
        "best_trade": round(max(nets), 2), "worst_trade": round(min(nets), 2),
        "max_drawdown": round(max_dd, 2),
        "avg_hold_hours": round(sum(holds) / len(holds), 1) if holds else None,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else None,
        "equity_curve": curve,
        "by_symbol": _bucket(closed, lambda t: t.get("symbol") or "?"),
        "by_type": _bucket(closed, lambda t: t.get("trade_type", t.get("type")) or "?"),
        "by_reason": _bucket(closed, lambda t: t.get("why") or "?"),
        "by_side": _bucket(closed, lambda t: "long" if t.get("side") == 1 else "short"),
    }


# ── diario ───────────────────────────────────────────────────────────────────
def build_diary(data_dir: str) -> dict:
    closed = closed_records(data_dir)
    days: dict = {}
    for t in closed:
        days.setdefault(_utc_day(t.get("close_ms")) if t.get("close_ms") else "?", []).append(t)
    result = []
    for day in sorted(days, reverse=True):
        day_trades = sorted(days[day], key=lambda x: x.get("close_ms") or 0)
        nets = [_f(t.get("net")) for t in day_trades]
        by_sym: dict = {}
        for t in day_trades:
            net = _f(t.get("net"))
            s = by_sym.setdefault(t.get("symbol") or "?", {"trades": 0, "wins": 0, "losses": 0,
                                                            "total_pnl": 0.0, "best": 0.0, "worst": 0.0})
            s["trades"] += 1
            s["total_pnl"] += net
            if net > 0:
                s["wins"] += 1
                s["best"] = max(s["best"], net)
            else:
                s["losses"] += 1
                s["worst"] = min(s["worst"], net)
        for s in by_sym.values():
            s["total_pnl"], s["best"], s["worst"] = (round(s[k], 2) for k in ("total_pnl", "best", "worst"))
        result.append({
            "day": day, "total_trades": len(day_trades),
            "wins": sum(1 for n in nets if n > 0), "losses": sum(1 for n in nets if n <= 0),
            "total_pnl": round(sum(nets), 2), "by_symbol": by_sym,
            "trades": [{
                "symbol": t.get("symbol"), "side": t.get("side"), "net": round(_f(t.get("net")), 2),
                "why": t.get("why") or t.get("reason") or "",
                "trade_type": t.get("trade_type", t.get("type")) or "?",
                "leverage": t.get("leverage", t.get("lev")), "margin": t.get("margin"),
                "close_ms": t.get("close_ms"), "partial": bool(t.get("partial")),
                "confidence": t.get("confidence"),
            } for t in day_trades],
        })
    return {"days": result, "total_closed": len(closed)}


# ── run archiviate (confronto prima/dopo un cambio di parametri) ─────────────
def list_runs(data_dir: str, portfolio: str = "", status: Optional[dict] = None) -> dict:
    state = read_state(data_dir)
    perf = build_performance(data_dir, portfolio)
    st = status if status is not None else build_status(data_dir, portfolio)
    recs = closed_records(data_dir, state)
    started = state.get("run_started_ms") or (min((t.get("open_ms") or 0 for t in recs), default=0) or None)
    limits = ((state.get("main") or {}).get("limits")) or {}
    current = {
        "run_no": state.get("run_no", 1), "started_ms": started,
        "trades": perf["total_trades"], "wins": perf["winning_trades"], "losses": perf["losing_trades"],
        "win_rate": perf["win_rate"], "net_total": perf["total_pnl"], "fees_total": perf["total_fees"],
        "best": perf.get("best_trade", 0), "worst": perf.get("worst_trade", 0),
        "profit_factor": perf["profit_factor"], "max_drawdown": perf.get("max_drawdown", 0),
        "start_equity": perf["start_equity"], "end_equity": st.get("equity"), "pnl": st.get("pnl_total"),
        "params": st.get("params") or {"limits": limits, "code_version": st.get("version")},
    }
    archived = []
    root = os.path.join(data_dir, "archive")
    try:
        names = sorted(os.listdir(root))
    except OSError:
        names = []
    for name in names:
        s = _read_json(os.path.join(root, name, "summary.json"))
        if s:
            s.setdefault("archive", name)
            archived.append(s)
    archived.sort(key=lambda s: s.get("ended_ms") or 0, reverse=True)
    return {"current": current, "archived": archived}


# ── comandi verso il bot (file-flag) ─────────────────────────────────────────
def _write_flag(data_dir: str, name: str, content: str = "") -> None:
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, name)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(content or str(int(time.time())))
    os.replace(tmp, path)


def _remove_flag(data_dir: str, name: str) -> None:
    try:
        os.remove(os.path.join(data_dir, name))
    except FileNotFoundError:
        pass


def _n_open(data_dir: str) -> int:
    return len(((read_state(data_dir).get("main")) or {}).get("positions") or {})


def command_pause(data_dir: str) -> dict:
    _write_flag(data_dir, "pause.flag")
    n = _n_open(data_dir)
    mode = derive_mode(True, n)
    return {"paused": True, "bot_mode": mode, "open_positions": n,
            "message": ("Pausa attivata: il bot non apre nuovi trade e lascia finire "
                        f"{n} posizioni gia' aperte (stop loss, take profit o uscita del bot)."
                        if n else "Pausa attivata: nessuna posizione aperta, il bot e' fermo.")}


def command_resume(data_dir: str) -> dict:
    _remove_flag(data_dir, "pause.flag")
    return {"paused": False, "bot_mode": "running", "open_positions": _n_open(data_dir),
            "message": "Bot avviato: riprende subito a cercare trade."}


def command_close_all(data_dir: str) -> dict:
    positions = ((read_state(data_dir).get("main")) or {}).get("positions") or {}
    if positions:
        _write_flag(data_dir, "reset.flag")
    return {"queued": bool(positions), "positions_found": len(positions), "symbols": list(positions),
            "message": (f"Chiusura inviata: {len(positions)} posizioni verranno chiuse a prezzo di mercato "
                        "entro pochi secondi." if positions else "Nessuna posizione aperta.")}


CLOSE_OLD_BOT_MESSAGE = ("Il bot gira ancora con la versione precedente, che non sa chiudere una singola posizione. "
                         "Il tasto si sblocca dopo la ridistribuzione dei bot (intanto resta Chiudi tutto).")


def can_close_position(hb: Optional[dict]) -> bool:
    """Il battito del bot dichiara `close_position` solo dalla versione che sa chiudere una singola posizione.
    Con un bot piu' vecchio il comando resterebbe in un file e scatterebbe a caso dopo il prossimo aggiornamento:
    meglio non accodarlo."""
    return bool(hb and hb.get("close_position") is True)


def _read_close_request(data_dir: str) -> list:
    try:
        with open(os.path.join(data_dir, "close_position.flag")) as f:
            req = json.loads(f.read() or "{}")
        return [str(x) for x in (req.get("symbols") or []) if x] if isinstance(req, dict) else []
    except Exception:
        return []


def close_pending(data_dir: str) -> list:
    """Simboli per cui l'utente ha chiesto la chiusura e il bot non l'ha ancora presa in carico."""
    return _read_close_request(data_dir)


def _find_position_key(positions: dict, symbol: str) -> Optional[str]:
    """Il simbolo come lo scrive il bot ('BTC'), trovato da quello che manda la pagina ('BTC', 'btc', 'BTCUSDT')."""
    want = str(symbol or "").strip().upper()
    if want.endswith("USDT") and len(want) > 4:
        want = want[:-4]
    for key in positions:
        k = str(key).upper()
        if k.endswith("USDT") and len(k) > 4:
            k = k[:-4]
        if k == want:
            return key
    return None


def command_close_position(data_dir: str, symbol: str) -> tuple:
    """(ok, http_status, risposta). Chiude UNA posizione a prezzo di mercato su richiesta dell'utente.
    Il comando e' un file che il bot prende in carico entro pochi secondi (e scarta se resta li' oltre 10 minuti).
    Rifiutato se: simbolo vuoto o strano, il bot e' di una versione che non lo sa fare, la posizione non c'e'."""
    sym = str(symbol or "").strip()
    if not sym or len(sym) > 24 or not all(c.isalnum() or c in "-_" for c in sym):
        return False, 400, {"ok": False, "message": "Simbolo non valido."}
    if not can_close_position(read_heartbeat(data_dir)):
        return False, 409, {"ok": False, "message": CLOSE_OLD_BOT_MESSAGE}
    positions = ((read_state(data_dir).get("main")) or {}).get("positions") or {}
    key = _find_position_key(positions, sym)
    if key is None:
        return False, 404, {"ok": False, "message": f"{sym.upper()}: il bot non ha una posizione aperta su questo "
                                                    "simbolo (forse è già stata chiusa)."}
    pending = _read_close_request(data_dir)
    if key not in pending:
        pending.append(key)
    _write_flag(data_dir, "close_position.flag", json.dumps({"symbols": pending, "ts": int(time.time() * 1000)}))
    return True, 200, {"ok": True, "queued": True, "symbol": key,
                       "message": f"Chiusura di {key} inviata: il bot la esegue a prezzo di mercato entro pochi "
                                  "secondi. La vedrai tra i trade chiusi come chiusa da te."}


def command_reset_budget(data_dir: str) -> dict:
    _write_flag(data_dir, "budget_reset.flag", "budget_only")
    return {"ok": True, "message": "Budget giornaliero di Claude azzerato (il conto non si tocca)."}


# ── orari di trading ─────────────────────────────────────────────────────────
# File `trading_hours.json` nella cartella dati del bot (lo legge il bot, vedi desk/trading_hours.py sul ramo del bot).
# Spento di default; lo accende solo l'utente da Impostazioni. Fuori dalle fasce il bot si comporta come in pausa:
# nessuna nuova apertura, le posizioni aperte si chiudono da sole. Il tasto Pausa vince sempre.
HOURS_FILE = "trading_hours.json"
HOURS_TZ = ("Europe/Rome", "UTC")
HOURS_MAX_WINDOWS = 14
HOURS_OLD_BOT_MESSAGE = ("Il bot gira ancora con la versione precedente, che non conosce gli orari di trading. "
                         "Si sblocca dopo la ridistribuzione dei bot.")
_HM_RE = re.compile(r"^(\d{2}):(\d{2})$")


def _hm_valid(value, allow_24: bool = False) -> bool:
    m = _HM_RE.match(value) if isinstance(value, str) else None
    if not m:
        return False
    h, mi = int(m.group(1)), int(m.group(2))
    return (h == 24 and mi == 0 and allow_24) or (h <= 23 and mi <= 59)


def validate_hours(body) -> tuple:
    """(config pulita, errore). Stesse regole del bot: fasce HH:MM nel fuso scelto, giorni 0=lunedi..6=domenica
    (se mancano valgono tutti), se la fine e' uguale o prima dell'inizio la fascia finisce il giorno dopo."""
    if not isinstance(body, dict):
        return None, "Richiesta non valida."
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        return None, "Indica se gli orari sono attivi o spenti."
    tz = body.get("tz", "Europe/Rome")
    if tz not in HOURS_TZ:
        return None, "Fuso orario non valido."
    raw = body.get("windows", [])
    if not isinstance(raw, list) or len(raw) > HOURS_MAX_WINDOWS:
        return None, f"Le fasce devono essere al massimo {HOURS_MAX_WINDOWS}."
    if enabled and not raw:
        return None, "Per attivare gli orari serve almeno una fascia."
    wins = []
    for i, w in enumerate(raw, 1):
        if not isinstance(w, dict) or not _hm_valid(w.get("start")) or not _hm_valid(w.get("end"), allow_24=True):
            return None, f"Fascia {i}: orari non validi (formato HH:MM)."
        if w["start"] == w["end"]:
            return None, f"Fascia {i}: inizio e fine uguali (per tutto il giorno usa 00:00 - 24:00)."
        days = w.get("days", list(range(7)))
        if (not isinstance(days, list) or not days
                or any(isinstance(d, bool) or not isinstance(d, int) or not 0 <= d <= 6 for d in days)):
            return None, f"Fascia {i}: giorni non validi."
        wins.append({"days": sorted(set(days)), "start": w["start"], "end": w["end"]})
    return {"enabled": enabled, "tz": tz, "windows": wins}, ""


def read_hours(data_dir: str) -> dict:
    """Impostazione salvata + stato di adesso come lo vede il bot (dal battito). `supported` = il bot gira con una
    versione che conosce gli orari (altrimenti salvarli non avrebbe alcun effetto)."""
    hb = read_heartbeat(data_dir)
    return {"config": _read_json(os.path.join(data_dir, HOURS_FILE)) or None,
            "state": (hb or {}).get("hours"), "supported": bool(hb and "hours" in hb)}


def command_set_hours(data_dir: str, body) -> tuple:
    """(ok, http_status, risposta). Attivare gli orari richiede un bot che li conosce; spegnerli e' sempre possibile."""
    clean, err = validate_hours(body)
    if err:
        return False, 400, {"ok": False, "message": err}
    if clean["enabled"] and not read_hours(data_dir)["supported"]:
        return False, 409, {"ok": False, "message": HOURS_OLD_BOT_MESSAGE}
    _write_flag(data_dir, HOURS_FILE, json.dumps({**clean, "updated_ms": int(time.time() * 1000)}))
    msg = ("Orari attivati: fuori dalle fasce il bot non apre nuove posizioni e lascia chiudere da sole quelle aperte."
           if clean["enabled"] else "Orari spenti: il bot lavora senza limiti di orario.")
    return True, 200, {"ok": True, "message": msg, **read_hours(data_dir)}


RESET_OLD_BOT_MESSAGE = ("Il bot gira ancora con la versione precedente, il cui azzeramento cancellerebbe anche "
                         "lo storico dei trade (il cervello). Si sblocca dopo la ridistribuzione dei bot.")


def reset_keeps_brain(hb: Optional[dict]) -> bool:
    """Il battito del bot dichiara `reset_keeps_brain` solo dalla versione in cui il reset non tocca piu' il cervello.
    Con un bot piu' vecchio (o senza battito) il reset resta bloccato: meglio nessun reset che uno che cancella."""
    return bool(hb and hb.get("reset_keeps_brain") is True)


def command_reset_portfolio(data_dir: str, clear_lessons: bool = False, reset_vault: bool = False) -> tuple:
    """(ok, http_status, risposta). Regole: solo in pausa e senza posizioni aperte; anche il bot le
    ricontrolla, qui si evita di accodare un comando che verrebbe rifiutato.
    `clear_lessons` e' accettato per compatibilita' ma NON ha effetto: il cervello non si cancella mai."""
    state = read_state(data_dir)
    if not state:
        return False, 404, {"ok": False, "message": "Nessun dato da azzerare: il bot non ha ancora salvato nulla."}
    if not pause_requested(data_dir):
        return False, 409, {"ok": False, "message": "Metti prima il bot in pausa: l'azzeramento è possibile solo da fermo."}
    n = _n_open(data_dir)
    if n > 0:
        return False, 409, {"ok": False, "message": (f"Ci sono ancora {n} posizioni aperte. Aspetta che si chiudano "
                                                       "da sole oppure usa Chiudi tutto, poi azzera.")}
    if os.path.exists(os.path.join(data_dir, "reset_portfolio.flag")):
        return True, 200, {"ok": True, "queued": True, "message": "Azzeramento già richiesto: il bot lo sta eseguendo."}
    if not reset_keeps_brain(read_heartbeat(data_dir)):
        return False, 409, {"ok": False, "message": RESET_OLD_BOT_MESSAGE}
    from salvadanaio_view import build_view
    has_vault = build_view(state, read_heartbeat(data_dir), time.time()).get("available")
    if has_vault and (reset_vault is not True or not read_heartbeat(data_dir).get("reset_with_vault")):
        return False, 409, {"ok": False, "message": "Conferma esplicitamente il reset del Salvadanaio e aggiorna il bot."}
    payload = {"clear_lessons": False}
    if has_vault:
        payload["reset_vault"] = True
    _write_flag(data_dir, "reset_portfolio.flag", json.dumps(payload))
    return True, 200, {"ok": True, "queued": True,
                       "message": "Azzeramento richiesto: la run attuale viene archiviata e il conto riparte da 1000$. "
                                   "Il Salvadanaio e i pending vengono azzerati solo se confermati. Il cervello (storico dei trade, appunti, registro) non si tocca. "
                                  "Il bot resta in pausa finché non premi Avvia."}


def health(data_dir: str, portfolio: str) -> dict:
    st = build_status(data_dir, portfolio)
    return {"available": bool(st.get("available")), "portfolio": portfolio,
            "bot_online": st.get("bot_online"), "bot_mode": st.get("bot_mode"),
            "halt": st.get("halt"), "version": st.get("version"),
            "last_ok": (st.get("cycle") or {}).get("last_ok")}
