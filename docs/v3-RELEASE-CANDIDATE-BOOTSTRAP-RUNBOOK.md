# SuperBot V3 — bootstrap PAPER separato (non eseguito su VPS)

Stato al 6 novembre 2026: PR #62 Release Candidate. Questa procedura è **documentazione di preparazione**; non è un'autorizzazione al deploy o all'avvio.

## Stato server verificato in sola lettura

- `superbot` web attivo in PAPER; Falco/Toro e vecchi container Brain fermati e con pause flag.
- Falco ha **6** posizioni registrate aperte; Toro **2**: sono storico PAPER da preservare, non da chiudere automaticamente.
- Il vecchio Brain conserva `/opt/superbot-desk-data/brain/brain.sqlite3`, NON il nuovo `journal.db` V3.
- Backup protetto salvato in `/opt/superbot-backups/rc-v3-20261106T150730Z` (tarball storici leggibili e copie SQLite con integrity_check OK). Prima del cutover, verificare uno snapshot aggiornato e recuperabilità.

## Gate capitale e run

Non usare implicitamente il valore di esempio nel file di configurazione. Il `runner_config.json` della PR #57 imposta `initial_equity=1000`, mentre in precedenti discussioni Brain era previsto con **2.000 USDT**. Richiedere il capitale esatto approvato per ogni portafoglio (Falco 1.000, Toro 1.000; Brain 1.000 oppure 2.000) e usare file di configurazione coerenti.

## Bootstrap di una run Brain V3 completamente nuova

Solo **dopo consenso di avvio, backup verificato e scelta capitale**, un operatore può usare il modulo `backend.v3.runner.bootstrap_paper`. Non è un servizio e non apre trade. Crea una cartella **prima inesistente** (errore se esiste), un journal V3 con evento `paper_run_initialized`, un budget SQLite, una ricevuta, `mandate.json` predefinito **NON approvato** e `pause.flag` presente. Verifica che l'equity dichiarata coincida con la configurazione. Non legge, migra, azzera o modifica i vecchi dati.

Esempio illustrativo, NON eseguire adesso:

```sh
DESK_MODE=paper python -m backend.v3.runner.bootstrap_paper \
  --data-dir /percorso/nuova-run-brain-v3 \
  --run-id brain-v3-20261106-001 \
  --config /percorso/config-approvato.json \
  --expected-initial-equity 2000 \
  --create-paper
```

Il numero `2000` è **solo illustrativo**. Deve coincidere con la configurazione definitivamente approvata. Dopo il bootstrap, prima di attivare il Brain: verificare `check_existing_data`, mandati, ownership unica EXIT, heartbeat del sidecar, controlli di perdita, pause, API UI e backup della nuova run. Il primo avvio dovrebbe avvenire con `pause.flag` presente, poi solo dopo verifica operativa e consenso esplicito togliere la pausa. Il CLI legacy non deve avviare EXIT insieme al sidecar.

## Falco e Toro

Non eseguire `docker start` sui vecchi container con 6+2 posizioni ancora registrate. È necessario un piano separato di run nuove per i classici, con directory e capitale indipendenti. Conservare i vecchi stati read-only per rendicontazione; l'app deve distinguere storico vecchio da run nuova. Nessuna chiusura forzata a mezzanotte, nessuna cancellazione o sovrascrittura dello storico.

## Perché ancora NO-GO

Il bootstrap risolve **solo** la lacuna del journal Brain V3 al primo avvio. Restano da verificare il montaggio reale del sidecar e il monitor durante guasti, l'unicità del proprietario OPEN/CLOSE, la UI delle tre run e il rollback. La CI di GitHub è verde sul ramo RC, ma non certifica un deploy VPS.