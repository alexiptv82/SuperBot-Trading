# SuperBot V3 — Coordinamento ChatGPT / Grok / Claude, mandato proposto RC80
Data: 2026-11-07 Europe/Rome. Stato: **MANDATO PREPARATO, NON ANCORA ESEGUITO**. L'utente ha fermato Grok e vuole utilizzarlo per le parti pesanti, con ChatGPT che controlla e Claude che potrà rientrare domani. Nessuna AI lavora automaticamente in background da questo documento.

## Base verificata
- RC77: Falco/Toro 0 posizioni PAPER aperte dopo le 8 chiusure manuali; backup locale post-close con hash e prova restore PASS, backup esterno NON certificato. Brain PAUSED. Nessun riavvio o nuova run.
- RC78 [PR #75](https://github.com/alexiptv82/SuperBot-Trading/pull/75) su `cursor/rc78-paper-stop-offline-31c4`, HEAD visto `b6eaa173c12c241647f89f730e1430a841cade3a`: monitor opt-in OFF di default per SL/TP/liquidazioni Falco/Toro, soli test offline dichiarati. Non deployato.
- RC79 [PR #76](https://github.com/alexiptv82/SuperBot-Trading/pull/76) su `cursor/rc79-post-trade-readonly-chatgpt`, HEAD visto `35ba0c471986e90510cd4e19c24d8f0f76d8934d`: diagnostica post-trade pura, draft, non integrata. **Non toccare RC79 nel mandato RC80**.
- Review statica RC78: https://github.com/alexiptv82/SuperBot-Trading/pull/75#issuecomment-6713495952. Rischio heartbeat READY anche con quotazioni fresche assenti su posizioni aperte; verifica crash consistency tra storico, journal e stato.

## Incarico riservato a Grok quando l'utente gli inoltra il prompt
RC80: audit tecnico e correzione SOLO offline del monitor PAPER RC78 per fail-visible dei feed prezzi, sicurezza del checkpoint di uscita, crash/restart, test multi-processo, invarianti idempotenza, no aperture, no ordini, nessun reindirizzamento dei worker. Separare i nuovi test dall'effettiva implementazione e riportare blocker residui. Grok deve creare un nuovo `work/v3-rc80-grok-stop-hardening-20261107` a partire dall'HEAD **verificato al momento del lavoro** della PR #75 e aprire una **PR DRAFT verso il branch RC78**, non verso main, con diff stretto.

Non fare merge, deploy, modifiche VPS, restart, nuova run, reset, operazioni live, segreti/log chiavi, budget AI, cambi di strategie/leva/size/rischio, modifiche su RC79 o sulle branch di Claude. Tutto PAPER. Predefinito OFF. Scrivere rapporto e handoff sul PROPRIO branch. Il ramo canonico diario resta sotto coordinamento ChatGPT.

## Gate rilascio futuri separati
1. Stop/TP/liquidazione funzionanti con monitor credibile e alert fail-visible per quote stale, watchdog/cutover e no doppio writer. 
2. Coerenza margin/liquidazione del simulatore, storico append-only e recupero crash.
3. Manual close Brain in pausa PR #74, isolamento run e mount UI.
4. Backup esterno e prova restore, nuova run isolata Falco 1000/Toro 1000/Brain 2000 senza cancellare memoria.
5. Test end-to-end su VPS con autorizzazione separata, dashboard Android, Claude classici, DeepSeek Brain, poi avvio PAPER graduale con nuovo OK specifico.

**Obiettivo:** tornare a fare test PAPER presto senza chiamare 'pronto' ciò che è stato provato solo offline.