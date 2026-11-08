# RC83 — Audit indipendente Brain V3 — Claude Sonnet 4.6 — 2026-11-08

**Revisore**: Claude Code CCR (session `ec005447`)  
**Base commit**: `29eb75750625a8819cd2db71dc2459d164c3199c` (RC81, PR #78)  
**Scope**: audit offline solo — nessuna VPS, nessuna AI, nessun ordine, nessun deploy

---

## Mandato ricevuto

Audit indipendente Brain V3 su RC81: motore AI, risk manager, stop/TP/liquidazione, exit worker, journal, gestione errori, cross-contamination Falco/Toro, "Chiudi ora" con AI in pausa, dashboard Brain, test sintetici offline. Se trovati P0/P1 con test riproducibili → branch `cursor/rc83-brain-readiness-claude-20261108` + fix + PR Draft.

---

## Lavoro svolto

1. Worktree isolato su commit RC81 (`29eb757`), nessuna modifica al working tree principale.
2. Letti e analizzati: `manual_close.py`, `exit_worker.py`, `exit_service.py`, `cutover_gate.py`, `exits.py`, `paper_close.py`, `monitor.py`, `paper_close_fence.py`, `risk.py`, `open_serial.py`, `events.py`, `v3_api.py` (completo), `runner.py` (excerpt).
3. Verificata cross-contamination Brain ↔ Falco/Toro: nessuna.
4. Eseguiti tutti i test V3 offline: **4 849 / 4 849 PASS** (0 fail).

Suite specifiche:
- `test_v3_runner_manual_close.py`: 34/34 ✅
- `test_v3_brain_single_manual_close_gate.py`: 4/4 ✅
- `test_v3_exit_service.py`: 46/46 ✅
- `test_v3_exit_worker.py`: 24/24 ✅
- `test_v3_rc_brain2000.py`: 5/5 ✅

---

## Esito

**Nessun P0. Nessun P1.** Nessun branch di fix creato.

**P2-1** (gap readiness): Exit sidecar `exit_worker.py` non ancora installato sul VPS (documentato in codice). Questo blocca sia nuove APERTURE Brain (`open_serial.py:114` gate `exit_service_unhealthy`) che "Chiudi ora" (`_brain_single_close_ready` → 409). Il sidecar deve essere avviato prima del run 2000 USDT.

**P2-2** (informativo): `loss_exceeds_margin` flagged ma non troncato — by design, nessuna azione richiesta.

**Funzioni verificate** (15/15):
- Brain isolato da Falco/Toro (CHECK SQL + nessun write cross-portfolio)
- "Chiudi ora" funziona con Brain PAUSED (no AI call in `run_manual_close`)
- Idempotenza chiusura (UNIQUE `event_id`, hash chain)
- Protezione doppio-tap (flock dir + check work file)
- Cutover gate 4-flag
- Gate OPEN sempre richiede sidecar sano
- Sidecar POSIX lease esclusivo
- Modulo rischio fail-closed, pure calculator
- Monitor: gap = no stop mancato (contiguous_runs)
- Hash chain journal (SHA-256, trigger anti-UPDATE/DELETE)
- Separazione path API Brain vs classici

**Prerequisito operativo per run 2000 USDT PAPER**: avviare il sidecar `exit_worker.py` sul VPS con `--start-paper --legacy-exits-disabled` e attendere stato `healthy`.

Report completo disponibile su branch `ccr-999de027-0stnyt` al path `claude/rc83-brain-audit-20261108.md`.

---

*Prossimo passo (ChatGPT/Alessandro)*: revisione indipendente del report, decisione sull'avvio sidecar VPS, conferma run 2000 USDT.
