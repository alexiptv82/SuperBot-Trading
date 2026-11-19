"""Runner PRIVILEGIATO della Fase 0 (opzione B): eseguito UNA volta dall'operatore, da un bundle sigillato.

Principi (ognuno e' un controllo automatico con test sintetici):
1. Codice solo da bundle revisionato e fissato per hash: il file deve coincidere con --expect-sha256 e vivere in
   una directory di root (nessun antenato scrivibile da altri, nessun symlink); mai codice da cartelle
   modificabili dall'agente.
2. Nessun input dell'agente: la spec delle fonti e' INCORPORATA nel bundle (coperta dall'hash); i percorsi devono
   stare sotto /opt e ogni antenato deve essere di root e non scrivibile da altri (altrimenti un symlink/rinomina
   potrebbe far leggere a root file diversi da quelli revisionati).
3. Preflight prima di ogni copia: spazio, tetto di dimensione, leggibilita', gruppi obbligatori con FILE DI DATI
   (non solo codice), stato dei DB WAL, quiescenza verificata a RUNTIME (unita' inattive + nessun processo con il
   DB aperto), non la fiducia in una stringa.
4. Nessun servizio fermato o riavviato: si leggono stati con `systemctl list-units|show` (nient'altro), prima e
   dopo, e si dichiara se sono cambiati. Priorita' di CPU abbassata; lettura a passi brevi, abbandono se occupato.
5. Dati originali e copie PRIVATI: tutto cio' che contiene dati sta in `private/` (0700, root). L'agente puo'
   leggere solo `public/`: numeri, codici e hash, mai percorsi, ID o contenuti.
6. Ripristino provato: restore su directory vuota + audit di quadratura; la copia di ripristino viene poi rimossa.
7. Nessuna copia esterna qui: fase successiva, con cifratura (vedi runbook). `certifies_backup` e' SEMPRE false.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
from typing import Any, Callable, Optional

import audit
import inventory as inv
import risk_audit
import snapshot as snap

SCHEMA = 1
BASE_DIR = "/var/lib/superbot-phase0"
ALLOWED_SRC_ROOT = "/opt"
UNIT_RE = re.compile(r"superbot-[A-Za-z0-9@:._-]{1,100}\.service")
STATE_PROPS = ("ActiveState", "SubState", "MainPID", "NRestarts")
ACTIVE_STATES = frozenset({"active", "activating", "reloading", "deactivating", "refreshing"})
MAX_TOTAL_GB = 10
PROVIDERS = ("deepseek", "qwen", "minimax")
RUNNER_UNIT_RE = re.compile(r"superbot-arena-runner@(deepseek|qwen|minimax)\.service")
TOKEN_RE = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
Runner = Callable[[list], tuple]


# --------------------------------------------------------------------------- fiducia nel codice e nei percorsi

def chain_problems(path: str, uid: int, include_leaf: bool = False, anchor: str = "/") -> list:
    """Antenati di `path` (e opzionalmente la foglia): directory vere, del proprietario atteso, non scrivibili da
    gruppo/altri. `anchor`: primo componente controllato (in produzione "/": TUTTA la catena; i test usano la
    propria radice temporanea). Ritorna l'elenco dei problemi (vuoto = fidato)."""
    p = os.path.abspath(path)
    parts = [x for x in p.split(os.sep) if x]
    probs = []
    chain = [os.sep] + [os.path.join(os.sep, *parts[:i + 1]) for i in range(len(parts) - (0 if include_leaf else 1))]
    if anchor != os.sep:
        a = os.path.abspath(anchor)
        if not (p == a or p.startswith(a + os.sep)):
            return ["outside_anchor"]
        chain = [c for c in chain if c == a or c.startswith(a + os.sep)]
    for c in chain:
        try:
            st = os.lstat(c)
        except OSError:
            probs.append("component_missing")
            break
        if stat.S_ISLNK(st.st_mode):
            probs.append("symlink_in_chain")
        elif not stat.S_ISDIR(st.st_mode) and c != p:
            probs.append("component_not_dir")
        if st.st_uid != uid:
            probs.append("component_not_owned_by_trusted_uid")
        if st.st_mode & 0o022:
            probs.append("component_writable_by_others")
    return sorted(set(probs))


