# SuperBot F0 — 2026-11-03 — collegamento GitHub↔VPS limitato, PR #30 DRAFT

## Mandato
Utente: «ok procediamo» per ridurre lavoro manuale su Termius e rendere leggibili da ChatGPT i risultati di diagnostica della VPS. Questo mandato NON implica autorizzazione a riavviare trade, migrare V3, ripristinare la connessione root di vecchi workflow, azzerare wallet o fare merge su main.

## Lavoro eseguito su GitHub, non sul server
- Creato ramo dedicato `work/f0-restricted-remote-diagnostics-20261103` da `main`, **separato** dalla V3 PR #29.
- Aperta [PR #30](https://github.com/alexiptv82/SuperBot-Trading/pull/30) in stato DRAFT.
- `ops/f0/restricted_status.py`: probe fisso non-root, solo stat di percorsi noti Brain/Hawk/Bull, conteggi sintetici servizi/processi. Non legge contenuti, database, segreti o comandi passati via SSH; rifiuta EUID root e segnala sempre `OBSERVATION_ONLY`, mai F0 certificato.
- `ops/f0/provision_account.sh`: richiede operatore root *una sola volta* tramite Termius, crea utente sistema `superbot-f0` senza sudo/Docker e installa comando root-owned; non crea chiavi.
- `ops/f0/install_public_key.sh`: accetta soltanto chiave ed25519 pubblica valida e la vincola in `authorized_keys` con `restrict,command="/usr/local/libexec/superbot-f0-status"`. Nessuna shell remota libera consentita con quella chiave.
- `.github/workflows/f0-restricted-status.yml`: esecuzione manuale e pianificazione giornaliera solo dopo merge indipendente sulla branch default, senza checkout, uso nuovo secret `SUPERBOT_F0_SSH_PRIVATE_KEY` e host ed25519 pinned, output JSON.
- `.github/workflows/f0-restricted-tests.yml`: nessun secret/SSH; Python unittest e Bash lint.
- Runbook `ops/f0/README.md`: impronta host attesa, PINNED_COMMIT per installare, creazione nuova chiave SSH senza condividere privata in chat, gestione secret GitHub e gate di attivazione.

## Evidenza CI
GitHub Actions [run #41576404958](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41576404958): **SUCCESS, Ran 8 tests, OK**, Bash syntax checks.
L'ultima versione codice sulla PR è commit `6931d84bed3867a9f773d22744795c9f5dd5c950` (verificare eventuali commit successivi prima di usare ref pinned).

## Stato reale
- Nessun accesso SSH alla VPS effettuato da ChatGPT, nessun utente `superbot-f0` creato dal modello sulla macchina, nessun secret GitHub inserito.
- Nuovo workflow NON attivo su default branch (PR DRAFT). Per funzionare occorrono prova chiave host via Termius, provision operatore, chiave ed25519 dedicata in GitHub Secret e merge separato dopo test.
- La chiave root legacy Singapore resta presente in altri workflow esistenti e **non è stata revocata**. È da migrare con piano dedicato evitando interruzione della sentinella backup.
- Storico Brain F0: copia locale WAL-consistente sul VPS verificata 8447 eventi al 2026-11-03 04:55, ma **non** certificata off-host; backup originale, WAL, SHM e classici non toccati da questo lavoro.

## Passo successivo
Chiedere all'utente un'unica verifica iniziale tramite Termius della fingerprint della chiave host ed25519 `SHA256:bocotz2mKh8rI/hgsqIUArcq8l8933UP0QWnwfaLrfs`, quindi installazione pin-digest e nuovo account (intervento da autorizzare). La chiave privata non deve transitare nella chat; inserire direttamente nei Secret di GitHub. Dopo first remote read-only job con prova SSH negative, ChatGPT può leggere autonomamente log da GitHub. Nessun deploy V3/merge PR #29 in questa fase.
