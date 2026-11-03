# SuperBot F0 — Prima esecuzione GitHub SSH diagnostica fallita alla lettura chiave (2026-11-03)

## Fonte verificata
Run GitHub Actions https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41582026933, generato dall'utente con workflow_dispatch su `main` il 3 novembre 2026 alle 05:07:23 UTC. Il run è stato completato con `conclusion=failure` nel job `status`.

Dal log del job 125738820686:
```
Load key "/tmp/tmp.********/id_ed25519": error in libcrypto
Process completed with exit code 255.
```
Il passo fallisce sul comando `ssh-keygen -y -f id_ed25519`, **prima di eseguire ssh**. Non si è ancora provata autenticazione verso la VPS, forced-command o accesso diagnostico. Il secret `SUPERBOT_F0_SSH_PRIVATE_KEY` era presente come variabile mascherata (`***`) nel job, ma il suo contenuto non viene letto da ChatGPT. L'errore è compatibile con chiave privata OpenSSH incompleta, non valida, in formato non corretto o con righe corrotte.

## Conseguenze e correzione richiesta
1. L'utente deve aggiornare **direttamente su GitHub** il repository secret `SUPERBOT_F0_SSH_PRIVATE_KEY` con il testo integrale della chiave privata ED25519 in formato OpenSSH, preservando BEGIN/END, righe reali e newline finale, senza inviarla in chat o allegarla in screenshot.
2. NON sostituire con la chiave pubblica `ssh-ed25519 ...`, né con PPK/JSON/singola riga.
3. Rilanciare il workflow da Actions → SuperBot F0 - restricted VPS status → Run workflow → main. ChatGPT può leggere il log quando disponibile.
4. Se Termius non fornisce un'esportazione OpenSSH utilizzabile, creare una nuova coppia in un ambiente fidato, aggiungere **solo la nuova chiave pubblica** a `superbot-f0` e sostituire il secret in GitHub, senza esporre private keys.
5. Se permane l'errore valutare revisione tecnica del workflow per normalizzazione CRLF e diagnostica booleana senza stampa di segreti.

## Perimetro
PR #30 merged su main (`281dff50...`). PR V3 #29 DRAFT, non mergiata. Nessun comando arrivato alla VPS nel run F0, nessun bot riavviato, nessun reset, nessun import storico, nessun backup offhost certificato. Non dichiarare la connessione attiva finché il workflow non restituisce un JSON `OBSERVATION_ONLY`.