def check_code_trust(path: str, data: bytes, expect_sha: str, uid: int = 0, anchor: str = "/") -> list:
    probs = []
    if hashlib.sha256(data).hexdigest() != (expect_sha or "").lower():
        probs.append("sha256_mismatch")
    try:
        st = os.lstat(path)
    except OSError:
        return probs + ["code_file_missing"]
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        probs.append("code_not_regular_file")
    if st.st_uid != uid:
        probs.append("code_not_owned_by_trusted_uid")
    if st.st_mode & 0o022:
        probs.append("code_writable_by_others")
    return sorted(set(probs + chain_problems(path, uid, anchor=anchor)))


# --------------------------------------------------------------------------- servizi (sola lettura)

def default_runner(argv: list) -> tuple:
    """Unici comandi ammessi: systemctl list-units / show. Mai start/stop/restart, mai shell."""
    if len(argv) < 2 or argv[0] != "systemctl" or argv[1] not in ("list-units", "show"):
        raise ValueError("command_not_allowed")
    exe = next((p for p in ("/usr/bin/systemctl", "/bin/systemctl") if os.path.exists(p)), None)
    if exe is None:
        return 127, ""
    try:
        r = subprocess.run([exe] + argv[1:], capture_output=True, text=True, timeout=30,
                           env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return r.returncode, r.stdout


def default_stopper(argv: list) -> tuple:
    """UNICO comando di scrittura ammesso nel bundle: `systemctl stop` di uno dei TRE runner dell'Arena (mai le
    uscite, mai il close-bridge, mai altre unita'). Il runner gestisce SIGTERM in modo ordinato."""
    if len(argv) != 3 or argv[0] != "systemctl" or argv[1] != "stop" or not RUNNER_UNIT_RE.fullmatch(argv[2]):
        raise ValueError("command_not_allowed")
    exe = next((p for p in ("/usr/bin/systemctl", "/bin/systemctl") if os.path.exists(p)), None)
    if exe is None:
        return 127, ""
    try:
        r = subprocess.run([exe, "stop", argv[2]], capture_output=True, text=True, timeout=300,
                           env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return r.returncode, r.stdout


def unit_states(run: Runner) -> Optional[dict]:
    rc, out = run(["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--plain", "--no-pager"])
    if rc != 0:
        return None
    names = sorted({t for line in out.splitlines() for t in line.split()[:1] if UNIT_RE.fullmatch(t)})
    states = {}
    for n in names:
        rc2, o2 = run(["systemctl", "show", n, "--no-pager"] + [x for p in STATE_PROPS for x in ("-p", p)])
        d = {}
        for line in o2.splitlines():
            k, eq, v = line.partition("=")
            if eq and k in STATE_PROPS:
                d[k] = v
        states[n] = d if rc2 == 0 else {"error": "show_failed"}
    return states


def compare_states(before: Optional[dict], after: Optional[dict]) -> dict:
    if before is None or after is None:
        return {"comparable": False, "unchanged": None, "changed_units": []}
    changed = sorted(u for u in set(before) | set(after) if before.get(u) != after.get(u))
    return {"comparable": True, "unchanged": not changed, "changed_units": changed, "units": len(before)}


def open_paths(proc_root: str = "/proc") -> set:
    """Percorsi aperti da QUALUNQUE processo (richiede root). Nessun contenuto, solo i link in /proc/*/fd."""
    out = set()
    try:
        pids = [d for d in os.listdir(proc_root) if d.isdigit()]
    except OSError:
        return out
    for pid in pids:
        fd_dir = os.path.join(proc_root, pid, "fd")
        try:
            for fd in os.listdir(fd_dir):
                try:
                    t = os.readlink(os.path.join(fd_dir, fd))
                except OSError:
                    continue
                if t.startswith("/"):
                    out.add(t.removesuffix(" (deleted)"))
        except OSError:
            continue
    return out


def verify_quiescence(src: str, q: Optional[dict], states: Optional[dict], opened: set) -> tuple:
    """(ok, dettaglio). Quiescente = unita' dichiarate NON attive (se systemctl non risponde: non provato) E nessun
    processo ha aperto un DB (o i suoi -wal/-shm/-journal) sotto `src`."""
    if not q or not isinstance(q.get("units"), list):
        return False, "no_quiescence_declared"
    if states is None:
        return False, "systemd_unavailable"
    for u in q["units"]:
        if not UNIT_RE.fullmatch(u):
            return False, "bad_unit_name"
        if states.get(u, {}).get("ActiveState") in ACTIVE_STATES:
            return False, "unit_active"
    base = os.path.abspath(src)
    for p in opened:
        if (p == base or p.startswith(base + os.sep)) and p.lower().endswith(inv.DB_EXT + inv.DB_SIDE):
            return False, "db_open_by_process"
    return True, "units_inactive_and_no_open_db_fds"


# --------------------------------------------------------------------------- esecuzione

def _write_json_new(path: str, obj: Any, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True)
    os.chmod(path, mode)                                   # file NUOVO: mode esplicito a prescindere dalla umask


def _mkdir_new(path: str, mode: int) -> None:
    os.mkdir(path)
    os.chmod(path, mode)                                   # directory NUOVA creata da noi


def _codes(items: list) -> list:
    return sorted({x["code"] for x in items})


def _new_run(base: str, trusted_uid: int, chain_anchor: str, now: Callable[[], float], code_sha: str) -> tuple:
    """Directory base fidata + nuova directory di esecuzione (public 0755 / private 0700). Errori: (1, {...})."""
    bp = os.path.abspath(base)
    if not os.path.lexists(bp):
        if chain_problems(bp, trusted_uid, anchor=chain_anchor):
            return 1, {"verdict": "NO-GO", "reason": "base_parent_not_trusted"}
        _mkdir_new(bp, 0o755)
    bst = os.lstat(bp)
    if (stat.S_ISLNK(bst.st_mode) or not stat.S_ISDIR(bst.st_mode) or bst.st_uid != trusted_uid
            or bst.st_mode & 0o022 or chain_problems(bp, trusted_uid, anchor=chain_anchor)):
        return 1, {"verdict": "NO-GO", "reason": "base_dir_not_trusted"}
    t0 = now()
    run_id = time.strftime("run-%Y%m%dT%H%M%SZ", time.gmtime(t0)) + "-" + (code_sha[:8] or "nohash")
    run_dir = os.path.join(bp, run_id)
    _mkdir_new(run_dir, 0o755)
    pub, priv = os.path.join(run_dir, "public"), os.path.join(run_dir, "private")
    _mkdir_new(pub, 0o755)
    _mkdir_new(priv, 0o700)
    _mkdir_new(os.path.join(priv, "reports"), 0o700)
    return run_id, run_dir, pub, priv, os.path.join(priv, "snapshot"), os.path.join(priv, "restore"), t0


def execute(spec: dict, mode: str, *, base: str = BASE_DIR, allowed_root: str = ALLOWED_SRC_ROOT, trusted_uid: int = 0,
            chain_anchor: str = "/", runner: Runner = default_runner, proc_root: str = "/proc", auth_ref: Optional[str] = None,
            code_sha: str = "", space_factor: float = 2.0, reserve_mb: int = 512, max_total_gb: float = MAX_TOTAL_GB,
            keep_restore: bool = False, groups: Optional[list] = None, ended_early_reason: Optional[str] = None,
            sleep: Callable[[float], None] = time.sleep, now: Callable[[], float] = time.time,
            out: Callable[[str], None] = print) -> tuple:
    if mode not in ("preflight", "full"):
        raise ValueError("bad_mode")
    if groups is not None:
        unknown = sorted(set(groups) - set(spec["required_groups"]))
        if unknown or not groups:
            raise ValueError("unknown_group")
        spec = {**spec, "required_groups": [g for g in spec["required_groups"] if g in groups],
                "sources": [s for s in spec["sources"] if s["group"] in groups]}
    nr = _new_run(base, trusted_uid, chain_anchor, now, code_sha)
    if isinstance(nr[0], int):
        return nr
    run_id, run_dir, pub, priv, snapdir, restdir, t0 = nr

    summary: dict[str, Any] = {"schema": SCHEMA, "run_id": run_id, "mode": mode, "code_sha256": code_sha,
                               "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
                               "certifies_backup": False, "groups": sorted(groups) if groups else "all",
                               "certification_blockers": ["same_host_copy", "capture_not_atomic_across_sources",
                                                          "external_encrypted_copy_not_done"]}

    def finish(verdict: str, code: int) -> tuple:
        summary["verdict"] = verdict
        _write_json_new(os.path.join(pub, "summary.json"), summary, 0o644)
        out(f"{verdict}: vedi {os.path.join(pub, 'summary.json')}")
        return code, summary

    # ---- stato iniziale dei servizi (sola lettura) e file aperti
    before = unit_states(runner)
    opened = open_paths(proc_root)

    # ---- spec incorporata -> spec risolta (evidenza di quiescenza VERIFICATA a runtime)
    pre_nogo: list[dict] = []
    issues: list[dict] = []                      # gruppo + motivo (mai percorsi) per capire subito cosa correggere
    resolved = []
    for s in spec["sources"]:
        sid, path = s["id"], s["path"]
        q = s.get("quiescence")
        item = {k: v for k, v in s.items() if k != "quiescence"}
        real_exists = os.path.lexists(path)
        if not (os.path.abspath(path) + os.sep).startswith(os.path.abspath(allowed_root).rstrip(os.sep) + os.sep):
            pre_nogo.append({"code": "source_outside_allowed_root", "id": sid})
            issues.append({"group": s["group"], "problems": ["outside_allowed_root"]})
        elif real_exists:
            probs = chain_problems(path, trusted_uid, anchor=chain_anchor)
            if probs:
                pre_nogo.append({"code": "source_path_not_root_controlled", "id": sid, "detail": probs})
                issues.append({"group": s["group"], "problems": probs})
        if q is not None:
            ok, detail = verify_quiescence(path, q, before, opened)
            if ok:
                item["quiescence_evidence"] = f"runtime:{detail}:t={int(t0)}"
            else:
                summary.setdefault("quiescence_not_proven", []).append({"id_hash": hashlib.sha256(sid.encode()).hexdigest()[:8],
                                                                         "why": detail})
        resolved.append(item)
    spec_path = os.path.join(priv, "spec.resolved.json")
    _write_json_new(spec_path, {"schema": 1, "required_groups": spec["required_groups"], "sources": resolved}, 0o600)

    maxb = int(max_total_gb * 1024 ** 3)
    kw = dict(space_factor=space_factor, reserve_mb=reserve_mb, sleep=sleep, require_data=spec.get("require_data", True),
              max_total_bytes=maxb)
    try:
        pf_code, pf = snap.run_snapshot(spec_path, snapdir, "preflight", True, **kw)
    except (ValueError, OSError) as exc:
        summary["preflight"] = {"go": False, "nogo_codes": ["spec_or_path_invalid:" + type(exc).__name__]}
        return finish("NO-GO", 1)
    pfs = pf["preflight"]
    nogo = list(pfs["nogo"]) + pre_nogo
    summary["preflight"] = {"go": not nogo, "nogo_codes": _codes(nogo), "warn_codes": _codes(pfs["warn"]),
                            "items": pfs["items"], "total_source_bytes": pfs["total_source_bytes"],
                            "free_bytes": pfs["free_bytes"], "bytes_by_group": pfs.get("bytes_by_group", {}),
                            "excluded": pfs["skipped"], "max_total_bytes": maxb}
    after = unit_states(runner)
    summary["services"] = compare_states(before, after)
    summary["source_issues"] = sorted(issues, key=lambda x: (x["group"], x["problems"]))
    if nogo:
        return finish("NO-GO", 1)
    if mode == "preflight":
        return finish("PREFLIGHT_GO", 0)
    if not auth_ref or not auth_ref.strip():
        summary["preflight"]["nogo_codes"].append("missing_authorization_reference")
        return finish("NO-GO", 1)

    # ---- snapshot reale (copie coerenti per file, in private/)
    code, rep = snap.run_snapshot(spec_path, snapdir, auth_ref, False, **kw)
    items = rep.get("items", [])
    summary["snapshot"] = {"complete": bool(rep.get("complete")), "items": len(items),
                           "items_ok": sum(1 for i in items if i["status"] == "OK"),
                           "failed_reasons": sorted({i.get("reason", "?") for i in items if i["status"] != "OK"}),
                           "retried_items": sum(1 for i in items if i.get("attempts", 1) > 1),
                           "partial_tail_items": sum(1 for i in items if i.get("partial_tail_bytes")),
                           "window_seconds": rep.get("window_seconds"), "consistency": rep.get("consistency")}
    if code != 0:
        summary["services"] = compare_states(before, unit_states(runner))
        return finish("NO-GO", 1)

    # ---- manifest SHA256 sulla copia (privato) + riepilogo numerico (pubblico)
    ns = argparse.Namespace(include_db=True, sqlite=True, include_ids=False, git_repo=None)
    manifest = inv.build([("snapshot", snapdir)], ns)
    _write_json_new(os.path.join(priv, "reports", "manifest.json"), manifest, 0o600)
    msum = inv.summary_of(manifest)
    _write_json_new(os.path.join(pub, "manifest_summary.json"), msum, 0o644)
    summary["manifest"] = {k: msum[k] for k in ("complete", "files_hashed", "unstable_count", "manifest_digest")}

    # ---- ripristino su directory vuota + audit
    res = audit.restore(snapdir, restdir)
    rep_a = audit.audit(restdir, res["log"], None)
    for e in res["restore_errors"]:
        rep_a["fails"].append({"code": "restore_copy_failed", **e})
    if res["restore_errors"]:
        rep_a["verdict"] = "FAIL"
    _write_json_new(os.path.join(priv, "reports", "audit.json"), rep_a, 0o600)
    asum = audit.summary_of(rep_a)
    _write_json_new(os.path.join(pub, "audit_summary.json"), asum, 0o644)
    chains = rep_a["checks"]["v3_chains"]
    anchors = {k: {"count": v["count"], "head": v["head"]} for k, v in chains.items()}
    _write_json_new(os.path.join(priv, "reports", "anchors.json"), anchors, 0o600)
    digest = hashlib.sha256(json.dumps(sorted((k, v["count"], v["head"]) for k, v in anchors.items()),
                                       separators=(",", ":")).encode()).hexdigest()
    summary["audit"] = {"verdict": asum["verdict"], "fail_codes": asum["fail_codes"],
                        "warning_codes": asum["warning_codes"], "v3_chains_ok": asum["v3_chains_ok"],
                        "v3_chains_total": asum["v3_chains_total"], "anchors_digest": digest}
    summary["certification_blockers"] = asum["certification_blockers"] + [
        b for b in summary["certification_blockers"] if b not in asum["certification_blockers"]]
    pol = spec.get("arena_risk_policy")
    if pol:
        risk, window = {}, {}
        for src in spec["sources"]:
            if not src["id"].startswith("arena_"):
                continue
            prov = src["id"][len("arena_"):]
            dbs, t0s = [], []
            for d, _, fn in os.walk(os.path.join(restdir, src["id"])):
                dbs += [os.path.join(d, n) for n in sorted(fn) if n == "journal.db"]
                t0s += [os.path.join(d, n) for n in fn if n == "arena_t0.json"]
            try:
                reps = [risk_audit.analyze(risk_audit.read_events(p), pol, pol.get("exit_max_hold_hours", 24)) for p in sorted(dbs)]
                risk[prov] = reps[0] if len(reps) == 1 else reps
                t0_ms = None
                for tp in t0s[:1]:
                    with open(tp, encoding="utf-8") as fh:
                        t0_ms = json.load(fh).get("trial_start_ms")
                last = max((r["window"]["last_event_ms"] or 0) for r in reps) if reps else None
                if isinstance(t0_ms, int) and last:
                    hrs = round((last - t0_ms) / 3_600_000, 2)
                    window[prov] = {"t0_ms": t0_ms, "last_event_ms": last, "effective_hours": hrs,
                                    "planned_hours": spec.get("arena_planned_hours", 72)}
            except (sqlite3.Error, OSError, ValueError, KeyError) as exc:
                risk[prov] = "error:" + type(exc).__name__
        summary["risk"], summary["arena_window"] = risk, window
        if ended_early_reason:
            summary["ended_early_reason"] = ended_early_reason
    if not keep_restore:
        shutil.rmtree(restdir)                              # la copia di ripristino e' solo una prova: si rimuove
    summary["services"] = compare_states(before, unit_states(runner))
    if rep_a["verdict"] == "FAIL" or not manifest["complete"]:
        return finish("NO-GO", 1)
    return finish("SNAPSHOT_GO", 0)


# --------------------------------------------------------------------------- status e arresto ordinato delle aperture

def _arena_units(provider: str) -> tuple:
    return f"superbot-arena-runner@{provider}.service", f"superbot-arena-exit@{provider}.service"


def _live_positions(spec: dict, provider: str, allowed_root: str, trusted_uid: int, chain_anchor: str) -> dict:
    """Posizioni aperte di un journal VIVO, in sola lettura e SENZA effetti sulla sorgente: si legge solo se il DB non e'
    in WAL, o e' in WAL con -shm gia' presente; un WAL fermo (senza sidecar) non si apre (creerebbe file)."""
    src = next((x for x in spec["sources"] if x["id"] == f"arena_{provider}"), None)
    if src is None:
        return {"status": "no_source"}
    if not (os.path.abspath(src["path"]) + os.sep).startswith(os.path.abspath(allowed_root).rstrip(os.sep) + os.sep):
        return {"status": "outside_allowed_root"}
    if chain_problems(src["path"], trusted_uid, anchor=chain_anchor):
        return {"status": "path_not_root_controlled"}
    dbs = [os.path.join(d, n) for d, _, fn in os.walk(src["path"], followlinks=False) for n in sorted(fn) if n == "journal.db"]
    if not dbs:
        return {"status": "journal_not_found"}
    out = []
    for p in dbs:
        method = snap.sqlite_method(snap.probe_sqlite(p))
        if method != "backup":
            out.append({"status": "skipped:" + method.replace("nogo:", "")})
            continue
        try:
            out.append({"status": "ok", **risk_audit.open_positions_status(p)})
        except (sqlite3.Error, OSError):
            out.append({"status": "unreadable"})
    return out[0] if len(out) == 1 else {"status": "multiple", "journals": out}


def execute_status(spec: dict, *, base: str = BASE_DIR, allowed_root: str = ALLOWED_SRC_ROOT, trusted_uid: int = 0,
                   chain_anchor: str = "/", runner: Runner = default_runner, code_sha: str = "",
                   now: Callable[[], float] = time.time, out: Callable[[str], None] = print) -> tuple:
    """SOLA LETTURA: stato delle unita' Arena e posizioni aperte per provider. Nessun lock persistente, nessuna copia."""
    nr = _new_run(base, trusted_uid, chain_anchor, now, code_sha)
    if isinstance(nr[0], int):
        return nr
    run_id, run_dir, pub, priv, _snap, _rest, t0 = nr
    states = unit_states(runner)
    summary: dict[str, Any] = {"schema": SCHEMA, "run_id": run_id, "mode": "status", "code_sha256": code_sha,
                               "at_ms": int(t0 * 1000), "certifies_backup": False}
    prov = {}
    for p in PROVIDERS:
        ru, eu = _arena_units(p)
        prov[p] = {"runner": (states or {}).get(ru, {}).get("ActiveState", "unknown"),
                   "exit": (states or {}).get(eu, {}).get("ActiveState", "unknown"),
                   "positions": _live_positions(spec, p, allowed_root, trusted_uid, chain_anchor)}
    summary["providers"] = prov
    summary["systemd_readable"] = states is not None
    _write_json_new(os.path.join(pub, "summary.json"), summary, 0o644)
    summary["verdict"] = "STATUS"
    out(f"STATUS: vedi {os.path.join(pub, 'summary.json')}")
    return 0, summary


def execute_stop(spec: dict, *, providers: Optional[list] = None, ended_early_reason: str, auth_ref: str,
                 base: str = BASE_DIR, allowed_root: str = ALLOWED_SRC_ROOT, trusted_uid: int = 0,
                 chain_anchor: str = "/", runner: Runner = default_runner, stopper: Callable[[list], tuple] = default_stopper,
                 code_sha: str = "", now: Callable[[], float] = time.time, out: Callable[[str], None] = print) -> tuple:
    """Blocca le NUOVE aperture fermando SOLO i runner Arena selezionati (SIGTERM ordinato). Le uscite (exit service) restano
    attive e chiudono le posizioni con le regole normali (stop, take-profit, durata massima): nessuna chiusura manuale.
    Idempotente. Si rifiuta di fermare qualsiasi cosa se un exit service selezionato non e' attivo (posizioni orfane)."""
    sel = list(PROVIDERS) if providers is None else list(providers)     # [] NON significa "tutti"
    if not sel or any(p not in PROVIDERS for p in sel) or len(set(sel)) != len(sel):
        raise ValueError("bad_providers")
    if not TOKEN_RE.fullmatch(ended_early_reason or "") or not (auth_ref or "").strip():
        raise ValueError("bad_reason_or_auth_ref")
    nr = _new_run(base, trusted_uid, chain_anchor, now, code_sha)
    if isinstance(nr[0], int):
        return nr
    run_id, run_dir, pub, priv, _snap, _rest, t0 = nr
    summary: dict[str, Any] = {"schema": SCHEMA, "run_id": run_id, "mode": "stop-openings", "code_sha256": code_sha,
                               "providers": sel, "ended_early_reason": ended_early_reason, "at_ms": int(t0 * 1000),
                               "certifies_backup": False}

    def finish(verdict: str, code: int) -> tuple:
        summary["verdict"] = verdict
        _write_json_new(os.path.join(pub, "summary.json"), summary, 0o644)
        out(f"{verdict}: vedi {os.path.join(pub, 'summary.json')}")
        return code, summary

    before = unit_states(runner)
    if before is None:
        summary["nogo"] = ["systemd_unavailable"]
        return finish("NO-GO", 1)
    nogo = []
    for p in sel:
        ru, eu = _arena_units(p)
        if ru not in before:
            nogo.append(f"runner_unit_not_found:{p}")
        if before.get(eu, {}).get("ActiveState") != "active":
            nogo.append(f"exit_service_not_active:{p}")               # fermare il runner lascerebbe posizioni senza uscite
    summary["positions_before"] = {p: _live_positions(spec, p, allowed_root, trusted_uid, chain_anchor) for p in sel}
    if nogo:
        summary["nogo"] = nogo
        summary["services_before"] = {u: before[u] for u in before if u.startswith("superbot-arena-")}
        return finish("NO-GO", 1)
    stopped, already, failed = [], [], []
    for p in sel:
        ru, _eu = _arena_units(p)
        if before[ru].get("ActiveState") not in ACTIVE_STATES:
            already.append(p)
            continue
        rc, _o = stopper(["systemctl", "stop", ru])
        (stopped if rc == 0 else failed).append(p)
    after = unit_states(runner) or {}
    still_active = [p for p in sel if after.get(_arena_units(p)[0], {}).get("ActiveState") in ACTIVE_STATES]
    exits_ok = all(after.get(_arena_units(p)[1], {}).get("ActiveState") == "active"
                   and after[_arena_units(p)[1]].get("MainPID") == before[_arena_units(p)[1]].get("MainPID")
                   and after[_arena_units(p)[1]].get("NRestarts") == before[_arena_units(p)[1]].get("NRestarts") for p in sel)
    summary.update({"stopped": stopped, "already_stopped": already, "stop_failed": failed,
                    "runners_still_active": still_active, "exit_services_untouched": exits_ok,
                    "services_before": {u: before[u] for u in before if u.startswith("superbot-arena-")},
                    "services_after": {u: after[u] for u in after if u.startswith("superbot-arena-")},
                    "positions_after": {p: _live_positions(spec, p, allowed_root, trusted_uid, chain_anchor) for p in sel},
                    "next": "attendere la chiusura naturale delle posizioni (max 24h) poi eseguire 'full' per lo snapshot definitivo"})
    ok = not failed and not still_active and exits_ok
    return finish("OPENINGS_STOPPED" if ok else "NO-GO", 0 if ok else 1)


# --------------------------------------------------------------------------- CLI

def main(argv: list, *, data: bytes, spec: dict, code_path: str, module_hashes: Optional[dict] = None) -> int:
    ap = argparse.ArgumentParser(prog="phase0_sealed.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest", help="nessun privilegio, nessun dato: versioni e hash dei moduli incorporati")

    def common(p, auth_required: bool):
        p.add_argument("--expect-sha256", required=True, help="hash atteso di QUESTO file (dal messaggio dell'operatore)")
        if auth_required:
            p.add_argument("--auth-ref", required=True)
    for name, hlp in (("preflight", "SOLA LETTURA di metadati: nessuna copia"),
                      ("full", "preflight + snapshot + manifest + ripristino + audit + limiti di rischio")):
        p = sub.add_parser(name, help=hlp)
        common(p, name == "full")
        p.add_argument("--max-total-gb", type=float, default=MAX_TOTAL_GB)
        p.add_argument("--keep-restore", action="store_true")
        p.add_argument("--groups", help="sottoinsieme di gruppi separati da virgola (es. arena_minimax)")
        p.add_argument("--ended-early-reason", help="motivo (token) se l'Arena e' conclusa prima delle 72h")
    common(sub.add_parser("status", help="SOLA LETTURA: unita' Arena e posizioni aperte"), False)
    p = sub.add_parser("stop-openings", help="ferma SOLO i runner Arena selezionati (le uscite restano attive)")
    common(p, True)
    p.add_argument("--ended-early-reason", required=True)
    p.add_argument("--providers", help="es. minimax oppure deepseek,qwen,minimax (default: tutti e tre)")
    p.add_argument("--confirm-stop-runners", action="store_true", required=True)
    a = ap.parse_args(argv)
    sha = hashlib.sha256(data).hexdigest()
    if a.cmd == "selftest":
        ok = sys.version_info >= (3, 8) and hasattr(sqlite3.Connection, "backup")
        print(json.dumps({"bundle_sha256": sha, "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
                          "backup_api": hasattr(sqlite3.Connection, "backup"), "modules": module_hashes or {},
                          "sources": len(spec["sources"]), "required_groups": spec["required_groups"],
                          "euid": os.geteuid()}, indent=1, sort_keys=True))
        return 0 if ok else 1
    if os.geteuid() != 0:
        print("NO-GO: richiede root (opzione B: esecuzione dell'operatore); nessuna azione eseguita")
        return 2
    probs = check_code_trust(code_path, data, a.expect_sha256, 0)
    if probs:
        print("NO-GO: codice non fidato (" + ", ".join(probs) + "); nessuna azione eseguita")
        return 2
    try:
        os.nice(19)
    except OSError:
        pass
    if a.cmd == "status":
        return execute_status(spec, code_sha=sha)[0]
    if a.cmd == "stop-openings":
        try:
            return execute_stop(spec, providers=a.providers.split(",") if a.providers else None,
                                ended_early_reason=a.ended_early_reason, auth_ref=a.auth_ref, code_sha=sha)[0]
        except ValueError as exc:
            print(f"NO-GO: argomenti non validi ({exc}); nessuna azione eseguita")
            return 2
    reason = getattr(a, "ended_early_reason", None)
    if reason is not None and not TOKEN_RE.fullmatch(reason):
        print("NO-GO: --ended-early-reason deve essere un token [A-Za-z0-9_.:-]{1,64}")
        return 2
    try:
        code, _ = execute(spec, a.cmd, auth_ref=getattr(a, "auth_ref", None), code_sha=sha, max_total_gb=a.max_total_gb,
                          keep_restore=a.keep_restore, groups=a.groups.split(",") if a.groups else None,
                          ended_early_reason=reason)
    except ValueError as exc:
        print(f"NO-GO: argomenti non validi ({exc}); nessuna azione eseguita")
        return 2
    return code
