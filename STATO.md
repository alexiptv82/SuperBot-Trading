# IN_CORSO — rilascio classici autorizzato il 28 ottobre 2026

ChatGPT Work prenota backend/desk classici, test e procedura di rilascio sul branch work/classics-sizing-direction-20261028, base dd04cc6. L'utente ha autorizzato esplicitamente: «adesso sistema, riavvia, falli partire bene». Sono autorizzati implementazione, test, integrazione e riavvio/deploy dei SOLI Hawk/Bull PAPER, subordinati a backup verificato e controlli di continuità. Nessuna autorizzazione Brain o reset.

Direzione: candidati tecnici continui come nelle prime run, AI con opportunità additive e veto esplicito per simbolo; nessun silenzio AI che blocchi globalmente la ricerca. Conservati minimi margine Hawk100/Bull150 e massimi250/350, slot10/3. Il minimo20x non è più obbligatorio: leva scelta in funzione di stop/rischio entro tier, senza aumentare proposte troppo piccole. Gestione scalp in ore, riferimento24h e prolungamenti motivati limitati; tutela del netto e liberazione slot, senza imporre leva35–40x o quota di trade. Le cifre di profitto citate dall'utente sono esempi, non target garantiti.

Prima si completano codice/test e diff; poi preflight, backup/restore, deploy con SHA fissato e postflight. Baseline ultima misurata73e9242, PR22 ancora non distribuita al momento dell'autorizzazione. Brain e archivi intatti.

---
# Audit tecnico classici — 28 ottobre 2026, checkpoint successivo

## Fase conclusa: analisi della prima run e della scarsa attività attuale

- Richiesta utente: capire cosa distingue la prima run positiva e recuperare il comportamento operativo; Breakout sospeso come priorità. Eseguita analisi, nessuna modifica ai parametri o al trading.
- Ricalcolati 357 gruppi posizione dal dataset forense 27/10: Hawk positiva è #2 (+1090,6136 PAPER,76 posizioni), Bull #1 (+770,7485,17 posizioni); Hawk #1 è snapshot vuoto. La V2 era già nel codice l'11/10. Ingressi golden attribuiti soprattutto a7ced3a6/9fa667f, nessuno a5818aee; attribuzioni iniziali inferite dai deploy.
- Job readonly esistenti rieseguiti senza push su rule-pool: run40655263204 attempt2/job122787111578 e run40634091693 attempt2/job122788147538 SUCCESS. Alle12:24 Roma: entrambi73e9242 healthy/PAPER,1 posizione ciascuno,nessuna chiusura della run,macro senza veto,nessuna pausa/orario/HALT nei log attuali.
- Alle12:27 Roma snapshot pubblico26/26 valide,0errori,0segnali sopra soglia tier; NEAR63/TIA62 contro70. Fotografia singola,non replay identico al ciclo.
- Differenza verificata:357/357 ingressi storici source=rules; oggi DeepSeek sostituisce il percorso regole nella sua fascia quando la risposta è valida, anche vuota/hold/skip. Prova locale sul codice73e9242: stesso segnale sintetico85 apre con sole regole o AI indisponibile, non con AI valida vuota/hold/skip. Non quantificato il profitto o il numero di occasioni realmente escluse oggi.
- PR22dd04cc6 rimane non distribuita. Minimo20x incompatibile con le due aperture odierne identiche(ETH10x/XAG15x); non equivale a tornare alla prima run. Non applicare insieme variazioni sizing e selettore senza separarne gli effetti.
- Rapporto tecnico completo consegnato all'utente con fonti,riconciliazioni e piano: confronto su stessi snapshot tra generatore storico,generatore corretto e selettoreAI; candidati tecnici sempre osservabili e opportunitàAI additive,senza aggirare veto/limiti. Architettura proposta,non implementata.
- Nessuna causa unica dimostrata del crollo storico. Prime perdite precedono FixA/P1/DeepSeek; run tarde talvolta più attive ma lordo medio molto inferiore. Non abbassate soglie e non reintrodotti vecchi difetti contabili per replicare i profitti.
- Prossima fase: eventuale preparazione di confronto osservazionale/pipeline candidati sul ramo di lavoro,dopo revisione del rapporto. Merge/deploy richiedono sempre OK esplicito; Brain intatto, nessun reset o doppia istanza.

---
## Checkpoint precedente: audit PR22

# Checkpoint ChatGPT Work — 28 ottobre 2026

## PR #22 — audit offline concluso, nessun rilascio autorizzato

- ChatGPT Work ha completato la fase codice/test dei classici, incaricata esplicitamente dall'utente. Branch `work/classics-sizing-direction-20261028`, PR #22 aperta e non mergiata. Commit verificato: `dd04cc6c017c779f4fd45b12c985bb2936cb58c1`, parent `0640bc5ac522dad6278bb58707781bd1b096cce8`; base PR `rule-pool` a `835a4f25a676f0bcab38a28b75e23402cefe298b`.
- Nuove aperture richieste: Hawk 100–250 USD e massimo 10 slot; Bull 150–350 USD e massimo 3 slot. Leva minima desiderata 20x, subordinata a stop/liquidazione e limiti tecnici. Proposte sotto minimo rifiutate e motivate, mai maggiorate automaticamente. Nessuna quota obbligatoria di trade.
- Risolte le fixture incompatibili: nuove proposte conformi; posizioni storiche a 10x conservate nei test di gestione. Verificati caricamento, DCA, parziali, stop, split pendenti, memoria e Salvadanaio.
- Corretti difetti preesistenti: parametri di ingresso non finiti; overflow della leva nel parser; rispetto congiunto di tetto globale e tier; margine complessivo anche per DCA; blocco di nuova esposizione DCA/split dopo stop giornaliero o kill-equity.
- Risultati: **346 test pertinenti PASS + 91 test backup/ripristino/guardie PASS**, compile/diff/YAML PASS. CI Python 3.11, run `40675333384`, job `122772168497`: SUCCESS, inclusi build Docker e controllo dei file Brain invariati. L'intera suite backend non è certificata: la raccolta generale include dipendenze app assenti localmente e un riferimento preesistente a `fetch_daily_history` rimosso.
- Ultime prove runtime lette nei log GitHub, non nuove misurazioni VPS: run `40661841445`, 28/10 alle 10:07 Roma (09:07 UTC), classici `73e9242`, PAPER e macro osservazionale; run `40641318508`, 07:01 Roma (06:01 UTC), Brain `a914803`, PAPER, pausa attiva e 3 posizioni. Non dedurre da queste prove lo stato minuto corrente.
- Nessun intervento su VPS, database, memoria AI, storici o posizioni. Nessun reset, doppia istanza, modifica Brain, merge o deploy. PAPER obbligatorio. Gli esiti offline non provano redditività futura.
- L'utente ha autorizzato espressamente la pubblicazione di questo checkpoint dopo il precedente blocco automatico del push al diario. Tale OK riguarda **solo il diario**, non merge o deploy.
- Prossimo passo: revisione dell'utente. Merge e futuro deploy richiedono OK esplicito separato; prima di qualsiasi rilascio servono controllo runtime e backup verificato. Brain richiede sempre autorizzazione distinta.

---
## Archivio storico — fotografia del 27 ottobre, non stato attuale certificato

# STATO CORRENTE SuperBot-Trading — 27 ottobre 2026
Fotografia runtime verificata alle **20:02 Roma / 19:02 UTC**, postflight40565394446 SUCCESS. Fonte: workflow e verifiche dirette sul VPS, non HEAD del ramo assunto come runtime.

## IN_CORSO
Nessun rilascio in corso. ChatGPT Work ha concluso rollback classici e dashboard approvati dall'utente. Prossimo passo: osservazione, incluso primo rollover Salvadanaio alle00:00UTC. Nuovi deploy richiedono un nuovo OK.

## Runtime classici e app — LIVE PAPER
- **Hawk e Bull classici**: SHA `3abf1f808b09bf9066d96a1d16f945d65601ba02`, code_version `3abf1f8`, healthy/restart0, istanza singola, PAPER. Rollback selettivo5818 con anti-biasLONG/SHORT e bugfixmotore (barre chiuse, ingresso, DCAstopnonallargato); soglieA/B60,C70; Hawk10slot/Bull3; stopgiornaliero12%; sizingstorico. P1/regime/Guardianavanzato esclusi. Posizioni2Hawk/3Bull conservate, run invariata.
- **Salvadanaio**: policy `salvadanaio-only-v1` READY in entrambi, CapitalV1OFF; eccedenza netta oltre1000operativi, no reintegroperdite, pending escluso dal saldo protetto. Journal separato, vecchioV1intatto. Primaattivazione senza credito retroattivo inventato; primo rollover live non ancora osservato. Dashboard mostra saldo/accreditigiornalieri/pending in sola lettura.
- **App**: SHA `56dc4bb62f64024d1ea7e5bc84602fbf52ea4ace`, main; HTTPAPI/frontend200, manifestocodice/frontend coerente, readerSalvadanaio realePASS. Non ha DockerHEALTHCHECK.
- Deploybot40564697020 e app40565004065 SUCCESS; postflight40565394446 SUCCESS: sourcehash, archiviprefixhash, run e budget preservati; backup nuovo journal con prova restorePASS. Nessunreset.
- Backup botpredeploy `/opt/superbot-backups/bots-20261027-185733-deploy`, postflight `bots-20261027-190211-classici_vault_postflight`; DBapp `superbot-deploy-20261027-190057.db`. Rollbackimmagine `superbot-desk:rollback-20261027-185733`, app `superbot:prev`, frontend `build.prev`. Ripristinare dati richiede decisione, non usarlo come reset.
- HEADrule-pool `183fdb7b1bf25140d2d236c98e50262b5cd3411b` contiene trigger/verifier successivi: **runtimebot resta3abf**. Main56dc. Triggerverifier disarmato, nessun forcepush o merge tra main/rule-pool.

## Brain e altri servizi — NON TOCCATI
- Brain adattivi Hawk/Bull: SHA `129547ed43a9aaec935df31102bb4e8016c38e7c`; Brain precedente `1f2edeb6182029adc96ba7218ad145a7503472a3`. Healthy/PAPER. IDcontainer e StartedAt uguali al preflight: nessun riavvio. Stesso confronto passato per tutti gli altri container non coinvolti.
- Datiadattivi `/opt/superbot-brain-adaptive/brain-{hawk,bull}`, ledger condiviso e budget invariati; seed backtest sintetici/nonverificati restano contesto distinto dall'esperienzaoperativa. Storico classico non importato automaticamente, nessun retraining dichiarato.
- TabBRAIN e mountRO dell'app conservati. HI-TV mai contattato. Segreti, DESK_MODE e conti reali non modificati.

Dettagli: `diario/2026-10-27_chatgpt.md` e `diario/ROLLBACK-CLASSICI-2026-10-27-DIFF-FINALE.md`.

---
**ARCHIVIO DI CONTINUITÀ:** le sezioni sottostanti sono cronologia conservata. Le descrizioni vecchie di codice attivo, Guardian, P1/P2 e stato deploy sono superate dalla fotografia sopra; non usarle come istruzioni operative correnti.

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

## Regime di mercato per Hawk e Bull — ramo `work/hawk-regime-v1` (NON deployato, 26/10 notte)
- Stato: codice pronto e testato (31 test del regime verdi; nel resto della suite restano solo i 2 test gia' rossi sul codice live
  `test_uptrend_scores_long_and_downtrend_scores_short` e `test_daily_trend_present_with_real_daily_bars`, probabilmente fermi ai pesi
  di prima di P1). NIENTE merge in `rule-pool` e NIENTE deploy senza OK esplicito dell'utente. Interruttore: `DESK_REGIME_V1=0`.
