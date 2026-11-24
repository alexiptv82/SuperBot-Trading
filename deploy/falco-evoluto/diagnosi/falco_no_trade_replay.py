"""Diagnosi in SOLA LETTURA dei NO_TRADE di Falco Evoluto: rigioca le regole REALI sulle candele pubbliche Bitget.

Per ogni giro da 15 minuti nella finestra richiesta e per ogni simbolo della configurazione della run:
* candele chiuse dei timeframe della vista di mercato (come ``wiring``: minimo della vista + 24, 4h almeno 300);
* regime con ``regime_for_context`` (stessa funzione del runner), poi ``falco_evoluto.evaluate`` (stesse regole);
* conteggio dei motivi (regime, punteggio, conflitto, dati) e, per i casi bloccati dal punteggio, quanto mancava.
Non legge e non scrive le run, non chiama l'AI, nessuna chiave: solo GET pubblici. Il prezzo e' la chiusura dell'ultima
candela 1h chiusa (il runner usa l'ultimo minuto: differenza minima, dichiarata nell'uscita). I limiti di rischio NON
sono rigiocati: un'apertura proposta dalle regole puo' ancora essere rifiutata dal RiskManager (vedi il journal).

Ogni segnale e' confrontato con lo stop massimo apribile dai limiti della run (leva minima e perdita/margine).

Uso: PYTHONPATH=. python3 falco_no_trade_replay.py <runner_config.json> <da_ms> <a_ms>
"""
from __future__ import annotations

import collections
import json
import sys
import time
from decimal import Decimal

from backend.v3.brain_market.view import min_bars, regime_for_context
from backend.v3.brain_market.params import load_default_params as load_market_params
from backend.v3.falco_evoluto import ENTRY_TIER_A, ENTRY_TIER_C, TIER_A, evaluate
from backend.v3.lab_tools.fetch_candles import http_json
from backend.v3.runner.feed import fetch_closed_bars
from backend.v3.runner.wiring import EXTRA_KEEP, FALCO_4H_KEEP

SLOT = 15 * 60_000


def get_json(url: str):
    """Client del progetto (ritardo minimo e nuovi tentativi su 429/5xx) piu' una pausa: stesso IP dei runner."""
    time.sleep(0.5)
    return http_json(url)


def main() -> None:
    cfg = json.loads(open(sys.argv[1]).read())
    start, end = int(sys.argv[2]) // SLOT * SLOT, int(sys.argv[3]) // SLOT * SLOT
    vp = load_market_params()
    keep = {s.name: (s.candle_ms, min_bars(s, vp.indicators) + EXTRA_KEEP) for s in vp.timeframes}
    keep["4h"] = (keep["4h"][0], max(keep["4h"][1], FALCO_4H_KEEP))
    rp = cfg["risk_policy"]
    # RiskManager (risk.py): leva * (stop + costi) <= max_loss_margin_fraction, con leva >= min_leverage
    stop_max = (Decimal(rp["max_loss_margin_fraction"]) / Decimal(rp["min_leverage"])
                - Decimal(rp["estimated_roundtrip_cost_bp"]) / Decimal(10000))
    print(f"FALCO_REPLAY limite: stop massimo apribile {float(stop_max) * 100:.2f} % (perdita allo stop <= "
          f"{float(rp['max_loss_margin_fraction']) * 100:.0f} % del margine a leva >= {rp['min_leverage']}x, costi "
          f"{rp['estimated_roundtrip_cost_bp']} bp)")
    blocked = 0
    stops: list = []
    codes, regimes = collections.Counter(), collections.Counter()
    best = {}
    per_symbol = collections.defaultdict(collections.Counter)
    for sym in cfg["symbols"]:
        series = {}
        for tf, (step, n) in keep.items():
            series[tf] = fetch_closed_bars(sym, start - n * step, end, candle_ms=step, get_json=get_json)
        for t in range(start, end + 1, SLOT):
            bars = {tf: [b for b in series[tf] if b.open_time_ms + keep[tf][0] <= t][-keep[tf][1]:] for tf in keep}
            try:
                regime = regime_for_context(bars, timestamp_ms=t, params=vp)
            except ValueError:
                regime = "VIEW_ERROR"
            regimes[regime] += 1
            if regime in ("UNKNOWN", "VIEW_ERROR") or not bars.get("1h"):
                codes["nessuna_decisione_dati"] += 1
                per_symbol[sym]["nessuna_decisione_dati"] += 1
                continue
            ev = evaluate(sym, regime, float(bars["1h"][-1].close), bars["1h"], bars["4h"])
            codes[ev.code] += 1
            if ev.stop_fraction is not None:
                stops.append(Decimal(str(ev.stop_fraction)))
            if ev.side:
                print(f"FALCO_REPLAY segnale {sym} {'LONG' if ev.side == 1 else 'SHORT'} a "
                      f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(t / 1000))} UTC: long {ev.long_score}, "
                      f"short {ev.short_score}, regime {regime}, consulto AI {list(ev.consult) or 'no'}, "
                      f"stop {ev.stop_fraction * 100:.2f} % -> "
                      f"{'apribile' if Decimal(str(ev.stop_fraction)) <= stop_max else 'RIFIUTATO dai limiti'}")
                blocked += Decimal(str(ev.stop_fraction)) > stop_max
            per_symbol[sym][ev.code] += 1
            thr = ENTRY_TIER_A if sym in TIER_A else ENTRY_TIER_C
            top = max(ev.long_score, ev.short_score)
            if sym not in best or top > best[sym][0]:
                best[sym] = (top, thr, ev.long_score, ev.short_score, regime, t, ev.facts.get("trend_4h"),
                             ev.facts.get("trend_1d"), ev.facts.get("bars_4h"), ev.facts.get("days_1d"))
    total = sum(codes.values())
    print(f"FALCO_REPLAY finestra {start}..{end} ms, {total} valutazioni ({len(cfg['symbols'])} simboli x giri da 15 min)")
    print("FALCO_REPLAY motivi:", json.dumps(dict(codes.most_common()), sort_keys=False))
    print(f"FALCO_REPLAY segnali rifiutati dal limite margine/stop: {blocked} su {codes['falco_short_signal'] + codes['falco_long_signal']}")
    if stops:
        ok = sum(1 for x in stops if x <= stop_max)
        srt = sorted(stops)
        print(f"FALCO_REPLAY stop ATR (1,2 x ATR 1h) su tutte le valutazioni: mediana {float(srt[len(srt) // 2]) * 100:.2f} %, "
              f"entro il massimo apribile {ok} su {len(stops)} ({ok * 100 // len(stops)} %)")
    print("FALCO_REPLAY regimi:", json.dumps(dict(regimes.most_common()), sort_keys=False))
    for sym in cfg["symbols"]:
        b = best.get(sym)
        print(f"FALCO_REPLAY {sym}: {dict(per_symbol[sym])}")
        if b:
            print(f"FALCO_REPLAY {sym}: punteggio massimo {b[0]} (soglia {b[1]}; long {b[2]}, short {b[3]}) "
                  f"regime {b[4]} a {b[5]}; trend 4h {b[6]}, 1d {b[7]}; barre 4h {b[8]}, giorni {b[9]}")


if __name__ == "__main__":
    main()
