#!/usr/bin/env python3
"""Aggiunge una chiave PUBBLICA age (es. quella personale del proprietario) ai destinatari V2 e riallinea TUTTO in una volta.

  set_recipients.py --add age1... [--comment "chiave personale"] [--root RADICE] [--dry-run]

Che cosa cambia (e nient'altro): deploy/extbackup/recipient-v2.txt (una riga in piu') e l'impronta `--expect-recipients-sha256`
nei due wrapper (run-classic.sh e run-v3.sh). Poi lancia check_recipient_consistency.py e fallisce se qualcosa non torna.
Il risultato e' un diff piccolo da REVISIONARE: il destinatario V2 resta (con la V2 si continua ad aprire tutto da GitHub Actions)
e la nuova chiave si aggiunge, cosi' ogni archivio nuovo si apre con ciascuna delle due chiavi private.
Rifiuta: una chiave non valida, duplicata, uguale alla chiave V1, una privata (AGE-SECRET-KEY) per errore.
Fatelo PRIMA di installare i file sul server: il server non sovrascrive i file esistenti (per scelta), quindi cambiare i destinatari
dopo l'installazione richiede un aggiornamento controllato a parte.
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "deploy", "scripts"))
import age_recipients as ar                                       # noqa: E402

WRAPPERS = ("deploy/extbackup/v2/run-classic.sh", "deploy/extbackup/brain-v3/run-v3.sh")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--add", required=True, help="chiave PUBBLICA age1... da aggiungere")
    ap.add_argument("--comment", default="chiave personale del proprietario (custodita fuori da GitHub)")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.add.startswith("AGE-SECRET-KEY"):
        print("RIFIUTATO: questa e' una chiave PRIVATA. Non va mai scritta in nessun file del repository: serve la parte pubblica (age1...).")
        return 1
    if not ar.KEY_RE.match(a.add):
        print("RIFIUTATO: non e' una chiave pubblica age valida (age1 + 58 caratteri)")
        return 1
    rec = os.path.join(a.root, "deploy", "extbackup", "recipient-v2.txt")
    v1 = os.path.join(a.root, "deploy", "extbackup", "recipient.txt")
    keys = ar.read_recipients(rec)
    if a.add in keys:
        print("RIFIUTATO: la chiave e' gia' tra i destinatari V2")
        return 1
    if a.add in ar.read_recipients(v1):
        print("RIFIUTATO: e' la chiave V1 (di cui non abbiamo la privata): non va riusata")
        return 1
    if len(keys) + 1 > ar.MAX_RECIPIENTS:
        print("RIFIUTATO: troppi destinatari")
        return 1
    old_fp, new_fp = ar.fingerprint(keys), ar.fingerprint(keys + [a.add])
    print("impronta dei destinatari: %s... -> %s... (%d -> %d chiavi)" % (old_fp[:12], new_fp[:12], len(keys), len(keys) + 1))
    if a.dry_run:
        print("SIMULAZIONE: nessun file modificato")
        return 0
    with open(rec, "a", encoding="utf-8") as f:
        f.write("# %s\n%s\n" % (a.comment.replace("\n", " ")[:120], a.add))
    for rel in WRAPPERS:
        path = os.path.join(a.root, rel)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        new, n = re.subn(r"--expect-recipients-sha256 [0-9a-f]{64}", "--expect-recipients-sha256 " + new_fp, text)
        if n != 1:
            print("ERRORE: impronta non trovata (o trovata %d volte) in %s: nessuna garanzia, controllare a mano" % (n, rel))
            return 1
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
    checker = os.path.join(a.root, "deploy", "extbackup", "v2", "check_recipient_consistency.py")
    if not os.path.isfile(checker):
        print("ERRORE: manca %s: nessuna verifica di coerenza possibile; annullare con git checkout dei tre file" % checker)
        return 1
    chk = subprocess.run([sys.executable, "-I", checker, "--root", a.root], capture_output=True, text=True)
    print((chk.stdout.strip().splitlines() or ["(nessun esito dal controllo di coerenza)"])[-1])
    if chk.returncode != 0:
        print("ERRORE: la coerenza non torna dopo la modifica; annullare con git checkout dei tre file")
        return 1
    print("FATTO: file modificati: recipient-v2.txt e i due wrapper. Revisionare il diff, fare il commit, poi installare.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
