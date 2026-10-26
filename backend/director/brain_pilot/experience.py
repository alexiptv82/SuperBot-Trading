"""Read-only PAPER snapshot intake and isolated cross-bot experience retrieval.

Research Console concepts reused: source hashes, explicit QA verdicts,
immutable experiment identity and a frozen research/validation boundary.
No source collector, strategy formulas, credentials or source database imports.
"""
from collections import defaultdict
from dataclasses import dataclass
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import tempfile

from . import learning as lm

SCHEMA = 1
MAX_BYTES = 64 * 1024 * 1024
MAX_LINE = 256 * 1024
MAX_ROWS = 100000
MAX_EPISODES = 5000
MAX_BUNDLE_BYTES = 8 * 1024 * 1024
MAX_VIEW_CHARS = 8500
HEX = re.compile(r"[a-f0-9]{64}")
REV = re.compile(r"[a-f0-9]{7,40}")


class IntakeError(ValueError):
    """Fixed public codes only: never echo source text or credentials."""


@dataclass(frozen=True)
class Snapshot:
    owner: str
    history: Path
    learning: Path | None = None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_rows(path):
    path = Path(path)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    rows = []
    hasher = hashlib.sha256()
    try:
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
                raise IntakeError("SOURCE_TYPE_OR_SIZE")
            while True:
                line = stream.readline(MAX_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_LINE or not line.endswith(b"\n"):
                    raise IntakeError("SOURCE_LINE_TRUNCATED_OR_TOO_LARGE")
                hasher.update(line)
                try:
                    row = json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                except (ValueError, UnicodeError):
                    raise IntakeError("SOURCE_INVALID_JSON") from None
                if not isinstance(row, dict) or len(rows) >= MAX_ROWS:
                    raise IntakeError("SOURCE_ROWS_INVALID_OR_TOO_MANY")
                rows.append(row)
            after = os.fstat(stream.fileno())
            if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise IntakeError("SOURCE_CHANGED_DURING_READ")
    except BaseException:
        raise
    return rows, hasher.hexdigest()


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def identity(row, owner, opening=False):
    if owner not in ("hawk", "bull"):
        raise IntakeError("UNKNOWN_SOURCE_OWNER")
    for field in ("portfolio", "account"):
        if field in row and row[field] != owner:
            raise IntakeError("SOURCE_OWNER_MISMATCH")
    if (row.get("mode") == "live" or row.get("exec_mode") == "live" or
        row.get("live_fill") or row.get("live_order_id") not in (None,"","paper") or row.get("live") or row.get("live_executed")):
        raise IntakeError("NON_PAPER_RECORD")
    stamp = row.get("ts") if opening else row.get("open_ms")
    if (not integer(row.get("id"), 1) or not integer(row.get("run_no"), 1) or
        not integer(stamp) or type(row.get("side")) is not int or row["side"] not in (-1, 1) or
        not isinstance(row.get("symbol"), str) or not re.fullmatch(r"[A-Z0-9]{1,20}", row["symbol"])):
        raise IntakeError("SOURCE_IDENTITY_INCOMPLETE")
    return (owner, row["run_no"], row["id"], row["symbol"], row["side"], stamp)


def entry_context(opening):
    if not opening:
        return {"regime": "unknown", "revision": "unknown", "decision_source": "unknown"}
    features = opening.get("features", {})
    if not isinstance(features, dict):
        features = {}
    a, b = features.get("daily_trend"), features.get("ema50_200_4h")
    known = type(a) in (int, float) and type(b) in (int, float) and a in (-1, 0, 1) and b in (-1, 0, 1)
    regime = ("up" if a == 1 else "down") if known and a == b and a != 0 else "mixed" if known else "unknown"
    revision = opening.get("code_version")
    revision = revision if isinstance(revision, str) and REV.fullmatch(revision) else "unknown"
    source = opening.get("source")
    source = source if source in ("rules", "claude", "fallback", "brain") else "unknown"
    return {"regime": regime, "revision": revision, "decision_source": source}


def normalize_snapshot(spec, exported_ms, split_ms):
    history, history_hash = read_rows(spec.history)
    opens = {}
    ambiguous = set()
    learning_hash = None
    if spec.learning:
        learning_rows, learning_hash = read_rows(spec.learning)
        for row in learning_rows:
            if row.get("ev") != "open":
                continue
            key = identity(row, spec.owner, opening=True)
            if key in opens and opens[key] != row:
                ambiguous.add(key)
            opens[key] = row
    grouped = defaultdict(list)
    seen = set()
    duplicates = 0
    for row in history:
        key = identity(row, spec.owner)
        if (not integer(row.get("close_ms")) or row["close_ms"] < row["open_ms"] or
            row["close_ms"] > exported_ms or not lm.finite(row.get("net")) or abs(row["net"]) > 1e12 or
            not isinstance(row.get("partial", False), bool)):
            raise IntakeError("INVALID_OR_FUTURE_REALIZATION")
        # Deduplicate equivalent realizations independently of export metadata.
        fields = {k: row.get(k) for k in ("net", "close_ms", "partial", "margin", "entry", "exit", "fraction")}
        fingerprint = sha([key, fields])
        if fingerprint in seen:
            duplicates += 1
            continue
        seen.add(fingerprint)
        grouped[key].append(row)
    episodes = []
    incomplete = unknown = overlap = missing_risk = 0
    for key, rows in sorted(grouped.items()):
        rows.sort(key=lambda r: (r["close_ms"], not r.get("partial", False)))
        finals = [r for r in rows if not r.get("partial", False)]
        if not finals:
            incomplete += 1
            continue
        if len(finals) != 1 or rows[-1] is not finals[0]:
            raise IntakeError("CONFLICTING_FINAL_REALIZATIONS")
        if key in ambiguous:
            raise IntakeError("CONFLICTING_ENTRY_PROVENANCE")
        final = finals[0]
        opening = opens.get(key)
        ctx = entry_context(opening)
        if ctx["revision"] == "unknown" or ctx["regime"] == "unknown" or ctx["decision_source"] == "unknown":
            unknown += 1
        if final["close_ms"] < split_ms:
            role = "research"
        elif key[-1] >= split_ms:
            role = "validation"
        else:
            role = "overlap_excluded"
            overlap += 1
        risk = opening.get("risk_plan_usd") if opening else None
        if not lm.finite(risk) or risk <= 0:
            risk = final.get("risk_plan_usd")
        net = sum(r["net"] for r in rows)
        normalized = net / risk if lm.finite(risk) and risk > 0 else None
        normalized = normalized if lm.finite(normalized) and abs(normalized) <= 10000 else None
        if normalized is None:
            missing_risk += 1
        excursions = {name:max([r[name] for r in rows if lm.finite(r.get(name)) and 0<=r[name]<=10000],default=None)
                      for name in ("mfe_r","mae_r")}
        episode = {"id": lm.digest(list(key)), "source_bot": spec.owner, "run_no": key[1],
            "position_id": key[2], "symbol": key[3], "side": key[4], "open_ms": key[-1],
            "close_ms": final["close_ms"], "net": net, "net_r": normalized, "parts": len(rows),
            "role": role, **ctx, **excursions, "regime_method": "desk_daily_and_ema50_200_4h",
            "exit": "take_profit" if final.get("why") in ("TP", "take_profit", "take profit") else
                    "stop_loss" if final.get("why") in ("SL", "stop_loss", "stop loss") else "other"}
        episodes.append(episode)
    verdict = "UNRESOLVED" if unknown or missing_risk or not spec.learning else "PASS_WITH_WARNING" if duplicates or incomplete or overlap else "PASS"
    report = {"source_bot": spec.owner, "declared_mode": "paper", "history_sha256": history_hash,
        "learning_sha256": learning_hash, "history_rows": len(history), "completed": len(episodes),
        "duplicates": duplicates, "incomplete": incomplete, "unknown_entry_context": unknown,
        "overlap_excluded": overlap, "missing_risk": missing_risk, "verdict": verdict}
    return episodes, report


def build_bundle(snapshots, *, exported_ms, validation_start_ms, paper_confirmed=False):
    if (paper_confirmed is not True or not integer(exported_ms, 1) or
        not integer(validation_start_ms, 1) or validation_start_ms > exported_ms or
        not 1 <= len(snapshots) <= 2 or len({s.owner for s in snapshots}) != len(snapshots)):
        raise IntakeError("PAPER_DECLARATION_OR_SPLIT_REQUIRED")
    episodes, reports = [], []
    for spec in sorted(snapshots, key=lambda s: s.owner):
        rows, report = normalize_snapshot(spec, exported_ms, validation_start_ms)
        episodes.extend(rows); reports.append(report)
    if len(episodes) > MAX_EPISODES:
        raise IntakeError("BUNDLE_EPISODE_CAPACITY")  # never silently select winners or truncate
    payload = {"schema": SCHEMA, "exported_ms": exported_ms, "validation_start_ms": validation_start_ms,
        "sources": reports, "episodes": sorted(episodes, key=lambda e: (e["close_ms"], e["id"]))}
    validate_payload(payload)
    bundle = {"payload": payload, "sha256": sha(payload)}
    if len(canonical(bundle)) > MAX_BUNDLE_BYTES:
        raise IntakeError("BUNDLE_SIZE_CAPACITY")
    return bundle


def write_bundle(bundle, output, snapshots):
    """Create-only destination, outside all source directories. Never overwrite."""
    output = Path(output)
    if output.name != "experience_seed.json" or output.is_symlink():
        raise IntakeError("OUTPUT_NAME_OR_SYMLINK")
    target = output.resolve()
    for s in snapshots:
        for path in (s.history, s.learning):
            if path and (Path(path).resolve().parent == target.parent or Path(path).resolve().parent in target.parents):
                raise IntakeError("OUTPUT_WITHIN_SOURCE_DIRECTORY")
    validate_payload(bundle.get("payload"))
    if sha(bundle["payload"]) != bundle.get("sha256"):
        raise IntakeError("BUNDLE_HASH_MISMATCH")
    # Atomic create-only publication. A reader never observes a half-written seed.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent,prefix=".experience-",delete=False) as stream:
            temporary=Path(stream.name)
            stream.write(canonical(bundle) + b"\n")
            stream.flush();os.fsync(stream.fileno())
        os.link(temporary,output,follow_symlinks=False)
        directory=os.open(output.parent,os.O_RDONLY | getattr(os,"O_DIRECTORY",0))
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def read_bundle(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor,"rb") as stream:
        meta=os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_size>MAX_BUNDLE_BYTES:
            raise IntakeError("BUNDLE_TYPE_OR_SIZE")
        raw = stream.read(MAX_BUNDLE_BYTES + 1)
    if len(raw) > MAX_BUNDLE_BYTES:
        raise IntakeError("BUNDLE_SIZE_CAPACITY")
    obj = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(IntakeError("BUNDLE_NONFINITE")))
    if not isinstance(obj, dict) or not HEX.fullmatch(str(obj.get("sha256", ""))) or sha(obj.get("payload")) != obj["sha256"]:
        raise IntakeError("BUNDLE_HASH_MISMATCH")
    validate_payload(obj["payload"])
    return obj


