"""Prova dal vivo (SOLA LETTURA) del codice NUOVO per trend 1d e dati OI/long-short.
Gira dentro un contenitore usa-e-getta dell'immagine dei bot, con il codice del commit montato in sola lettura.
Non apre ordini, non ha chiavi, non scrive dati dei bot. Scarica solo dati pubblici di Bitget."""
import time

import numpy as np

from desk import cli, signals
from desk import market_context as mc

now = int(time.time() * 1000)
syms = list(cli.SYMBOLS)
print("simboli:", len(syms))

# 1) trend giornaliero: tempo e risultato per tutti i simboli, esattamente come lo fa il ciclo del bot
t0 = time.time()
ok = short = 0
bull = bear = 0
lens = []
for s in syms:
    arr = cli.daily_bars(s, now)
    lens.append(len(arr))
    if len(arr) >= signals.DAILY_MIN_BARS:
        ok += 1
        cd = arr[:, 4]
        if signals.ema(cd, 50)[-1] > signals.ema(cd, 200)[-1]:
            bull += 1
        else:
            bear += 1
    else:
        short += 1
print("1D: simboli con >=%d barre chiuse: %d su %d | corti/assenti: %d | trend bull %d bear %d | tempo %.1fs" % (
    signals.DAILY_MIN_BARS, ok, len(syms), short, bull, bear, time.time() - t0))
print("1D: barre per simbolo:", dict(zip(syms, lens)))
t1 = time.time()
cli.daily_bars(syms[0], now)
print("1D: seconda lettura dalla cache: %.3fs" % (time.time() - t1))

# 2) OI e long/short, esattamente come li scarica il bot ogni 30 minuti
t0 = time.time()
ctx = mc.fetch_all_context(syms, now)
print("CTX: tempo %.1fs | funding %d/%d | OI %d/%d | L/S %d/%d" % (
    time.time() - t0, len(ctx["funding"]), len(syms), len(ctx["oi"]), len(syms), len(ctx["ls_ratio"]), len(syms)))
for s in ("BTC", "ETH", "SOL", "XAU"):
    print("CTX", s, "| OI:", getattr(ctx["oi"].get(s), "note", None), "| L/S:", getattr(ctx["ls_ratio"].get(s), "note", None))
missing_oi = [s for s in syms if s not in ctx["oi"]]
missing_ls = [s for s in syms if s not in ctx["ls_ratio"]]
print("CTX: senza OI:", missing_oi, "| senza L/S:", missing_ls)

# 3) la variazione 24h dell'OI: simulazione con una lettura di 24 ore fa pari al 95% di quella di oggi
rows = {k: dict(vars(v)) for k, v in ctx["oi"].items()}
hist = {k: [[now - 24 * 3_600_000, v["oi_usd"] * 0.95]] for k, v in rows.items()}
mc.apply_oi_history(rows, hist, now)
print("OI-STORICO (simulato +5.3%%):", {k: rows[k]["oi_change_24h"] for k in list(rows)[:4]})
