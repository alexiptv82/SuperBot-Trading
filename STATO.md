# STATO CORRENTE SuperBot-Trading — 27 ottobre 2026
Fotografia aggiornata alle 05:19 UTC (06:19 Roma). Per lo storico consultare le sezioni sottostanti e diario/2026-10-27_chatgpt.md. Protocollo: SINCRONIZZAZIONE-WORK-CHAT.md.

## Runtime PAPER attuali — verificati sul VPS Singapore
- **Classici Hawk e Bull:** SHA `89b0dca3e259c548ed82754c2301c7b024d18ff5`, deploy Claude 27/10 03:59UTC. Entrambi healthy/PAPER, restart0; started_at Hawk03:59:19.624UTC e Bull03:59:42.179UTC. Il rilascio Brain non li ha riavviati. Pesi classici e filtro regime approvati; Bull rischio SL aggregato250; DESK_CAPITAL_V1=off.
- **Hawk + Brain / Bull + Brain LIVE PAPER:** due processi `superbot-brain-hawk`/`superbot-brain-bull`, SHA `5024fbdfe3a9719098f905b28eac5d0feb9848e6`, healthy/restart0, partiti05:15:31UTC. Attivazione40453369414 SUCCESS05:17:42UTC; source PR14, merge operativo b17e79a7. Ciascuno conto separato1000PAPER; metodo classico corrente e relativi limiti, supervisione locale1m H24, segnali15m/cooldown nativi, AI asincrona entro budget. Nessun ordine LIVE.
- Verifica readonly40454674575 SUCCESS05:19:46UTC: 5cicli ciascuno, equity/cash1000, margine0, nessuna posizione ancora aperta, nessun entry_cycle_failed, feed freschi/coverage integra, pause nuove rimosse. Origine attuale classical_rules; provider paced_profile_allowance. Non dichiarare già verificati trade eseguiti o redditività.
- **Brain precedente** `superbot-brain-pilot` SHA1f2edeb6182029adc96ba7218ad145a7503472a3, healthy/PAPER/restart0, partito26/10 14:54:27UTC. Le4posizioni restano gestite e visibili nel conto precedente; SOLO nuove aperture/chiamate AI in pausa tramite pause.flag. Dati/storico/memoria non azzerati.
- Budget Brain CONDIVISO0.50USD/giorno e12/mese, non raddoppiato. Spesa legacy conservata e checksum congelato verificato: riservato giorno0.256114/mese0.356914; nessuna prenotazione nuova al controllo. AI al momento limitata dal pacing e consumo precedente; supervisione e fallback regole attivi. Non aumentare budget implicitamente.
- Dati nuovi: /opt/superbot-brain-adaptive/brain-hawk e brain-bull; ledger parent brain-api-budget.sqlite3. Identità metodo persistente: futuri aggiornamenti codice richiedono migrazione conservativa esplicita, nessun reset per aggirare la guardia.
- Storico classico reale NON ancora importato come experience_seed.json. Memoria nuovi esiti predisposta/persistente, nessun retraining dichiarato; euristica uscita su profitto netto/indebolimento sperimentale PAPER. LONG/up e SHORT/down e veti opposti testati; non prova della redditività LONG.
- Trigger attivazione DISARMATO (action=none/approved=no, commit3333e62c); non rilanciare primo avvio su dati esistenti. Tutti gli archivi classici e precedenti restano intatti.

## App Dashboard — tre conti Brain LIVE
- SHA `4cf41d23bb94f7a868b25dd1c89b3e4e8993d9a8`, main PR15, deploy40452932435 SUCCESS05:02:43UTC. Frontend/SHA/API/nginx/HTTPS e backup/restore DB verificati. App non ha Docker HEALTHCHECK: endpoint HTTP /api/health verificato200; non inventare Docker healthy.
- Tab BRAIN: **Hawk + Brain / Bull + Brain / Brain precedente**. Margine, leva effettiva, esposizione, floating e netto stimato, età/stop/target, origine AI/regole e proposte separate dalle esecuzioni; nessun saldo fittizio se profilo assente, nessuna somma dei conti.
- GET /api/brain/profiles autenticato/no-store; reader SQLite mode=ro/query_only con deadline, parent /opt/superbot-brain-adaptive montato:ro e BRAIN_ADAPTIVE_DATA_DIR. GET /api/brain/status compatibile, vecchio root brain:ro/BRAIN_DATA_DIR mantenuto.
- Postflight ha interrogato reader reale dentro app e controllato tutti gli SHA/PAPER/health dei5worker, pause/feed/ledger/vecchie4posizioni. Il primo postflight40454569926 fallì per asserzione erronea Docker health app; corretto SOLO verifier con controllo HTTP, nessun redeploy/riavvio correttivo.
- Backup preflight: /opt/superbot-backups/brain-adaptive-preflight-20261027T042052Z (integrity+restore comparato PASS). Backup finale preattivazione: /opt/superbot-backups/brain-before-adaptive-20261027T050607Z. Backup DBapp: /opt/superbot-backups/superbot-deploy-20261027-050221.db (restore comparato PASS); rollback immagine/frontend conservati.
- CI runtime finale40452483812/40452479075 e legacy40452483743 SUCCESS;32testnuovi,142regressioni+Docker5posizioni. App41testreader/API+10React+build, CI40451305609/40451300902 e main40452532496 SUCCESS.

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
