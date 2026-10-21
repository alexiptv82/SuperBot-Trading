"""Dalla risposta del modello agli ordini: lettura rigida, controllo (arbitro) e dimensionamento.

Il modello propone; il codice decide cosa e' ammesso e quanto e' grande. Ogni voce scartata resta nel registro con il
suo motivo (`rifiutata:<motivo>`), cosi' si vede anche cosa l'AI avrebbe voluto e non ha potuto fare.
Regola monotona: nessuna voce dell'AI puo' allargare uno stop, togliere uno stop o aumentare il rischio di una
posizione aperta (MOVE_STOP solo verso il prezzo; PARTIAL_CLOSE/CLOSE riducono).
"""
import json
import math
import re

ACTIONS = ("OPEN_LONG", "OPEN_SHORT", "CLOSE", "PARTIAL_CLOSE", "MOVE_STOP", "HOLD")
MAX_ITEMS = 60


def _num(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        v = float(x)
    elif isinstance(x, str):
        try:
            v = float(x.strip())
        except ValueError:
            return None
    else:
        return None
    return v if math.isfinite(v) else None


def _txt(x, n):
    return str(x)[:n] if isinstance(x, (str, int, float)) and not isinstance(x, bool) else ""


def parse_response(text: str) -> tuple:
    """(market_read, voci, errore). Ammette recinti ```json e testo attorno al JSON. Una voce illeggibile e' una voce
    scartata (con motivo), non un ciclo perso."""
    if not isinstance(text, str) or not text.strip():
        return "", [], "risposta vuota"
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I)
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        return "", [], "nessun oggetto json"
    try:
        obj = json.loads(s[a:b + 1])
    except ValueError:
        return "", [], "json non valido"
    if not isinstance(obj, dict) or not isinstance(obj.get("decisions"), list):
        return "", [], "campo decisions mancante"
    items = []
    for raw in obj["decisions"][:MAX_ITEMS]:
        if not isinstance(raw, dict):
            items.append({"_err": "voce non e' un oggetto"})
            continue
        act = str(raw.get("action", "")).strip().upper()
        conv = _num(raw.get("conviction"))
        it = {"symbol": str(raw.get("symbol", "")).strip().upper().replace("USDT", ""),
              "action": act,
              "conviction": int(conv) if conv is not None else None,
              "stop_loss": _num(raw.get("stop_loss")), "take_profit": _num(raw.get("take_profit")),
              "close_fraction": _num(raw.get("close_fraction")), "new_stop": _num(raw.get("new_stop")),
              "horizon_bars": _num(raw.get("horizon_bars")),
              "thesis": _txt(raw.get("thesis"), 200), "invalidate_if": _txt(raw.get("invalidate_if"), 140)}
        if act not in ACTIONS:
            it["_err"] = "azione sconosciuta"
        items.append(it)
    return _txt(obj.get("market_read"), 200), items, None


def _rej(it, reason):
    return {"symbol": it.get("symbol", ""), "action": it.get("action", ""), "accepted": False, "reason": "rifiutata:" + reason}


def _ok(it, extra=None):
    r = {"symbol": it["symbol"], "action": it["action"], "accepted": True, "reason": "ok"}
    if extra:
        r.update(extra)
    return r


