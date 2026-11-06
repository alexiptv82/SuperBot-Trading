# SuperBot V3 — Revisione S1b, controllo stop e heartbeat (6 novembre 2026)

**Autore:** ChatGPT GPT-6. **Stato:** lavoro isolato PAPER. NESSUN merge, push di codice, deploy, avvio Brain, redeploy Falco/Toro, modifica rischio o storico.

## Sorgenti
- PR #57 (runner) head `e25c8dd8db88fd6994e3b7a75ecfdec5ff258421` e PR #61 (dashboard) head `a9044b6759da327b44da04f9e7f51e211d44e03f`: due bozze separate.
- S0/S1 presenti nella copia locale sono ricostruzioni, NON copie originali certificate degli ZIP della Libreria. S2 è la versione verificata in isolamento della consegna precedente.
- Nuove modifiche NON applicate al repository del codice: due patch separate e test mirati.

## Bug S1b confermato e corretto nella nuova patch opzionale
La precedente `S1b-RUNNER-OPT-IN-NON-APPLICARE.patch` registra una `supervisor_observation` READY, poi su una eccezione inattesa durante `execute_paper` tenta di aggiungere un evento SKIPPED con lo stesso ID deterministico. Si ottengono `cycle_error` e un falso `supervisor_evidence_failed`. Nuovo test con la vecchia patch: **1 failed** (difetto riprodotto). La patch corretta inizializza `observation=None` per candidato e scrive SKIPPED soltanto **prima** della osservazione; dopo READY lascia un eventuale esito `pending`, senza sovrascrivere la cronologia. `supervisor_evidence=False` resta default.
- Nuova patch `S1b-RUNNER-OPT-IN-REVISIONATO-NON-APPLICARE.patch`, SHA256 `9b5e5826fef01e61c4876dd7897b59d3e287bc3a9791287378f511b4ab9048dd`, sostituisce la vecchia (NON concatenarla).
- `patch --dry-run -p1` e `git apply --check` sull'originale e25: PASS.

## Test eseguiti
- Regressione completa su worktree ibrido e25 + S0/S1 ricostruiti + S2 + patch S1b nuova: **4379 PASS in 150.35s**, exit 0. Include sei nuovi test safety; il settimo è stato aggiunto successivamente e testato separatamente.
- Mirati S1b/safety/runner: **86 PASS in 2.15s**.
- Da /tmp: **19 PASS in 0.59s**.
- Test di errore del runner PROPOSTO con patch heartbeat + aggiornamento test originale: **46 PASS in 0.15s**; senza aggiornamento il test legacy fallisce, comportamento documentato. Patch NON integrata.

## Problemi ancora aperti — non dichiarare pronta la release
**P0 STOP:** `Runner.tick` esegue `_commands` e `_monitor` prima di `run_cycle`, ma durante DeepSeek lento lo stesso thread non ricontrolla stop/manual close. Un test locale con barrier riproduce la limitazione; non la risolve. Serve servizio di uscite indipendente o soluzione equivalente testata a 30 s, con idempotenza del journal.

**P1 HEARTBEAT:** con tick fallito `Runner.run` invia `state=running` anche se esiste `pause.flag`. Proposta `HEARTBEAT-FAIL-CLOSED-PROPOSTA-CON-TEST.patch` rende `halted` su errore e aggiorna test, ma NON crea un latch persistente né risolve le latenze. Revisione necessaria da Claude.

**Non eseguiti:** test Jest/CRA, benchmark VPS a 30 simboli, risposta DeepSeek reale, unificazione GitHub PR #57/#61, merge, deploy.

## Libreria ChatGPT e allegati
- `/SuperBot-Trading/SuperBot-V3-S1b-Gate-Sicurezza-Stop-2026-11-06.zip`, SHA256 `ac945ac69958d6ab38d96f4b700221d90e4731d1eb4d65fe83a3e3681f2a8807`, libfile `libfile_8033c1b1c5dc81918df4eb16c883a4a0`.
- `/SuperBot-Trading/RAPPORTO_SUPERBOT_V3_GATE_STOP_S1B_2026-11-06.md`, SHA256 `472f04b82428aa02d0c02ba5b075134128ccbd4d6856c201df4c5d00b79e2344`, libfile `libfile_72fdec30354481918bbfac27977baaeb`.

## Prossimo gate
Claude (proprietario runner) rivede le patch; testare separazione dei monitor stop/close da analisi DeepSeek bloccante, controllo latenza e concorrenza; integrazione isolata PR57+61 con S0/S1/S2, Jest e CI; solo poi valutare rilascio con OK esplicito dell'utente. Restano PAPER e invariati: rischio trade 2%, open risk 5%, daily warn 35%, stop 50%, floor 450 USDT. Non adottare ticket/margine 43% del video.
