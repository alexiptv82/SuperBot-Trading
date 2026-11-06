# SuperBot V3 PR #62 — RC integrata, ripristino storico e onboarding PAPER
**Data:** 6 novembre 2026 | **Autore:** ChatGPT GPT-6 | **Stato:** NO-GO deploy/merge/avvio. Solo codice su branch RC e verifiche VPS non distruttive.

## Stato verificato
- PR #62 `work/v3-release-candidate-gpt6-20261106` draft, basata su PR #57. UI tre portafogli PR #60 + #61, Supervisore, Brain split runner, exit sidecar, open writer e osservatori SHADOW nel ramo isolato.
- CI `v3-dashboard-ci` **success** al commit `6078be700ecb1820ff45481a83439f4e653b96b5`: backend, suite V3 (Python 3.11), frontend test e build. Test locali precedenti integrazione 4.583 passed. CI non è un deploy smoke test.
- Preflight VPS Singapore READ ONLY: web container `superbot` running in PAPER; `superbot-desk-hawk`, `superbot-desk-bull`, `superbot-brain-free` exited. `pause.flag` presente per i tre.
- Portfolio storici: Hawk 6 posizioni PAPER registrate aperte; Bull 2. CLI legacy reset ne impedisce il reset in presenza di posizioni. Non avviare vecchi container e non forzare close o reset.
- Brain legacy `brain.sqlite3` distinto dal journal `journal.db` V3. Nessuna conversione o sovrascrittura dello storico.
- Snapshot VPS: `/opt/superbot-backups/rc-v3-20261106T150730Z`: tarballs superbot-desk-data, superbot-brain-free e copie SQLite legacy `brain-legacy.sqlite3`, `app.sqlite3`; controlli archivi/integrity-check PASS.
- Rehearsal restore in directory /tmp PASS: Hawk 6, Bull 2; Brain archive restored; due SQLite integrità OK; copia temporanea rimossa (nessun dato originale alterato).

## Unico preparatore run V3 PAPER
- Il ramo ha ricevuto in parallelo due comandi (prepare_paper_run e bootstrap_paper). Sono stati consolidati eliminando il duplicato `bootstrap_paper.py` e il test duplicato. **UNICO canonical:** `backend/v3/runner/prepare_paper_run.py`, test `backend/tests/test_v3_rc_prepare_paper_run.py`.
- Il preparatore richiede directory nuova dedicata, `DESK_MODE=paper`, opzione esplicita, `--expected-initial-equity` esattamente uguale al file config. Crea journal e budget, mandata NON approvato, pause flag e snapshot config; non avvia bot, non chiude posizioni, non modifica storico.
- CI verde dopo il consolidamento. Documento di avvio: `docs/v3/RC62-PAPER-AVVIO-CONTROLLATO-2026-11-06.md`; runbook aggiornato `docs/v3-RELEASE-CANDIDATE-BOOTSTRAP-RUNBOOK.md`.

## Gate di rilascio ancora NO-GO
1. Capitale Brain: esempio runner_config.json PR57 = 1000 USDT, desiderio storico progetto = 2000 USDT. Richiede scelta esplicita prima di preparare la run; Falco/Toro tipicamente 1000 USDT ciascuno.
2. Falco/Toro devono usare run nuove in directory separate da quelle con 6+2 posizioni storiche, evitando il reset legacy. Il codice classico ha fallback rules-only se non passa API key Anthropic, ma parametri e policy legacy non coincidono automaticamente con specifiche V3; nessun nuovo motore costruito.
3. Prova effettiva di ownership esclusiva OPEN/CLOSE, monitor stop durante crash/restart/AI lenta, log di heartbeat e fail closed dopo avvio sidecar. Installazione supervisione non fatta.
4. Montaggio dell'app sui nuovi percorsi e test comandi manual close per tutti e tre. UI/CI pronta a livello software, non ancora provata con processi del VPS.
5. Backup fresco + restore, config PAPER e mandato esplicito prima di rimuovere pausa su run nuove. Nessun LIVE, merge, deploy, restart o aggiornamento di chiavi fino ad approvazione.

**Regola principale:** user vuole finire V3 e ripartire in PAPER, non altre implementazioni. Nessun rifacimento bot. Preservare storico. Rischio Brain max 2% trade/5% open, warn/halt 35%/50%, floor 450. Falcon/Toro mantengono policy legacy finché non espressamente approvate/aggiornate. Le vecchie posizioni archiviate non contaminano equity delle nuove run.