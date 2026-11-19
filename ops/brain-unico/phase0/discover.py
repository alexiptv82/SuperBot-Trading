#!/usr/bin/env python3
"""Fase 0 — discovery NON privilegiata del codice in esecuzione e dei metadati delle fonti.

Cosa fa (solo metadati, nessun contenuto di dati):
- processi rilevanti e unita' systemd `superbot-*` (stato, utente, directory di lavoro, ExecStart);
- per ogni percorso della spec: esiste? permessi/owner numerici, leggibile da questo utente? dimensione;
- `codefp`: impronta dei file .py di una directory di codice (blob SHA1 stile git) e confronto con i commit
  di un clone di laboratorio, per ricavare il commit/branch che corrisponde davvero a cio' che gira.

Cosa NON fa (e i test lo verificano):
- non apre mai /proc/<pid>/environ ne' file di ambiente; non usa `systemctl cat/show -p Environment`;
- gli argomenti di riga di comando sono redatti: restano nomi di opzioni e percorsi, i valori diventano <arg>;
- nessun comando fuori da una lista chiusa (ps, systemctl show/list-units, id, uname, df), nessuna shell;
- non usa sudo, docker, journalctl; cio' che non e' leggibile e' riportato come tale (non_readable), mai aggirato;
- non apre file di dati, journal, DB; non scrive nulla tranne il report (nuovo, 0600, fuori da repo git).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from typing import Any, Callable, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import inventory as inv  # noqa: E402

RELEVANT = re.compile(r"superbot|brain|arena|falco|toro|hawk|bull|exit[-_]|v3|uvicorn|gunicorn", re.I)
UNIT_RE = re.compile(r"superbot-[A-Za-z0-9@:._-]{1,100}\.service")
SECRETISH = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|[A-Za-z0-9+/_=-]{32,}|://[^/\s:@]+:[^@\s]+@|eyJ[A-Za-z0-9_-]{10,})")
SHOW_PROPS = ("Id", "LoadState", "ActiveState", "SubState", "Result", "MainPID", "User", "NRestarts",
              "WorkingDirectory", "FragmentPath", "ExecStart", "ActiveEnterTimestamp", "EnvironmentFiles")
ALLOWED = {"ps", "systemctl", "id", "uname", "df"}

Runner = Callable[[list], tuple]


def real_runner(argv: list) -> tuple:
    if argv[0] not in ALLOWED:
        raise ValueError("command_not_allowed")
    if argv[0] == "systemctl" and (len(argv) < 2 or argv[1] not in ("show", "list-units")):
        raise ValueError("systemctl_subcommand_not_allowed")
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=20, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, type(exc).__name__
    return r.returncode, r.stdout


_FLAG_LONG = re.compile(r"--[A-Za-z][A-Za-z0-9-]{0,40}")
_SEG_SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]{10,}|[A-Za-z0-9+_=-]{32,})")


def _clean_path(tok: str) -> str:
    tok = re.split(r"[?#;=]", tok, 1)[0]                          # niente querystring/frammenti/valori incorporati
    return "/".join("<redacted>" if _SEG_SECRET.fullmatch(s) else s for s in tok.split("/"))


def redact_args(cmdline: str) -> str:
    """Restano: nome dell'eseguibile, nomi di opzione, percorsi ripuliti, modulo dopo -m. Tutto il resto -> <arg>."""
    toks = cmdline.split()
    if not toks:
        return ""
    out = [os.path.basename(toks[0])]
    prev = ""
    for t in toks[1:]:
        if t.startswith("--"):
            name, eq, _ = t.partition("=")
            out.append((name if _FLAG_LONG.fullmatch(name) else "<arg>") + ("=<arg>" if eq else ""))
        elif t.startswith("-") and len(t) > 1:
            out.append(t if len(t) == 2 and t[1].isalpha() else (t[:2] + "<arg>" if t[1].isalpha() else "<arg>"))
        elif "://" in t:
            out.append("<redacted>")
        elif t.startswith(("/", "./")) or t.endswith((".py", ".json", ".service")):
            out.append(_clean_path(t))
        elif SECRETISH.search(t):
            out.append("<redacted>")
        elif prev == "-m" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", t):
            out.append(t)                                          # modulo python
        else:
            out.append("<arg>")
        prev = t
    return " ".join(out)


def parse_ps(text: str) -> list:
    rows = []
    for line in text.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        pid, ppid, user, etimes, args = parts
        if RELEVANT.search(args):
            rows.append({"pid": int(pid), "ppid": int(ppid), "user": user,
                         "elapsed_s": int(etimes) if etimes.isdigit() else None, "cmd": redact_args(args)})
    return rows


