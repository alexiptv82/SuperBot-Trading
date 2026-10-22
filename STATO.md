## Aggiornamento 22/10/2026 — ChatGPT: analisi step 4 preparata, in attesa di revisione

- Ramo `work/director-chatgpt` HEAD `ed3c65c`: aggiunti `deploy/scripts/regime_trade_analysis.py`, workflow `desk-regime-trades.yml` e 7 test sintetici. Il ramo non contiene un trigger attivo.
- Regole di calcolo: chiave `(bot, run_no, id)`; una sola apertura; trade incluso solo con una chiusura finale; `net_r` additivo sommato su tutte le chiusure, parziali incluse; lato e BTC `roc24h` presi dall'evento di apertura. Down <−1%, up >+1%, flat negli altri casi. Report aggregato stratificato anche per run e versione.
- Il report non stampa simboli, ID, prezzi o PnL in dollari. Il workflow previsto è usa-e-getta, rete disabilitata nel container, volume dati `:ro`, snapshot SHA-256 e controllo che ID/immagine/start-time dei container Hawk/Bull non cambino durante la misura.
- Verifiche locali: `py_compile`, YAML parse e 7 test manuali passati con Python 3.12.14. `pytest` e Python 3.11 non sono disponibili in questo ambiente. Nessuna esecuzione sul server e nessun merge del workflow.
- **Gate prima del merge:** revisione di Claude, poiché il workflow accede al VPS; poi attivazione esplicita del trigger di sola lettura e controllo che i due bot non siano stati riavviati.

## Aggiornamento 22/10/2026 — ChatGPT: step 3 attivato, incompatibilità dello schema rilevata

- Merge manifest in `rule-pool`: `0cc1f035`; trigger aggiornato al commit `8b0fcaa`. Nessun deploy dei bot.
- Workflow `desk-manifest` run `39719909269` completato. Hash dei registri verificati: Hawk `87b7e871…ef443c7` (2.483 righe), Bull `d273b2e4…d1ac261` (3.107 righe); JSON invalidi 0.
- Il parser si aspetta record di trade (`symbol`, `side`, `entry_ts`, `exit_ts`, `net`, `gross`, `fees`), ma `learning_log.jsonl` è un registro di eventi (`ev=open/close/candidate`, dati annidati in `features`, `net_r` sulle chiusure). Risultato: righe valide 0; il workflow ha comunque stampato “MANIFESTO OK” perché considera fatale solo il file mancante. Gli hash attestano i byte letti, non la validità semantica.
- Step 4 (R per regime e lato) non ancora calcolato. Serve parser event-aware che unisca `open`/`close` per `(bot, run_no, id)`, sommi `net_r` delle chiusure e classifichi il regime usando solo dati d’ingresso. La classificazione disponibile nel log è BTC `roc24h` (<−1% down, >+1% up, altrimenti flat), quindi va etichettata come proxy BTC; la mediana cross-section dei 26 simboli non è direttamente registrata come singola feature.
- Workflow di sola lettura: Hawk e Bull risultavano in esecuzione senza riavvii osservati. Nessuna strategia, database o stato dei bot modificati.
- Rami: `rule-pool` `8b0fcaa`; `work/director-claude` `40157c3`; `work/director-chatgpt` `9255093`; questo aggiornamento documenta il limite emerso.

# STATO SuperBot — aggiornato 2026-10-22 06:00 Roma (Claude)

## Ultima azione
**Commit `40157c3`** su `work/director-claude`:
- Step 3 ricerca: `learning_log_manifest.py` + workflow `desk-manifest.yml` + 11 test
- Nessun dato grezzo nel repo pubblico; solo sha256 + conteggi

## Deploy attivo (rule-pool HEAD: 4aabeb8 / trigger pushato stamani)
- `4eaaf67` — daily_stop 12% → 10% (Hawk + Bull) ← **nuovo**, riavvio gestito da desk-deploy.yml
- `880c4a4` — fix barre 1d (pause/retry 429, serie ieri come riserva)
- `eab355d` — 4 fix integrità replay (snapshot, tolleranza 0.05$, MFE upper bound, exit code reale)
- DESK_MODE: paper (invariato)
- Nessun bot riavviato manualmente da Claude/ChatGPT: gestito da desk-deploy.yml

## Rami
- `work/director-claude` HEAD: `40157c3` (Claude, non unire senza OK)
- `work/director-chatgpt` HEAD: `9255093` (ChatGPT, non toccare)
- `work/research-integrity` HEAD: `b229963` (ChatGPT, non unire)
- `rule-pool` HEAD: `4aabeb8` (merge + trigger pushato 22/10)

