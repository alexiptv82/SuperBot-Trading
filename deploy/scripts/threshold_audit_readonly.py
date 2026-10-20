"""Read-only entry diagnostics; emit only allowlisted aggregate data."""
import collections
import datetime
import json
import math
from pathlib import Path
import re
import subprocess
import time


def read_json(path):
    try:
        with path.open() as stream:
            return json.load(stream)
    except Exception:
        return {}


def count_events(path, start, end):
    events, candidates, sources, calls, confidence = [collections.Counter() for _ in range(5)]
    bad = 0
    allowed = {"conf_bassa", "conf_bassa_macro", "macro_blocco", "rr_basso", "cooldown"}
    if not path.exists():
        return {"missing": True}
    with path.open() as stream:
        for line in stream:
            try:
                row = json.loads(line)
                ts = row.get("ts", row.get("open_ms", row.get("logged_ms", 0)))
                if not isinstance(ts, (int,float)) or not start <= ts < end:
                    continue
                ev = row.get("ev")
                if ev not in {"open", "close", "candidate", "claude_call", "split_fill", "split_cancel"}:
                    continue
                events[ev] += 1
                source = row.get("source") if row.get("source") in ("claude", "rules") else "unknown"
                if ev in ("open", "candidate"):
                    sources[ev+":"+source] += 1
                if ev == "candidate":
                    status = row.get("status", "")
                    label = status if status in allowed else "account_rejected" if status.startswith("rifiutata:") else "other"
                    candidates[label] += 1
                    conf = (row.get("features") or {}).get("conf")
                    if isinstance(conf,(int,float)) and math.isfinite(conf):
                        confidence[str(int(conf)//10*10)+"s:"+source] += 1
                if ev == "claude_call":
                    calls["parsed_ok" if row.get("ok") is True else "failed_or_unparsed"] += 1
                    if row.get("stop_reason") in ("max_tokens", "end_turn", "stop_sequence"):
                        calls[row["stop_reason"]] += 1
                    n = row.get("n_decisions")
                    if isinstance(n,int): calls["decisions_total"] += n
            except Exception:
                bad += 1
    return dict(events=dict(events),candidates=dict(candidates),sources=dict(sources),claude_calls=dict(calls),confidence_buckets=dict(confidence),bad_rows=bad)


def main():
    now = int(time.time()*1000)
    print(json.dumps({"checked_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"read_only":True}))
    for bot in ("hawk","bull"):
        root=Path('/opt/superbot-desk-data')/bot
        state=read_json(root/'state_v2.json'); hb=read_json(root/'heartbeat.json')
        account=state.get('main') or {}; budget=state.get('budget') or {}
        run_start=state.get('run_started_ms',now)
        limits=account.get('limits') or {}; positions=account.get('positions') or {}
        prices=state.get('last_prices') or {}
        equity=account.get('cash',0)+sum(p.get('total_margin',0)+p.get('side',0)*(prices.get(s,p.get('entry',0))-p.get('entry',0))*p.get('qty',0) for s,p in positions.items())
        cap=hb.get('daily_cap_usd',.7)
        spent=budget.get('spent',0) if budget.get('day')==time.strftime('%Y-%m-%d',time.gmtime(now/1000)) else 0
        report=dict(bot=bot,run_no=state.get('run_no'),cycle=hb.get('cycles'),last_end_ms=hb.get('last_end_ms'),heartbeat_age_seconds=round(now/1000-hb.get('ts',0)),paper=hb.get('exec_mode')=='paper',paused=hb.get('pause_requested'),trading_enabled=hb.get('trading_enabled'),open_positions=len(positions),current_run_closed=len(account.get('closed') or []),prices_available=len(prices),
                    halt_capital=equity<=limits.get('kill_equity',0),halt_daily=equity<=account.get('day_start_equity',0)*(1-limits.get('daily_stop',0)),
                    ai_budget_calls=budget.get('calls'),ai_budget_remaining_approx=round(cap-spent,4),ai_reserve_available=(cap-spent)>=.04,last_ai_call_ms=state.get('last_call_ms'),
                    macro_enforced=(hb.get('macro') or {}).get('enforce'),macro_blackout=(hb.get('macro') or {}).get('blackout'),hours_blocked=(hb.get('hours') or {}).get('blocked'),claude_schedule_allowed=(hb.get('claude_schedule') or {}).get('allowed'))
        report['pause_flag_exists']=(root/'pause.flag').exists()
        report['run_started_ms']=run_start
        report['cycle_interval_ms']=(hb.get('next_cycle_ms') or 0)-(hb.get('last_end_ms') or 0)
        report['position_limit']=limits.get('max_open')
        report['position_limit_reached']=len(positions)>=limits.get('max_open',999)
        used=sum(p.get('total_margin',0) for p in positions.values())
        report['margin_total_limit_reached']=used>=limits.get('max_margin_total',1e99)
        report['minimum_margin_available']=min(limits.get('max_margin_trade',0),limits.get('max_margin_total',0)-used,account.get('cash',0)*.95)>=limits.get('min_margin',0)
        report['active_cooldowns']={str(window):sum(now-t<window for t in (state.get('last_open_ms') or {}).values() if isinstance(t,(int,float))) for window in (600000,3600000)}
        statuses=collections.Counter()
        with (root/'learning_log.jsonl').open() as stream:
            for line in stream:
                try: row=json.loads(line)
                except ValueError: continue
                if row.get('ev')=='candidate' and row.get('ts',0)>=run_start:
                    reason=str(row.get('status','')).split(':',1)[-1]
                    known={"troppe posizioni aperte","margine disponibile troppo basso","stop troppo lontano (liquidazione verrebbe prima)","cassa insufficiente","capitale sotto la soglia minima","stop giornaliero raggiunto","stop loss obbligatorio","stop dal lato sbagliato","posizione gia' aperta su questa coppia"}
                    if str(row.get('status','')).startswith('rifiutata:'): statuses[reason if reason in known else 'other_redacted']+=1
        report['account_rejection_reasons']=dict(statuses)
        report['since_run_start']=count_events(root/'learning_log.jsonl',run_start,now+1)
        report['daily_utc']={}
        for day in range(12,21):
            dt=datetime.datetime(2026,10,day,tzinfo=datetime.timezone.utc)
            start=int(dt.timestamp()*1000)
            report['daily_utc'][dt.strftime('%Y-%m-%d')]=count_events(root/'learning_log.jsonl',start,min(start+86400000,now+1))
        since=datetime.datetime.fromtimestamp(run_start/1000,datetime.timezone.utc).isoformat()
        proc=subprocess.run(['docker','logs','--since',since,'superbot-desk-'+bot],capture_output=True,text=True,timeout=30)
        log=proc.stdout+proc.stderr
        tags=collections.Counter(re.findall(r'^\[([A-Za-z0-9_: ]+)\]',log,re.M))
        allowed_tags={'CONF_LOW','RR_LOW','COOLDOWN','HALT','FINESTRA','Claude','OPEN','CLOSE','SKIP','WARN','ORARI','PAUSA','MACRO_BLOCCO','MACRO_OSSERVATO','SLEEP','DESK V2'}
        report['log_error_counts']={k:log.count(k) for k in ('Traceback (most recent call last)', 'ERROR', '[WARN]', 'TimeoutError')}
        report['log_tags_since_run']={k:v for k,v in tags.items() if k in allowed_tags}
        report['confidence_rejections']=[dict(confidence=int(a),threshold=int(b),count=n) for (a,b),n in collections.Counter(re.findall(r'conf=(\d+) < soglia=(\d+)',log)).most_common(12)]
        report['latest_market_coverage']=re.findall(r'\[DESK V2\] (?:candles ok|readings validi): \d+/\d+ simboli',log)[-4:]
        print(json.dumps(report,sort_keys=True))


if __name__=='__main__': main()

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

import json
import math
import time
import urllib.request

BAR_MS = 900_000                       # candele da 15 minuti
MIN_N = 30                             # sotto questo i numeri sono solo indicativi
MIN_DAYS = 7                           # sotto questo i giorni coperti sono troppo pochi per dire "il filtro costa/protegge"
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
    if s["giorni"] < MIN_DAYS:
        return (f"solo {s['giorni']} giorni di dati (ne servono almeno {MIN_DAYS}, in mercati diversi): "
                "dipende dal mercato di quei giorni, non concludere")
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

"""Read-only research. Concatenate after analyst.py; never import the live engine."""
import collections
import datetime
import hashlib
import random
import statistics
from pathlib import Path

def stats(rows):
    if not rows: return {'n':0}
    rs=[r['r'] for r in rows]; days=sorted(set(r['day'] for r in rows))
    rng=random.Random(20261020); means=[]
    for _ in range(1500):
        sample=[r['r'] for d in rng.choices(days,k=len(days)) for r in rows if r['day']==d]
        means.append(statistics.mean(sample))
    means.sort(); wins=sum(r>0 for r in rs)
    return dict(n=len(rs),days=len(days),mean_net_R=round(statistics.mean(rs),4),win_rate=round(wins/len(rs),4),win_wilson95=wilson(wins,len(rs)),mean_day_bootstrap95=[round(means[37],4),round(means[1462],4)] if len(days)>1 else None,indicative=len(rs)<30 or len(days)<7)

def simulate(c,bars,now):
    f=c.get('features') or {}
    try:
        ts=int(c['ts']); side=int(c['side']); sl=float(f['dec_sl_pct']); tp=float(f['dec_tp_pct']); lev=int(f['dec_lev'])
        if side not in (-1,1) or not all(math.isfinite(v) and v>0 for v in (sl,tp,lev)): return None,'invalid_plan'
    except (KeyError,ValueError,TypeError): return None,'missing_plan'
    if 'split' in str(f.get('dec_action','')): return None,'split_not_reconstructed'
    start=(ts//BAR_MS+1)*BAR_MS
    horizon=HORIZON_BARS.get(f.get('dec_type'),96)
    by={int(b[0]):b for b in bars if b[0]+BAR_MS<=now}
    if start not in by: return None,'missing_first_closed_bar'
    # Explicit delayed-entry scenario, not an exact reconstruction of an unexecuted fill.
    price=by[start][1]; entry=price*(1+side*.0002)
    original=float(c.get('price') or 0)
    if not math.isfinite(original) or original<=0: return None,'missing_candidate_price'
    stop=original*(1-side*sl); take=original*(1+side*tp)
    if side*(price-stop)<=0 or side*(take-price)<=0: return None,'levels_crossed_before_delayed_entry'
    lev=min(max(1,lev),45 if c['symbol'] in ('BTC','XAU','XAG') else 30 if c['symbol']=='ETH' else 25)
    dist=abs(entry-stop)/entry
    if dist>.75*(1/lev-.005): return None,'engine_liquidation_guard'
    ambiguous=False; exitpx=None
    for i in range(horizon):
        t=start+i*BAR_MS
        if t not in by: return None,'censored_or_gap'
        _,op,hi,lo,cl,*_=by[t]
        hit_sl=lo<=stop if side==1 else hi>=stop
        hit_tp=hi>=take if side==1 else lo<=take
        if hit_sl:
            exitpx=min(stop,op) if side==1 else max(stop,op); ambiguous=hit_tp; break
        if hit_tp: exitpx=take; break
    if exitpx is None: exitpx=cl
    exitfill=exitpx*(1-side*.0002)
    hours=(i+1)*.25
    net=side*(exitfill-entry)-entry*.0006-exitfill*.0006-(entry*.0001*hours/8 if side==1 else 0)
    original_fill=original*(1+side*.0002)
    original_risk_fraction=abs(original_fill-stop)/original_fill
    return dict(r=net/(entry*original_risk_fraction),ambiguous=ambiguous),None

def measure_main():
    now=int(time.time()*1000); allc=[]; events={}; hashes={}; bad={}
    for bot in ('hawk','bull'):
        path=Path('/opt/superbot-desk-data')/bot/'learning_log.jsonl'
        blob=path.read_bytes(); hashes[bot]=hashlib.sha256(blob).hexdigest(); evs=[]; bad[bot]=0
        for line in blob.splitlines():
            try: evs.append(json.loads(line))
            except ValueError: bad[bot]+=1
        events[bot]=evs
        for e in evs:
            if e.get('ev')=='candidate': allc.append(dict(e,bot=bot))
    targets=[]; coverage=collections.Counter()
    for c in allc:
        f=c.get('features') or {}; conf=f.get('conf'); tier=c.get('symbol') in ('BTC','ETH','XAU','XAG')
        if not isinstance(conf,(int,float)): continue
        if status_head(c)!='conf_bassa': continue
        band='50-59_tier60' if tier and 50<=conf<60 else '60-69_tier70' if not tier and 60<=conf<70 else None
        if band: c['band']=band; targets.append(c); coverage[band]+=1
    uniq=dedupe(targets); candles={}
    for sym in sorted(set(c['symbol'] for c in uniq)):
        lo=min(c['ts'] for c in uniq if c['symbol']==sym)
        candles[sym]=fetch_range(sym,lo-BAR_MS,now,max_pages=16)
    groups=collections.defaultdict(list); excluded=collections.Counter(); ambiguous=0
    for c in uniq:
        lab,why=simulate(c,candles.get(c['symbol'],[]),now)
        if why: excluded[why]+=1; continue
        f=c.get('features') or {}; roc=f.get('btc_roc24h')
        regime='unknown' if not isinstance(roc,(int,float)) else 'calo' if roc<-.01 else 'rialzo' if roc>.01 else 'piatto'
        side='long' if c['side']==1 else 'short'; typ=f.get('dec_type','unknown')
        row=dict(lab,day=time.strftime('%Y-%m-%d',time.gmtime(c['ts']/1000)))
        ambiguous+=lab['ambiguous']
        for key in ('ALL',c['band'],'score:'+('60-64' if f.get('conf',0)<65 else '65-69'),'bot:'+c['bot'],'regime:'+regime,'side:'+side,'type:'+typ,'cross:'+regime+'/'+side+'/'+typ): groups[key].append(row)
    longs={}
    for bot,evs in events.items():
        per=collections.defaultdict(list)
        for e in evs:
            if e.get('ev')!='candidate' or time.strftime('%Y-%m-%d',time.gmtime(e.get('ts',0)/1000))!='2026-10-18': continue
            f=e.get('features') or {}
            if isinstance(f.get('sig_long'),(float,int)): per[e['symbol']].append(f)
        longs[bot]={s:dict(n=len(fs),long_min=min(f['sig_long'] for f in fs),long_max=max(f['sig_long'] for f in fs),short_max=max(f.get('sig_short',0) or 0 for f in fs),h4= dict(collections.Counter(str(f.get('ema50_200_4h')) for f in fs)),daily=dict(collections.Counter(str(f.get('daily_trend')) for f in fs))) for s,fs in per.items()}
    real={}; realexcluded=collections.Counter()
    for bot,evs in events.items():
        opened={}
        for e in evs:
            k=(e.get('run_no'),e.get('id'))
            if e.get('ev')=='open': opened[k]=e
            if e.get('ev')!='close' or not isinstance(e.get('net_r'),(int,float)): continue
            # Do not merge recycled ids without run identity; final closes only for complete trade stats.
            if k[0] is None: realexcluded['missing_run']+=1;continue
            key=(bot,)+k
            v=real.setdefault(key,dict(r=0,final=False,day=time.strftime('%Y-%m-%d',time.gmtime(e.get('ts',0)/1000)),side=e.get('side')))
            v['r']+=e['net_r']; v['final'] |= not e.get('partial',False)
    complete=[v for v in real.values() if v['final']]
    print(json.dumps(dict(kind='threshold_measurement',asof_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_sha256=hashes,bad_rows=bad,raw_target_counts=dict(coverage),deduped=len(uniq),excluded=dict(excluded),ambiguous_sl_first=ambiguous,groups={k:stats(v) for k,v in groups.items()},long_scores_oct18=longs,executed_complete=stats(complete),executed_to_oct15=stats([v for v in complete if v['day']<='2026-10-15']),executed_excluded=dict(realexcluded),executed_sides_to_oct15={str(s):sum(v['side']==s for v in complete if v['day']<='2026-10-15') for s in (1,-1)},method='delayed first-next-15m-open; original candidate SL/TP levels and planned risk denominator; fee6bp/side slip2bp/side long funding1bp/8h; no DCA/trailing/AI/split; horizons6h/24h; regime BTC trailing24h +/-1% known at decision; dedup4h per bot/run/symbol/side/status; day-cluster bootstrap1500; not portfolio P&L',candle_counts={s:len(v) for s,v in candles.items()}),sort_keys=True))

measure_main()
