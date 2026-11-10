#!/usr/bin/env python3
"""Crea e prova la CHIAVE PERSONALE di recupero dei backup, sul TUO computer. Niente rete, niente GitHub, niente VPS, niente chat.

  python3 chiave_personale.py crea  --cartella ~/Documents/superbot-chiave [--nome chiave-personale] [--proteggi]
  python3 chiave_personale.py prova --identita ~/Documents/superbot-chiave/chiave-personale.txt --pubblica age1...
  python3 chiave_personale.py prova --identita-protetta ~/Documents/superbot-chiave/chiave-personale.txt.age --pubblica age1...

Che cosa fa (e nient'altro):
  crea   genera la coppia con `age-keygen`, scrive la PRIVATA in un file con permessi 600 nella cartella che indichi e stampa SOLO la
         chiave PUBBLICA (age1...) e la sua impronta. La privata non viene mai stampata, mai copiata altrove, mai inviata. Con
         --proteggi ne fa anche una copia protetta da passphrase (`age -p`, la passphrase la digiti tu nel terminale di age).
  prova  controlla che la privata corrisponda alla pubblica e che il giro cifra/decifra funzioni (16 KiB casuali), stampando solo
         frasi fisse. Con --identita-protetta decifra la copia protetta in una cartella privata temporanea che poi cancella.
Rifiuta di lavorare: dentro un repository git (la privata non deve finire in un commit), sul server (se vede /opt/superbot-tools o
/opt/superbot-extbackup-v2) e su una cartella che non sia tua. Serve il programma `age` (macOS: brew install age; Windows: winget
install FiloSottile.age; Linux: apt install age). Solo libreria standard; nessun import di rete (c'e' un test che lo verifica).
Dopo `crea`: invia in chat SOLO la riga `chiave pubblica: age1...` (e' pubblica); la privata non va incollata da nessuna parte.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

SERVER_MARKERS = ("/opt/superbot-tools", "/opt/superbot-extbackup-v2", "/opt/superbot-extbackup")
KEY_RE_PREFIX = "age1"
PRIVATE_PREFIX = "AGE-SECRET-KEY-"


def say(msg=""):
    print(msg, flush=True)


def need(tool):
    if not shutil.which(tool):
        say("MANCA il programma '%s'. Installalo (macOS: brew install age · Windows: winget install FiloSottile.age · Linux: apt install age)." % tool)
        return False
    return True


def inside_git(path):
    p = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(p, ".git")):
            return True
        parent = os.path.dirname(p)
        if parent == p:
            return False
        p = parent


def looks_like_server():
    return [m for m in SERVER_MARKERS if os.path.exists(m)]


def public_of(identity_path):
    p = subprocess.run(["age-keygen", "-y", identity_path], capture_output=True, text=True)
    pub = p.stdout.strip()
    return pub if p.returncode == 0 and pub.startswith(KEY_RE_PREFIX) and len(pub) == 62 else ""


def fingerprint(pub):
    return hashlib.sha256((pub + "\n").encode()).hexdigest()


def cmd_crea(a):
    if looks_like_server():
        say("RIFIUTATO: questo sembra il server (%s). La chiave personale si crea sul TUO computer, non sulla VPS." % looks_like_server()[0])
        return 1
    if not (need("age-keygen") and (not a.proteggi or need("age"))):
        return 1
    folder = os.path.abspath(os.path.expanduser(a.cartella))
    if inside_git(folder):
        say("RIFIUTATO: %s e' dentro un repository git: la chiave privata non deve poter finire in un commit. Scegli una cartella fuori da ogni repository." % folder)
        return 1
    if not __import__("re").fullmatch(r"[A-Za-z0-9._-]{1,40}", a.nome):
        say("RIFIUTATO: il nome puo' contenere solo lettere, cifre, punto, trattino e underscore (massimo 40).")
        return 1
    ident = os.path.join(folder, a.nome + ".txt")
    if os.path.exists(ident) or os.path.exists(ident + ".age"):
        say("RIFIUTATO: in %s esiste gia' una chiave: non la sovrascrivo." % folder)
        return 1
    os.makedirs(folder, mode=0o700, exist_ok=True)
    os.umask(0o077)
    p = subprocess.run(["age-keygen", "-o", ident], capture_output=True, text=True)
    if p.returncode != 0 or not os.path.isfile(ident):
        say("ERRORE: age-keygen non ha creato la chiave (%s)." % (p.stderr.strip().splitlines() or ["?"])[-1][:120])
        return 1
    os.chmod(ident, 0o600)
    pub = public_of(ident)
    if not pub:
        say("ERRORE: non riesco a ricavare la chiave pubblica; il file creato e' %s" % ident)
        return 1
    with open(os.path.join(folder, a.nome + "-pubblica.txt"), "w", encoding="utf-8") as f:
        f.write("# chiave PUBBLICA di recupero dei backup SuperBot (si puo' condividere)\n%s\n" % pub)
    say("FATTO. La chiave PRIVATA e' qui (permessi 600, non la mostro e non la invio): %s" % ident)
    say("chiave pubblica: %s" % pub)
    say("impronta della pubblica (da annotare nel diario): %s" % fingerprint(pub))
    if a.proteggi:
        say("")
        say("Adesso `age` ti chiede una passphrase (scrivila tu, due volte; non e' quella del gestore di password).")
        r = subprocess.run(["age", "-p", "-o", ident + ".age", ident])
        if r.returncode != 0 or not os.path.isfile(ident + ".age"):
            say("ATTENZIONE: la copia protetta NON e' stata creata; ripeti con: age -p -o '%s.age' '%s'" % (ident, ident))
            return 1
        say("Copia protetta creata: %s.age" % ident)
    say("")
    say("PROSSIMI PASSI (nell'ordine):")
    say(" 1. Prova subito:  python3 chiave_personale.py prova --identita '%s' --pubblica %s" % (ident, pub))
    say(" 2. Fai almeno DUE copie della privata (o della copia protetta) in luoghi fisicamente diversi: gestore di password e chiavetta/carta in cassaforte.")
    say(" 3. Ripeti la prova partendo dalla COPIA (non dall'originale): una copia mai provata non e' una copia.")
    say(" 4. Cancella l'originale in chiaro solo dopo la prova della copia protetta (macOS: rm -P; Linux: shred -u).")
    say(" 5. Scrivi in chat SOLO la riga 'chiave pubblica: ...' qui sopra. Mai la privata: se per errore finisce in una chat, e' esposta e va rifatta.")
    return 0


def cmd_prova(a):
    if not (need("age") and need("age-keygen")):
        return 1
    want = a.pubblica.strip()
    if want.startswith(PRIVATE_PREFIX):
        say("RIFIUTATO: hai incollato una chiave PRIVATA. Qui serve la parte pubblica (age1...). Considera quella chiave esposta.")
        return 1
    if not (want.startswith(KEY_RE_PREFIX) and len(want) == 62):
        say("RIFIUTATO: la chiave pubblica deve iniziare con age1 ed essere lunga 62 caratteri.")
        return 1
    tmp = None
    try:
        ident = a.identita
        if a.identita_protetta:
            tmp = tempfile.mkdtemp(prefix="chiave-")
            os.chmod(tmp, 0o700)
            ident = os.path.join(tmp, "id.txt")
            say("Digita la passphrase della copia protetta quando age la chiede.")
            r = subprocess.run(["age", "-d", "-o", ident, a.identita_protetta])
            if r.returncode != 0 or not os.path.isfile(ident):
                say("ESITO copia protetta: NO (passphrase errata o file non valido)")
                return 1
        if not ident or not os.path.isfile(ident):
            say("ESITO: NO (file della chiave privata non trovato)")
            return 1
        derived = public_of(ident)
        ok_pair = derived == want
        say("ESITO la privata corrisponde alla pubblica indicata: %s" % ("OK" if ok_pair else "NO"))
        ok_round = False
        if derived:
            work = tempfile.mkdtemp(prefix="prova-")
            try:
                os.chmod(work, 0o700)
                plain, enc, dec = (os.path.join(work, n) for n in ("p", "p.age", "p.out"))
                data = os.urandom(16 * 1024)
                with open(plain, "wb") as f:
                    f.write(data)
                e = subprocess.run(["age", "-r", want, "-o", enc, plain], capture_output=True)
                d = subprocess.run(["age", "-d", "-i", ident, "-o", dec, enc], capture_output=True) if e.returncode == 0 else None
                ok_round = bool(d) and d.returncode == 0 and os.path.isfile(dec) and open(dec, "rb").read() == data
            finally:
                shutil.rmtree(work, ignore_errors=True)
        say("ESITO cifratura e decifratura di prova (16 KiB casuali): %s" % ("OK" if ok_round else "NO"))
        total = ok_pair and ok_round
        say("ESITO COMPLESSIVO: %s" % ("OK - la chiave funziona" if total else "NO - non usare questa chiave"))
        if total:
            say("impronta della pubblica: %s" % fingerprint(want))
        return 0 if total else 1
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crea")
    c.add_argument("--cartella", required=True)
    c.add_argument("--nome", default="chiave-personale", help="nome dei file (es. chiave-actions per la chiave da mettere nell'ambiente di GitHub)")
    c.add_argument("--proteggi", action="store_true", help="crea anche la copia protetta da passphrase (age -p)")
    t = sub.add_parser("prova")
    g = t.add_mutually_exclusive_group(required=True)
    g.add_argument("--identita", help="file della privata in chiaro")
    g.add_argument("--identita-protetta", help="copia protetta da passphrase (.age)")
    t.add_argument("--pubblica", required=True)
    a = ap.parse_args(argv)
    return {"crea": cmd_crea, "prova": cmd_prova}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
