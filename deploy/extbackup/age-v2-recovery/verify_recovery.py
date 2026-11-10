#!/usr/bin/env python3
"""Verifica di recupero dei backup cifrati con una chiave age (da lanciare SOLO dal workflow age-v2-recovery-verify).

Che cosa fa, in un runner isolato e senza rete:
  1. deriva internamente la chiave PUBBLICA dalla chiave privata (age-keygen -y) e la confronta con il destinatario scritto
     nel manifesto di ogni archivio: nei log compare soltanto ESITO OK/NO, mai la chiave, mai il destinatario;
  2. per ogni famiglia (Falco/Toro, Brain V3, Brain Free) elenca gli archivi e quanti sono cifrati per questa chiave;
  3. se il PIU' RECENTE e' cifrato per questa chiave, lo scarica (solo quel file), lo decifra e lo ripristina con gli
     script verificati (restore_external_backup.py / restore_brain_v3_backup.py al commit fissato; per Brain V3 anche il
     codice RC84 fissato), poi CANCELLA subito il ripristino;
  4. stampa un rapporto sintetico a frasi fisse e, per ogni famiglia ripristinata, una riga CERTIFICATO (solo nomi e hash, mai
     dati di portafoglio): e' l'attestazione che l'installatore dei timer accetta come ripristino indipendente.

Garanzie di non divulgazione (verificate da test statici e di esecuzione):
  - il file della chiave privata NON viene mai aperto da questo programma: si passa solo il suo percorso ad age;
  - l'uscita degli script di ripristino (che contiene conteggi e dettagli dei portafogli) va in un file temporaneo e
    non viene MAI stampata: si stampano solo frasi fisse scelte in un elenco chiuso (booleani, nessun numero di portafoglio);
  - niente viene scritto fuori da --work, niente viene caricato altrove, tutto il decifrato e' rimosso a fine famiglia.
Uscita: 0 se i tre archivi piu' recenti sono stati ripristinati; 2 se qualcuno non e' decifrabile con questa chiave o non
e' stato confermato; 1 per errori del programma.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

FAMILIES = (
    {"nome": "Falco/Toro", "ramo": "main", "dir": "archives", "tipo": "classico",
     "rx": r"^superbot-backup-(\d{8}T\d{6}Z)\.tar\.gz\.age$"},
    {"nome": "Brain V3", "ramo": "brain-v3", "dir": "brain-v3", "tipo": "v3",
     "rx": r"^superbot-brainv3-(\d{8}T\d{6}Z)\.tar\.gz\.age$"},
    {"nome": "Brain Free storico", "ramo": "brain-free", "dir": "brain-free", "tipo": "brain-free",
     "rx": r"^superbot-brainfree-(\d{8}T\d{6}Z)\.tar\.gz\.age$"},
)
# frasi dell'uscita degli script di ripristino che si ammette di riportare (booleani): (espressione, frase pubblicata)
COMMON = ((r"SHA-256 e dimensione uguali al manifesto", "manifest e SHA-256 dell'archivio cifrato: OK"),
          (r"decifratura riuscita", "decifratura age (cifratura autenticata): OK"),
          (r"manifesto interno: \d+ file controllati", "manifesto interno, SHA-256 di ogni file: OK"))
CHECKS = {
    "classico": COMMON + ((r"database \S+: integrity_check ok", "integrita' dei database SQLite: OK"),
                          (r"coerenza hawk:.*\| OK\s*$", "coerenza semantica del primo portafoglio classico: OK"),
                          (r"coerenza bull:.*\| OK\s*$", "coerenza semantica del secondo portafoglio classico: OK")),
    "v3": COMMON + ((r"catena hash OK, .*identita unica OK", "catena hash del journal e identita' unica: OK"),
                    (r"RC84 \(codice vero\) accetta la run", "codice RC84 fissato: accetta la run ripristinata")),
    "brain-free": COMMON + ((r"Brain Free storico: integrity_check ok", "integrita' e misura del database storico: OK"),),
}
FINAL = (r"^RISULTATO: OK", "ripristino isolato completo: OK")


FAMIGLIA = {"classico": "classico", "v3": "v3", "brain-free": "brain-free"}


def certificate(fam, latest, ctx):
    """Attestazione del ripristino indipendente: solo nomi, hash e identificativi (nessun dato decifrato)."""
    return {"schema": "superbot-brain-v3-restore-certificate-v1", "esito": "OK", "famiglia": FAMIGLIA[fam["tipo"]],
            "archivio": latest["archivio"], "archivio_sha256": latest["sha256"], "eseguito_su": "github-actions",
            "origine": "github-actions", "run_id": ctx["run_id"], "workflow_sha256": ctx["workflow_sha256"],
            "script_sha256": ctx["script_sha256"], "pinned_sha": ctx["pinned_sha"],
            "controllo_rc84": "eseguito" if (fam["tipo"] == "v3" and ctx.get("rc84")) else "non eseguito"}


def out(msg=""):
    print(msg, flush=True)


def git(repo, *args):
    p = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError("git %s non riuscito" % args[0])
    return p.stdout


def derive_public(identity):
    """Chiave pubblica derivata dalla privata. La privata non passa mai da questo programma: solo il percorso."""
    p = subprocess.run(["age-keygen", "-y", identity], capture_output=True, text=True, timeout=60)
    pub = p.stdout.strip()
    return pub if p.returncode == 0 and re.fullmatch(r"age1[0-9a-z]{58}", pub) else None


def inventory(repo, fam):
    rx = re.compile(fam["rx"])
    names = git(repo, "ls-tree", "-r", "--name-only", "HEAD", "--", fam["dir"]).decode().splitlines()
    found = []
    for path in sorted(names):
        base = os.path.basename(path)
        if not base.endswith(".manifest.json"):
            continue
        archive = base[: -len(".manifest.json")] + ".tar.gz.age"
        if not rx.match(archive):
            continue
        try:
            man = json.loads(git(repo, "show", "HEAD:" + path))
        except (RuntimeError, ValueError):
            continue
        cif = man.get("cifratura") or {}
        raw = cif.get("destinatari") or cif.get("destinatario") or ""
        keys = [str(k) for k in raw] if isinstance(raw, (list, tuple)) else [k for k in str(raw).split(",") if k]
        found.append({"manifest": path, "archivio": archive, "creato": str(man.get("creato", "")),
                      "destinatari": keys, "parti": man.get("parti") or [], "sha256": str(man.get("sha256", ""))})
    found.sort(key=lambda m: (m["creato"], m["archivio"]))
    return found


def fetch_files(repo, paths):
    git(repo, "checkout", "HEAD", "--", *paths)


def restore_family(fam, latest, repo, identity, pinned, rc84, work):
    """Ripristina l'archivio `latest`; restituisce (confermato, [frasi])."""
    base = os.path.dirname(latest["manifest"])
    wanted = [latest["manifest"]] + ([os.path.join(base, p["nome"]) for p in latest["parti"]] if latest["parti"]
                                     else [os.path.join(base, latest["archivio"])])
    fetch_files(repo, wanted)
    archive = os.path.join(repo, base, latest["archivio"])
    manifest = os.path.join(repo, latest["manifest"])
    dest = os.path.join(work, "ripristino-" + fam["tipo"])
    log = os.path.join(work, "ripristino-" + fam["tipo"] + ".log")
    shutil.rmtree(dest, ignore_errors=True)
    scripts = os.path.join(pinned, "deploy", "scripts")
    if fam["tipo"] == "classico":
        cmd = [sys.executable, "-I", os.path.join(scripts, "restore_external_backup.py"), "--archive", archive,
               "--manifest", manifest, "--identity", identity, "--out", dest]
    else:
        cmd = [sys.executable, "-I", os.path.join(scripts, "restore_brain_v3_backup.py"), "--archive", archive,
               "--manifest", manifest, "--identity", identity, "--out", dest]
        if fam["tipo"] == "v3" and rc84:
            cmd += ["--v3-src", rc84]
    try:
        with open(log, "w") as lf:                              # l'uscita completa NON viene stampata
            rc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=3000).returncode
        with open(log, errors="replace") as lf:
            text = lf.read()
    finally:
        shutil.rmtree(dest, ignore_errors=True)                  # il decifrato non resta
        if os.path.exists(log):
            os.unlink(log)
    lines, ok = [], rc == 0
    for rx, phrase in CHECKS[fam["tipo"]]:
        hit = re.search(rx, text, re.M) is not None
        lines.append("%s%s" % (phrase if hit else phrase.split(":")[0] + ": NON CONFERMATO", ""))
        ok = ok and hit
    final = re.search(FINAL[0], text, re.M) is not None
    lines.append(FINAL[1] if final else "ripristino isolato completo: NON CONFERMATO")
    if fam["tipo"] == "v3":
        runs = len(re.findall(r"^\s+run \S+: journal ", text, re.M))
        lines.append("run Brain V3 ripristinate e verificate: %d" % runs)
        ok = ok and runs > 0
    if fam["tipo"] == "classico" and re.search(r"ECCEZIONE AMMESSA", text):
        lines.append("nota: copia del cervello con eccezione dichiarata nel manifesto (bot fermi o prima installazione)")
    return ok and final, lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--identity", required=True, help="PERCORSO del file con la chiave privata (non viene mai letto qui)")
    ap.add_argument("--repos-dir", required=True, help="contiene una cartella per ramo: main, brain-v3, brain-free")
    ap.add_argument("--pinned", required=True, help="checkout degli script verificati (commit fissato)")
    ap.add_argument("--rc84", default="", help="checkout di RC84 (commit fissato) per Brain V3")
    ap.add_argument("--work", required=True)
    ap.add_argument("--summary", default="", help="file a cui accodare lo stesso rapporto (GITHUB_STEP_SUMMARY)")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--workflow-sha256", default="")
    ap.add_argument("--script-sha256", default="")
    ap.add_argument("--pinned-sha", default="")
    a = ap.parse_args(argv)
    os.umask(0o077)
    os.makedirs(a.work, mode=0o700, exist_ok=True)
    report = []

    def say(msg=""):
        report.append(msg)
        out(msg)
    pub = derive_public(a.identity)
    say("# Verifica di recupero con la chiave age V2")
    if pub is None:
        say("ESITO chiave privata leggibile e valida: NO")
        say("ESITO COMPLESSIVO: NO")
        _write_summary(a.summary, report)
        return 2
    say("ESITO chiave privata leggibile e valida: OK")
    verdicts = []
    for fam in FAMILIES:
        repo = os.path.join(a.repos_dir, fam["ramo"])
        say("")
        say("## %s (ramo %s)" % (fam["nome"], fam["ramo"]))
        if not os.path.isdir(os.path.join(repo, ".git")):
            say("ESITO accesso agli archivi: NO (ramo non disponibile in questo runner)")
            verdicts.append("NO")
            continue
        try:
            inv = inventory(repo, fam)
        except RuntimeError:
            say("ESITO accesso agli archivi: NO")
            verdicts.append("NO")
            continue
        if not inv:
            say("ESITO archivi presenti: NO (nessun archivio nel ramo)")
            verdicts.append("NO")
            continue
        mine = [m for m in inv if pub in m["destinatari"]]
        say("archivi nel ramo: %d | cifrati per questa chiave: %d | altro destinatario: %d"
            % (len(inv), len(mine), len(inv) - len(mine)))
        latest = inv[-1]
        say("archivio piu' recente: %s%s" % (latest["archivio"], " (in %d parti)" % len(latest["parti"]) if latest["parti"] else ""))
        if pub not in latest["destinatari"]:
            say("ESITO destinatario del piu' recente = questa chiave: NO (non decifrabile con questa chiave: nessun tentativo)")
            verdicts.append("NO")
            continue
        say("ESITO destinatario del piu' recente = questa chiave: OK")
        try:
            confirmed, lines = restore_family(fam, latest, repo, a.identity, a.pinned, a.rc84, a.work)
        except (RuntimeError, OSError, subprocess.SubprocessError):
            confirmed, lines = False, ["ripristino: ERRORE (dettagli non pubblicati)"]
        for ln in lines:
            say("- " + ln)
        say("ESITO ripristino: %s" % ("OK" if confirmed else "NO"))
        if confirmed and a.run_id and a.workflow_sha256 and a.script_sha256 and a.pinned_sha:
            ctx = {"run_id": a.run_id, "workflow_sha256": a.workflow_sha256, "script_sha256": a.script_sha256,
                   "pinned_sha": a.pinned_sha, "rc84": a.rc84}
            say("CERTIFICATO " + json.dumps(certificate(fam, latest, ctx), sort_keys=True, separators=(",", ":")))
        verdicts.append("OK" if confirmed else "NO")
    say("")
    total = "OK" if all(v == "OK" for v in verdicts) else ("NO" if all(v == "NO" for v in verdicts) else "PARZIALE")
    say("ESITO COMPLESSIVO: %s" % total)
    say("Nessun file decifrato e' stato caricato o conservato; nessun dato di portafoglio e' stato stampato.")
    _write_summary(a.summary, report)
    return 0 if total == "OK" else 2


def _write_summary(path, report):
    if path:
        with open(path, "a") as f:
            f.write("\n".join(report) + "\n")


if __name__ == "__main__":
    sys.exit(main())
