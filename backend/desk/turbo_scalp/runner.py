"""Processo dell'ombra Turbo Scalp: a ogni chiusura di barra da 5 minuti scarica le candele pubbliche BitGet
(nessuna chiave), applica `strategy.step` e registra gli eventi. Nessun ordine, nessun accesso ai dati dei bot.

Uscita in <out-root>/turbo/:
  events-YYYY-MM-DD.jsonl  una riga per ciclo con eventi (append-only; ogni evento ha un id stabile: se il
                           processo cade tra il registro e lo stato, al riavvio un evento puo' ripetersi e chi
                           legge deduplica per id)
  state.json               posizioni e segnali ipotetici aperti, ultima barra per simbolo (scrittura atomica)
  status.json              battito: ts_ms, ultimo ciclo riuscito, errori per simbolo (per il healthcheck)
"""
import argparse
import json
import os
import sys
import time
import urllib.request

from . import strategy

BASE = "https://api.bitget.com"
DELAY_MS = 15_000          # si scarica 15 s dopo la chiusura della barra
LIMIT = 300


def fetch_closed_bars(symbol, now_ms, cfg, opener=urllib.request.urlopen, base=BASE):
    """Barre 5m CHIUSE ordinate e senza duplicati. Controllo dell'orologio: l'ultima riga deve essere la barra
    in formazione (o quella appena chiusa); altrimenti la serie non si usa."""
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym += "USDT"
    url = (f"{base}/api/v2/mix/market/candles?symbol={sym}&productType=USDT-FUTURES"
           f"&granularity=5m&limit={LIMIT}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with opener(req, timeout=10) as r:
        payload = json.loads(r.read())
    if not isinstance(payload, dict) or payload.get("code") != "00000" or not isinstance(payload.get("data"), list):
        raise ValueError("risposta rifiutata")
    rows = {}
    for r in payload["data"]:
        t = int(float(r[0]))
        rows[t] = (t, float(r[1]), float(r[2]), float(r[3]), float(r[4]))
    bars = [rows[t] for t in sorted(rows)]
    if not bars:
        raise ValueError("nessuna barra")
    newest = bars[-1][0]
    if not (now_ms - 2 * cfg.bar_ms < newest <= now_ms):
        raise ValueError("orologio delle candele non coerente")
    return [b for b in bars if b[0] + cfg.bar_ms <= now_ms]


def _atomic_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_state(path, cfg):
    try:
        with open(path) as f:
            st = json.load(f)
        if st.get("schema") == strategy.SCHEMA and st.get("config_hash") == strategy.config_hash(cfg):
            return st, None
        return strategy.new_state(cfg), "configurazione cambiata: si riparte senza posizioni ipotetiche"
    except FileNotFoundError:
        return strategy.new_state(cfg), None
    except (OSError, ValueError):
        return strategy.new_state(cfg), "stato illeggibile: si riparte senza posizioni ipotetiche"


def run_once(out_dir, cfg, now_ms, fetch=fetch_closed_bars):
    os.makedirs(out_dir, exist_ok=True)
    state_path = os.path.join(out_dir, "state.json")
    st, note = load_state(state_path, cfg)
    bars, errors = {}, {}
    for sym in cfg.symbols:
        try:
            bars[sym] = fetch(sym, now_ms, cfg)
        except Exception as e:          # un simbolo che non risponde resta indietro e recupera al giro dopo
            errors[sym] = str(e)[:80]
    new, events = strategy.step(st, bars, cfg)
    if note:
        events.insert(0, {"ev": "ripartenza", "id": "ripartenza:%d" % now_ms, "why": note})
    if events:
        day = time.strftime("%Y-%m-%d", time.gmtime(now_ms / 1000))
        line = {"schema": strategy.SCHEMA, "ts_ms": now_ms, "algo": strategy.algo(cfg), "mode": "ombra",
                "applied": False, "events": events}
        with open(os.path.join(out_dir, "events-%s.jsonl" % day), "a") as f:
            f.write(json.dumps(line, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())
    _atomic_json(state_path, new)
    _atomic_json(os.path.join(out_dir, "status.json"),
                 {"ts_ms": now_ms, "last_success_ms": now_ms, "algo": strategy.algo(cfg), "mode": "ombra",
                  "applied": False, "open": len(new["open"]), "pending": len(new["pending"]),
                  "symbols_ok": len(bars), "errors": errors})
    return new, events


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default="/out")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args(argv)
    cfg = strategy.Config()
    out_dir = os.path.join(args.out_root, "turbo")
    print("[TURBO] ombra avviata: %s %s, simboli %s" % (cfg.name, cfg.version, ",".join(cfg.symbols)), flush=True)
    while True:
        now = int(time.time() * 1000)
        try:
            _, events = run_once(out_dir, cfg, now)
            for e in events:
                if e["ev"] in ("fill", "exit", "buco", "ripartenza"):
                    print("[TURBO] %s" % json.dumps(e, separators=(",", ":")), flush=True)
        except Exception as e:          # il processo non si ferma mai per un ciclo andato male
            print("[TURBO ERRORE] %s" % str(e)[:200], flush=True)
        if args.once:
            return 0
        nxt = (int(time.time() * 1000) // cfg.bar_ms + 1) * cfg.bar_ms + DELAY_MS
        time.sleep(max(1.0, (nxt - time.time() * 1000) / 1000))


if __name__ == "__main__":
    sys.exit(main())