def parse_show(text: str) -> dict:
    d: dict[str, Any] = {}
    for line in text.splitlines():
        k, eq, v = line.partition("=")
        if not eq or k not in SHOW_PROPS:
            continue
        if k == "ExecStart":
            m = re.search(r"argv\[\]=(.*?)(?: ; ignore_errors=|\s*\}|$)", v)
            d[k] = redact_args(m.group(1)) if m else "<unparsed>"
        elif k == "EnvironmentFiles":
            d[k] = [re.sub(r"\s*\(.*\)$", "", x) for x in v.split() if x.startswith("/")][:5]   # solo il percorso
        else:
            d[k] = v
    return d


def discover_services(run: Runner) -> dict:
    rc, out = run(["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--plain", "--no-pager"])
    if rc != 0:
        return {"readable": False, "units": []}
    names = sorted({t for line in out.splitlines() for t in line.split()[:1] if UNIT_RE.fullmatch(t)})
    units = []
    for n in names:
        argv = ["systemctl", "show", n, "--no-pager"] + [x for p in SHOW_PROPS for x in ("-p", p)]
        rc2, o2 = run(argv)
        units.append({"unit": n, **(parse_show(o2) if rc2 == 0 else {"error": "show_failed"})})
    return {"readable": True, "units": units}


