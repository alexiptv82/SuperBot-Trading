"""Analista, parte 2: l'ESAMINATORE dei candidati scartati. SOLA LETTURA: non tocca il bot, il suo stato o il cervello.

Il bot scrive nel registro (learning_log.jsonl) anche le aperture che ha deciso ma NON eseguito ("candidati": cooldown,
confidenza bassa, R:R basso, blocco macro...). Qui si guarda come sarebbero andate, con i prezzi pubblici di mercato:
entrata al prezzo del candidato, stop e take profit decisi dal bot, candele da 15 minuti successive. Serve a misurare
se ogni filtro PROTEGGE (i candidati scartati avrebbero perso) o COSTA (avrebbero guadagnato).

Regole di onesta' (dette anche nel rapporto):
- e' una simulazione semplice: niente DCA, niente uscite di Claude, niente trailing, niente commissioni/slippage;
- se nella stessa candela si toccano stop e take profit si conta lo STOP (scelta prudente);
- un candidato ancora "aperto" (ne' stop ne' take profit toccati e l'orizzonte non e' finito) non si etichetta:
  contarlo a prezzo di mercato falserebbe il risultato;
- candidati quasi uguali (stesso simbolo/lato/stato nella stessa finestra) contano UNA volta: Claude puo' riproporre la
  stessa idea a ogni ora e il campione sembrerebbe piu' grande di quello che e';
- sotto 30 casi i numeri sono solo indicativi.

Solo libreria standard e nessuna sintassi recente: gira anche con il python di sistema del server.
"""
from __future__ import annotations

import json
import math
import time
import urllib.request

BAR_MS = 900_000                       # candele da 15 minuti
MIN_N = 30                             # sotto questo i numeri sono solo indicativi
HORIZON_BARS = {"scalp": 24, "medio": 96}   # 6 ore per gli scalp, 24 ore per gli altri
DEDUPE_MS = 4 * 3_600_000
BITGET = "https://api.bitget.com"


# ---------------------------------------------------------------- lettura registro
def read_jsonl(path: str) -> list:
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except OSError:
        pass
    return out


def status_head(c: dict) -> str:
    """Stato del candidato senza il dettaglio ('rifiutata:margine...' -> 'rifiutata')."""
    return str(c.get("status") or "?").split(":")[0]


def dedupe(cands: list, window_ms: int = DEDUPE_MS) -> list:
    """Tiene il primo di una serie di candidati simili (stesso bot, simbolo, lato, stato) entro `window_ms`."""
    last = {}
    out = []
    for c in sorted(cands, key=lambda x: x.get("ts") or 0):
        key = (c.get("bot"), c.get("run_no"), c.get("symbol"), c.get("side"), status_head(c))
        ts = c.get("ts") or 0
        if key in last and ts - last[key] < window_ms:
            continue
        last[key] = ts
        out.append(c)
    return out


