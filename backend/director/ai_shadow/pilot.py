"""Il pilota: un conto virtuale (stesso motore e stessi costi dei bot) gestito dalle decisioni del modello.

Ordine di un ciclo (a ogni chiusura di barra da 15 minuti):
  1. si scaricano le candele pubbliche (solo barre chiuse);
  2. gli ordini decisi alla barra precedente si eseguono all'APERTURA della barra appena chiusa (come l'etichettatore:
     nessuna conoscenza del futuro); poi il motore giudica la barra con stop, TP e liquidazione (stop prima del TP);
  3. se la barra non e' gia' stata decisa, si costruisce il prompt, si controlla il tetto di spesa, si chiama il modello,
     si legge la risposta, il controllore (arbitro) scarta il non ammesso e dimensiona il resto;
  4. si registra tutto e si salva lo stato in modo atomico.
Nessun ordine verso nessun exchange: il conto e' finto e il modulo non contiene nessun codice di trading.
"""
import os
import time

from desk.engine import Limits, PaperAccount, max_leverage_for

from . import SCHEMA, VERSION, decisions, deepseek, features, journal, prompt
from .budget import Budget, worst_case_usd
from .config import Config, config_hash

KIND_ORDER = {"close": 0, "partial": 1, "move_stop": 2, "open": 3}


def make_limits(cfg: Config) -> Limits:
    return Limits(start_equity=cfg.start_equity, max_margin_trade=cfg.max_margin_trade,
                  max_margin_total=cfg.max_margin_total, max_open=cfg.max_open,
                  kill_equity=cfg.kill_equity, daily_stop=cfg.daily_stop)


def new_state(cfg: Config) -> dict:
    acc = PaperAccount(make_limits(cfg), cfg.name)
    return {"schema": SCHEMA, "version": VERSION, "config_hash": config_hash(cfg), "acc": acc.to_dict(),
            "pending": [], "last_bar_t": 0, "last_decided_bar_t": 0, "closed_total": 0, "closed_logged": 0,
            "last_read": "", "recent": [],
            "model": {"fail_streak": 0, "backoff_until_ms": 0, "last_error": "", "calls_ok": 0, "calls_failed": 0,
                      "last_call_ms": 0}}


