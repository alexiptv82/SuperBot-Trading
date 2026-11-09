# 09/11/2026 — SuperBot V3, audit integrato Claude RC84 e valutazione ChatGPT

## Provenienza
- [PR #80 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/80) all'HEAD immutato `0637e01b2b41a4c89fdbe7473bdc867ee5c58860`, base RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05`; niente merge, deploy, VPS, restart/reset o ordini.
- Rapporto Claude (audit read-only/sandbox) pubblicato come `claude/audit-integrato-rc84-20261109.md`, e sonde `claude/probes/probe_claim_visibility.py` e `claude/probes/test_f3_fixture_aligned.py`, branch `ccr-999de027-0stnyt`, commit `f65edce865d7efdf623ba03b008b10893b208054`.
- [Commento di valutazione ChatGPT sulla PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6740016283). ChatGPT ha letto il rapporto, verificato il codice `backend/v3_api.py`, `frontend/src/pages/Overview.js`, `backend/desk_view.py`, `backend/v3/runner/wiring.py`, `runner.py`, `exit_worker.py`, `exit_service.py`, `legacy_exit_fence.py` e il workflow staging; **non ha rieseguito i test** né effettuato richieste alla VPS.

## D1 — confermato: claim contabili invisibili per Falco/Toro
`backend/desk/cli.py` salva i claim PAPER `paper_close_claims` con `pending/conflict` se storico/learning incompleti; `backend/v3_api.py::_classic` legge lo stato ma **non espone** il claim, mentre ritorna `closed_trades`, equity, PnL e win-rate. `frontend/src/pages/Overview.js` mostra la posizione chiusa senza allarme di riconciliazione. `desk_view.closed_records` può usare le closed dello stato se lo storico manca. La sonda Claude lo riproduce con dati sintetici: dashboard non ha modo di distinguere chiusura contabile checkpointata e definitiva. **Release gate P1.**

Soluzione mirata: API overview autenticata read-only espone payload sanitizzato `reconciliation` (stato ok/pending/conflict/unknown, conteggi, simboli con whitelist/limiti, senza claim grezzo né dettagli sensibili), UI Falco/Toro evidenzia avviso anche con 0 posizioni, distingue i risultati contabili pendenti da risultati definitivi, senza inventare PnL o ordini; test sintetici backend, Jest frontend, fail-visible se dati mancanti.

## D2 — confermato: Brain legacy non escluso dal sidecar
`backend/v3/runner/wiring.py` ha `--exit-mode legacy` di default; `runner.py` in legacy gestisce monitor e comandi; `exit_worker.py` accetta un flag `--legacy-exits-disabled` **solo assertivo**. `exit_service.py` assicura lock fra exit-worker ma non impedisce un runner legacy indipendente. `legacy_exit_fence.py` esplicitamente non protegge processi legacy non patchati. Non vi è prova deploy/ownership unico Brain sotto systemd, né template systemd che abiliti correttamente l'exit-worker. **Release gate P1.**

Soluzione da disegnare/testare prima di deploy: handshake/fence mutualmente esclusivo legacy ↔ exit worker, fail-closed, handover con posizioni aperte e crash/lease restart; template systemd da revisionare non attivare, default e command-line explicit PAPER, metriche ownership per UI. Non toccare ordini/chiusure reali, non avviare servizi.

## QA riclassificata dall'audit Claude
| Test eseguiti da Claude | Interprete | Risultato |
|---|---|---|
| Backend senza auth/profiles | Python 3.13 | 6801 PASS / 32 FAIL / 3 xfail |
| Backend completo | **Python 3.11** | **6841 PASS / 34 FAIL / 3 xfail** |
| Auth+profiles isolati | Python 3.11 | 42/42 PASS |
| Jest / build | Node 22 | 109/109 PASS / build PASS |
| F3 con fixture corretta **solo in copia scratch** | Python 3.13 | 37/37 PASS |

Dei **34 FAIL backend 3.11**: 20 fixture PolicyFixture Brain F3 obsoleta, 1 `desk_view` messaggio UX errato, 1 `live_view` clock non propagato, 1 test S25 hash fisso obsoleto di brain.py, 9 `test_superbot.py` che richiedono server attivo, **2** test RC80 falliti solo con suite completa perché `test_auth_flow.py`/`test_profiles_engine.py` fanno `os.chdir` all'import senza ripristino (subprocess senza `PYTHONPATH` assoluto). Non confondere «preesistente» con «PASS». `sqlalchemy==2.0.28` funziona su deploy Python 3.11 (e 3.12) ma non su 3.13.

## Stack GitHub
- PR #74 Brain manual close, #77 RC80, #78 RC81 e #79 RC82 incluse nella genealogia di #80.
- PR #76 RC79 diagnosi post-trade **NON inclusa**: GitHub compare head #76 vs #80: diverged ahead 48/behind 4, comune antenato `52c21b5...`.
- `main` diverge dalla PR #80: compare ahead 485/behind 2; i 2 commit di `main` non sono nella RC. Prima della RC unica decidere se includere o escludere i cambi di #76 e main; nessun merge automatico.
- Nessun job GitHub Actions sulla head RC84; commit marcati `[skip ci]`.

## Controllo di sicurezza staging
Confermato in `.github/workflows/staging-deploy.yml` un valore **statico pubblico** per password di bootstrap staging; il workflow può pubblicare un backend su interfaccia HTTP e scrive l'env. **Non copiare né pubblicare la password** nei documenti. Stato reale staging sconosciuto: richiesta di preflight VPS read-only separata, verifica se attivo, rotazione credenziali se in uso, rimuovere il valore dal workflow e sostituire con secret, restringere esposizione di rete. Non è stato tentato alcun login o contatto VPS.

## Decisione e prossimo lavoro
**RC84 code-review intra-cycle PASS precedente; release integrata ancora NO-GO per D1+D2, QA 34 FAIL, staging da verificare e gate VPS.** Prima fase suggerita: patch mirata API/UI D1 con test read-only (Claude Sonnet 5.5). Seconda fase: fencing Brain D2 con audit di architettura/handover e suite synthetic, preferibilmente Claude Opus 5.5. Terza: QA Python 3.11 e CI sul commit senza `skip ci`, decisione stack #76/main, backup off-host/restore, browser autenticato Android e preflight VPS separatamente autorizzato. Stop classici OHLC 15m ogni 15/30min non real-time, nessun ordine exchange certificato. Reset nuovi wallet solo PAPER Falco/Toro 1000 USDT e Brain 2000 USDT dopo consenso specifico, preservando storico e lessons.

**Nessun merge, deploy, accesso VPS, restart, reset, modifica di codice trading o ordine.**
