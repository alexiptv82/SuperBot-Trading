#!/usr/bin/env python3
"""Copia AGGIUNTIVA cifrata degli INDISPENSABILI per un secondo destinatario (es. la chiave age dello smartphone).

Riusa SENZA modificarle le funzioni di external_backup.py (stesso codice della prova certificata): copie fresche e
verificate (database + run V3/Arena con catena EventJournal), archivio con manifesto interno, cifratura age,
divisione in parti, verifica con un clone NUOVO da GitHub. Differenze, tutte di isolamento:
  - destinatario passato come valore (--recipient), MAI letto ne' scritto nel recipient.txt di produzione;
  - l'archivio va in copie/<etichetta>/AAAA/MM/, FUORI da archives/: la retention (che guarda solo archives/)
    non lo tocca e lui non tocca gli originali. Qui la retention NON viene applicata;
  - prima del commit: le modifiche preparate devono stare TUTTE sotto copie/<etichetta>/ (altrimenti nessun
    commit e nessun push); dopo il push: il commit inviato tocca solo copie/<etichetta>/ e gli archivi originali
    visibili sono gli stessi di prima;
  - recipient.txt e LEGGIMI.md della radice del repository non vengono riscritti.
Esce con 0 solo se tutto torna, altrimenti 1. Push mai forzato.
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import sys

LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
HERE = os.path.dirname(os.path.abspath(__file__))

LEGGIMI = """# Copia aggiuntiva `%(label)s`

