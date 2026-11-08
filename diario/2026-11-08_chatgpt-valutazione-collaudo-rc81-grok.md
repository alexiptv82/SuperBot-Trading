# RC81 — Valutazione ChatGPT del collaudo indipendente Grok (8 novembre 2026)

## Provenienza
L'utente ha allegato `RAPPORTO-RC81.md` (135 righe) e `HANDOFF-RC81-COLLAUDO.txt` (21 righe), prodotti da Grok sulla VM Cursor. Commit verificato del collaudo: `c980489ac8809c2109c89f3bfc3b4691b194d14f`, PR Draft [#78](https://github.com/alexiptv82/SuperBot-Trading/pull/78), ramo `cursor/rc81-stop-telemetry-ui-chatgpt-20261108`. Grok non ha fatto commit, merge, deploy, push o modifiche VPS. I risultati sono dichiarati nel rapporto di Grok, con comandi e log identificati, non CI GitHub. Nessun browser autenticato.

## Comandi e risultati del rapporto
- `PYTHONPATH=.:backend python3 -m pytest -q -p no:cacheprovider --tb=line backend/tests/test_v3_rc81_classic_stop_health.py backend/tests/test_v3_rc80_paper_stop_hardening.py backend/tests/test_v3_rc78_paper_stop_monitor.py backend/tests/test_v3_classic_exit_only.py` => **82 passed, 0 failed, 7 warnings** (15+30+22+15), 35.38s, Python 3.12.3.
- `CI=true npx react-scripts test --watchAll=false --runInBand --testPathPattern='ClassicStopNotice|Overview|ThreePortfolios|Brain'` => **10 suite, 86 test passed, 0 failed**; Node 22.23.4, npm 10.9.9.
- `BUILD_PATH=/tmp/rc81-frontend-build CI=true npm run build` => **Compiled successfully**. La build definitiva è separata dal checkout. Nel bundle compaiono i messaggi sulla non certificazione degli stop.
- Primo comando pytest senza `PYTHONPATH`: fallita raccolta per `No module named desk`. `npm test` inesistente nel `package.json`; corretto usare `npx react-scripts test`. Non sono fallimenti delle suite dopo configurazione corretta.
- Test negativi su health quote e UI: missing/bad JSON/off/stale/telemetry_failed e wrong-portfolio non mostrano protezione certificata. `covered` vale solo candela 1m già conclusa; **non** stop intrabar. Nessun test browser autenticato, VPS, no GitHub Actions, frontend Jest filtrato (non tutta cartella).
- Brain non monta RC80 (per contratto **solo classici in manutenzione**): non costituisce falso verde. Brain richiede indicatori propri run/AI/exit-service e il classico RUNNING un audit stop separato. Zero posizioni => notice nascosto: nessun falso verde ma manca un indicatore pre-run generale.

## Code review ChatGPT e patch puntuale
Grok ha segnalato caso UI (costruibile da client) `state: covered, quote_coverage: false`: il titolo era di allarme ma il sottotitolo diceva «Prezzi recenti disponibili». ChatGPT ha modificato **solo la UI** `frontend/src/components/ClassicStopNotice.js` affinché mostri «Copertura prezzi non dimostrata: dati incoerenti o incompleti» e aggiunto regression test `frontend/src/pages/ClassicStopNotice.test.js`. Nessun backend, worker, orizzonte prezzi o strategy modificata.

**Nuovo HEAD PR #78:** `29eb75750625a8819cd2db71dc2459d164c3199c`; i risultati 82+86 PASS e build hanno valore verificato nel report SOLO per il commit precedente `c980489ac8809c2109c89f3bfc3b4691b194d14f`. Sul nuovo HEAD test non ancora ri-eseguiti. [Review-comment PR #78](https://github.com/alexiptv82/SuperBot-Trading/pull/78#issuecomment-6722821020).

## Prossimi gate immediati
1. Retest **solo locale** sul nuovo HEAD con Jest UI filtrato e **suite Jest completa**, build isolata; considerare python suite backend invariata ma utile per attestare SHA esatto. Log e status. Tutto no VPS.
2. Definire contratto e test run-specific per stop/TP/liquidazione di Falco/Toro quando il trader è RUNNING, distinto da RC80 maintenance-only. Verificare se engine gestisce wick intrabar vs close-only prima del riavvio.
3. Collegare stato exit service, run_id, AI and position protections specifiche Brain alla UI, senza importare indicatore RC80.
4. Validare browser/sessione autenticata e tablet/smartphone, manual-close PR #74, backup esterno e ripartenza con capitali PAPER Falco 1000/Toro 1000/Brain 2000 solo dopo nuovo mandato e backup. Preservare gli storici.

**NO MERGE, NO DEPLOY, NO VPS, NO RIAVVIO, NO RESET, NO ordini LIVE.** PR #78 DRAFT.
