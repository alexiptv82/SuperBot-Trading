#!/usr/bin/env python3
"""Ritiro del "ponte" temporaneo del 18/10: container superbot-desk-api e chiave SSH del tunnel.

Il ponte collegava l'app (a Strasburgo) ai bot (a Singapore). Dal 19/10 app e bot stanno sullo stesso
server e l'app legge i dati dei bot direttamente: il ponte non serve piu'. Questo strumento lo ritira
in modo REVERSIBILE e VERIFICATO. Non cancella dati, backup o container di rollback e non tocca HI-TV.

Sottocomandi:
  check    sola lettura: stato del container, chi lo usa, righe di authorized_keys che sembrano la chiave del
           tunnel (con impronta), stato del backup esterno, stato dei container dell'app e dei bot.
  retire   (solo con --fingerprint della riga da togliere e solo se il primo backup esterno e' verificato)
             1. controlli preliminari, poi copia di sicurezza (authorized_keys, fotografia del container);
             2. ferma il container superbot-desk-api, toglie il riavvio automatico e lo RINOMINA
                (superbot-desk-api-retired-<data>): non viene cancellato;
             3. toglie da authorized_keys SOLTANTO la riga con quell'impronta e con le restrizioni del tunnel
                (from=..., restrict, permitopen="127.0.0.1:18002", command="/bin/false"), una e una sola;
             4. controllo finale: app risponde, nessun ascolto su 127.0.0.1:18002, nessun'altra chiave toccata,
                bot e app con gli stessi container (stesso id, nessun riavvio), container di rollback intatti.
  restore  rimette tutto com'era: riaggiunge la riga della chiave (se manca), riporta il nome e la politica di
           riavvio originali al container e lo riavvia.

Esce con 1 se qualcosa non torna. Non stampa mai chiavi private ne' variabili d'ambiente dei container.
"""
import argparse
import base64
import binascii
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

GATEWAY = "superbot-desk-api"
ROLLBACK_PREFIX = "superbot-desk-api-retained-"       # container di rollback del 18/10: non si tocca mai
WATCHED = ("superbot", "superbot-desk-hawk", "superbot-desk-bull", "superbot-pool")
TUNNEL_MARKS = ('permitopen="127.0.0.1:18002"', 'command="/bin/false"', "restrict")
FP_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")
KEY_TYPES = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
             "sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com")


def sh(cmd, timeout=60, inp=None):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=inp)
    return p.returncode, (p.stdout + p.stderr).strip()


def say(msg=""):
    print(msg, flush=True)


# ---- authorized_keys -----------------------------------------------------------------

def split_line(raw):
    """(opzioni, tipo, blob, commento) di una riga authorized_keys; None se non e' una chiave."""
    s = raw.strip()
    if not s or s.startswith("#"):
        return None
    toks, i, n = [], 0, len(s)
    # le opzioni possono contenere spazi dentro virgolette: si cerca il primo token che e' un tipo di chiave
    pos = None
    for t in KEY_TYPES:
        m = re.search(r'(?:^|\s)(%s)\s+(\S+)(?:\s+(.*))?$' % re.escape(t), s)
        if m and (pos is None or m.start(1) < pos[0]):
            pos = (m.start(1), m)
    if pos is None:
        return None
    m = pos[1]
    return s[: m.start(1)].strip(), m.group(1), m.group(2), (m.group(3) or "").strip()


def fingerprint(typ, blob):
    """Impronta come la stampa OpenSSH: SHA256:<base64 senza '=' dello SHA-256 del blob della chiave>."""
    try:
        raw = base64.b64decode(blob.encode(), validate=True)
    except (ValueError, binascii.Error):
        return "?"
    return "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")


def option_names(opts):
    return ",".join(m.group(1) for m in re.finditer(r'([A-Za-z-]+)(?:="[^"]*")?(?:,|$)', opts))


