#!/usr/bin/env python3
"""Controllo ISOLATO di una chiave privata age contro il destinatario pubblico documentato (da lanciare dal workflow age-v2-key-check).

Che cosa fa (nessun archivio, nessuna rete, nessun repository privato, nessuna VPS):
  1. deriva internamente la chiave PUBBLICA dalla privata (age-keygen -y);
  2. la confronta con le chiavi pubbliche del file dei destinatari documentati (il destinatario V2 del 23 ottobre) e, se indicato con
     --current-recipients, con i destinatari ATTUALI dei backup (file di questo commit): se il Secret e' stato sostituito da una
     chiave nuova, la seconda verifica e' quella che conta, la prima diventa un'informazione ("non e' la V2 documentata");
  3. se la chiave e' un destinatario valido, prova che la coppia FUNZIONA: cifra 4 KiB casuali verso la propria chiave pubblica, li
     decifra con la chiave privata e confronta l'impronta; i file di prova stanno in --work e vengono cancellati.
Nei log compare soltanto ESITO ... OK/NO: mai la chiave privata, mai la pubblica, mai il destinatario.
Il file della chiave privata NON viene mai aperto da questo programma: si passa solo il suo percorso ad age.
Uscita 0 solo se la chiave e' un destinatario valido (quello documentato, oppure uno attuale se --current-recipients) E la prova di
cifratura/decifratura riesce; 2 altrimenti.
NON dice dove sia memorizzato il Secret (di repository o di ambiente): quello si controlla solo nell'interfaccia di GitHub.
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys

KEY_RE = re.compile(r"^age1[0-9a-z]{58}$")


def say(msg=""):
    print(msg, flush=True)


def derive_public(identity):
    p = subprocess.run(["age-keygen", "-y", identity], capture_output=True, text=True, timeout=60)
    pub = p.stdout.strip()
    return pub if p.returncode == 0 and KEY_RE.match(pub) else None


def documented_keys(path):
    with open(path, encoding="utf-8") as f:
        keys = [l.strip() for l in f.read().splitlines() if l.strip() and not l.strip().startswith("#")]
    return [k for k in keys if KEY_RE.match(k)]


def roundtrip(identity, keys, work):
    """Cifra verso i destinatari documentati e decifra con la chiave privata: True se il contenuto coincide."""
    os.makedirs(work, mode=0o700, exist_ok=True)
    plain, enc, dec = (os.path.join(work, n) for n in ("prova.bin", "prova.age", "prova.dec"))
    try:
        data = os.urandom(4096)
        with open(plain, "wb") as f:
            f.write(data)
        cmd = ["age"]
        for k in keys:
            cmd += ["-r", k]
        if subprocess.run(cmd + ["-o", enc, plain], capture_output=True, timeout=120).returncode != 0:
            return False
        if subprocess.run(["age", "-d", "-i", identity, "-o", dec, enc], capture_output=True, timeout=120).returncode != 0:
            return False
        with open(dec, "rb") as f:
            return hashlib.sha256(f.read()).digest() == hashlib.sha256(data).digest()
    finally:
        for p in (plain, enc, dec):
            if os.path.exists(p):
                os.unlink(p)
        shutil.rmtree(work, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--identity", required=True, help="PERCORSO del file con la chiave privata (non viene mai letto qui)")
    ap.add_argument("--recipients", required=True, help="file con la/le chiave/i PUBBLICA/HE documentata/e")
    ap.add_argument("--current-recipients", default="", help="file dei destinatari ATTUALI dei backup (di questo commit)")
    ap.add_argument("--work", required=True)
    ap.add_argument("--summary", default="")
    a = ap.parse_args(argv)
    os.umask(0o077)
    report = []

    def line(msg=""):
        report.append(msg)
        say(msg)
    line("# Controllo isolato della chiave privata age V2")
    keys = documented_keys(a.recipients)
    pub = derive_public(a.identity)
    ok_read = pub is not None
    line("ESITO chiave privata leggibile e valida: %s" % ("OK" if ok_read else "NO"))
    ok_doc = bool(ok_read and keys and pub in keys)
    line("ESITO la chiave pubblica derivata coincide con il destinatario V2 documentato il 23 ottobre: %s" % ("OK" if ok_doc else "NO"))
    ok_match = ok_doc
    if a.current_recipients:
        current = documented_keys(a.current_recipients)
        ok_cur = bool(ok_read and current and pub in current)
        line("ESITO la chiave e' tra i destinatari dei backup di questo commit: %s" % ("OK" if ok_cur else "NO"))
        ok_match = ok_cur
    ok_trip = False
    if ok_match:
        ok_trip = roundtrip(a.identity, [pub], a.work)
        line("ESITO prova di cifratura e decifratura con la coppia: %s" % ("OK" if ok_trip else "NO"))
    else:
        line("ESITO prova di cifratura e decifratura con la coppia: NO (non eseguita: la chiave non coincide)")
    total = ok_read and ok_match and ok_trip
    line("ESITO COMPLESSIVO: %s" % ("OK" if total else "NO"))
    if total and ok_doc:
        line("La chiave V2 nel Secret appartiene alla coppia documentata: puo' decifrare gli archivi cifrati per quel destinatario.")
    elif total:
        line("La chiave nel Secret e' un destinatario attuale dei backup ma NON e' la V2 documentata il 23 ottobre: chiave sostituita.")
    if a.summary:
        with open(a.summary, "a") as f:
            f.write("\n".join(report) + "\n")
    return 0 if total else 2


if __name__ == "__main__":
    sys.exit(main())
