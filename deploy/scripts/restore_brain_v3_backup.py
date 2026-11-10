#!/usr/bin/env python3
"""Verifica e ripristino ISOLATO di un backup cifrato Brain V3 / Brain Free (prodotto da external_backup_brain_v3.py).

Uso:
  restore_brain_v3_backup.py --archive superbot-brainv3-AAAAMMGGTHHMMSSZ.tar.gz.age \\
      --identity chiave-di-recupero.txt --out /cartella/vuota [--manifest ...manifest.json] [--v3-src /percorso/RC84]

Serve la chiave PRIVATA di recupero (custodita dall'utente, fuori da GitHub e dal server). Scrive SOLO dentro --out
(vuota o inesistente; mai dentro le cartelle vere /opt/superbot-v3-paper-runs, /opt/superbot-brain-free,
/opt/superbot-desk-data). Non avvia, non ferma e non esegue niente: nessun bot, nessun ordine, nemmeno PAPER.

Passi (qualunque difetto = uscita 1, e --out resta per l'esame):
  1. archivio (o parti .partNNN) con SHA-256 e dimensione uguali al manifesto in chiaro;
  2. decifratura age (cifratura autenticata) ed estrazione SICURA (solo file normali sotto dati/);
  3. manifesto interno: ogni file con dimensione e SHA-256 dichiarati, nessun file in piu';
  4. per ogni run V3: le STESSE verifiche del backup sui file ripristinati (integrita' SQLite, catena hash del journal,
     identita' unica, coerenza configurazione/marcatore/mandato/evento di preparazione, budget, posizioni PAPER) e
     confronto con i valori registrati al momento del backup (eventi, hash di testa, posizioni ancora aperte,
     righe e spesa del budget, impronta dell'identita'); nessun evento duplicato o mancante;
  5. database storico Brain Free: integrita' e misura (eventi, hash del flusso, hash dello stato) uguali al manifesto;
  6. la run ripristinata e' sempre IN PAUSA: se la sorgente non aveva pause.flag ne viene scritto uno nella COPIA;
     heartbeat e richieste di chiusura restano in transient/ (non vengono mai rimessi in funzione);
  7. file sconosciuti archiviati in extra/: elencati nel manifesto con il percorso originale; qui si controllano
     dimensione e SHA-256, si ripristina la data di modifica e si riportano modo e percorso originale in
     RESTORE-REPORT.json. Restano SOLO in extra/: nulla viene rimesso nella cartella della run (nessuna attivazione);
  8. facoltativo --certificate FILE: se, e solo se, TUTTO e' OK, scrive un certificato del ripristino (archivio, SHA-256
     dell'archivio cifrato, macchina, data, run con eventi e hash di testa, impronte degli strumenti). L'installatore lo
     richiede, insieme alla prova di un backup realmente pubblicato, prima di attivare il timer;
  9. facoltativo --v3-src: controllo con il codice VERO di RC84 (check_existing_data, verify_prepared_run_config,
     load_runner_config, build_summary): se non indicato il passo e' dichiarato NON ESEGUITO (non e' un PASS).
"""
import argparse
import gzip
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FORBIDDEN_OUT = ("/opt/superbot-v3-paper-runs", "/opt/superbot-brain-free", "/opt/superbot-desk-data")


def load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def under(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root.rstrip("/") + "/")


def assemble(archive, pub, tmpdir, problems, sha256_file):
    """Percorso dell'archivio cifrato unico (ricomposto dalle parti se serve), con i controlli sul manifesto."""
    if pub.get("parti"):
        joined = os.path.join(tmpdir, "archivio.tar.gz.age")
        with open(joined, "wb") as out:
            for p in pub["parti"]:
                path = os.path.join(os.path.dirname(archive), p["nome"])
                if not os.path.isfile(path):
                    problems.add("parte mancante: %s" % p["nome"])
                    return None
                if os.path.getsize(path) != p["dimensione"] or sha256_file(path) != p["sha256"]:
                    problems.add("la parte %s non coincide col manifesto (alterata o incompleta)" % p["nome"])
                    return None
                with open(path, "rb") as f:
                    shutil.copyfileobj(f, out)
        archive = joined
    if not os.path.isfile(archive):
        problems.add("archivio cifrato non trovato: %s" % archive)
        return None
    if pub:
        if sha256_file(archive) != pub.get("sha256") or os.path.getsize(archive) != pub.get("dimensione"):
            problems.add("l'archivio cifrato NON coincide col manifesto (SHA-256 o dimensione diversi)")
            return None
        print("  archivio cifrato: SHA-256 e dimensione uguali al manifesto%s"
              % (" (ricomposto da %d parti)" % len(pub["parti"]) if pub.get("parti") else ""))
    return archive


