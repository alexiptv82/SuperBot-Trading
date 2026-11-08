# SuperBot V3 — seconda code review RC84 (08/11/2026)

## Identità
- PR #80 Draft https://github.com/alexiptv82/SuperBot-Trading/pull/80, branch `cursor/rc84-running-stop-health-telegram-20261108`, HEAD esatto `2e2aad27b48627cef7807ac75c5ea1b54bbb3ad8`, base RC82 PR #79 `1e64684b9d813aad1ca1c7d344872333e451fd05`.
- Commit codice+test `bbecbf976813cf69948d43026d6e0e1f18ff6085`, commit successivo `2e2aad` handoff soltanto. Fonte Claude report nel commit/handoff.
- Perimetro modificato dal precedente `bfe5ab9...`: `backend/desk/cli.py`, `backend/tests/test_v3_rc84_telegram_durable_close.py`, `docs/v3/RC84-P1-TELEGRAM-CLAUDE-HANDOFF-20261108.md`. Nessuna CI GitHub sullo SHA, nessun merge/deploy/VPS/riavvio/reset/ordini. ChatGPT ha letto diff e codice su GitHub, non rieseguito pytest.
- Test LOCALI Claude riferiti: 27/27 nuovi test Telegram, Jest completo 109/109 e build OK. Suite backend estesa esclusi test_auth_flow/test_profiles_engine (sqlalchemy mancante): 6770 PASS, **32 FAIL**, 3 xfail. Claude dichiara 23 preesistenti sul baseline, 9 di rete in `test_superbot.py`. Non sono prove di suite integrata tutta verde.

## Esito del P1 notifiche
Il nuovo backend usa outbox in RAM `_PENDING_CLOSE_NOTICES` / `_RECENT_CLOSES` e sposta l'invio Telegram dopo `save_state` per chiusure regole/Claude, manuali single, parziali, S25 in PAPER. La funzione `_flush_close_notices` verifica history+learning, altrimenti omette la notifica, e il crash su `save_state` scarta la coda. In generale evita il falso messaggio. Conserva ramo LIVE per l'ordine delle notifiche, ma `record_close` condiviso ora deduplica e va verificato in regressione.

## DUE P0 di release NON risolti
**P0-A — wallet salvato prima del controllo history+learning:** `record_close` esegue append in entrambi i file, ma due writer possono fallire silenziosamente; `_save_state_then_notify` salva il wallet **prima** che `_flush_close_notices` verifichi `_close_logged`. Se history non scrive (caso già testato), Telegram taciuto ma `save_state` completa con conto chiuso o parzialmente ridotto e registri incompleti. Nuovo test negativo controlla soltanto l'assenza dell'avviso e del file history, non l'invariante economico. Non è fail-closed.

**P0-B — doppie chiusure dopo retry a timestamp diverso:** il test `test_manual_retry_at_another_instant_is_a_new_fill_and_never_rewrites_history` asserisce esattamente due registrazioni per la stessa posizione originale: una orfana post-crash e un altro terminale (tempo differente). Quella storia append-only produce conti/storici/learning discordanti. La deduplica `_has_close_row` accetta soltanto lo stesso fill esatto e non respinge terminali diversi della stessa posizione/run. Rischio analogo regole/Claude/S25; partial richiede identità e sequenza distinta per partial multiple legittime, senza confondere retry. Claim `.work` manuale eliminato da finally su errore e richiedibile nuovamente.

**Ulteriore P1 tecnico da valutare nel prossimo code review:** coda notifiche associa `sym+net` a `_RECENT_CLOSES` anziché un identificativo univoco, ambiguità se due chiusure nel ciclo hanno stesso netto. Prevenire doppio invio/dubbia correlazione con chiave fill esatta; non riaprire API LIVE.

**Decisione:** P1 Telegram come invio post-save migliorato, ma RC84 ancora **REQUEST CHANGES / RELEASE NO-GO** su P0-A e P0-B. [Commento di code-review GitHub](https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6727282024).

## Prossimo incarico proposto
Assegnare a Claude **Opus 5.5 (ragionamento approfondito)** la progettazione/patch circoscritta dei P0 con prove sintetiche:
1. Tutti i percorsi PAPER non-protective rifiutano di commitare conto quando registri history/learning non sono provati (e non notificano).
2. Recovery dopo crash con diverso timestamp/price: un solo terminale per run+posizione, oppure blocco fail-closed e riconciliazione esplicita; no cancellazione storici. Distinguere partial multiple legittime, idempotenza per singolo evento.
3. No doppio record, saldo/PnL/learning coerenti, test in crash/ripartenza, errori history/learning/save_state, preexisting terminal discordante.
4. Non modificare strategie, formule economiche, leva/size/risk, regole, integrazioni Brain, PR #77-79, frontend già fissato, né deploy.
5. Verificare live unchanged e separare i 32 fallimenti prima di considerare PASS la suite estesa. Commit e PR Draft sullo stesso ramo, SHA/prompt/handoff; diary solo ChatGPT.

## Gate finali ancora aperti
Classici OHLC 15m a cicli 15/30m non è stop real-time e wick di apertura ignorato; Brain exit-worker non installato/certificato VPS e --legacy-exits-disabled è solo asserzione; browser autenticato/Android, backup off-host e restore, preflight VPS read-only e nuova run PAPER Falco/Toro 1000, Brain 2000 solo previa autorizzazione, storico preservato.

Nessun merge, deploy, intervento VPS, riavvio/reset o ordine eseguito durante questa review.
