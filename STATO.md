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