def validate_payload(p):
    if (not isinstance(p, dict) or p.get("schema") != SCHEMA or not integer(p.get("exported_ms"), 1) or
        not integer(p.get("validation_start_ms"), 1) or p["validation_start_ms"] > p["exported_ms"] or
        not isinstance(p.get("episodes"), list) or len(p["episodes"]) > MAX_EPISODES or
        not isinstance(p.get("sources"), list) or not 1 <= len(p["sources"]) <= 2):
        raise IntakeError("BUNDLE_SCHEMA")
    owners = set()
    source_fields = {"source_bot", "declared_mode", "history_sha256", "learning_sha256", "history_rows", "completed",
                     "duplicates", "incomplete", "unknown_entry_context", "overlap_excluded", "missing_risk", "verdict"}
    episode_fields = {"id", "source_bot", "run_no", "position_id", "symbol", "side", "open_ms", "close_ms", "net", "net_r",
                      "parts", "role", "regime", "revision", "decision_source", "regime_method", "exit", "mfe_r", "mae_r"}
    for source in p["sources"]:
        if not isinstance(source, dict) or set(source) != source_fields:
            raise IntakeError("BUNDLE_SOURCE_SCHEMA")
        if any(not integer(source[k]) for k in ("history_rows", "completed", "duplicates", "incomplete", "unknown_entry_context", "overlap_excluded", "missing_risk")):
            raise IntakeError("BUNDLE_SOURCE_COUNTS")
        if source["learning_sha256"] is not None and not HEX.fullmatch(str(source["learning_sha256"])):
            raise IntakeError("BUNDLE_SOURCE_HASH")
        owner = source.get("source_bot")
        if (owner not in ("hawk", "bull") or owner in owners or source.get("declared_mode") != "paper" or
            not HEX.fullmatch(str(source.get("history_sha256", ""))) or
            source.get("verdict") not in ("PASS", "PASS_WITH_WARNING", "UNRESOLVED")):
            raise IntakeError("BUNDLE_SOURCE_PROVENANCE")
        owners.add(owner)
    seen = set()
    for e in p["episodes"]:
        if (not isinstance(e, dict) or set(e) != episode_fields or e.get("source_bot") not in owners or e.get("id") in seen or
            not re.fullmatch(r"[a-f0-9]{20}", str(e.get("id", ""))) or
            not integer(e.get("run_no"),1) or not integer(e.get("position_id"),1) or
            not integer(e.get("open_ms")) or not integer(e.get("close_ms")) or
            not e["open_ms"] <= e["close_ms"] <= p["exported_ms"] or
            type(e.get("side")) is not int or e["side"] not in (-1,1) or
            not re.fullmatch(r"[A-Z0-9]{1,20}", str(e.get("symbol", ""))) or
            not lm.finite(e.get("net")) or abs(e["net"]) > 1e14 or
            (e.get("net_r") is not None and (not lm.finite(e["net_r"]) or abs(e["net_r"]) > 10000)) or
            e.get("regime") not in ("up","down","mixed","unknown") or
            (e.get("revision") != "unknown" and not REV.fullmatch(str(e.get("revision", "")))) or
            e.get("decision_source") not in ("rules","claude","fallback","brain","unknown") or
            e.get("regime_method") != "desk_daily_and_ema50_200_4h" or
            e.get("exit") not in ("take_profit","stop_loss","other") or not integer(e.get("parts"),1)):
            raise IntakeError("BUNDLE_EPISODE_SCHEMA")
        if e["id"] != lm.digest([e["source_bot"],e["run_no"],e["position_id"],e["symbol"],e["side"],e["open_ms"]]):
            raise IntakeError("BUNDLE_IDENTITY_MISMATCH")
        role = "research" if e["close_ms"] < p["validation_start_ms"] else (
            "validation" if e["open_ms"] >= p["validation_start_ms"] else "overlap_excluded")
        if e.get("role") != role:
            raise IntakeError("BUNDLE_PARTITION_CHANGED")
        for name in ("mfe_r","mae_r"):
            if e.get(name) is not None and (not lm.finite(e[name]) or not 0<=e[name]<=10000):
                raise IntakeError("BUNDLE_EXCURSION_SCHEMA")
        seen.add(e["id"])
    for source in p["sources"]:
        subset=[e for e in p["episodes"] if e["source_bot"]==source["source_bot"]]
        unknown=sum(e["regime"]=="unknown" or e["revision"]=="unknown" or e["decision_source"]=="unknown" for e in subset)
        missing=sum(e["net_r"] is None for e in subset)
        overlap=sum(e["role"]=="overlap_excluded" for e in subset)
        if (source["completed"]!=len(subset) or source["unknown_entry_context"]!=unknown or
            source["missing_risk"]!=missing or source["overlap_excluded"]!=overlap or
            source["history_rows"] < sum(e["parts"] for e in subset)+source["duplicates"]+source["incomplete"]):
            raise IntakeError("BUNDLE_SOURCE_COMPLETENESS")
        verdict="UNRESOLVED" if unknown or missing or source["learning_sha256"] is None else (
            "PASS_WITH_WARNING" if source["duplicates"] or source["incomplete"] or overlap else "PASS")
        if source["verdict"]!=verdict:
            raise IntakeError("BUNDLE_QUALITY_MISMATCH")


