# RC83 — Audit indipendente Brain V3 — Claude Sonnet 4.6
**Data**: 2026-11-08  
**Base commit**: `29eb75750625a8819cd2db71dc2459d164c3199c` (RC81)  
**Branch di sviluppo**: `ccr-999de027-0stnyt`  
**Revisore**: Claude Code (CCR, session `ec005447`)

---

## Sintesi

**Nessun P0. Nessun P1.** L'architettura Brain V3 è solida, fail-closed, e ben coperta da test.  
Le 4 849 test V3 passano tutte (0 fallimenti) sul commit RC81.

Trovato **1 gap di readiness** (P2): il sidecar di uscita `exit_worker.py` non è ancora installato sul VPS. Questo blocca sia le nuove APERTURE che la "Chiudi ora" manuale — per design e in modo fail-closed.

---

## Funzioni verificate

| # | Funzione | File/riga chiave | Stato |
|---|----------|-----------------|-------|
| 1 | Brain isolato da Falco/Toro | `events.py:111` CHECK `portfolio_id IN ('hawk','bull','brain')`, mai mischiati | ✅ CONFERMATO |
| 2 | Nessun componente Brain scrive su hawk/bull | Nessuna chiamata a `execute_paper` / `close_paper` con portfolio_id ≠ 'brain' | ✅ CONFERMATO |
| 3 | "Chiudi ora" funziona con Brain in PAUSA | `run_manual_close`: nessuna chiamata AI, nessun controllo pause — test `test_commands_run_on_every_tick_before_the_monitor_even_when_paused_or_halted` ✅ | ✅ CONFERMATO |
| 4 | Idempotenza chiusura | `paper_close.py`: `event_id = paper_close.<position_id>`, UNIQUE constraint SQLite | ✅ CONFERMATO |
| 5 | Protezione doppio-tap (UI) | `_close_request` in `v3_api.py:556-572`: flock dir + controlla `.close_request.work` esistente → 409 | ✅ CONFERMATO |
| 6 | Cutover gate 4-flag | `cutover_gate.py:brain_single_close_enabled`: richiede V3_CUTOVER_READONLY + V3_ALLOW_BRAIN_SINGLE_CLOSE + TRADING_MODE=paper + DESK_MODE=paper | ✅ CONFERMATO |
| 7 | Gate APERTURA → richiede sidecar sano | `open_serial.py:114`: `exit_service_healthy(...)` incondizionale, nessun `exit_mode` lo bypassa | ✅ CONFERMATO |
| 8 | Sidecar ha lease esclusivo POSIX | `exit_service.py:182`: `LOCK_EX | LOCK_NB`, token rinnovato a ogni restart — test `test_posix_lease_is_exclusive_across_real_processes` ✅ | ✅ CONFERMATO |
| 9 | Heartbeat stale → blocca OPEN | `exit_service_healthy`: MAX_BEAT_AGE_MS=15 000 ms, re-check token finale | ✅ CONFERMATO |
| 10 | Modulo rischio fail-closed | `risk.py`: pure calculator, nessuna rete, nessuna strategia hard-coded, fail su input invalido | ✅ CONFERMATO |
| 11 | Monitor: gap = no stop mancato | `feed.py:contiguous_runs` + `monitor.py:49` — test `test_v3_rc78_paper_stop_monitor.py` ✅ | ✅ CONFERMATO |
| 12 | Stop sempre tiene su TP | `exits.py:evaluate_exit` — stop vince su TP se colpiti nella stessa barra | ✅ CONFERMATO |
| 13 | Hash chain journal | `events.py:187-207:verify_chain` SHA-256, trigger impedisce UPDATE/DELETE | ✅ CONFERMATO |
| 14 | Separazione path API | `/api/v3/brain/close` ≠ `/api/desk/close-position` ≠ `/api/desk/bull/close-position` | ✅ CONFERMATO |
| 15 | Dashboard Brain ≥ qualità classici | `v3_api.py`: equity, day_pnl, margin_in_use, win_rate, open/closed trades, peer_observations (display-only) | ✅ CONFERMATO |

---

## Risultati test offline (sintetici, nessuna VPS, nessuna AI)

| Suite | Esito |
|-------|-------|
| `test_v3_runner_manual_close.py` | **34/34 PASS** |
| `test_v3_brain_single_manual_close_gate.py` | **4/4 PASS** |
| `test_v3_exit_service.py` | **46/46 PASS** |
| `test_v3_exit_worker.py` | **24/24 PASS** |
| `test_v3_rc_brain2000.py` | **5/5 PASS** |
| Tutti i test V3 (totale) | **4 849/4 849 PASS** |

