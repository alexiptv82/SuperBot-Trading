# Brain V3 PAPER — un solo proprietario delle chiusure (RC84 D2)

**Stato: materiale di revisione.** Nulla qui è installato, abilitato o avviato. Ogni passo sul server richiede un mandato esplicito dell'utente. Solo PAPER (`DESK_MODE=paper`); nessun ordine, nessun reset.

## Protocollo

Per ogni cartella dati Brain esiste **un solo lease kernel**: `flock` esclusivo su `<data_dir>/.exit_service.lock`.

| Processo | Possiede le chiusure? | Lease |
|---|---|---|
| `python -m backend.v3.runner.wiring … --exit-mode legacy` (default) | sì (monitor + chiusure manuali) | **detenuto per tutta la vita** (`LegacyExitFence`); se occupato esce con codice 3 `exit_owner_busy` prima di costruire il runner |
| `python -m backend.v3.runner.exit_worker … --start-paper` | sì | detenuto per tutta la vita (`ExitService`); se occupato esce con 3 `exit_owner_busy` (con `--wait-lease-s N` attende al massimo N s) |
| `… wiring … --exit-mode sidecar` | **no** | non lo prende; apre solo se `exit_service_healthy` (lease + heartbeat sano + monitor recente), altrimenti `halted:exit_service_unhealthy` |

- Il kernel rilascia il lease solo quando il processo termina, anche con crash o `SIGKILL`: nessun lease orfano, nessuna pulizia manuale.
- Un nuovo proprietario non eredita la certificazione del precedente: `exit_service_healthy` torna vero solo dopo un tick sano del nuovo processo, con token nuovo.
- Il lease detenuto dal runner legacy **non** certifica mai il sidecar: in legacy l'exit-worker non c'è e le aperture in modalità sidecar restano bloccate.
- Doppia chiusura della stessa posizione: anche in caso di errore umano, il journal accetta un solo evento `paper_close.<position_id>`; il secondo scrittore riceve un rifiuto.
- Ogni heartbeat del runner contiene ora `exit_mode` (`legacy`/`sidecar`).

### Runner di versione precedente (non aggiornato)

**Non rispetta il lease: l'esclusione verso di lui NON è dimostrabile.** L'exit-worker lo riconosce dall'heartbeat senza `exit_mode`:
- all'avvio rifiuta (codice 3 `foreign_exit_owner:unpatched_runner_recent`) se quell'heartbeat ha meno di 45 minuti, oppure se l'heartbeat non è leggibile;
- durante il servizio, se ricompare, ogni tick è `degraded`: nessuna chiusura del worker e aperture sidecar bloccate.

È solo una difesa in profondità: un vecchio runner bloccato per più di 45 minuti che poi riparte non verrebbe riconosciuto. **Per questo la migrazione passa obbligatoriamente da un runner legacy aggiornato** (fase A).

## Migrazione legacy → sidecar (proposta, da eseguire solo con mandato)

0. Prerequisiti: backup off-host verificato; run PAPER preparata (`runner_config.json` nella cartella dati); posizioni aperte annotate; `DESK_MODE=paper`.
1. **Fase A — aggiornare il runner legacy a questo codice** e verificarlo:
   - `heartbeat.json` contiene `"exit_mode": "legacy"`;
   - un secondo avvio sulla stessa cartella esce con 3 `exit_owner_busy`;
   - `python -m backend.v3.runner.exit_worker --data-dir … --run-id … --validate-only` (sola lettura) non segnala `foreign_exit_owner`.
2. **Fase B — passaggio di consegne senza sovrapposizione:**
   1. avviare l'exit-worker con `--wait-lease-s 120`: attende, perché il lease è del runner legacy;
   2. fermare il runner legacy con `SIGTERM`: il lease viene rilasciato all'uscita e l'exit-worker lo acquisisce entro circa 0,25 s;
   3. attendere `READY=1` (primo tick sano: monitor eseguito, nessun errore);
   4. avviare il runner `--exit-mode sidecar` (l'unità ha `BindsTo`/`After` sull'exit-worker).
   Le posizioni aperte restano nel journal: il primo tick dell'exit-worker le monitora. Nessuna chiusura forzata, nessun reset.
3. **Ritorno indietro:** fermare il runner sidecar, poi l'exit-worker (il lease si libera), poi avviare il runner legacy aggiornato (riprende il lease).

## Verifiche in sola lettura

- `systemctl status superbot-brain-v3-exit-worker@<run>` → `active (running)` e `Status:` senza `exit_service_degraded`.
- `GET /api/v3/overview` → `brain_single_close_allowed` vero solo con `V3_ALLOW_BRAIN_SINGLE_CLOSE=1` ed exit-worker sano.
- `heartbeat.json` del runner sidecar con `exit_mode: "sidecar"`; `exit_heartbeat.json` con `state: "healthy"`.

## Template

- `superbot-brain-v3-exit-worker@.service.template` — `Type=notify`, `WatchdogSec=60`, `--wait-lease-s 120`.
- `superbot-brain-v3-runner-sidecar@.service.template` — `BindsTo`/`After` sull'exit-worker.

Segnaposto da sostituire con valori **verificati**: `@@SERVICE_USER@@`, `@@REPO_DIR@@`, `@@PYTHON@@` (3.11/3.12; `sqlalchemy==2.0.28` non funziona su 3.13), `@@BRAIN_DATA_DIR@@`, `@@BRAIN_ENV_FILE@@`. Nessuna credenziale nei template.
