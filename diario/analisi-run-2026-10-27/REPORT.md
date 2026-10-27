# Audit forense run classici Hawk/Bull — 27 ottobre 2026

**Solo PAPER, sola lettura operativa.** Snapshot trade 2026-10-27T14:30:30.415Z. Nessun cambio a strategia, soglie, prompt, limiti, modalità, file di memoria; nessun deploy/restart/reset. Gli importi qui riportati sono risultati del simulatore PAPER. I file operativi originali non sono pubblicati; solo campi consentiti, dati pubblici di mercato e impronte. Non contiene saldi o importi di trading reale, credenziali o risposte/prompt privati.

## Risultato principale

Non è dimostrata una causa unica. Il primo crollo precede sia Fix A sia il pacchetto motore/soglia del 21/10: Hawk #3 perde con Tier C ancora a 70 e punteggi d’ingresso C più alti della run positiva. SL=1,2×ATR era già presente nelle run positive. Cambiano realmente mercato, disponibilità/uso di Claude, numero e composizione dei trade, poi input/motore/soglie/slot; i cambi sono sovrapposti, senza replay controfattuale non separabili. Nelle ultime due run complete le fee registrate sono sufficienti, contabilmente, a portare sottozero un risultato prima di quelle fee positivo; questo non dimostra che i costi siano aumentati né che basti eliminarli.

## Metodo, riconciliazione e unità statistica

Fonti: `trade_history.jsonl` root e copie archiviate, `state_v2.json` archiviati, `summary.json`, eventi numerici di `learning_log.jsonl`; Actions SSH/deploy manifest e versioni runtime; candele pubbliche Bitget futures 1H. I due root hanno 278+149=427 realizzi; il multinsieme di identificativi, tempi, margini e netti coincide esattamente con tutte le chiusure degli stati, inclusa la run attiva. Le copie storiche non sono ricontate. Le run complete contengono 404 realizzi, ma **357 posizioni complete**: sommo chiusure parziali e finale per `(bot,run,id,symbol,side,open_ms)`. Ogni gruppo ha esattamente una chiusura finale, nessuna durata negativa; totale netto riconciliato con ogni summary entro 0,02 USD (arrotondamenti).

Il WR dashboard conta realizzi, non prove indipendenti. Per l’analisi principale una posizione vince se la somma dei suoi netti è positiva; profit factor = somma netti positivi / valore assoluto somma netti negativi. Commissioni/funding sommati su tutte le tranche; durata fino alla finale; una parziale non libera lo slot. Le medie non sono normalizzate per capitale o rischio: margini/leve differiscono. Intervalli Wilson descrittivi al 95%, con ipotesi di indipendenza ottimistica data la correlazione tra simboli e posizioni sovrapposte.

Il collector apre le fonti `O_RDONLY|O_NOFOLLOW`, controlla PAPER, esporta whitelist, non importa il runtime trading e non scrive flag o dati bot. Durante la lettura size/mtime dei sei file protetti presenti non cambiano; `errors.md` è assente in entrambi i profili e non è stato creato. `lessons.md` è esportato solo come hash. Controlli, file hash e byte letti: [source_provenance.json ](source_provenance.json). Gli autonomi writer bot non sono stati fermati; per questa acquisizione le statistiche prima/dopo sono stabili.

Acquisizioni readonly: [run iniziale ](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40520808530), [trade/livelli/mercato ](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40521704685), [copertura e macro ](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40524300414). Estensione delle sole candele pubbliche ai simboli SOL/BNB/XRP: [run 40526731267](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40526731267). I conteggi delle call provengono dalla lettura metadata delle 14:46 UTC; trade e run restano fissati allo snapshot delle 14:30 UTC. Nessuna acquisizione è un redeploy.

## 1. Run e codice realmente eseguito

Tutti gli orari delle tabelle sono **UTC**, date 2026; il CSV deploy contiene anche Europe/Zurich (UTC+2 fino al 24/10, UTC+1 dal 25/10). Intervallo run = apertura del conto/reset fino all’archiviazione, non primo/ultimo trade. Un SHA nella run può avere zero nuove aperture. Le run non corrispondono a un commit singolo; `summary.params` è fotografia finale, non configurazione di tutti i trade.

| Run | Inizio UTC | Fine UTC | Versioni runtime in ordine |
| --- | --- | --- | --- |
| Hawk #1 | 2026-10-12T14:51:23.724Z | 2026-10-12T14:51:23.724Z | a0afc63 |
| Hawk #2 | 2026-10-12T14:51:23.726Z | 2026-10-16T02:49:49.578Z | a0afc63 → 7ced3a6 → 5a4e383 → 9fa667f → 5818aee |
| Hawk #3 | 2026-10-16T02:49:49.589Z | 2026-10-19T17:36:50.107Z | 5818aee → 18d145f → b4709d1 |
| Hawk #4 | 2026-10-19T17:36:50.111Z | 2026-10-22T06:10:33.389Z | b4709d1 → b6b9911 → fa3e220 |
| Hawk #5 | 2026-10-22T06:10:33.393Z | 2026-10-26T18:55:45.799Z | fa3e220 → f87f2d6 → 297b126 → 886b30f → 63641f7 → 35f08cf |
| Bull #1 | 2026-10-12T14:48:44.501Z | 2026-10-16T02:50:48.667Z | prima apertura: 43c79cf/a0afc63 incerto; poi a0afc63 → 7ced3a6 → 5a4e383 → 9fa667f → 5818aee |
| Bull #2 | 2026-10-16T02:50:48.671Z | 2026-10-19T17:37:17.089Z | 5818aee → 18d145f → b4709d1 |
| Bull #3 | 2026-10-19T17:37:17.092Z | 2026-10-21T03:58:05.990Z | b4709d1 → b6b9911 |
| Bull #4 | 2026-10-21T03:58:05.993Z | 2026-10-26T18:55:46.717Z | b6b9911 → fa3e220 → f87f2d6 → 297b126 → 886b30f → 63641f7 → 35f08cf |


Hawk #1 è uno snapshot tecnico vuoto di 0 secondi. La prima posizione di Bull #1 (14:48:44 UTC) cade dentro la finestra del deploy iniziale: non ha code_version. Non posso distinguere con certezza 43c79cf dal nuovo a0afc63 per quel singolo ingresso; il CSV lo marca deployment_transition_uncertain e lascia SHA vuoto. Le restanti attribuzioni golden sono inferenze dagli intervalli di deploy, non tag presenti nei trade. Le prime due posizioni di Hawk #2 e Bull #1 precedono la strumentazione entry; gli ingressi golden non hanno `code_version`. La sequenza golden si ricostruisce dai deploy: la prima parte non girava su 5818aee (arrivato solo il 15/10 sera). Le versioni successive sono confermate direttamente dal learning log. Eventi e conteggi di aperture/chiusure per versione: [version_events.csv ](version_events.csv).

