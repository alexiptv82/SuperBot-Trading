"""Single writer, hash chained JSONL segments. No automatic deletion/repair.

A cycle and its restart cache are ONE committed line. Restart scans the journal;
no separately updated cursor can cause missed events. A torn tail blocks writing
and requires explicit operator recovery, preserving every byte as evidence.
"""
import fcntl
import os
from pathlib import Path
from .common import Freeze, canonical, decode, sha


class Journal:
    def __init__(self, root, *, max_segment_bytes=8*1024*1024):
        self.root = Path(root).resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = open(self.root / "writer.lock", "a+b")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise Freeze("observer_already_running") from None
        self.limit = max_segment_bytes
        self.ids, self.cache = {}, {}
        self.chain, self.sequence = "0"*64, 0
        self.segment = 1
        try:
            paths = sorted(self.root.glob("events-*.jsonl"))
            for number, path in enumerate(paths, 1):
                if path.name != f"events-{number:08d}.jsonl" or path.is_symlink():
                    raise Freeze("journal_segment_sequence")
                with path.open("rb") as stream:
                    for line in stream:
                        if not line.endswith(b"\n"):
                            raise Freeze("journal_truncated_tail")
                        envelope = decode(line)
                        body = envelope["body"]
                        expected = sha([self.chain, self.sequence+1, body])
                        if envelope.get("hash") != expected or envelope.get("previous") != self.chain or envelope.get("sequence") != self.sequence+1:
                            raise Freeze("journal_integrity")
                        if body["event_id"] in self.ids:
                            raise Freeze("journal_duplicate")
                        self._accept(body, expected)
                self.segment = number
        except BaseException:
            self.close()
            raise

    def _accept(self, body, chain):
        self.ids[body["event_id"]] = sha(body)
        if "cache" in body:
            self.cache[body["portfolio"]] = body["cache"]
        self.chain = chain
        self.sequence += 1

    def append(self, body):
        event_id = body["event_id"]
        if event_id in self.ids:
            if self.ids[event_id] != sha(body):
                raise Freeze("event_id_collision")
            return False
        chain = sha([self.chain, self.sequence+1, body])
        line = (canonical({"sequence":self.sequence+1,"previous":self.chain,"hash":chain,"body":body})+"\n").encode()
        path = self.root / f"events-{self.segment:08d}.jsonl"
        if path.exists() and path.stat().st_size and path.stat().st_size+len(line) > self.limit:
            self.segment += 1
            path = self.root / f"events-{self.segment:08d}.jsonl"
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "ab") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        self._accept(body, chain)
        return True

    def close(self):
        if not self.lock.closed:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            self.lock.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
