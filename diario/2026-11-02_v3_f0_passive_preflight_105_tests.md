# Checkpoint SuperBot V3 F0 — 2026-11-02 21:15 Europe/Zurich — Preflight passivo VPS

## Mandato
Utente ha scritto «ok procediamo», autorizzando la prosecuzione del lavoro SuperBot V3. PR #29 resta DRAFT. Nessun contatto con la VPS, nessuna connessione SSH o root, nessun cambio di servizi, reset, importazione reale, deploy o merge effettuato in questa sessione.

## Riscontro tecnico su GitHub
- La PR #29 è aperta, in bozza, non integrata. Head sul branch `work/v3-foundations-event-risk-20261102`.
- Nessuna integrazione SSH/VPS a privilegi minimi disponibile in questa sessione. Scartato riuso delle vecchie GitHub Actions root (alcune usate ancora come sentinelle o manutenzione).
- Preflight preparatorio F0: `backend/v3/f0_host_preflight.py`, esclusivamente metadata filesystem e nomi/stato di servizi via Docker/systemd. Non apre database, non legge lezioni, non copia file né modifica processi.
- Controlli: Brain `brain.sqlite3`, sidecar WAL/-SHM/-journal e potenziali file extra di memoria (solo presenza e dimensioni), Falco/Toro `state_v2.json`, trade_history/learning_log, `lessons.md`, cartelle archivi, entry symlink/unsafe.
- Almeno nove test sintetici in `backend/tests/test_v3_f0_host_preflight.py`: assenza worker, worker presente, stato servizi indeterminato, WAL, symlink, file lessons mancante, file extra Brain senza esposizione contenuto.
- GitHub CI **105 PASS su Python 3.10 e 105 PASS su Python 3.11**: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41517886282
- Nuova procedura di verifica preliminare con singolo blocco Termius di comandi read-only e senza download di codice: https://github.com/alexiptv82/SuperBot-Trading/blob/work/v3-foundations-event-risk-20261102/docs/v3/f0-live-preflight-termius-20261102.md
- PR #29 e README V3 aggiornati.

## Bloccante operativo
Nessuna evidenza fresca dello stato servizi o dei percorsi esistenti in VPS: lo script è stato TESTATO soltanto con fixture e non ESEGUITO su Singapore. Richiesto output primo controllo effettuato da utente/operatore Termius. Non si può attestare stato attuale dei worker, né integrità backup Brain in presenza di WAL con i log vecchi.

## Prossimo passo
1. Ricevere output del blocco Termius (solo status + nomi e dimensioni, non password o chiavi).
2. Stabilire sorgenti e servizio fermo con prova fresca; definire permessi OS e un account F0 separato e senza sudo.
3. Generare capture Brain SQLite API WAL-aware e witness fonte, poi trasporto cifrato off-host e restore indipendente; Falco/Toro archivi e lezioni vanno verificati con witness integrali.
4. Continuare NO-GO: niente import V3 reale, niente nuovi wallet 1000/1000/1000 né restart fino a verifica e nuova autorizzazione.

## Nota apprendimento
Il backup `lessons.md` classici viene preservato a livello hash, ma NON è già una memoria strutturata e attiva della V3. I file Brain non-SQLite devono essere inventariati. Il conteggio storico precedentemente osservato non certifica WAL mai mancanti.
