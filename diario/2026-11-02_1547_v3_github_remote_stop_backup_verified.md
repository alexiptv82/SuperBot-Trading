# 2026-11-02 15:47 Europe/Rome — SuperBot V3: accesso GitHub VPS operativo, tutti i worker fermati

## Evidenza verificata (senza Termius)
È stato creato in `main` il workflow read-only `.github/workflows/v3-vps-inventory.yml` che usa il Secret GitHub `SINGAPORE_SSH_PRIVATE_KEY`, la chiave host ED25519 già fissata dal deploy Singapore, la VPS Singapore e lo script `deploy/scripts/v3-vps-inventory.sh`. Esecuzioni riuscite:
- Inventario originale: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41462639966
- Diagnosi componenti e mount: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41463172097
- Verifica indipendente stop: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41465049997

## Stop approvato ed eseguito
Workflow GitHub `.github/workflows/v3-stop-paper-workers.yml` e script `deploy/scripts/v3-stop-paper-workers.sh` con approvazione esplicita via trigger dedicato. Esecuzione con **SUCCESS**:
https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41464111891

Dai log (UTC 14:40–14:46):
- Falco/Hawk `superbot-desk-hawk`: STOP.
- Toro/Bull `superbot-desk-bull`: STOP.
- `superbot-brain-free`: STOP.
- `superbot-turbo`: STOP.
- `superbot-ai` (AI Shadow): STOP.
- `superbot-sidecar`: STOP.
- `superbot-pool`: già STOP, confermato.
- Tutti i worker hanno **restart policy = no**, confermato con audit indipendente.
- I vecchi container Brain, già spenti, restano spenti (restart=no).
- Dashboard `superbot`: **RUNNING**, in modalità PAPER, non interrotta.
- Pause flag Hawk, Bull, Brain Free: **presenti**.

Contabilità esistente al checkpoint: Falco PAPER 6 posizioni aperte, run_no=8; Toro PAPER 2 posizioni aperte, run_no=7. **Non chiuse né azzerate**: restano registrate nello stato sospeso per manutenzione. Brain Free PAPER paused con 0 posizioni aperte. Pool 291 trade chiusi e un trade simulato aperto, mantenuti.

## Backup
Creato archivio consistente solo dopo arresto dei worker:
`/opt/superbot-v3-backups/20261102T144010Z/worker-data.tar.gz`

Include sette directory worker: superbot-desk-data, superbot-brain-free, superbot-brain-adaptive, superbot-ai-data, superbot-turbo-data, superbot-sidecar-data, superbot-pool-data.
- SHA256SUMS verificato.
- Tar leggibile.
- Estrazione completa in `restore-test` sotto la directory di backup.
- `diff -qr` di tutte e sette le directory: **PASS**.
- PRAGMA integrity_check sulle copie SQLite Brain Free e Pool: **OK**.
- Log: `V3_ALL_WORKERS_STOPPED=YES`, `V3_BACKUP_VERIFIED=YES`, `DASHBOARD=RUNNING`.

**Limite:** questo archivio generale è ancora sulla stessa VPS: backup remoto esterno non certificato in questa operazione. Non condividere l'archivio (può contenere dati/chiavi) su GitHub pubblico. I worker hanno ricevuto SIGTERM e alcuni sono stati forzati a uscire al termine dei 60 s (exit 137): le snapshot dei file sono coerenti dopo stop, non si pretende di recuperare attività che non fosse stata persistita prima.

## Stato SuperBot V3
Richiesta utente: un cervello centrale, DeepSeek AI primaria H24 e Claude consulente, memoria condivisa, selezione strategie adattiva e validata, dashboard unica con controlli manuali, tre portafogli PAPER **da 1000 USDT ciascuno** nella futura nuova run. Storici e vecchie run da preservare integralmente, nessun reset adesso. Prompt di progettazione inviati a due AI esterne: risposte non ancora ricevute. Niente PR merge, release o riavvii fino a nuova autorizzazione.

**Nessuna connessione SSH diretta alla chat:** il collegamento operativo è mediato da workflow GitHub autorizzati, con log consultabili automaticamente via GitHub connector.
