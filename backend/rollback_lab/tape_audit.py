"""Forensic inventory of historical PAPER positions. Read-only and deterministic.

Reconciles trade groups by real exit reason, source, commit and metadata gaps.
Does not replay prices, import the trading engine, or infer an AI attribution.
Historical source: immutable diary export of 2026-10-27.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess

SOURCE = "diario/analisi-run-2026-10-27/positions.csv"
GROUPS = {"golden": (("hawk", 2), ("bull", 1)),
          "first_crisis": (("hawk", 3), ("bull", 2))}
REQUIRED = {"bot", "run_no", "id", "symbol", "side", "open_ms", "close_ms",
            "net", "gross", "fees", "source", "exit_kind", "entry_code",
            "entry_log_present", "entry_sl", "entry_tp", "entry_fill",
            "features_json", "score", "exit_code"}


def _decimal(s: str) -> Decimal:
    return Decimal(s if s else "0")


def load_tape(raw: bytes) -> tuple[list[dict], str]:
    doc = raw.decode("utf-8-sig")
    rd = csv.DictReader(io.StringIO(doc, newline=""))
    if not rd.fieldnames or not REQUIRED.issubset(rd.fieldnames):
        raise ValueError("missing_export_columns")
    rows = list(rd)
    if not rows:
        raise ValueError("empty_tape")
    ids = set()
    for row in rows:
        identity = (row["bot"], row["run_no"], row["id"])
        if identity in ids:
            raise ValueError("duplicate_complete_position_" + repr(identity))
        ids.add(identity)
        if not row["bot"] or not row["symbol"] or row["side"] not in ("-1", "1"):
            raise ValueError("invalid_identity_or_side")
        if not int(row["open_ms"]) < int(row["close_ms"]):
            raise ValueError("noncausal_position_timestamps")
        _decimal(row["net"])
        _decimal(row["gross"])
        _decimal(row["fees"])
    return rows, sha256(raw).hexdigest()


def _totals(rows: list[dict]) -> dict:
    exits = defaultdict(list)
    codes = Counter()
    missing = Counter()
    sides = Counter()
    sources = Counter()
    for row in rows:
        exits[row["exit_kind"]].append(row)
        codes[row["entry_code"] or "(unknown)"] += 1
        sources[row["source"] or "(unknown)"] += 1
        sides["LONG" if row["side"] == "1" else "SHORT"] += 1
        for field in ("entry_sl", "entry_tp", "entry_fill", "score", "exit_code"):
            if not row[field]: missing[field] += 1
        if row["entry_log_present"].lower() != "true": missing["entry_log"] += 1
        if not row["features_json"] or row["features_json"] in ("{}", "null"):
            missing["features_json"] += 1
    total = lambda group, field: round(float(sum((_decimal(r[field]) for r in group), Decimal(0))), 4)
    return {
        "positions": len(rows),
        "net_usd": total(rows, "net"),
        "gross_usd": total(rows, "gross"),
        "fees_usd": total(rows, "fees"),
        "direction_counts": dict(sorted(sides.items())),
        "opening_sources": dict(sorted(sources.items())),
        "entry_commit_counts": dict(sorted(codes.items())),
        "missing_fields": dict(sorted(missing.items())),
        "exits": {name: {"n": len(part), "net_usd": total(part, "net"),
                         "gross_usd": total(part, "gross"),
                         "fees_usd": total(part, "fees")}
                  for name, part in sorted(exits.items())},
    }


def analyze(raw: bytes) -> dict:
    rows, digest = load_tape(raw)
    groups = {}
    for name, ids in GROUPS.items():
        selected = [r for r in rows if (r["bot"], int(r["run_no"])) in ids]
        sub = {f"{bot}#{run}": _totals(
            [r for r in selected if r["bot"] == bot and int(r["run_no"]) == run])
               for bot, run in ids}
        groups[name] = {"all": _totals(selected), "portfolios": sub}
    ambiguous = []
    for row in rows:
        if not any((row["bot"], int(row["run_no"])) in ids
                   for ids in GROUPS.values()):
            continue
        if row["exit_kind"] in ("model_or_rule_close_labeled_claude", "manual"):
            ambiguous.append({
                "portfolio": row["bot"], "run_no": int(row["run_no"]),
                "position_id": row["id"], "symbol": row["symbol"],
                "side": row["side"], "open_ms": int(row["open_ms"]),
                "close_ms": int(row["close_ms"]),
                "net_usd": float(_decimal(row["net"])),
                "exit_kind": row["exit_kind"], "entry_code": row["entry_code"],
                "exit_code": row["exit_code"] or None,
                "attribution": "UNKNOWN_NOT_PROVEN_CLAUDE",
            })
    ambiguous.sort(key=lambda x:(x["close_ms"],x["portfolio"],x["position_id"]))
    return {
        "kind": "ARCHIVED_PAPER_TRADE_PROVENANCE_NOT_REPLAY",
        "source": SOURCE,
        "export_sha256": digest,
        "source_record_count": len(rows),
        "groups": groups,
        "ambiguous_exits": ambiguous,
        "cautions": [
            "Opening source=rules does NOT identify the closing agent.",
            "model_or_rule_close_labeled_claude does NOT establish Claude caused the close.",
            "Entry code inferred from deployment timestamps can be uncertain.",
            "Missing exit_code and missing raw market snapshots block faithful counterfactual exits.",
            "This is a pre-existing PAPER export, not live VPS status.",
            "No source code/market replay or prediction is performed.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path,
                   default=Path(__file__).resolve().parents[2])
    p.add_argument("--csv", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.csv:
        raw = args.csv.read_bytes()
    else:
        raw = subprocess.check_output(
            ["git", "show", "origin/diario:" + SOURCE],
            cwd=args.repo, timeout=20)
    result = analyze(raw)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print("SOURCE_SHA256",result["export_sha256"])
    for name, item in result["groups"].items():
        x = item["all"]
        exit_short = [(k, v["n"], v["net_usd"]) for k,v in x["exits"].items()]
        print("RUN_GROUP", name,"POSITIONS",x["positions"],
              "NET",x["net_usd"],"EXITS",exit_short,
              "ENTRY_CODE",x["entry_commit_counts"],
              "MISSING",x["missing_fields"])
    print("AMBIGUOUS_EXITS",len(result["ambiguous_exits"]))
    print("FORENSIC_ONLY_NO_TRADING_NO_DEPLOY")


if __name__ == "__main__":
    main()
