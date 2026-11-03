# Checkpoint SuperBot V3 — 2026-11-03 04:48 Europe/Zurich — F0 no PID, spazio libero

## Evidenza Termius fornita dall'utente
L'utente ha eseguito il comando di preflight in Termius su VPS SuperBot e condiviso screenshot. Righe leggibili:
- `brain.sqlite3 - NESSUN PID RILEVATO`.
- `brain.sqlite3-wal - NESSUN PID RILEVATO`.
- `brain.sqlite3-shm - NESSUN PID RILEVATO`.
- `df -h /opt/superbot-brain-free /opt/superbot-v3-backups`: entrambe sullo stesso filesystem `/dev/sda1`, 38G totale, 6.6G occupati, 32G liberi, 18% uso.
- `PRECHECK_F0_COMPLETATO`.
- Screenshot precedente 21:25: container SuperBot visibili Exited; systemd nessun servizio corrispondente; `/opt/superbot-brain-free/brain.sqlite3` 469327872 byte, WAL 4309552 byte, SHM 32768 byte. Le misure sono relative a quella verifica e non necessariamente attuali.
## Interpretazione
Preflight favorevole per copia CONSISTENTE via API SQLite, ma no-PID in un istante non impedisce restart successivo; ribadire check subito prima della cattura. Il WAL deve essere letto insieme al database, non cancellato/troncato/coppiato separatamente. Fonte principale non deve essere sottoposta a `PRAGMA wal_checkpoint(TRUNCATE)`, `VACUUM`, reset o import V3. Proteggere risultato in nuova directory univoca sotto `/opt/superbot-v3-backups`, senza sovrascrivere precedenti; validare integrità e count/max sequence pre/post, SHA256 e copia esterna cifrata con witness separato. F0 NON ancora certificato, nessun deploy, merge o riavvio autorizzato.
## Stato di esecuzione
Questo checkpoint registra **solo** screenshot osservato e progetto del prossimo passo. Non costituisce prova che il backup sia già stato creato o verificato fuori VPS; attendere output dell'utente.