def plan_cycle(items: list, cfg, snap: dict) -> tuple:
    """(ordini, esiti). `snap`: px {sym: ultima chiusura}, positions {sym: {side, sl, tp, entry}}, pending_open {sym},
    universe {sym}, halted str, bar_t (apertura dell'ultima barra chiusa). Gli ordini vengono eseguiti all'apertura
    della barra successiva: prima uscite e stop, poi le aperture."""
    orders, results = [], []
    pos, px = snap["positions"], snap["px"]
    closing = set()
    # ---- 1) gestione delle posizioni aperte
    for it in items:
        if it.get("_err"):
            results.append(_rej(it, it["_err"]))
            continue
        a, sym = it["action"], it["symbol"]
        if a in ("OPEN_LONG", "OPEN_SHORT"):
            continue
        if sym not in snap["universe"]:
            results.append(_rej(it, "simbolo_sconosciuto"))
            continue
        if a == "HOLD":
            results.append(_ok(it))
            continue
        p = pos.get(sym)
        if p is None:
            results.append(_rej(it, "nessuna_posizione"))
            continue
        if sym in closing:
            results.append(_rej(it, "gia_in_chiusura"))
            continue
        if a == "CLOSE":
            closing.add(sym)
            orders.append({"kind": "close", "symbol": sym, "thesis": it["thesis"], "bar_t": snap["bar_t"]})
            results.append(_ok(it))
        elif a == "PARTIAL_CLOSE":
            f = it["close_fraction"]
            if f is None or not (0.1 <= f <= 0.9):
                results.append(_rej(it, "frazione_non_valida"))
                continue
            orders.append({"kind": "partial", "symbol": sym, "fraction": f, "thesis": it["thesis"], "bar_t": snap["bar_t"]})
            results.append(_ok(it))
        elif a == "MOVE_STOP":
            ns, last = it["new_stop"], px.get(sym)
            if ns is None or ns <= 0 or last is None:
                results.append(_rej(it, "stop_non_valido"))
            elif p["side"] == 1 and not (p["sl"] < ns < last):
                results.append(_rej(it, "stop_non_stringe_o_oltre_il_prezzo"))
            elif p["side"] == -1 and not (last < ns < p["sl"]):
                results.append(_rej(it, "stop_non_stringe_o_oltre_il_prezzo"))
            else:
                orders.append({"kind": "move_stop", "symbol": sym, "new_stop": ns, "thesis": it["thesis"], "bar_t": snap["bar_t"]})
                results.append(_ok(it))
    # ---- 2) nuove aperture, dalla piu' convinta; con un tetto per ciclo
    opens = sorted([it for it in items if not it.get("_err") and it["action"] in ("OPEN_LONG", "OPEN_SHORT")],
                   key=lambda i: -(i["conviction"] or 0))
    used = len(pos) - len(closing) + len(snap["pending_open"])
    n_new = 0
    for it in opens:
        sym, long_ = it["symbol"], it["action"] == "OPEN_LONG"
        last = px.get(sym)
        if sym not in snap["universe"]:
            results.append(_rej(it, "simbolo_sconosciuto"))
        elif last is None:
            results.append(_rej(it, "senza_dati_in_questo_ciclo"))
        elif snap["halted"]:
            results.append(_rej(it, "conto_fermo"))
        elif sym in pos and sym not in closing:
            results.append(_rej(it, "posizione_gia_aperta"))
        elif sym in snap["pending_open"]:
            results.append(_rej(it, "ordine_gia_in_attesa"))
        elif n_new >= cfg.max_new_per_cycle:
            results.append(_rej(it, "troppe_aperture_nel_ciclo"))
        elif used >= cfg.max_open:
            results.append(_rej(it, "slot_pieni"))
        elif it["conviction"] is None or it["conviction"] < cfg.min_conviction:
            results.append(_rej(it, "convinzione_bassa"))
        elif it["stop_loss"] is None or it["stop_loss"] <= 0:
            results.append(_rej(it, "stop_mancante"))
        elif it["take_profit"] is None or it["take_profit"] <= 0:
            results.append(_rej(it, "tp_mancante"))
        else:
            sl, tp = it["stop_loss"], it["take_profit"]
            if (long_ and not (sl < last < tp)) or ((not long_) and not (tp < last < sl)):
                results.append(_rej(it, "livelli_dal_lato_sbagliato"))
                continue
            sl_pct = abs(last - sl) / last * 100.0
            if sl_pct < cfg.min_sl_pct:
                results.append(_rej(it, "stop_troppo_vicino"))
            elif sl_pct > cfg.max_sl_pct:
                results.append(_rej(it, "stop_troppo_lontano"))
            elif abs(tp - last) / abs(last - sl) < cfg.min_rr:
                results.append(_rej(it, "rr_basso"))
            else:
                n_new += 1
                used += 1
                orders.append({"kind": "open", "symbol": sym, "side": 1 if long_ else -1, "sl": sl, "tp": tp,
                               "conviction": it["conviction"], "horizon_bars": it["horizon_bars"],
                               "thesis": it["thesis"], "invalidate_if": it["invalidate_if"], "ref_px": last,
                               "bar_t": snap["bar_t"]})
                results.append(_ok(it))
    return orders, results


def size_position(cfg, equity: float, side: int, fill: float, sl: float, tier_cap: int,
                  slip_bp: float, maint: float, sl_liq_frac: float) -> tuple:
    """(margine, leva, rischio_pianificato) oppure (None, motivo, 0). Rischio fisso `risk_pct` del capitale allo stop.
    La leva e' la minima che permette di fare quel rischio con al massimo `max_margin_trade` di margine; se anche la
    leva massima ammessa (tetto per asset e distanza dalla liquidazione) non basta, il margine si ferma al tetto e il
    rischio reale scende: non si rischia mai di piu' del previsto."""
    fill_eff = fill * (1 + side * slip_bp / 1e4)
    dist = abs(fill_eff - sl) / fill_eff
    if dist <= 0:
        return None, "stop_non_valido", 0.0
    risk = equity * cfg.risk_pct / 100.0
    notional = risk / dist
    lev_liq = int(math.floor(1.0 / (dist / sl_liq_frac + maint)))
    lev_cap = min(int(tier_cap), lev_liq)
    if lev_cap < 1:
        return None, "stop_oltre_la_liquidazione", 0.0
    lev = min(lev_cap, max(1, int(math.ceil(notional / cfg.max_margin_trade))))
    margin = min(notional / lev, cfg.max_margin_trade)
    if margin < 10.0:
        return None, "margine_troppo_basso", 0.0
    return round(margin, 2), lev, round(margin * lev * dist, 4)
