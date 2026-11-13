#!/usr/bin/env python3
"""Replay di COLLAUDO: esegue il vero desk.cli.run_cycle di un checkout su candele REALI Bitget USDT-FUTURES
(scaricate con fetch_bitget_futures_history.py del ramo work/toro-long-mirror-15m-20261113). Offline, PAPER,
nessun ordine, nessuna rete: fetch_candles/fetch_history_page/contesto/Claude sono sostituiti.

Serve a due cose: (1) confronto SHORT-by-SHORT di Falco fra due versioni sullo stesso flusso; (2) comportamento
di Toro gemello sulle regole reali. Con CLAUDE=1 le risposte di "Claude" sono decisioni pseudo-casuali
deterministiche (stesse in ogni versione): servono a coprire il percorso Claude, NON misurano una strategia.

Uso: python deploy/scripts/replay_classics_twin_real.py TREE DATA OUT PORTFOLIO START_MS END_MS STEP_MIN CLAUDE [ENV=VAL ...]
"""
import json
import os
import sys
import tempfile

tree, data, out, portfolio, start, end, step, claude = sys.argv[1:9]
start, end, step, claude = int(start), int(end), int(step) * 60_000, claude == "1"
work = tempfile.mkdtemp(prefix="twin_")
os.environ.update({"DESK_PORTFOLIO": portfolio, "DESK_MODE": "paper", "DESK_DATA_DIR": work,
                   "DESK_DEEPSEEK_CLASSICS": "0"})
for k in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "DESK_LONG_S25", "DESK_S25_TORO_ENTRY_APPROVED",
          "DESK_HAWK_ENTRY_MODE", "DESK_BULL_TWIN_MODE"):
    os.environ.pop(k, None)
for kv in sys.argv[9:]:
    k, v = kv.split("=", 1)
    os.environ[k] = v
sys.path.insert(0, os.path.join(tree, "backend"))

import numpy as np  # noqa: E402
from desk import cli  # noqa: E402
import desk.market_context as mc  # noqa: E402

M15, H4 = 900_000, 14_400_000
SYMS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
A = {s: np.loadtxt(f"{data}/{f}_15m.csv", delimiter=",", skiprows=1)[:, :6] for s, f in SYMS.items()}
A4 = {s: np.loadtxt(f"{data}/{f}_4H.csv", delimiter=",", skiprows=1)[:, :6] for s, f in SYMS.items()}
NOW = [0]


def fetch_candles(sym, bar="15m", limit=1000):
    sym = sym.upper().replace("USDT", "")
    if sym not in A:
        return []
    a, step_ms = (A[sym], M15) if bar == "15m" else (A4[sym], H4)
    k = int(np.searchsorted(a[:, 0], NOW[0] - step_ms, side="right"))       # only CLOSED bars
    return a[max(0, k - limit):k].tolist()


ctx = lambda s, n: {"funding": {}, "oi": {}, "news": [], "ts": n}  # noqa: E731
cli.DATA_DIR = work
cli.STATE_FILE = os.path.join(work, "state_v2.json")
cli.SYMBOLS = list(SYMS)
mc.fetch_all_context = ctx
cli.fetch_all_context = ctx
cli.time.sleep = lambda _: None
cli.fetch_candles = fetch_candles
cli.fetch_history_page = lambda *a, **k: []
cli.load_lessons = lambda *a, **k: ""
if claude:
    ACTIONS = ["open_long", "open_short", "open_long_split", "open_short_split", "close", "partial_close", "hold",
               "dca"]

    def fake_claude(system, prompt, max_tokens=900, timeout=60):
        rng = np.random.default_rng(NOW[0] // 60_000)
        decs = []
        for sym in rng.choice(list(SYMS), size=int(rng.integers(0, 3)), replace=False):
            act = str(rng.choice(ACTIONS))
            d = {"symbol": str(sym), "action": act, "trade_type": "scalp" if rng.random() < 0.8 else "medio",
                 "confidence": int(rng.integers(55, 95)), "leverage": int(rng.integers(5, 35)),
                 "margin_usd": float(rng.integers(30, 120)), "stop_loss_pct": round(float(rng.uniform(.004, .02)), 4),
                 "take_profit_pct": round(float(rng.uniform(.006, .04)), 4), "reason": "replay deterministico"}
            if act.endswith("_split"):
                d["split_retrace_pct"] = round(float(rng.uniform(.002, .008)), 4)
            if act == "partial_close":
                d["partial_close_fraction"] = 0.5
            if act == "dca":
                d.update(dca_sl_pct=0.01, dca_tp_pct=0.02)
            decs.append(d)
        return json.dumps({"decisions": decs, "note": "replay"}), {"input_tokens": 10, "output_tokens": 10}
    cli.apply_claude_schedule = lambda *a: True
    cli.can_call = lambda *a, **k: True
    cli.call_claude = fake_claude
    cli.record_spend = lambda *a, **k: 0.0
else:
    cli.apply_claude_schedule = lambda *a: False

state = {}
import contextlib, io  # noqa: E401,E402
t = start
while t < end:
    NOW[0] = t + 20_000
    with contextlib.redirect_stdout(io.StringIO()):
        cli.run_cycle(state, NOW[0])
    t += step


def jl(name):
    p = os.path.join(work, name)
    return [json.loads(x) for x in open(p)] if os.path.exists(p) else []


VOL = {"ts_wall", "wall_ms", "pid", "started_ms", "elapsed_ms", "run_no"}
learn = jl("learning_log.jsonl")
acc = cli.make_account(state)
res = {"closed": jl("trade_history.jsonl"),
       "opens": [{k: v for k, v in e.items() if k not in VOL} for e in learn if e.get("ev") == "open"],
       "candidates": [{k: e.get(k) for k in ("ts", "symbol", "side", "status", "source")} for e in learn
                      if e.get("ev") == "candidate"],
       "positions": {s: p.__dict__ for s, p in acc.positions.items()},
       "cash": acc.cash}
os.makedirs(out, exist_ok=True)
json.dump(res, open(os.path.join(out, "result.json"), "w"), default=str, sort_keys=True)
print(out, "closed", len(res["closed"]), "opens", len(res["opens"]), "cand", len(res["candidates"]), "cash",
      round(acc.cash, 2))
