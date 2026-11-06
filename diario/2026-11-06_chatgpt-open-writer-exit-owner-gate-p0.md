# SuperBot V3 — P0: serializzazione delle aperture PAPER e proprietario unico delle uscite
**Checkpoint:** 6 novembre 2026 — ChatGPT GPT-6. Solo sviluppo LOCALE/PAPER; nessun merge, deploy, avvio, VPS, cambio capitali o storico.

## Baseline e rami verificati
- PR #57 runner `e25c8dd8db88fd6994e3b7a75ecfdec5ff258421` draft e PR #61 dashboard `a9044b6759da327b44da04f9e7f51e211d44e03f` draft, separate.
- ZIP base `superbot-trading-e25c8dd.zip`; **385/385 file originali invariati byte per byte**. La patch Runner è stata applicata temporaneamente per test e poi tolta.

## Nuovo sviluppo isolato
- `backend/v3/runner/open_serial.py`: `commit_paper_open` richiede PAPER, il journal originale preesistente, un lock `flock` su `.brain-paper-open.lock`, ripete `post_ai_guard.recheck_paper_open` dopo acquisizione, verifica la vera lease + heartbeat di `ExitService` e scrive l'OPEN usando `execute_paper` originale prima di liberare il lock. Replay `decision_event_id` vietato anche dopo close. Solo writer aderenti al protocollo sono serializzati.
- `backend/v3/runner/legacy_exit_fence.py`: legacy può acquisire l'identico lock `.exit_service.lock` del sidecar per l'intera sua sessione. Non finge il heartbeat healthy del sidecar. Il runner VPS attuale NON usa questo lock.
- `backend/v3/runner/cutover_preflight.py`: preflight sola lettura: rifiuta se posizioni PAPER ancora aperte o richieste di chiusura manuale pendenti; non dichiara mai che un cutover sia autorizzato, richiede prova indipendente del fermo legacy e nessuna chiusura forzata.
- `EXIT-LEGACY-FENCE-RUNNER-OPTIN-REVIEW-ONLY.patch`: solo proposta da far revisionare a Claude, aggiunge `legacy_exit_fence=None` al Runner e acquisizione per tutta Runner.run. Non applicata al codice in GitHub.

## Test verificati
- Con patch Runner applicata SOLO in sandbox: **1263 PASS in 18.65s** (runner, risk, executor, journal, exit, new tests), exit 0.
- Con patch da /tmp: **36 PASS in 3.90s**, exit 0.
- Tornati ai 385 file originali: **1258 PASS in 17.46s**, exit 0.
- Solo nuovi da /tmp su baseline originale: **31 PASS in 3.38s**, exit 0.
- `patch --dry-run` e `git apply --check` contro Runner originale: PASS. Python compile PASS.
- Test concorrenti: 2 processi stesso decision ID -> massimo un `paper_open`; 2 processi simboli differenti quasi a budget rischio -> massimo un open e retry veto; owner legacy/sidecar con lock coerente; fake heartbeat, symlink/permessi lock, replay dopo close e cutover con pending/posizioni fail closed.

## P0 rimasti NON risolti
1. Vecchio `run_brain_cycle` usa `execute_paper` diretto (bypassa lock nuovo); niente migrazione né prova del processo legacy attivo. Il coordinatore protegge solo processi aderenti.
2. `post_ai_guard` e `execute_paper` usano connessioni journal separate: flock protegge writer cooperanti, NON è una transazione SQLite globale su processi che lo ignorano, budget separato o cambiamenti di mercato esterni.
3. Handover tra old e sidecar non provato senza vuoto di monitor; preflight richiede portfolio flat e nessuna richiesta manual, e controllo sistema reale solo dopo OK dell'utente.
4. Non eseguiti full suite 6k+, CI multi-versione, Jest/CRA, benchmark VPS, DeepSeek o Bitget live, deploy/systemd reali.

## Files in ChatGPT Library /SuperBot-Trading
- `SuperBot-V3-Open-Writer-Exit-Ownership-Gate-P0-2026-11-06.zip`, SHA-256 `c1731441c30fde90f3fcf45a8b308203794804f610bc59206c0f7bd1013167a9`, libfile `libfile_66404a90bc788191b3711317725ad48f`.
- `RAPPORTO_SUPERBOT_V3_OPEN_SERIAL_CUTOVER_P0_2026-11-06.md`, SHA-256 `da1500c76930689d847bad4b98eb8e366f16c66127d783887bf94ae0cbdc275f`, libfile `libfile_4cf28333027c81918e464d334306558c`.
- `HANDOFF_CLAUDE_OPEN_OWNER_PROTOCOL_2026-11-06.md`, SHA-256 `54cc1a76e46524d4fea3589a57f86736f1b03603e397d7bd3a6af03db0b0ae64`, libfile `libfile_b005738d10f48191be6eaf8999333f34`.

## Prossimo gate
Revisione Claude / code-owner, integrazione su branch ISOLATO delle patch in modo che `run_brain_cycle` non abbia fallback diretto in split mode; stage legacy-fence e avvio sidecar con conferma vera di stop processo legacy, preferibilmente portfolio flat; test rollback e multiprocesso + CI totale. NO deploy/merge/avvio senza OK esplicito. Parametri PAPER invariati: rischio per trade 2%, open risk 5%, warn 35%, halt 50%, floor 450 USDT.