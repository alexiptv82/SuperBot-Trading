"""One-shot read-only collection from COPIED paper state files.

No VPS access, no exchange calls, no daemon, no deploy and no bot imports.
Writes ONLY to a user-specified output path (never to bot data directories).
Use distinct copies from successive moments to build chronological JSONL.
"""
import argparse
import json
import sys
from pathlib import Path

try:
    from .profit_manager_state_adapter import read_state_file
except ImportError:
    from profit_manager_state_adapter import read_state_file


def collect(hawk_copy, bull_copy):
    records, excluded = [], []
    for bot, path in (("hawk", hawk_copy), ("bull", bull_copy)):
        if not path:
            continue
        ticks, skips = read_state_file(path, bot=bot)
        records.extend(vars(tick) for tick in ticks)
        excluded.extend({"bot": bot, **entry} for entry in skips)
    return records, excluded


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hawk-copy", type=Path)
    parser.add_argument("--bull-copy", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if not args.hawk_copy and not args.bull_copy:
        parser.error("Supply at least one copied state file")
    out = args.output.resolve()
    # Avoid overwriting any original state or input file.
    inputs = {p.resolve() for p in (args.hawk_copy, args.bull_copy) if p}
    if out in inputs or out.name in {"state_v2.json", "trade_history.jsonl", "learning_log.jsonl"}:
        parser.error("Refusing to overwrite paper bot state or learning files")
    records, excluded = collect(args.hawk_copy, args.bull_copy)
    if records:
        with out.open("a", encoding="utf-8") as stream:
            for row in records:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
    print(json.dumps({"records_appended": len(records), "excluded": excluded,
                      "warning": "Repeated collection of unchanged states yields duplicate ticks; replay rejects them."},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