| Deploy / prova | Finestra UTC di esecuzione workflow o osservazione | Codice effettivo | Esito |
| --- | --- | --- | --- |
| #26 | 2026-10-12T14:04:58Z → 2026-10-12T14:06:08Z | 43c79cf | success, predecessore iniziale |
| #27 | 2026-10-12T14:48:01Z → 2026-10-12T14:49:11Z | a0afc63 | success |
| #28 | 2026-10-12T16:50:01Z → 2026-10-12T16:51:13Z | 7ced3a6 | success |
| #29 | 2026-10-13T06:36:44Z → 2026-10-13T06:37:50Z | 5a4e383 | success |
| #30 | 2026-10-13T07:51:20Z → 2026-10-13T07:52:30Z | 9fa667f | success |
| #31 | 2026-10-15T19:45:57Z → 2026-10-15T19:47:04Z | 5818aee | success |
| #32 | 2026-10-16T08:01:40Z → 2026-10-16T08:02:45Z | 18d145f | success |
| #33 | 2026-10-16T09:42:46Z → 2026-10-16T09:43:50Z | b4709d1 | success |
| #34 | 2026-10-21T03:08:29Z → 2026-10-21T03:09:59Z | b6b9911 | failure_but_runtime_updated |
| #35 | 2026-10-21T06:14:10Z → 2026-10-21T06:15:31Z | fa3e220 | success |
| #36 | 2026-10-22T03:01:39Z → 2026-10-22T03:01:52Z | nessun nuovo SHA provato | failure_no_deployment_evidence |
| manifest + runtime | 2026-10-23T08:08:17.098Z → 2026-10-23T08:08:52Z | f87f2d6 | runtime_and_manifest |
| #37 | 2026-10-24T06:33:48Z → 2026-10-24T06:35:38Z | 297b126 | success |
| #38 | 2026-10-24T15:38:13Z → 2026-10-24T15:40:07Z | 297b126 | success |
| #39 | 2026-10-24T17:33:18Z → 2026-10-24T17:35:05Z | 297b126 | success |
| #40 | 2026-10-25T21:11:10Z → 2026-10-25T21:13:02Z | 886b30f | success |
| #41 | 2026-10-26T08:51:49Z → 2026-10-26T08:53:51Z | 63641f7 | success |
| #42 | 2026-10-26T18:31:46Z → 2026-10-26T18:33:40Z | 35f08cf | success |
| #43 | 2026-10-27T03:58:40Z → 2026-10-27T04:00:33Z | 89b0dca | success |


Le finestre Actions delimitano l’oper azione, non sono orari esatti di switchover simultaneo dei due container; il log HEAD mostra checkout, gli eventi runtime provano esecuzione. **#34 risulta failed ma b6b9911 è entrato realmente in esecuzione** (primi eventi Hawk 21/10 03:09:21, Bull 03:09:31); #36 fallito il 22/10 non prova alcun deploy. Fix A è provato da eventi del 23/10 08:08:17/27 e manifest 08:08:52. Trigger SHA e codice checkout possono differire: uso il secondo. [deployments.csv ](deployments.csv) conserva fonti/link e limiti temporali.

Correzione cronologica: Hawk #3 termina il 19/10; Hawk #4 termina il **22/10 06:10 UTC (08:10 Zurigo)**, non prima del 22. Entrambe precedono Fix A del 23. Bull #3 finisce l’archiviazione dopo il primo deploy b6, ma **tutti i suoi quattro ingressi e quattro esiti sono b4709d1, ultimo esito 21/10 03:02:38**, prima del b6. I parametri nuovi presenti nel summary Bull #3 non spiegano quei trade.

### Differenze funzionali tra revisioni effettivamente deployate

