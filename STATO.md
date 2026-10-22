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
- [ ] 4. R per regime (down/flat/up) e lato (long/short) — richiede manifesto attivato sul VPS
- [ ] 5. Stagionalità A/B su score only (seasonality_audit.py già pronto)
- [ ] 6. Replay economico + validazione out-of-sample → raccomandazione all'utente

## Per attivare il manifesto (step 4)
1. Merge `40157c3` da work/director-claude in rule-pool (come deploy precedenti)
2. Aggiornare `deploy/desk-manifest.trigger` con sha del commit in rule-pool
3. Push su rule-pool → GitHub Actions gira il manifesto (sola lettura VPS)
4. Hash + conteggi visibili nelle annotations — usarli come verifica per step 4

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
