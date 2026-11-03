# SuperBot V3 — F0 Brain copia SQLite locale confermata, 2026-11-03 04:55 Europe/Zurich

Fonte: screenshot Termius inviato dall'utente nella conversazione, non accesso SSH di ChatGPT.

Risultato visibile: `F0_COPIA_LOCALE_PASS`; directory `/opt/superbot-v3-backups/f0-brain-20261103T035500Z`; numero eventi Brain `8447`; `MAX_SEQ=8447`. Il codice eseguito nella sessione precedente ha confrontato lettura del database sorgente via SQLite `mode=ro`, copia via `Connection.backup()`, integrità, conteggio e hash del flusso eventi e dello stato; il backup ha prodotto `manifest.json` e checksum del database. In screenshot presenti `HASH_EVENTI_FONTE` e `HASH_DB`. L'output finale chiarisce `F0_CERTIFICAZIONE_ESTERNA: NON ANCORA`.

I precedenti screenshot mostravano tutti i container SuperBot visibili con stato Exited, nessun servizio systemd correlato, `fuser` senza PID su `brain.sqlite3`, WAL e SHM; spazio libero circa 32 GB. WAL originale presente (4.309.552 byte) e database sorgente circa 469 MB. Il controllo sulla copia non è un'evidenza di offhost.

**Stato effettivo:** nuova copia locale Brain verificata, ma non cifrata né trasferita fuori dalla VPS e non ripristinata su storage indipendente. Non è possibile chiamare F0 COMPLETO, né importare storico in V3. La cartella originale, il WAL e lo SHM devono restare intatti. Non riavviare processi, non azzerare PAPER, non fare merge/deploy.

**Passo successivo:** leggere in sola lettura manifest, dimensioni e digest della copia e verificare disponibilità di GnuPG/strumenti di trasferimento sicuro. Successivamente, con guida operatore, produrre archivio cifrato e copiarlo su storage esterno, conservarne witness separato ed eseguire verifica dopo recupero. Estendere poi la stessa protezione a Hawk/Bull e agli eventuali altri file Brain.

La PR #29 resta DRAFT, il nuovo cervello V3 non è attivo.