| Revisioni | Deploy UTC | Aperture / uscite / dati / limiti |
| --- | --- | --- |
| 43c79cf → a0afc63 | 12/10 14:48–14:49 | Pausa con gestione protettiva senza ingressi/DCA, comandi app distinti per budget/chiusure/reset conto e archiviazione; heartbeat e prezzi memorizzati; limiti codice riletti al caricamento, controlli sulle righe storiche. Nuovo loop 30/15 minuti e polling comandi 5s. Singola apertura Bull iniziale non attribuibile con certezza ai due lati dello switchover. |
| a0afc63 → 7ced3a6 | 12/10 16:50–16:51 | Split reale 50/50 con scadenza 3h scalp/12h medio, retrace max 60% distanza SL, annullamento su DCA/parziale/pausa/close; registrazione feature, MAE/MFE/R e candidati. Il prompt descrive split e seconda gamba. Non cambia lo scoring. Già entro le run positive. |
| 7ced3a6 → 5a4e383 | 13/10 06:36–06:37 | Audit chiamate Claude (risposta parsabile, token/stop); non cambia pesi/soglie/motore. |
| 5a4e383 → 9fa667f | 13/10 07:51–07:52 | Calendario finestre Claude e budget; fuori finestra restano regole. Cambia la disponibilità della fonte decisionale, non il punteggio tecnico. Configurazioni storiche delle finestre non versionate per ogni ciclo. |
| 9fa667f → 5818aee | 15/10 19:45–19:47 | Macro gate su nuove aperture e contesto prompt; trading-hours opzionali, pause/chiusura singola manuale, TP impossibili scartati; max risposta Claude PAPER 1100→3000 e timeout60→120s. Rimossa MATIC dall’universo. Live connector/sync e daily-loss LIVE non sono attivi nel PAPER. Politica di conservazione memoria al reset; non è una modifica fatta da questo audit. |
| 5818aee → 18d145f | 16/10 08:01–08:02 | Macro più selettiva tra eventi grandi e secondari; grandi -60/+120min, lookahead12→6h, extra soglia 5→3; secondari -15/+30min, nessun extra. Conteggio macro-blocco limitato ai candidati sopra soglia base. |
| 18d145f → b4709d1 | 16/10 09:42–09:43 | Macro in osservazione per default; enforce solo tramite flag/env esplicito. Negli ingressi delle run negative con campo disponibile, macro_enforced=false, blackout=false e bonus 0 (262 enforcement esplicitamente false; due primi ingressi negativi senza quel campo). Non prova assenza di altri blocchi in tutti i cicli non eseguiti. |
| b4709d1 → b6b9911 | 21/10 03:08–03:09 | Bundle e91 e successivi: Tier C70→63 (65 è commit intermedio non dimostrato come versione deployata); AB60 invariato. Esclude 15m in formazione dagli indicatori/uscite, ultimo prezzo ancora disponibile; feed daily260 barre, EMA50/200 vere con >=200 giorni. Barre protettive prima delle decisioni, una volta per cursor; barra d’ingresso inclusa con ambiguità intrabar dichiarata; DCA non allarga stop, daily reference corretta. Bull slot3→10, margine totale1050→1000, minimo disponibile150 rifiutato, cap leva Hawk #20/Bull #15 con rifiuto sopra cap. I moduli profit/sidecar/turbo separati non equivalgono a hook attivo del classico; exit_first LIVE non cambia PAPER. |
| b6b9911 → fa3e220 | 21/10 06:14–06:15 | Rimossi cap leva profilo20/15; restano tier motore45 BTC/XAU/XAG,30 ETH,25 altcoin e vincolo stop/liquidazione. Bull slot10→6, totale1000→1050. Nessun cambiamento al coefficiente SL. |
| fa3e220 → f87f2d6 | 23/10 08:08 | Fix A: feed4h nativo e warmup EMA200 vero, prima slow EMA su circa 61 barre ricampionate; uguaglianze neutrali, RSI piatto neutro, punteggio proprio/opposto corretto per gestione/prompt. Daily history endpoint/cache/retry corretti e scheda posizione. Questo può cambiare input/lettura, non spiega perdite antecedenti. |
| f87f2d6 → 297b126 | 24/10 06:33–06:35 | Daily stop legacy 12%→10% (il caricamento dei limiti dal codice esisteva già in a0); Capital V1 opt-in PAPER, rollover/cassa/vault/sizing e outbox chiusure; arricchimento OI/funding/long-short ratio nel contesto. V1 abilitato solo successivamente 15:40 e disabilitato17:35 stesso SHA: vedere sotto, non trattare tutto il giorno come identico. |
| 297b126 → 886b30f | 25/10 21:11–21:13 | P1 pesi 4h20→14,1d15→10, bonus LONG rimbalzo10; P2 risposta Claude senza decisioni non autorizza nuove aperture fallback (solo gestione), indisponibilità sì. Può cambiare campione ingressi dopo questa ora. |
| 886b30f → 63641f7 | 26/10 08:51–08:53 | Aggiunti profit_guardian e portfolio_alert, ma cli/engine non modificati e nessun hook di esecuzione classico attivato: presenza del file non prova modifica alle uscite. |
| 63641f7 → 35f08cf | 26/10 18:31–18:33 | Stagionalità additiva invece moltiplicativa e frenata dal BTC3 giorni; Bull rischio SL aggregato160 e veto SHORT se BTC24h>+2%. Nessuna nuova apertura/chiusura registrata con 35f nelle run complete Hawk #5/Bull #4 prima del reset18:55, quindi non attribuirgli i risultati già maturati. |
| 35f08cf → 89b0dca | 27/10 03:58–04:00 | Filtro regime BTC nuovo, pesi classici20/15 ripristinati per default, Bull cap rischio250, ratchet/flip disattivi. Solo run attive Hawk #6/Bull #5: non causa run complete negative21–26. |


Inventario completo dei file desk modificati e dei nodi AST top-level (classi/funzioni/globali), con link ai diff integrali per tutte le transizioni: [code_changes.json ](code_changes.json). Include anche moduli non attivati e test per rendere verificabile il perimetro; un nodo cambiato non è da solo prova di effetto operativo.

Capital V1: le Actions #38/#39 e i trigger documentano ON 24/10 ~15:40 e OFF ~17:35 senza cambio di SHA 297. Nel codice V1 il budget giornaliero è distinto dal conto legacy, cap posizione 10% Hawk/25% Bull,6 slot Bull, daily stop 20%, latch/fail-closed fino a rollover valido. Il toggle non prova stato READY né sizing eseguito: mancano snapshot/journal V1 storici in questa acquisizione. Non mescolo questo20% con il daily_stop legacy10%, né il limite `_daily_loss_exceeded` LIVE con il PAPER. Nessuna quantificazione causale di questa breve finestra.

### Limiti di base e sizing verificati nel codice

| Profilo / periodo | Margine per nuova posizione | Margine totale / slot | Leva e stop giornaliero legacy |
| --- | --- | --- | --- |
| Hawk, baseline e successive | massimo 100 PAPER; guardrail sotto 50 o leva sotto 10 forza 60 / 15x | 1000 / 10 | tier 45 BTC/XAU/XAG, 30 ETH, 25 altri; daily 12% fino a f87 |
| Bull fino a b470 | massimo 350; guardrail sotto 150 o leva sotto 10 forza 200 / 15x | 1050 / 3 | stessi cap tier; daily 12% |
| b6, breve finestra 21/10 | Hawk invariato; Bull rifiuta se spazio disponibile sotto 150 | Bull 1000 / 10 | rifiuto sopra Hawk 20x / Bull 15x; daily 12% |
| fa3 / f87 | Hawk invariato; Bull massimo 350 e minimo disponibile 150 | Bull 1050 / 6 | cap profilo rimosso, tier invariati; daily 12% |
| 297 e successive, V1 spento | come fa3 | come fa3 | daily legacy 10%; V1 acceso è una policy distinta |

Tetti comuni del motore: minimo eseguibile 30, limite totale DCA 700, kill equity 450 PAPER, margine disponibile limitato anche al 95% della cassa; vincolo distanza stop/liquidazione conservato. Le aggiunte DCA dipendono anche dal tetto per asset e dalla cassa. Cooldown invariati: scalp 15 minuti, medio 1 ora. Il normale ciclo è 30 minuti, con scalp aperti o in svuotamento 15 minuti; non è monitoraggio tick-by-tick.

Il fallback delle regole propone leva/margine dal punteggio: `frac=clip((score-60)/40,0,1)`; scalp leva `round(15+30*frac)` e margine `round(150+100*frac)`, medio leva `round(5+20*frac)` e margine `round(80+170*frac)`. Poi intervengono guardrail, tier, spazio cassa e limiti del profilo: la proposta non è il margine effettivo. La chiusura da regole valuta score del proprio lato sotto 35 o score opposto almeno 60; non è un timer fisso. Le modifiche successive elencate sopra si applicano dopo il relativo deploy, non retroattivamente.

### Coppie di run consecutive: quali transizioni attraversano

