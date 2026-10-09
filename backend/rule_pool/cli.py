"""Riga di comando del pool: `python -m rule_pool.cli once|loop|report --data-dir DIR`.

`loop` gira per sempre (un giro ogni 15 minuti, poco dopo la chiusura della candela) e non
si ferma per un errore: lo registra e riprova al giro dopo. Solo dati pubblici.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from rule_pool import runner
from rule_pool.journal import Journal, ParamsChangedError
from rule_pool.rules import initial_rules

RUN_OFFSET_MS = 20_000          # secondi dopo la chiusura della candela prima di leggerla


def next_run_ms(now_ms: int) -> int:
    """Prossimo giro: il prossimo multiplo di 15 minuti piu' un piccolo margine."""
    return (now_ms // runner.M15 + 1) * runner.M15 + RUN_OFFSET_MS


def open_journal(data_dir: str) -> Journal:
    os.makedirs(data_dir, exist_ok=True)
    return Journal(os.path.join(data_dir, "pool.db"))


def iteration(journal: Journal, data_dir: str, notify, fetch=runner.fetch_bitget,
              now_ms: int | None = None) -> dict | None:
    """Un giro protetto: ritorna il risultato o None se e' fallito (errore stampato)."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    try:
        store = runner.CandleStore(os.path.join(data_dir, "candles"))
        res = runner.run_once(journal, initial_rules(), store, fetch, now_ms, notify=notify)
        bad = ", ".join(f"{s}: {m}" for s, m in sorted(res["errors"].items())) or "ok"
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now_ms / 1000))}Z] giro fatto; "
              f"allarme={res['alarm']}; dati: {bad}", flush=True)
        return res
    except ParamsChangedError as exc:
        print(f"ERRORE parametri regola cambiati senza nuova versione: {exc}", flush=True)
        if notify is not None and journal.get_meta("params_alert") is None:
            journal.set_meta("params_alert", "1")
            notify("Pool regole: parametri cambiati senza nuova versione, il runner non scrive")
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE giro fallito: {type(exc).__name__}: {str(exc)[:150]}", flush=True)
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["once", "loop", "report"])
    ap.add_argument("--data-dir", default=os.getenv("POOL_DATA_DIR", "data/pool"))
    ap.add_argument("--no-telegram", action="store_true")
    args = ap.parse_args(argv)
    journal = open_journal(args.data_dir)
    if args.command == "report":
        print(runner.render_report(journal, initial_rules()))
        return 0
    notify = None if args.no_telegram else runner.telegram_sender()
    print(f"pool avviato; telegram={'si' if notify else 'no'}; dati in {args.data_dir}", flush=True)
    if args.command == "once":
        res = iteration(journal, args.data_dir, notify)
        if res is not None:
            print(runner.render_report(journal, initial_rules(), res))
        return 0 if res is not None else 1
    while True:
        iteration(journal, args.data_dir, notify)
        now = int(time.time() * 1000)
        time.sleep(max(1.0, (next_run_ms(now) - now) / 1000.0))


if __name__ == "__main__":
    sys.exit(main())