def path_meta(path: str) -> dict:
    """Solo lstat/access. Nessuna lettura di contenuto, nessun listing di directory."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return {"path": path, "status": "not_found"}
    except PermissionError:
        return {"path": path, "status": "permission_denied"}
    except OSError as exc:
        return {"path": path, "status": "error:" + type(exc).__name__}
    kind = ("symlink" if stat.S_ISLNK(st.st_mode) else "dir" if stat.S_ISDIR(st.st_mode) else
            "file" if stat.S_ISREG(st.st_mode) else "special")
    readable = os.access(path, os.R_OK | (os.X_OK if kind == "dir" else 0))
    return {"path": path, "status": "ok" if readable else "non_readable", "kind": kind,
            "mode": oct(stat.S_IMODE(st.st_mode)), "uid": st.st_uid, "gid": st.st_gid, "size": st.st_size,
            "mtime": int(st.st_mtime)}


# ------------------------------------------------------------------ codefp

def _blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def fingerprint_dir(root: str, exts: tuple = (".py",), max_bytes: int = 2_000_000) -> dict:
    fp: dict[str, str] = {}
    skipped = 0
    for d, dn, fn in os.walk(root, followlinks=False):
        dn[:] = sorted(x for x in dn if x not in (".git", "__pycache__", ".venv", "node_modules"))
        for n in sorted(fn):
            if not n.endswith(exts) or inv.SENSITIVE.search(n):
                continue
            p = os.path.join(d, n)
            try:
                st = os.lstat(p)
                if not stat.S_ISREG(st.st_mode) or st.st_size > max_bytes:
                    skipped += 1
                    continue
                with open(p, "rb") as fh:
                    fp[os.path.relpath(p, root)] = _blob_sha1(fh.read())
            except OSError:
                skipped += 1
    return {"files": fp, "skipped": skipped}


def match_commits(fp: dict, repo: str, refs: list, subdir: str = "", exts: tuple = (".py",)) -> list:
    """Per ogni ref: file identici / diversi / solo nel deploy / solo nel commit. Ordinato per somiglianza."""
    rows = []
    for ref in refs:
        r = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--full-tree", ref, "--"] + ([subdir] if subdir else []),
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            rows.append({"ref": ref, "error": "ls_tree_failed"})
            continue
        tree = {}
        for line in r.stdout.splitlines():
            meta, _, path = line.partition("\t")
            sha = meta.split()[2]
            rel = os.path.relpath(path, subdir) if subdir else path
            if rel.endswith(exts):
                tree[rel] = sha
        files = fp["files"]
        same = sum(1 for k, v in files.items() if tree.get(k) == v)
        diff = sorted(k for k, v in files.items() if k in tree and tree[k] != v)
        only_dep = sorted(k for k in files if k not in tree)
        only_commit = sorted(k for k in tree if k not in files)
        head = subprocess.run(["git", "-C", repo, "rev-parse", ref], capture_output=True, text=True).stdout.strip()
        rows.append({"ref": ref, "commit": head, "identical": same, "different": len(diff),
                     "only_in_deploy": len(only_dep), "only_in_commit": len(only_commit),
                     "exact_match": not diff and not only_dep and not only_commit and same > 0,
                     "different_sample": diff[:10], "only_in_deploy_sample": only_dep[:10]})
    rows.sort(key=lambda r: (-r.get("identical", -1), r.get("different", 0), r.get("only_in_deploy", 0)))
    return rows


# ------------------------------------------------------------------ CLI

def completeness(rep: dict) -> dict:
    """Distingue i FALLIMENTI (dati mancanti per la mappatura) dalle assenze legittime (nessuna unita' superbot-*)."""
    problems, notes = [], []
    if not isinstance(rep["processes"], list):
        problems.append("ps_unavailable")
    sd = rep["systemd"]
    if not sd["readable"]:
        problems.append("systemd_unavailable")
    else:
        if not sd["units"]:
            notes.append("no_matching_units")
        problems += [f"unit_show_failed:{u['unit']}" for u in sd["units"] if u.get("error")]
    return {"complete": not problems, "problems": problems, "notes": notes}


def run_discovery(paths: list, run: Runner = real_runner) -> dict:
    rc, ps = run(["ps", "-eo", "pid=,ppid=,user=,etimes=,args="])
    me = run(["id", "-u"])[1].strip()
    rep = {"schema": 1, "classification": "PRIVATE_DO_NOT_COMMIT", "euid": me,
           "processes": parse_ps(ps) if rc == 0 else {"readable": False},
           "systemd": discover_services(run),
           "containers": {"readable": False, "note": "docker non accessibile senza privilegi: non verificato"},
           "paths": [path_meta(p) for p in paths]}
    rep["completeness"] = completeness(rep)
    return rep


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("services", help="processi, unita' systemd e metadati dei percorsi")
    d.add_argument("--spec", help="spec JSON (snapshot.py) da cui prendere i percorsi")
    d.add_argument("--path", action="append", default=[])
    d.add_argument("--report", required=True)
    c = sub.add_parser("codefp", help="confronta una directory di codice con i commit di un clone")
    c.add_argument("--code-dir", required=True)
    c.add_argument("--repo", required=True, help="clone di laboratorio (con i rami gia' scaricati)")
    c.add_argument("--ref", action="append", required=True)
    c.add_argument("--subdir", default="", help="sottocartella del repo che corrisponde alla code-dir")
    c.add_argument("--report", required=True)
    a = ap.parse_args(argv)
    if os.path.lexists(a.report) or inv.inside_git_worktree(a.report):
        print("NO-GO: output esistente o dentro un working tree git")
        return 1
    if a.cmd == "services":
        paths = list(a.path)
        if a.spec:
            with open(a.spec, encoding="utf-8") as fh:
                paths += [s["path"] for s in json.load(fh)["sources"]]
        rep = run_discovery(paths, real_runner)
        cmp_ = rep["completeness"]
        msg = (f"{'GO' if cmp_['complete'] else 'NO-GO (INCOMPLETO: ' + ', '.join(cmp_['problems']) + ')'}: processi={len(rep['processes']) if isinstance(rep['processes'], list) else 'n/d'} "
               f"unita={len(rep['systemd']['units'])} percorsi={len(rep['paths'])} "
               f"non_leggibili={sum(1 for p in rep['paths'] if p['status'] != 'ok')}"
               + (f" note={','.join(cmp_['notes'])}" if cmp_["notes"] else ""))
        rc_out = 0 if cmp_["complete"] else 1
    else:
        fp = fingerprint_dir(a.code_dir)
        rep = {"schema": 1, "classification": "PRIVATE_DO_NOT_COMMIT", "files_fingerprinted": len(fp["files"]),
               "skipped": fp["skipped"], "matches": match_commits(fp, a.repo, a.ref, a.subdir)}
        best = rep["matches"][0] if rep["matches"] else {}
        bad = [] if fp["files"] else ["no_files_fingerprinted"]
        bad += [f"{m['ref']}:{m['error']}" for m in rep["matches"] if "error" in m]
        rep["completeness"] = {"complete": not bad, "problems": bad}
        rc_out = 0 if not bad else 1
        msg = (f"{'GO' if not bad else 'NO-GO (INCOMPLETO: ' + ', '.join(bad) + ')'}: file={len(fp['files'])} "
               f"migliore={best.get('ref')} esatto={best.get('exact_match')}")
    fd = os.open(a.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1, sort_keys=True)
    print(msg)
    return rc_out


if __name__ == "__main__":
    sys.exit(main())
