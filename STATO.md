# STATO CORRENTE SuperBot-Trading — 26 ottobre 2026
Fotografia sintetica per ChatGPT Work, chat normale e Claude. Per lo storico precedente consultare i commit di questo file e ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md. Protocollo: SINCRONIZZAZIONE-WORK-CHAT.md.

## Runtime PAPER (NON toccare senza nuova autorizzazione)
- Hawk + Bull in PAPER sul VPS Singapore, codice **35f08cf** (deploy 26/10/2026 sera — trigger fcea423, run #42, DEPLOY OK). Precedente: 63641f70 (Fix B).
- Fix B AI Profit Guardian V1 attivo: `profit_guardian.py` + `portfolio_alert.py` in produzione.
- Capital Management V1 integrato ma con DESK_CAPITAL_V1=off, non abilitare senza OK dell'utente.
- Vincolo immutabile: nessun reset di trade_history, learning_log, lessons.md, errors.md.
- rule-pool HEAD: `f76c5b108300b8b2efe37e2dfb99811ba61499cc` (trigger deploy Brain, 26/10/2026 17:xx UTC).

## App Dashboard — DEPLOY TAB BRAIN (26/10/2026, SHA a9df40e8)
- **SHA deployato**: `a9df40e87c1cdb4b3b3fbb1e78813397223e0b6f` (main, 26/10/2026)
- Deploy confermato dall'utente: tab 🧠 BRAIN visibile e funzionante nell'app.
- Commit su main: 9559ee5c (brain_view.py + BrainDashboard.js) + a9df40e8 (test, CI, server, frontend).
- Mount aggiunto in run_app(): `-v /opt/superbot-desk-data/brain:/opt/superbot-desk-data/brain:ro` + `-e BRAIN_DATA_DIR=...`
- Tab BRAIN in PAPER_TABS (sola lettura, 6 card, polling 30s). LIVE_TABS non modificato.
- Endpoint: GET `/api/brain/status` (autenticato, no-cache, SQLite :ro, deadline 2s).

## AI IN OMBRA (DeepSeek) — ATTIVO DAL 21/10/2026
- Container `superbot-ai` su VPS Singapore, **Up 5 days (healthy)**, riavvii: 0.
- Commit installato: `53111b30b633add0869c5eea031d72739f438261` (21/10/2026 08:13 Roma, OK utente).
- Modalità: **ombra pura** (`applied: False`, nessun ordine reale né virtuale verso exchange).
- Conto virtuale separato (`PaperAccount`): equity di partenza 1000 $.
- Report 26/10 ore 12:01 UTC (workflow run #5, SUCCESS):
  - **Cicli completati:** 504 | **Chiamate DeepSeek:** 504 ok / 0 fallite
  - **Equity virtuale:** 724.78 $ (partenza 1000 $, -275.22 $ = -27.5%)
  - **Trade chiusi:** 97 (+ 7 parziali) | vincenti: 30/97 (31%) | netto: -274.97 $
  - Win rate 31%, bias LONG forte (65 long vs 32 short). Da monitorare.

## Fix P1 e P2 — DEPLOYATI (25/10/2026, inclusi in 63641f70)
- **P1 sbias LONG**: `backend/desk/signals.py` — rimbalzo RSI 1h.
- **P2 smart fallback**: `backend/desk/cli.py` + `brain.py` — flag `_claude_responded`.

## Fix B AI PROFIT GUARDIAN V1 — DEPLOYATO (26/10/2026)
- Deploy: trigger `6f73e800`, APPROVED_SHA=`63641f7059a977368f8bb8aecc517f7a7c74cbce`, Actions SUCCESS.
- Moduli attivi: `backend/desk/profit_guardian.py`, `backend/desk/portfolio_alert.py`.

## AI Write unificato — 26/10/2026
- `claude-write.yml` rinominato "AI Write": supporta `claude/claude-write.trigger` e `chatgpt/chatgpt-write.trigger`.

## Director V1 — COMPLETATO (26/10/2026)
- Branch: **`work/director-v1-unified`**, commit `d2b351e0`.

## Fix Segnali V2 — DEPLOYATO (26/10/2026 sera, 18:31-18:33 UTC)
- OK esplicito dell'utente al redeploy: "ok, procedi con il deploy" (dopo un primo tentativo bloccato dal controllo di sicurezza
  della sessione, che chiedeva una conferma diretta).
- Deploy: trigger `fcea423` (`sha=35f08cf8d16097d8ca365892a3f9a9ef23996709`), workflow `Sala segnali - deploy` run #42 = SUCCESS.
  Esito dal log: PAPER_AND_RISK_ENVIRONMENT=PASS, RUNTIME_BASELINE_SOURCE=PASS, backup del cervello verificato, hawk e bull
  healthy, una sola istanza per bot, versione dichiarata `35f08cf` da entrambi, PAPER_AND_CAPITAL_ENV_VERIFIED_AFTER_DEPLOY=PASS.
- Codice: ramo `work/fix-segnali-v2` (commit `b93196b`) unito in `rule-pool` col merge `35f08cf`. Il commit `767bee0` sul ramo
  `ccr-999de027-0stnyt` era basato su `main` (codice bot vecchio): NON usarlo, NON unirlo.
- Contenuto: `seasonal.py` formula additiva (0.60 mensile + 0.40 ciclo), curva del ciclo morbida (mese 30 = -0.40), freno
  di mercato (`btc_return_3d`); `seasonal_v1.py` = vecchia formula byte-identica per gli script di audit;
  `signals.py` passa `btc_return_3d`; `cli.py` solo Bull: tetto rischio SL aperto 160$ (la prima posizione passa sempre) e
  nessun nuovo SHORT se BTC +2% in 24h. BTC ott 2026: da 5 SHORT a 5 LONG; 1 nov BTC/ETH: da 9/10 SHORT a 6 LONG.
- NON cambiato: `_daily_loss_exceeded` (in paper lo stop giornaliero e' quello del motore, equity -10%; un test lo fissa);
  engine, brain, prompt di Claude, soglie di confidenza, R:R, leve, margini, DESK_MODE (paper).
- Baseline del workflow di deploy aggiornata a `63641f7` prima del deploy (commit `5151b01`); la prossima volta andra'
  riportata a `35f08cf` (la guardia `runtime_version_mismatch` pretende la versione in esecuzione).
- CI: `desk-ci` run 91 e "Capital Management V1" su `35f08cf` falliscono solo sui test gia' rossi sul codice live prima del
  fix (`test_uptrend_scores_long_and_downtrend_scores_short`, `test_daily_trend_present_with_real_daily_bars`); gli step
  dopo il primo fallimento (inclusi i test nuovi per-file) vengono saltati: rieseguiti a mano con Python 3.11 = verdi.
- Verifica post-deploy (desk-status 18:36 UTC): primo ciclo dei bot col nuovo codice completato 18:33 UTC, 0 posizioni aperte,
  conti e storico del giorno invariati, Hawk e Bull ancora fermi per stop giornaliero (si sblocca col nuovo giorno UTC).
- **Reset portafogli + riavvio bot (utente, 26/10 ~18:30-18:55 UTC, dopo il deploy)**: Hawk e Bull ripartiti da 1000 in un nuovo
  run, su `35f08cf`, healthy, PAPER. Cervello intatto: `learning_log.jsonl` continua a crescere (nessun azzeramento) e
  `trade_history`/lessons non toccati. Primo ciclo 18:55 UTC: entrambi hanno aperto **DOT SHORT SCALP** (conf 66, 20x,
  stop ~1,5%), `source=rules`. In entrambi i log: "[Fallback] Claude non disponibile: decisioni affidate alle regole" =
  in questo momento decidono le REGOLE, non Claude. La prova della nuova stagionalita' vale quindi per punteggi e regole,
  non per il giudizio di Claude. Causa non ancora verificata (ipotesi: tetto giornaliero `DESK_DAILY_CAP_USD`, finestra del
  calendario Claude, o chiave): controllo di sola lettura disponibile con `desk-claude-finestra` / `desk-diag`.
- Nota sul tetto Bull (precisazione): il tetto limita il RISCHIO SL totale (160$), non il numero di posizioni. Con 350$ x 15x x
  3% (157$) passa una sola posizione; con le dimensioni attuali del fallback (165$ x 20x x ~1,5% = ~51$) ne passano fino a tre.
- Da osservare: da domani i candidati rifiutati dal Bull compaiono nel registro come `rifiutata:rischio_aperto_bull` e
  `rifiutata:veto_short_rimbalzo_btc`; il bonus stagionale compare nel `why` dei segnali ("stagionalità long/short +N").
  Nota gia' presente prima del deploy: "[Fallback] Claude non disponibile: decisioni affidate alle regole" nei log di entrambi.
- Rollback: immagine `superbot-desk:rollback-<data>` creata dal deploy, oppure trigger con
  `sha=63641f7059a977368f8bb8aecc517f7a7c74cbce` (rimettere prima la baseline del workflow a `35f08cf`).

## Task aperti (in ordine di priorità)
0. **Osservazione Fix Segnali V2** (24-48h in paper): segnali LONG/SHORT di Bull e Hawk, rifiuti `rifiutata:*` di Bull, nessun nuovo errore nei log (desk-status).
1. **Osservazione Fix B**: finestra 24-48h in paper (sola lettura, desk-status)
2. **Punto 4 — AI shadow**: in osservazione. Analisi dati disponibile (504 cicli, 5 gg).
3. **Punto 5** — Capital Dashboard V1 (`work/capital-dashboard-v1`)
4. **Punto 6** — Profit audit read-only (`work/profit-audit-readonly`) — pronto, serve review + OK utente
5. **Punto 7** — A/B proposals (`work/profit-correctness-proposals`)
6. **Punto 8** — Capital Management V1 activation (decisione utente)
7. **Director V1 review**: run test su `work/director-v1-unified`, decidere integrazione Pilot↔Arbitro
8. **Market Regime + Episode Memory**: review Claude su `work/market-regime-episode-memory`

## Claude — collaboratore permanente (25/10)
- Claude (Claude Code, Sonnet 4.6) attivo come collaboratore permanente.

## Documenti di riferimento AI
- `claude/protocollo-collaborazione-ai.md` — regole collaborazione ChatGPT+Claude, onboarding
- MANUALE-OPERATIVO.md (sezione 8: passaggio di turno tra AI)

## Riferimenti
- LEGGIMI.md, MANUALE-OPERATIVO.md, SINCRONIZZAZIONE-WORK-CHAT.md.

## Storico deploy
| Data | SHA | Contenuto |
|---|---|---|
| 25/10/2026 | 886b30f | Fix P1 (sbias LONG) + Fix P2 (smart Claude fallback) |
| 26/10/2026 | 63641f70 | Fix B (AI Profit Guardian V1) |
| 26/10/2026 | **a9df40e8** | Tab 🧠 BRAIN live (port su main + mount brain :ro) |

## Brain Pilot V1 — SHA 1f2edeb6 ATTIVO (26/10/2026)
- SHA container: `1f2edeb6182029adc96ba7218ad145a7503472a3` (ATR sizing, daily stop 20%, thesis debate, context.py).
- Upgrade autorizzato utente 26/10. Hawk/Bull NON toccati.

## Brain Portfolio Dashboard — LIVE (26/10/2026 ~17:16 UTC)
- Tab 🧠 BRAIN visibile e funzionante nell'app. Confermato dall'utente alle 17:16.
- Dati visibili: equity $992.12, cash $669.37, P&L -$7.88 (-0.79%), 15 cicli, 4 posizioni SHORT aperte.
- Sviluppo: ChatGPT Work (rule-pool PR#11) → port controllato su main + deploy: Claude Sonnet 4.6.
- CI brain-view-ci.yml: reader Python 3.10/3.11 (26 test) + pwa React (4 test + build) su main.

## Chiarimento Brain — autonomia e apprendimento (26/10/2026)
- Verifica codice1f2edeb6: unico conto PAPER, decisioni DeepSeek vincolate da prompt e guardrail; engine condiviso, selettore Hawk/Bull non usato.
- Storico persistente, ma solo ultimi10 realizzi forniti al modello; apprendimento automatico/lezioni persistenti non implementati nel Brain.
- Mitigazione bias bull/bear attiva secondo runtime documentato; efficacia da misurare con trade post-upgrade e regime. Quattro SHORT non certificano la correzione. Nessun intervento runtime.

## IN_CORSO — Brain Learning V1 (ChatGPT Work, 26/10/2026)
- Implementazione pronta per review sul branch work/brain-learning-v1, base f76c5b108300b8b2efe37e2dfb99811ba61499cc. PR draft#12, SHA e871ccff819e7d5afb54e5c4a498a58e9a1e2c00.
- Memoria episodica persistente, aggregazione parziali, lezioni con supporto storico/validazione cronologica, recupero nel prompt e audit delle lezioni inviate. Nessun retraining o modifica automatica dei limiti.
- Test locali104PASS+1Docker skip,26regressioni dashboard PASS; CI finale40361447734 SUCCESS (Python3.10/3.11+Docker+probe migrazione5posizioni).
- Prossimo: Claude review docs/brain-learning-v1-review.md; componente in review, un autore alla volta. Nessun merge/deploy autorizzato. Runtime invariato rispetto allo stato documentato, non riverificato sulVPS in questa sessione.

## Research Console — valutazione recupero (ChatGPT Work, 26/10/2026)
- Analizzato alexiptv82/SuperBot-Research-Console, main bd9b04277dda8ed6a1ab310220a9b96e6234a0ed. Solo lettura; nessuna integrazione o avvio collector.
- Recupero consigliato: controlli qualità/provenienza, separazione ricerca-validazione, registro esperimenti/report. Riutilizzo selettivo adattato a Brain, senza duplicare journal/dedup già presenti nella PR#12.
- Collector multi-venue100ms solo candidato ricerca futura: orizzonti100ms–30s, diverso dal Brain15m. FrozenAnalysisEngine NOT_CONFIGURED; harness riproduzione ancora placeholder;11449righe golden pending. Report36h respinge alpha direzionale sotto hurdle15bps; candidati execution non strategie certificate.
- DB committato letto mode=ro:23sessioni(11OLD36_REFERENCE+12NEW36),36QA runs. Nessun raw ZIP/Parquet nel checkout. Registri QA non equivalgono a storico trading né conferma indipendente dei risultati.
- Prossimo: concordare recupero selettivo insieme al ponte storico Hawk/Bull→Brain; nessuna nuova implementazione richiesta in questa analisi. Runtime e PR#12 invariati.

## IN_CORSO — Recupero Research + esperienza Hawk/Bull (ChatGPT Work)
- OK utente 26/10: implementazione recupero selettivo qualità/provenienza/validazione e ponte storico verso Brain. Componente riservato a ChatGPT Work su work/brain-learning-v1 (PR#12, base e871ccff819e7d5afb54e5c4a498a58e9a1e2c00).
- Fonti lette soltanto, modelli/versioni separati, nessun merge/deploy/trigger o avvio collector. Il diario di correzioni documenta intenzioni, non certifica profitti. Prossimo checkpoint: codice/test e handoff review.

## Recupero Research + esperienza Hawk/Bull — implementato per review
- PR#12 aggiornata su work/brain-learning-v1, commit a175ae6d455f694f8c24149eb6daa1422520c819. Componente ChatGPT Work; prossimo ruolo Claude review.
- experience.py: builder offline readonly su copie PAPER, hash/provenienza e QA, identità bot/run/versione, parziali aggregati, confine ricerca/validazione fisso e pacchetto immutabile atomico. Runtime legge solo esperienza preparata nella propria cartella, senza accesso ai dati Hawk/Bull.
- knowledge.py: note documentate separate da esiti; catalogo iniziale3note (contratto bull/bear, Profit Guardian fonte SHADOW ONLY, limiti ricerca microstruttura). Nessuna efficacia presunta o segnale ricostruito.
- Test locali135PASS+1Docker skip,26regressioni dashboard PASS; CI40380945666 SUCCESS sul commit finale (Python3.10/3.11, build/smoke Docker e probe migrazione5posizioni). Nessuno storico reale acquisito/importato, seed installato o interventoVPS. Nessun merge/deploy/riavvio/trigger operativo.
- Review: docs/brain-experience-transfer-review.md. Dopo review: acquisizione readonly di copie PAPER con provenienza, preparazione/controllo seed e deploy Brain separatamente autorizzato; i dati mancanti non vanno inventati.

## IN_CORSO — Dettagli posizioni BRAIN PWA (ChatGPT Work)
- Mandato utente: mostrare margine e leva per capire il dimensionamento. Riservati brain_view.py, BrainDashboard.js e relativi test su work/brain-position-details da main a9df40e87c1cdb4b3b3fbb1e78813397223e0b6f.
- Sola osservazione: nessuna modifica rischio/size/leva dei bot, nessun deploy o trigger. Verifica sizing dal codice Brain installato documentato1f2edeb6; valori live non ancora riletti.

## Dettagli posizioni BRAIN PWA — pronti per review
- Branch work/brain-position-details da main a9df40e8; PR draft#13, commit7a3348fbf5b827aaf1295aa077153a36ab451298. Componente ChatGPT Work, separato dalla PR#12 Brain Learning.
- API reader aggiunge margin(total_margin), leverage salvata, notional_entry(entry×qty), floating_margin_roi_pct e margin_in_use totale. UI mostra margine/levа/esposizione/ROI lordo. Mancanti non inventati; DCA e parziali usano margine/quantità residui.
- Locale:31testreader/API+7componenti PASS, buildReact PASS; sintassi3.10 e byte pubblicati verificati. CI40382342014 in corso.
- Analisi sizing dal codice1f2edeb6: budget stop1%equity ×size_pct ×conviction/100, poi cap/fee/slippage/liquidazione. Margine100$ è un tetto, non importo fisso. Nessun valore posizione live rilevato; perdita1$ da sola non prova sottodimensionamento.
- Nessuna modifica size/rischio/leva/strategia, bot, dati, deploy o trigger operativo. Nessun merge o riavvio. Prossimo: review e rilascio app separato dal runtime bot.