- Contenuto del ramo: `regime.py` (regime su/giu'/laterale/inversione da BTC+ETH, ampiezza, momento BTC 24h), filtro dei lati in
  apertura (short non in salita ne' dopo un crollo BTC < -3%/24h; long solo se il mercato sale o gira al rialzo), tetto Bull 250 (era 160),
  `signals_pre_p1.py` (copia congelata dei punteggi di prima di P1, usata SOLO da banco e audit).
  **Profilo di produzione = solo filtro** (ratchet e uscita per inversione spenti, laterale senza punti extra); si riaccendono con
  `DESK_REGIME_RATCHET=1`, `DESK_REGIME_FLIP=1`, `DESK_REGIME_RANGE_EXTRA=n`.
- **Scoperte della serata (da non perdere)**:
  1. La modifica **P1** (commit `635b964`, 25/10 19:38 +01, "sbias scoring LONG") e' in produzione dal deploy `63641f7` (NON dal deploy
     `35f08cf`): trend 4h da 20 a 14 punti, trend 1d da 15 a 10, +10 ai long per "rimbalzo RSI". Nel registro dei bot il trend 4h vale 20
     fino al 25/10 sera e 14 da tutte le aperture del 26/10. I giorni buoni di Hawk (12-24/10) sono con i pesi vecchi.
  2. Il trend 1d era ASSENTE nei bot fino al 22/10 (0% delle aperture; le barre 1d vere sono arrivate col fix del 21/10 e
     si vedono dal 24/10: 80%, poi 100%). Il banco storico lo ha sempre avuto.
  3. Hawk 12-26/10: 247 aperture, 13 long e 234 short. Rifacendo col banco i trade veri (stessi prezzi, stop, TP, leva, margine) il risultato
     e' praticamente lo stesso (85% di uscite uguali): il MOTORE e' fedele. Le APERTURE del banco invece non coincidono con quelle dei bot
     (solo ~15% in comune): pesano le chiamate a Claude (nei cicli in cui risponde le regole non aprono; 221 chiamate in 14 giorni),
     i candidati scartati dal bot (confidenza bassa, troppe posizioni, stop giornaliero) e un trend 4h che differisce nel 25% dei casi.
     Il banco NON si usa per valori assoluti ne' per "cosa aprirebbe il bot".
  4. Regime applicato ai trade VERI di Hawk (stessi 228 trade, effetto del solo regime): solo filtro **+266**; filtro con laterale senza punti
     extra **+420**; blocco degli short dopo un crollo vale +250 a -3% (a -2%: piu' alto, ma e' un solo episodio); protezione dello stop
     (pareggio a 1R + traino) **-340** (accorcia le vincite grosse); uscita per inversione ~0; long anche se il mercato non sale: peggio.
     Il filtro non riduce molto le aperture (-7%). Limite: non misura i long che il filtro farebbe aprire in piu' (si vedono solo in paper).
- Strumenti di sola lettura creati (workflow su `rule-pool`, partono solo cambiando il file `deploy/*.trigger`):
  `desk-backtest` (banco storico su candele pubbliche), `desk-fedelta` (legge in SOLA LETTURA il `learning_log.jsonl` di Hawk via SSH con
  impronta del server verificata e lo confronta col banco; opzioni `match=` e `overlay=1|2`). Script in `deploy/scripts/desk_backtest.py`,
  `desk_fedelta.py`, `desk_fedelta_leggi.py`.
- **Decisioni che spettano all'utente**: (1) pesi del punteggio: classici (prima di P1) oppure P1; (2) deploy del regime "solo filtro";
  (3) tetto Bull 250 (nel ramo); (4) rinnovo del calendario di Claude prima dell'8/11 (dopo, Claude resta spento).

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
- **Perche' i bot sembrano "frenati" (diagnosi 26/10 sera, desk-claude-finestra #3, sola lettura)**: il tetto giornaliero di Claude
  (0,70$ a bot, ~0,05$ a chiamata = ~14 chiamate) e' stato consumato tra le 03:33 e le 05:35 ora svizzera (Hawk 0,67$, Bull 0,68$):
  da allora, per tutto il giorno, decidono le REGOLE (soglie 63 altcoin / 60 BTC-ETH). Calendario Claude = nessuno (`mode: none`).
  Il reset dei portafogli NON azzera il budget (conto per giorno). Hawk e Bull con le regole prendono le stesse decisioni
  (stesso DOT SHORT, stesso prezzo e stop; cambia solo il margine: Hawk 100$ cappato, Bull 165$): le differenze vengono dai prompt.
- Effetto della stagionalita' V2 sui punteggi (calcolo offline, 26/10): altcoin SHORT +2 -> LONG +1 (SHORT perde 2 punti);
  BTC SHORT +5 -> LONG +5, ETH SHORT +4 -> LONG +4. Dal 3/11: altcoin SHORT +3 -> LONG +2; BTC SHORT +9 -> LONG +6; ETH SHORT +10 -> LONG +6.
  Esempio reale: APT 62 contro soglia 63 (con la vecchia formula sarebbe stato 64). E' un freno secondario sugli SHORT, voluto dal fix.
- Opzioni in discussione con l'utente (nessuna applicata): (A) finestre/tetto di Claude (operativo, `desk-schedule`, senza riavvio:
  es. una finestra nelle ore di mercato invece di spendere il budget di notte); (B) alleggerire il peso della stagionalita';
  (C) decisioni diverse tra Hawk e Bull anche in fallback; (D) rilevamento del cambio di mercato (backlog: Market Regime + Episode Memory).
- **Calendario di Claude APPLICATO (26/10 ~19:17 UTC, scelta dell'utente "va bene cosi")**: una finestra al giorno 14:00-22:00 ora svizzera,
  uguale per Hawk e Bull, 14 giorni (26/10 - **8/11**). Ramo `work/claude-finestra-14-22` unito in `rule-pool` col merge `e70c474`;
  workflow `calendario di Claude` run #4 = SUCCESS (file scritto nei dati di entrambi i bot, 14 finestre, i bot lo leggono:
  `mode: calendar`). Nessun riavvio, nessuna modifica a strategia/soglie/prompt. Verifica (desk-claude-finestra #4): "[FINESTRA] inizia
  una finestra di Claude: budget azzerato" e prima chiamata a Claude riuscita su entrambi (Hawk 6 decisioni, Bull 5).
  **DOPO L'8/11 CLAUDE RESTA SPENTO finche' non si aggiunge un nuovo calendario**: rinnovare prima (file `deploy/claude-schedule.json`,
  si applica da solo al merge in `rule-pool`). Ogni finestra ha il suo budget da 0,70$ a bot (~14 chiamate = ~3,5h a cicli di 15 min):
  la parte finale delle 8 ore puo' restare alle regole; opzione per coprirla: due finestre consecutive 14-18 e 18-22 (fino a 1,40$/bot/giorno).
  Correzioni: il "giorno" del budget senza calendario e' UTC (reset 01:00 ora svizzera invernale); lo script desk-claude-finestra mostra
  l'ora svizzera con +1h di troppo dal cambio d'ora del 25/10 (CH=7200 fisso).
- Osservazione 19:17 UTC: Hawk e Bull hanno entrambi 3 SHORT scalp aperti dalle regole (DOT, APT, OP; stessa direzione, correlati);
  Claude li ha lasciati ("tre short correlati gia' aperti: nessun nuovo ingresso"). Il tetto di rischio Bull (160$) non li ferma perche'
  ognuno vale ~50$ di rischio a stop. Possibile ritocco (decisione dell'utente): limite di posizioni nella stessa direzione.
- **ANALISI STORICO 12-26/10 (357 trade chiusi, paper; workflow di sola lettura `desk-storico`, trigger `deploy/desk-storico.trigger`, rieseguibile)**:
  1) 96% SHORT (338 su 353); i LONG sono 15, 1 sola vincente, netto circa -514$: il lato long non ha mai funzionato.
  2) Giorni buoni (Hawk 12/10 +515$, 15/10 +309$, 14/10 +260$, 24/10 +245$): BTC in discesa regolare (-1..-2% a 24h), tante uscite a TP.
     Giorni cattivi: BTC piatto o in rimbalzo, o dopo un crollo (short con BTC < -3% a 24h: 15 trade, 13% vinte, -267$). Bull 25/10 -392$, 26/10 -286$.
  3) TUTTE le aperture eseguite sono decise dalle REGOLE (Hawk 245, Bull 114), nessuna da Claude. Le proposte di apertura di Claude vengono
     rifiutate dal motore con "stop troppo lontano (liquidazione verrebbe prima)" (Hawk 73, Bull 8). Claude incide solo sulle chiusure.
  4) Perche' aprono poco: Hawk 1077 candidati rifiutati per "troppe posizioni aperte"; Bull 1510 per "margine sotto minimo" + 402 posizioni piene;
     stop giornaliero 352/298; il grosso resta "confidenza sotto soglia" (2281/2832). Tenuta media ~6h: gli slot restano pieni.
  5) Durata: trade chiusi entro 6h = 239, netto -2457$ (vincenti ~30%); oltre 6h = 114, netto +2705$ (vincenti ~60%). I profitti vengono dai trade
     che durano, non dagli scalp veloci (la durata e' anche effetto: gli SL scattano presto).
  6) Chiudere al 35-40% di ROI (simulazione ottimistica col picco di profitto): NON migliora: a 35% -72$ contro +248$ reali, a 40% +149$;
     Hawk migliora (+352 -> +440/+573), Bull peggiora molto (-105 -> -511/-424). Rinuncia a 1,4-1,8k$ di code destra (67 trade con ROI>=40% = +4611$).
     Conviene solo proteggere dopo picchi molto alti (>=80%: +449$). Il guadagno di liberare slot (rotazione) NON e' misurato.
  Decisioni in attesa dell'utente: togliere/alzare il tetto 160$ di Bull; carta d'intenti per Claude (scalp, molte posizioni, long quando gira);
  motore long/regime; perche' Claude non apre (stop vs liquidazione); quale "brain" intende (Brain Pilot?).
