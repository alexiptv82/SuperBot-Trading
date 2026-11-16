#!/usr/bin/env python3
"""One-shot isolated PAPER research replay on VPS.

Reads the existing Brain SQLite journal ONLY through read-only SQLite backup.
Fetches public Bitget closed 1m candles into a private /tmp research directory.
Runs existing, pinned counterfactual code from the SAME immutable Git commit.
Does not write to any live run, stop/start service, or contact trading endpoints.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import time
import urllib.request

RUN_ID = "brain-v3-paper20261111"
LIVE_RUN = Path("/opt/superbot-v3-paper-runs") / RUN_ID
M1 = 60_000
MAX_SPAN_MS = 12 * 86_400_000
SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT",
    "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT",
)
SOURCE_PATHS = (
    "research/brain_counterfactual/ledger.py",
    "research/brain_counterfactual/analysis.py",
    "research/brain_counterfactual/post_ai.py",
    "backend/v3/lab_tools/fetch_candles.py",
)
URL_ROOT = "https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/"
PUB_TEST = ("https://api.bitget.com/api/v2/mix/market/ticker?"
            "symbol=BTCUSDT&productType=USDT-FUTURES")


def say(name: str, data: object) -> None:
    print("BRAIN_REPLAY " + name + "=" + str(data), flush=True)


def load_source(scratch: Path, revision: str) -> dict:
    manifest = {}
    for rel in SOURCE_PATHS:
        url = URL_ROOT + revision + "/" + rel
        req = urllib.request.Request(url, headers={"User-Agent": "superbot-paper-research/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read(250_001)
        if not body or len(body) > 250_000:
            raise RuntimeError("source_size_invalid_" + Path(rel).name)
        # Code is pinned to a full Git commit SHA, never a mutable branch.
        target = scratch / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        manifest[rel] = hashlib.sha256(body).hexdigest()
    return manifest


def consistent_snapshot(scratch: Path) -> tuple[Path, int, int, int]:
    live = LIVE_RUN / "journal.db"
    if (not live.is_file() or live.is_symlink()
            or not stat.S_ISREG(live.stat().st_mode)):
        raise RuntimeError("live_brain_journal_not_regular")
    target = scratch / "journal-snapshot.db"
    source = sqlite3.connect(live.resolve().as_uri() + "?mode=ro", uri=True, timeout=20)
    try:
        source.execute("PRAGMA query_only=ON")
        dest = sqlite3.connect(target)
        try:
            # Official SQLite online backup: consistent with concurrent WAL writers.
            source.backup(dest, pages=256, sleep=0.05)
            if dest.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise RuntimeError("journal_snapshot_failed_integrity")
            row = dest.execute(
                "SELECT COUNT(*),MIN(occurred_at_ms),MAX(occurred_at_ms) "
                "FROM v3_events WHERE portfolio_id='brain' AND run_id=? "
                "AND kind='brain_decision'", (RUN_ID,),
            ).fetchone()
            dest.commit()
        finally:
            dest.close()
    finally:
        source.close()
    count, earliest, latest = row
    if not count or not isinstance(earliest, int) or not isinstance(latest, int):
        raise RuntimeError("no_brain_decisions_in_run")
    return target, count, earliest, latest


def candle_window(first: int, last: int, now_ms: int) -> tuple[int, int]:
    start = first // M1 * M1
    end = min(
        ((last + 24 * 3_600_000 + M1 - 1) // M1) * M1,
        now_ms // M1 * M1,
    )
    if end <= start or end - start > MAX_SPAN_MS:
        raise RuntimeError("research_window_outside_12_days")
    return start, end


def quick_public_probe() -> None:
    req = urllib.request.Request(PUB_TEST, headers={"User-Agent": "superbot-paper-research/1.0"})
    with urllib.request.urlopen(req, timeout=7) as resp:
        obj = json.load(resp)
    if obj.get("code") != "00000":
        raise RuntimeError("bitget_public_data_unavailable")


def import_fetch(scratch: Path):
    file = scratch / "backend/v3/lab_tools/fetch_candles.py"
    spec = importlib.util.spec_from_file_location("isolated_public_candles", file)
    if spec is None or spec.loader is None:
        raise RuntimeError("candle_helper_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch_data(scratch: Path, start: int, end: int) -> dict:
    fetch = import_fetch(scratch)
    target = scratch / "candles"
    expected = (end - start) // M1
    info = {}
    for sym in SYMBOLS:
        try:
            rows = fetch.fetch_rows(
                sym, start, end, candle_ms=M1,
                window_bars=200, max_requests=110,
            )
            path = target / sym / "1m.csv"
            digest = fetch.write_csv(path, rows)
            times = sorted(rows)
            gaps = sum((b - a) // M1 - 1 for a, b in zip(times, times[1:]))
            coverage = round(len(times) / expected, 4) if expected else 0
            info[sym] = {
                "received": len(times), "expected": expected, "gaps_internal": gaps,
                "coverage": coverage, "sha256": digest,
                "first_open_ms": times[0] if times else None,
                "last_open_ms": times[-1] if times else None,
            }
            say("candles_" + sym, f"{len(times)}/{expected} coverage={coverage:.1%} gaps={gaps}")
        except Exception as exc:
            # Continue research with UNAVAILABLE for this symbol, explicitly.
            info[sym] = {"received": 0, "expected": expected,
                         "error_type": type(exc).__name__, "coverage": 0}
            say("candles_" + sym, "UNAVAILABLE_" + type(exc).__name__)
    if not any(meta["received"] for meta in info.values()):
        raise RuntimeError("no_public_candles_downloaded")
    return info


def summarize(scratch: Path, journal: Path, candle_meta: dict, revision: str,
              start: int, end: int, src_digests: dict) -> dict:
    sys.path.insert(0, str(scratch))
    from research.brain_counterfactual.ledger import build
    from research.brain_counterfactual.analysis import analyze
    from research.brain_counterfactual.post_ai import audit

    entries, ledger_summary = build(journal, RUN_ID, scratch / "candles")
    paired = {str(lag): analyze(entries, str(lag)) for lag in (0, 1, 3)}
    gap_report = audit(entries)
    results = scratch / "counterfactual.jsonl"
    with results.open("x", encoding="utf-8") as handle:
        for item in entries:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    output = {
        "research": "brain_counterfactual_paper_only",
        "revision": revision,
        "run_id": RUN_ID,
        "closed_candle_end_exclusive_ms": end,
        "window_start_ms": start,
        "source_sha256": src_digests,
        "candle_sources": candle_meta,
        "journal_decisions": ledger_summary["decision_count"],
        "verified_executed": ledger_summary["executed_decision_count"],
        "approved_without_open_cause_unknown":
            ledger_summary["approved_without_open_unknown_cause"],
        "unknown_side": ledger_summary["unknown_side_count"],
        "orphan_opens": ledger_summary["orphan_open_count"],
        "decision_counts": ledger_summary["decision_counts"],
        "paired_hypotheses": paired,
        "post_ai_gap_audit": gap_report,
        "limitations": [
            "Hypothetical trade PnL is NOT real trading profit",
            "Decision timestamp can PRECEDE the completed DeepSeek inference",
            "NO_TRADE and RISK_REJECTED proposals cannot recover side without prior observer",
            "Overlapping simulated trades ignore portfolio margin and correlations",
            "Post-AI denial reason per decision is unavailable in historical journal",
            "Missing Bitget candles cause UNAVAILABLE or CENSORED; never interpolate",
            "No inference of AI alpha without independent future/holdout validation",
        ],
        "live_journal_modified": False,
        "orders_sent": 0,
        "deploy_executed": False,
    }
    report = scratch / "summary.json"
    with report.open("x", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    return output


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Isolated Brain PAPER historical replay")
    ap.add_argument("--revision", required=True, help="Full 40-character immutable Git commit")
    opts = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", opts.revision):
        ap.error("revision must be a full immutable commit SHA")
    if os.geteuid() != 0:
        ap.error("run as root to read PAPER journal")
    if shutil.disk_usage("/tmp").free < 256 * 1024 * 1024:
        raise RuntimeError("insufficient_scratch_disk_space")
    scratch = Path(tempfile.mkdtemp(prefix="superbot-brain-research-", dir="/tmp"))
    os.chmod(scratch, 0o700)
    say("research_dir", scratch)
    say("mode", "PAPER_OFFLINE_READ_ONLY")
    # Do not stop or restart containers/systemd; do not access trading APIs.
    journal, n, first, last = consistent_snapshot(scratch)
    say("snapshot_decisions", n)
    start, end = candle_window(first, last, int(time.time() * 1000))
    say("window_utc", time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(start / 1000))
        + "..." + time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(end / 1000)))
    src_digests = load_source(scratch, opts.revision)
    quick_public_probe()
    candle_meta = fetch_data(scratch, start, end)
    output = summarize(scratch, journal, candle_meta, opts.revision,
                       start, end, src_digests)
    gap = output["post_ai_gap_audit"]
    say("approvals", gap["approved_total"])
    say("verified_opens", gap["executed_with_verified_decision_link"])
    say("unexecuted_unknown_cause", gap["approved_unexecuted_reason_unknown"])
    say("model_side_unknown", output["unknown_side"])
    for lag, item in output["paired_hypotheses"].items():
        say("paired_lag_" + lag + "m", "n=" + str(item["paired_n"])
            + " model_minus_always_short_R=" + str(item["model_minus_always_short_r"]))
    say("summary_file", scratch / "summary.json")
    say("raw_ledger_file_private", scratch / "counterfactual.jsonl")
    say("live_unchanged", "YES")
    say("orders_sent", "0")
    say("RESULT", "COMPLETED_WITH_COVERAGE_LIMITS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Avoid leaking journal contents or credentials in exceptions.
        say("RESULT", "FAILED_" + type(exc).__name__ + "_" + str(exc)[:90].replace("\n", "_"))
        sys.exit(2)
