# 09/11/2026 — ChatGPT, RC84 review su SHA 8591dba8 (P0 contabili corretti, 3 guard operativi necessari)

## Verifiche GitHub effettuate
- [PR #80 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/80) head `8591dba8c2152c0e9cb4cc104e7ddcaba09b35de`, base `cursor/rc82-active-paper-stops-31c4` SHA `1e64684b9d813aad1ca1c7d344872333e451fd05`, non mergeata.
- Commit codice+test `5bc0f48bddea37fc353d1cfd92f7fdaf3ba11ab9`, diff contro `2e2aad27b48627cef7807ac75c5ea1b54bbb3ad8`: soltanto `backend/desk/cli.py`, `backend/desk/long_s25.py`, `backend/tests/test_v3_rc84_telegram_durable_close.py`, oltre a handoff aggiornato nello SHA finale.
- Nessun workflow GitHub associato allo SHA. Test **riferiti da Claude in VM locale**, non rieseguiti ChatGPT: 36/36 regressioni contabili nuove, 109/109 Jest, React build PASS, backend esteso 6779 PASS / 32 FAIL / 3 xfail con stesso gruppo di 32 FAIL della base (23 baseline, 9 rete/server). `test_auth_flow.py` e `test_profiles_engine.py` esclusi per `sqlalchemy` mancante. Non c'è full-suite completamente verde.
- Review completa su [commento PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6734234466).

## Buona evidenza: P0 contabili originali sostanzialmente affrontati
Il protocollo PAPER non-protective ora crea `paper_close_claims` salvati insieme al conto, verifica `trade_history.jsonl` e `learning_log.jsonl` sul record esatto, rimuove claim con secondo salvataggio e solo poi notifica Telegram. Retry non ricalcola fill; due partial legittime distinte. `record_close` LIVE è stato ripristinato alla forma precedente e testato sulla VM. Nessuna garanzia transazionale di database o ordine exchange; si tratta di journal locale PAPER.

## Tre gate operativi non coperti dai 36 test
1. **PAUSED+FLAT impedisce recupero automatico:** `loop_step` chiama `iteration/run_cycle` solo se `not (paused and n_open==0)`; `_commit_paper_closes` sui claim pendenti è chiamato all'inizio di `run_cycle` e dentro richieste di chiusura. Se l'ultima posizione è chiusa manualmente quando il bot è in pausa e un registro è indisponibile, claim e conto risultano checkpointati ma lo stato non si completa da solo dopo il ritorno dello storage o restart; `loop_step` resta inattivo. Recupero claims indipendente dal ciclo mercato, senza aprire posizioni, rate-limited, log/heartbeat.
2. **Reset con claims pendenti:** `_check_portfolio_reset_flag` controlla solo pausa e assenza `acc.positions`; se il claim è pending, può archiviare e cancellare `trade_history.jsonl` corrente, poi `state.clear()`, perdendo claim non finalizzati. Gate esplicito deny di reset se claim pending/conflict; preservare file, audit `last_action` e test sintetico paused+0 open.
3. **Nuove esposizioni con claim pending/conflict:** `run_cycle` tenta recupero ma continua con Claude/regole, aperture/DCA e S25 anche se claims restano. Questo può usare saldo non finalizzato o fare nuove partial mentre previous partial pending. Blocco mirato **soltanto nuove aperture e DCA** finché any claims, senza fermare i protective exits né forzare chiusure; verificare nessuna operazione ingiustificata e sblocco dopo recovery. Possibile stop informativo HB `paper_close_claims` già presente, la UI attuale non visualizza dedicated pending.

## Decisione
**Code review P0 originali: progressione positiva; RC84 ancora RELEASE NO-GO per integrazione e 32 FAIL backend estesi non superati.** Richiesta correzione strettamente limitata: 3 guard in `backend/desk/cli.py` e regressioni `loop_step`, reset, claim pending + apertura/DCA e recovery, stesso PR Draft, senza toccare LIVE/strategie e senza nuovo refactoring. Modello per Claude **Sonnet 5.5** per patch mirata; **Opus 5.5** per eventuale verifica finale indipendente del protocollo.

Gates prima di start PAPER Falco/Toro 1000 / Brain 2000: codice integrato/pinned, log/backup off-host + restore, Browser Android autenticato, stop OHLC 15m cadenza 15/30m non stop real-time, Brain exit-worker con single-owner reale, preflight VPS read-only autorizzato e approvazione user separata per merge/deploy/run, storico preservato.

**Nessun merge, deploy, contatto VPS, riavvio, reset o ordine in questa review.**
