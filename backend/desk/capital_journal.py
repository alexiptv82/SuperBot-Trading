"""Single-writer durable capital journal for PAPER-only portfolio snapshots.

A journal record is an atomic proposed account+capital state (not an instruction
to create credit). fsync intent BEFORE replace(state), with deterministic recovery.
Never use this on live containers without explicit release approval & migration.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping

from .capital_manager import CapitalInvariantError, dec


def _canonical(x: object) -> bytes:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def _hash(x: object) -> str:
    return hashlib.sha256(_canonical(x)).hexdigest()


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf8") as fp:
        parsed = json.load(fp)
    if not isinstance(parsed, dict):
        raise CapitalInvariantError("state is not a JSON object")
    return parsed


def _sync_directory(parent: Path) -> None:
    fd = os.open(str(parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _replace_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".capital-v1-tmp")
    if tmp.exists():
        raise CapitalInvariantError("unfinished temp state requires review")
    with tmp.open("xb") as f:
        f.write(_canonical(payload) + b"\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _sync_directory(path.parent)


class PaperCapitalJournal:
    """Offline transaction boundary: one bot owner, one state file per account.

    Both snapshots and the journal must reside on the SAME persistent volume.
    Append-only transaction contains exact post-state and pre/post SHA-256.
    Journal recovery MUST run before bot's next market or command iteration.
    """

    def __init__(self, root: str, bot: str):
        if bot not in ("hawk", "bull"):
            raise CapitalInvariantError("unknown portfolio")
        self.root = Path(root)
        self.state_path = self.root / "state_v2.json"
        self.journal_path = self.root / "capital-v1-journal.jsonl"
        self.bot = bot
        self._cached_records = None
        self._cached_stat = None

    def _records(self) -> list:
        try:
            stat=self.journal_path.stat()
            signature=(stat.st_ino,stat.st_size,stat.st_mtime_ns)
        except FileNotFoundError:
            signature=None
        if self._cached_records is not None and signature==self._cached_stat:
            return self._cached_records
        try:
            with self.journal_path.open("rb") as f:
                raw = f.read()
        except FileNotFoundError:
            return []
        if raw and not raw.endswith(b"\n"):
            raise CapitalInvariantError("truncated capital journal (manual recovery required)")
        events = []
        prev_hash = "GENESIS"
        for line in raw.splitlines():
            try:
                rec = json.loads(line)
            except (ValueError, TypeError) as e:
                raise CapitalInvariantError("journal contains invalid JSON") from e
            digest = rec.pop("checksum", None)
            if not isinstance(digest, str) or _hash(rec) != digest:
                raise CapitalInvariantError("journal checksum mismatch")
            if rec.get("prev_hash") != prev_hash:
                raise CapitalInvariantError("journal hash chain mismatch")
            rec["checksum"] = digest
            prev_hash = digest
            # Only the last record needs its full post_state for crash recovery.
            if events:
                events[-1].pop("post_state",None)
            events.append(rec)
        self._cached_records=events
        self._cached_stat=signature
        return events

    def recover(self) -> dict:
        state = _load_json(self.state_path)
        records = self._records()
        if not records:
            return state
        # A transaction may be recorded but not reflected by the state file.
        # Never blindly overwrite an unrelated or more recent state.
        last = records[-1]
        h = _hash(state)
        # Crash during fsynced temp->rename may leave an uncommitted tmp file.
        # Verified journal is authoritative; never load/guess from the temp.
        temp=self.state_path.with_name(self.state_path.name+".capital-v1-tmp")
        if h in (last["pre_hash"],last["post_hash"]) and temp.exists():
            temp.unlink()
            _sync_directory(self.state_path.parent)
        if h == last["post_hash"]:
            return state
        if h == last["pre_hash"]:
            new = last["post_state"]
            if _hash(new) != last["post_hash"]:
                raise CapitalInvariantError("journal recovery post-state corrupt")
            _replace_json(self.state_path, new)
            return new
        raise CapitalInvariantError("account state diverges from durable journal")

    def commit_snapshot(self, state_after: Mapping, *, event_id: str, paper_mode: bool = True) -> dict:
        """Atomic journal+snapshot for every bot state mutation (trades included).

        One running PAPER bot is the exclusive writer. Each persisted state is
        journaled, so a trade cannot race ahead of a vault transfer on disk.
        A money transfer must conserve cash+vault, and cannot alter positions.
        """
        if not paper_mode:
            raise CapitalInvariantError("journal V1 is PAPER-only")
        if not isinstance(state_after, dict) or not event_id or len(event_id) > 128:
            raise CapitalInvariantError("invalid transaction")
        before = self.recover()
        previous = (before.get("capital") or {})
        after = copy.deepcopy(dict(state_after))
        capital = after.get("capital")
        if not isinstance(capital, dict) or capital.get("schema_version") != 1:
            raise CapitalInvariantError("missing capital schema")
        previous_revision = int(previous.get("revision", 0))
        capital["revision"] = previous_revision + 1
        after["capital"] = capital
        old_v = dec((previous.get("vault") or {}).get("balance", 0))
        new_v = dec((capital.get("vault") or {}).get("balance", 0))
        old_main, new_main = before.get("main") or {}, after.get("main") or {}
        if new_v != old_v:
            if not event_id.startswith(("capital:rollover:", "capital:settle:", "capital:withdraw:")):
                raise CapitalInvariantError("vault balance changed outside authorized transfer")
            old_cash = dec(old_main.get("cash", 0))
            new_cash = dec(new_main.get("cash", 0))
            if new_cash - old_cash != -(new_v - old_v):
                raise CapitalInvariantError("transfer violates cash + vault conservation")
            if old_main.get("positions") != new_main.get("positions") or old_main.get("closed") != new_main.get("closed"):
                raise CapitalInvariantError("transfer mutated trade state")
        records = self._records()
        if any(rec.get("event_id") == event_id for rec in records):
            raise CapitalInvariantError("duplicate event: explicit receipt required")
        event = {"schema": 1, "bot": self.bot, "event_id": event_id,
                 "revision_from": previous_revision, "revision_to": previous_revision + 1,
                 "prev_hash": records[-1]["checksum"] if records else "GENESIS",
                 "pre_hash": _hash(before), "post_hash": _hash(after),
                 "post_state": after}
        event["checksum"] = _hash(event)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("ab") as fp:
            fp.write(_canonical(event) + b"\n")
            fp.flush()
            os.fsync(fp.fileno())
        _sync_directory(self.root)
        _replace_json(self.state_path, after)
        # Keep the hot single-writer cache coherent; avoid quadratic full-journal
        # rereads at every market state save. Startup still verifies full chain.
        if records:
            records[-1].pop("post_state",None)
        records.append(event)
        stat=self.journal_path.stat()
        self._cached_records=records
        self._cached_stat=(stat.st_ino,stat.st_size,stat.st_mtime_ns)
        return after

    def commit(self, state_before: Mapping, state_after: Mapping,
               *, event_id: str, expected_revision: int) -> dict:
        if not event_id or len(event_id) > 128 or any(c.isspace() for c in event_id):
            raise CapitalInvariantError("invalid event identifier")
        if expected_revision < 0:
            raise CapitalInvariantError("negative revision")
        if not isinstance(state_before, dict) or not isinstance(state_after, dict):
            raise CapitalInvariantError("only dict snapshots accepted")
        before = copy.deepcopy(state_before)
        after = copy.deepcopy(state_after)
        rev_before = int((before.get("capital") or {}).get("revision", 0))
        rev_after = int((after.get("capital") or {}).get("revision", 0))
        if rev_before != expected_revision or rev_after != expected_revision + 1:
            raise CapitalInvariantError("unexpected state revision")
        old = self.recover()
        if _hash(old) != _hash(before):
            raise CapitalInvariantError("state changed since transaction prepared")
        # Prevent accidentally hiding exchange trades, position changes or brain
        # modifications inside a mere capital transfer journal record.
        safe_keys = {"capital", "main"}
        if any(before.get(k) != after.get(k) for k in set(before) | set(after) if k not in safe_keys):
            raise CapitalInvariantError("noncapital fields changed during capital transfer")
        old_main, new_main = before.get("main") or {}, after.get("main") or {}
        for k in set(old_main) | set(new_main):
            if k != "cash" and old_main.get(k) != new_main.get(k):
                raise CapitalInvariantError("position or account history modified by transfer")
        old_cash = dec(old_main.get("cash",0))
        new_cash = dec(new_main.get("cash",0))
        old_vault = dec(((before.get("capital") or {}).get("vault") or {}).get("balance",0))
        new_vault = dec(((after.get("capital") or {}).get("vault") or {}).get("balance",0))
        if new_cash < 0 or new_vault < 0 or new_cash - old_cash != -(new_vault - old_vault):
            raise CapitalInvariantError("capital conservation violation")
        records = self._records()
        if any(x["event_id"] == event_id for x in records):
            raise CapitalInvariantError("duplicate event id; reconcile receipt instead")
        record = {
            "schema": 1, "bot": self.bot, "event_id": event_id,
            "revision_from": expected_revision, "revision_to": rev_after,
            "prev_hash": records[-1]["checksum"] if records else "GENESIS",
            "pre_hash": _hash(before), "post_hash": _hash(after),
            "post_state": after,
        }
        record["checksum"] = _hash(record)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("ab") as f:
            f.write(_canonical(record) + b"\n")
            f.flush()
            os.fsync(f.fileno())
        _sync_directory(self.root)
        _replace_json(self.state_path, after)
        return after