def view(bundle, summaries, now_ms):
    """Separate cross-bot evidence: never contributes to Brain win rate or cash."""
    p = bundle["payload"]
    if now_ms < p["exported_ms"]:
        raise IntakeError("BUNDLE_NOT_YET_AVAILABLE")
    relevant = {lm.entry_context(s)["regime"] for s in summaries.values()} - {"unknown"}
    rows = [e for e in p["episodes"] if now_ms-lm.WINDOW <= e["close_ms"] <= now_ms]
    groups = defaultdict(list)
    for e in rows:
        if e["regime"] in relevant and e["revision"] != "unknown" and lm.finite(e["net_r"]):
            groups[(e["source_bot"],e["run_no"],e["revision"],e["decision_source"],e["side"],e["regime"])].append(e)
    allowed = {s["source_bot"] for s in p["sources"] if s["verdict"] in ("PASS","PASS_WITH_WARNING")}
    lessons = []
    for cohort, episodes in sorted(groups.items()):
        episodes.sort(key=lambda e: (e["close_ms"], e["id"]))
        train = [e for e in episodes if e["role"] == "research"]
        valid = [e for e in episodes if e["role"] == "validation"]
        if (cohort[0] not in allowed or len(train)<8 or len(valid)<4 or
            len({e["close_ms"]//lm.DAY for e in train+valid})<3 or len({e["close_ms"]//lm.DAY for e in valid})<2 or
            now_ms-max(e["close_ms"] for e in train+valid)>lm.FRESH):
            continue
        a,b=lm.metrics(train),lm.metrics(valid)
        weak=a["mean_net_r"]<0 and b["mean_net_r"]<0 and b["win_rate_95pct"][1]<.5
        strong=a["mean_net_r"]>0 and b["mean_net_r"]>0 and b["win_rate_95pct"][0]>.5
        if not (weak or strong):continue
        lessons.append({"id":lm.digest([bundle["sha256"],cohort]),"source_bot":cohort[0],"run_no":cohort[1],
            "entry_revision":cohort[2],"decision_source":cohort[3],"side":"LONG" if cohort[4]==1 else "SHORT",
            "entry_regime":cohort[5],"finding":"historical_weakness" if weak else "historical_strength",
            "research":a,"later_partition":b,"evidence_ids":[e["id"] for e in (train+valid)[-4:]],
            "transferability":"Different strategy/trend definition; hypothesis for Brain, never a hard rule or causal result.",
            "validation_type":"Fixed historical chronological split; not an independent prospective trial."})
    # Include both outcomes when available; deterministic latest cases, no winner cherry-picking.
    matching=[e for e in rows if e["regime"] in relevant or e["regime"]=="unknown"]
    cases=[]
    for owner in sorted(allowed | {s["source_bot"] for s in p["sources"]}):
        group=[e for e in matching if e["source_bot"]==owner and e["role"]!="overlap_excluded"]
        for win in (True,False):
            choices=[e for e in group if (e["net"]>0)==win]
            if choices:cases.append(max(choices,key=lambda e:(e["close_ms"],e["id"])))
    result={"schema":SCHEMA,"status":"historical_evidence" if lessons else "insufficient_data",
        "bundle_id":bundle["sha256"],"exported_ms":p["exported_ms"],"validation_start_ms":p["validation_start_ms"],
        "quality":p["sources"],"lessons":lessons[:2],"cases":cases[:4],
        "source_scope":"Hawk/Bull PAPER snapshots, separate from Brain performance; sources may be correlated.",
        "case_selection":"Latest positive and nonpositive case per bot; illustrative, not an unbiased performance sample."}
    if len(canonical(result))>MAX_VIEW_CHARS:raise IntakeError("EXPERIENCE_CONTEXT_CAPACITY")
    return result


def load_view(root, summaries, now_ms):
    path=Path(root)/"experience_seed.json"
    if not path.exists():return {"status":"not_imported","lessons":[],"cases":[]}
    try:
        if path.is_symlink():raise IntakeError("BUNDLE_SYMLINK")
        return view(read_bundle(path),summaries,now_ms)
    except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return {"status":"unavailable","lessons":[],"cases":[]}


def main():
    parser=argparse.ArgumentParser(description="Build a reviewable seed from copied PAPER snapshots; no runtime access")
    parser.add_argument("--hawk-history",type=Path);parser.add_argument("--hawk-learning",type=Path)
    parser.add_argument("--bull-history",type=Path);parser.add_argument("--bull-learning",type=Path)
    parser.add_argument("--validation-start-ms",type=int,required=True)
    parser.add_argument("--confirm-paper",action="store_true")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    specs=[Snapshot(owner,getattr(args,owner+"_history"),getattr(args,owner+"_learning"))
           for owner in ("hawk","bull") if getattr(args,owner+"_history")]
    try:
        bundle=build_bundle(specs,exported_ms=int(time.time()*1000),validation_start_ms=args.validation_start_ms,
                            paper_confirmed=args.confirm_paper)
        write_bundle(bundle,args.output,specs)
        print(json.dumps({"status":"prepared_for_review","bundle_id":bundle["sha256"],"sources":bundle["payload"]["sources"]}))
    except (OSError,ValueError,TypeError,KeyError):
        raise SystemExit("EXPERIENCE_INTAKE_FAILED") from None


if __name__ == "__main__":main()
