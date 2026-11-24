"""Diagnosi PAPER in SOLA LETTURA (root): perdita del trade BTC e aggressivita' dei bot (24/11/2026).

Nessuna scrittura nelle run, nei servizi o nei journal: i database si leggono da COPIE (backup SQLite in sola lettura)
in una cartella temporanea. Scrive un solo rapporto JSON leggibile dall'agente (``--out``) e stampa un riassunto.

A. Run attiva (slot ``brain-v3-brain-scalp-p1``): cronologia completa delle posizioni BTC (aperture, revisioni AI,
   consulti, stop spostati, riduzioni, chiusure con motivo/prezzo/lordo/commissioni/netto), esiti dei canali di
   chiusura (manuale e del Brain), battito, configurazione; candele Bitget da 1 minuto dall'apertura alla chiusura e
   RIESECUZIONE del monitor delle uscite con il codice installato (stesso calcolo del servizio delle uscite).
B. Aggressivita': per ogni run (attiva e archiviate) configurazione, decisioni per tipo/stato/motivo/rifiuto di rischio,
   aperture con leva/margine/distanza dello stop, chiusure, consulti di Claude, revisioni, stati del Guardian, ritmo.
C. Primi bot: statistiche aggregate dei file JSONL di ``/opt/superbot-desk-data`` (Falco/hawk, Toro/bull, Brain pilota).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

RUNS = Path("/opt/superbot-v3-paper-runs")
DESK = Path("/opt/superbot-desk-data")
SCALP = "brain-v3-brain-scalp-p1"
MIN = 60_000


def ro_events(run_dir: Path, tmp: Path) -> list[dict]:
    db = run_dir / "journal.db"
    if not db.is_file():
        return []
    dst = tmp / f"{abs(hash(str(run_dir)))}.db"
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    out = sqlite3.connect(str(dst))
    with out:
        src.backup(out)
    src.close()
    rows = out.execute("SELECT seq, event_id, kind, occurred_at_ms, source, payload_json FROM v3_events ORDER BY seq").fetchall()
    out.close()
    return [{"seq": s, "id": i, "kind": k, "t": t, "src": so, "p": json.loads(pj)} for s, i, k, t, so, pj in rows]


def read_json(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def iso(ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ms / 1000))


# ----------------------------------------------------------------------------- A. trade BTC
def btc_timeline(events: list[dict], symbol: str = "BTCUSDT") -> dict:
    pids = {e["p"].get("position_id") for e in events if e["kind"] == "paper_open" and e["p"].get("symbol") == symbol}
    groups = {e["p"].get("decision_event_id") for e in events if e["p"].get("position_id") in pids}
    keep = []
    for e in events:
        p = e["p"]
        if (p.get("position_id") in pids or p.get("group") in groups or e["id"] in groups
                or (e["kind"] in ("ai_consultation", "position_review", "stop_move") and p.get("symbol") == symbol)):
            keep.append({"seq": e["seq"], "time": iso(e["t"]), "t": e["t"], "kind": e["kind"], "source": e["src"],
                         "payload": p})
    closes = [k for k in keep if k["kind"] in ("paper_close", "paper_reduce")]
    tot = {f: str(sum((Decimal(str(c["payload"].get(f, "0"))) for c in closes), Decimal(0)))
           for f in ("gross_pnl", "fees", "realized_pnl")}
    return {"position_ids": sorted(x for x in pids if x), "events": keep, "totals": tot,
            "close_reasons": [(c["payload"].get("position_id"), c["payload"].get("reason"), c["payload"].get("stop_kind"),
                               c["time"], c["payload"].get("exit_price")) for c in closes]}


def bitget_minutes(symbol: str, start: int, end: int) -> list[list]:
    """Candele da 1 minuto pubbliche (nessuna chiave) a blocchi di 200."""
    import urllib.request
    out, cur = [], start
    while cur < end:
        stop = min(end, cur + 200 * MIN)
        url = (f"https://api.bitget.com/api/v2/mix/market/history-candles?symbol={symbol}&productType=USDT-FUTURES"
               f"&granularity=1m&startTime={cur}&endTime={stop}&limit=200")
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                data = json.loads(r.read().decode()).get("data") or []
        except Exception:
            data = []
        out += [row[:5] for row in data]
        cur = stop
        time.sleep(0.3)
    return sorted({int(r[0]): r for r in out}.values(), key=lambda r: int(r[0]))


def replay(stage: Path, run_dir: Path, tl: dict, candles: list[list]) -> list[dict]:
    """Rigioca il monitor (codice installato) su ogni quota: che uscita avrebbe dovuto produrre e quando."""
    sys.path.insert(0, str(stage))
    from backend.v3.features.indicators import Bar
    from backend.v3.runner.config import load_runner_config
    from backend.v3.runner.exits import evaluate_exit
    from dataclasses import replace
    cfg = load_runner_config((run_dir / "runner_config.json").read_bytes())
    pol = cfg.exit_policy
    bars = [Bar(int(c[0]), Decimal(c[1]), Decimal(c[2]), Decimal(c[3]), Decimal(c[4]), Decimal(0)) for c in candles]
    moves = {}
    for e in tl["events"]:
        if e["kind"] == "stop_move":
            at = (e["t"] // MIN + 1) * MIN
            moves.setdefault(e["payload"]["position_id"], []).append((at, Decimal(e["payload"]["stop_price"])))
    out = []
    for e in tl["events"]:
        if e["kind"] != "paper_open":
            continue
        p = e["payload"]
        tp_r = p.get("take_profit_r")
        pp = pol if tp_r is None else replace(pol, take_profit_r=Decimal(tp_r))
        mine = [b for b in bars if b.open_time_ms >= e["t"]]
        try:
            sig = evaluate_exit(side=int(p["side"]), fill_price=Decimal(p["fill_price"]), stop_price=Decimal(p["stop_price"]),
                                opened_at_ms=e["t"], bars=mine, candle_ms=MIN, policy=pp, fee_bps=cfg.fee_bps,
                                stop_moves=tuple(moves.get(p["position_id"], ())))
        except Exception as exc:                              # noqa: BLE001
            out.append({"position_id": p["position_id"], "error": type(exc).__name__})
            continue
        best = max((b.high for b in mine), default=None) if int(p["side"]) == 1 else min((b.low for b in mine), default=None)
        out.append({"position_id": p["position_id"], "leg": p.get("leg"), "fill": p["fill_price"],
                    "stop": p["stop_price"], "take_profit_r": tp_r or str(pol.take_profit_r),
                    "best_price_seen": None if best is None else str(best),
                    "monitor_exit": None if sig is None else {"reason": sig.reason, "price": str(sig.price),
                                                              "bar": iso(sig.bar_open_time_ms),
                                                              "stop_kind": sig.stop_kind}})
    return out


# ----------------------------------------------------------------------------- B. aggressivita' delle run V3
def run_stats(run_dir: Path, events: list[dict]) -> dict:
    cfg = read_json(run_dir / "runner_config.json") or {}
    dec = [e for e in events if e["kind"] == "brain_decision"]
    opens = [e for e in events if e["kind"] == "paper_open"]
    closes = [e for e in events if e["kind"] in ("paper_close", "paper_reduce")]
    span_h = ((events[-1]["t"] - events[0]["t"]) / 3_600_000) if events else 0
    lev = [o["p"].get("leverage") for o in opens]
    margin = [Decimal(str(o["p"].get("margin_used", "0"))) for o in opens]
    stops = [abs(Decimal(str(o["p"]["fill_price"])) - Decimal(str(o["p"]["stop_price"]))) / Decimal(str(o["p"]["fill_price"]))
             * 10000 for o in opens if o["p"].get("fill_price") and o["p"].get("stop_price")]
    return {
        "run": run_dir.name, "config": {k: cfg.get(k) for k in ("schema_version", "initial_equity", "cycle_minutes",
                                                              "analyst", "risk_policy", "exit_policy", "brain_unico",
                                                              "guardian", "daily_loss_halt_fraction")},
        "hours": round(span_h, 1), "decisions": len(dec),
        "decision_kind_status": Counter(f"{d['p'].get('kind')}:{d['p'].get('status')}" for d in dec).most_common(),
        "rationale": Counter(str(d["p"].get("rationale")) for d in dec).most_common(15),
        "risk_reason": Counter(str(d["p"].get("risk_reason")) for d in dec if d["p"].get("risk_reason")).most_common(),
        "regime": Counter(str(d["p"].get("regime")) for d in dec).most_common(),
        "opens": len(opens), "opens_per_day": round(len(opens) / span_h * 24, 2) if span_h else None,
        "leverage": Counter(lev).most_common(), "margin_avg": str(sum(margin) / len(margin)) if margin else None,
        "margin_max": str(max(margin)) if margin else None,
        "stop_bp_avg": str(sum(stops) / len(stops)) if stops else None,
        "closes": len(closes), "close_reasons": Counter(f"{c['p'].get('reason')}:{c['p'].get('stop_kind')}"
                                                        for c in closes).most_common(),
        "realized": str(sum((Decimal(str(c["p"].get("realized_pnl", "0"))) for c in closes), Decimal(0))),
        "fees": str(sum((Decimal(str(c["p"].get("fees", "0"))) for c in closes), Decimal(0))),
        "consult_codes": Counter(str(e["p"].get("code")) for e in events if e["kind"] == "ai_consultation").most_common(),
        "consult_triggers": Counter(t for e in events if e["kind"] == "ai_consultation"
                                    for t in (e["p"].get("triggers") or [])).most_common(),
        "review_codes": Counter(f"{e['p'].get('proposed')}->{e['p'].get('executed')}:{e['p'].get('code')}"
                                for e in events if e["kind"] == "position_review").most_common(20),
        "guardian_states": Counter(str(e["p"].get("state")) for e in events if e["kind"] == "guardian_state").most_common(),
        "post_ai_errors_hint": "vedi heartbeat/last_error nei log del runner",
    }


# ----------------------------------------------------------------------------- C. primi bot (desk)
def desk_stats(folder: Path) -> dict:
    out = {"folder": folder.name, "files": {}}
    for f in sorted(folder.rglob("*")):
        if not f.is_file() or f.stat().st_size > 200_000_000:
            continue
        info = {"bytes": f.stat().st_size}
        if f.suffix in (".jsonl",):
            rows = []
            for line in f.read_text(errors="ignore").splitlines():
                try:
                    r = json.loads(line)
                    if isinstance(r, dict):
                        rows.append(r)
                except ValueError:
                    pass
            info["rows"] = len(rows)
            keys = Counter(k for r in rows for k in r)
            info["keys"] = [k for k, _ in keys.most_common(40)]
            num = {}
            for k in ("leverage", "margin", "margin_usd", "total_margin", "pnl", "pnl_usd", "net", "confidence",
                      "sl_pct", "tp_pct", "stop_loss_pct", "take_profit_pct", "hold_minutes", "held_ms"):
                vals = []
                for r in rows:
                    try:
                        vals.append(float(r[k]))
                    except (KeyError, TypeError, ValueError):
                        pass
                if vals:
                    vals.sort()
                    num[k] = {"n": len(vals), "min": vals[0], "median": vals[len(vals) // 2], "max": vals[-1],
                              "mean": round(sum(vals) / len(vals), 4)}
            info["numeric"] = num
            for k in ("action", "side", "trade_type", "reason", "exit_reason", "outcome", "decision", "status"):
                c = Counter(str(r.get(k)) for r in rows if k in r)
                if c:
                    info.setdefault("categories", {})[k] = c.most_common(12)
            ts = [r.get(k) for r in rows for k in ("open_ms", "opened_ms", "ts", "timestamp", "time") if k in r]
            ts = [int(x) for x in ts if isinstance(x, (int, float))]
            if len(ts) > 1:
                info["span_days"] = round((max(ts) - min(ts)) / (86_400_000 if max(ts) > 1e12 else 86_400), 2)
        out["files"][str(f.relative_to(folder))] = info
    return out


def main(argv=None) -> int:
    global RUNS, DESK
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--owner", default="")
    ap.add_argument("--runs", default=str(RUNS))            # solo per le prove locali
    ap.add_argument("--desk", default=str(DESK))
    ap.add_argument("--stage", default="")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    RUNS, DESK = Path(a.runs), Path(a.desk)
    tmp = Path(tempfile.mkdtemp(prefix="diagnosi-"))
    rep: dict = {"generated": iso(int(time.time() * 1000))}
    try:
        cur = RUNS / SCALP
        stage = Path(a.stage or subprocess.run(["systemctl", "show", "-p", "WorkingDirectory", "--value",
                                                "superbot-brain-scalp-p1-exit.service"],
                                               capture_output=True, text=True).stdout.strip())
        ev = ro_events(cur, tmp)
        tl = btc_timeline(ev)
        rep["A_btc"] = {"timeline": tl, "close_result": read_json(cur / "close_result.json"),
                        "brain_close_result": read_json(cur / "brain_close_result.json"),
                        "heartbeat": read_json(cur / "heartbeat.json"), "stage": str(stage)}
        opens = [e for e in tl["events"] if e["kind"] == "paper_open"]
        if opens:
            start = min(e["t"] for e in opens) // MIN * MIN
            ends = [e["t"] for e in tl["events"] if e["kind"] in ("paper_close", "paper_reduce")]
            end = (max(ends) if ends else int(time.time() * 1000)) // MIN * MIN + 5 * MIN
            candles = [] if a.offline else bitget_minutes("BTCUSDT", start, end)
            rep["A_btc"]["candles_1m"] = candles
            try:
                rep["A_btc"]["monitor_replay"] = replay(stage, cur, tl, candles)
            except Exception as exc:                          # noqa: BLE001
                rep["A_btc"]["monitor_replay"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        for unit in () if a.offline else ("superbot-brain-scalp-p1-exit.service", "superbot-brain-scalp-p1-runner.service"):
            j = subprocess.run(["journalctl", "-u", unit, "--since", "2026-11-24 14:00", "--no-pager", "-o", "short-iso"],
                               capture_output=True, text=True).stdout.splitlines()
            rep.setdefault("A_service_log", {})[unit] = j[-120:]
        runs = [cur] + sorted(p for p in (RUNS / ".archivio").glob("reset-*/brain-v3-*") if p.is_dir())
        runs += [p for p in RUNS.glob("brain-v3-*") if p.is_dir() and p != cur]
        rep["B_runs"] = []
        for r in runs:
            try:
                rep["B_runs"].append(dict(run_stats(r, ro_events(r, tmp)), path=str(r.relative_to(RUNS))))
            except Exception as exc:                          # noqa: BLE001
                rep["B_runs"].append({"path": str(r), "error": type(exc).__name__})
        rep["C_desk"] = [desk_stats(d) for d in sorted(DESK.iterdir()) if d.is_dir()] if DESK.is_dir() else []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=1, default=str))
    out.chmod(0o644)
    if a.owner:
        shutil.chown(out, a.owner, a.owner)
    tl = (rep.get("A_btc") or {}).get("timeline") or {}
    print("DIAGNOSI_BTC_CHIUSURE=" + json.dumps(tl.get("close_reasons")))
    print("DIAGNOSI_BTC_TOTALI=" + json.dumps(tl.get("totals")))
    print("DIAGNOSI_RUN=" + str(len(rep.get("B_runs") or [])) + " DESK=" + str(len(rep.get("C_desk") or [])))
    print("DIAGNOSI_RAPPORTO=" + str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
