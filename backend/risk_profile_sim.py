"""
SuperBot — Simulatore storico dei profili di rischio / leva (offline)
=====================================================================

Strumento di ricerca SOLO LETTURA: non tocca il bot, il DB, l'exchange
(oltre a scaricare candele pubbliche) né alcun processo in esecuzione.

Perche' esiste
--------------
Il paper trading del bot, oggi, NON simula due cose che con la leva alta
contano moltissimo:

  1. La LIQUIDAZIONE (a 30x basta un movimento contrario di circa il 3%).
  2. Le COMMISSIONI (round-trip taker ~0,12% del nozionale: con stop da
     frazioni di punto percentuale e' un costo enorme).

In piu', con la formula di sizing attuale la leva e' quasi "cosmetica": la
size e' decisa dal rischio (1% fino allo stop) con un tetto al 20% del
capitale, e lo stop e' basato sull'ATR a 1 minuto (stretto) -> a decidere e'
quasi sempre il tetto, quindi cambiare la leva cambia solo il margine
bloccato, non il rischio reale. Questo simulatore lo misura sui dati.

Cosa fa
-------
  1. Scarica candele 1m pubbliche da BitGet (ccxt), le ricampiona a 15m/1h
     (stessa finestra di 100 barre che usa il bot) e genera i segnali V1
     (signal_engine.analyze, identico al bot) ogni `--stride` minuti.
  2. Per ogni PROFILO di rischio simula un portafoglio unico (capitale
     condiviso, max posizioni aperte, una posizione per simbolo, limite di
     perdita giornaliera) con SL/TP/liquidazione/commissioni/slippage,
     controllando le candele 1m successive (se SL e TP cadono nella stessa
     candela si assume lo SL: ipotesi prudente).
  3. Stampa una classifica (rendimento netto/lordo, drawdown, liquidazioni,
     profit factor, stabilita' tra prima e seconda meta' del periodo).

Profilo di rischio (parametri)
------------------------------
  max_lev / min_lev   leva massima / minima
  lev_mode            'legacy' = int(forza/10) come il bot attuale;
                      'scaled' = interpola la forza del segnale (50..110)
                      tra min_lev e max_lev
  risk_pct            % del capitale perso se viene colpito lo stop
  cap_ref_pct         tetto sul nozionale (% capitale) alla leva ref_lev
  margin_exp (k)      "piu' leva = meno budget": il margine usato scala
                      come (ref_lev/leva)^k  =>  nozionale ∝ leva^(1-k)
                        k=1   nozionale costante (la leva non cambia l'esposizione)
                        k=0.5 nozionale ∝ radice della leva
                        k=0   margine costante (esposizione ∝ leva)
  liq_safety          lo stop deve stare entro 1/liq_safety della distanza
                      di liquidazione, altrimenti la leva viene ABBASSATA
                      automaticamente (0 = disattivato, come oggi)
  sl_scale            moltiplicatore della distanza di stop (1 = come oggi)
  min_strength        forza minima del segnale per operare (50 = come oggi;
                      piu' alta = meno operazioni, quindi meno commissioni)

Uso (in locale servono ccxt+pandas; in CI vedi .github/workflows/risk-sim.yml)
------------------------------------------------------------------------------
    python risk_profile_sim.py --candles 43200 --stride 5 --sweep standard
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import math
import os
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional

# Profilo, dimensionamento e liquidazione vivono in risk_profiles.py: sono lo
# stesso codice che usa il bot, cosi' il simulatore e il bot non possono
# divergere.
from risk_profiles import (  # noqa: F401,E402
    MEDIUM_TP_RATIO, MMR, SCALP_TP_RATIO, Profile, lev_target, liquidation_price, size_trade,
)

ONE_MINUTE_MS = 60_000
WINDOW_SIZE = 100            # come bot_engine: ultime 100 barre per timeframe

DEFAULT_SYMBOLS = "BTC/USDT:USDT,ETH/USDT:USDT,XAU/USDT:USDT,XAG/USDT:USDT"


# ─────────────────────────────────────────────────────────────────────────────
# Simulazione di una singola operazione sulle candele 1m
# ─────────────────────────────────────────────────────────────────────────────

def simulate_exit(
    candles: list,
    i: int,
    side: str,
    sl: float,
    tp: float,
    liq: float,
    max_hold: int,
    slip_frac: float,
) -> tuple[int, float, str]:
    """Scorre le candele dopo l'ingresso (barra i) e ritorna
    (indice_uscita, prezzo_uscita, motivo) con motivo in
    {'sl','tp','liq','timeout'}.

    Ipotesi prudenti: se nella stessa candela cadono sia lo stop che il
    take-profit vale lo stop; gap oltre lo stop si riempiono all'apertura;
    lo stop si riempie con slippage avverso; se il riempimento dello stop
    supera il prezzo di liquidazione l'operazione e' liquidata."""
    n = len(candles)
    last = min(i + max_hold, n - 1)
    is_long = side == "long"
    for j in range(i + 1, last + 1):
        o, h, l, c = candles[j][1], candles[j][2], candles[j][3], candles[j][4]
        if is_long:
            stop_level = max(sl, liq)
            if l <= stop_level:
                if liq > sl:
                    return j, liq, "liq"
                fill = min(sl, o) * (1.0 - slip_frac)
                if fill <= liq:
                    return j, liq, "liq"
                return j, fill, "sl"
            if h >= tp:
                return j, tp, "tp"
        else:
            stop_level = min(sl, liq)
            if h >= stop_level:
                if liq < sl:
                    return j, liq, "liq"
                fill = max(sl, o) * (1.0 + slip_frac)
                if fill >= liq:
                    return j, liq, "liq"
                return j, fill, "sl"
            if l <= tp:
                return j, tp, "tp"
    c = candles[last][4]
    exit_price = c * (1.0 - slip_frac) if is_long else c * (1.0 + slip_frac)
    return last, exit_price, "timeout"


# ─────────────────────────────────────────────────────────────────────────────
# Portafoglio
# ─────────────────────────────────────────────────────────────────────────────

def _day(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def run_portfolio(
    profile: Profile,
    signals: list[dict],
    candles: dict[str, list],
    *,
    initial_capital: float = 1000.0,
    fee_frac: float = 0.0006,
    slip_frac: float = 0.0002,
    max_hold: int = 720,
    max_open: int = 3,
    max_daily_loss_pct: float = 5.0,
) -> dict:
    """Simula un portafoglio unico (come il bot: un solo capitale, max
    posizioni aperte, una posizione per simbolo, stop giornaliero)."""
    capital = initial_capital
    open_pos: list[dict] = []
    closed: list[dict] = []
    day_pnl: dict[str, float] = {}
    skips: Counter = Counter()
    peak = capital
    max_dd = 0.0

    def settle(upto_ts: float) -> None:
        nonlocal capital, peak, max_dd
        due = sorted((p for p in open_pos if p["exit_ts"] <= upto_ts), key=lambda p: p["exit_ts"])
        for p in due:
            open_pos.remove(p)
            capital += p["net"]
            d = _day(p["exit_ts"])
            day_pnl[d] = day_pnl.get(d, 0.0) + p["net"]
            closed.append(p)
            if capital > peak:
                peak = capital
            dd = (peak - capital) / peak * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

    for sig in sorted(signals, key=lambda s: (s["ts"], s["symbol"])):
        settle(sig["ts"])
        sym = sig["symbol"]
        if sig["strength"] < profile.min_strength:
            skips["forza_insufficiente"] += 1
            continue
        if any(p["symbol"] == sym for p in open_pos):
            skips["simbolo_gia_aperto"] += 1
            continue
        if len(open_pos) >= max_open:
            skips["max_posizioni"] += 1
            continue
        if day_pnl.get(_day(sig["ts"]), 0.0) <= -(capital * max_daily_loss_pct / 100.0):
            skips["limite_giornaliero"] += 1
            continue
        if capital <= 0:
            skips["capitale_esaurito"] += 1
            continue
        params = size_trade(profile, capital, sig["price"], sig["atr"], sig["side"],
                            sig["trade_type"], sig["strength"], slip_frac)
        if params is None:
            skips["nessun_dimensionamento"] += 1
            continue
        free_margin = capital - sum(p["margin"] for p in open_pos)
        if params["margin"] > free_margin:
            skips["margine_insufficiente"] += 1
            continue

        side = sig["side"]
        sgn = 1.0 if side == "long" else -1.0
        entry_fill = sig["price"] * (1.0 + sgn * slip_frac)      # slippage avverso
        liq = liquidation_price(side, entry_fill, params["leverage"])
        j, exit_price, reason = simulate_exit(
            candles[sym], sig["i"], side, params["stop_loss"], params["take_profit"],
            liq, max_hold, slip_frac)
        qty = params["quantity"]
        entry_fee = qty * entry_fill * fee_frac
        if reason == "liq":
            gross = -params["margin"]                              # margine isolato perso
            fees = entry_fee
        else:
            gross = sgn * qty * (exit_price - entry_fill)
            fees = entry_fee + qty * exit_price * fee_frac
        net = gross - fees
        open_pos.append({
            "symbol": sym, "side": side, "trade_type": sig["trade_type"],
            "strength": sig["strength"], "entry_ts": sig["ts"],
            "exit_ts": candles[sym][j][0] + ONE_MINUTE_MS,
            "leverage": params["leverage"], "notional": params["notional"],
            "margin": params["margin"], "capital_at_open": capital,
            "reason": reason, "gross": gross, "fees": fees, "net": net,
        })
    settle(float("inf"))
    return _stats(profile, closed, initial_capital, capital, max_dd, skips, signals)


def _stats(profile, closed, initial_capital, final_capital, max_dd, skips, signals) -> dict:
    n = len(closed)
    wins = [t for t in closed if t["net"] > 0]
    losses = [t for t in closed if t["net"] <= 0]
    gross_total = sum(t["gross"] for t in closed)
    fees_total = sum(t["fees"] for t in closed)
    net_total = sum(t["net"] for t in closed)
    win_sum = sum(t["net"] for t in wins)
    loss_sum = -sum(t["net"] for t in losses)
    reasons = Counter(t["reason"] for t in closed)
    by_symbol: dict[str, float] = {}
    for t in closed:
        by_symbol[t["symbol"]] = by_symbol.get(t["symbol"], 0.0) + t["net"]
    by_type: dict[str, dict] = {}
    for t in closed:
        d = by_type.setdefault(t["trade_type"], {"n": 0, "net": 0.0, "gross": 0.0})
        d["n"] += 1
        d["net"] += t["net"]
        d["gross"] += t["gross"]
    # stabilita': rendimento netto nella prima e nella seconda meta' del periodo (per ingresso)
    half = [0.0, 0.0]
    if signals:
        t0 = min(s["ts"] for s in signals)
        t1 = max(s["ts"] for s in signals)
        mid = (t0 + t1) / 2.0
        for t in closed:
            half[0 if t["entry_ts"] < mid else 1] += t["net"]
    return {
        "name": profile.name,
        "profile": asdict(profile),
        "trades": n,
        "final_capital": final_capital,
        "return_pct": net_total / initial_capital * 100.0,
        "gross_return_pct": gross_total / initial_capital * 100.0,
        "fees": fees_total,
        "max_dd_pct": max_dd,
        "win_rate": (len(wins) / n * 100.0) if n else 0.0,
        "profit_factor": (win_sum / loss_sum) if loss_sum > 0 else (float("inf") if win_sum > 0 else 0.0),
        "liquidations": reasons.get("liq", 0),
        "sl": reasons.get("sl", 0),
        "tp": reasons.get("tp", 0),
        "timeout": reasons.get("timeout", 0),
        "avg_leverage": (sum(t["leverage"] for t in closed) / n) if n else 0.0,
        "avg_notional_pct": (sum(t["notional"] / t["capital_at_open"] for t in closed) / n * 100.0) if n else 0.0,
        "avg_margin_pct": (sum(t["margin"] / t["capital_at_open"] for t in closed) / n * 100.0) if n else 0.0,
        "worst_trade_pct": (min(t["net"] / t["capital_at_open"] for t in closed) * 100.0) if n else 0.0,
        "half_1_pct": half[0] / initial_capital * 100.0,
        "half_2_pct": half[1] / initial_capital * 100.0,
        "by_symbol": {k: round(v, 2) for k, v in sorted(by_symbol.items())},
        "by_type": {k: {"n": v["n"], "net": round(v["net"], 2), "gross": round(v["gross"], 2)}
                    for k, v in sorted(by_type.items())},
        "skips": dict(skips),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Insiemi di profili da confrontare
# ─────────────────────────────────────────────────────────────────────────────

def build_round2() -> list[Profile]:
    """Secondo giro: stop piu' larghi + soglia di forza + famiglie di leva.
    ATT = formula attuale (leva legacy, tetto 20%, nessuna sicurezza di
    liquidazione); A30* = leva fino a 30 autogestita (meno margine con piu'
    leva, leva abbassata se lo stop e' vicino alla liquidazione) con tetti
    d'esposizione crescenti."""
    fams = [
        ("ATT", dict()),
        ("L30-cap20", dict(max_lev=30, lev_mode="scaled", margin_exp=0.5, cap_ref_pct=20.0, liq_safety=3.0)),
        ("L30-cap50", dict(max_lev=30, lev_mode="scaled", margin_exp=0.5, cap_ref_pct=50.0, liq_safety=3.0)),
        ("L30-cap100", dict(max_lev=30, lev_mode="scaled", margin_exp=0.5, cap_ref_pct=100.0, liq_safety=3.0)),
    ]
    out = []
    for sl_scale in (1.0, 2.0, 3.0, 5.0, 8.0):
        for min_str in (50, 70, 90):
            for fam, kw in fams:
                out.append(Profile(name=f"{fam} sl{sl_scale:g}x forza>={min_str}",
                                   sl_scale=sl_scale, min_strength=min_str, **kw))
    return out


def build_sweep(kind: str) -> list[Profile]:
    if kind == "round2":
        return build_round2()
    base = [
        Profile(name="ATTUALE lev<=10 tetto20 sl1x"),
        Profile(name="ATTUALE lev<=10 tetto20 sl2x", sl_scale=2.0),
    ]
    if kind == "legacy":
        return base
    out = list(base)
    for sl_scale in (1.0, 2.0):
        for max_lev in (5, 10, 20, 30):
            for k in (1.0, 0.5):
                for cap in (20.0, 50.0):
                    out.append(Profile(
                        name=f"lev<={max_lev} k{k:g} tetto{cap:g} sl{sl_scale:g}x",
                        max_lev=max_lev, lev_mode="scaled", margin_exp=k,
                        cap_ref_pct=cap, liq_safety=3.0, sl_scale=sl_scale))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Dati: download, ricampionamento, segnali
# ─────────────────────────────────────────────────────────────────────────────

def fetch_1m_history(symbol: str, total_candles: int, end_ms: Optional[int] = None,
                     batch_limit: int = 200) -> list:
    # batch_limit=200: l'endpoint storico di BitGet restituisce al massimo 200
    # candele per chiamata; con limit=1000 ccxt chiede una finestra di 1000
    # minuti e se ne vedono solo le ultime 200 (buchi da ~800 minuti).
    import ccxt  # import locale: i test del simulatore non richiedono ccxt
    client = ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    end_ms = end_ms if end_ms is not None else client.milliseconds()
    since = end_ms - total_candles * ONE_MINUTE_MS
    collected: dict[int, list] = {}
    calls = 0
    while True:
        attempt, batch = 0, None
        while attempt < 3:
            try:
                batch = client.fetch_ohlcv(symbol, "1m", since=since, limit=batch_limit)
                break
            except Exception as exc:  # noqa: BLE001
                attempt += 1
                print(f"  [warn] fetch_ohlcv retry {attempt}/3: {exc}", file=sys.stderr)
                time.sleep(1.0 * attempt)
        if not batch:
            break
        calls += 1
        if calls <= 2:
            print(f"  [diag] chiamata {calls}: since={since} -> {len(batch)} candele, "
                  f"prima={int(batch[0][0])} ultima={int(batch[-1][0])}", flush=True)
        for c in batch:
            if int(c[0]) <= end_ms:
                collected[int(c[0])] = c
        # NB: il numero di candele per chiamata dipende dalla versione di ccxt
        # (200 o 1000): si avanza finche' si fanno progressi, senza presumere
        # che un batch "corto" significhi fine dei dati.
        last_ts = max(int(c[0]) for c in batch)
        if last_ts < since:
            break                       # nessun progresso
        since = last_ts + ONE_MINUTE_MS
        if since >= end_ms or len(collected) >= total_candles:
            break
        if calls % 50 == 0:
            print(f"  ...{symbol}: {len(collected)}/{total_candles} candele", flush=True)
        time.sleep(0.1)
    ordered = sorted(collected.values(), key=lambda c: c[0])
    return ordered[-total_candles:] if len(ordered) > total_candles else ordered


def describe_candles(symbol: str, candles: list) -> str:
    """Diagnostica sui dati scaricati: copertura, buchi, barre complete."""
    if not candles:
        return f"{symbol}: nessuna candela"
    fmt = lambda ms: datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")  # noqa: E731
    gaps = [(b[0] - a[0]) // ONE_MINUTE_MS for a, b in zip(candles, candles[1:]) if b[0] - a[0] != ONE_MINUTE_MS]
    return (f"{symbol}: {len(candles)} candele {fmt(candles[0][0])} -> {fmt(candles[-1][0])} UTC, "
            f"buchi {len(gaps)} (max {max(gaps) if gaps else 0} min), "
            f"barre complete 15m={len(resample(candles, 15))} 1h={len(resample(candles, 60))}")


def resample(candles_1m: list, minutes: int) -> list:
    """Aggrega candele 1m in barre da `minutes`; scarta i bucket incompleti."""
    bucket_ms = minutes * ONE_MINUTE_MS
    buckets: dict[int, list] = {}
    for c in candles_1m:
        buckets.setdefault(int(c[0]) - (int(c[0]) % bucket_ms), []).append(c)
    out = []
    for key in sorted(buckets):
        g = buckets[key]
        if len(g) < minutes:
            continue
        out.append([key, g[0][1], max(c[2] for c in g), min(c[3] for c in g),
                    g[-1][4], sum(c[5] for c in g)])
    return out


def generate_signals(symbol: str, candles: list, stride: int, max_hold: int,
                     quiet: bool = False) -> list[dict]:
    """Segnali V1 (signal_engine.analyze, identico al bot) ogni `stride` barre.
    Si fermano `max_hold` barre prima della fine, cosi' ogni operazione ha
    abbastanza storia davanti per chiudersi davvero."""
    from signal_engine import signal_engine  # richiede pandas
    c15 = resample(candles, 15)
    c1h = resample(candles, 60)
    end15 = [c[0] + 15 * ONE_MINUTE_MS for c in c15]
    end1h = [c[0] + 60 * ONE_MINUTE_MS for c in c1h]
    out: list[dict] = []
    last = len(candles) - 1 - max_hold
    i = WINDOW_SIZE - 1
    steps = 0
    t_report = time.time()
    while i <= last:
        t = candles[i][0]
        n15 = bisect.bisect_right(end15, t)
        n1h = bisect.bisect_right(end1h, t)
        if n15 >= WINDOW_SIZE and n1h >= WINDOW_SIZE:
            res = signal_engine.analyze(
                candles[i - WINDOW_SIZE + 1: i + 1],
                c15[n15 - WINDOW_SIZE: n15],
                c1h[n1h - WINDOW_SIZE: n1h])
            steps += 1
            if not res.get("error") and res["signal"] != "hold":
                atr = res["indicators_1m"]["atr"]
                if atr == atr and atr > 0:     # scarta NaN
                    out.append({
                        "symbol": symbol, "i": i, "ts": t + ONE_MINUTE_MS,
                        "price": candles[i][4], "atr": atr,
                        "side": res["signal"], "trade_type": res["trade_type"],
                        "strength": res["strength"],
                    })
        if not quiet and time.time() - t_report > 30:
            print(f"  ...{symbol}: i={i}/{last}, {len(out)} segnali", flush=True)
            t_report = time.time()
        i += stride
    print(f"  {symbol}: {steps} analisi, {len(out)} segnali", flush=True)
    return out


def _cache_path(cache_dir: str, kind: str, symbol: str, tag: str, ext: str) -> str:
    safe = symbol.replace("/", "_").replace(":", "_")
    return os.path.join(cache_dir, f"{kind}_{safe}_{tag}.{ext}")


def load_or_fetch_candles(symbol, total, end_ms, cache_dir, tag) -> list:
    if cache_dir:
        path = _cache_path(cache_dir, "candles", symbol, tag, "json.gz")
        if os.path.exists(path):
            with gzip.open(path, "rt") as f:
                data = json.load(f)
            print(f"  {symbol}: {len(data)} candele da cache")
            return data
    data = fetch_1m_history(symbol, total, end_ms=end_ms)
    print(f"  {symbol}: {len(data)} candele scaricate")
    if cache_dir and data:
        os.makedirs(cache_dir, exist_ok=True)
        with gzip.open(_cache_path(cache_dir, "candles", symbol, tag, "json.gz"), "wt") as f:
            json.dump(data, f)
    return data


def load_or_generate_signals(symbol, candles, stride, max_hold, cache_dir, tag) -> list:
    sig_tag = f"{tag}_s{stride}_h{max_hold}"
    if cache_dir:
        path = _cache_path(cache_dir, "signals", symbol, sig_tag, "json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            print(f"  {symbol}: {len(data)} segnali da cache")
            return data
    data = generate_signals(symbol, candles, stride, max_hold)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        with open(_cache_path(cache_dir, "signals", symbol, sig_tag, "json"), "w") as f:
            json.dump(data, f)
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────

def _pf(v: float) -> str:
    return "inf" if v == float("inf") else f"{v:.2f}"


def format_row(r: dict) -> str:
    return (f"{r['name']:<34} netto {r['return_pct']:+8.2f}% lordo {r['gross_return_pct']:+8.2f}% "
            f"comm {r['fees']:7.2f} dd {r['max_dd_pct']:5.2f}% n={r['trades']:5d} "
            f"vinc {r['win_rate']:4.1f}% pf {_pf(r['profit_factor']):>5} liq {r['liquidations']:3d} "
            f"leva {r['avg_leverage']:4.1f} nozion {r['avg_notional_pct']:5.1f}% "
            f"margine {r['avg_margin_pct']:4.1f}% peggiore {r['worst_trade_pct']:+6.2f}% "
            f"H1 {r['half_1_pct']:+7.2f} H2 {r['half_2_pct']:+7.2f}")


NOTICE_LABEL = ""


def notice(title: str, lines: list[str]) -> None:
    """Annotazione GitHub Actions (leggibile anche senza scaricare i log)."""
    if NOTICE_LABEL:
        title = f"[{NOTICE_LABEL}] {title}"
    msg = "%0A".join(line.replace("%", "%25").replace("\r", "").replace("\n", " ") for line in lines)
    print(f"::notice title={title}::{msg}")


def print_report(results: list[dict], scenario: str, annotate: bool) -> None:
    ranked = sorted(results, key=lambda r: r["return_pct"], reverse=True)
    print(f"\n===== Scenario {scenario}: classifica per rendimento netto =====")
    for r in ranked:
        print(format_row(r))
    if not annotate:
        return
    solid = [r for r in ranked if r["trades"] >= 100]          # sotto 100 operazioni e' rumore
    top = solid[:12]
    legacy = [r for r in ranked if r["name"].startswith("ATT")]
    shown, seen = [], set()
    for r in top + legacy[:3]:
        if r["name"] not in seen:
            seen.add(r["name"])
            shown.append(r)
    positive = sum(1 for r in solid if r["return_pct"] > 0)
    notice(f"Classifica {scenario} (top12 con >=100 operazioni + ATTUALE; {positive}/{len(solid)} in positivo)",
           [format_row(r) for r in shown])

    def detail(r: dict) -> list[str]:
        return [
            f"{r['name']}: per simbolo (USDT netti) {json.dumps(r['by_symbol'])}",
            f"per tipo {json.dumps(r['by_type'])}",
            f"uscite: SL {r['sl']} TP {r['tp']} timeout {r['timeout']} liquidazioni {r['liquidations']}",
            f"operazioni saltate: {json.dumps(r['skips'])}",
        ]
    if solid:
        notice(f"Dettaglio migliore {scenario}", detail(solid[0]))
    if legacy:
        notice(f"Dettaglio ATTUALE {scenario}", detail(legacy[0]))


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Simulatore storico profili di rischio/leva")
    ap.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    ap.add_argument("--candles", type=int, default=43200, help="candele 1m per simbolo (default 30 giorni)")
    ap.add_argument("--stride", type=int, default=5, help="minuti tra una analisi e la successiva")
    ap.add_argument("--offset-days", type=float, default=0.0, help="la finestra termina N giorni fa")
    ap.add_argument("--max-hold", type=int, default=720, help="uscita a tempo (barre 1m)")
    ap.add_argument("--scenarios", default="6:2",
                    help="coppie commissione_bps:slippage_bps separate da virgola (es. 6:2,0:0,6:10)")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--max-open", type=int, default=3)
    ap.add_argument("--max-daily-loss", type=float, default=5.0)
    ap.add_argument("--sweep", default="standard", choices=["standard", "legacy", "round2"])
    ap.add_argument("--cache-dir", default="")
    ap.add_argument("--out", default="risk_sim_results.json")
    ap.add_argument("--annotate", action="store_true", help="stampa annotazioni GitHub Actions")
    ap.add_argument("--label", default="", help="prefisso dei titoli delle annotazioni")
    args = ap.parse_args()
    global NOTICE_LABEL
    NOTICE_LABEL = args.label

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    end_ms = None
    if args.offset_days > 0:
        end_ms = int(time.time() * 1000 - args.offset_days * 86_400_000)
    tag = f"c{args.candles}_o{args.offset_days:g}"

    print(f"Simboli: {symbols} | candele {args.candles} | stride {args.stride} | max_hold {args.max_hold}")
    candles: dict[str, list] = {}
    signals: list[dict] = []
    data_diag: list[str] = []
    for sym in symbols:
        print(f"\n=== {sym} ===", flush=True)
        data = load_or_fetch_candles(sym, args.candles, end_ms, args.cache_dir, tag)
        if len(data) < WINDOW_SIZE * 60 + args.max_hold + 10:
            print(f"  [skip] storico insufficiente ({len(data)} candele)")
            continue
        candles[sym] = data
        data_diag.append(describe_candles(sym, data))
        print("  " + data_diag[-1], flush=True)
        signals.extend(load_or_generate_signals(sym, data, args.stride, args.max_hold, args.cache_dir, tag))
    if not candles:
        print("Nessun dato utilizzabile.", file=sys.stderr)
        sys.exit(1)

    span_days = 0.0
    if signals:
        span_days = (max(s["ts"] for s in signals) - min(s["ts"] for s in signals)) / 86_400_000
    sides = Counter(s["side"] for s in signals)
    kinds = Counter(s["trade_type"] for s in signals)
    info = data_diag + [f"simboli {list(candles)}", f"segnali totali {len(signals)} su {span_days:.1f} giorni",
            f"lato {dict(sides)} tipo {dict(kinds)}"]
    print("\n" + "\n".join(info))
    if args.annotate:
        notice("Dati e segnali", info)

    profiles = build_sweep(args.sweep)
    all_results: dict[str, list[dict]] = {}
    for scen in [s.strip() for s in args.scenarios.split(",") if s.strip()]:
        fee_bps, slip_bps = (float(x) for x in scen.split(":"))
        res = [run_portfolio(p, signals, candles, initial_capital=args.capital,
                             fee_frac=fee_bps / 10_000.0, slip_frac=slip_bps / 10_000.0,
                             max_hold=args.max_hold, max_open=args.max_open,
                             max_daily_loss_pct=args.max_daily_loss) for p in profiles]
        label = f"comm{fee_bps:g}bps-slip{slip_bps:g}bps"
        all_results[label] = res
        print_report(res, label, args.annotate)

    with open(args.out, "w") as f:
        json.dump({"args": vars(args), "signals": len(signals), "span_days": span_days,
                   "results": all_results}, f, indent=1)
    print(f"\nRisultati salvati in {args.out}")


if __name__ == "__main__":
    main()