def check_run(out, rec, snap, problems, now_ms):
    name = rec["run_name"]
    base = os.path.join(out, "dati", "runs", name)
    try:
        got = snap.facts_from_files(base, name, now_ms)
    except snap.Refused as e:
        problems.add("run %s: verifica fallita (%s) %s" % (name, e.code, e.detail))
        return None
    j, rj, b, rb = got["journal"], rec["journal"], got["budget"], rec["budget"]
    pairs = [("eventi", j["eventi"], rj["eventi"]), ("seq_max", j["seq_max"], rj["seq_max"]),
             ("testa", j["testa"], rj["testa"]), ("primo", j["primo"], rj["primo"]),
             ("posizioni aperte (ids)", j["paper"]["ids_aperte_sha256"], rj["paper"]["ids_aperte_sha256"]),
             ("posizioni chiuse", j["paper"]["chiuse"], rj["paper"]["chiuse"]),
             ("budget righe", b["righe"], rb["righe"]), ("budget unita", b["unita"], rb["unita"]),
             ("budget testa", b["testa"], rb["testa"]), ("config sha256", got["config"]["sha256"], rec["config"]["sha256"]),
             ("identita", got["identita_sha256"], rec["identita_sha256"])]
    for label, now, then in pairs:
        if now != then:
            problems.add("run %s: %s diverso dal manifesto del backup" % (name, label))
    pause = os.path.join(base, "pause.flag")
    forced = False
    if not os.path.lexists(pause):
        with open(pause, "w") as f:
            f.write("restored_and_paused\n")
        os.chmod(pause, 0o600)
        forced = True
    print("  run %s: journal %d eventi, catena hash OK, testa %s..., identita unica OK | posizioni PAPER: %d aperte, %d chiuse | "
          "budget %d righe | config %s... | %s" % (
              name, j["eventi"], j["testa"][:10], j["paper"]["ancora_aperte"], j["paper"]["chiuse"], b["righe"],
              got["config"]["sha256"][:10], "pausa FORZATA nella copia" if forced else "gia' in pausa"))
    return {"run": name, "eventi": j["eventi"], "testa": j["testa"], "aperte": j["paper"]["ancora_aperte"],
            "chiuse": j["paper"]["chiuse"], "pausa_forzata": forced, "ids_aperte": j["paper"]["ids_aperte"],
            "run_id": got["run_id"]}


RUN_ROOT_ALLOWED = ("journal.db", "budget.db", "runner_config.json", "PREPARED_PAUSED_ONLY.json", "mandate.json",
                    "daily_loss.json", "pause.flag", "transient", "extra")


def check_extras(out, rec, problems):
    """Controlla i file sconosciuti di una run (extra/) contro il manifesto. Restituisce l'elenco per il rapporto."""
    name = rec["run_name"]
    base = os.path.join(out, "dati", "runs", name)
    extra_dir = os.path.join(base, "extra")
    declared = {e["nome"]: e for e in rec.get("extra", [])}
    present = sorted(os.listdir(extra_dir)) if os.path.isdir(extra_dir) else []
    if sorted(declared) != present:
        problems.add("run %s: i file in extra/ (%s) non coincidono con quelli del manifesto (%s)"
                     % (name, ",".join(present) or "-", ",".join(sorted(declared)) or "-"))
    stray = sorted(n for n in os.listdir(base) if n not in RUN_ROOT_ALLOWED)
    if stray:
        problems.add("run %s: file non previsti nella cartella della run: %s" % (name, ",".join(stray)))
    done = []
    for n, e in sorted(declared.items()):
        path = os.path.join(extra_dir, n)
        if not os.path.isfile(path):
            continue
        if os.path.getsize(path) != e["size"] or classic_sha(path) != e["sha256"]:
            problems.add("run %s: extra/%s diverso dal manifesto" % (name, n))
            continue
        ts = e["mtime_ms"] / 1000.0
        os.utime(path, (ts, ts))
        print("  extra: %s/%s  originale %s -> extra/%s  (%d byte, modo originale %s)"
              % (name, n, e["percorso_originale"], n, e["size"], e["modo"]))
        done.append({"run": name, "nome": n, "percorso_originale": e["percorso_originale"], "archiviato_in": "extra/" + n,
                     "size": e["size"], "sha256": e["sha256"], "modo_originale": e["modo"], "mtime_ms": e["mtime_ms"]})
    if declared:
        print("  extra: nessun file e' stato rimesso nella cartella della run (nessuna attivazione automatica)")
    return done


