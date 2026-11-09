# SuperBot V3 — ChatGPT code review D1 claim visibility, RC84 SHA c6082d (09/11/2026)

## Identità e limiti della verifica
- [PR #80 RC84 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/80), HEAD verificato `c6082dfefc26d4ed61aaa3363bb24af45612db8b`, base RC82 PR #79 `1e64684b9d813aad1ca1c7d344872333e451fd05`. Nessun merge.
- Commit codice/test `973fe5722b7c7b8dee8cb25d273c24406652b8bb`, commit seguente solo `docs/v3/RC84-P1-TELEGRAM-CLAUDE-HANDOFF-20261108.md`.
- [Commento PR con decisione code review](https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6743483471).
- ChatGPT ha verificato diff GitHub, non eseguito localmente pytest/Jest, nessuna CI GitHub sullo SHA, nessun browser autenticato o Android, nessun contatto VPS/ordini/deploy/restart/reset.

## Decisione: D1 APPROVED a livello di code review, non autorizzazione rilascio
`backend/v3_api.py::_classic` espone nell'API GET autenticata `/api/v3/overview` il campo sanitizzato `close_reconciliation` per Falco e Toro; Brain invariato. Payload: `state: ok|pending|conflict|unknown`, `pending_count`, `conflict_count`, `affected_symbols` (max 8, regex), `checkpointed_not_final`. Non espone claim_id, rec, net, motivi o notice. `ClaimReconciliationNotice.js`, incluso in Overview e Dashboard Classici, mostra alert anche con zero posizioni, distingue pending, conflitto con intervento umano e non verificabile, senza azzerare contabili, senza controlli di scrittura. `ClassicStopNotice` invariato.

### Test riferiti da Claude
- Nuovi 19 backend `test_v3_rc84_claim_visibility.py`, incluse auth 401, read-only file, dati Brain assenti, malformazioni.
- Nuovi 15 Jest (11 component, 4 integrazione dashboard), totale **124/124 PASS**, build React CI=true PASS.
- Backend completo Python 3.11 **6860 PASS / 34 FAIL / 3 xfail**, stesso insieme 34 FAIL della base audit `0637e01b`. Fallimenti rimasti: 20 Brain F3 fixture, 1 desk_view UX, 1 live_view clock, 1 long_s25 hash, 9 test_superbot richiedono server, 2 RC80 subprocess a causa os.chdir import-time auth/profiles. Non segnare suite verde.
- Nessun workflow GitHub Actions sul nuovo SHA.

### Nota QA di telemetria divergente, non-bloccante D1
`_claim_reconciliation` usa `heartbeat.paper_close_claims.conflict` se fresco (age_s<120s), ma non il suo `pending`. Se HB fresco dice pending>0 e `state` mostra zero claims, API può mostrare `ok` anziché `unknown`/diagnostica di mismatch. Un conflict HB per lo stesso claim che il file mostra pending può causare doppio conteggio pending+conflict per una sola chiusura. È una possibile incoerenza visiva su snapshot discordanti, non una riproduzione di errore contabile. Suggerito test fail-visible nell'ultimo gate QA; evitare nuovi cicli generalizzati di sviluppo.

## D2 Brain ancora blocker rilascio
`backend/v3/runner/wiring.py` default `--exit-mode legacy`. `runner.py` mantiene monitor+commands in legacy, mentre `exit_worker.py` richiede `--legacy-exits-disabled` solo come dichiarazione operatore, non come prova tecnica. `exit_service.py` possiede lock POSIX solo fra exit-workers; `legacy_exit_fence.py` bridge opzionale, NON sicuro verso un vecchio runner non patchato. Richiesti design e test cross-process esclusione reciproca/handover, no doppio writer, fail-closed nuovi ingressi su exit unhealthy, unità systemd come **artefatti** non installate, audit readiness del processo di migrazione. Modello Claude **Opus 5.5**, no VPS, nessun LIVE né ordine.

## Gate complessivi
- Backend Python 3.11 34 FAIL da correggere/classificare; GitHub Actions CI senza [skip ci] per RC pinned.
- Git history: PR #76 RC79 diagnosi post-trade non antenato RC84; main ha 2 commit mancanti: decidere integrazione prima di release candidata unica.
- Staging: workflow pubblico contiene password bootstrap staticamente configurata: NON ripeterne il valore; stato VPS ignoto, richiede controllo autorizzato, secret + eventuale rotazione.
- Backup off-host + restore, browser autenticato Android, preflight VPS READ-ONLY previa autorizzazione, classici stop OHLC 15m ogni 15/30min non stop tick-by-tick; autorizzazione separata utente per nuovo run esclusivamente PAPER Falco/Toro 1000 e Brain 2000, dati storici preservati.

**NO MERGE/DEPLOY/VPS/RESTART/RESET/ORDINI.**
