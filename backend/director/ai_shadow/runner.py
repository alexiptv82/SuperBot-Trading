"""Processo dell'AI in ombra: a ogni chiusura di barra da 15 minuti esegue un ciclo del pilota.

Uscita in <out-root>/ai/: state.json (conto, ordini in attesa), status.json (battito, spesa, esiti), cycles-*.jsonl,
trades-*.jsonl, prompts-*.jsonl.gz, spend.jsonl. Per fermare le chiamate senza fermare il container: creare il file
<out-root>/ai/pause.flag (le posizioni aperte restano gestite da stop e TP del conto virtuale).
La chiave del modello arriva SOLO dalla variabile d'ambiente DEEPSEEK_API_KEY e non viene mai stampata ne' scritta.
"""
import argparse
import json
import os
import sys
import time

from .config import Config
from .market import BarCache
from .pilot import Pilot


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", default="/out")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args(argv)
    cfg = Config()
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    out_dir = os.path.join(args.out_root, "ai")
    pilot = Pilot(cfg, out_dir, key, BarCache(cfg))
    print("[AI-OMBRA] avviata: %s %s, %d simboli, tetto %.2f$/giorno %.1f$/mese, chiave %s" % (
        cfg.name, cfg.model, len(cfg.symbols), cfg.daily_cap_usd, cfg.monthly_cap_usd,
        "presente" if key else "ASSENTE"), flush=True)
    while True:
        now = int(time.time() * 1000)
        try:
            line = pilot.run_once(now)
            d = line["decision"]
            print("[AI-OMBRA] barra %d simboli %d chiamata %s %s equity %.2f aperte %d eventi %s" % (
                line["bar_t"], line["bars_ok"], d.get("called"), d.get("skip") or d.get("error") or
                ("%d voci" % d.get("n_items", 0)), line["equity"], line["open"],
                json.dumps([e["ev"] for e in line["events"]], separators=(",", ":"))), flush=True)
        except Exception as e:           # il processo non si ferma mai per un ciclo andato male
            print("[AI-OMBRA ERRORE] %s %s" % (type(e).__name__, str(e)[:200]), flush=True)
        if args.once:
            return 0
        nxt = (int(time.time() * 1000) // cfg.bar_ms + 1) * cfg.bar_ms + cfg.delay_ms
        time.sleep(max(1.0, (nxt - time.time() * 1000) / 1000))


if __name__ == "__main__":
    sys.exit(main())
