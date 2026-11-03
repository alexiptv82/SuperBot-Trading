# SuperBot F0 — 2026-11-03 — secret F0B64 aggiornato, fresh dispatch necessario

L'utente ha confermato `fatto aggiornato ✅` per GitHub Actions secret `SUPERBOT_F0_SSH_PRIVATE_KEY` dopo merge PR #31 e istruzioni di inserire formato `F0B64:`. Il valore del secret non è accessibile al modello: nessun contenuto privato acquisito.

Verifica effettuata su GitHub: `.github/workflows/f0-restricted-status.yml` su `main` include ramo di decoding `F0B64:`, `workflow_dispatch` e schedule `35 3 * * *` (UTC). PR #31 confermata merged.

La sola esecuzione F0 visibile al momento della verifica è `41582026933`, `head_sha=281dff50ead29b1ca2bfa79772cdf40033698289`, creata prima del merge PR #31, `status=completed`, `conclusion=failure`, `run_attempt=2`. Un **rerun di quel vecchio workflow** riuserebbe il codice/commit originario, che non capisce `F0B64:`, e rischierebbe un falso errore di chiave. NON rilanciare il vecchio job.

Gli strumenti GitHub esposti al modello supportano `rerun_workflow_job` ma NON hanno `workflow_dispatch` remoto per lanciare un job nuovo. Serve quindi una sola esecuzione nuova dall'UI GitHub → Actions → SuperBot F0 - restricted VPS status → Run workflow → main. Successivamente il modello potrà leggere autonomamente i nuovi job/log, diagnosticare parse `F0_KEY_PARSE_PASS` e poi SSH forced-command e JSON `OBSERVATION_ONLY`. Non confondere successo parse con successo collegamento o certificazione offhost.

Stato: **nessuna nuova connessione eseguita; nessun bot, DB, WAL, backup o wallet modificato.**