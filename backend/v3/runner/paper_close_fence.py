"""PAPER sidecar CLOSE fence compatible with `open_serial` writer lock.

A fresh risk quote and paper_open are held under ``.brain-paper-open.lock``.
The genuine exit worker must acquire the SAME lock around its CLOSE journal
callbacks, so an exit cannot change realized PnL after the post-AI quote but
before the OPEN append. Only *cooperating* writers are serialized; no lock can
fence legacy code that has never adopted it. The sidecar exit lease remains
separate and held for its entire lifetime.

No network, no trading, no journal writes here; one lock inode, fail closed.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import time
from typing import Iterator

LOCK_FILE = ".brain-paper-open.lock"
WAIT_SECONDS = 5.0


class PaperCloseFenceBusy(RuntimeError):
    """Closed error vocabulary: invalid/unsafe/unavailable/timeout."""


@contextmanager
def paper_close_fence(data_dir: Path) -> Iterator[None]:
    """Exclusive owner of shared PAPER journal writer fence, max 5 s wait.

    CLOSE/stop activity should never wait indefinitely for an OPEN. If an
    opening is stuck, the exit tick becomes degraded and the watchdog may
    restart the worker; no new OPEN is authorized while the exit is degraded.
    """
    if (not isinstance(data_dir, Path) or not data_dir.is_absolute()
            or data_dir.is_symlink() or not data_dir.is_dir()):
        raise PaperCloseFenceBusy("invalid_paper_close_scope")
    fd = None
    locked = False
    try:
        root = data_dir.resolve(strict=True)
        lock = root / LOCK_FILE
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(lock, flags, 0o600)
        st = os.fstat(fd)
        lst = lock.lstat()
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or (st.st_mode & 0o077) != 0
                or (st.st_dev, st.st_ino) != (lst.st_dev, lst.st_ino)):
            raise PaperCloseFenceBusy("unsafe_paper_close_lease")
        deadline = time.monotonic() + WAIT_SECONDS
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PaperCloseFenceBusy("paper_close_writer_busy") from None
                time.sleep(0.025)
        yield
    except PaperCloseFenceBusy:
        raise
    except (OSError, ValueError, RuntimeError):
        raise PaperCloseFenceBusy("paper_close_lease_unavailable") from None
    finally:
        if fd is not None:
            if locked:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