---

## Finding P2 — Gap di readiness

### P2-1 · Exit sidecar non ancora installato sul VPS

**Gravità**: P2 (non blocca la correttezza del codice, ma blocca il deployment operativo)

**Evidenza**:
- `exit_worker.py` docstring: *"The launcher/wiring on the VPS is NOT yet installed."*
- `exit_service.py` docstring: *"NOT wired into live runner."*
- `open_serial.py:114`: `exit_service_healthy(...)` è incondizionale — senza sidecar, **nessuna nuova posizione Brain può aprirsi**.
- `_brain_single_close_ready`: senza sidecar, "Chiudi ora" restituisce 409 `servizio_uscita_non_pronto`.

**Impatto**:
1. Run 2000 USDT PAPER attuale non può aprire posizioni (exit_service_unhealthy).
2. "Chiudi ora" non disponibile finché il sidecar non è attivo e sano.

**Correzione necessaria prima del run**:
```
# Sul VPS, nella data-dir del run Brain:
python -m backend.v3.runner.exit_worker \
  --data-dir /opt/superbot-desk-data/brain/<run_id>/ \
  --run-id <run_id> \
  --config /opt/superbot-desk-data/brain/<run_id>/runner_config.json \
  --start-paper \
  --legacy-exits-disabled
```
Il sidecar deve essere supervisionato (systemd) e deve raggiungere lo stato `healthy` prima di avviare il Brain runner.

**Nota**: il gap è intenzionale (by design). Il codice include un template systemd ed è pronto per il deployment.

---

### P2-2 · loss_exceeds_margin non troncato

**Gravità**: P2 informativo

**Evidenza**: `paper_close.py`: `loss_exceeds_margin = bool(realized < 0 and -realized > margin)` — flag impostato ma la perdita NON viene troncata.

**Impatto**: In scenari estremi (gap, liquidazione), la perdita registrata può superare il margine depositato. Non è un errore — rispecchia il comportamento reale degli exchange a leva. Per un run PAPER da 2000 USDT, è corretto lasciarlo così (il log serve come indicatore di liquidazione simulata).

**Nessuna azione richiesta** prima del run.

---

## Cross-contamination check

| Domanda | Risposta |
|---------|----------|
| Brain scrive su journal Falco/Toro? | No. `execute_paper`/`close_paper` usano `portfolio_id='brain'`. CHECK SQL impedisce portfolio_id errato. |
| Falco/Toro scrivono su journal Brain? | No. `legacy_audit.py`, `legacy_multirun.py`, `offline_import.py` verificano `portfolio_id in ("hawk","bull")` e rifiutano "brain". |
| `v3_api.py` legge dati classici? | Sì, via `desk_view` (read-only). Non scrive mai su journal classico. |
| "Chiudi ora" Brain chiude posizioni Falco/Toro? | No. L'IPC scrive solo `close_request.json` nella data-dir Brain; `run_manual_close` usa `portfolio_id='brain'`. |
| Sidecar Brain interferisce con exit classici? | No. ExitService usa il proprio POSIX flock nella data-dir Brain; i classici hanno il proprio canale `desk_view`. |

---

## Rischi residui per il run 2000 USDT PAPER

| Rischio | Mitigazione esistente | Livello |
|---------|----------------------|---------|
| Sidecar non avviato | Gate OPEN `exit_service_unhealthy` blocca aperture | Basso (fail-closed) |
| Heartbeat stale (sidecar stoppato) | MAX_BEAT_AGE_MS=15s, `exit_service_healthy` blocca nuovi OPEN | Basso |
| Doppio click "Chiudi ora" | flock dir + check work file → 409 | Basso |
| Loss > margin in mercato volatile | `loss_exceeds_margin` flag; nessun truncation (by design) | Informativo |
| Falco/Toro down durante Brain aperto | Brain è isolato; non dipende da Falco/Toro per le proprie uscite | Basso |
| Feed market fetch fallisce durante monitor | `monitor.py:66`: errore su singola posizione non ferma le altre | Basso |

---

## Conclusione

**Brain V3 su RC81 è pronto per il run 2000 USDT PAPER**, con un prerequisito operativo:

> **Avviare il sidecar `exit_worker.py`** sulla VPS prima di attivare il Brain runner.  
> Senza sidecar, nessuna posizione Brain si apre e "Chiudi ora" è disabilitata — by design, fail-closed.

Nessuna modifica al codice è necessaria. Nessun branch di fix creato (nessun P0/P1 trovato).

---

*Audit condotto offline su commit `29eb757`, nessuna VPS, nessun AI call, nessun ordine reale.*
