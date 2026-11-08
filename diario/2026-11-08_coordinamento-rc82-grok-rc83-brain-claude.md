# SuperBot V3 — Coordinamento parallelo 8 novembre 2026 (ChatGPT / Grok / Claude)

**Stato:** Piano operativo; Claude non è stato automaticamente avviato tramite questo diario. L'utente ha comunicato che Claude è nuovamente disponibile e autorizza a proseguire. Nessun merge, deploy, test VPS, riavvio, reset o trade autorizzati.

## Verifiche GitHub al checkpoint
- **Grok owner RC82 classici**: [PR #79 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/79), head `bccfddfb98e6ee0213962951879426fc61ef6f13`, base RC81 `29eb75750625a8819cd2db71dc2459d164c3199c`. L'ultima review ChatGPT [commento](https://github.com/alexiptv82/SuperBot-Trading/pull/79#issuecomment-6724909518) richiede correzioni solo di stale prices per new exposure e recovery dopo DCA con learning failure. Non interferire finché Grok lavora.
- **RC81 dashboard/telemetria classici manutenzione**: [PR #78 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/78), head `29eb75750625a8819cd2db71dc2459d164c3199c`; 99 Jest PASS sul medesimo SHA e build VM Grok, non deploy.
- **Brain manual close RC74**: [PR #74 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/74), head `91214f9064ee2fba478a5c4fcdf5efc3f21a707b`, antenata di RC81. Documentazione [RC74](https://github.com/alexiptv82/SuperBot-Trading/blob/work/v3-rc74-brain-single-manual-close-20261107/docs/v3/RC74-BRAIN-MANUAL-SINGLE-PAPER-CLOSE-20261107.md): test CI offline precedenti; exit-worker sidecar Brain non certificato sulla VPS; occorre verificare run_id, single owner, lock/lease, heartbeat, paths esatti `close_request.json`/`close_result.json`, Journal e UI.
- **UI uniformata tre wallet RC72** [PR #72 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/72), già antenata di RC81. **Diagnosi post-trade RC79** [PR #76 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/76) su ramo separato, non necessaria per audit Brain P0.

## Divisione di ownership
- ChatGPT: coordinamento, diario canonico, review PR Grok e Claude, gate di cutover, nessun coding in file in proprietà Grok/Claude.
- Grok: esclusiva scrittura `backend/desk/cli.py`, e relativi test RC82, più eventuali utility strettamente connesse e handoff sul proprio ramo. No altri file shared.
- Claude: **audit indipendente Brain V3** su checkout isolato, riferito a base `29eb75750625a8819cd2db71dc2459d164c3199c`; percorso separato da classici: `backend/v3/runner/exit_worker.py`, `backend/v3/runner/manual_close.py`, `backend/v3/cutover_gate.py`, `backend/v3_api.py`, e i test di RC74 + UI Brain. Priorità: sidecar single owner, run-id, lock, idempotenza, price freshness, stop/TP/liq, manual close con AI in pausa, journal, risk fail closed, API/UI. Claude NON modifica `backend/desk/*`, né PR #77/#78/#79, né `diario/STATO.md`.
- Claude può preparare soltanto una PR DRAFT `cursor/rc83-brain-readiness-claude-20261108` verso RC81 se trova un P0/P1 reale dimostrato con test riproducibili; patch minime. Altrimenti consegna rapporto di audit + test (nessun codice).
- Nessuna promessa di avvio in background: Claude opera solo quando l'utente inoltra l'incarico. Nessuna azione Cloud automatica.

## Mandato tecnico Claude (in sintesi)
1. Verifica che un comando manuale single-close sia eseguibile solo su PAPER, run Brain corretto, `position_id` effettivamente aperto, con exit-worker indipendente vivo; AI PAUSED non deve essere confusa con stop protection.
2. Verifica no doppio writer/close, doppio tap, crash tra journal/history/state/result, e assenza di ordini live. Flag `V3_ALLOW_BRAIN_SINGLE_CLOSE` OFF di default, `V3_CUTOVER_READONLY=1` mantiene altre mutazioni bloccate.
3. Diagnostica Brain risk/exit con dati stale/missing e ruolo separato di DeepSeek/Claude; niente inventare un motore live o segnalare readiness con il solo heartbeat.
4. Controlla UI identica a Falco/Toro nei campi delle posizioni, conteggi, leve, PnL, trade aperti/chiusi; se Brain è paused/no data non inventare numeri né attribuire allarmi RC80 a Brain.
5. Test sintetici offline con comandi, log e SHA esatto; report con P0/P1/P2, blockers al GO e raccomandazioni minime, senza toccare VPS.
6. Non fondere le PR esistenti, non installare un exit-sidecar, non avviare Brain né azzerare le run, non modificare strategie/AI budgets/leva/size/rischio.

## Gate comune e prerequisiti GO
- RC82 correzioni Grok con test offline e review ChatGPT.
- RC83 audit Brain (Claude) con test e review; Brain manual-close RC74 solo con sidecar realmente testato isolatamente.
- Visualizzazione allarme `stop_feed` RUNNING Falco/Toro separata da RC80 maintenance; stato Brain specifico.
- Test end-to-end browser autenticato su build integrata, compatibilità frontend/backend, no comandi live.
- Backup off-host e restore verificati; controllo VPS read-only e poi deploy/nuova run PAPER solo su nuova autorizzazione specifica. Kapitali desiderati Falco 1000, Toro 1000, Brain 2000 USDT, storici intatti.

**Ultimo audit noto VPS nel diario RC77:** Falco/Toro 0 PAPER posizioni aperte, Brain in pausa; nessuna riconferma live in questo mandato.
