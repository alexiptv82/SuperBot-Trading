"""Read-only shadow monitor for *copied* PAPER state files.

Runs outside both bots. Never imports bot runtime, accesses exchange, places
orders, or writes to either bot's data directory. Output is exclusively a
separate directory explicitly selected by the operator.

Usage (after a security review and supplying safe copied files):
 python -m backend.desk.profit_manager_monitor --hawk-copy /safe/hawk.json --bull-copy /safe/bull.json --output-dir /safe/shadow --once

Continuous mode (omit --once) is intentionally NOT deployed automatically.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    from .profit_manager_state_adapter import read_state_file
    from .profit_manager_replay import ShadowReplay
except ImportError:
    from profit_manager_state_adapter import read_state_file
    from profit_manager_replay import ShadowReplay


PROTECTED = {"state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md", "errors.md"}


def check_output(output_dir, sources):
    target = Path(output_dir).resolve()
    source_paths = [Path(p).resolve() for p in sources if p]
    if not source_paths:
        raise ValueError("At least one copied input is required")
    if target == Path("/") or target == Path("/opt") or str(target).startswith("/opt/superbot-desk-data"):
        raise ValueError("Output under bot data directory is forbidden")
    for src in source_paths:
        if target == src or target in src.parents or src in target.parents:
            raise ValueError("Output and input locations must be isolated")
        if src.name == "state_v2.json":
            raise ValueError("Use separately named copies, never original state files")
    return target


def run_once(inputs, replay, last_seen, output_dir, *, now_ms=None, max_age_ms=120000):
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    observations, exclusions = [], []
    for bot, path in inputs.items():
        if not path:
            continue
        try:
            ticks, skips = read_state_file(path, bot=bot)
            exclusions.extend({"bot": bot, **skip} for skip in skips)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            exclusions.append({"bot": bot, "reason": f"unreadable_copy: {exc}"})
            continue
        for snap in ticks:
            if snap.timestamp_ms > now_ms + 5000 or now_ms - snap.timestamp_ms > max_age_ms:
                exclusions.append({"bot": bot, "symbol": snap.trade_id, "reason": "stale_or_future_price"})
                continue
            if snap.timestamp_ms <= last_seen.get(snap.trade_id, -1):
                continue
            try:
                decision = replay.observe(snap)
                last_seen[snap.trade_id] = snap.timestamp_ms
                observations.append({
                    "bot": bot, "trade_id": snap.trade_id,
                    "timestamp_ms": snap.timestamp_ms,
                    "mark": snap.mark, "action": decision.action,
                    "reason": decision.reason,
                    "estimated_net_usdt": decision.estimated_net_usdt,
                    "roi_net_pct": decision.roi_net_pct,
                    "peak_roi_net_pct": decision.peak_roi_net_pct,
                    "source": "copied_paper_state_last_price_not_executable",
                })
            except (ValueError, TypeError) as exc:
                exclusions.append({"bot": bot, "symbol": snap.trade_id, "reason": str(exc)})
    output_dir = Path(output_dir)
    if observations or exclusions:
        # Open with O_NOFOLLOW where supported, append-only and private perms.
        fd = os.open(str(output_dir / "observations.jsonl"),
                     os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            for row in observations:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
            for row in exclusions:
                stream.write(json.dumps({"type": "excluded", **row}, sort_keys=True) + "\n")
    return {"observations": len(observations), "excluded": len(exclusions)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hawk-copy", type=Path)
    parser.add_argument("--bull-copy", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.interval < 15:
        parser.error("Minimum interval is 15 seconds")
    sources = {"hawk": args.hawk_copy, "bull": args.bull_copy}
    try:
        output = check_output(args.output_dir, sources.values())
    except ValueError as exc:
        parser.error(str(exc))
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    replay, last_seen = ShadowReplay(), {}
    while True:
        result = run_once(sources, replay, last_seen, output)
        print(json.dumps(result), flush=True)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