| Coppia | Differenze che entrano nella seconda run / transizioni interne |
| --- | --- |
| Hawk #1→2 | Snapshot vuoto→run; a 0→7ced→5a 4→9fa→5818. |
| Hawk #2→3 / Bull #1→2 | 5818→18d→b470: calendario macro/observation e uso Claude; SL1.2, pesi e C70 invariati. |
| Hawk #3→4 | b470→b6→fa 3 durante Hawk #4; prime perdite e LIQ del 20 avvengono ancora su b470. |
| Bull #2→3 | b470 per tutti i quattro trade; b6 entra solo dopo la loro ultima chiusura. Confronto non attribuibile a nuovi parametri finali. |
| Hawk #4→5 | fa 3→f87→297 (toggle V1 ON/OFF)→886→636→35f: input4h/daily, daily stop, P1/P2, poi moduli shadow e veto/rischio tardivi. |
| Bull #3→4 | b6 senza aperture→fa 3 e successive f87/297/886/636/35f: slot/minimo, threshold63 e nuovo motore rispetto ai trade Bull3. |
| Hawk #5→6 / Bull #4→5 | 35f→89 solo nelle run attive, escluso dal confronto conclusivo. |


### Scoring e SL: cosa è provato

SL1,5→1,2×ATR è nel commit f7fbf19 dell’11/10, **prima delle run positive**. Per tutte le versioni confrontate fino al27: `SL=min(3,5%,max(0,3%,1,2×ATR%))`, TP tecnico=1,8×SL. Il valore percentuale cambia con ATR e clipping; non è una riduzione post-golden del coefficiente. DCA e stop spostati restano distinti dallo stop proposto iniziale.

Pesi baseline5818 contro bundle20/21:4h20,1h15,1d15 se presente, prezzo/EMA8, momentum0..12 sat3%24h, breakout10, RSI8, volume4 sopra 1,3, pattern8/doji−5, RSI estremo−12, stagionalità0..15: identici. La riduzione 4h/1d è P1 del 25 sera. Alzare warmup 1d30→200 non ha tolto punti1d agli ingressi golden: **nessun ingresso loggato** Hawk #2/3/4 e Bull1/2/3 ha contributo1d; 1000×15m sono circa 10,4 giorni, già insufficienti a 30. Inoltre tutti i74 ingressi loggati Hawk2 e38 Hawk3 hanno4h+20: la scomparsa di quei punti non spiega il primo crollo. Non estendo questa prova ai candidati non eseguiti. Nelle run tardive il contributo1d compare 39/112 Hawk5 e29/77 Bull4.

## 2. Trade per trade e metriche per run completa

Dati posizione per posizione con timestamp, fonte ingresso, versione ingresso/osservazione e finale, livelli iniziali disponibili, leva, margine, score, componenti/feature consentite, netto/fee/funding, durata, uscita e parziali: [positions.csv ](positions.csv). Ogni realizzo separato (incluse run attive marcate): [realizations.csv ](realizations.csv). Non sono copie dei file protetti. [run_metrics.json ](run_metrics.json) contiene distribuzioni e riconciliazioni numeriche complete.

| Run | Realizzi / posizioni | WR dashboard / posizione | Netto PAPER | Vincita media / perdita media | PF | Durata media h |
| --- | --- | --- | --- | --- | --- | --- |
| Hawk #2 | 76 / 76 | 60.5% / 60.5% | 1090.61 | 44.84 / 32.40 | 2.12 | 5.95 |
| Hawk #3 | 38 / 38 | 26.3% / 26.3% | -284.87 | 33.25 / 22.05 | 0.54 | 6.34 |
| Hawk #4 | 18 / 18 | 16.7% / 16.7% | -335.60 | 33.88 / 29.15 | 0.23 | 4.02 |
| Hawk #5 | 131 / 112 | 46.6% / 37.5% | -50.81 | 37.19 / 23.04 | 0.97 | 4.97 |
| Bull #1 | 30 / 17 | 80.0% / 70.6% | 770.75 | 79.47 / 36.58 | 5.21 | 11.86 |
| Bull #2 | 18 / 15 | 38.9% / 26.7% | -144.68 | 38.44 / 27.13 | 0.52 | 6.69 |
| Bull #3 | 4 / 4 | 0.0% / 0.0% | -312.41 | — / 78.10 | 0.00 | 6.81 |
| Bull #4 | 89 / 77 | 44.9% / 36.4% | -214.02 | 59.66 / 38.46 | 0.89 | 5.19 |


Bull #1:24 realizzi positivi/30=80%, ma 12 posizioni positive/17=70,6%. Hawk #5:61/131=46,6%, ma 42/112=37,5%. Bull #4:40/89=44,9%, ma 28/77=36,4%. Non confronto 80% con 44,9% come se fossero frequenze di posizioni indipendenti. Hawk #3WR26,3% e Hawk4WR16,7%: il WR38–46% non descrive tutte le run negative.

### Fonte decisionale

**357/357 ingressi di posizioni complete hanno source=rules**. Non risultano nuove aperture source=claude. Questo non significa che Claude non fosse consultato o non gestisse posizioni: i log mostrano chiamate e decisioni parsabili. Il campo source sui close è ereditato dall’ingresso, e la stringa “chiusura Claude” è usata dal ramo comune per close di entrambe le fonti: non dimostra chi abbia deciso l’uscita. Registro quindi quella categoria come “close decisionale, fonte uscita non identificabile”.

| Run | Call registrate | Risposte parsabili | Decisioni restituite totali |
| --- | --- | --- | --- |
| Hawk #2 | 47 | 1 | 4 |
| Hawk #3 | 56 | 56 | 398 |
| Hawk #4 | 51 | 51 | 277 |
| Hawk #5 | 60 | 60 | 443 |
| Hawk #6 | 7 | 7 | 42 |
| Bull #1 | 48 | 34 | 119 |
| Bull #2 | 64 | 64 | 288 |
| Bull #3 | 21 | 21 | 102 |
| Bull #4 | 99 | 99 | 481 |
| Bull #5 | 14 | 14 | 77 |


La strumentazione call inizia il 13/10: copertura incompleta delle golden. Hawk #2 ha 1/47risposte parsabili registrate, Bull #1 34/48; nelle prime negative56/56 Hawk3,64/64 Bull2. Cambia quindi realmente il contesto di disponibilità/parsabilità Claude, anche se le aperture rimangono da regole. Non ricostruibile da questi campi quanto ogni sua azione di gestione abbia prodotto profitto/perdita. `claude_calls.csv` omette deliberatamente spesa API e testo. Dalla fine25/10 P2 distingue hold Claude da indisponibilità per il fallback.

### Distribuzione score raw all’ingresso, separata per tier

Uso `features.sig_score`, non confidence del modello. Tier A/B=BTC, ETH, XAU, XAG; altri C. Mancano le feature delle prime 2 posizioni di ciascuna golden: n score353/357. Quantili su ingressi eseguiti, non su tutto l’universo di opportunità.

