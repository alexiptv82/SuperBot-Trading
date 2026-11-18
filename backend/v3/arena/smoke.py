"""Prova a secco di UN ciclo delle tre AI, sulle COPIE delle run e con un modello finto che risponde NO_TRADE.

Verifica sul VPS, senza spendere e senza toccare la gara: feed Bitget reale, regole di contratto, vista di mercato
sui 27 simboli, percorso di attivazione (T0 comune, mandati, pause) e passaggio fino alla decisione. Le run vere non
vengono mai scritte: si copiano con il backup a caldo in una cartella temporanea, che viene eliminata alla fine.
Nessuna chiave letta, nessuna chiamata a DeepSeek/OpenRouter (il trasporto e' un finto locale).

Uso: DESK_MODE=paper python -m backend.v3.arena.smoke --day AAAA-MM-GG [--root /opt/superbot-ai-arena-paper]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from backend.v3.arena import backup as BK
from backend.v3.arena import runner as R
from backend.v3.arena import trial_setup as TS
from backend.v3.brain_f3.providers import TransportResponse
from backend.v3.lab_tools.fetch_candles import http_json
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.exit_worker import build_exit_worker


class NoTradeModel:
    """Trasporto finto: nessuna rete, risposta sempre NO_TRADE, uso dichiarato zero."""

    def __init__(self):
        self.calls = 0

    def __call__(self, payload):
        self.calls += 1
        return TransportResponse(200, {"choices": [{"finish_reason": "stop",
                                                    "message": {"content": json.dumps({"kind": "NO_TRADE"})}}],
                                       "usage": {"prompt_tokens": 0, "completion_tokens": 0}})


def run_smoke(root: Path, day: date, *, now_fn: Callable[[], int], get_json=http_json,
              view_params=None, workdir: Optional[Path] = None) -> dict:
    report = TS.inspect(root, day, now_fn())
    if report["stage"] != "PREPARED_PAUSED_NO_T0":
        raise TS.SetupRefused("smoke_needs_prepared_runs")
    tmp = Path(tempfile.mkdtemp(prefix="arena-smoke-", dir=workdir))
    try:
        copy_root = tmp / "copy"
        BK.snapshot_all(root, day, copy_root)                        # copia coerente, verificata
        for f in copy_root.rglob("backup_manifest.json"):
            f.unlink()                                                # nella copia la run deve sembrare intatta
        plans = TS._plans(copy_root, day)
        exits = {}
        now = now_fn()
        for p, plan in plans.items():
            cfg = load_runner_config((plan.folder / "runner_config.json").read_bytes())
            exits[p] = build_exit_worker(data_dir=plan.folder, run_id=plan.run_id, config=cfg, get_json=get_json)
            exits[p].start()
            exits[p].tick(now)
        stop = threading.Event()

        def keep_exits_alive():                          # come in produzione: tick continuo (ogni 5 s)
            while not stop.wait(5):
                for w in exits.values():
                    try:
                        w.tick(now_fn())
                    except Exception:
                        pass
        pump = threading.Thread(target=keep_exits_alive, daemon=True)
        pump.start()
        try:
            symbols = list(load_runner_config((plans["qwen"].folder / "runner_config.json").read_bytes()).symbols)
            snap = tmp / "universe-smoke.json"
            snap.write_text(json.dumps({"schema": "arena_universe_snapshot_v1", "symbols": symbols,
                                        "crypto_target_met": True, "as_of_ms": now}))
            TS.activate(copy_root, day, t0_ms=now, now_ms=now, desk_mode="paper",
                        confirm=f"{TS.ACTIVATE_PREFIX}{now}", approved_by="smoke-copy",
                        universe_snapshot=snap, approved_total_budget_usd="18")
            out = {}
            for p, plan in plans.items():
                model = NoTradeModel()
                kw = {} if view_params is None else {"view_params": view_params}
                built = R.build_arena_runner(plan, environ={"DESK_MODE": "paper"}, clock_ms=now_fn,
                                             get_json=get_json, inner_transport=model, **kw)
                t = built.runner.tick(now_fn())
                cyc = t.cycle
                out[p] = {"state": t.state, "last_error": t.last_error, "model_calls": model.calls,
                          "decisions": 0 if cyc is None else len(cyc.decisions),
                          "opened": 0 if cyc is None else len(cyc.opened),
                          "errors_by_code": dict(Counter(c for _, c in (cyc.errors if cyc else ()))),
                          "symbols_with_errors": sorted({s for s, _ in (cyc.errors if cyc else ())}),
                          "symbols": len(symbols)}
        finally:
            stop.set()
            pump.join(timeout=30)
            for w in exits.values():
                w.stop()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    after = TS.inspect(root, day, now_fn())
    return {"schema": "arena_smoke_v1", "providers": out, "real_runs_stage_after": after["stage"],
            "real_runs_untouched": after["stage"] == "PREPARED_PAUSED_NO_T0",
            "paid_inference": False, "network_ai_calls": 0}


def main(argv=None, *, now_fn=lambda: int(time.time() * 1000), get_json=http_json) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/opt/superbot-ai-arena-paper")
    ap.add_argument("--day", required=True)
    a = ap.parse_args(argv)
    try:
        res = run_smoke(Path(a.root), date.fromisoformat(a.day), now_fn=now_fn, get_json=get_json)
    except Exception as exc:                                          # codice breve, mai percorsi o segreti
        print(json.dumps({"ok": False, "code": (str(exc) or type(exc).__name__)[:80]}))
        return 2
    print(json.dumps({"ok": True, **res}, indent=1, sort_keys=True))
    ok = res["real_runs_untouched"] and all(v["state"] == "running" and v["opened"] == 0
                                            for v in res["providers"].values())
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
