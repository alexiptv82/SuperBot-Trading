# SuperBot F0 — Collegamento automatico GitHub ↔ VPS, account limitato

**Stato al 2026-11-03:** collegamento GitHub Actions → VPS verificato in sola lettura (run [41596313485](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41596313485), `success`). Il sistema continua a consentire soltanto un comando diagnostico fisso. La copia Brain F0 verificata è ancora solo locale; F0 off-host non è certificato.

Questa integrazione non sostituisce Termius: lo riduce a una **configurazione iniziale**, e poi rende leggibili in GitHub Actions i risultati di diagnostica della VPS. Il primo livello consente solo **lettura di metadati** (dimensioni dei file e stato sintetico dei processi); non può fare backup, restart, reset, trade, installazioni, modifiche all'AI o consultare contenuti/segreti. La certificazione F0 del backup fuori VPS resta un gate separato.

## Architettura di sicurezza

- Account OS dedicato `superbot-f0`, non-root, senza `sudo` né accesso al gruppo Docker.
- `authorized_keys`: una chiave SSH nuova, *esclusivamente per questa automazione*, con `restrict,command="/usr/local/libexec/superbot-f0-status"`. Questo comando non deve essere scrivibile dall'account e deve essere posseduto da root.
- La diagnostica Python `ops/f0/restricted_status.py` installata come comando root-owned. Stampa soltanto JSON limitato, mai contenuto file o argv di processi.
- Workflow `.github/workflows/f0-restricted-status.yml`: `workflow_dispatch` e controllo giornaliero, senza checkout del repository e con token `contents: read`, SSH host key ed25519 pinned, `BatchMode=yes`, nessun forwarding.
- Chiave **privata** esclusivamente in GitHub Actions Secret `SUPERBOT_F0_SSH_PRIVATE_KEY`. **MAI in commit, chat, screenshot, diario o output di console pubblicato.**
- Workflow attivo solo dopo revisione e merge dedicato nella branch predefinita, **senza** eseguire merge della PR V3 #29. Richiesto controllo della protezione di `main` prima di esporre un secret a workflow.
- I vecchi workflow che usano la chiave root Singapore NON vengono cancellati o modificati in questo cambiamento. Pianificare rotazione/limitazione senza rompere backup o sentinelle.

## Passaggio iniziale A — Revisione prima dell'installazione

1. Revisionare i file di questa PR e i risultati di `f0-restricted-tests.yml`, che non richiede secrets.
2. Confermare sul server, **con Termius**, la chiave host:
   `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256`.
   L'impronta attesa per la chiave pubblica SSH già pinned nei vecchi workflow è
   `SHA256:bocotz2mKh8rI/hgsqIUArcq8l8933UP0QWnwfaLrfs`.
   **Se differisce, fermarsi** e verificare con l'amministratore; non usare `StrictHostKeyChecking=no`.
3. Proteggere la branch di destinazione con review obbligatoria per cambi a `.github/workflows/**`; evitare accessi di scrittura non necessari.

## Passaggio iniziale B — installazione una tantum (Termius, solo dopo revisione)

I file da installare sul server sono `ops/f0/restricted_status.py`,
`ops/f0/provision_account.sh` e `ops/f0/install_public_key.sh`.

Scaricarli da uno **specifico commit SHA completo revisionato**, mai da `main`, HEAD o dal ramo V3 mutabile. Conservarli temporaneamente fuori dalle directory del bot, controllare la revisione/digest e usare `bash -n` prima di eseguire lo script. Comandi di riferimento, con `PINNED_COMMIT` sostituito dal commit revisionato:

```bash
set -e
install -d -m 0700 /root/superbot-f0-setup
cd /root/superbot-f0-setup
BASE="https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/PINNED_COMMIT/ops/f0"
curl -fsSLo restricted_status.py "$BASE/restricted_status.py"
curl -fsSLo provision_account.sh "$BASE/provision_account.sh"
curl -fsSLo install_public_key.sh "$BASE/install_public_key.sh"
bash -n provision_account.sh
bash -n install_public_key.sh
python3 -m py_compile restricted_status.py
# Confrontare SHA256/file con la revisione approvata prima di procedere
bash provision_account.sh restricted_status.py
```

