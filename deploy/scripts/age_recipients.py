#!/usr/bin/env python3
"""Destinatari age (uno o piu') per i backup esterni cifrati, con impronta di controllo.

Un file di destinatari contiene SOLO chiavi PUBBLICHE `age1...` (una per riga, commenti con #). Con piu' destinatari
l'archivio si apre con QUALUNQUE delle rispettive chiavi private (age -r A -r B): e' il modo di non dipendere da una
sola chiave (es. la chiave V2 recuperabile dalle Actions + una chiave personale custodita dal proprietario).

L'IMPRONTA dei destinatari (sha256 delle chiavi ordinate, una per riga) viene fissata nei wrapper: se il file sul server
cambia (chiave sostituita, riga tolta o aggiunta senza revisione) i programmi di backup RIFIUTANO di cifrare
(`recipient_mismatch`), invece di produrre archivi che nessuno sa piu' aprire.

Solo libreria standard. Nessun segreto: questo modulo non legge mai chiavi private.
"""
import hashlib
import os
import re
import subprocess

KEY_RE = re.compile(r"^age1[0-9a-z]{58}$")
AGE_MAGIC = b"age-encryption.org/v1"
MAX_RECIPIENTS = 4


class RecipientError(ValueError):
    """Codice fisso in `code` (recipient_file_unreadable, recipient_invalid, recipient_mismatch, ...)."""

    def __init__(self, code, detail=""):
        super().__init__(code + ((": " + detail) if detail else ""))
        self.code = code


class RecipientSet(str):
    """Valore che si comporta da stringa (chiavi unite da virgola) ma porta con se' l'elenco delle chiavi.
    Con una sola chiave coincide con la chiave stessa (compatibile con i manifesti gia' esistenti)."""

    def __new__(cls, keys):
        obj = super().__new__(cls, ",".join(keys))
        obj.keys = tuple(keys)
        return obj


def read_recipients(path):
    """Elenco delle chiavi pubbliche del file (ordine del file). Rifiuta file vuoti, righe non valide, duplicati."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        raise RecipientError("recipient_file_unreadable")
    keys = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not KEY_RE.match(line):
            raise RecipientError("recipient_invalid", "una riga non e' una chiave pubblica age (age1...)")
        keys.append(line)
    if not keys:
        raise RecipientError("recipient_invalid", "nessuna chiave pubblica nel file")
    if len(set(keys)) != len(keys):
        raise RecipientError("recipient_invalid", "chiave duplicata")
    if len(keys) > MAX_RECIPIENTS:
        raise RecipientError("recipient_invalid", "troppi destinatari")
    return keys


def fingerprint(keys):
    return hashlib.sha256(("\n".join(sorted(keys)) + "\n").encode()).hexdigest()


def split_recipients(value):
    """Chiavi da un valore di manifesto: stringa singola, stringa con virgole, oppure elenco."""
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [v for v in str(value or "").split(",") if v]


def check_expected(keys, expected_sha256):
    if not re.fullmatch(r"[0-9a-f]{64}", str(expected_sha256 or "")):
        raise RecipientError("recipient_mismatch", "impronta attesa assente o non valida")
    if fingerprint(keys) != expected_sha256:
        raise RecipientError("recipient_mismatch", "i destinatari del file non sono quelli approvati")


def load_checked(path, expected_sha256):
    keys = read_recipients(path)
    check_expected(keys, expected_sha256)
    return RecipientSet(keys)


def encrypt_to(plain, out_path, keys, age_bin="age"):
    """age -r K1 -r K2 ... -o out plain; controlla il formato del risultato. Solleva RecipientError se age fallisce."""
    cmd = [age_bin]
    for k in keys:
        cmd += ["-r", k]
    cmd += ["-o", out_path, plain]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if p.returncode != 0:
        raise RecipientError("encryption_failed", (p.stdout + p.stderr).strip()[-300:])
    os.chmod(out_path, 0o600)
    with open(out_path, "rb") as f:
        head = f.read(len(AGE_MAGIC))
    if head != AGE_MAGIC or os.path.getsize(out_path) < 200:
        raise RecipientError("encryption_failed", "il file cifrato non ha il formato age atteso")
