# F0 — confronto di metadati backup esterno e snapshot Brain (NON una certificazione)

**Stato:** script di preflight preparato per revisione e test offline. Non installato né eseguito sulla VPS. Nessun backup, trasferimento, restore o verifica di credenziali è stato effettuato da questa PR.

## Scopo

Il vecchio watcher GitHub `.github/workflows/sg-extbackup-watch.yml` ha riferito l'ultimo archivio cifrato `superbot-backup-20261102T032845Z.tar.gz.age` con timestamp 2026-11-02 03:28:45 UTC (run [41447751395](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41447751395)). Separatamente, la copia locale del database Brain di F0 fu creata su VPS il 2026-11-03 intorno alle 03:55 UTC, in `/opt/superbot-v3-backups/f0-brain-20261103T035500Z`, e un controllo locale aveva riportato 8.447 eventi.

**Un archivio che risale al giorno precedente NON può provare di contenere lo snapshot creato dopo.** Una sentinella recente è soltanto un indizio sull'esito del backup, non prova la destinazione off-host, copertura dei dati storici, chiave decrittazione, integrità dell'archivio o restore riuscito. Non si assume assenza di backup più recenti: è necessario osservare lo stato attuale.

## Script

`ops/f0/offhost_preflight.py` è un programma **standalone di sola lettura**. Non importa moduli dei bot, non apre SQLite, non legge il contenuto degli archivi `.age`, non accede a chiavi, non esegue subprocess e non effettua connessioni.

Legge **soltanto** due file con percorso fisso:
- `/opt/superbot-extbackup/status.json` — data dell'ultimo successo, nome archivio solo per validarne il formato, presenza di errore (boolean, senza testo);
- `/opt/superbot-v3-backups/f0-brain-20261103T035500Z/manifest.json` — schema, timestamp, numero eventi, seq massimo, hash del manifesto, coerenza tra osservazioni dichiarate.

Con `O_NOFOLLOW` rifiuta file finali symlink, limita ciascun JSON a 64 KiB, valida i campi e produce un JSON **allowlist** senza stampare contenuti di errore, segreti, percorsi remoti, token o credenziali. I fallimenti sono `UNAVAILABLE`, mai certificazioni positive. L'esecuzione da shell root locale è deliberatamente richiesta per leggere file forse protetti: **NON** è un comando permesso attraverso l'utente SSH `superbot-f0`.

Il campo `archive_newer_than_brain_snapshot` indica **soltanto la cronologia**, non la copertura dell'archivio. Dopo la revisione, il confronto usa la data codificata nel nome dell'archivio, verificata come data di calendario reale; non basta un `ultimo_successo` recente quando il nome è vecchio, assente o impossibile. Se la data nel nome è successiva al successo dichiarato, l'esito cronologico è `UNKNOWN`. Lo strumento apre i file JSON regolari in modo non bloccante per rifiutare anche una FIFO senza attendere. Queste restrizioni non certificano la presenza dei byte. `externally_certified=false`, `restore_verified=false`, `archive_coverage_verified=false`, `external_storage_verified=false` sono **invarianti sempre false** per questo strumento.

## Gate successivi

1. Riesaminare sicurezza e CI; chiedere approvazione distinta all'operatore prima di qualsiasi ispezione live. Eseguire una copia del codice **pinned a commit revisionato** (niente download eseguibile da `main` non fissato), verificare hash e non condividere il JSON raw dell'origine.
2. Se il metadata preflight segnala un backup successivo allo snapshot, **non** dichiarare successo. Certificare invece destinazione realmente esterna, cifratura e accesso alle chiavi, contenuto dei backup per Brain WAL e `hawk/bull` con `archive/*`, `lessons.md`, `learning_log.jsonl`, ed evidenza source-side indipendente.
3. Scaricare/ripristinare su host differente in una cartella isolata e applicare le verifiche di `backend/v3/backup_certification.py` e `backend/v3/f0_classic_certificate.py` della PR #29, con witness esterni. Questa PR #34 **non** crea quelle prove e non trasferisce i dati.
4. Evitare di riutilizzare o ampliare l'accesso SSH legacy root della sentinella. La futura sostituzione con account limitato, se necessaria, richiede approvazioni specifiche e test di sicurezza.

Nessun merge, deploy, reset, avvio, import, modifica ACL o cancellazione è autorizzato da questo preflight. Baseline: 7/7 PASS. Revisione offline successiva: 12 fixture, incluse date incompatibili nel nome e FIFO. Il nuovo esito CI deve essere verificato indipendentemente prima di dichiarare la revisione superata.