`provision_account.sh` rifiuta di procedere se un account omonimo o il comando già esistono: questo è intenzionale, **non** forzare la rimozione di account/file esistenti.

Si può generare la **nuova** chiave SSH da un dispositivo personale affidabile ed esportare soltanto il file pubblico sul server. Se si usa Termius sul server per generare una chiave temporanea, attenzione: la chiave privata non va inviata a ChatGPT né catturata con uno screenshot.

Dopo aver generato la coppia ed25519, registrare sul server **solo il file pubblico**:

```bash
bash /root/superbot-f0-setup/install_public_key.sh /PERCORSO/NUOVA_CHIAVE.pub
```

Il comando aggiunge `restrict,command=\"/usr/local/libexec/superbot-f0-status\"` al file `authorized_keys` dell'utente nuovo. Testare con account non-root che il comando remoto non dia shell e che i permessi su `/usr/local/libexec/superbot-f0-status` siano `root:root 755`.

## Passaggio iniziale C — GitHub Actions Secret

Con l'interfaccia GitHub del repository, creare il secret **`SUPERBOT_F0_SSH_PRIVATE_KEY`** incollando la chiave privata dal dispositivo sicuro **direttamente in GitHub**, non in ChatGPT. Percorso GitHub: repository → Settings → Secrets and variables → Actions → New repository secret.

Non usare `SINGAPORE_SSH_PRIVATE_KEY` e non riutilizzare la chiave di Termius personale. Dopo aver verificato il secret, eliminare in modo appropriato eventuali copie temporanee della chiave privata su server e dispositivo, secondo la procedura operativa scelta. GitHub Actions non permette di rileggere in chiaro un secret dopo la creazione.

## Passaggio D — attivazione controllata

Solo dopo la conferma dell'account, host key e secret, approvare separatamente il merge della **sola PR di diagnostica F0**. Il workflow apparirà tra le Actions della branch principale; eseguire una volta `workflow_dispatch`. Il risultato mostrerà un JSON `OBSERVATION_ONLY`, non un certificato di backup. Un controllo quotidiano userà la stessa identità senza ulteriori operazioni da Termius; i risultati saranno consultabili da ChatGPT tramite GitHub.

**Test negativo obbligatorio:** cercare di eseguire una shell con la chiave F0 deve fallire/essere sostituito dal comando forzato; tentativi di forwarding e PTY devono essere rifiutati. Non usare il secret per eseguire comandi o Python di GitHub arbitrari.

## Limitazioni operative

La diagnostica può restituire `UNAVAILABLE` se le cartelle storiche non concedono permesso di attraversamento alla nuova identità. **Non** dare permessi globali ai dati, non mettere F0 nel gruppo Docker e non modificare ACL a intuito. Se succede, definire puntualmente le ACL dei soli percorsi necessari prima di richiedere una modifica separata.

Questo schema evita di consegnare a ChatGPT accesso SSH generico alla VPS: ChatGPT può mantenere il codice e leggere i risultati della diagnostica GitHub, mentre il server rifiuta qualsiasi azione diversa dal comando già approvato. Per eseguire backup reali occorrerà una seconda funzionalità separata con limiti e autorizzazioni specifici.


## Recovery for Android/Termius private-key line endings (2026-11-03)

If the initial GitHub job reports `Load key "...id_ed25519": error in libcrypto`, the private key in GitHub is malformed or was pasted without correct newline boundaries. The workflow supports both normal PEM/OpenSSH multiline text and a one-line **`F0B64:`** transport format. This prefix is NOT a public key; it contains the private key encoded as Base64.

On the **VPS Termius root session where the new, dedicated F0 GitHub key was created**, after checking the local private key is present with `ssh-keygen -y -P '' -f /root/superbot-f0-setup/github-f0-ed25519 >/dev/null`, run the command below. **The one-line output is a secret, equivalent to the full private key; never screenshot or paste it into chat, a GitHub Issue/PR, or a terminal log shared with anyone.**