| Run | Tier | n score | Min / Q1 / mediana / Q3 / max |
| --- | --- | --- | --- |
| Hawk #2 | A/B | 23 | 60.0 / 61.5 / 63.0 / 72.5 / 77.0 |
| Hawk #2 | C | 51 | 70.0 / 71.0 / 71.0 / 73.0 / 79.0 |
| Hawk #3 | A/B | 9 | 60.0 / 65.0 / 66.0 / 66.0 / 75.0 |
| Hawk #3 | C | 29 | 70.0 / 71.0 / 74.0 / 78.0 / 79.0 |
| Hawk #4 | A/B | 4 | 60.0 / 61.5 / 62.0 / 62.2 / 63.0 |
| Hawk #4 | C | 14 | 63.0 / 64.2 / 69.0 / 75.0 / 75.0 |
| Hawk #5 | A/B | 19 | 60.0 / 61.5 / 63.0 / 67.0 / 78.0 |
| Hawk #5 | C | 93 | 63.0 / 65.0 / 68.0 / 75.0 / 94.0 |
| Bull #1 | A/B | 11 | 60.0 / 63.0 / 73.0 / 74.0 / 77.0 |
| Bull #1 | C | 4 | 72.0 / 72.0 / 72.5 / 73.5 / 75.0 |
| Bull #2 | A/B | 8 | 60.0 / 64.0 / 66.0 / 66.2 / 75.0 |
| Bull #2 | C | 7 | 70.0 / 70.5 / 72.0 / 73.0 / 76.0 |
| Bull #3 | A/B | 2 | 62.0 / 62.2 / 62.5 / 62.8 / 63.0 |
| Bull #3 | C | 2 | 75.0 / 75.5 / 76.0 / 76.5 / 77.0 |
| Bull #4 | A/B | 17 | 60.0 / 61.0 / 63.0 / 68.0 / 78.0 |
| Bull #4 | C | 60 | 63.0 / 65.0 / 68.0 / 75.0 / 84.0 |


Hawk #2 C mediana 71, Hawk #3C74: i punteggi **non erano sistematicamente più deboli nella prima run negativa** e C70 era ancora attivo. Bull #1 ha solo 4 score C disponibili contro 11A/B: la run positiva non dipendeva da tante altcoin sopra 70; sul totale posizioni C sono5/17 e A/B12/17. Bull #1 occupa in media 2,40 slot su 3, tutti 3 pieni58,36 ore su 84,03 (~69,4%), non sempre.

Filtro descrittivo sui trade realmente eseguiti, non simulazione di una soglia diversa: Hawk #5 C<70:53pos,+176,78; C≥70:40pos,−126,53. Bull #4 C<70:37pos,+135,70; C≥70:23pos,−171,94. Questo campione non sostiene “i trade63–69 hanno causato il rosso”. Non sommare questi gruppi per stimare una strategia 70: togliere ingressi cambia slot, capitale, cooldown e opportunità successive.

### LONG e SHORT

| Run | Lato | n | WR posizione | Netto | Netto medio |
| --- | --- | --- | --- | --- | --- |
| Hawk #2 | SHORT | 74 | 62.2% | 1222.05 | 16.51 |
| Hawk #2 | LONG | 2 | 0.0% | -131.43 | -65.72 |
| Hawk #3 | SHORT | 35 | 28.6% | -250.69 | -7.16 |
| Hawk #3 | LONG | 3 | 0.0% | -34.19 | -11.40 |
| Hawk #4 | SHORT | 14 | 21.4% | -191.34 | -13.67 |
| Hawk #4 | LONG | 4 | 0.0% | -144.26 | -36.06 |
| Hawk #5 | SHORT | 110 | 37.3% | -105.02 | -0.95 |
| Hawk #5 | LONG | 2 | 50.0% | 54.21 | 27.11 |
| Bull #1 | SHORT | 17 | 70.6% | 770.75 | 45.34 |
| Bull #1 | LONG | 0 | — | 0.00 | — |
| Bull #2 | SHORT | 13 | 30.8% | -122.95 | -9.46 |
| Bull #2 | LONG | 2 | 0.0% | -21.73 | -10.87 |
| Bull #3 | SHORT | 3 | 0.0% | -117.53 | -39.18 |
| Bull #3 | LONG | 1 | 0.0% | -194.88 | -194.88 |
| Bull #4 | SHORT | 76 | 36.8% | -171.91 | -2.26 |
| Bull #4 | LONG | 1 | 0.0% | -42.11 | -42.11 |


