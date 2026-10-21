"""Scrittura dei file dell'AI in ombra: righe in aggiunta (append-only) e scritture atomiche. Niente viene mai cancellato."""
import gzip
import json
import os
import time


def day_of(ms: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))


def append_jsonl(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj, separators=(",", ":"), allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def append_gz(path: str, obj: dict) -> None:
    """Un membro gzip per riga: si legge con gzip.open come un unico file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "ab") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb") as g:
            g.write((json.dumps(obj, separators=(",", ":"), allow_nan=False) + "\n").encode())
        raw.flush()
        os.fsync(raw.fileno())


def atomic_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"), allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path: str):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