# ---------------------------------------------------------------- etichettatura di un candidato
def label_candidate(c: dict, candles: list, horizon_bars=None) -> dict:
    """Come sarebbe andato. candles = [[ts_apertura, open, high, low, close, vol], ...] in ordine crescente.
    Ritorna {"ok": False, "why": ...} se non si puo' etichettare, altrimenti
    {"ok": True, "outcome": "tp"|"sl"|"timeout", "r": ..., "mfe_r": ..., "mae_r": ..., "bars": n, "ambiguous": bool}."""
    f = c.get("features") or {}
    try:
        entry, side = float(c["price"]), int(c["side"])
        sl = float(f.get("dec_sl_pct") or 0)
        tp = float(f.get("dec_tp_pct") or 0)
        ts = int(c["ts"])
    except (KeyError, TypeError, ValueError):
        return {"ok": False, "why": "dati mancanti"}
    if entry <= 0 or side not in (1, -1):
        return {"ok": False, "why": "dati non validi"}
    if sl <= 0:
        return {"ok": False, "why": "senza stop deciso"}
    if horizon_bars is None:
        horizon_bars = HORIZON_BARS.get(str(f.get("dec_type") or "medio"), HORIZON_BARS["medio"])
    bars = [k for k in candles if k[0] > ts][:horizon_bars]      # dalla prima candela che inizia DOPO il candidato
    if not bars:
        return {"ok": False, "why": "senza candele"}
    sl_px = entry * (1 - side * sl)
    tp_px = entry * (1 + side * tp) if tp > 0 else None
    mfe = mae = 0.0
    for n, (_t, _o, hi, lo, cl, *_rest) in enumerate(bars, 1):
        fav = ((hi - entry) if side == 1 else (entry - lo)) / entry / sl
        adv = ((entry - lo) if side == 1 else (hi - entry)) / entry / sl
        hit_sl = lo <= sl_px if side == 1 else hi >= sl_px
        hit_tp = tp_px is not None and (hi >= tp_px if side == 1 else lo <= tp_px)
        if hit_sl:                                               # stop e take profit nella stessa candela: conta lo stop
            return {"ok": True, "outcome": "sl", "r": -1.0, "mfe_r": round(mfe, 3),
                    "mae_r": round(max(mae, adv), 3), "bars": n, "ambiguous": bool(hit_tp)}
        mfe, mae = max(mfe, fav), max(mae, adv)
        if hit_tp:
            return {"ok": True, "outcome": "tp", "r": round(tp / sl, 3), "mfe_r": round(mfe, 3), "mae_r": round(mae, 3),
                    "bars": n, "ambiguous": False}
    if len(bars) < horizon_bars:
        return {"ok": False, "why": "non ancora risolto"}
    last = bars[-1][4]
    return {"ok": True, "outcome": "timeout", "r": round(side * (last - entry) / entry / sl, 3),
            "mfe_r": round(mfe, 3), "mae_r": round(mae, 3), "bars": len(bars), "ambiguous": False}


# ---------------------------------------------------------------- statistiche
def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 3), round(c + h, 3)


