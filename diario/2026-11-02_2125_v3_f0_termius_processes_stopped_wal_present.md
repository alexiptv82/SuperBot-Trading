# SuperBot V3 F0 — screenshot Termius 2026-11-02, 21:25

## Evidenza fresca (osservata nello screenshot dell'utente)
- Server Termius mostra prompt `root@vps-a06df2a7`, VPS SuperBot Singapore.
- Container visibili (tra cui superbot-brain-hawk, superbot-brain-bull-previous, superbot-brain-pilot, superbot-turbo, superbot-ai, superbot-sidecar, superbot-pool) tutti `Exited`; la maggior parte `Exited (137)` circa 6–7 ore prima o da giorni, alcuni vecchi `Exited (0)`. Lo screenshot non è inventario completo dei container precedenti al punto di scroll.
- Ricerca servizi systemd running: `NESSUN SERVIZIO CORRISPONDENTE` per filtro superbot/brain/pool/shadow.
- Dimensioni visibili: `/opt/superbot-brain-free/brain.sqlite3` = 469327872 byte; `brain.sqlite3-wal` = 4309552 byte; `brain.sqlite3-shm` = 32768 byte. WAL ancora non vuoto.
- Il risultato della schermata precedente alle 21:21 indicava `lessons.md` e `learning_log.jsonl` presenti nei classici Hawk/Bull e loro archive, assenti nel percorso Brain controllato.
- Exit 137 significa SIGKILL e NON prova da sola corruzione dei dati né ragione certa (OOM/stop manuale possibili); non presumere che il WAL sia interamente checkpointed.
- `VERIFICA_COMPLETATA` significa comando terminato, NON backup certificato.

## Stato e decisione
Prima di catturare Brain via SQLite backup API, ottenere prova che nessun PID stia usando brain.sqlite3/WAL/-SHM e che lo spazio sufficiente sia disponibile. Non cancellare/archiviare/separare i sidecar; NON fare `cp` del solo .sqlite3, `immutable=1` sull'originale, `wal_checkpoint(TRUNCATE)` o riavvii.
Il nuovo codice F0 `backend/v3/backup_certification.py` e `f0_cli.py` esiste nel branch V3 con test sintetici, ma NON è installato sulla VPS. L'accesso remoto automatico root non deve essere usato.
PR #29 resta DRAFT; nessun deploy, merge, reset, import dati reali o riavvio dei bot autorizzato.
Il prossimo passo utile è una verifica manuale, read-only, da Termius di PID file aperti, spazio e percorso di destinazione per nuova cattura consistente. La prova va poi trasferita fuori VPS e confrontata con witness indipendente; F0 ancora NO-GO.
