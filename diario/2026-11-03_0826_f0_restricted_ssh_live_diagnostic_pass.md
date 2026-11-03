# SuperBot F0 — 2026-11-03 08:26 Europe/Zurich — SSH GitHub→VPS DIAGNOSTICA PASS

## Esito confermato con log GitHub Actions
L'utente ha attivato una **nuova** esecuzione manuale di `SuperBot F0 - restricted VPS status` dopo merge PR #31 e aggiornamento del secret `SUPERBOT_F0_SSH_PRIVATE_KEY` nel formato `F0B64:`. 
- Run: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41596313485
- Run ID `41596313485`, commit `fb38267433235780e5f22a335837139cf5ec4211`, `workflow_dispatch`, `status: completed`, `conclusion: success`.
- Job ID `125784384545`, concluso success. Log `F0_KEY_PARSE_PASS`, poi ricevuto JSON `schema: superbot-v3-f0-restricted-status-v1`, `status: OBSERVATION_ONLY`, `read_only: true`, `operator: superbot-f0`, `not_a_backup_certificate: true`.
- Output inventario da host reale:
```json
{
  "backup_root": "PRESENT",
  "brain": {
    "brain.sqlite3": {"bytes": 469327872, "status": "PRESENT"},
    "brain.sqlite3-shm": {"bytes": 32768, "status": "PRESENT"},
    "brain.sqlite3-wal": {"bytes": 4309552, "status": "PRESENT"}
  },
  "classics": {
    "hawk": {"directory": "PRESENT", "archive_directory": "UNAVAILABLE", "required": {"learning_log.jsonl": {"status": "UNAVAILABLE"}, "lessons.md": {"status": "UNAVAILABLE"}, "state_v2.json": {"status": "UNAVAILABLE"}, "trade_history.jsonl": {"status": "UNAVAILABLE"}}},
    "bull": {"directory": "PRESENT", "archive_directory": "UNAVAILABLE", "required": {"learning_log.jsonl": {"status": "UNAVAILABLE"}, "lessons.md": {"status": "UNAVAILABLE"}, "state_v2.json": {"status": "UNAVAILABLE"}, "trade_history.jsonl": {"status": "UNAVAILABLE"}}}
  },
  "processes": {"status": "NO_NAME_MATCH", "matching_count": 0},
  "systemd": {"status": "NO_MATCHING_UNITS", "matching_count": 0}
}
```
- La cartella data Hawk/Bull è attraversabile fino al root directory, ma il nuovo utente non riesce ad accedere ad archive/required. Non interpretare `UNAVAILABLE` come file mancante; da vecchi controlli root i files e archive esistevano. È una **limitazione di permessi o accessibilità** da investigare senza divulgare segreti e senza chmod ricorsivi.
- `processes.NO_NAME_MATCH` e `systemd.NO_MATCHING_UNITS` non costituiscono una verifica esaustiva `fuser` dei DB né prova di bot eternamente fermi.
- Nessun deploy, restart, reset, import storico o operazione di trading eseguita. La PR V3 #29 resta non mergiata.
- **F0 backup NON certificato offhost**: precedente copia locale Brain 8447 eventi resta sul VPS.

## Nuova capacità effettivamente validata
Da ora ChatGPT può recuperare autonomamente gli esiti delle esecuzioni GitHub Actions via connettore, senza chiedere screenshot Termius. L'utente deve ancora effettuare un dispatch manuale se richiede una nuova esecuzione immediata; il workflow ha già schedule giornaliera 03:35 UTC. L'account forced-command `superbot-f0` può produrre soltanto metadati read-only, non backup o modifiche VPS.

## Follow-up sicuro
La coppia SSH privata generata temporaneamente su `/root/superbot-f0-setup/github-f0-ed25519` è ora ridondante se il secret GitHub è funzionante: valutare una pulizia operatore controllata per ridurre esposizione, *senza cancellare la chiave pubblica registrata* o il secret GitHub. Se si desiderano metadati di Hawk/Bull, prima verificare solo i permessi e applicare eventualmente ACL `--x` mirate alle directory, non concedere `chmod 777` o lettura dei file sensibili. Richiedere autorizzazione esplicita per permessi di sistema e cancellazione file, distinta dal test.