def _day(c: dict) -> int:
    return int((c.get("ts") or 0) // 86_400_000)


def summarize(labeled: list) -> dict:
    """labeled = [(candidato, etichetta ok)]. Riassunto di un gruppo. Oltre ai numeri semplici calcola quanto
    reggono se si toglie il giorno migliore (o peggiore): i candidati dello stesso giorno sono quasi lo stesso evento
    (un'unica mossa di mercato), quindi la media puo' dipendere da un solo giorno."""
    n = len(labeled)
    if not n:
        return {"n": 0}
    rs = [lab["r"] for _c, lab in labeled]
    wins = sum(1 for r in rs if r > 0)
    lo, hi = wilson(wins, n)
    by_day = {}
    for c, lab in labeled:
        by_day.setdefault(_day(c), []).append(lab["r"])
    without_best = without_worst = None
    if len(by_day) >= 2:
        best = max(by_day, key=lambda d: sum(by_day[d]))
        worst = min(by_day, key=lambda d: sum(by_day[d]))
        rest = [r for d, v in by_day.items() if d != best for r in v]
        rest_w = [r for d, v in by_day.items() if d != worst for r in v]
        without_best, without_worst = round(sum(rest) / len(rest), 3), round(sum(rest_w) / len(rest_w), 3)
    return {"n": n, "giorni": len(by_day), "r_senza_giorno_migliore": without_best,
            "r_senza_giorno_peggiore": without_worst,
            "tp": sum(1 for _c, lab in labeled if lab["outcome"] == "tp"),
            "sl": sum(1 for _c, lab in labeled if lab["outcome"] == "sl"),
            "timeout": sum(1 for _c, lab in labeled if lab["outcome"] == "timeout"),
            "ambigue": sum(1 for _c, lab in labeled if lab.get("ambiguous")),
            "win_rate": round(wins / n, 3), "win_lo": lo, "win_hi": hi,
            "r_medio": round(sum(rs) / n, 3), "r_totale": round(sum(rs), 2),
            "mfe_medio": round(sum(lab["mfe_r"] for _c, lab in labeled) / n, 3),
            "mae_medio": round(sum(lab["mae_r"] for _c, lab in labeled) / n, 3),
            "indicativo": n < MIN_N}


def verdict(s: dict) -> str:
    """Una riga di lettura prudente. Non e' una raccomandazione: serve a capire dove guardare."""
    if not s.get("n"):
        return "nessun caso etichettabile"
    if s["indicativo"]:
        return f"solo {s['n']} casi: troppo pochi per dire (servono almeno {MIN_N})"
    if s["giorni"] < 3:
        return f"solo {s['giorni']} giorni di dati: dipende dal mercato di quei giorni, non concludere"
    lo, hi = s["win_lo"], s["win_hi"]
    if s["r_medio"] > 0.15 and lo is not None and lo > 0.4:
        if s["r_senza_giorno_migliore"] is not None and s["r_senza_giorno_migliore"] > 0.1:
            return "il filtro sembra COSTARE: i candidati scartati avrebbero guadagnato (regge anche senza il giorno migliore)"
        return "positivo ma regge solo grazie a UN giorno: non e' una prova, non cambiare nulla"
    if s["r_medio"] < -0.15 and hi is not None and hi < 0.5:
        if s["r_senza_giorno_peggiore"] is not None and s["r_senza_giorno_peggiore"] < -0.1:
            return "il filtro sembra PROTEGGERE: i candidati scartati avrebbero perso (regge anche senza il giorno peggiore)"
        return "negativo ma dipende solo da UN giorno: non e' una prova, non cambiare nulla"
    return "nessuna differenza chiara: non cambiare nulla"


def conf_bucket(x):
    if x is None:
        return None
    return "<50" if x < 50 else "50-59" if x < 60 else "60-69" if x < 70 else "70-79" if x < 80 else "80+"


def group_by(items: list, key) -> dict:
    out = {}
    for c, lab in items:
        k = key(c)
        if k is not None:
            out.setdefault(str(k), []).append((c, lab))
    return out


# ---------------------------------------------------------------- candele pubbliche
def _http_get(url: str, timeout: int = 12) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_range(symbol: str, start_ms: int, end_ms: int, get=None, max_pages: int = 8) -> list:
    """Candele 15m pubbliche di Bitget tra start e end (a pagine da 1000, dalla piu' recente indietro). Mai solleva:
    se l'exchange non risponde ritorna quello che ha."""
    get = get or _http_get
    sym = symbol.upper()
    sym = sym if sym.endswith("USDT") else sym + "USDT"
    out = {}
    end = end_ms
    for _ in range(max_pages):
        url = (f"{BITGET}/api/v2/mix/market/history-candles?symbol={sym}&productType=USDT-FUTURES&granularity=15m"
               f"&startTime={start_ms}&endTime={end}&limit=200")
        try:
            d = json.loads(get(url))
        except Exception:
            break
        rows = d.get("data") if isinstance(d, dict) and d.get("code") == "00000" else None
        if not rows:
            break
        got = [[float(x) for x in r[:6]] for r in rows]
        for r in got:
            out[r[0]] = r
        oldest = min(r[0] for r in got)
        if oldest <= start_ms or len(got) < 2:
            break
        end = int(oldest) - 1
    return [out[k] for k in sorted(out)]


# ---------------------------------------------------------------- rapporto
def examine(events_by_bot: dict, candles_by_symbol: dict, now_ms: int = None) -> str:
    """Rapporto testuale sui candidati scartati. events_by_bot = {bot: [righe del registro]}."""
    now_ms = now_ms or int(time.time() * 1000)
    cands = []
    for bot, evs in events_by_bot.items():
        for e in evs:
            if e.get("ev") == "candidate":
                cands.append({**e, "bot": bot})
    uniq = dedupe(cands)
    labeled, skipped = [], {}
    for c in uniq:
        lab = label_candidate(c, candles_by_symbol.get(c.get("symbol"), []))
        if lab["ok"]:
            labeled.append((c, lab))
        else:
            skipped[lab["why"]] = skipped.get(lab["why"], 0) + 1
    L = []
    L.append("=" * 60)
    L.append("ESAMINATORE DEI CANDIDATI SCARTATI (simulazione semplice, sola lettura)")
    L.append(f"candidati nel registro: {len(cands)}  dopo aver unito i quasi uguali: {len(uniq)}  etichettati: {len(labeled)}"
             f"  non etichettabili: {skipped or 0}")
    L.append("entrata al prezzo del candidato, stop/TP decisi dal bot, candele 15m successive; se stop e TP nella stessa "
             "candela conta lo stop; niente DCA/uscite di Claude/commissioni.")
    if not labeled:
        L.append("Nessun candidato etichettabile per ora.")
        L.append("=" * 60)
        return "\n".join(L)

    def line(name, s):
        if not s["n"]:
            return f"  {name:<24} n=0"
        ic = f"{100 * s['win_lo']:.0f}-{100 * s['win_hi']:.0f}%" if s["win_lo"] is not None else "-"
        flag = " [IND]" if s["indicativo"] else ""
        return (f"  {name:<24} n={s['n']:<4} TP={s['tp']:<3} SL={s['sl']:<3} tempo={s['timeout']:<3} "
                f"win={100 * s['win_rate']:.0f}% IC95={ic:<9} R_medio={s['r_medio']:+.2f} R_tot={s['r_totale']:+.1f}"
                f" MFE={s['mfe_medio']:.2f} MAE={s['mae_medio']:.2f} gg={s['giorni']}"
                + (f" senza_top={s['r_senza_giorno_migliore']:+.2f}" if s.get("r_senza_giorno_migliore") is not None else "")
                + flag)

    L.append("\n== PER STATO (cosa ha scartato il filtro) ==")
    for k, v in sorted(group_by(labeled, status_head).items()):
        s = summarize(v)
        L.append(line(k, s))
        L.append(f"      -> {verdict(s)}")
    for title, key in (("PER LATO", lambda c: {1: "long", -1: "short"}.get(c.get("side"))),
                       ("PER CONFIDENZA (la confidenza distingue i buoni dai cattivi?)", lambda c: conf_bucket((c.get("features") or {}).get("conf"))),
                       ("PER GIORNO UTC (i casi sono concentrati in pochi giorni?)", lambda c: time.strftime("%Y-%m-%d", time.gmtime((c.get("ts") or 0) / 1000))),
                       ("PER BOT", lambda c: c.get("bot")),
                       ("PER SIMBOLO (n>=5)", lambda c: c.get("symbol")),
                       ("PER REGIME MACRO", lambda c: (c.get("features") or {}).get("macro_regime")),
                       ("PER VERSIONE CODICE", lambda c: c.get("code_version"))):
        groups = group_by(labeled, key)
        if title.startswith("PER SIMBOLO"):
            groups = {k: v for k, v in groups.items() if len(v) >= 5}
        if len(groups) <= 1:
            continue
        L.append(f"\n== {title} ==")
        for k, v in sorted(groups.items()):
            L.append(line(k, summarize(v)))
    L.append("\n== TUTTI ==")
    L.append(line("tutti i candidati", summarize(labeled)))

    # confronto con cio' che il bot ha davvero eseguito (R reale netto, dalle chiusure del registro)
    real, real_side = {}, {}
    for bot, evs in events_by_bot.items():
        for e in evs:
            if e.get("ev") == "close" and e.get("net_r") is not None:
                k = (bot, e.get("run_no"), e.get("id"))
                real.setdefault(k, 0.0)
                real[k] += float(e["net_r"])
                real_side.setdefault(k, e.get("side"))
    if real:
        rv = list(real.values())
        L.append(f"\n== PER CONFRONTO: trade eseguiti (R reale netto, con commissioni) ==\n  n={len(rv)}  R_medio={sum(rv) / len(rv):+.2f}"
                 f"  win={100 * sum(1 for r in rv if r > 0) / len(rv):.0f}%")
        for lato, nome in ((1, "long"), (-1, "short")):
            vals = [real[k] for k in real if real_side.get(k) == lato]
            if vals:
                L.append(f"  {nome:<8} n={len(vals):<4} R_medio={sum(vals) / len(vals):+.2f}  win={100 * sum(1 for r in vals if r > 0) / len(vals):.0f}%")
    L.append("=" * 60)
    return "\n".join(L)