Le golden sono già quasi esclusivamente SHORT (Hawk #74/76, Bull #17/17). Le successive conservano la concentrazione SHORT. La direzione da sola non basta: quando BTC rimbalza/si muove lateralmente la stessa esposizione può diventare sfavorevole. I pochi LONG non permettono stima robusta del loro edge.

### Cause d’uscita e stop precoci

| Run | SL | TP | Close decisionale ambiguo | Manuale | LIQ | Trailing / timeout |
| --- | --- | --- | --- | --- | --- | --- |
| Hawk #2 | 29 (38.2%) | 45 (59.2%) | 2 (2.6%) | 0 (0.0%) | 0 (0.0%) | non identificabili |
| Hawk #3 | 16 (42.1%) | 10 (26.3%) | 10 (26.3%) | 2 (5.3%) | 0 (0.0%) | non identificabili |
| Hawk #4 | 11 (61.1%) | 1 (5.6%) | 1 (5.6%) | 4 (22.2%) | 1 (5.6%) | non identificabili |
| Hawk #5 | 59 (52.7%) | 36 (32.1%) | 16 (14.3%) | 1 (0.9%) | 0 (0.0%) | non identificabili |
| Bull #1 | 5 (29.4%) | 9 (52.9%) | 2 (11.8%) | 1 (5.9%) | 0 (0.0%) | non identificabili |
| Bull #2 | 4 (26.7%) | 4 (26.7%) | 6 (40.0%) | 1 (6.7%) | 0 (0.0%) | non identificabili |
| Bull #3 | 3 (75.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 1 (25.0%) | non identificabili |
| Bull #4 | 44 (57.1%) | 25 (32.5%) | 8 (10.4%) | 0 (0.0%) | 0 (0.0%) | non identificabili |


Percentuali sulla causa **finale della posizione**, non sulle parziali. Nessun tag finale affidabile per trailing/timeout: “0 osservati” non equivale a zero reali; uno SL può essere iniziale o spostato a protezione. La label manuale identifica il ramo manuale, non il motivo umano. I47 realizzi parziali sono nel CSV e già sommati nel netto della posizione.

| Run | SL totali | entro ≤1 / ≤2 / ≤4 intervalli15m | Leva mediana | Margine realizzato mediano | ATR mediana / SL proposto mediano |
| --- | --- | --- | --- | --- | --- |
| Hawk #2 | 29 | 0 / 0 / 5 | 23.0 | 100.00 | 0.994% / 1.192% |
| Hawk #3 | 16 | 0 / 0 / 8 | 24.5 | 100.00 | 0.800% / 0.961% |
| Hawk #4 | 11 | 0 / 0 / 0 | 19.0 | 100.00 | 1.172% / 1.407% |
| Hawk #5 | 59 | 4 / 4 / 9 | 20.0 | 100.00 | 0.889% / 1.067% |
| Bull #1 | 5 | 0 / 0 / 1 | 25.0 | 182.00 | 0.856% / 1.027% |
| Bull #2 | 4 | 0 / 0 / 1 | 22.0 | 175.00 | 0.572% / 0.686% |
| Bull #3 | 3 | 0 / 0 / 0 | 21.0 | 173.00 | 0.955% / 1.145% |
| Bull #4 | 44 | 3 / 4 / 10 | 20.0 | 165.00 | 0.777% / 0.932% |


Definizione stop precoce: differenza tra indice floor(close/15m) e floor(open/15m), non numero garantito di chiamate on_bar; include0..k e conta solo tag SL. Il vecchio motore saltava la barra contenente l’ingresso; il nuovo la include e usa un cursor. Quindi frequenze early-stop tra versioni sono confondibili con una diversa simulazione/esposizione ai controlli, non prova autonoma di stop più stretti sul rumore. Margine realizzato somma le tranche e può includere aggiunte: il margine iniziale effettivo, quando loggato, è in CSV. Gli SL proposti si riferiscono al segnale prima dello slippage, non a modifiche successive.

Due liquidazioni incidono materialmente prima Fix A: Hawk #4NEARSHORT20/10 08:50→14:15,−101,50 (~30,2%perdita run); Bull #3INJLONG20/10 15:10→15:30,−194,88 (~62,4%). Entrambi b470. Nel motore OHLC il controllo liquidazione precede quello SL: se una barra attraversa entrambi, la precedenza non ricostruisce il percorso dei prezzi. Senza esatto input 15m/intrabar non dimostro che questi due trade dovessero uscire SL o a quale prezzo. Inoltre LIQ sovrascrive il netto a−margine−fee_open: gross−fee−funding non riconcilia come negli altri esiti (residui~10,95 Hawk4 e21,20 Bull3), eccezione di contabilità nota, non fee nascoste inventate.

### Occupazione slot e frequenza

| Run | Slot medi | Ore senza posizioni (%) | Posizioni/giorno | Ore per occupazione |
| --- | --- | --- | --- | --- |
| Hawk #2 | 5.39 | 16.76 (20.0%) | 21.72 | 0:16.8h; 1:8.0h; 2:2.0h; 3:1.0h; 4:2.8h; 5:7.2h; 6:13.6h; 7:1.5h; 8:1.5h; 9:10.5h; 10:19.3h |
| Hawk #3 | 2.78 | 38.29 (44.1%) | 10.51 | 0:38.3h; 1:12.9h; 2:4.0h; 3:2.1h; 4:2.6h; 5:4.2h; 6:1.5h; 7:10.4h; 8:0.8h; 9:6.9h; 10:3.3h |
| Hawk #4 | 1.19 | 30.80 (50.9%) | 7.13 | 0:30.8h; 1:15.2h; 2:6.9h; 3:1.9h; 4:0.8h; 5:0.0h; 6:1.0h; 7:2.9h; 8:1.0h |
| Hawk #5 | 5.12 | 24.84 (22.8%) | 24.72 | 0:24.8h; 1:15.0h; 2:8.4h; 3:4.6h; 4:3.8h; 5:1.0h; 6:1.1h; 7:2.6h; 8:1.5h; 9:5.8h; 10:40.2h |
| Bull #1 | 2.40 | 11.05 (13.2%) | 4.86 | 0:11.1h; 1:2.7h; 2:11.9h; 3:58.4h |
| Bull #2 | 1.16 | 42.33 (48.8%) | 4.15 | 0:42.3h; 1:10.7h; 2:11.4h; 3:22.3h |
| Bull #3 | 0.79 | 18.43 (53.7%) | 2.80 | 0:18.4h; 1:9.7h; 2:1.0h; 3:5.2h |
| Bull #4 | 2.96 | 32.66 (24.2%) | 13.69 | 0:32.7h; 1:24.9h; 2:13.2h; 3:6.2h; 4:5.1h; 5:7.7h; 6:45.1h |


Medie integrate sui tempi di apertura/chiusura delle posizioni, intervalli tagliati agli estremi run; non derivano da uno screenshot. Distribuzione completa in JSON. Slot Bull cambiano3→10→6: non confronto la saturazione usando un unico tetto finale. Le ore vuote possono includere pausa, orari, daily-stop, cooldown, dati mancanti o assenza di setup: manca una timeline completa di questi stati per attribuirle a un solo gate.

### Fee, funding e netto

| Run | Netto | Fee totali | Funding | Netto + sole fee | Fee / abs(netto) |
| --- | --- | --- | --- | --- | --- |
| Hawk #2 | 1090.61 | 203.03 | 0.09 | 1293.65 | 18.6% |
| Hawk #3 | -284.87 | 105.39 | 0.28 | -179.48 | 37.0% |
| Hawk #4 | -335.60 | 43.45 | 0.31 | -292.15 | 12.9% |
| Hawk #5 | -50.81 | 276.98 | 0.11 | 226.17 | 545.1% |
| Bull #1 | 770.75 | 80.17 | 0.00 | 850.91 | 10.4% |
| Bull #2 | -144.68 | 67.08 | 0.22 | -77.60 | 46.4% |
| Bull #3 | -312.41 | 17.56 | 0.02 | -294.85 | 5.6% |
| Bull #4 | -214.02 | 330.25 | 0.73 | 116.23 | 154.3% |


Hawk #5:+226,17 prima delle fee riportate→−50,81 dopo; Bull #4:+116,23→−214,02. È identità contabile sul percorso eseguito, non backtest senza costi. Il rapporto fee/abs(netto) può superare100% e non è una quota causale della perdita. Configurazione registrata invariata:6bp per lato fee,2bp slippage per lato,1bp funding8h LONG. Lo slippage è nei fill, non separabile esattamente dai prezzi di riferimento conservati. Le fee assolute dipendono da notional, durata/turnover e parziali; non c’è evidenza di un aumento tariffa dopo le golden.

### Run attive, escluse dalle inferenze concluse

| Run | Inizio UTC | Posizioni complete / realizzi | Realizzato PAPER | Ancora aperte | Codice |
| --- | --- | --- | --- | --- | --- |
| Hawk #6 | 2026-10-26T18:55:45.815Z | 15 / 15 | -232.44 | 3 | 35f08cf → 89b0dca |
| Bull #5 | 2026-10-26T18:55:46.738Z | 6 / 8 | -113.31 | 3 | 35f08cf → 89b0dca |


Snapshot, non risultati finali: floating/equity non stimati. Posizioni ancora aperte sono censurate a destra; non calcolo per esse durata/esito definitivo e non le mescolo con le357 posizioni complete delle run archiviate.

## 3. Ipotesi nulla: mercato e variabilità campionaria

Acquisite candele **pubbliche Bitget USDT futures 1H**, complete e ordinate:10 simboli × 3 finestre,120/120/144 ore, nessuna risposta fallita; giorno 16 sovrapposto identico. Snapshot riproducibile in [market_hourly.csv ](market_hourly.csv). Finestre calendariali UTC12–16inclusi,16–20inclusi (aggiunta per le prime run negative),21–26inclusi. Rendimenti first-open→last-close; volatilità=deviazione standard dei log-rendimenti orari×√24, non annualizzata; efficienza=abs(somma logreturn)/sommaabs(logreturn).

| Simbolo | 12–16 rendimento / vol giorn. | 16–20 rendimento / vol giorn. | 21–26 rendimento / vol giorn. |
| --- | --- | --- | --- |
| BTC | -2.58% / 2.02% | 0.95% / 1.40% | -3.45% / 1.44% |
| ETH | -4.45% / 2.83% | 0.28% / 2.37% | -5.08% / 2.07% |
| ADA | -10.55% / 4.23% | -2.65% / 3.21% | -7.69% / 2.91% |
| DOGE | -6.73% / 3.40% | 0.88% / 2.89% | -5.02% / 2.30% |
| SOL | -6.18% / 3.60% | 1.04% / 2.74% | -5.22% / 2.11% |
| BNB | -4.31% / 2.03% | 1.65% / 1.44% | 0.18% / 1.55% |
| XRP | -6.98% / 3.19% | 0.06% / 2.50% | -2.01% / 2.23% |
| DOT | -5.66% / 5.43% | 0.09% / 5.26% | -12.17% / 4.07% |
| XAU | -0.61% / 1.00% | -0.98% / 0.75% | -2.62% / 1.05% |
| XAG | -6.31% / 1.95% | 1.22% / 1.46% | -6.74% / 1.89% |


Inclusi i sette simboli più tradati nelle posizioni complete (ETH 44, BTC 35, ADA 26, DOGE 24, SOL 23, BNB 20, XRP 18), oltre a DOT e ai metalli XAU/XAG. Finestre 21–26 ancora ribassiste: BTC−3,45%, ETH−5,08%, ADA−7,69%, DOT−12,17%. Non regge una spiegazione generale “non scendeva più il mercato”. La volatilità oraria è però inferiore per le crypto: con fee costanti il rapporto movimento/costo può peggiorare; non basta il rendimento aggregato per dedurre raggiungimento TP/SL.

Le finestre calendariali non coincidono con le run: le golden iniziano il 12 pomeriggio e finiscono il 16 alle 02:50. Ritagliando le sole ore integralmente comprese nella run, senza inventare la candela parziale iniziale/finale:

| Run | Ore complete | BTC rendimento | Vol giornaliera | Efficienza |
| --- | --- | --- | --- | --- |
| Hawk #2 | 83 | -0.59% | 2.18% | 0.0235 |
| Hawk #3 | 86 | -0.06% | 1.29% | 0.0038 |
| Hawk #4 | 60 | 1.09% | 1.67% | 0.0814 |
| Hawk #5 | 107 | -2.63% | 1.40% | 0.1172 |
| Bull #1 | 83 | -0.59% | 2.18% | 0.0235 |
| Bull #2 | 86 | -0.06% | 1.29% | 0.0038 |
| Bull #3 | 33 | 1.06% | 1.69% | 0.1531 |
| Bull #4 | 134 | -2.91% | 1.47% | 0.1001 |


Nel primo passaggio golden→Hawk #3/Bull #2 BTC passa da−0,59% a−0,06%, con vol 2,18→1,29% e minore direzionalità; in Hawk #4/Bull #3 rimbalza~+1,1%. Questo è compatibile con peggioramento di una popolazione quasi tutta SHORT. È un’associazione, non una quota di perdita spiegata. Le finestre tardive tornano in discesa e restano negative: mercato e campione di trade/codice devono essere valutati insieme. Nei soli ingressi osservati la mediana BTC roc24h passa−1,55→−0,66% Hawk #2→3 e−1,14→−0,53% Bull #1→2: conferma locale del contesto, soggetta a selezione degli ingressi.

Bull #1 ha 12 vittorie/17 posizioni: Wilson95% **46,9–86,7%**. Il calcolo ingenuo 24/30=80% darebbe 62,7–90,5%, ma tratta tranche della stessa posizione come indipendenti. Anche 17 è un N ottimistico: posizioni contemporanee e correlate. Il campione golden è troppo piccolo per dichiarare un 80% persistente o una strategia stabile. Intervalli delle altre run:

| Run | Vittorie / posizioni | WR | Wilson95% |
| --- | --- | --- | --- |
| Hawk #2 | 46/76 | 60.5% | 49.3–70.8% |
| Hawk #3 | 10/38 | 26.3% | 15.0–42.0% |
| Hawk #4 | 3/18 | 16.7% | 5.8–39.2% |
| Hawk #5 | 42/112 | 37.5% | 29.1–46.7% |
| Bull #1 | 12/17 | 70.6% | 46.9–86.7% |
| Bull #2 | 4/15 | 26.7% | 10.9–52.0% |
| Bull #3 | 0/4 | 0.0% | 0.0–49.0% |
| Bull #4 | 28/77 | 36.4% | 26.5–47.5% |


Non è possibile stimare “X%mercato/Y%codice” da questi dati osservazionali: codice, regime, uso Claude, selezione degli asset e disponibilità del capitale cambiano insieme; mancano identici input/cicli riprodotti sotto entrambe le versioni. Nessun p-value di queste differenze viene presentato come prova causale, né un backtest sintetico come evidenza reale.

## 4. Differenza → evidenza → confidenza

Confidenza riguarda l’affermazione esatta nella riga, non il successo futuro di un parametro.

| Differenza o ipotesi | Evidenza nei dati / codice / deploy | Confidenza |
| --- | --- | --- |
| Fix A causa Hawk #3/#4 | Esiti del 19/22 ottobre precedono il runtime Fix A del 23. Escluso temporalmente. | Alta: esclusione |
| SL 1,5→1,2 dopo le run positive | Modifica dell’11 ottobre; coefficiente 1,2 identico nelle golden e nelle negative. | Alta: ipotesi cronologica smentita |
| Scoring indebolito prima del primo crollo | Hawk #3 C mediana 74 contro 71 di Hawk #2; 4h +20 presente in tutti gli ingressi loggati di entrambe. | Alta sugli ingressi, non su tutte le opportunità |
| Soglia 63 causa il primo crollo | Hawk #3 e tutti i trade di Bull #3 sono ancora con C70; C63 è deployato il 21 ottobre. | Alta: esclusione per quei trade |
| I trade 63–69 causano il rosso tardivo | Sottogruppi C<70 con netto positivo in Hawk #5 e Bull #4; non è una simulazione della strategia a 70. | Alta descrittiva; bassa causale |
| Trend 1d perso per il warmup 200 | Contributo 1d assente anche nelle golden, presente nelle run tarde. | Alta sugli ingressi loggati |
| Disponibilità Claude cambiata | Hawk golden 1/47 risposte parsabili, prima negativa 56/56; ingressi sempre rules, fonte uscita non persistita. | Alta sui conteggi; bassa sull’effetto P&L |
| Rumore ed early stop | Alcuni SL precoci tardivi, ma barra d’ingresso/cursore/motore cambiano; coefficiente SL invariato e ATR diverso. | Media descrittiva; bassa causale |
| Due liquidazioni pesanti | NEAR −101,50 in Hawk #4; INJ −194,88 in Bull #3, entrambi b470. Il motore controlla LIQ prima di SL, ma manca il percorso intrabar. | Alta su importi e codice; bassa sulla loro evitabilità |
| Fee ribaltano il netto tardivo | Hawk #5: −50,81+276,98=+226,17; Bull #4: −214,02+330,25=+116,23. Tariffa salvata invariata. | Alta contabile; non prova causa unica |
| Mercato meno favorevole nelle prime negative | BTC quasi piatto o in rimbalzo, volatilità inferiore, esposizione quasi tutta SHORT; nelle tarde BTC scende di nuovo ma i risultati restano negativi. | Alta sulle metriche; media sulla compatibilità, bassa sulla quota causale |
| Bull golden dimostra un 80% stabile | 30 realizzi sono 17 posizioni; WR 70,6%, Wilson 46,9–86,7%, con dipendenza tra asset. | Alta sul conteggio; bassa generalizzabilità |
| Capitale, slot e leva modificati | Deploy del 21/24 ottobre, configurazioni e leve/margini effettivi variabili; nessun confronto controllato. | Alta sull’esistenza; bassa sulla quota di P&L |
| Regime BTC del 27 causa perdite 21–26 | Runtime 89b0dca successivo alle run complete. | Alta: esclusione |
| Guardian nuovo attivo il 26 | Moduli aggiunti senza hook nel CLI/engine classico; presenza del file non prova esecuzione. | Alta sul confronto sorgente; effetto non provato |

## 5. Cosa manca per separare davvero le cause

1. **Fonte dell’azione.** Un evento immutabile per ogni ciclo con ID, fonte effettiva di ciascuna azione (close, partial, DCA, hold inclusi), versione del deploy e digest di policy/prompt/configurazione. La fonte ereditata dall’ingresso non identifica l’autore dell’uscita. Il testo privato del modello non serve nel report pubblico.
2. **Input osservati allora.** Serie 15m con candela in formazione, timestamp della lettura, quantità e validità delle barre 4h/1d, prezzo usato e spread. Le candele definitive scaricate oggi non ricostruiscono una candela 15m parziale vista dal bot.
3. **Storia dei livelli.** Vecchio/nuovo SL e TP, autore, causa e tempo di efficacia; eventi split, DCA e cursore delle barre. Servono per separare stop iniziale, trailing/protezione e possibili riesami di barre vecchie. MAE/MFE aggregati non bastano.
4. **Percorso intrabar.** Tick o almeno barre 1m per distinguere la sequenza SL/TP/LIQ e i primi minuti dopo l’ingresso. Una OHLC 15m non dice quale livello sia stato toccato prima o dopo l’apertura.
5. **Timeline operativa.** Pause, orari, finestre Claude, budget disponibile, halt e capitale di inizio giornata, stati Capital V1 READY/rollover/stop latch, flag/env e limiti effettivi. Il manifest del codice non sostituisce questi stati.
6. **Universo completo per ciclo.** Tutti gli score LONG/SHORT, componenti, dati mancanti, soglie applicate e prima causa di esclusione. I conteggi candidate esistenti riguardano proposte già selezionate e soggette a limitazione di frequenza; non costituiscono il denominatore completo delle opportunità.
7. **Dettaglio dei costi.** Notional e ledger per ordine, commissioni, slippage separato e prezzo prima del fill. Fee e funding realizzati sono disponibili, ma manca il percorso completo per un confronto senza attrito.
8. **Controfattuale.** Per quantificare codice rispetto al mercato servirebbe un replay fedele agli input e ai tempi effettivi, oppure una raccolta controllata PAPER. Nessuno dei due è stato eseguito in questo audit; non propongo patch.

## Modifiche al prompt di analisi originale

Ho corretto i confini delle run dagli archivi (Hawk #4 termina il 22 ottobre mattina), distinto le posizioni dai realizzi parziali, separato la fonte dell’ingresso da quella dell’uscita e usato le prove runtime anche quando il workflow risultava fallito. Ho aggiunto il 16–20 ottobre per coprire le prime perdite, ritagliato le ore effettive delle run e isolato quelle ancora aperte.

Queste correzioni evitano di trattare le tranche come osservazioni indipendenti, attribuire un’intera run ai parametri del suo snapshot finale o dedurre cause dai soli P&L. Nessuna modifica al prompt di Claude o al trading.

## Allegati e verificabilità

- [positions.csv](positions.csv): 357 posizioni complete, con dati numerici e provenienza; [realizations.csv](realizations.csv): 427 realizzi, comprese le run attive.
- [run_metrics.json](run_metrics.json) e [active_runs.json](active_runs.json): metriche complete e campioni attivi separati.
- [deployments.csv](deployments.csv), [version_events.csv](version_events.csv), [code_changes.json](code_changes.json): deploy effettivi, eventi di versione e inventario dei confronti del codice.
- [market_context.csv](market_context.csv), [market_by_run.csv](market_by_run.csv), [market_hourly.csv](market_hourly.csv): contesto pubblico e barre utilizzate.
- [claude_calls.csv](claude_calls.csv), [candidate_counts.csv](candidate_counts.csv): conteggi senza prompt, risposte o spesa API.
- [source_provenance.json](source_provenance.json), [checks.json](checks.json): impronte delle fonti, stabilità durante la lettura, riconciliazioni e prove Actions.

Nessun file di memoria originale, credenziale, importo di trading reale o estratto LIVE è incluso. Nessuna raccomandazione di patch.