```bash
printf 'F0B64:'
base64 -w0 /root/superbot-f0-setup/github-f0-ed25519
printf '\n'
```

Copy the **whole line** starting `F0B64:` and paste it **only into** GitHub → repository Settings → Secrets and variables → Actions → edit `SUPERBOT_F0_SSH_PRIVATE_KEY`. No trailing spaces or line breaks are needed; the workflow will restore the original bytes in an ephemeral file, validate its OpenSSH header/footer and parse it without printing the key.

After the merge of this patch, re-run the failing GitHub Actions diagnostic job and verify its `F0_KEY_PARSE_PASS` followed by a JSON `OBSERVATION_ONLY`. When functional, handle the temporary private-key file on the VPS with an explicit cleanup procedure; until then, keep `/root/superbot-f0-setup` restricted `0700` and never transmit the private key in chat. Do not revoke the already-used Termius account key.

The Base64 format is **encoding, not encryption**. The output is sensitive and must only be entered in GitHub Actions Secrets.


## Hawk/Bull: diagnostica metadati con ACL minima (separata, NON applicata)

L'esecuzione remota F0 riuscita mostra le directory `/opt/superbot-desk-data/hawk` e `bull` come `PRESENT`, ma gli `state_v2.json`, `trade_history.jsonl`, `learning_log.jsonl`, `lessons.md` e la directory `archive` come `UNAVAILABLE` per `superbot-f0`. I precedenti controlli locali root li avevano individuati. Questo è **un limite di accessibilità**, non evidenza di perdita dati.

Il probe F0 usa soltanto `stat()`: per conoscere l'esistenza e le dimensioni di un file non è necessario concedere lettura del suo contenuto. Serve permesso di attraversamento (`--x`) sulla directory immediatamente superiore. Non servono `chmod 777`, gruppi Docker, `sudo` o accesso root via SSH.

È stato preparato `ops/f0/classic_metadata_acl.sh`, per una **sola esecuzione locale sotto controllo operatore** e con queste proprietà:
- Default `--check`: controllo in sola lettura, nessun cambio di ACL.
- `--apply` solo su **esplicita autorizzazione**: concede soltanto `user:superbot-f0:--x` alle due directory precise `/opt/superbot-desk-data/{hawk,bull}`, lasciando i permessi dei file invariati.
- Prima dell'applicazione: verifica che i percorsi non siano symlink, che i quattro file essenziali e `archive` esistano, che il nuovo account non abbia gruppi privilegiati e che un eventuale ACL mask non debba essere ampliato.
- Salva un testimone ACL originale in `/root/superbot-f0-setup/acl-before-hawk-bull.*` (file `0600`, directory `0700`). Se il controllo successivo fallisce, tenta il ripristino automatico di entrambe le ACL.
- Rifiuta di procedere se non sono installati `getfacl` e `setfacl`. Non installa pacchetti.
- Non cambia file di trading, DB, backup, WAL, container, bot o crontab.
- Il controllo manuale successivo può essere un rerun del job GitHub F0; non occorre inviare screenshot della VPS.

Per provarlo **solo dopo revisione della PR**, scaricare da un **commit SHA specifico e verificato**, mai un branch mutevole, e lanciare inizialmente esclusivamente `--check`. Esempio per Termius root:

```bash
# Sostituire il segnaposto con il commit SHA approvato dal revisore:
REF="COMMIT_SHA_REVISIONATO"
curl -fsSLo /root/superbot-f0-setup/classic_metadata_acl.sh \
  "https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/$REF/ops/f0/classic_metadata_acl.sh"
bash -n /root/superbot-f0-setup/classic_metadata_acl.sh
bash /root/superbot-f0-setup/classic_metadata_acl.sh --check
```

**Non eseguire `--apply` per il solo fatto di aver scaricato il file.** Il risultato del preflight non è una certificazione dello storico. Anche dopo l'ACL, il collegamento rimane diagnostico e **non può acquisire, esportare o leggere il contenuto** dei file Falco/Toro: per la certificazione F0 servono uno snapshot in ambiente autorizzato, copia cifrata off-host e restore verificato.