class Pilot:
    def __init__(self, cfg: Config, out_dir: str, api_key: str, cache, model_call=deepseek.call, sleep=time.sleep):
        self.cfg, self.out, self.key, self.cache, self.model_call = cfg, out_dir, api_key, cache, model_call
        self.sleep = sleep
        os.makedirs(out_dir, exist_ok=True)
        self.state_path = os.path.join(out_dir, "state.json")
        self.status_path = os.path.join(out_dir, "status.json")
        self.budget = Budget(os.path.join(out_dir, "spend.jsonl"), cfg.daily_cap_usd, cfg.monthly_cap_usd,
                             cfg.cost_safety)
        self.state, self.note = self._load()
        self.acc = PaperAccount.from_dict(self.state["acc"])
        self.acc.name = cfg.name

    # ---------------------------------------------------------------- stato
    def _load(self) -> tuple:
        raw = journal.read_json(self.state_path)
        if raw is None:
            return new_state(self.cfg), ("stato illeggibile: si riparte da un conto nuovo" if os.path.exists(self.state_path) else None)
        if raw.get("schema") != SCHEMA:
            return new_state(self.cfg), "schema cambiato: si riparte da un conto nuovo"
        note = None
        if raw.get("config_hash") != config_hash(self.cfg):
            note = "config_cambiata %s -> %s (il conto prosegue)" % (raw.get("config_hash"), config_hash(self.cfg))
            raw["config_hash"] = config_hash(self.cfg)
        return raw, note

    def _save(self) -> None:
        self.state["acc"] = self.acc.to_dict()
        journal.atomic_json(self.state_path, self.state)

    # ---------------------------------------------------------------- prezzi e posizioni
    @staticmethod
    def _last_close(bars: dict):
        b = (bars.get("15m") or [])
        return b[-1][4] if b else None

    def _position_rows(self, prices: dict, now_ms: int) -> list:
        rows = []
        for sym, p in sorted(self.acc.positions.items()):
            px = prices.get(sym, p.entry)
            r_den = p.entry0 * p.r_dist if p.entry0 and p.r_dist else 0.0
            best = p.px_hi if p.side == 1 else p.px_lo
            rows.append({"symbol": sym, "side": p.side, "entry": features.fmt_price(p.entry),
                         "px": features.fmt_price(px), "pnl_pct": p.side * (px - p.entry) / p.entry * 100.0,
                         "r": p.side * (px - p.entry0) / r_den if r_den else 0.0,
                         "sl": features.fmt_price(p.sl), "tp": features.fmt_price(p.tp) if p.tp is not None else None,
                         "age_min": max(0, now_ms - p.open_ms) // 60_000,
                         "mfe_r": max(0.0, p.side * (best - p.entry0)) / r_den if r_den and best else 0.0})
        return rows

    # ---------------------------------------------------------------- esecuzione degli ordini
    def _execute(self, orders: list, t: int, opens: dict, prices: dict, events: list) -> None:
        cfg, acc = self.cfg, self.acc
        for o in sorted(orders, key=lambda x: KIND_ORDER[x["kind"]]):
            sym = o["symbol"]
            px_open = opens.get(sym)
            if px_open is None:
                events.append({"ev": "ordine_scaduto", "symbol": sym, "kind": o["kind"], "why": "senza_barra"})
                continue
            pos = acc.positions.get(sym)
            if o["kind"] == "close":
                rec = acc.close(sym, px_open, t, "ai: chiusura") if pos else None
                events.append({"ev": "exit" if rec else "ordine_scaduto", "symbol": sym, "kind": "close",
                               "net": rec and rec["net"], "why": None if rec else "nessuna_posizione"})
            elif o["kind"] == "partial":
                rec = acc.partial_close(sym, px_open, t, o["fraction"], why="ai: parziale") if pos else None
                events.append({"ev": "exit_parziale" if rec else "ordine_scaduto", "symbol": sym, "kind": "partial",
                               "net": rec and rec["net"], "why": None if rec else "nessuna_posizione"})
            elif o["kind"] == "move_stop":
                ns = o["new_stop"]
                ok = pos is not None and ((pos.side == 1 and pos.sl < ns < px_open) or (pos.side == -1 and px_open < ns < pos.sl))
                if ok:
                    pos.sl = float(ns)
                events.append({"ev": "stop_spostato" if ok else "ordine_scaduto", "symbol": sym, "kind": "move_stop",
                               "new_stop": ns, "why": None if ok else "non_piu_valido_all_apertura"})
            elif o["kind"] == "open":
                events.append(self._open(o, px_open, t, prices))

    def _open(self, o: dict, fill: float, t: int, prices: dict) -> dict:
        cfg, acc = self.cfg, self.acc
        sym, side, sl, tp = o["symbol"], o["side"], o["sl"], o["tp"]
        base = {"ev": "ordine_respinto", "symbol": sym, "kind": "open"}
        if sym in acc.positions:
            return dict(base, why="posizione_gia_aperta")
        if not ((side == 1 and sl < fill < tp) or (side == -1 and tp < fill < sl)):
            return dict(base, why="livelli_dal_lato_sbagliato_all_apertura")
        if abs(tp - fill) / abs(fill - sl) < cfg.min_fill_rr:
            return dict(base, why="rr_basso_all_apertura")
        margin, lev, risk = decisions.size_position(
            cfg, acc.equity(prices), side, fill, sl, max_leverage_for(sym), acc.limits.slip_bp_side,
            acc.limits.maint, acc.limits.sl_liq_frac)
        if margin is None:
            return dict(base, why=lev)
        hz = o.get("horizon_bars")
        pos, msg = acc.open(sym, side, margin, lev, fill, sl, tp, t, prices, confidence=o["conviction"],
                            reason=o["thesis"], source="ai-deepseek",
                            trade_type="scalp" if (hz is not None and hz <= 8) else "medio",
                            features={"conviction": o["conviction"], "horizon_bars": hz,
                                      "invalidate_if": o.get("invalidate_if", ""), "ref_px": o["ref_px"]})
        if pos is None:
            return dict(base, why=msg)
        return {"ev": "fill", "symbol": sym, "side": side, "entry": round(pos.entry, 8), "margin": pos.total_margin,
                "lev": pos.leverage, "risk_usd": pos.risk_plan_usd, "sl": sl, "tp": tp, "conviction": o["conviction"]}

    # ---------------------------------------------------------------- un ciclo
    def run_once(self, now_ms: int) -> dict:
        cfg, st, acc = self.cfg, self.state, self.acc
        bar = cfg.bar_ms
        bar_t = (now_ms - cfg.delay_ms) // bar * bar - bar            # apertura dell'ultima barra chiusa
        events = []
        if self.note:
            events.append({"ev": "nota", "why": self.note})
            self.note = None
        data = self.cache.refresh(now_ms, bar_t)
        fresh = {s: d for s, d in data.items() if d["15m"] and d["15m"][-1][0] == bar_t}
        if len(fresh) < cfg.min_symbols_ok:       # la barra appena chiusa puo' arrivare con qualche secondo di ritardo
            self.sleep(20)
            data = self.cache.refresh(now_ms + 20_000, bar_t)
            fresh = {s: d for s, d in data.items() if d["15m"] and d["15m"][-1][0] == bar_t}
        stale = [s for s in cfg.symbols if s not in fresh]
        prices = {s: self._last_close(d) for s, d in data.items() if self._last_close(d) is not None}

        # ---- 1) barre nuove: ordini all'apertura dell'ultima, poi giudizio del motore su ogni barra
        by_sym = {s: {b[0]: b for b in d["15m"]} for s, d in data.items()}
        times = sorted({t for m in by_sym.values() for t in m if st["last_bar_t"] < t <= bar_t})
        pending = list(st["pending"])
        due = [o for o in pending if o["bar_t"] + bar == bar_t]
        for o in pending:
            if o["bar_t"] + bar < bar_t:
                events.append({"ev": "ordine_scaduto", "symbol": o["symbol"], "kind": o["kind"], "why": "container_fermo_o_dati_mancanti"})
        keep = [o for o in pending if o["bar_t"] + bar > bar_t]
        for t in times:
            if t == bar_t and due:
                opens = {s: m[t][1] for s, m in by_sym.items() if t in m}
                self._execute(due, t, opens, prices, events)
                due = []
            for s, m in by_sym.items():
                if t in m:
                    b = m[t]
                    rec = acc.on_bar(s, b[0], b[1], b[2], b[3], b[4], bar)
                    if rec:
                        events.append({"ev": "exit", "symbol": s, "kind": "auto", "why": rec["why"], "net": rec["net"]})
        if due:     # la barra di destinazione non c'e' (dati mancanti): l'ordine decade, non si esegue a ritroso
            for o in due:
                events.append({"ev": "ordine_scaduto", "symbol": o["symbol"], "kind": o["kind"], "why": "barra_mancante"})
        st["pending"] = keep
        if times:
            st["last_bar_t"] = max(st["last_bar_t"], times[-1])
        acc.roll_day(journal.day_of(bar_t + bar), prices)

        self._log_trades()

        # ---- 2) decisione del modello (una sola volta per barra)
        dec = self._decide(now_ms, bar_t, data, fresh, stale, prices, events)

        # ---- 3) registri e stato
        eq = acc.equity(prices)
        line = {"schema": SCHEMA, "ts_ms": now_ms, "bar_t": bar_t, "cfg": config_hash(cfg), "bars_ok": len(fresh),
                "stale": stale, "decision": dec, "events": events, "equity": round(eq, 4), "cash": round(acc.cash, 4),
                "open": len(acc.positions), "pending": len(st["pending"])}
        journal.append_jsonl(os.path.join(self.out, "cycles-%s.jsonl" % journal.day_of(now_ms)), line)
        self._save()
        self._write_status(now_ms, bar_t, fresh, dec, eq)
        return line

    # ---------------------------------------------------------------- decisione
    def _decide(self, now_ms: int, bar_t: int, data: dict, fresh: dict, stale: list, prices: dict, events: list) -> dict:
        cfg, st, acc, m = self.cfg, self.state, self.acc, self.state["model"]
        dec = {"called": False, "skip": None}
        if st["last_decided_bar_t"] == bar_t:
            dec["skip"] = "barra_gia_decisa"
            return dec
        if os.path.exists(os.path.join(self.out, "pause.flag")):
            dec["skip"] = "pausa"
            return dec
        if len(fresh) < cfg.min_symbols_ok:
            dec["skip"] = "dati_insufficienti:%d" % len(fresh)
            return dec
        if not self.key:
            dec["skip"] = "chiave_assente"
            return dec
        if now_ms < m["backoff_until_ms"]:
            dec["skip"] = "attesa_dopo_errori:%s" % m["last_error"][:40]
            return dec

        # prompt
        lines, summ = [], {}
        for s in cfg.symbols:
            if s in fresh:
                r = features.summarize(s, fresh[s])
                if r:
                    summ[s] = r
                    lines.append(r["line"])
        missing = [s for s in cfg.symbols if s not in summ]
        px = {s: v["price"] for s, v in summ.items()}
        eq = acc.equity(prices)
        account = {"equity": eq, "cash": acc.cash, "margin": acc.margin_in_use(), "max_margin": cfg.max_margin_total,
                   "n_open": len(acc.positions), "max_open": cfg.max_open,
                   "day_pnl_pct": (eq / acc.day_start_equity - 1.0) * 100.0 if acc.day_start_equity else 0.0,
                   "halted": acc.halted(prices)}
        user = prompt.build_user(bar_t + cfg.bar_ms, account, self._position_rows(prices, now_ms), st["recent"],
                                 st["last_read"], lines, missing)
        system = prompt.SYSTEM
        ok, why, worst = self.budget.check(cfg.model, now_ms, len(system) + len(user), cfg.max_tokens)
        if not ok:
            dec["skip"] = "spesa:" + why
            return dec

        dec.update({"called": True, "skip": None, "prompt_chars": len(system) + len(user), "worst_usd": round(worst, 6),
                    "prompt_version": cfg.prompt_version})
        m["last_call_ms"] = now_ms
        try:
            res = self.model_call(cfg, self.key, system, user)
        except deepseek.ModelError as e:
            u = e.usage
            self.budget.record(cfg.model, now_ms, u["hit"], u["miss"], u["out"], False, e.kind, est_cost=worst)
            m["calls_failed"] += 1
            m["fail_streak"] += 1
            m["last_error"] = e.kind + (":%s" % e.status if e.status else "")
            if e.kind in ("auth", "balance"):
                m["backoff_until_ms"] = now_ms + 6 * 3_600_000
            elif m["fail_streak"] >= 3:
                m["backoff_until_ms"] = now_ms + 30 * 60_000
            msg = str(e)[:160].replace(self.key, "***") if self.key else str(e)[:160]     # difesa in piu': mai la chiave nei registri
            dec.update({"error": e.kind, "error_msg": msg, "spend_usd": self.budget.spent_day(now_ms)})
            events.append({"ev": "errore_modello", "kind": e.kind})
            return dec
        u = res["usage"]
        cost = self.budget.record(cfg.model, now_ms, u["hit"], u["miss"], u["out"], True, "ok", est_cost=worst)
        m["calls_ok"] += 1
        m["fail_streak"] = 0
        m["last_error"] = ""
        journal.append_gz(os.path.join(self.out, "prompts-%s.jsonl.gz" % journal.day_of(now_ms)),
                          {"bar_t": bar_t, "prompt_version": cfg.prompt_version, "user": user, "response": res["content"],
                           "usage": u})
        read, items, perr = decisions.parse_response(res["content"])
        dec.update({"model": res["model"], "latency_ms": res["latency_ms"], "usage": u, "cost_usd": round(cost, 6),
                    "market_read": read, "parse_error": perr, "n_items": len(items)})
        if perr is None:
            snap = {"px": px, "positions": {s: {"side": p.side, "sl": p.sl, "tp": p.tp, "entry": p.entry}
                                            for s, p in acc.positions.items()},
                    "pending_open": {o["symbol"] for o in st["pending"] if o["kind"] == "open"},
                    "universe": set(cfg.symbols), "halted": account["halted"], "bar_t": bar_t}
            orders, results = decisions.plan_cycle(items, cfg, snap)
            st["pending"].extend(orders)
            st["last_read"] = read
            dec["results"] = results
            dec["orders"] = len(orders)
        st["last_decided_bar_t"] = bar_t       # anche con risposta illeggibile: la barra e' stata pagata, non si ripete
        self._save()
        return dec

    # ---------------------------------------------------------------- registri
    def _log_trades(self) -> None:
        """Scrive nei file dei trade i record di chiusura nuovi. `closed_logged` = quanti record del vettore attuale
        sono gia' scritti; nello stato ne restano 300 (il resto e' nei file)."""
        st, acc = self.state, self.acc
        start = min(st["closed_logged"], len(acc.closed))
        for rec in acc.closed[start:]:
            journal.append_jsonl(os.path.join(self.out, "trades-%s.jsonl" % journal.day_of(rec["close_ms"])), rec)
            st["recent"].append({"symbol": rec["symbol"], "side": rec["side"], "net_r": rec.get("net_r"),
                                 "why": rec.get("why", ""), "hold_min": rec.get("hold_min")})
            st["closed_total"] += 1
        st["recent"] = st["recent"][-6:]
        if len(acc.closed) > 300:
            acc.closed = acc.closed[len(acc.closed) - 300:]
        st["closed_logged"] = len(acc.closed)

    def _write_status(self, now_ms: int, bar_t: int, fresh: dict, dec: dict, eq: float) -> None:
        cfg, st, m = self.cfg, self.state, self.state["model"]
        prev = journal.read_json(self.status_path) or {}
        last_ok = now_ms if len(fresh) >= cfg.min_symbols_ok else prev.get("last_success_ms")
        journal.atomic_json(self.status_path, {
            "ts_ms": now_ms, "last_success_ms": last_ok, "algo": "%s/%s/%s" % (VERSION, cfg.model, cfg.prompt_version),
            "mode": "ombra", "applied": False, "bar_t": bar_t,
            "symbols_ok": len(fresh), "symbols_total": len(cfg.symbols), "errors": dict(list(self.cache.errors.items())[:5]),
            "equity": round(eq, 2), "open": len(self.acc.positions), "closed_total": st["closed_total"],
            "model": {"calls_ok": m["calls_ok"], "calls_failed": m["calls_failed"], "last_error": m["last_error"],
                      "fail_streak": m["fail_streak"], "backoff_until_ms": m["backoff_until_ms"],
                      "last_call_ms": m["last_call_ms"]},
            "spend": {"day_usd": round(self.budget.spent_day(now_ms), 4), "month_usd": round(self.budget.spent_month(now_ms), 4),
                      "daily_cap": cfg.daily_cap_usd, "monthly_cap": cfg.monthly_cap_usd},
            "last_cycle": {"called": dec.get("called"), "skip": dec.get("skip"), "error": dec.get("error")}})
