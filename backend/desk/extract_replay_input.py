"""Extract private replay EVIDENCE from a verified, offline bot backup.

No network, no server commands, no invented historical snapshots. Review before
using on operational data. An external SHA-256 manifest is mandatory. The result
is an evidence bundle, NOT automatically a runnable input for profit_replay_v1.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import shutil

REQUIRED = ("state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "heartbeat.json")
MAX_FILE_BYTES = 256 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("non-finite JSON value")
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("non-finite JSON number")
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid, parse_float=number)


def rows(raw):
    if raw and not raw.endswith(b"\n"):
        raise ValueError("incomplete JSONL final line")
    result = []
    for line in raw.splitlines():
        if not line.strip():
            raise ValueError("blank JSONL line")
        value = strict_json(line)
        if not isinstance(value, dict):
            raise ValueError("JSONL rows must be objects")
        result.append(value)
    return result


def coverage(payloads, portfolio, run_no):
    if portfolio not in ("hawk", "bull") or type(run_no) is not int or run_no != {"hawk": 3, "bull": 2}[portfolio]:
        raise ValueError("expected Hawk run 3 or Bull run 2")
    state = strict_json(payloads["state_v2.json"])
    heartbeat = strict_json(payloads["heartbeat.json"])
    if not isinstance(state, dict) or not isinstance(heartbeat, dict):
        raise ValueError("state and heartbeat must be objects")
    if type(state.get("run_no")) is not int or state["run_no"] < run_no:
        raise ValueError("backup predates requested run")
    if heartbeat.get("portfolio") != portfolio or heartbeat.get("exec_mode") != "paper":
        raise ValueError("backup portfolio/PAPER mode not established")
    history = rows(payloads["trade_history.jsonl"])
    events = rows(payloads["learning_log.jsonl"])
    for row in history + events:
        if "portfolio" in row and row["portfolio"] != portfolio:
            raise ValueError("mixed portfolio data")
    selected = [r for r in events if r.get("run_no") == run_no]
    closed = [r for r in history if r.get("run_no") == run_no]
    if not selected or not closed:
        raise ValueError("requested run lacks tagged learning/history evidence")
    counts = Counter(str(r.get("ev", "missing")) for r in selected)
    opens = [r for r in selected if r.get("ev") == "open"]
    return {
        "portfolio": portfolio, "run_no": run_no,
        "events_by_type": dict(sorted(counts.items())),
        "history_rows": len(closed), "open_events": len(opens),
        "untagged_history_rows": sum("run_no" not in r for r in history),
        "untagged_learning_rows": sum("run_no" not in r for r in events),
        "declared_version_at_backup": heartbeat.get("version"),
        "historical_code_sha_verified": False,
        "replay_ready": False,
        "limitations": [
            "These files do not prove contemporaneous accounting snapshots for every cycle.",
            "Final state must not be projected backwards; no quantities, fees or funding are inferred.",
            "Closed OHLC with timestamp convention, historical decision times and execution prices are separate inputs.",
            "DCA, split fills and partial closures require an audited chronological adapter.",
            "Version in heartbeat describes backup time, not necessarily all historical decisions.",
            "No input.json generated until coverage and reconstruction assumptions are independently reviewed.",
        ],
    }


def extract(source, output, expected_manifest, portfolio, run_no):
    source, output = Path(source).resolve(), Path(output).absolute()
    parent = output.parent.resolve(strict=True)
    output = parent / output.name
    if output.exists() or output.is_symlink():
        raise ValueError("output already exists")
    if source == parent or source in parent.parents:
        raise ValueError("output must be outside source backup")
    if any((p / ".git").exists() for p in (parent, *parent.parents)):
        raise ValueError("private output must be outside any git checkout")
    expected_raw = Path(expected_manifest).read_bytes()
    expected = strict_json(expected_raw)
    if not isinstance(expected, dict) or set(expected) != set(REQUIRED):
        raise ValueError("manifest must map exactly the four source filenames to SHA-256")
    payloads = {}
    for name in REQUIRED:
        path = source / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("missing, symlink or oversized required source")
        raw = path.read_bytes()
        if not raw or digest(raw) != expected[name]:
            raise ValueError("source hash mismatch/empty file: " + name)
        payloads[name] = raw
    report = coverage(payloads, portfolio, run_no)
    for name in REQUIRED:
        if (source / name).is_symlink() or digest((source / name).read_bytes()) != expected[name]:
            raise ValueError("source changed during extraction")
    # Exclusive directory, never reuse or clean a pre-existing output.
    output.mkdir(mode=0o700)
    try:
        manifest = {}
        for name, raw in payloads.items():
            fd = os.open(output / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if digest((output / name).read_bytes()) != expected[name]:
                raise ValueError("output verification failed")
            manifest[name] = {"sha256": expected[name], "bytes": len(raw)}
        report["source_manifest_sha256"] = digest(expected_raw)
        report["files"] = manifest
        fd = os.open(output / "COVERAGE.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf8") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        shutil.rmtree(output)
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-manifest", required=True, type=Path)
    parser.add_argument("--portfolio", required=True, choices=("hawk", "bull"))
    parser.add_argument("--run", required=True, type=int)
    args = parser.parse_args()
    report = extract(args.source, args.output, args.expected_manifest, args.portfolio, args.run)
    # No balances, positions, paths, prompts or raw events in public job logs.
    print(json.dumps({"extraction_verified": True, "replay_ready": report["replay_ready"]}))


if __name__ == "__main__":
    main()
