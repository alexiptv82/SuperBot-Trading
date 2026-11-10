#!/usr/bin/env python3
"""Backup esterno cifrato di Falco/Toro con DESTINATARI MULTIPLI e impronta approvata, SENZA modificare external_backup.py.

Esegue external_backup.py (quello rivisto, identico byte per byte: l'impronta e' controllata qui) sostituendo soltanto due
funzioni del modulo caricato, in memoria:
  - read_recipient: legge un file con una o piu' chiavi PUBBLICHE age e RIFIUTA se le chiavi non sono quelle approvate
    (--expect-recipients-sha256, vedi age_recipients.py);
  - encrypt: age -r A -r B ... (chiunque possieda UNA delle chiavi private apre l'archivio).
Tutto il resto (copie verificate, archivio, retention, push senza forzature, riscaricamento di controllo, stato) e' il
codice classico. Con una sola chiave il manifesto e il risultato coincidono con quelli di external_backup.py; con piu' chiavi
il campo `destinatario` del manifesto contiene le chiavi unite da virgola.

Uso: identico a external_backup.py, piu' --expect-recipients-sha256 <impronta> (obbligatoria).
"""
import argparse
import hashlib
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CLASSIC_SHA256 = "7cad7d8fdc83b76f9cd28e93edcc75aafcca05955bf4214a0058b88e491fa5ab"      # external_backup.py rivisto (521f7fd)


def load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--expect-recipients-sha256", default="")
    known, rest = pre.parse_known_args(argv)
    if not known.expect_recipients_sha256 and not ({"-h", "--help"} & set(rest)):
        print("ERRORE BACKUP ESTERNO: serve --expect-recipients-sha256 (impronta dei destinatari approvati)")
        return 1
    with open(os.path.join(HERE, "external_backup.py"), "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != CLASSIC_SHA256:
            print("ERRORE BACKUP ESTERNO: external_backup.py non e' la versione rivista: nessun backup")
            return 1
    ar = load("age_recipients", "age_recipients.py")
    classic = load("external_backup", "external_backup.py")

    def read_recipient(path):
        try:
            return ar.load_checked(path, known.expect_recipients_sha256)
        except ar.RecipientError as e:
            raise classic.Fail(str(e))

    def encrypt(plain, out_path, recipient):
        try:
            ar.encrypt_to(plain, out_path, getattr(recipient, "keys", (str(recipient),)))
        except ar.RecipientError as e:
            raise classic.Fail(str(e))

    classic.read_recipient = read_recipient
    classic.encrypt = encrypt
    return classic.main(rest)


if __name__ == "__main__":
    sys.exit(main())
