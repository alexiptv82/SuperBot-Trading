# Checkpoint F0 — 2026-11-02 ore 21:21, evidenza Termius WAL Brain

## Fonte e limiti
Screenshot condiviso dall'utente (Termius Singapore, prompt root@vps-a06df2a7). Contenuto visibile soltanto nella parte inferiore della risposta al comando di preflight; la parte superiore con lista container e servizi attivi NON è presente nell'immagine. **Nessun accesso VPS eseguito da ChatGPT** in questa fase.

## Evidenza osservata direttamente nello screenshot
- `/opt/superbot-brain-free/brain.sqlite3-wal`: **4.309.552 byte**.
- `/opt/superbot-brain-free/brain.sqlite3-shm`: **32.768 byte**.
- `/opt/superbot-brain-free/learning_log.jsonl` e `lessons.md`: ASSENTI nel percorso verificato. Non dedurre perdita dati senza inventario completo: Brain può archiviare dati su SQLite o altrove.
- Hawk `/opt/superbot-desk-data/hawk`: state_v2.json, trade_history.jsonl, learning_log.jsonl, lessons.md tutti segnalati OK; directory archive PRESENTE.
- Bull `/opt/superbot-desk-data/bull`: stessi quattro file OK e archive PRESENTE.
- Output finale `F0_CONTROLLO_COMPLETATO`. Questo indica che il comando è terminato, **non** che F0 sia certificato né che bot siano spenti.

## Interpretazione tecnica
Un WAL non vuoto è un vincolo essenziale: NON fare copia grezza del solo brain.sqlite3, NON spostare/cancellare/checkpointare manualmente WAL/-shm e NON invocare `immutable=1` sull'originale per attestare completezza. Non si può dire dal solo WAL se SQLite è ancora aperto o se le transazioni WAL siano già state checkpointed. Usare la SQLite backup API su sorgente autorizzata e con stato processi verificato fresco; conservare prova indipendente del conteggio/seq/digest prima della cattura.

## Prossimo controllo e vincoli
1. Raccogliere schermata completa dello stato dei worker (Docker + systemd) perché è fuori inquadratura; verificare anche database principale e possibili processi fuori Docker.
2. Non usare workflow GitHub SSH-root per aggirare il blocco. Nessuna operazione su produzione finché non siamo sicuri che è fermata e non esiste conflitto tra processi.
3. Solo dopo preparare cattura consistente Brain via backup API su nuova directory isolata, hash e testimone originale separato, trasferimento cifrato fuori host e ripristino verificato.
4. PR #29 sempre DRAFT, nessun import persistente, reset o riavvio V3 autorizzato da questo checkpoint.

Fonte: screenshot nella conversazione corrente, 2026-11-02 21:21; i numeri sono riportati dalla porzione visibile e non da lettura remota del filesystem.