- **LAVORO IN CORSO: regime di mercato per Hawk e Bull (richiesta dell'utente 26/10 sera; NON deployato)**.
  Decisioni dell'utente: tetto Bull 160$ -> 250$; priorita' a Hawk; Hawk e Bull devono tornare ad aprire quasi di continuo, con logica
  migliore di apertura e gestione: niente short a ripetizione quando il mercato gira, aprire long quando gira al rialzo, non perdere i
  long quando il mercato torna ribassista, gestire meglio il profitto. Stessa metodologia scalp per entrambi (Hawk piu' aggressivo).
  Scoperte tecniche: le regole (`brain.rules_decisions`) aprivano il lato col punteggio piu' alto simbolo per simbolo, senza guardare il
  mercato, e gestivano solo con "chiudi se il segnale si ribalta"; i moduli salva-profitto/inversione (`desk/profit/*`,
  `profit_guardian`) NON sono collegati al ciclo dei bot (solo ricerca/ombra). Nessuna protezione del profitto era attiva.
  Costruito sul ramo `work/hawk-regime-v1` (base rule-pool): `desk/regime.py` (regime da BTC/ETH + ampiezza + momento BTC, con
  inversione; filtro dei lati; stop che sale a pareggio e poi segue il prezzo, solo paper; uscita se il mercato gira), integrazione in
  `rules_decisions` e `cli.py`, interruttore `DESK_REGIME_V1=0`, tetto Bull 250. 57 test nuovi/aggiornati verdi (regime 30, guardrail Bull).
  Banco di prova storico `deploy/scripts/desk_backtest.py` (motore e regole vere su candele pubbliche Bitget, molte varianti) + workflow
  `desk-backtest` (trigger `deploy/desk-backtest.trigger`, legge `ref=` dal file): prima esecuzione in corso.
  I parametri vanno scelti dai risultati (robusti sui terzi del periodo), poi si chiede l'OK dell'utente al deploy.
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
- Locale:31testreader/API+7componenti PASS, buildReact PASS; sintassi3.10 e byte pubblicati verificati. CI40382342014 SUCCESS: readerPython3.10/3.11,7testReact e buildPWA verdi.
- Analisi sizing dal codice1f2edeb6: budget stop1%equity ×size_pct ×conviction/100, poi cap/fee/slippage/liquidazione. Margine100$ è un tetto, non importo fisso. Nessun valore posizione live rilevato; perdita1$ da sola non prova sottodimensionamento.
- Nessuna modifica size/rischio/leva/strategia, bot, dati, deploy o trigger operativo. Nessun merge o riavvio. Prossimo: review e rilascio app separato dal runtime bot.

## Direttiva utente — Brain orientato allo SCALP (26/10)
- L'utente chiarisce che l'obiettivo è operazioni brevi, profitti netti utili e rotazione del capitale, evitando ore di attesa per target elevati. Il Brain attuale non rispecchia questa impostazione.
- Verifica codice: trade_type=medio, ciclo/esecuzione15m, riferimento uscita25–30%ROI, ATR1h. Serve riallineamento di dati/motore/uscite oltre al prompt.
- Design salvato: work/brain-scalp-design @6988c7a435eb61edafe0465839bbd50691e4469d, docs/brain-scalp-realignment.md. Nessuna implementazione runtime, merge/deploy/riavvio, nessuna modifica Hawk/Bull.
- Direzione strategica chiarita; durata precisa, profitto netto minimo e altri parametri restano da definire. Nessun aumento implicito rischio/leva/margine. Memoria e statistiche dei futuri scalp da separare dal Brain medio e dalle fonti classiche.

## Precisazione utente — scalp a durata adattiva
- Riferimenti1–5min e5–15min, con possibilità di proseguire oltre se il trade resta valido; evitare ore di attesa. Questi tempi non sono chiusure automatiche o modifiche di Bull.
- Brain: profitto netto, slancio residuo e rischio guidano continuazione/uscita; stop e uscita da tesi invalidata restano attivi anche in perdita. Nessun profitto garantito, attesa indefinita o soglia numerica nuova approvata.
- Aggiornato docs/brain-scalp-realignment.md su work/brain-scalp-design. Solo design; nessun cambio runtime, deploy o riavvio.

## Nuova richiesta — margine Brain simile Bull e dashboard visibile
- Utente chiede margini significativi sul contoPAPER1000, riferimentoBull. Verificata configurazioneBull: minimo150/max350USD; Brainattuale cap100USD e budgetstop1%×size×conviction. Riferimento registrato nel design, nessuna variazione numerica di rischio/levа applicata.
- PR#13 verificata ancoraAPERTA/nonmerged: UI margine/levа/esposizione/ROI non è live. Richiesto rilascio concreto come prossimo passo; resta il vincolo iniziale nessun deploy senzaOK specifico. Nessun merge/deploy/riavvio in questa verifica.

## AUTORIZZAZIONE — rilascio dashboard margini/leva Brain
- Utente risponde sì alla richiesta esplicita: integrare PR#13 e pubblicare solo aggiornamento app. Autorizzati merge main e deploy app; Hawk/Bull/Brain Pilot e loro strategia/rischio restano fuori dal rilascio.
- Target revisionato PR#13:7a3348fbf5b827aaf1295aa077153a36ab451298,31testreader+7React e CI40382342014 verdi. Deploy tramite workflowufficiale con SHA fissato, backup DB e rollback immagine/frontend.
- Ulteriore mandato: BrainPilot deve applicare l'idea trading dell'utente e usare esperienza/metodo del botclassico con la propria analisi. Specifica da rendere esplicita; non interpretare come deploy del nuovo motore scalp o aumento numerico del rischio.

## Rilascio PR#13 — dashboard margine/leva LIVE e verificata
- Autorizzazione utente: sì alla pubblicazioneapp. PR#13 integrata main con SHA d4865ddcf1c3dece3cd7d7336e4bfcbcb29b28cc; trigger rule-pool b54296d0c6774658bb0abce42c90d507a0f50ce2.
- Deploy40392367666 SUCCESS: backupSQLiteapp e prova ripristino PASS, immagine/frontendprecedenti conservati, saluteAPI/frontend/HTTPS PASS. Rilascioapp completato20:06UTC(21:06Roma).
- Verifica readonly40393188194 SUCCESS: SHAapp e labelUI PASS, campi reader presenti. Alle21:10Roma4SHORT: DOGE margine78.98 leva2x; ETH85.63/3x; XAG85.24/2x; XRP77.19/3x. Totale margine327.04PAPER. Nessun saldo reale letto.
- Hawk/Bull healthy SHA35f08cf8d16097d8ca365892a3f9a9ef23996709; Brain healthy1f2edeb6182029adc96ba7218ad145a7503472a3; tuttiPAPER, restartcount0, started_at antecedente alrilascioapp. Nessun deploy/controllooperativo dei bot.
- Nuovo workflowbrain-dashboard-verify.yml e trigger(784154c387b7d1f3aab76ed92c67f0811c9a5bf6) eseguono soloinspect/reader/etichettefrontend, nessun ordine o scrittura alle sorgenti.

## Mandato operatore Brain — implementato nel candidato, NON live
- PR#12 SHA db3a45897a572a3eca64c355c9cc00acde9fc04b, CI40394126770 SUCCESS. mandate.py passa operator_mandate versionato, obiettivoutente/classicalexperience e capacità realmenteattive. Snapshotmandato neljournal primaAPI.
- Prompt candidato: presa profittonetto quando indebolisce la prosecuzione; rimossa preferenza25–30%ROI/vincenteanziana. Modifica qualitativa richiesta dall'utente, non solo memoria passiva. Politicaversionata e coorti separate.
- Limiti numerici/cadenza15m/ATR1h/classificazione medio restano; readiness=full_scalp_engine_not_implemented, fast_exit_supervisor=false, marginiBull come riferimento NONapplicato, segnali classici live not_connected, storico reale not_imported. Nessuna dichiarazione falsa di scalprapido giàattivo.
- Locale140testPASS+1Docker skip; CI Python3.10/3.11+Docker/probe5posizioni verdi. Nessun merge/deployBrain. Prossimo: reviewPR#12 e completamento dati/uscite/sizing scalp, conservando storico e posizioni.


## IN_CORSO — Brain dimensionamento Bull di riferimento (ChatGPT Work)
- Mandato utente: cambiare metodo Brain, margini/leva attuali troppo contenuti. Componente Brain Pilot riservato a ChatGPT Work su work/brain-learning-v1; nessun intervento Hawk/Bull in parallelo.
- Implementazione candidata: profilo sizing distinto dal legacy1%, riferimento margine150–350USD/levа15x(min10), controlli stop/liquidazione/costi/cassa e budget rischio aggregato esplicito. Nessun budget numerico Brain inventato come autorizzato: parametro obbligatorio prima dell'attivazione del profilo. Non copiare il tettoBull160 contestato dall'utente o il250 in sviluppo come nuova regolaBrain.
- Nessun deploy/riavvio/merge o aumento delle posizioni esistenti. Il profilo sizing non costituisce pieno motore scalp; dati e uscite rapide ancora da completare. Test e review prima di ogni rilascio separato.


## Precisazione finale utente — Hawk e Bull con intelligenza adattiva H24
- Richiesta esplicita: Brain deve usare esattamente i metodi di Hawk e Bull come base, con intelligenza adattiva24h/7d. Sostituisce l'interpretazione di un terzo profilo di sizing simileBull; i due profili e relativi controlli devono restare distinti. Nessun nuovo budget rischio o API numerico approvato.
- PR#12 aggiornata SHA41161f42c85da444e1540b6cb32256d5411b4f4b: mandato versionato operator-classical-adaptive-h24-20261026, prompt e test esplicitano base classica reale/H24/provenienzaAIvsfallback e limiti effettivi. Prototipo sizing separato rimosso prima integrazione, nessun nuovo modulo/parametro operativo.
- Locale142PASS+1Docker skip, sintassi3.10/diffcheckPASS; CI40397263058 SUCCESS sul commit41161f42 (Python3.10/3.11+Docker/probe migrazione); byte pubblicati confrontati identici ai testati. La modifica è input/contratto, NON implementa collegamento esecutivo Hawk/Bull né supervisione rapida o secondo conto. Nessun merge/deploy/riavvio/reset o modifica dei bot classici. Prossimo: implementare adaptermetodo e routingprofili/motoreH24 con testcausali, riusando codiceclassico versionato e valutando arbitroDirector esistente(d2b351e0), senza confonderlo con integrazioneattiva.


## IN_CORSO — Implementazione Brain classico adattivo H24 (27/10, ChatGPT Work)
- OK utente "ok procedi" dopo chiarimento Hawk/Bull+BrainH24. Autorizzata preparazione codice/test; nessun deploy/riavvio implicito.
- Riserva esclusiva nuovo package director/classical_adaptive, relativi test/Docker/CI/docs, branch work/brain-classical-adaptive-h24 da rule-poole5d45f9; dipendenza candidata PR#12@41161f42. Nessuna modifica desk/* (in sviluppo Claude su work/hawk-regime-v1).
- Riutilizzare ciclo desk.cli e configurazioni effettive Hawk/Bull (byte-identici a35f08cf per desk/*), adattatore DeepSeek isolato PAPER con dati propri brain-hawk/brain-bull, budget condiviso Brain senza aumento implicito, provenienzaAI/fallback. Vecchio conto Brain e dati classici non toccati.
- Regime/P1/tettoBull250 pending non importati come approvati. DirectorArbitro V1 rivalutato: ridimensiona1%/max4slot e quindi non corrisponde al mandato di riuso del metodo reale; non adottato come nuovo sizer.


## Brain classico adattivo H24 — implementato candidato PR#14 (27/10, ChatGPT Work)
- Mandato utente "ok procedi": implementazione/test del collegamento reale Hawk/Bull+BrainH24. PRdraft#14 https://github.com/alexiptv82/SuperBot-Trading/pull/14, branch work/brain-classical-adaptive-h24, SHA25d5bd6a1a6d111bdea43c442ef139896ab105f4, base rule-poole5d45f9 e dipendenza PR#12@41161f42. PR mergeable, non integrata/distribuita.
- Nuovo director/classical_adaptive richiama desk.cli.run_cycle/fabbricheprofili/regole/engine reali senza modificare desk/* (byteidentici a35f08cf documentato live). Due processi/account brain-hawk e brain-bull isolati, inizializzazione PAPER1000 solo esplicita su cartelle vuote; vecchio Brain/Hawk/Bull non aperti/modificati. Nessun recupero storico reale eseguito.
- Valori ereditati,classici: Hawkcap100/10slot, Bullcap350/6slot/minimo150, guardrailforzati60o200/15x, daily_stop10%(non20delvecchioBrain), kill450. RestaBull160/vetoBTC2% della baseline; non adottati regime/P1/tetto250 pending di Claude. Non inventato terzo sizing1%. Probe reale medesima proposta200/15x ->Hawk100/15x,Bull200/15x; nessuna prova di redditività o risoluzione LONG.
- Loop obiettivo60s H24, feedpubblici lenti/fast e DeepSeek su worker separati, unico writerfinanziario. Entrysegnali15m/cooldown e controllinativi; protezione causalebarre1m ed esclusione minutod'ingresso, quoteosservate con costimotore; profittonetto utile su indebolimento2min è euristica sperimentale locale, non policy appresa/provata. Nessun timerforzato5/15min. Dati mancanti/stale ->drain; buchi oltre copertura ->latch/no nuovaexposure, nientelezioni daesitiincompleti.
- OutputAI asincroni scartati per >120s/esposizionecambiata/derivaprezzo/schema. Inputesatto auditato primaAPI; statosorgenteAI/regole/protezionelocale distinti. SQLitecommitta account+esiti+learning atomicamente, protezione primaentry; SQLabort/recovery e exportidempotente testati. Nuova identitàaccount/strategyversion separa coortiperprofilo/codice e trendclassicoEMA50/200 da vecchioBrainEMA20/50.
- Budgetcondiviso dueprofili0.50giorno/12mese, prenotazioni conservative e pacingUTC senza raddoppio. Baselineverificata dello spend.jsonl vecchioBrain obbligatoria, importoconsumato conservato, rollbackledger rilevato. Preparatoreoffline baseline_from_spend su copiareadonly; copia/provenienza NON ancora acquisita. H24locale non significa AIcontinua: fallbackregoleesplicito entrobudget.
- Locale20nuovitestPASS +142regressioniBrainPASS/1Docker skip, sintassi3.10/diffcheckPASS. CI40431469535 e40431465061 SUCCESS (3.10/3.11+immagine nuova e4probeDocker Hawk/Bull LONG/SHORT con rete disabilitata); regressioni/vecchioBrainCI40431469438 SUCCESS inclusa migrazioneDockerreale5posizioni. Bytepubblicati identici ai testati, worktreepulita. Nessunworkflowdeploy/SSH operativo aggiunto.
- Review dettagliata docs/brain-classical-adaptive-review.md. Restano: review incrociata adattatori/atomicità/profitheuristic, osservazionePAPERcausale comparativa, UI/reader dueprofili(app attuale mostra contoBrainvecchio), acquisizionespendbaseline e piano deployseparato conbackup/restore/rollback. Nessunmerge/deploy/riavvio/reset/ordine reale o accessoVPS in questa implementazione. PASSAGGIO: codice pronto perreview, ChatGPTWork autorecomponentenuovo; Claude può leggere/revisionare senza scrivere contemporaneamente.


## IN_CORSO — Review Brain H24 + PWA due profili (27/10, ChatGPT Work)
- Nuovo "ok procedi" dopo candidato PR#14 verde: proseguire review, UI e preparazione rilascio. Riservati director/classical_adaptive e relativi test su work/brain-classical-adaptive-h24, più nuovo reader/UI read-only da main su work/brain-paired-dashboard. Nessuna modifica desk/* classico o lavoro Claude sul regime.
- App: distinguere Brain Hawk, Brain Bull e conto Brain precedente; niente numeri inventati se profili non avviati. Margine/leva/esposizione, valore e fonte decisione, protezione/AI/fallback e stato feed con timestamp reali. Accesso auth/no-cache e mount readonly nella preparazione.
- Preparare piano backup/rollout con baseline spesa Brain e conservazione conto precedente. Nessun trigger/merge/deploy/riavvio in questa fase prima di risultati concreti revisionati.


## Checkpoint UI/review e backup readonly Brain (27/10, ChatGPT Work)
- PWA PRdraft#15 da main, SHA09f6eae99376c40fd66f18ffa390cc6d1ea04abb;41testPython+10React+buildPASS; CI40448036278/40448031293 SUCCESS. Readerprofili read-only/autenticato,no-cache, isolamentolegaсy/Hawk/Bull, margini/levа/nettostimato/fonti/AIpropostevsesecuzioni/datiobsoleti; nessun profilo fittizio se nonavviato. Non integrata/distribuita.
- ReviewPR#14 aggiornata SHA91df7432183ac235b9f837d1ae22f4963d11ba84: timestampveri persimbolo/stepcounter/indiceSQL/proposteAI separate, nessun parametroclassicocambiato. Nuovopreflightsolo lettura conbackupSQLiteonline e restoreconfrontato, manifestprivato;23testlocaliPASS (20motore+3backup), CI nuova in corso. Errorelocale sui permessi del manifest corretto (creazione600), quindi3testbackup verdi; nessuna esposizioneproduzione.
- Procedo a installare/eseguire solohelper+workflow+trigger readonly su rule-pool, preservando checkdiClaude b60d396. Effetti: inventarioDockerPAPER e nuovo backupprivato verificato; nessunflagpausa, chiave, budget, ordine, avvio/stop/riavvio o stato sorgentecambiato. Backupattivo non è baseline spesa congelata perattivazione. Attivazione motore/app non eseguita inquesto controllo.


## Preparazione finale rilascio PAPER Brain/app (27/10, ChatGPT Work)
- L'ultimo OKutente segue il riepilogo delle fasi residue(revisione, dueprofiliapp, rilascio conbackup). Si prosegue sul rilascio PAPER descritto, senza modifica dei botclassici o reset del contoprecedente. Targetapp PR#15@795cf312375d4eb411247755a78852bf55eb7707, CI40451305609/40451300902 SUCCESS,41reader+10React+buildverdi. Runtime PR#14 target5024fbdfe3a9719098f905b28eac5d0feb9848e6,32testmotore/backup/rolloutPASS+142regressioni/1Docker skip; CI finalepending, precedente5a1b4ab8 CI40451314993/40451309419/40451314932 SUCCESS inclDocker.
- Nel frattempoClaudehaeffettivamenteintegrato/deployato regimeselezionepesiclassici/Bull250: confermato source89b0dca e server readonly. Candidato riallineato condividendo sorgenticlassici di e0efa6e, nessun cambiodesk/* rispettoalramooperativo. CIprima91df743 suPRfallìperfixtureSHORTinmercatoup, mentrepushpassava sulvecchiobase: corretto scenariotest, NON disattivato filtro. ProveLONG/up,SHORT/down e vetoopposti conregimeattivo PASS; identitàmetodo includeconfigregime/pesi.
- Backupreale readonly40449215014 SUCCESS sucontrol7a5f90c: /opt/superbot-backups/brain-adaptive-preflight-20261027T042052Z, integrity+restorecomparatoPASS,4posizioniPAPERvecchioBrain, nessunpause/restart/cambiofonti. Fonte1f2edeb6 eclassici89b0dca3e259c548ed82754c2301c7b024d18ff5 tuttihealthy/PAPER/restarts0; classici partiti03:59UTC, Brain26/10 14:54UTC. SoloDESK_CAPITAL_V1=off neicontrollipoliticaclassica. MemAvailable2519340KiB/disco34078MiB. BackupattivoNONbaselineAPIcongelata.
- Rilascio pronto: app mantiene contoprecedente e aggiungetabHawk/BullBrain; mountnuovoparentreadonly. Controlloattivazione separato, fullSHA/approvedPAPER, backupnuovo, pausaSOLOnuoveesposizioni/APIlegacy(gestione4posizionirestaattiva), attesa cicloquiescente, importoesattospendlegacy, nuoviaccountwarmupinpausa1000PAPERciascuno, verifica zeroesposizione/spesanuova/feed/app, quindiabilitazione. NessunordineLIVE,nessunastoppataHawk/Bull,nessunristorinorollbackdibalancivecchisunuoviesiti.
- Rafforzamenti review: timestampquotesveri/proposteAIvsexecution, pausaoperatore visibile, controllocoldstartinpausa; simulazionirollout riuscito/buildfail senzafermavecchio/uncertezzaesposizionemantienegestione; outboxincrementale validata evita scansionireiterateH24, auditinputsolo primarealesubmission. Archivi e memoria non azzerati. Prima dei trigger di deploy: CI finaleverde e mergeexpectedhead. Dopo: verifiche effettive e diario.


## Rilascio in corso — app integrata, motore finale in verifica (27/10)
- PR#15 mergedmain4cf41d23bb94f7a868b25dd1c89b3e4e8993d9a8 dahead795cf31 verde; mergecodice nonèdeploy. Targetappfisso4cf41d23. PR#14 headfinale5024fbdfe3a9719098f905b28eac5d0feb9848e6,32nuovitestlocaliPASS inclwarmuppausato/controllorollout/failure/outboxincrementale; nessunparametroclassicocambiato.
- Si completano gli stepdi rilascioPAPER oggettodell'OK: integrazionebot solo aCIfinaleverde, triggerapp conbackupDBautomatico, poi attivazione tramitecontrollospecializzato conSHA esatti. OldBrain1f2edeb6 da conservare in gestione4posizioni, nuoviingressi/APIlegacyinpausa dopo backup. Classici89b0dca invariati e senza riavvii daquestorilascio. Nuovibudget condivisi comprendonospesavecchia, nessunreset.


## Rilascio avviato — PR#14/#15 integrate e trigger app (27/10)
- PR#14 mergedrule-pool b17e79a72ff01233f65867d2aca8c306455855d5 dahead5024fbdf verificato; PR#12dipendenza inclusa. CIfinali40452483812/40452479075 SUCCESS (32testnuovi+Docker) e40452483743 SUCCESS(legacy/Docker5posizioni). Sorgenteclassica invariata rispetto89b0dca. Controlloattivazione ancora non armatosenzaappverificata.
- PR#15 mergedmain4cf41d23; CImergemain40452532496 SUCCESS. Triggerapp87e0886eb03fe023fd898b8187969958a8c83a2a fissasha4cf41d23; workflowufficiale backupDB+restore automatico, rollback frontend/immagine, nuoviRootreadonly. Nessuntriggerdi redeploydei classici; nessunresetstorici.


## App paired Brain LIVE; attivazione PAPER due profili (27/10)
- Deployapp40452932435 SUCCESS, target4cf41d23, terminato05:02:43UTC(06:02Roma). BackupDBapp /opt/superbot-backups/superbot-deploy-20261027-050221.db integrity/restoreverificato, frontend eSHA/API/nginx/HTTPSPASS; rollbackimmagine/buildprecedenti conservati. Nuovo mountparentprofili readonly. Trebotprecedenti risultanohealthy senza riavvio delrilascioapp; poolunhealthy preesistente non toccato.
- Ora trigger specificoattivazionePAPER con source5024fbdfe3a9719098f905b28eac5d0feb9848e6, vecchio1f2edeb6182029adc96ba7218ad145a7503472a3, classici89b0dca3e259c548ed82754c2301c7b024d18ff5, app4cf41d23bb94f7a868b25dd1c89b3e4e8993d9a8. Controlloimpone backupaggiuntivo, quiescenzaAPIlegacy, ledgerconservato,warmuppausato, readerapp/zerofee-esposizione, solopoi nuoviingressi. Iquattrotradeprecedenti restanogestiti dalvecchio container; classici nonstoppati/riavviati. TuttoPAPER, attivazioneesito ancora da verificare.

## Esito finale rilascio Brain paired (27/10, ChatGPT Work)
- Autorizzazione OKutente eseguita: PR14/PR15 integrate, app e due nuovi motori PAPER rilasciati e verificati; dettagli attuali in testa. Il commit3333e62c disarma il trigger; non cambia il codice o lo stato dei container.
- Attivazione40453369414 SUCCESS, nuovi profili healthy e reader app effettivo; vecchio Brain con4posizioni protette e API/nuove aperture in pausa. Backup finale e spesa legacy conservati, classici89b0dca invariati.
- Warmup readonly40454443967 SUCCESS ha osservato vecchio ciclo quiescente e nuovi processi ancora in pausa, nessuna mutazione. Primo postflight40454569926 fallito per guardia Docker app non prevista: corretto verifier9fd449e9, rerun readonly40454674575 SUCCESS. Nessun errore motore riscontrato, nessun reset o redeploy correttivo.
- Al05:19UTC5cicli,0posizioni,1000PAPER ciascuno; non ancora campione operativo per valutare scalp/LONG/profitti. AI attuale paced_profile_allowance (legacy già0.256114/giorno); regole classiche e protezione locale attive.

## Patch profit-first e Run #2 — pubblicata, NON attivata
- Allegato utente chatgpt-push-istruzioni.md completo letto; autorizza pubblicazione due moduli su rule-pool, PR verso main e solo deploy app. Push eseguito con lease sul parent9a07e16, commit85b34608b1367fbe9ca000dfc10504788a2ac8e8. Messaggio/coautore Claude conservati come forniti.
- PRdraft16 https://github.com/alexiptv82/SuperBot-Trading/pull/16 rule-pool->main. Moduli mandate.py e knowledge.py più aggiornamento test esistente test_brain_pilot_experience.py. Sorgenti pubblicati da confrontare con byte locali testati.
- Mandato NET_PROFIT primario entro controlli vincolanti, obiettivo sostenibile dopo costi; nessun recupero forzato o modifica autonoma dei limiti. Preservati metodo Hawk/Bull, scalp e rotazione; adattamento su evidenze senza inventare nuova strategia eseguibile.
- Run #2 registrata come caso RIPORTATO da Claude tramite utente: +1090USD PAPER,60.5%,76trade,12-16ott2026/rev5818aee, non riconciliato con archivi o attribuito causalmente alla soglia70. Documento fonte identificato SHA256, nessun trade sintetico o seed importato. Le7 note prive di studi specifici sono ipotesi esplicite, percentuali universali/promesse rimosse. Corretto availability dal2024 alla data/ora effettiva;3note engineering originali conservate,8nuove senza duplicati.
- Test locali:145 legacy (144PASS,1Docker skip),32classical PASS,diffcheckPASS. Primo tentativo pytest non disponibile: usato unittest nativo. Primo test legacy fissava catalogo3 e falliva con11: aggiornato per verificare3engineering+8nuove, provenienza, assenza lookahead e obiettivo subordinato ai controlli.
- NESSUN merge/deploy/restart/reset. Istruzione allegata che app gestisca brain-hawk/bull è errata:5container trading separati verificati nel rilascio precedente. App-only NONattiva questi moduli. PRdraft perché rule-pool->main comprende inoltre codice operativo accumulato, non solo la patch. Non fare merge massivo presentandolo come2file.
- Prossimo: integrazione isolata revisionata, verifiche CI e piano aggiornamento conservativo SOLOdueBrain adattivi; autorizzazione allegata limita deploy adapp e non autorizza a sostituire tale azione con restartworker. Prima di approvazione operativa rendere concreto piano backup/stato/posizioni/budget e verifica successiva. Classici,legacy,APIbudget e dati immutati; nessuna pretesa mandato giàlive.

## Seed backtest allegati — push sul branch di lavoro, nessun rilascio
- Richiesta esplicita utente: quattro file dallo ZIP superbot_experience_seed_patch.zip su work/brain-classical-adaptive-h24, senza prefisso superbot_patch/. Commit ca193819bcf7080bdd594528433aa0e211d8cf53, parent5024fbdfe3a9719098f905b28eac5d0feb9848e6; messaggio esatto richiesto con [skip ci], aggiornamento ref con expectedSHA e senza force.
- Percorsi: backend/desk/brain.py, backend/desk/cli.py, brain/experience_seed/{hawk,bull}/experience_seed.json. Nessun altro file nel commit. Entrambi Python contenevano in fondo una riga JSON completa di risposta MCP del downloader con copia del sorgente originale: rimossa esclusivamente quella riga per ottenere moduli eseguibili, comunicato all'utente. I JSON seed conservati invariati.
- Sintassi Python/JSON valida, import brain e loader con Hawk/Bull effettivi PASS (1434caratteri ciascuno), assenza file restituisce stringa vuota;32testclassical adattivi PASS. CI saltata come richiesto [skip ci]. Non equivale a audit scientifico dei risultati.
- Provenienza dichiarata nei seed: synthetic_backtest_binance_futures_5m_15m_2023_2024. Messaggio utente dice dati reali/Grok, loader dice dati reali Binance: incongruenza NONrisolta né certificata. Numeri riportati dall'utente Hawk1053/WR41.9/PF0.85 eBull1045/43.7/0.87 non verificati su candele o elenco integrale trade. Non assimilare a trade operativi PAPER.
- Loader legge DATA_DIR/experience_seed.json; la semplice presenza in brain/experience_seed nel repository NON installa seed nei dati runtime. Formato distinto da director.brain_pilot.experience: NON copiare questi JSON al reader experience_seed del Brain adattivo come se fossero bundle validati.
- CLI allegato rimuove docstring iniziale oltre alle tre modifiche funzionali (import/caricamento/passaggio prompt); nessun altro cambio funzionale rilevato rispetto alla baseline5024. Cambiare desk/brain.py e cli.py cambia identità metodo adattivo: eventuale upgrade deve preservare stati e gestire migrazione, non reset.
- Nessun merge/PR nuovo/deploy/riavvio/ordine o scrittura ai dati VPS; classici e Brain in esecuzione restano invariati. Branch storico PR14 giàmerged ora contiene nuovo commit da revisionare separatamente. Patch profit-first85b34608 resta su rule-pool/PR16, NON inclusa automaticamente nel branch5024 di questa richiesta.

## Patch backtest_seed — BLOCCATA prima del push
- Nuova richiesta utente con allegato superbot_backtest_seed_patch.zip: leggere prima claude/diario-27-ottobre-per-chatgpt.md, poi push4file+rimozione brain/experience_seed, diario Claude PM e migrazione/redeploy SOLOBrain adattivi PAPER senza reset. Istruzione esplicita: fermarsi e documentare a qualsiasi blocco/dubbio.
- Documento preliminare NONaccessibile: nessun risultato nelle due ricerche documentali (nome esatto e query semplice); percorso GitHub claude/diario-27-ottobre-per-chatgpt.md assente sia su diario sia su rule-pool. I Project docs privati Claude non sono condivisi automaticamente con ChatGPT. Nessun contenuto della voce Claude PM o procedura completa inferito/inventato.
- ZIP inventariato senza estrazione o esecuzione: migrate_method_digest.py (6048byte), backend/desk/brain.py (60915byte), brain/backtest_seed/hawk/backtest_seed.json (27768byte), brain/backtest_seed/bull/backtest_seed.json (27778byte). Nessun cli.py e nessun diario/documento istruzioni incluso.
- Ispezione statica brain.py: ancora presente una riga finale JSON di risposta downloader; funzione nominata load_experience_seed. Non applicate correzioni a tentativi né valutato lo script di migrazione come pronto/eseguibile.
- STOP prima step1: nessun push codice, rimozione file, merge, build, SSH, stop/restart container, migrazione SQLite o installazione seed eseguiti. Solo questa registrazione sul ramo diario.
- Per riprendere occorre allegare/incollare il documento completo di Claude, inclusi contenuto previsto per diario/2026-10-27_claude_pm.md e istruzioni operative8step. Non creare la voce a nome Claude con contenuto non ricevuto. Aggiornamento precedente ca193819 resta invariato.

## Patch backtest_seed v2 — STOP per migratore incompatibile
- Ricevuti ZIP superbot_backtest_seed_patch_v2.zip e istruzioni complete in chat; precedente blocco documento mancante superato. Parent remoto verificato ca193819bcf7080bdd594528433aa0e211d8cf53. brain.py ora pulito e sintassi valida, nessun JSON downloader in coda.
- Revisione preliminare del migratore allegato rileva incompatibilità BLOCCANTI: legge/aggiorna state(value,key='runtime_meta'), mentre Store usa state(id=1,body); inserisce events(ts,data), mentre schema effettivo è events(seq,kind,body). Dry-run eseguito SOLO su DB scratch con schema effettivo: OperationalError no such column: value. Nessun accesso dati VPS.
- compute_method_digest allegato concatena nomi/contenuti sorgenti e profilo e tronca SHA256 a16caratteri. runtime.method_digest restituisce64caratteri calcolati sul JSON di hash dei moduli desk/adaptive, configurazione profilo e controlli/regime. Anche correggendo SQL, questa impronta sarebbe rifiutata dal runtime.
- Backup proposto cp SQLite prima dello stop non garantisce snapshot coerente con WAL; serve SQLite backup API/restorecheck e snapshot finale coerente a writer fermi. Start del vecchio container non sostituisce la sua immagine con codice nuovo: manca build/promozione immagine con SHA fissato nella sequenza allegata.
- Istruzione esplicita utente fermarsi/documentare a qualsiasi blocco: STOP prima push codice/rimozione seed, nessun SSH/stop/restart/migrazione/copia ai dati. Nessuna correzione a tentativi dello script. Parent e runtime restano invariati.
- Sezione richiesta patch backtest_seed resta PIANIFICATA, non applicata: brain.py che legge backtest_seed.json, nuovi percorsi brain/backtest_seed/{hawk,bull}, migratore e rimozione brain/experience_seed non ancora pubblicati. Redeploy rinviato finché migratore e procedura sono corretti e testati.
- Creato diario/2026-10-27_claude_pm.md come riepilogo delle informazioni Claude trasmesse dall'utente, con stato bloccato esplicito; non è trascrizione di Project doc non accessibile.

## Patch backtest_seed v3 corretta e pubblicata — NON deployata
- Utente autorizza espressamente correzione autonoma dei problemi e push diretto. ZIPv3 letto da allegato; istruzioni complete precedentemente ricevute in chat utilizzate, nessuna pretesa accesso al Project doc Claude.
- Commit 129547ed43a9aaec935df31102bb4e8016c38e7c su work/brain-classical-adaptive-h24, parentca193819bcf7080bdd594528433aa0e211d8cf53, [skip ci], aggiornamento lease/no force. Pubblicati backend/desk/brain.py, brain/backtest_seed/{hawk,bull}/backtest_seed.json, migrate_method_digest.py e nuovo test backend/tests/test_backtest_method_migration.py. Rimossi due vecchi file brain/experience_seed/ nello stesso commit. CLI mantiene import/caricamento/keyword del commitca193819; funzione load_experience_seed conservata per compatibilità ma legge backtest_seed.json.
- Correzioni al migratorev3: SQLite online backup API anziché copy2 DB/WAL/SHM, integrity e confronto indipendente della copia su intere tabelle state/events; writer.lock condiviso col runtime acquisito esclusivo nonblocking, profilo/account/versione/PAPER e pausa verificati; expected-old-method64obbligatorio; nessuna creazione account o sovrascrittura stato estraneo.
- Digest calcolato tramite runtime.configure+method_digest reali in subprocess isolato, senza helper fisso in /tmp, output import catturato per isolare il solo hash64, errori sanitizzati senza raw stderr/segreti. Prima prova effettiva fallì perché importCLI stampa anche messaggi: corretto redirect stdout e poi entrambi profili PASS.
- Migrazione in transazione: confronto stato/eventcount dopo backup, modifica SOLO state.method, aggiunta journal method_migration con old/new/sourceSHA, verifica restoJSON integralmente identico, rollback su inserimentoevento fallito. Contesti/learning/posizioni/budgetcheckpoint e vecchi eventi restano invariati. Shared APIledger non aperto dal migratore. source-sha40 è provenienza dichiarata: l'operatore/workflow deve verificare esternamente corrispondenza checkout/immagine e ambiente policy; lo script non costruisce/promuove immagini.
- Header prompt corretto: contesto backtest2023-2024 fonte dichiarata sintetica/nonverificata, non trade operativi PAPER. Seed JSON conservati; nessuna nuova certificazione del backtest o import nel bundle experience.
- Test locali:5nuovi migration PASS (dryrun senza stato/eventi/backup, conservazione intero stato+eventi+restorebackup, writer attivo respinto, pausa/profilo, rollback SQL);32classical PASS;143legacy di cui142PASS+1Docker skip. Digest64 da entrambi runtime reali e lettura backtest_seed Hawk/Bull PASS; diffcheckPASS. CI volutamente saltata come richiesto.
- Solo push e diario in questa fase: nessun SSH, pausa operativa, migrazione dati VPS, installazione seed, stop/restart, build/deploy. Le autorizzazioni e gli obiettivi precedenti restano, ma questo messaggio chiede correzione/push, non è una conferma di rilascio riuscito. Procedura rollout completa con snapshot profili/ledger e nuova immagine/postflight resta da preparare/testare prima dell'esecuzione. Non usare start del vecchio container come aggiornamento codice.
- Comandi migratore aggiornati richiedono --profile, --expected-old-method HASH64, --source-sha SHA40 e opzionale --dry-run; radice dati predefinita /opt/superbot-brain-adaptive. Da eseguire nel medesimo ambiente dell'immagine target; worker fermo e pausa file presente per scrittura, mai reset per risolvere mismatch.


## Redeploy Brain adattivi autorizzato — preflight in avvio
- OKutente «ok, facciamo il redeploy»: target fissato129547ed43a9aaec935df31102bb4e8016c38e7c, baseline adattivi5024fbdfe3a9719098f905b28eac5d0feb9848e6. SOLOdueBrain adattivi PAPER; classici/legacy/app da non riavviare. Riservato controllo operativo nuovo deploy/scripts/brain_paired_update.py e workflowbrain-paired-update su rule-pool.
- Preparato e testato controllo con backupSQLite/restorecomparato, buildprima stop, pausanuoveesposizioni, snapshotfinaleprofili+ledger, dryrun/apply migratore pinned129, seedbacktest distinti, workerimmutabiliinpausa e confronto storico/posizioni/budget/app prima rilascio. Rollback riavvia vecchi worker con migrazione inversa della sola identità, NON ripristina snapshot finanziari.5test controlloPASS inclusi successo e migrazioneparzialefallita; sintassiPython/YAMLPASS.
- Primo trigger solo preflight: inventarioPAPER/SHA, backupprivati e build/smoke nuova immagine. Non crea flag, non stoppa o migra conti. Solo dopo preflightverificato si applica aggiornamento giàautorizzato. Nessun ulterioreOK necessario per lo scope descritto.


## Redeploy Brain — preflight reale riuscito, applicazione avviata
- Preflight40512246319 SUCCESS,13:28:13UTC/14:28Roma, target129547ed. Backup /opt/superbot-backups/brain-paired-update-20261027T132806Z con restorecomparatoDBPASS; nuova immagineDocker build+smoke PASS. DueBrain5024healthy/restart0 e treworkerprecedenti89b0dca/1f2healthy/restart0; app4cf invariata e reader effettivook. Nessuna sospensione/stop avvenuta nel preflight.
- Ora triggerapply del controllo f8a055d5, che usa solo migrazione129547ed, baseline5024, pausa prima stop, snapshotsfinali e ledgerconservato. Autorizzazione utente già presente; nessun reset o restart classici. Esito applicazione ancora da verificare.

## REDEPLOY COMPLETATO — due Brain adattivi 129547ed, 27/10 14:34 Zurigo
- Autorizzazione esplicita utente eseguita. Apply40512553461/job122217893542 SUCCESS, controllo f8a055d5, trigger1191c743. Targetimmutabile129547ed43a9aaec935df31102bb4e8016c38e7c, baseline5024fbd. Backup /opt/superbot-backups/brain-paired-update-20261027T133014Z: live+finale a writerfermi, SQLite API/integrity e restore indipendente comparato; profili/log e ledgercondiviso conservati. Buildimmagine completata prima dello stop.
-13:30:35UTC nuoveesposizioni sospese con gestioneprotettiva;13:31:36 dueworkerfermi e snapshotfinale verificato; dryrun/apply nella nuova immagine/reteoff, interostato identico salvo method, vecchievents append-only. Nessun conto ricreato. Migrazione Hawk1fb9aa05f8ae9afd8abb451fc4b74952e72733b22ff33202c0827727aa66f7ac ->fa3c3f36a95e2b1ddee22f6e659bf235413244441a8b8ae16d02ad498df311e4; Bull e69a2eaedb2be6771d43f63357e943ba7f20cff3d5854a145e79c597ad3ab780 ->6d70ea9fe1b6e35381615a500bfd42aa73c20ec6c5992ed43e46e57680b21d50.
- Superbot-brain-hawk iniziato13:31:39.477UTC e bull13:31:39.778UTC, SHA129547ed, healthy/restart0. Warmupinpausa fino a feed freschi, coverageintegra, nessun entrycycleerror, conti/storico/posizioni verificati, ledgerprenotazioniimmutato, readerapp effettivook; poi nuove aperture riabilitate e ciclo successivo osservato. Applycompletion13:34:41UTC(14:34Zurigo). Vecchi container fermati e conservati con suffisso -previous-20261027T133014Z; nessun duplicatoattivo previsto e nessun reset.
- Seed installati solo /opt/superbot-brain-adaptive/brain-hawk/backtest_seed.json e brain-bull/backtest_seed.json. Copia byteidentica al source pinned; esperienzaoperativa experience_seed distinta, nessun bundleclassico inventato/importato.
- Verifica indipendente readonly40513939339/job122222802204 SUCCESS13:39:31UTC(14:39Zurigo): cinqueworkerhealthy/PAPER, SHA esatti; appHTTP200 e readerok, nuove pausefalse, feedfreschi, coveragefalse, nessunentrycyclefailed negliultimi40journal. Cicli504Hawk/505Bull (continuità, nonripartenzada0); cash/equity1000PAPER ciascuno, margine0/0tradechiusi/0posizioni. Non dichiarare redditività o operazioni non osservate.
- Dockerexec readonly in entrambi nuoviworker importa desk.brain e legge seed: prompt_context_present=true,1463caratteri; Hawksha2560951c98abc9be15e49cd569ef87b10ea6600fef362354f0db1381fe60f955e27, Bull1775f52c99999f0c3e1f526ec5a4ba762d048fe054d23394f70cbb2e3a98f288. Verificato ciclo completato dopo riapertura. Non è prova che il modello abbia già usato/appreso questi dati: attuale sourceclassical_rules, providerpaced_profile_allowance.
- LedgerAPI preservato: riservato giorno0.286987/mese0.387787, profiloHawk0.015525/Bull0.015348, legacytotale0.356914; cap0.50giorno/12mese immutato. Nessun azzeramento/credito restituito per incertezza.
- Classici89b0dca e legacy1f2healthy/restart0/startedimmutati, app4cf/restart0/started05:02immutato. Legacyreader4posizioni e pausanuoveaperturetrue. Nessun intervento classici/legacy/app o LIVE.
- Il primo controlloaggiuntivo40513803525 fallì per mia indentazione nel codicePython annidato delverifier, nonpererroreworker. Corretto soloopsworkflow ebda..., verificati YAML+Pythonesterno+Pythoninterno, rerun40513939339PASS; nessun restartcorrettivo. Workflowverifier ora attende SHA129, ciclo successivo e verifica seed nell'immagine.
- Triggerupgrade disarmato6937021fb32165efb49df8959061895d0f98b6f6: action=none approved=no [skipci]. Preservati backup/vecchieimmagini/container. Profit-first85b34608/PR16 NONincluso nel source129 diquestorilascio: resta attivitàseparata. Storico backtest sintetico/nonverificato come contesto, nessunretraining dichiarato.

## Audit run classici — ipotesi SL post-run positiva smentita dalla cronologia
- Richiestautente analisi readonly Hawk/Bull PAPER, numerirun riportati dall'utente non riconciliati con tradeindividuali inquesta verifica. Nessun cambio parametri, deploy, restart o accessoVPS.
- Git history: SL1.5->1.2ATR introdotto f7fbf198545c609877aef32bbcbf01e26ca6edfd l'11/10/2026, prima delle runpositive12-16/10. Baseline5818aee1e587f103d222510e761b30e02776ff15(15/10) eclassici89b0dca attuali entrambe sl=min(.035,max(.003,1.2*ATRpct)),TP=1.8SL. Non risulta modifica SL successiva che spieghi regressione. Maggioreadeguatezza di1.5oggi resta ipotesi da testare, non esclusa dal confronto.
- DAILY_MIN_BARS200 introdotto e91e885(20/10), dati1d/cacheretryfix880c4a4(21/10). Baseline5818 usava almeno30giorni ricampionati da massimo1000barre15m (~10.4giorni), quindi normalmente trend1dassente giànei giorni buoni. Se30-49giorni disponibili, EMA200=e50d e confronto >else producevaSHORT artificiale; non ripristinare warmup30 per rappresentare EMA200. Diario auditprecedente riporta0%trend1d aperturefino22, poi80-100%dal24: evidenza annotata precedente, non nuova misurazione VPS.
- Regime BTC sviluppato26/10, merge89b0dca e deploy27/10 03:59UTC: non causa delle runnegative21-26. Mantenere selezione regimeseparata nell'esperimento.
- Modifica veramente successivaallepositive: sogliaaltcoin70->65 e91e885 epoi63 a08afa4(20/10). TiersBTC/ETH/XAU/XAG restano60; non chiamare70sogliauniversale. P1pesi25/10 interveniva entroRun5, ora ripristinaticlassici27/10; runnoncoincidono necessariamente con singolaversione.
- Datiutente: Hawk2 +1090/76=+14.34USD/trade, WR60.5;Hawk5 -50/131=-.38,WR46.6;Bull1+770/30=+25.67,WR80;Bull4-214/89=-2.40,WR44.9. WRscende13.9ppHawk e35.1ppBull, nonsimiletra positive/negative. WRda solo non prova maggioreSLnoise: servono medie vincite/perdite nette,costi,sizing,SL/TPeffettivi econtestoasset/regime perversione.
- Prima prova consigliata SOLOPAPERcomparativa: sogliaaltcoin63vs70 conaltri parametricorrenti congelati, conteggioopportunitàescluse/attese e valutaPnLnetto/drawdown, non soloWR. Nessun ripristino automatico. ProvaSL1.2vs1.5 separata: in zona nonclippata1.5aumenta stop eTP25% a margine/levacostanti, quindirischio stop25% piùalto; non confondere con testSLsoloTPfisso. PnLnetto atteso=WR*avgwin_net-(1-WR)*avgloss_abs_net.

## Audit soglia TierC e scoring completo — 5818aee contro20ottobre
- Richiesta utente readonly: non assumere70causa, capire forza segnali RunBull1. Baseline5818cli ha tier_entry_score60perBTC/ETH/XAU/XAG e70peraltcoin, confrontato con dec.confidence+eventualebonusmacro. rules_decisions chiamata con_ENTRY_SCORE_BASE60 generaproposte conconfidence=r.score; secondo gate tier rifiutaaltcoinsotto70. ConClaude confidence può essereautonoma, non necessariamente punteggioraw.
- Confronto5818 vs e91e885(20/10): bloccoscoringpesi identico e seasonal.py byteidentico. Trend4h20,1h15,1d15sepresente,prezzovsEMA8,momentum0..12(sat3%24h),breakout10,RSI8,volume4se>1.3,pattern8/doji-5,RSIestremo-12,stagionalità0..15. 65poi63 cambiaammissione, non alza/abbassa score.
- Verifica riproducibile in scratch: eseguiti entrambi moduli originali con seasonal5818,100serieOHLCV15m sintetiche1000barrex4asset, stessonow e nessundailyesterno;400casi,0differenze su long_score/short_score/score/side/SL/TP/why. Prova equivalenzainquestoscenario, NON misura segnali/traderunreali oeffetti nuoviinput.
- Cosa cambia20ott: nativeCLI escludeultima15min formazione primaindicatori, aggiunge dailyesterno reale e modificheengineA-E (gestioneSL/TP/gap/DCA/barraingresso), oltre soglia70->65->63. Input/contabilità/uscite possono cambiare performance anche senza cambiare i pesi. Non attribuire causalità alle correzioni senza replay.
- Cambiodopo20: FixA23ott f87f2d6: trend4hprima e50vsEMAmin(200,len4h-1); con1000barre15m ~62barre4h, slow~61. DopoEMA200vera con>=200barre4h, altrimenti20punti assenti; conseriecompleta segnale puòinvertirsi. Pesi20restano. Neutralità sulleuguaglianze/RSIpiatto rimuovepuntiartificiali; non ripristinarebug percrearesegnali.
- P125ott635b964 riduce davvero4h20->14,1d15->10 eaggiunge rimbalzoLONG10: successivo all'abbassamentosoglia20ott, quindi nonspiegacronologia «pesiabbassati20poi sogliapercompensare». Pesi classici ripristinati27ott565115c ma definizioniindicatoricorrette conservate.
- Esempio SOLOipotetico: SHORT4h20+1h15+prezzosottoEMA8+momentum8+breakout10+RSI8+volume4=73, nessun1d/pattern/stagionalità necessario. Senza4h53. Nonètradeosservato néprovaRun1 segnali73.
- 30tradein4-5giorni (~6-7.5chiusure/giorno) nonprovafrequenzaelevata o slotsemprepieni; slotoccupazioneèdurata×frequenza. Occorronoaperture/chiusure/posizioni aperte iniziali/partial eoccupazionepertimestamp, oltreversione pertrade. Baseline5818commit15ott noncopre automaticamente l'intera run12-16; datiaggregatiutente nonsufficienti percausalità.
- Conclusione: nessuna riduzionepesisistematica entro20dimostrata; cambiinput/definizionie successivi P1 possono spiegare difficoltàasuperare70, non ancora quantificati sui trade. Raccomandazione precedente70da considerare testisolato, NONripristino dimostrato. Prioritàanalitica: distribuzionepunteggi/contributi suidentichefinestre, affiancataaperturereali e coderevision, opportunity/rejectionlog e dati4h/1dvalidi. Nessun cambio parametri/redeploy/riavvio.


## Audit run reali classici — IN CORSO, esclusivamente lettura
- Correzione richiesta: FixA23ott NONpuòspiegare HawkRun3/4 terminateprima22ott; nessuna causalità attribuita a quella modifica per quelle run. Ricostruire deploy effettivi e trade perrun, non datecommits.
- Utente autorizza soloanalisi, nessun cambio codice trading/parametri/prompt, nessunredeploy o scrittura ai quattrofilecervello. Nuovo collectorops bc9905c42be2907147fee996cf2242ea2d4fc12c legge fonti con O_RDONLY/O_NOFOLLOW, guardia runtimePAPER e rifiuto recordLIVE, esporta esclusivamente whitelist di campi trade/feature/summary e metadata SHA/date deploy. Nessun rawprompt/chiave/env o saldo reale. Testallowlist/refusalLIVE e sintassiPython/YAML PASS.
- Lettura rootclassici+archivi, deduprealizzazioni e riconciliazione con learninglog; sourcehash/size/mtime prima/dopolettura registrati, append dei bot operativi distinti da modificheanalista. Nessun import runtime,flag,stop,reset,ordine o invocazionetrading. Avvio workflowreadonlyclassic-run-forensics, nonworkflowdeploy. Diario/report con [skipci].

## Audit forense run classici completato — 27/10/2026, sola lettura

- Autorizzazione limitata all'analisi rispettata: nessun deploy/restart/reset, cambio strategia/soglie/prompt/limiti, modifica DESK_MODE o scrittura ai file cervello. Solo collector/workflow di lettura su rule-pool e questo diario; nessun force push. Classici e Brain non aggiornati da questo audit.
- Rapporto completo: [diario/analisi-run-2026-10-27/REPORT.md](diario/analisi-run-2026-10-27/REPORT.md), con CSV posizioni/realizzi/deploy/mercato e JSON metriche/provenienza. Gli importi nuovi pubblicati sono esclusivamente PAPER. Nessun prompt/risposta privata, credenziale o importo di trading reale.
- Snapshot 14:30:30 UTC: root history Hawk278/Bull149=427 realizzi; multinsieme esattamente coincidente con chiusure negli stati. Run concluse404 realizzi ->357 posizioni complete dopo aggregazione parziali. Entrate353/357 con feature; tutte357 source=rules. Fonte decisionale delle uscite non identificabile dal source ereditato o dalla label comune “chiusura Claude”.
- Rettifica delle sintesi precedenti: Bull1 30 realizzi/17 posizioni, WR dashboard80% ma per posizione70,6%, Wilson95%46,9–86,7%. Hawk5 131/112, WR46,6% vs37,5%; Bull4 89/77, WR44,9% vs36,4%. Hawk3WR26,3%, Hawk4WR16,7%.
- Cronologia corretta: Hawk4 termina22/10 06:10UTC (08:10Zurigo), comunque primaFixA23/10. Golden attraversano a0/7ced/5a4/9fa/5818; non sono tutte5818. Prima aperturaBull1 durante deploy iniziale43c79/a0 senza tagversione: attribuzione incerta documentata, non SHA inventato.
- Workflow#34 fallito ma b6b9911 effettivamente eseguito21/10~03:09; #36 fallito22/10 non prova deploy. Daily stop legacy10% è provato nel deploy297 del24/10, non dal triggerfallito22. Tutti4tradeBull3 chiusi sotto b470 prima b6, non attribuire loro i parametri del summary finale.
- SL1,2ATR era già attivo prima golden. Hawk3 ancoraC70, scoreC mediano74 contro71Hawk2, contributo4h+20 presente in tutti gli ingressi loggati di entrambe. Nessuna evidenza di indebolimento scoring all'origine del primo crollo. 1d assente anche golden, compare nelle tarde. RegimeBTC27/10 non causa runconcluse21–26.
- Hawk5 nettoPAPER-50,81/fee276,98: netto+fee+226,17. Bull4-214,02/fee330,25: +116,23. Identità contabile, NON backtest senza costi o prova di tariffa aumentata. LIQNEARHawk4-101,50 eINJBull3-194,88 pesano30,2%/62,4% della perdita; precedenzaLIQsuSL nelmotore, evitabilità non provata senza percorsointrabar.
- Mercato pubblicoBitget1H su10simboli,30finestre complete: aggiunto16–20 oltre12–16/21–26, ritaglioore effettive run. Prime negativeBTC piùpiatto/inrimbalzo e meno volatile, compatibile con peggioramentoSHORT; tardeBTC di nuovoincalo ma runrosse. Nessuna quota causale mercato/codice identificabile.
- Raccomandazione analitica precedente di testare70 NON è un ripristino dimostrato: gruppiC63–69 realmente eseguiti positivi nelle ultime run. Nessuna patch o prova parametri proposta/eseguita in questo lavoro. Servono fonteperazione, inputpoint-in-time, storialivelli e configoperativa per attribuzione.
- Acquisizioni40520808530/40521704685/40524300414/40526731267 SUCCESS, soloO_RDONLY e whitelist. Sei fileprotetti presenti con size/mtime invariati durante lettura; errors.md assente suentrambi e non creato. Hash/byte/provenienza pubblicati, nessun rawfilememoria.
- Stato task: COMPLETATO. Prossimo passo: decisione esplicita utente su eventuale ulteriore raccolta/esperimento; nessuna autorizzazione implicita a cambiare trading.

## Analisi fee run golden contro negative — 27/10/2026
- Nuova richiesta utente: costi, size, frequenza, lordo positivo diventato netto negativo; autorizzata proposta ma NON implementazione.
- Dettaglio: [analisi fee](diario/analisi-run-2026-10-27/FEES.md). Dati del precedente snapshot PAPER riconciliato; nessun nuovo intervento VPS.
- Hawk2/5: fee203,03/276,98; posizioni76/112, realizzi76/131; fee/posizione2,67/2,47; margine medio99,60/97,92; posizioni/giorno21,72/24,72. Bull1/4: fee80,17/330,25; posizioni17/77, realizzi30/89; fee/posizione4,72/4,29; margine medio174,29/170,29; posizioni/giorno4,86/13,69.
- Fee/notional andata-ritorno circa12bp tutte: nessuna tariffa aumentata. Lordo medio crolla Hawk17,02→2,02, Bull50,05→1,52; size solo leggermente inferiore. Bull frequenza2,82x. Nessuna causa unica del crollo dell'edge dimostrata.
- Ribaltati da lordo positivo a netto negativo:0/2/0/0 posizioni; Hawk5ATOMid64-0,6522 eXAUid75-2,2288, funding0. Totale-2,8810: non spiegano tutto il rosso; nessun casoBull4.
- Proposta NON implementata: valutazione/filtro valore atteso netto (probabilità calibrata su dati, mai score=probabilità), costi completi senza doppio slippage, prima misurazione in ombra PAPER; netto visibile per prese di profitto discrezionali, mai blocco a uscite protettive. Nessun nuovo parametro numerico arbitrario o aumento size/leva.
- Nessun cambio di strategia, soglie, prompt, limiti, dati memoria o modalità; nessun redeploy, reset o force push. Attendere OK utente per qualsiasi implementazione.

## Confronto condizioni d'ingresso — run positive e tarde
- Analisi richiesta dall'utente, nessuna autorizzazione a implementare filtri: confronto282posizioni, score disponibile278/282; dataset precedente PAPER, nessun accesso operativo aggiuntivo.
- Rapporto: [ENTRIES.md](diario/analisi-run-2026-10-27/ENTRIES.md), dettagli413raggruppamenti in entry_groups.csv. Partizioni per score/tier/direzione/simbolo/ora/giorno/batch/versione riconciliate.
- Score medio Hawk2→5:70,57→69,29; Bull1→4:70,00→68,82. TierC Hawk52/76→93/112, Bull5/17→60/77; direzione quasi tuttaSHORT in entrambe le fasi. Peggiorano anche stessi tier e stessi simboli, non soltanto mix.
- Ricetta score cambiata: breakout Hawk54/74→20/112,Bull9/15→11/77; contributo volume53/74→29/112 e8/15→14/77; daily0→39/112 e0→29/77. Score75+ tarda molto diverso da golden. WR75+Hawk83,3→32,0%,Bull100%(solo3casi)→29,4%; non dimostra utilità ritorno70.
- Controprova: breakout+volume nelle tardeWR12,5%Hawk(16posizioni) e20%Bull(10). Non imporre questo filtro dai soli dati osservati. Inputvolume non omogenei tra versioni (1hricampionata ancheincompleta,15mchiusi/formazione).
- Orario migliore si inverte: golden12–24UTC, tarde00–06UTC. Un batchHawk24/10 04:00UTC9posizioni+460,03 supera tutto il nettofascia+432,42; Bull04:30UTC5posizioni+358,69 su+459,62. Nessun vantaggio orario stabile; dipendenza tra asset/profili, non repliche indipendenti.
- Pista esplorativa ATR1h/prezzo1% (NON soglia approvata/ottimizzata): tardeATR<1%Hawk68posizioni-607,49,Bull52-937,97; ATR>=1%Hawk44+556,68,Bull25+723,94. Differenza ricorre22/24/25perdataapertura,26entrambigruppiperdono; golden non mostrano stesso vantaggio. Associazione di regime da validare, non causa dimostrata o filtro pronto.
- Limiti: solo4run, goldenBull17posizioni con5Cvincenti~80%profitto; sottogruppi ex-post e dati/log incompleti, PnLdipende dauscite successive; non attribuire capacitàpredittiva alle condizioni senza verifica fuoricampione.
- Nessuna modifica a strategia/soglie/prompt/rischio/orari/memoria, nessun redeploy/reset/forcepush. Proposte precedenti restano non implementate. Solo rapporto e diario [skip ci].

## ATR nelle golden — verifica distribuzione e sotto1%, 27/10/2026
- Richiesta analitica utente, dati PAPER immutabili positions.csv al commit5327cc3c; nessun intervento operativo o cambio parametri.
- Hawk2: ATR disponibile74/76, mediana0,994%, min0,459%, max2,237%. ATR<1%39/74(52,7%),25vittorie/39(64,1%), netto+501,8718; ATR>=1%35,19vittorie(54,3%), netto+521,6550. Due ATR mancanti, netto+67,0868, esclusi dalle fasce.
- Bull1: disponibile15/17, mediana0,856%, min0,524%, max1,469%. ATR<1%10/15(66,7%),8vittorie(80%), netto+418,8387; ATR>=1%5,2vittorie(40%), netto+147,6328. Due mancanti netto+204,2770, non imputati.
- Distribuzione Hawk (n/netto PAPER): <0,5%3/+56,6449;0,5–<0,75%17/+70,6433;0,75–<1%19/+374,5836;1–<1,5%26/+615,6595;>=1,5%9/-94,0045. Bull:0/0;7/+193,3340;3/+225,5047;5/+147,6328;0/0, stessefasce.
- Profitti ATRbasso già dopo fee: lordo603,2697-fee101,3979=+501,8718Hawk;469,8377-50,9990=+418,8387Bull,funding0inquestigruppi. Non è evidenza di commissioni incapaci di coprire sempre ATRbassi.
- HawkATRbasso include19C,+397,4212 e20A/B,+104,4506; Bull2C,+148,5725 e8A/B,+270,2662. Non spiegato soltanto daBTC/ETH; campioni piccoliBull.
- Conclusione: golden NON erano sempreATR>=1; gli ingressi conATRbassa erano spesso profittevoli. Non identificata causa unica della diversa efficacia fra periodi. Nessuna sogliaATR universale dimostrata, nessun PnLcontrofattuale ottenuto togliendo trade (cambierebbero slot/ingressi). Nessuna patch/redeploy/modifica memoria.

## Piano rollback classici — SOLO preparazione, attesa OK
- Nuova istruzione utente: prima salvataggio e piano con verifica3funzioni, poi attendere conferma; nessun redeploy o pushmain/rule-pool/stable autorizzato.
- Creati e verificati backup/classici-2026-10-27 ->89b0dca3e259c548ed82754c2301c7b024d18ff5 (ultimo runtimeverificato) e backup/rule-pool-2026-10-27 ->d1701f22f2a615ac3ef05f96b9d1d3b297abf0bc (HEADrepo). Sono backupcodice, non snapshotdati/immagine. Nessunforce.
- Piano completo: [ROLLBACK-CLASSICI-2026-10-27.md](diario/ROLLBACK-CLASSICI-2026-10-27.md). Golden attraversano5versioni;5818ultimo15/10sera,9fagenera maggioranzaingressi. Non esiste SHAunico che abbia prodotto tutta la run.
- LONG: correzioni anti-biasFixA presenti; bonusP1rimbalzo spento inclassic. Distinguere filtroregime da correzioneLONG.
- Salva profitto: close/partialClaude+regole giàbaseline; GuardianSHADOW ONLY scollegato,ratchet/flipDEFAULTspenti. Funzioneavanzata non è operativa da copiare/attivare implicitamente.
- Vault esiste maCapitalV1off ultimo controllo; separarlo da sizingpercentuale e stop20% per non importare policy ulteriori. Eccedenza oltre1000, nessun reintegroperdite; cashdisponibile/posizioniaperte possono rinviare accantonamento. Interpretazione da confermare.
- Baseline ripristinerebbeC70,slotsBull3,dailystop12%,stagionalitàoriginale;SL1,2ATR giàbaseline. Regime/rischioBull250/veti nuovi esclusi salvodecisione. Cooldownscalp10min, revisione15min (rettifica descrizione cooldown15in vecchioaudit).
- SchemaPosition5818 non accetta last_bar_ms degli stati moderni: adattatoreconservativo necessario, nessuna cancellazione campi/reset dati. Rollbackmotore ripristina difetti barre/DCA noti; possibile quartaeccezione richiededecisione esplicita, non chiamarla salva-profitto per includerla.
- Stato ATTESA OK: nessun ramoimplementativo, modifica strategia/prompt/limiti, trigger operativo, redeploy, ordine, migrazione, reset o intervento a Brain/app/memoria. Dopo conferma solo preparazione/test ramoisolato; deploy richiedealtroOK.

## Rollback classici AUTORIZZATO per implementazione, NON deploy
- Utente conferma5818aee, tutte correzioni motore, esclusioneGuardianavanzato, Salvadanaio visibile. Domanda sul reintegro risolta: selezionato Mantieni il residuo. Nessun apporto esterno o consumo del vault dopo perdite; accantonare eccedenza netta oltre1000, senza chiusureforzate a mezzanotteUTC.
- Prenotati daChatGPT: backend/desk classici su work/classici-5818-vault-20261027 da d1701f2; lettura/UI Salvadanaio su work/classici-salvadanaio-dashboard-20261027 da main4cf41d2 (storie separate, niente merge tra main/rule-pool).
- Backupcodice89b0dca e d1701f2 esistenti preservati. Nessun push su main/rule-pool/stable, trigger, deploy, ordine o scrittura ai dati operativi. Implementazione e test solooffline, poi diff finale per conferma separata deploy.


## Rollback classici: implementazione pronta, CI verde, NON DEPLOYATO
- Baseline approvata 5818aee; mantenute tutte le correzioni motore/LONG. Engine corrente conservato: solo default stop giornaliero torna al 12%. Guardian avanzato escluso dall'esecuzione.
- Ripristinati C70/A-B60, Bull3slot/Hawk10, sizing storico, macro originale attiva e stagionalità originale; rimossi dal percorso classico regime/P1/P2/veti e sizing percentuale successivi. SL resta1.2ATR come5818, feed daily successivo escluso ma correttezza dati mantenuta.
- Salvadanaio automatico solo PAPER: surplus netto sopra1000 al confine UTC, saldo separato e storico giornaliero visibili, pending distinto. Dopo perdita conserva residuo: nessun rabbocco/consumo vault, nessun reset o chiusura forzata. Prima attivazione senza inventare storico, posizioni/memoria conservate. Stato vuoto esistente rifiutato; prima installazione gestita. Journal separato salvadanaio-journal.jsonl con snapshot atomici e recupero crash; vecchio journal V1 non riscritto.
- Ramo bot work/classici-5818-vault-20261027: codice 08a8e6c644540b367adb6e052c5a6925a36a1e19; HEAD 27d2bf03fa2fba22f5021ec99f3c6720807d8583 (ultimo commit solo documentazione). Base d1701f2.
- Ramo app work/classici-salvadanaio-dashboard-20261027: codice e236d399e9c78ff9222bd817e59529a91f743e8f; HEAD 56dc4bb62f64024d1ea7e5bc84602fbf52ea4ace (ultimo commit solo documentazione). Base main4cf41d2. Dashboard in sola lettura, saldo/accrediti/pending/ultimo aggiornamento; P&L include vault, operativo distinto. Storie main/rule-pool mantenute separate.
- Test GitHub: 187 base/rollback/correzioni/journal +71 adapter fake +15rulepool +44guardie deploy =317; immagine bot e import sanity verdi. App:43reader,3React, build CRA completa verde. Run CI: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40558479403 e https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40558483663 . Ultimi commit documentazione [skip ci], prodotto identico a quello testato.
- Diff bot: https://github.com/alexiptv82/SuperBot-Trading/compare/d1701f22f2a615ac3ef05f96b9d1d3b297abf0bc...27d2bf03fa2fba22f5021ec99f3c6720807d8583 ; diff app: https://github.com/alexiptv82/SuperBot-Trading/compare/4cf41d23bb94f7a868b25dd1c89b3e4e8993d9a8...56dc4bb62f64024d1ea7e5bc84602fbf52ea4ace . Dettaglio: diario/ROLLBACK-CLASSICI-2026-10-27-DIFF-FINALE.md.
- main4cf41d2/rule-poold1701f2 invariati verificati. Backup codice precedenti conservati; nessun deploy, trigger operativo, accesso/scrittura VPS, ordine o modifica agli archivi operativi. DESK_MODE resta PAPER. Nessun intervento ai Brain adattivi; nessun force push.
- Prenotazioni implementazione concluse: pronto per revisione operatore. Attesa conferma SEPARATA per futuro rilascio bot+app; backup dati/immagini e ispezione runtime attuale da fare prima del deploy. Nessun test garantisce risultati economici della baseline storica.


## IN_CORSO — deploy rollback classici e dashboard AUTORIZZATO
- ChatGPT Work: ricevuto OK esplicito utente «OK al deploy. Procedi.». Prenotati rilascio classici e app Salvadanaio, candidati bot27d2bf03/app56dc4bb6 già testati. PAPER obbligatorio, nessun reset, archivi protetti append-only, Brain adattivi intoccati.
- Prima controllo runtime, sorgenti, istanze e backup/restore; poi integrazione dei soli due rami approvati nelle rispettive storie e trigger con SHA immutabile. Deploy classici e app sequenziali, controllo finale Salvadanaio e continuità dati. Workflow desk-deploy contiene guardia sorgente35f08cf obsoleta rispetto al runtime89b0dca: aggiornamento guardia ammesso solo dopo prova runtime, nessuna modifica strategia ulteriore.


## Checkpoint preflight deploy approvato — 27/10
- Run40564193487: sorgenti runtime89b0dca verificati per sei moduli, PAPER, istanza singola, Hawk2/Bull3posizioni; app4cf/Brain129/legacy1f2 confermati. Backup bots-20261027-185400-classici_vault_preflight e DBclassici-vault-app-20261027-185401.db: hash/integrità/restore PASS. Nessuno stop o restart.
- Verifier fallisce successivamente per FileNotFoundError: errors.md opzionale assente nel backup (non richiesto dal backup ufficiale). Corretto SOLO verificatore per memorizzare assenza e non creare/scrivere il file. Nuovo preflight avviato. Nessun dubbio su dati da sanare per tentativi; memoria operativa intatta.


## Pre-deploy rollback classici — autorizzazione eseguita in sequenza
- Preflight40564354802 SUCCESS18:55UTC: sei moduli89b0dca verificati, entrambiPAPER/healthy/istanza singola; Hawk2/Bull3posizioni. Backup bots-20261027-185504-classici_vault_preflight e classici-vault-app-20261027-185505.db con restoreverificato. Snapshot privato continuità suVPS, nessun saldo pubblico.
- Integrato ramo bot con merge3abf1f808b09bf9066d96a1d16f945d65601ba02 su rule-pool [skipci]; codice trading identico al diff27d2 approvato. Sole aggiunte ops: guardia sorgente89verificata, verifierpre/post e backup journalSalvadanaio obbligatorio invece diV1quando policyvault-only. Test91backup/deployguard +1selector/danneggiamentojournal PASS, oltre317+43+3 giàverdi.
- Appmain avanzato fast-forward a56dc4bb62f64024d1ea7e5bc84602fbf52ea4ace; nessun merge tra main/rule-pool. Pushmain nonrilascia. Imminente triggerdesk con sha3abf e capital=off: stop/restartsequenziale soli classici, backup ulteriore e immagini rollback; poi apppinnata56dc. Brain adattivi elegacy intoccati. OKutente esplicito inquestachat, PAPER/noreset.


## Classici deploy SUCCESS — dashboard successiva
- Workflow40564697020/job122402718915 SUCCESS: SHA3abf1f808b09bf9066d96a1d16f945d65601ba02 su entrambi classici, heartbeat3abf1f8, processi nuovi e istanza singola, PAPER e CapitalV1off verificati; backup obbligatorio prima dei riavvii, immagine rollback conservata. Nessun reset. Verifica indipendente continuità/vault ancora da eseguire dopo app.
- Imminente deploy ufficiale app da56dc4bb62f64024d1ea7e5bc84602fbf52ea4ace per rendere visibile il Salvadanaio. OKutente medesimo rilascio, backupSQLite/restore e immagine/frontend precedenti conservati dal workflow. Non interviene sui workerclassici né Brain.


## Dashboard Salvadanaio deploy SUCCESS — postflight in corso
- App40565004065/job122403831134 SUCCESS19:01UTC, SHA56dc4bb62f64024d1ea7e5bc84602fbf52ea4ace; codice/server/frontend coerenti, HTTPAPI e frontend200. Backup DBsuperbot-deploy-20261027-190057.db verificato con restore; rollbackappsuperbot:prev e frontendbuild.prev conservati. Nessun riavvio dei worker previsto dal workflow app.
- Avviata verifica indipendente postflight: sorgenti/policy/health classici, prefixhash archivi precedenti, run/posizioni/budget, identità immutata di tutti i container non coinvolti (Brain inclusi), reader reale dashboard e manifestofrontend, backup nuovo journalSalvadanaio con restore. In attesa esito, non dichiarare ancora continuità finale provata.


## ROLLBACK CLASSICI + SALVADANAIO LIVE PAPER — 27/10, 20:02 Roma (19:02 UTC)
- OK deploy esplicito utente eseguito. Classici Hawk/Bull su3abf1f808b09bf9066d96a1d16f945d65601ba02, heartbeat3abf1f8, healthy/restart0/PAPER, istanza singola. Metodo5818 selettivo come diff approvato, anti-biasLONG/SHORT e bugfixmotore mantenuti, P1/regime/Guardianavanzato esclusi. CapitalV1off, policySalvadanaioonlyREADY.
- App su56dc4bb62f64024d1ea7e5bc84602fbf52ea4ace, HTTP200, codiceserver/frontend/manifesto coerenti. Bundle frontend contiene Salvadanaio e reader reale installato restituisce available/ready per Hawk/Bull. App non ha DockerHEALTHCHECK: verificato HTTP, non inventare healthy.
- Deployclassici40564697020 SUCCESS18:58UTC; backupbots-20261027-185733-deploy + immagine superbot-desk:rollback-20261027-185733. Deployapp40565004065 SUCCESS19:01UTC; backupSQLite superbot-deploy-20261027-190057.db con restorePASS, superbot:prev e build.prev preservati.
- Postflight indipendente40565394446/job122405174661 SUCCESS19:02:12UTC: sorgenti sette moduli classici hashidentici al codice approvato, nuovi heartbeat/cicli riusciti; archivi protetti prefixhashidentici al preflight (append consentito), run_no/run_started_ms invariati, budgettotale non diminuito. Tutte le posizioni precedenti conservate:2Hawk/3Bull. Nessun reset o ricostruzione account; nessuna modifica manuale a memoria/storico/flag.
- Nuovo backupbots-20261027-190211-classici_vault_postflight: include salvadanaio-journal.jsonl (2righe ciascuno), hash/JSON/ripristinoPASS; vecchi journalV1 intatti (11Hawk/8Bull). Tradehistory279Hawk/152Bull, lessons45/54righe; learningcresce normalmente. errors.md assente prima non creato dal deploy. Nessun importo reale esposto.
- Tutti i container non coinvolti, inclusi Brain129547ed e legacy1f2edeb6, hanno stessoID/StartedAt del preflight: nessun riavvio o cambiamento. HI-TV mai contattato. Nessun ordine live.
- Salvadanaio: primaattivazione senza accreditare profitto passato fittizio. Eccedenza netta realizzata sopra1000 al rollover00:00UTC, residuo dopo perdite, nessun reintegro né prelievo dal vault. Pending distinto, nessuna chiusura forzata. Primo rollover live ancora da osservare: testofflinePASS non equivale a evento già avvenuto.
- Opsdi rilascio: guardiasorgente89misurata; backup riconosce journalSalvadanaio come critico/obbligatorio al postoV1quando policyvault-only.91testbackup/deployguard +1testselezionejournal/corruzionePASS; nessuna modifica aggiuntiva a strategia. Primo preflightfallito perverifiererrorsopzionale giàdocumentato, nessun restartcorrettivo.
- HEADrule-pool ora183fdb7b1bf25140d2d236c98e50262b5cd3411b (ultimi commit solo trigger/verifier), main56dc; differiscono dal codice botdistribuito3abf intenzionalmente. Trigger verifier disarmato phase=none approved=no [skipci], vecchi backup/immagini conservati. Riserva rilascio ChatGPT conclusa. Prossimo: osservare prima giornata/rollover senza modificare parametri; nuovi deploy richiedono nuovoOK.


## Brain AI libero — SOLO PIANO, attesa OK implementazione
- BriefClaude27/10 allegato letto; decisioni utente successive prevalgono: UNcontoPAPER2000nuovo/azzerato, treprofiliBrain sostituiti soloal futurocutover con archivi preservati; classici e Salvadanaio intatti.
- AIunicodecisoreH24, Hawk/Bull solo contesto, memoriaultimi10trade e motivazioneprimaapertura; dominanceBTC/FearGreed/macro come contestoNONfiltro. Leve45/30/25,margine1600,slotproposti10,datistale/schema/liquidazione. Nessun RR/regime/ATR/orario/cooldown/budgetstop o fallbackregole; nuovo namespace isolato da129547ed, no modifica desk/classical_adaptive/brain_pilot.
- SpesaDeepSeekoggi+cumulato e report/Telegram[BRAIN] richiesti senza cap; listinoofficialverificato, riferimento1.50nonlimite. Credito/API indisponibile non eliminabile via software. Proposti analisi15min/gestione5min/supervisore5s, report22Roma. Test168ore daeffettivostartverificato, non retroattivo.
- Piano completo diario/BRAIN-AI-LIBERO-PIANO-2026-10-27.md. Brief allegato conservato accanto, segnato storico/non decisioni correnti. Ora nessuncodice/branch/container/reset/deploy; attesa OKpiano, poi test/diff e OKdeployseparato. ChatGPTautoreproposto, nessuna revisioneClaude indipendente dichiarata.


## IN_CORSO — Brain AI libero IMPLEMENTAZIONE autorizzata, NO DEPLOY
- Utente conferma10slot e implementazione/testoffline, aspetta diffprima del deploy. Piano893ef387 approvato: contoPAPER2000nuovo, margine1600, AIonly/no gate strategici/no budgetcap, memoria10, contesto opzionale, Telegram[BRAIN], report22Roma,168hdaavvioverificato.
- ChatGPTWork prenota backend/director/brain_free, nuovi ops/test su work/brain-ai-libero da129547ed; dashboard/reader nuovi su work/brain-ai-libero-dashboard da main56dc. Non modificare desk/*, classical_adaptive/*, brain_pilot/*; classici/Salvadanaio/Brainoperativi intatti. Nessun reset effettivo, stop, migrazione o deploy autorizzati ora. Altro autore solo revisione.