def classic_sha(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cross_check_rc84(src, out, restored, problems):
    """Controllo con il codice vero di RC84 (facoltativo). Restituisce True se eseguito."""
    sys.path.insert(0, src)
    try:
        from backend.v3.runner.exit_worker import check_existing_data
        from backend.v3.runner.prepared_config_guard import verify_prepared_run_config
        from backend.v3.runner.config import load_runner_config
        from backend.v3.dashboard import build_summary
    except ImportError as e:
        problems.add("--v3-src indicato ma il codice RC84 non e' importabile: %s" % e)
        return False
    from pathlib import Path
    for r in restored:
        d = Path(os.path.join(out, "dati", "runs", r["run"])).resolve()
        try:
            journal = check_existing_data(data_dir=d, run_id=r["run_id"])
            cfg = load_runner_config((d / "runner_config.json").read_bytes())
            verify_prepared_run_config(data_dir=d, run_id=r["run_id"], config=cfg)
            ids = sorted(p.position_id for p in build_summary(journal, "brain", r["run_id"]).open_positions)
        except Exception as e:                                           # codici fissi del codice RC84
            problems.add("run %s: il codice RC84 rifiuta la copia ripristinata (%s)" % (r["run"], str(e)[:120]))
            continue
        if ids != r["ids_aperte"]:
            problems.add("run %s: posizioni aperte secondo RC84 diverse dal manifesto" % r["run"])
        else:
            print("  RC84 (codice vero) accetta la run %s: catena, configurazione preparata e %d posizioni aperte coincidono"
                  % (r["run"], len(ids)))
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", required=True)
    ap.add_argument("--identity", required=True, help="file con la chiave PRIVATA di recupero (AGE-SECRET-KEY-...)")
    ap.add_argument("--out", required=True, help="cartella vuota o inesistente (mai una cartella di produzione)")
    ap.add_argument("--manifest", default="")
    ap.add_argument("--certificate", default="", help="scrive il certificato del ripristino solo se TUTTO e' OK")
    ap.add_argument("--v3-src", default="", help="checkout di RC84 per il controllo con il codice vero (facoltativo)")
    a = ap.parse_args(argv)

    classic = load("restore_external_backup", "restore_external_backup.py")
    snap = load("brain_v3_snapshot", "brain_v3_snapshot.py")
    problems = classic.Problems()
    if any(under(a.out, f) for f in FORBIDDEN_OUT):
        print("ERRORE: --out non puo' stare dentro una cartella di produzione")
        return 1
    if os.path.exists(a.out) and os.listdir(a.out):
        print("ERRORE: la cartella di ripristino %s non e' vuota" % a.out)
        return 1
    if not shutil.which("age"):
        print("ERRORE: serve il programma age (apt install age)")
        return 1
    print("RIPRISTINO DI PROVA di %s" % os.path.basename(a.archive))

    mpath = a.manifest or (a.archive[: -len(".tar.gz.age")] + ".manifest.json" if a.archive.endswith(".tar.gz.age") else "")
    pub = {}
    if mpath and os.path.isfile(mpath):
        with open(mpath) as f:
            pub = json.load(f)
    else:
        print("  (nessun manifesto in chiaro: salto il controllo dell'hash del cifrato; age controlla comunque l'integrita')")
    os.makedirs(a.out, mode=0o700, exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="restore-v3-")
    try:
        enc = assemble(a.archive, pub, tmpdir, problems, classic.sha256_file)
        if enc is None:
            print("RISULTATO: FALLITO")
            return 1
        enc_sha = classic.sha256_file(enc)
        plain = os.path.join(tmpdir, "archivio.tar.gz")
        p = subprocess.run(["age", "-d", "-i", a.identity, "-o", plain, enc], capture_output=True, text=True)
        if p.returncode != 0:
            problems.add("decifratura non riuscita (chiave sbagliata o archivio alterato): %s" % p.stderr.strip()[-200:])
            print("RISULTATO: FALLITO")
            return 1
        print("  decifratura riuscita (cifratura autenticata: archivio non alterato)")
        try:
            extracted = classic.safe_extract(plain, a.out, problems)
        except (tarfile.TarError, OSError, EOFError, gzip.BadGzipFile) as e:
            problems.add("archivio non leggibile: %s" % e)
            print("RISULTATO: FALLITO")
            return 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    try:
        with open(os.path.join(a.out, classic.INTERNAL_MANIFEST)) as f:
            inner = json.load(f)
    except (OSError, ValueError):
        problems.add("manifesto interno mancante o illeggibile")
        inner = {"file": []}
    if inner.get("schema") != "superbot-brain-v3-backup-v1":
        problems.add("schema del manifesto interno non riconosciuto: %s" % inner.get("schema"))
    declared = {x["file"]: x for x in inner.get("file", [])}
    for name, x in declared.items():
        path = os.path.join(a.out, *name.split("/"))
        if not os.path.isfile(path):
            problems.add("file dichiarato ma assente: %s" % name)
        elif os.path.getsize(path) != x["size"] or classic.sha256_file(path) != x["sha256"]:
            problems.add("file diverso dal manifesto interno: %s" % name)
    for name in extracted:
        if name != classic.INTERNAL_MANIFEST and name not in declared:
            problems.add("file non dichiarato nel manifesto interno: %s" % name)
    print("  manifesto interno: %d file controllati (dimensione e SHA-256) | famiglia %s | creato %s"
          % (len(declared), inner.get("famiglia"), inner.get("creato")))

    now_ms = int(time.time() * 1000)
    restored, extras_report = [], []
    if inner.get("famiglia") == "v3":
        runs = inner.get("runs") or []
        if not runs:
            problems.add("il manifesto non elenca nessuna run")
        for rec in runs:
            r = check_run(a.out, rec, snap, problems, now_ms)
            if r:
                restored.append(r)
                extras_report += check_extras(a.out, rec, problems)
        names = sorted(os.listdir(os.path.join(a.out, "dati", "runs"))) if os.path.isdir(os.path.join(a.out, "dati", "runs")) else []
        if names != sorted(r["run_name"] for r in runs):
            problems.add("le cartelle delle run ripristinate non coincidono con il manifesto")
        if a.v3_src:
            cross_check_rc84(a.v3_src, a.out, restored, problems)
        else:
            print("  controllo con il codice vero di RC84: NON ESEGUITO (indicare --v3-src); non e' un PASS")
    elif inner.get("famiglia") == "brain-free":
        path = os.path.join(a.out, "dati", "legacy", "brain.sqlite3")
        try:
            got = snap.verify_legacy_copy(path, inner.get("legacy"))
            print("  Brain Free storico: integrity_check ok | %d eventi (seq max %d) | hash flusso %s... | stato %s..."
                  % (got["eventi"], got["seq_max"], got["events_sha256"][:10], got["state_sha256"][:10]))
        except snap.Refused as e:
            problems.add("database storico: %s %s" % (e.code, e.detail))
    else:
        problems.add("famiglia di backup sconosciuta: %s" % inner.get("famiglia"))

    report = {"archivio": os.path.basename(a.archive), "esito": "FALLITO" if problems else "OK",
              "problemi": list(problems), "run": [{k: v for k, v in r.items() if k != "ids_aperte"} for r in restored],
              "controllo_rc84": "eseguito" if a.v3_src else "non eseguito", "extra": extras_report}
    with open(os.path.join(a.out, "RESTORE-REPORT.json"), "w") as f:
        json.dump(report, f, indent=1, sort_keys=True)
    if problems:
        print("RISULTATO: FALLITO (%d problemi). La cartella %s resta per l'esame. Nessun certificato scritto." % (len(problems), a.out))
        return 1
    if a.certificate:
        cert = {"schema": "superbot-brain-v3-restore-certificate-v1", "esito": "OK", "famiglia": inner.get("famiglia"),
                "archivio": os.path.basename(a.archive), "archivio_sha256": enc_sha, "eseguito_su": socket.gethostname(),
                "eseguito_il": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "controllo_rc84": "eseguito" if a.v3_src else "non eseguito",
                "run": [{"nome": r["run"], "eventi": r["eventi"], "testa": r["testa"]} for r in restored],
                "extra": len(extras_report),
                "strumenti": {"restore_brain_v3_backup.py": classic_sha(os.path.abspath(__file__)),
                              "brain_v3_snapshot.py": classic_sha(os.path.join(HERE, "brain_v3_snapshot.py"))}}
        with open(a.certificate, "w") as f:
            json.dump(cert, f, indent=1, sort_keys=True)
        print("  certificato del ripristino scritto in %s (archivio sha256 %s...)" % (a.certificate, enc_sha[:12]))
    print("RISULTATO: OK  backup decifrato, completo e coerente in %s (nulla avviato, nulla scritto fuori da questa cartella)" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