def parse_auth(path):
    out = []
    with open(path) as f:
        for n, raw in enumerate(f, 1):
            sp = split_line(raw)
            if sp is None:
                continue
            opts, typ, blob, comment = sp
            out.append({"lineno": n, "raw": raw.rstrip("\n"), "options": opts, "type": typ, "comment": comment,
                        "fp": fingerprint(typ, blob),
                        "tunnel": all(mark in opts for mark in TUNNEL_MARKS)})
    return out


# ---- docker -----------------------------------------------------------------------------

def inspect(name):
    rc, out = sh(["docker", "inspect", name])
    if rc != 0:
        return None
    try:
        return json.loads(out)[0]
    except (ValueError, IndexError):
        return None


def container_names():
    rc, out = sh(["docker", "ps", "-a", "--format", "{{.Names}}"])
    return sorted(out.split()) if rc == 0 else []


def summary(c):
    st, hc = c.get("State", {}), c.get("HostConfig", {})
    return {"id": c.get("Id"), "running": st.get("Running"), "started": st.get("StartedAt"),
            "restarts": c.get("RestartCount"), "restart_policy": (hc.get("RestartPolicy") or {}).get("Name"),
            "image": (c.get("Config") or {}).get("Image") or c.get("Image"),
            "health": ((st.get("Health") or {}).get("Status"))}


def snapshot(names=WATCHED):
    snap = {}
    for n in names:
        c = inspect(n)
        snap[n] = summary(c) if c else None
    return snap


def health_ok():
    rc, _ = sh(["curl", "-fsS", "-m", "8", "http://127.0.0.1:8002/api/health"])
    return rc == 0


def listening_18002():
    rc, out = sh(["ss", "-tln"])
    return rc == 0 and any(re.search(r":18002\s", l) for l in out.splitlines())