## Sequenza ricerca (ChatGPT → Claude)
- [x] 1. Review codice — fatto
- [x] 2. Integrità: complete_window, snapshot, RECON_TOL 0.05$, MFE upper bound, exit code — fatto (commit eab355d)
- [x] 3. Manifesto/hash learning_log (sola lettura, nessun dato grezzo) — fatto (commit 40157c3)
- [x] 4. R per regime BTC proxy e lato — Actions run 39741314265; risultati/limiti nel diario ChatGPT
- [ ] 5. Stagionalità A/B su score only (seasonality_audit.py già pronto)
- [ ] 6. Replay economico + validazione out-of-sample → raccomandazione all'utente

## Manifesto e step 4
- Manifesto `learning_log` attivato in sola lettura; schema event-aware verificato nel lavoro dello step 4.
- Misura step 4 completata in Actions run `39741314265`; non riavvia i bot. Risultati e limiti in `diario/2026-10-22_chatgpt.md`.
- Prossimi: step 5 stagionalità A/B in sola lettura; step 6 replay economico e validazione fuori campione.

## Regole inviolabili (sempre valide)
1. Nessun redeploy senza OK esplicito utente
2. DESK_MODE=paper finché utente non dice live
3. Nessuna modifica a strategia/soglie/prompt senza decisione utente
4. Il "cervello" (trade_history, lessons, errors, learning_log) non si cancella/azzera
5. API key solo nei GitHub Secrets
6. Mai toccare HI-TV/hitvprime (Strasburgo)
7. Repo pubblico: nessun segreto, nessun importo/saldo reale
8. Mai git push --force; non unire work/backend-singapore-audit; no push su stable/* e v0.5
9. Un solo autore alla volta per componente


## Aggiornamento 22/10/2026 — step 4 avviato, output Actions da recuperare

- Review Claude di `work/director-chatgpt` `ed3c65c` recepita: newline finale esplicitamente testato; `sys` e `all_trades` inutilizzati rimossi. 8 test manuali e `py_compile` passati.
- In `rule-pool`: analisi read-only (script `3c5853e`, test `27062d6`, workflow `a589635`); trigger dedicato in `595c032` che fissa il codice allo SHA `3c5853e`. Nessun trigger/deploy dei bot modificato.
- L'esecuzione di step 4 è stata attivata, ma il connettore GitHub qui non espone le run Actions da push né il loro riepilogo. Conteggi, hash letti e controllo d'invarianza dei container restano da confermare dall'output Actions/run ID. Non considerare ancora completata la misura.
- Diario dettagliato: `diario/2026-10-22_chatgpt.md` (commit `a7ab54b`).

## Aggiornamento 22/10/2026 — step 4 misurato (Actions run 39741314265)

- Workflow read-only concluso con success. SHA codice verificato: 3c5853e2f7463957199e4dc524395ebb24aa0a09. Controllo prima/dopo container Hawk/Bull passato: nessun cambio ID/immagine/StartedAt.
- Hawk: 130 trade eleggibili, 11 giorni, media +0,10594 R, IC bootstrap per giorno UTC 95% [−0,56208; +0,71016]. Bull: 36 trade, 11 giorni, +0,00500 R, IC [−0,50208; +0,56903]. Intervalli entrambi includono zero.
- Report regime/lato e limiti completi in diario/2026-10-22_chatgpt.md. La stratificazione per run/versione non è recuperabile dal log, troncato da GitHub; niente conclusioni per-run da questo output.
- Nessuna modifica o riavvio dei bot. Nessun dato grezzo pubblicato.

## Aggiornamento 22/10/2026 — step 5 preparato
- PR #1 `work/seasonality-audit`: https://github.com/alexiptv82/SuperBot-Trading/pull/1
- CI test Python 3.11: success (Actions run 39747560290); test locale 12/12 e YAML workflow validati.
- Workflow dedicato è sola lettura, esegue cutoffs tecnici 60/63 per descrivere l'effetto sul punteggio. Non equivale alla confidenza Claude e non misura redditività.
- Nessun merge o run sul VPS. Attende review Claude sul workflow server-side; dopo il merge il trigger dedicato eseguirà il report aggregato.
- Diario dettagliato: `diario/2026-10-22_chatgpt.md` (commit 142cc297).
