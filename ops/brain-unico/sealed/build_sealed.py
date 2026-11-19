#!/usr/bin/env python3
"""Genera il bundle SIGILLATO `phase0_sealed.py` in modo DETERMINISTICO (nessun timestamp).

Il bundle e' un unico file di testo: un caricatore di poche righe in chiaro + i moduli revisionati incorporati come
commenti (`#|`), + la spec delle fonti. Si verifica con:
    python3 build_sealed.py --check      # esce 1 se il file committato non coincide con i sorgenti
    sha256sum phase0_sealed.py           # l'hash che l'operatore confronta prima di eseguire come root
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "phase0_sealed.py")
MODULES = (("inventory", os.path.join(ROOT, "inventory.py")),
           ("snapshot", os.path.join(ROOT, "phase0", "snapshot.py")),
           ("audit", os.path.join(ROOT, "phase0", "audit.py")),
           ("sealed_root", os.path.join(HERE, "sealed_root.py")))
SPEC = os.path.join(HERE, "sources.sealed.json")

LOADER = '''#!/usr/bin/env python3
"""SuperBot Brain Unico - bundle SIGILLATO della Fase 0 (opzione B). GENERATO da build_sealed.py: NON modificare.

Uso (selftest: nessun privilegio e nessun dato; preflight/full: solo root, solo da una directory di root):
    python3 -I phase0_sealed.py selftest
    python3 -I phase0_sealed.py preflight --expect-sha256 <HASH>
    python3 -I phase0_sealed.py full --expect-sha256 <HASH> --auth-ref <RIFERIMENTO>
Moduli incorporati (sha256 dei sorgenti):
%(hashes)s
"""
import hashlib
import json
import os
import sys
import types

_ORDER = %(order)r


def _extract(raw):
    blocks, cur, buf = {}, None, []
    for ln in raw.decode("utf-8").split("\\n"):
        if ln.startswith("#@@ BEGIN "):
            cur, buf = ln[len("#@@ BEGIN "):], []
        elif ln.startswith("#@@ END "):
            blocks[cur] = "\\n".join(buf) + "\\n"
            cur = None
        elif cur is not None:
            if not ln.startswith("#|"):
                raise SystemExit("bundle corrotto")
            buf.append(ln[2:])
    return blocks


def _boot():
    path = os.path.abspath(__file__)
    with open(path, "rb") as fh:
        raw = fh.read()
    blocks = _extract(raw)
    sys._phase0_sealed = True
    for name in _ORDER:
        mod = types.ModuleType(name)
        mod.__file__ = "<sealed:%%s>" %% name
        sys.modules[name] = mod
        exec(compile(blocks[name], mod.__file__, "exec"), mod.__dict__)
    spec = json.loads(blocks["sources.json"])
    hashes = {n: hashlib.sha256(blocks[n].encode()).hexdigest() for n in _ORDER + ("sources.json",)}
    return sys.modules["sealed_root"].main(sys.argv[1:], data=raw, spec=spec, code_path=path, module_hashes=hashes)


if __name__ == "__main__":
    sys.exit(_boot())
'''


def _read(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        s = fh.read()
    assert "\r" not in s and s.endswith("\n"), path
    return s


def _block(name: str, src: str) -> str:
    lines = src.split("\n")[:-1]
    assert not any(l.startswith("#@@") for l in lines)
    return "#@@ BEGIN %s\n%s\n#@@ END %s\n" % (name, "\n".join("#|" + l for l in lines), name)


def build() -> str:
    mods = [(n, _read(p)) for n, p in MODULES]
    spec_src = _read(SPEC)
    json.loads(spec_src)                                    # deve essere JSON valido
    mods.append(("sources.json", spec_src))
    hashes = "\n".join("  %-12s %s" % (n, hashlib.sha256(s.encode()).hexdigest()) for n, s in mods)
    head = LOADER % {"hashes": hashes, "order": tuple(n for n, _ in MODULES)}
    return head + "\n" + "\n".join(_block(n, s) for n, s in mods)


def main(argv: list) -> int:
    text = build()
    if "--check" in argv:
        try:
            with open(OUT, encoding="utf-8", newline="") as fh:
                cur = fh.read()
        except OSError:
            cur = None
        print("OK: bundle aggiornato" if cur == text else "DIFFERENTE: rigenerare con build_sealed.py")
        return 0 if cur == text else 1
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    print("scritto", OUT, hashlib.sha256(text.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
