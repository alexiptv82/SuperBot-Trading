# SuperBot F0 — Collegamento automatico GitHub ↔ VPS, account limitato

**Stato:** codice pronto per revisione tecnica. Il collegamento NON è ancora installato, la chiave privata GitHub NON è stata configurata e nessun accesso SSH è stato eseguito.

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
