"""Simulazione OFFLINE delle proposte d'apertura del Brain unico (24/11/2026): veto attuale contro alternative.

Ingresso: l'esportazione del journal (``esporta_journal.py``). Nessuna scrittura nella run; rete solo verso le API
PUBBLICHE di Bitget (candele e regole dei contratti, senza chiavi), con cache locale.

Per ogni proposta di apertura di DeepSeek registrata nei consulti (``ai_consultation``, scope ``entry``):
* ingresso = chiusura dell'ultima candela da 1 minuto CHIUSA prima della decisione + slittamento di 2 bp (come il
  runner); stop = quello di DeepSeek, o quello di Claude se adottato; nessun dato successivo alla decisione;
* filtri della politica V2 calcolati sugli stessi dati: trend 1h/4h (EMA 20/50 su candele chiuse), costi / 1R;
* dimensione = preventivo di rischio REALE (``quote_paper_risk``) con la leva "fit" del motore (15-50x), sullo stato
  del portafoglio simulato in quel momento (capitale realizzato, rischio aperto, margine, posizioni, stessa direzione);
* uscite meccaniche della politica della run (stop, pareggio, trailing, take profit 3,5R) e presa parziale del 35 % a
  2R come il monitor; NESSUNA revisione AI (non ricostruibile): e' un limite dichiarato. Commissioni 6 bp per lato
  su ogni parte, slittamento 2 bp sull'ingresso e sugli stop. Una posizione ancora aperta a fine dati e' "incerta"
  (valutata all'ultimo prezzo, separata dai risultati chiusi).

Scenari: S0 veto attuale (esito reale del consulto); S1 S0 + rischio dimezzato quando Claude non ha giudicato;
S2 consulto selettivo (soglie 0,60 BTC/ETH/oro/argento e 0,70 altri, EXPANSION da solo non basta; dove il consulto
non scatterebbe si apre a rischio pieno, altrove vale l'esito reale di Claude); S3 = S2 + S1; S4 tutte le proposte di
DeepSeek senza Claude (riferimento). Ogni scenario anche con i filtri V2 (LONG con trend, costi).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

M = 60_000
H, H4 = 3_600_000, 14_400_000
TIER_A = {"BTCUSDT", "ETHUSDT", "XAUUSDT", "XAGUSDT"}
NOT_CONSULTED = ("skipped_limit", "budget", "timeout_or_error", "unavailable", "invalid")
D = Decimal


# ----------------------------------------------------------------------------- dati di mercato (cache locale)
def candles(cache: Path, symbol: str, gran: str, step: int, start: int, end: int) -> list[tuple]:
    f = cache / f"{symbol}-{gran}-{start}-{end}.json"
    if f.is_file():
        return [tuple(x) for x in json.loads(f.read_text())]
    out, cur = {}, start
    while cur < end:
        stop = min(end, cur + 200 * step)
        url = (f"https://api.bitget.com/api/v2/mix/market/history-candles?symbol={symbol}&productType=USDT-FUTURES"
               f"&granularity={gran}&startTime={cur}&endTime={stop}&limit=200")
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=20) as r:
                    data = json.loads(r.read().decode()).get("data") or []
                break
            except Exception:                                 # noqa: BLE001
                data = []
                time.sleep(1 + attempt)
        for row in data:
            t = int(row[0])
            if start <= t < end:
                out[t] = (t, row[1], row[2], row[3], row[4])
        cur = stop
        time.sleep(0.15)
    rows = [out[t] for t in sorted(out)]
    f.write_text(json.dumps(rows))
    return rows


def ema(values: list[Decimal], n: int) -> Decimal | None:
    if len(values) < n:
        return None
    k = Decimal(2) / Decimal(n + 1)
    e = sum(values[:n]) / n
    for v in values[n:]:
        e = v * k + e * (1 - k)
    return e


def trend(rows: list[tuple]) -> int | None:
    closes = [D(r[4]) for r in rows]
    fast, slow = ema(closes, 20), ema(closes, 50)
    if fast is None or slow is None:
        return None
    c = closes[-1]
    return 1 if (c > slow and fast > slow) else -1 if (c < slow and fast < slow) else 0


# ----------------------------------------------------------------------------- proposte
def proposals(events: list[dict]) -> list[dict]:
    out = []
    for e in events:
        p = e["payload"]
        if e["kind"] != "ai_consultation" or p.get("scope") != "entry":
            continue
        ds, cl, fin = p.get("deepseek") or {}, p.get("claude") or {}, p.get("final") or {}
        out.append({"t": e["t"], "seq": e["seq"], "symbol": p["symbol"], "regime": p.get("regime"),
                    "side": int(ds["side"]), "ds_stop": D(str(ds["stop_price"])), "conf": float(ds.get("confidence", 0)),
                    "uncertain": bool(ds.get("uncertain")), "reasons": list(ds.get("reasons") or []),
                    "triggers": list(p.get("triggers") or []), "claude_status": cl.get("status"),
                    "claude_verdict": cl.get("verdict"), "claude_conf": cl.get("confidence"), "code": p.get("code"),
                    "final_open": bool(fin.get("open")), "final_side": fin.get("side"),
                    "final_stop": None if fin.get("stop_price") is None else D(str(fin["stop_price"]))})
    return sorted(out, key=lambda x: (x["t"], x["seq"]))


def executions(events: list[dict]) -> dict:
    opens = [e for e in events if e["kind"] == "paper_open"]
    groups = {}
    for o in opens:
        groups.setdefault(o["payload"].get("decision_event_id"), []).append(o["payload"])
    approved = [e for e in events if e["kind"] == "brain_decision" and e["payload"].get("status") == "APPROVED"]
    return {"paper_open_events": len(opens), "distinct_trades": len(groups),
            "legs_per_trade": {k: [x.get("leg") for x in v] for k, v in groups.items()},
            "approved_decisions": [(a["payload"].get("symbol"), a["t"], a["id"]) for a in approved],
            "approved_without_open": [a["payload"].get("symbol") for a in approved if a["id"] not in groups]}


def selective_triggers(pr: dict) -> list[str]:
    thr = 0.60 if pr["symbol"] in TIER_A else 0.70
    out = []
    if pr["uncertain"] or pr["conf"] < thr:
        out.append("uncertainty")
    if {"conflicting_signals", "trend_change", "reversal_risk"} & set(pr["reasons"]):
        out.append("trend_change_or_conflict")
    if "portfolio_risk" in pr["triggers"]:
        out.append("portfolio_risk")
    return out


def decide(pr: dict, scenario: str) -> tuple[bool, float, str]:
    """(apre?, quota di rischio, motivo) per lo scenario."""
    thr = 0.60 if pr["symbol"] in TIER_A else 0.70
    missing = pr["claude_status"] in NOT_CONSULTED
    half_ok = missing and not pr["uncertain"] and pr["conf"] >= thr
    if scenario == "S4":
        return True, 1.0, "deepseek_alone"
    if scenario in ("S2", "S3") and not selective_triggers(pr):
        return True, 1.0, "no_consult_under_v2"
    if pr["final_open"]:
        return True, 1.0, "claude_ok"
    if scenario in ("S1", "S3") and half_ok:
        return True, 0.5, "half_risk_claude_missing"
    return False, 0.0, pr["code"] or "veto"


# ----------------------------------------------------------------------------- simulazione di una posizione
def simulate_exit(side, fill, stop, opened_ms, bars, policy, partial, fee_bps):
    from backend.v3.features.indicators import Bar
    from backend.v3.runner.exits import evaluate_exit
    bb = [Bar(int(r[0]), D(r[1]), D(r[2]), D(r[3]), D(r[4]), D(0)) for r in bars if int(r[0]) >= opened_ms]
    if not bb:
        return None
    sig = evaluate_exit(side=side, fill_price=fill, stop_price=stop, opened_at_ms=opened_ms, bars=bb, candle_ms=M,
                        policy=policy, fee_bps=D(fee_bps))
    risk = abs(fill - stop)
    part = None
    if partial is not None and risk > 0:
        target = fill + side * partial.at_r * risk
        for b in bb:
            if b.open_time_ms < opened_ms:
                continue
            if sig is not None and (b.open_time_ms > sig.bar_open_time_ms
                                    or (b.open_time_ms == sig.bar_open_time_ms and sig.reason == "stop")):
                break
            if (b.high >= target) if side == 1 else (b.low <= target):
                part = (b.open_time_ms, target)
                break
    return {"signal": None if sig is None else (sig.reason, sig.price, sig.bar_open_time_ms, sig.stop_kind),
            "partial": part, "last": (bb[-1].open_time_ms, bb[-1].close),
            "mfe_r": float(max((side * ((b.high if side == 1 else b.low) - fill) for b in bb), default=0) / risk)
            if risk else None}


def run_scenario(name, props, ctx, *, filters: bool) -> dict:
    from backend.v3.brain_f2.engine import _LEVERAGE_RETRY
    from backend.v3.risk import RiskRequest, quote_paper_risk
    cfg, rules, pol = ctx["config"], ctx["rules"], ctx["risk_policy"]
    fee = D(str(cfg.fee_bps))
    eq0 = D(str(cfg.initial_equity))
    realized, closes_at = D(0), []                       # (t, net) delle chiusure: capitale realizzato nel tempo
    open_pos, trades, skipped = [], [], []
    peak, max_dd, max_open, max_risk, max_margin = eq0, D(0), 0, D(0), D(0)
    for pr in props:
        t = pr["t"]
        # libera le posizioni chiuse prima di t
        for p in list(open_pos):
            if p["exit_ms"] is not None and p["exit_ms"] <= t:
                open_pos.remove(p)
        equity = eq0 + sum((n for (ct, n) in closes_at if ct <= t), D(0))
        go, scale, why = decide(pr, name)
        info = ctx["per_prop"][pr["seq"]]
        if go and filters and info["filter"]:
            go, why = False, info["filter"]
        if not go:
            skipped.append((pr["symbol"], why))
            continue
        if any(p["symbol"] == pr["symbol"] for p in open_pos):
            skipped.append((pr["symbol"], "already_open"))
            continue
        side = pr["side"] if name == "S4" or not pr["final_open"] else int(pr["final_side"] or pr["side"])
        stop = pr["final_stop"] if (pr["final_open"] and pr["final_stop"] is not None and name != "S4") else pr["ds_stop"]
        entry = info["entry"]
        if entry is None or side * (entry - stop) <= 0:
            skipped.append((pr["symbol"], "entry_unavailable_or_stop_wrong_side"))
            continue
        r = rules.get(pr["symbol"])
        if r is None:
            skipped.append((pr["symbol"], "rules_missing"))
            continue
        open_risk = sum((p["risk"] for p in open_pos), D(0))
        side_risk = sum((p["risk"] for p in open_pos if p["side"] == side), D(0))
        margin_used = sum((p["margin"] for p in open_pos), D(0))
        cap = equity * pol.max_loss_fraction * D(str(scale)) if scale < 1 else None
        base = RiskRequest(equity=equity, available_cash=equity - margin_used, margin_used=margin_used,
                           existing_open_risk=open_risk, entry_price=entry, stop_price=stop, side=side,
                           requested_leverage=pol.min_leverage, exchange_leverage_limit=int(r["exchange_leverage_limit"]),
                           quantity_step=D(str(r["quantity_step"])), minimum_notional=D(str(r["minimum_notional"])),
                           maintenance_fraction=D(str(r["maintenance_fraction"])), market_data_fresh=True,
                           paused=False, daily_loss_latched=False, open_positions=len(open_pos),
                           same_side_open_risk=side_risk, external_risk_cap=cap)
        best = None
        for lev in range(pol.min_leverage, min(pol.max_leverage, int(r["exchange_leverage_limit"])) + 1):
            q = quote_paper_risk(pol, replace(base, requested_leverage=lev))
            if q.allowed and (best is None or q.quantity > best[1].quantity):
                best = (lev, q)
            elif not q.allowed and q.reason not in _LEVERAGE_RETRY:
                if best is None:
                    best = (lev, q)
                break
        if best is None or not best[1].allowed:
            skipped.append((pr["symbol"], "risk:" + (best[1].reason if best else "no_quote")))
            continue
        lev, q = best
        fill = entry * (1 + side * D("0.0002"))          # slittamento d'ingresso 2 bp (come il runner)
        qty = q.quantity
        sim = info["exit"].get((str(stop), side))
        if sim is None:
            sim = simulate_exit(side, fill, stop, t, ctx["bars"][pr["symbol"]], cfg.exit_policy,
                                cfg.unico.partial if cfg.unico else None, fee)
            info["exit"][(str(stop), side)] = sim
        parts, exit_ms, status = [], None, "closed"
        rest = qty
        if sim and sim["partial"]:
            pq = (qty * cfg.unico.partial.fraction / D(r["quantity_step"])).to_integral_value(rounding="ROUND_DOWN") \
                * D(r["quantity_step"])
            if pq > 0 and pq < qty:
                parts.append((pq, sim["partial"][1], sim["partial"][0], "partial_2R"))
                rest = qty - pq
        if sim and sim["signal"]:
            parts.append((rest, sim["signal"][1], sim["signal"][2], sim["signal"][0]))
            exit_ms = sim["signal"][2] + M
        else:
            status = "uncertain_open"
            last = sim["last"] if sim else (t, fill)
            parts.append((rest, D(last[1]), last[0], "mark_to_market"))
        gross = sum(((px - fill) * side * qq for qq, px, _, _ in parts), D(0))
        fees = sum(((fill * qq + px * qq) * fee / D(10000) for qq, px, _, _ in parts), D(0))
        slip = fill * qty * D("0.0002") + sum((px * qq * D("0.0002") for qq, px, _, why in parts if why == "stop"), D(0))
        net = gross - fees
        risk_usd = q.worst_case_loss_estimate if q.worst_case_loss_estimate else qty * abs(fill - stop)
        pos = {"symbol": pr["symbol"], "side": side, "risk": risk_usd, "margin": q.margin, "exit_ms": exit_ms}
        open_pos.append(pos)
        max_open = max(max_open, len(open_pos))
        max_risk = max(max_risk, sum((p["risk"] for p in open_pos), D(0)) / equity)
        max_margin = max(max_margin, sum((p["margin"] for p in open_pos), D(0)) / equity)
        if status == "closed":
            closes_at.append((exit_ms, net))
        trades.append({"t": t, "symbol": pr["symbol"], "side": side, "why": why, "risk_scale": scale, "lev": lev,
                       "entry": str(fill), "stop": str(stop), "stop_bp": float(abs(fill - stop) / fill * 10000),
                       "qty": str(qty), "margin": str(q.margin), "risk_usd": str(risk_usd.quantize(D("0.01"))),
                       "status": status, "exits": [(w, str(px), time.strftime("%d/%m %H:%M", time.gmtime(ts / 1000)))
                                                   for _, px, ts, w in parts],
                       "gross": str(gross.quantize(D("0.01"))), "fees": str(fees.quantize(D("0.01"))),
                       "slippage_est": str(slip.quantize(D("0.01"))), "net": str(net.quantize(D("0.01"))),
                       "mfe_r": None if not sim else round(sim["mfe_r"], 2)})
    # drawdown sul capitale realizzato (chiusure in ordine di tempo)
    eq = eq0
    for _, n in sorted(closes_at):
        eq += n
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
    closed = [x for x in trades if x["status"] == "closed"]
    nets = [D(x["net"]) for x in closed]
    gp, gl = sum((n for n in nets if n > 0), D(0)), -sum((n for n in nets if n < 0), D(0))
    unc = [x for x in trades if x["status"] != "closed"]
    return {"scenario": name + ("+filtri" if filters else ""), "opened": len(trades), "closed": len(closed),
            "uncertain": len(unc), "wins": sum(n > 0 for n in nets), "losses": sum(n < 0 for n in nets),
            "net_closed": str(sum(nets, D(0)).quantize(D("0.01"))),
            "gross_closed": str(sum((D(x["gross"]) for x in closed), D(0)).quantize(D("0.01"))),
            "fees_closed": str(sum((D(x["fees"]) for x in closed), D(0)).quantize(D("0.01"))),
            "slippage_est_closed": str(sum((D(x["slippage_est"]) for x in closed), D(0)).quantize(D("0.01"))),
            "profit_factor": round(float(gp / gl), 2) if gl else None,
            "uncertain_mtm": str(sum((D(x["net"]) for x in unc), D(0)).quantize(D("0.01"))),
            "max_drawdown_realized": str(max_dd.quantize(D("0.01"))), "max_concurrent": max_open,
            "max_open_risk_pct": round(float(max_risk) * 100, 2), "max_margin_pct": round(float(max_margin) * 100, 2),
            "half_risk_trades": sum(1 for x in trades if x["risk_scale"] < 1),
            "skipped": sorted({(s, w) for s, w in skipped}), "trades": trades}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--until-ms", type=int, default=0)
    a = ap.parse_args(argv)
    from backend.v3.runner.config import load_runner_config
    from backend.v3.runner.contracts import ContractRules
    from backend.v3.lab_tools.fetch_candles import http_json
    exp = json.loads(Path(a.export).read_text())
    cfg = load_runner_config(json.dumps(exp["config"]).encode())
    pol = replace(cfg.risk_policy, leverage_fit=True) if cfg.unico and cfg.unico.leverage_fit else cfg.risk_policy
    events = exp["events"]
    props = proposals(events)
    cache = Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)
    until = a.until_ms or int(time.time() * 1000) // M * M
    cr = ContractRules(http_json, maintenance_fraction=cfg.maintenance_fraction)
    cr.load(until)
    rules = {s: cr(s) for s in cfg.symbols}
    first = min((p["t"] for p in props), default=until)
    start = first // M * M - 5 * M
    bars, per = {}, {}
    for sym in sorted({p["symbol"] for p in props}):
        bars[sym] = candles(cache, sym, "1m", M, start, until)
    for p in props:
        m_end = p["t"] // M * M
        before = [r for r in bars[p["symbol"]] if int(r[0]) < m_end]
        entry = D(before[-1][4]) if before and int(before[-1][0]) == m_end - M else None
        h1 = candles(cache, p["symbol"], "1H", H, p["t"] // H * H - 300 * H, p["t"] // H * H)
        h4 = candles(cache, p["symbol"], "4H", H4, p["t"] // H4 * H4 - 300 * H4, p["t"] // H4 * H4)
        t1, t4 = trend(h1), trend(h4)
        stop = p["ds_stop"]
        cost = None if entry is None or entry == stop else float((entry * D(16) / D(10000)) / abs(entry - stop))
        filt = None
        if p["conf"] < 0.56:                                       # confidenza minima della V2
            filt = "confidence_below_floor"
        elif p["side"] == 1 and not (t1 == 1 and t4 == 1):
            filt = "long_against_trend" if t1 is not None and t4 is not None else "long_trend_unknown"
        elif cost is not None and cost > 0.30:
            filt = "cost_too_high_for_stop"
        per[p["seq"]] = {"entry": entry, "trend_1h": t1, "trend_4h": t4, "cost_fraction_r": cost, "filter": filt,
                         "exit": {}}
    ctx = {"config": cfg, "rules": rules, "risk_policy": pol, "bars": bars, "per_prop": per}
    res = [run_scenario(s, props, ctx, filters=f) for f in (False, True) for s in ("S0", "S1", "S2", "S3", "S4")]
    rep = {"generated_ms": until, "proposals": len(props),
           "by_code": {c: sum(1 for p in props if p["code"] == c) for c in sorted({p["code"] for p in props})},
           "executions": executions(events),
           "proposals_detail": [{"t": time.strftime("%H:%M", time.gmtime(p["t"] / 1000)), "symbol": p["symbol"],
                                 "side": p["side"], "conf": p["conf"], "uncertain": p["uncertain"], "code": p["code"],
                                 "claude": [p["claude_status"], p["claude_verdict"], p["claude_conf"]],
                                 "triggers": p["triggers"], "v2_triggers": selective_triggers(p),
                                 "entry": None if per[p["seq"]]["entry"] is None else str(per[p["seq"]]["entry"]),
                                 "stop": str(p["ds_stop"]), "trend_1h": per[p["seq"]]["trend_1h"],
                                 "trend_4h": per[p["seq"]]["trend_4h"],
                                 "cost_fraction_r": None if per[p["seq"]]["cost_fraction_r"] is None
                                 else round(per[p["seq"]]["cost_fraction_r"], 3), "filter": per[p["seq"]]["filter"]}
                                for p in props],
           "scenarios": res}
    Path(a.out).write_text(json.dumps(rep, indent=1, default=str))
    for r in res:
        print(f"{r['scenario']:11s} aperte {r['opened']:3d} chiuse {r['closed']:3d} incerte {r['uncertain']:2d} "
              f"V/P {r['wins']}/{r['losses']} netto {r['net_closed']:>9s} lordo {r['gross_closed']:>9s} "
              f"comm {r['fees_closed']:>7s} PF {r['profit_factor']} DD {r['max_drawdown_realized']} "
              f"max pos {r['max_concurrent']} rischio {r['max_open_risk_pct']}% margine {r['max_margin_pct']}% "
              f"mezze {r['half_risk_trades']} incerte_mtm {r['uncertain_mtm']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