def ext_backup_ok(path, max_age_h):
    """Il primo backup esterno e' verificato? (status.json scritto da external_backup.py dopo aver riscaricato e riverificato)"""
    try:
        with open(path) as f:
            st = json.load(f)
    except (OSError, ValueError):
        return False, "nessuno stato del backup esterno (%s)" % path
    ok_time = st.get("ultimo_successo")
    if not ok_time or not st.get("archivio") or not st.get("sha256"):
        return False, "nessun backup esterno riuscito e verificato"
    if st.get("ultimo_errore"):
        return False, "l'ultimo tentativo di backup esterno e' fallito: %s" % st["ultimo_errore"][:120]
    try:
        age = time.time() - datetime.datetime.strptime(ok_time, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        return False, "data del backup esterno illeggibile"
    if age > max_age_h * 3600:
        return False, "l'ultimo backup esterno riuscito e' vecchio di %.0f ore" % (age / 3600)
    return True, "ultimo backup esterno verificato: %s (%s)" % (st["archivio"], ok_time)


# ---- comandi --------------------------------------------------------------------------------

def cmd_check(a):
    say("## CONTROLLO INIZIALE DEL PONTE (sola lettura)")
    names = container_names()
    say("container del ponte: %s" % ", ".join(n for n in names if n.startswith(GATEWAY)) or "nessuno")
    g = inspect(GATEWAY)
    if g:
        s = summary(g)
        ports = {k: v for k, v in ((g.get("NetworkSettings") or {}).get("Ports") or {}).items()}
        say("  %s: in esecuzione=%s | riavvio=%s | immagine=%s | salute=%s | porte=%s"
            % (GATEWAY, s["running"], s["restart_policy"], s["image"], s["health"], json.dumps(ports)))
        mounts = [(m.get("Source"), m.get("Destination"), "rw" if m.get("RW") else "ro") for m in g.get("Mounts") or []]
        say("  cartelle montate (solo nomi): %s" % "; ".join("%s -> %s [%s]" % m for m in mounts))
    else:
        say("  %s: non esiste (gia' ritirato?)" % GATEWAY)
    for n in names:
        if n.startswith(ROLLBACK_PREFIX):
            say("  container di rollback (NON si toccano): %s" % n)
    say("ascolto su 127.0.0.1:18002: %s" % ("SI" if listening_18002() else "no"))
    say("")
    say("## authorized_keys (%s)" % a.auth)
    try:
        keys = parse_auth(a.auth)
    except OSError as e:
        say("ERRORE: %s" % e)
        return 1
    for k in keys:
        # il repository e' pubblico: della riga del tunnel (nostra) si mostra tutto; delle altre chiavi solo tipo,
        # impronta e NOME delle opzioni (mai commenti, indirizzi o comandi)
        if k["tunnel"]:
            desc = "TUNNEL commento=%s opzioni=%s" % (k["comment"] or "-", k["options"][:200])
        else:
            desc = "altra chiave | opzioni: %s" % (option_names(k["options"]) or "nessuna")
        say("  riga %d | %s | %s | %s" % (k["lineno"], k["type"], k["fp"], desc))
    tun = [k for k in keys if k["tunnel"]]
    say("righe che sembrano la chiave del tunnel: %d%s" % (len(tun), (" -> impronta " + tun[0]["fp"]) if len(tun) == 1 else ""))
    say("")
    say("## backup esterno")
    ok, why = ext_backup_ok(a.ext_status, a.max_age_h)
    say("  " + ("OK: " if ok else "NON ANCORA: ") + why)
    say("")
    say("## app e bot (devono restare come sono)")
    for n, s in snapshot().items():
        say("  %s: %s" % (n, json.dumps(s) if s else "assente"))
    say("")
    say("ESITO: " + ("pronto per il ritiro (serve --fingerprint %s)" % tun[0]["fp"] if len(tun) == 1 and g and ok
                     else "NON ancora pronto: vedi sopra"))
    return 0


def final_checks(a, before, key_before, root_auth_hash, removed_fp, retired_name, auth_meta):
    problems = []

    def check(cond, ok_msg, bad_msg):
        say(("  OK     " if cond else "  ERRORE ") + (ok_msg if cond else bad_msg))
        if not cond:
            problems.append(bad_msg)

    g = inspect(retired_name)
    check(g is not None and not g["State"]["Running"] and (g["HostConfig"]["RestartPolicy"] or {}).get("Name") in ("no", ""),
          "container ritirato fermo e senza riavvio automatico (%s)" % retired_name,
          "il container ritirato risulta ancora attivo o con riavvio automatico")
    check(inspect(GATEWAY) is None, "nessun container con il nome %s" % GATEWAY, "esiste ancora un container %s" % GATEWAY)
    check(not listening_18002(), "nessun ascolto su 127.0.0.1:18002", "qualcosa ascolta ancora su 127.0.0.1:18002")
    keys = parse_auth(a.auth)
    check(not any(k["tunnel"] for k in keys), "nessuna riga del tunnel in authorized_keys", "resta una riga del tunnel")
    before_set = {k["fp"] for k in key_before}
    after_set = {k["fp"] for k in keys}
    check(after_set == before_set - {removed_fp} and len(keys) == len(key_before) - 1,
          "authorized_keys: tolta solo la chiave del tunnel, le altre %d intatte" % len(keys),
          "authorized_keys cambiato oltre la sola chiave del tunnel")
    st = os.stat(a.auth)
    check((st.st_mode & 0o777, st.st_uid, st.st_gid) == auth_meta,
          "permessi e proprietario di authorized_keys invariati", "permessi/proprietario di authorized_keys cambiati")
    if a.root_auth and root_auth_hash is not None:
        check(file_hash(a.root_auth) == root_auth_hash, "authorized_keys di root non toccato",
              "authorized_keys di root cambiato")
    check(health_ok(), "l'app risponde (http://127.0.0.1:8002/api/health)", "l'app NON risponde")
    after = snapshot()
    for n, s in before.items():
        if s is None:
            continue
        t = after.get(n)
        same = bool(t) and t["id"] == s["id"] and t["restarts"] == s["restarts"] and t["running"] == s["running"] \
            and t["started"] == s["started"]
        check(same, "%s invariato (stesso container, nessun riavvio)" % n, "%s e' cambiato durante il ritiro" % n)
    for n in container_names():
        if n.startswith(ROLLBACK_PREFIX):
            check(True, "container di rollback intatto: %s" % n, "")
    return problems


def file_hash(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def cmd_retire(a):
    say("## RITIRO DEL PONTE")
    if not a.fingerprint or not FP_RE.match(a.fingerprint):
        say("ERRORE: serve --fingerprint SHA256:... (quello stampato dal controllo iniziale)")
        return 1
    ok, why = ext_backup_ok(a.ext_status, a.max_age_h)
    say("backup esterno: " + why)
    if not ok:
        say("ERRORE: il ritiro parte solo dopo il primo backup esterno verificato.")
        return 1
    g = inspect(GATEWAY)
    if g is None:
        say("ERRORE: il container %s non esiste (gia' ritirato?)" % GATEWAY)
        return 1
    keys = parse_auth(a.auth)
    cand = [k for k in keys if k["tunnel"] and k["fp"] == a.fingerprint]
    if len(cand) != 1:
        say("ERRORE: attesa UNA riga del tunnel con impronta %s, trovate %d. Non tocco niente." % (a.fingerprint, len(cand)))
        return 1
    if not health_ok():
        say("ERRORE: l'app non risponde gia' prima del ritiro: non e' il momento di cambiare altro.")
        return 1
    before = snapshot()
    root_hash = file_hash(a.root_auth) if a.root_auth else None
    st = os.stat(a.auth)
    auth_meta = (st.st_mode & 0o777, st.st_uid, st.st_gid)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    bdir = os.path.join(a.backup_root, "ponte-" + stamp)
    os.makedirs(bdir, mode=0o700)
    shutil.copy2(a.auth, os.path.join(bdir, "authorized_keys.before"))
    os.chmod(os.path.join(bdir, "authorized_keys.before"), 0o600)
    with open(os.path.join(bdir, "removed-line.txt"), "w") as f:
        f.write(cand[0]["raw"] + "\n")
    os.chmod(os.path.join(bdir, "removed-line.txt"), 0o600)
    gsum = summary(g)
    with open(os.path.join(bdir, "gateway.json"), "w") as f:
        json.dump({"nome": GATEWAY, "fotografia": gsum, "baseline": before,
                   "chiave_rimossa": {"impronta": cand[0]["fp"], "riga": cand[0]["lineno"]}}, f, indent=1)
    say("copia di sicurezza in %s (authorized_keys, riga tolta, fotografia del container)" % bdir)

    retired = "%s-retired-%s" % (GATEWAY, time.strftime("%Y%m%d"))
    if retired in container_names():
        retired += "-" + time.strftime("%H%M%S")
    for cmd in (["docker", "update", "--restart=no", GATEWAY],
                ["docker", "stop", "--time", "20", GATEWAY],
                ["docker", "rename", GATEWAY, retired]):
        rc, out = sh(cmd, timeout=90)
        say("  %s -> %s" % (" ".join(cmd), "ok" if rc == 0 else "ERRORE " + out[:200]))
        if rc != 0:
            say("ERRORE: interrotto: rimetto il ponte com'era.")
            return auto_restore(a, bdir)
    # riga della chiave: solo quella, scrittura atomica con gli stessi permessi
    with open(a.auth) as f:
        lines = f.read().split("\n")
    remove_idx = cand[0]["lineno"] - 1
    if lines[remove_idx].rstrip("\n") != cand[0]["raw"]:
        say("ERRORE: authorized_keys e' cambiato nel frattempo. Interrotto prima di toccarlo: rimetto il ponte com'era.")
        return auto_restore(a, bdir)
    new = lines[:remove_idx] + lines[remove_idx + 1:]
    tmp = a.auth + ".new-%d" % os.getpid()
    with open(tmp, "w") as f:
        f.write("\n".join(new))
    os.chmod(tmp, auth_meta[0])
    try:
        os.chown(tmp, auth_meta[1], auth_meta[2])
    except PermissionError:
        pass
    os.replace(tmp, a.auth)
    say("  tolta da authorized_keys la riga %d (impronta %s)" % (cand[0]["lineno"], cand[0]["fp"]))

    say("")
    say("## CONTROLLO FINALE")
    problems = final_checks(a, before, keys, root_hash, cand[0]["fp"], retired, auth_meta)
    say("")
    if problems:
        say("RISULTATO: FALLITO (%d problemi): rimetto il ponte com'era." % len(problems))
        auto_restore(a, bdir)
        return 1
    say("RISULTATO: OK. Ponte ritirato (container fermo e rinominato %s, chiave del tunnel tolta). "
        "Nessun dato, backup o container di rollback cancellato." % retired)
    return 0


def auto_restore(a, bdir):
    """Ritorno automatico dopo un ritiro andato male. Esce sempre con 1: il ritiro NON e' riuscito."""
    a.from_dir = os.path.basename(bdir)
    cmd_restore(a)
    return 1


def cmd_restore(a):
    say("## RIPRISTINO DEL PONTE")
    dirs = sorted(d for d in os.listdir(a.backup_root) if d.startswith("ponte-")) if os.path.isdir(a.backup_root) else []
    if a.from_dir:
        dirs = [a.from_dir]
    if not dirs:
        say("ERRORE: nessuna copia di sicurezza ponte-* in %s" % a.backup_root)
        return 1
    bdir = os.path.join(a.backup_root, dirs[-1])
    with open(os.path.join(bdir, "gateway.json")) as f:
        meta = json.load(f)
    with open(os.path.join(bdir, "removed-line.txt")) as f:
        line = f.read().rstrip("\n")
    say("uso la copia %s" % bdir)
    sp = split_line(line)
    if sp is None:
        say("ERRORE: la riga salvata non e' leggibile")
        return 1
    fp = fingerprint(sp[1], sp[2])
    current = parse_auth(a.auth)
    if any(k["fp"] == fp for k in current):
        say("  la chiave %s e' gia' in authorized_keys: non la riaggiungo" % fp)
    else:
        with open(a.auth, "rb") as f:
            old = f.read()
        with open(a.auth, "ab") as f:
            f.write((b"\n" if old and not old.endswith(b"\n") else b"") + (line + "\n").encode())
        say("  riaggiunta la riga della chiave %s" % fp)
    retired = sorted(n for n in container_names() if n.startswith(GATEWAY + "-retired-"))
    if inspect(GATEWAY) is None and retired:
        rc, out = sh(["docker", "rename", retired[-1], GATEWAY])
        say("  rinominato %s -> %s: %s" % (retired[-1], GATEWAY, "ok" if rc == 0 else out[:200]))
        if rc != 0:
            return 1
    if inspect(GATEWAY) is None:
        say("ERRORE: container %s non trovato" % GATEWAY)
        return 1
    policy = (meta.get("fotografia") or {}).get("restart_policy") or "unless-stopped"
    for cmd in (["docker", "update", "--restart=" + policy, GATEWAY], ["docker", "start", GATEWAY]):
        rc, out = sh(cmd, timeout=60)
        say("  %s -> %s" % (" ".join(cmd), "ok" if rc == 0 else out[:200]))
        if rc != 0:
            return 1
    g = inspect(GATEWAY)
    ok = bool(g and g["State"]["Running"])
    say("RISULTATO: %s" % ("OK, ponte ripristinato" if ok else "FALLITO: il container non e' in esecuzione"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("check", "retire", "restore"))
    ap.add_argument("--auth", default="/home/ubuntu/.ssh/authorized_keys")
    ap.add_argument("--root-auth", default="/root/.ssh/authorized_keys")
    ap.add_argument("--ext-status", default="/opt/superbot-extbackup/status.json")
    ap.add_argument("--max-age-h", type=float, default=36.0)
    ap.add_argument("--backup-root", default="/opt/superbot-backups")
    ap.add_argument("--fingerprint", default="")
    ap.add_argument("--from-dir", default="")
    a = ap.parse_args(argv)
    return {"check": cmd_check, "retire": cmd_retire, "restore": cmd_restore}[a.command](a)


if __name__ == "__main__":
    sys.exit(main())