Archivi degli INDISPENSABILI (database dell'app e del pool, Brain V3, run Arena) cifrati con age per UN SOLO
destinatario: `%(key)s`. La chiave privata corrispondente non e' qui.

- E' una copia in PIU': gli archivi in `archives/` (chiave dei backup periodici) restano come sono.
- Nessuna retention automatica: la retention del backup periodico guarda solo `archives/`.
- Ripristino: `deploy/scripts/restore_external_backup.py` (repository SuperBot-Trading), come per gli altri archivi.
"""


def load_ext(tools):
    spec = importlib.util.spec_from_file_location("external_backup_lib", os.path.join(tools, "external_backup.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def changed(repo, *args):
    p = repo.git(*args, "-z", binary=True)
    return [x for x in p.stdout.decode().split("\0") if x]


def execute(ext, a):
    if not ext.KEY_RE.match(a.recipient):
        raise ext.Fail("il destinatario non e' una chiave pubblica age valida")
    if a.recipient in a.forbidden:
        raise ext.Fail("il destinatario della copia aggiuntiva e' la chiave dei backup periodici: non serve una copia")
    created_dt = ext.now_utc()
    created = created_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    name = "superbot-backup-indispensabili-%s.tar.gz.age" % ext.stamp(created_dt)
    stage = os.path.join(a.work, "staging")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage, mode=0o700)
    plain = os.path.join(a.work, "staging.tar.gz")
    cipher = os.path.join(a.work, name)
    try:
        ext.make_staging(a, stage)
        ext.clean_stage_locks(stage)
        ext.say("creo l'archivio e lo cifro con age per il SOLO destinatario %s ..." % a.recipient)
        meta = ext.build_archive(stage, plain, created, a)
        ext.encrypt(plain, cipher, a.recipient)
    finally:
        try:
            os.unlink(plain)
        except FileNotFoundError:
            pass
        shutil.rmtree(stage, ignore_errors=True)
    prefix = "copie/" + a.label
    try:
        digest, size = ext.sha256_file(cipher), os.path.getsize(cipher)
        rel_dir = "/".join((prefix, created_dt.strftime("%Y"), created_dt.strftime("%m")))
        repo = ext.Repo(a)
        repo.sync()
        before = [os.path.relpath(p, repo.dir) for p, _ in ext.archives_in(repo.dir)]
        out_dir = os.path.join(repo.dir, *rel_dir.split("/"))
        os.makedirs(out_dir, exist_ok=True)
        part_list = None
        if size > a.part_mib * 1048576:
            part_list = []
            for part in ext.split_file(cipher, a.part_mib * 1048576):
                part_list.append({"file": os.path.basename(part), "sha256": ext.sha256_file(part),
                                  "dimensione": os.path.getsize(part)})
                shutil.move(part, os.path.join(out_dir, os.path.basename(part)))
        else:
            shutil.copyfile(cipher, os.path.join(out_dir, name))
        plain_bytes = sum(x["size"] for x in meta["file"])
        public = {"formato": ext.FORMAT, "componente": a.component, "archivio": name, "sha256": digest,
                  "dimensione": size, "creato": created, "parti": part_list,
                  "origine": meta["origine"], "versioni": meta["versioni"],
                  "cifratura": {"strumento": "age", "destinatario": a.recipient},
                  "contenuto": {"file": len(meta["file"]), "byte_in_chiaro": plain_bytes},
                  "copia_aggiuntiva": a.label, "retention": "nessuna"}
        with open(os.path.join(out_dir, ext.manifest_name(name)), "w") as f:
            json.dump(public, f, indent=1, sort_keys=True)
        with open(os.path.join(repo.dir, *prefix.split("/"), "LEGGIMI.md"), "w") as f:
            f.write(LEGGIMI % {"label": a.label, "key": a.recipient})
        # isolamento: si committa SOLO se ogni modifica sta sotto copie/<etichetta>/
        repo.git("add", "-A")
        staged = changed(repo, "diff", "--cached", "--name-only")
        outside = [p for p in staged if not p.startswith(prefix + "/")]
        if outside or not staged:
            repo.git("reset", "-q", "--hard")
            raise ext.Fail("modifiche fuori da %s/ (nessun commit, nessun push): %s" % (prefix, outside[:5]))
        repo.publish("copia aggiuntiva cifrata %s/%s (retention: nessuna)" % (a.label, name))
        sent = changed(repo, "diff", "--name-only", "--no-renames", "HEAD^", "HEAD")
        if any(not p.startswith(prefix + "/") for p in sent):
            raise ext.Fail("il commit inviato tocca file fuori da %s/" % prefix)
        after = [os.path.relpath(p, repo.dir) for p, _ in ext.archives_in(repo.dir)]
        if not set(before) <= set(after):
            raise ext.Fail("archivi originali spariti dalla punta del ramo: %s" % sorted(set(before) - set(after))[:5])
        repo.verify_remote(rel_dir + "/" + name, digest, part_list)
    finally:
        try:
            os.unlink(cipher)
        except FileNotFoundError:
            pass
    ext.say("RISULTATO: OK  copia aggiuntiva %s  archivio %s/%s  %d byte (in chiaro %d)  sha256 %s%s"
            % (a.label, rel_dir, name, size, plain_bytes, digest,
               ("  in %d parti" % len(part_list)) if part_list else ""))
    ext.say("  archivi originali in archives/: %d prima, %d dopo, nessuno tolto; retention non applicata"
            % (len(before), len(after)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tools", default=HERE, help="cartella con external_backup.py, backup_app_db.py, backup_brain.py")
    ap.add_argument("--label", required=True, help="etichetta della copia (es. android): cartella copie/<etichetta>/")
    ap.add_argument("--recipient", required=True, help="chiave PUBBLICA age del secondo destinatario")
    ap.add_argument("--forbidden-recipient", action="append", default=[], dest="forbidden",
                    help="chiave da NON usare (quella dei backup periodici)")
    ap.add_argument("--root", required=True)
    ap.add_argument("--app-db", required=True)
    ap.add_argument("--pool-db", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--remote", required=True)
    ap.add_argument("--ssh-key", default="")
    ap.add_argument("--known-hosts", default="")
    ap.add_argument("--app-repo", default="/opt/superbot")
    ap.add_argument("--bots-repo", default="/opt/superbot-desk")
    ap.add_argument("--docker-bin", default="docker")
    ap.add_argument("--containers", default="superbot,superbot-desk-hawk,superbot-desk-bull,superbot-pool")
    ap.add_argument("--part-mib", type=int, default=90)
    ap.add_argument("--required-v3-run-dir", action="append", default=[], dest="required_v3_run_dirs")
    a = ap.parse_args(argv)
    a.component = "indispensabili"
    a.required_run_dirs, a.run_dirs, a.brain_args = [], [], []
    ext = load_ext(a.tools)
    if not LABEL_RE.match(a.label):
        print("ERRORE: etichetta non valida (minuscole, cifre, trattini)")
        return 1
    if not 1 <= a.part_mib <= 95:
        print("ERRORE: --part-mib deve stare tra 1 e 95")
        return 1
    if a.ssh_key and not a.known_hosts:
        print("ERRORE: con --ssh-key serve anche --known-hosts")
        return 1
    os.makedirs(a.work, mode=0o700, exist_ok=True)
    os.chmod(a.work, 0o700)
    try:
        lock = ext.take_lock(a.work)
    except ext.Fail as e:
        print("ERRORE COPIA AGGIUNTIVA: %s" % e)
        return 1
    try:
        return execute(ext, a)
    except (ext.Fail, OSError, ext.subprocess.SubprocessError, ext.tarfile.TarError) as e:
        print("ERRORE COPIA AGGIUNTIVA: %s" % str(e)[:700])
        print("RISULTATO: FALLITO. Nessuna copia aggiuntiva e' stata considerata inviata.")
        return 1
    finally:
        os.close(lock)


if __name__ == "__main__":
    sys.exit(main())
