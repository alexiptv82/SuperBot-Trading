#!/usr/bin/env python3
"""Fase 0 — orchestratore a passi: un comando per passo, un solo verdetto GO / NO-GO per riga.

    python3 phase0.py --work DIR step1-discover  --spec SPEC [--code-dir D --repo R --ref REF]
    python3 phase0.py --work DIR step2-preflight --spec SPEC
    python3 phase0.py --work DIR step3-snapshot  --spec SPEC --auth-ref RIF
    python3 phase0.py --work DIR step4-manifest
    python3 phase0.py --work DIR step5-restore-audit [--expect-v3 FILE]
    python3 phase0.py --work DIR status

DIR e' una directory di lavoro NUOVA o gia' di Fase 0, fuori da qualunque repository git:
  DIR/reports/   report PRIVATI (0600) + riepiloghi numerici condivisibili (*_summary.json)
  DIR/snapshot/  copie coerenti per file (0400) + snapshot_log.json
  DIR/restore/   ripristino su directory vuota
I passi 1-3 leggono le sorgenti reali e richiedono ciascuno una autorizzazione esplicita (--auth-ref e'
obbligatorio solo per lo snapshot, ma ogni passo reale va comunque lanciato solo dopo il consenso). I passi 4-5
lavorano esclusivamente sulle COPIE. Nessun passo scrive sulle sorgenti o tocca servizi.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import audit  # noqa: E402
import discover  # noqa: E402
import inventory as inv  # noqa: E402
import snapshot as snap  # noqa: E402


def paths(work: str) -> dict:
    return {"reports": os.path.join(work, "reports"), "snapshot": os.path.join(work, "snapshot"),
            "restore": os.path.join(work, "restore")}


def prepare(work: str) -> Optional[str]:
    work = os.path.abspath(work)
    if snap.inside_git(work):
        return "NO-GO: la directory di lavoro non puo' stare in un working tree git"
    os.makedirs(paths(work)["reports"], mode=0o700, exist_ok=True)
    os.chmod(work, 0o700)
    return None


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", required=True)
    sub = ap.add_subparsers(dest="step", required=True)
    s1 = sub.add_parser("step1-discover")
    s1.add_argument("--spec")
    s1.add_argument("--code-dir")
    s1.add_argument("--repo")
    s1.add_argument("--ref", action="append")
    s1.add_argument("--subdir", default="")
    s2 = sub.add_parser("step2-preflight")
    s2.add_argument("--spec", required=True)
    s3 = sub.add_parser("step3-snapshot")
    s3.add_argument("--spec", required=True)
    s3.add_argument("--auth-ref", required=True)
    sub.add_parser("step4-manifest")
    s5 = sub.add_parser("step5-restore-audit")
    s5.add_argument("--expect-v3")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    err = prepare(a.work)
    if err:
        print(err)
        return 1
    P = paths(os.path.abspath(a.work))
    R = P["reports"]

    if a.step == "step1-discover":
        rc = discover.main(["services", "--report", os.path.join(R, "step1_services.json")] +
                           (["--spec", a.spec] if a.spec else []))
        if rc == 0 and a.code_dir:
            if not a.repo or not a.ref:
                print("NO-GO: --code-dir richiede --repo e almeno un --ref")
                return 1
            rc = discover.main(["codefp", "--code-dir", a.code_dir, "--repo", a.repo, "--subdir", a.subdir,
                                "--report", os.path.join(R, "step1_codefp.json")] +
                               [x for r in a.ref for x in ("--ref", r)])
        return rc
    if a.step == "step2-preflight":
        return snap.main(["--spec", a.spec, "--dest", P["snapshot"], "--dry-run"])
    if a.step == "step3-snapshot":
        return snap.main(["--spec", a.spec, "--dest", P["snapshot"], "--auth-ref", a.auth_ref])
    if a.step == "step4-manifest":
        if not os.path.isfile(os.path.join(P["snapshot"], "snapshot_log.json")):
            print("NO-GO: snapshot assente (eseguire prima step3)")
            return 1
        return inv.main(["--root", f"snapshot={P['snapshot']}", "--include-db", "--sqlite",
                         "--out", os.path.join(R, "step4_manifest.json"),
                         "--summary-out", os.path.join(R, "step4_manifest_summary.json")])
    if a.step == "step5-restore-audit":
        if not os.path.isfile(os.path.join(P["snapshot"], "snapshot_log.json")):
            print("NO-GO: snapshot assente (eseguire prima step3)")
            return 1
        return audit.main(["--snapshot", P["snapshot"], "--restore-dir", P["restore"],
                           "--report", os.path.join(R, "step5_audit.json"),
                           "--summary", os.path.join(R, "step5_audit_summary.json")] +
                          (["--expect-v3", a.expect_v3] if a.expect_v3 else []))
    # status: solo numeri
    out = {}
    for f in sorted(os.listdir(R)):
        if f.endswith("_summary.json"):
            with open(os.path.join(R, f), encoding="utf-8") as fh:
                out[f] = json.load(fh)
    out["done"] = {"step1": os.path.exists(os.path.join(R, "step1_services.json")),
                   "step3": os.path.exists(os.path.join(P["snapshot"], "snapshot_log.json")),
                   "step4": os.path.exists(os.path.join(R, "step4_manifest.json")),
                   "step5": os.path.exists(os.path.join(R, "step5_audit.json"))}
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
