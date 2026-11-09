# SuperBot V3 — Revisione ChatGPT RC84 commit 8b486f (09/11/2026)

## Riferimenti verificati
- [PR #80 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/80): branch `cursor/rc84-running-stop-health-telegram-20261108`, HEAD esatto `8b486f1d40aaec36e398ef43774fb19bc5106c26`, base RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05`.
- Patch codice/test `f0ea0c1d9e9110b439903c19785306c454375ca4` (`backend/desk/cli.py`, `backend/tests/test_v3_rc84_claim_integration.py`); commit successivo soltanto handoff.
- PR ancora Draft, no merge/deploy/VPS/restart/reset/ordini; nessun workflow GitHub legato a HEAD.
- Test dichiarati da Claude su sandbox senza segreti: nuovo 11/11 + vecchio claim 36/36 = 47/47 mirati; Jest 109/109 e build React PASS; backend esteso 6790 PASS, 32 FAIL, 3 xfail, stesso insieme di fallimenti della precedente base `8591dba`; test auth/profiles esclusi per mancanza sqlalchemy. Non sono risultati di CI o test rieseguiti da ChatGPT.

## Gate precedenti ora code-review PASS
1. `_recover_paper_claims` nel `loop_step` gira ogni massimo 60s con claim pendenti anche in pausa + zero posizioni, senza avviare trading; in caso errore heartbeat `paper_close_claims_error`.
2. `_check_portfolio_reset_flag` nega reset e archiviazione con claims pendenti o conflittuali, con `last_action` e file storici intatti.
3. `run_cycle` controlla claims irrisolti all'inizio, filtra nuove aperture/DCA, cancella seconde gambe, passa `drain=no_new` a S25, lascia uscite protettive disponibili. Correzione final-save: se `save_state` fase 3 fallisce, ripristina `state[CLAIMS_KEY]` in memoria per evitare commit involontario da `sync_mode`.

## Un solo P1 integrazione, esposto dalla lettura della sequenza decisioni
**Blocco nuove esposizioni solo calcolato prima del batch:** `claim_block` e `no_new` sono determinati una volta prima di iterare `for dec in decisions`. Una decisione `close(A)` o `partial_close(A)` aggiunge un nuovo `paper_close_claims` ma una successiva `open_long(B)` o `dca(A)` nello stesso batch può essere eseguita perché il filtro è già passato. Analogamente S25 alla fine riceve `drain=no_new` definito prima dei nuovi claims, quindi potrebbe aprire usando il capitale della close non ancora riconciliata. Questo è un rischio desunto direttamente dall'ordine del codice, non un test end-to-end eseguito. Limitazione dello SHA riportata da Claude: blocco solo per claim a inizio ciclo.

**Richiesta puntuale:** aggiungere controllo dinamico della presenza di claims nello stesso ciclo PRIMA di ogni nuova apertura/DCA; per S25, ricalcolare il `drain` con claims correnti; evitare seconde gambe nuove con claim creato durante il batch. Non toccare il protocollo di claim, strategie, risk, LIVE, SL/TP o Brain. Regressioni sintetiche su decisioni miste `[close(A),open(B)]`, `[partial_close(A),dca(A)]` e S25 open nel medesimo ciclo con persistenza guasta, più percorso positivo dopo riconciliazione al ciclo successivo. [Commento GitHub review](https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6734798159).

**Verificare anche** comportamento di una seconda chiusura non protettiva sulla *stessa* posizione parzialmente chiusa con claim pending; non bloccare manuale su posizioni estranee né stop protettivi.

## Esito
Tre guard già richiesti verificati nella code review. **RC84 NON ancora autorizzata per rilascio** per il P1 intra-cycle e i restanti gate esterni. Mantenere PR #80 DRAFT. Priorità dopo mini-fix: code-review SHA finale, collaudo consolidato; browser/app autenticata, sidecar Brain single-owner, backup off-host/restore, preflight VPS read-only, consenso utente per riavvio PAPER 1000/1000/2000 con storici preservati. Nessuna operazione VPS o di trading.
