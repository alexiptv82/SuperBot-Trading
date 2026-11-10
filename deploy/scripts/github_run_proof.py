#!/usr/bin/env python3
"""Prova AUTENTICA che una riga CERTIFICATO viene davvero da una run di GitHub Actions (solo lettura, solo API pubbliche, nessun token).

Una riga CERTIFICATO copiata a mano e' solo testo: chiunque puo' scriverne una uguale. Questo modulo la confronta con quello che GitHub
stesso dichiara, interrogando le API pubbliche del repository (che e' pubblico; non si invia nessuna credenziale):

  1. la run `run_id` esiste, e' completata con successo, ed e' stata eseguita sul commit indicato nel certificato (`commit`), in questo
     stesso repository (non un fork), per il workflow giusto, con evento push/workflow_dispatch e dal ramo atteso;
  2. i file del workflow e dello script, letti da GitHub AL COMMIT della run, hanno gli SHA-256 dichiarati nel certificato (e attesi
     dall'installatore): la run ha eseguito il codice rivisto, non uno modificato;
  3. tutti i job di quella run sono andati a buon fine;
  4. un'ANNOTAZIONE del job (titolo CERTIFICATO), creata dal workflow nella run, contiene un testo identico al certificato: il contenuto
     e' quello prodotto dalla run, non scritto a mano.

Limite dichiarato: non prova chi abbia premuto il pulsante (l'ambiente protetto `age-recovery` con revisore obbligatorio serve a
quello) ne' che il Secret fosse quello giusto; prova che quel codice, a quel commit, ha concluso con successo e ha emesso quel testo.
Se l'API non e' raggiungibile o risponde in modo imprevisto, il risultato e' "non verificato" (mai "verificato").
"""
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request

MAX_BYTES = 4 * 1024 * 1024
API_VERSION = "2022-11-28"


class ProofError(Exception):
    pass


def http_get(url, accept="application/vnd.github+json", allow_http=False, timeout=30):
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" and not (allow_http and u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost")):
        raise ProofError("indirizzo non ammesso (serve https)")
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "superbot-certificate-check",
                                               "X-GitHub-Api-Version": API_VERSION})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise ProofError("GitHub ha risposto %d" % e.code)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ProofError("GitHub non raggiungibile (%s)" % type(e).__name__)
    if len(data) > MAX_BYTES:
        raise ProofError("risposta troppo grande")
    return data


def get_json(url, **kw):
    try:
        return json.loads(http_get(url, **kw).decode("utf-8"))
    except ValueError:
        raise ProofError("risposta non valida")


def verify(cert, api_base, repo, expect, allow_http=False):
    """Lista dei problemi (vuota = la run di GitHub conferma il certificato).

    expect: {"workflow_path", "script_path", "workflow_sha256", "script_sha256", "branches"}"""
    bad = []
    run_id, commit, attempt = str(cert.get("run_id", "")), str(cert.get("commit", "")), str(cert.get("run_attempt", ""))
    if not re.fullmatch(r"\d{5,20}", run_id):
        return ["il certificato non indica il numero della run"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        return ["il certificato non indica il commit su cui e' girata la run (certificato di una versione senza prova verificabile)"]
    if not re.fullmatch(r"\d{1,3}", attempt):
        return ["il certificato non indica il tentativo della run"]
    if cert.get("repository") != repo:
        return ["il certificato riguarda un altro repository"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        return ["nome del repository non valido"]
    base = api_base.rstrip("/") + "/repos/" + repo

    def get(path, **kw):
        return get_json(base + path, allow_http=allow_http, **kw)

    try:
        run = get("/actions/runs/" + run_id)
        if str(run.get("id")) != run_id:
            bad.append("GitHub non riconosce la run %s" % run_id)
            return bad
        if str(run.get("run_attempt")) != attempt:
            bad.append("il tentativo della run non coincide con quello del certificato")
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            bad.append("la run non e' conclusa con successo (stato %s / esito %s)" % (run.get("status"), run.get("conclusion")))
        if run.get("head_sha") != commit:
            bad.append("la run e' stata eseguita su un commit diverso da quello del certificato")
        if run.get("event") not in ("push", "workflow_dispatch"):
            bad.append("evento della run non ammesso (%s)" % run.get("event"))
        if run.get("head_branch") not in expect["branches"]:
            bad.append("la run non e' partita da un ramo atteso (%s)" % run.get("head_branch"))
        if (run.get("path") or "").split("@")[0] != expect["workflow_path"]:
            bad.append("la run e' di un altro workflow (%s)" % (run.get("path") or "?").split("@")[0])
        for key in ("repository", "head_repository"):
            if (run.get(key) or {}).get("full_name") != repo:
                bad.append("la run non appartiene a questo repository (%s)" % key)
        for path, want, label in ((expect["workflow_path"], expect["workflow_sha256"], "workflow"),
                                  (expect["script_path"], expect["script_sha256"], "script")):
            body = http_get(base + "/contents/" + urllib.parse.quote(path) + "?ref=" + commit,
                            accept="application/vnd.github.raw", allow_http=allow_http)
            if hashlib.sha256(body).hexdigest() != want:
                bad.append("il %s al commit della run non e' quello rivisto (SHA-256 diverso)" % label)
        jobs = get("/actions/runs/%s/attempts/%s/jobs?per_page=100" % (run_id, attempt)).get("jobs") or []
        if not jobs or any(j.get("conclusion") != "success" for j in jobs):
            bad.append("non tutti i job della run sono andati a buon fine")
        seen = False
        for j in jobs:
            ann = get("/check-runs/%s/annotations?per_page=100" % j.get("id"))
            for x in ann if isinstance(ann, list) else []:
                if x.get("title") == "CERTIFICATO":
                    try:
                        if json.loads(x.get("message", "")) == cert:
                            seen = True
                    except ValueError:
                        pass
        if not seen:
            bad.append("nessuna annotazione CERTIFICATO della run coincide con il certificato (testo scritto altrove o modificato)")
    except ProofError as e:
        bad.append("prova non verificabile: %s" % e)
    return bad
