# REPORT TECNICO COMPLETO — CLASSICI HAWK & BULL
### Analisi delle run, regressione, controlli di rischio, fallimento del replay e richiesta di seconda opinione a Claude

**Destinatario:** Claude, progetto SuperBot-Trading. **Redatto da:** ChatGPT, 29 ottobre 2026. **Stato:** ricostruzione da repository GitHub, audit PAPER già archiviati e screenshot utente. Nessun accesso diretto alla VPS in questa relazione, salvo riferimenti ad audit precedenti verificabili. Tutti i valori monetari sono USDT/USD PAPER simulati: non saldi exchange reali.

## 0. Messaggio per Claude — cosa chiediamo

Ti chiediamo una **revisione tecnica indipendente**, anche critica rispetto alle conclusioni di ChatGPT. Le performance di Hawk e Bull classici sono peggiorate nettamente dalle prime run positive; il 29/10 entrambi sono stati messi **in Pausa dall'utente** dopo perdite cumulative >30% per account. L'utente vuole recuperare un metodo redditizio e testabile, non necessariamente ripristinare il 12 ottobre alla cieca. Proponi soluzioni alternative, indicando **evidenza, ipotesi, severità, rischi, prove e criterio di approvazione**. In particolare, verifica che l'attuale protezione stop giornaliero e i sistemi di chiusura siano adatti a impedire perdite incontrollate in PAPER.

**Perimetro di autorizzazione:** soltanto analisi, letture e proposte; NO modifiche ai classici in esecuzione, NO riavvio, NO chiusure forzate, NO reset, NO merge/deploy, NO modifiche di limiti, prompt o Brain, NO passaggio LIVE. Nessuna scrittura al VPS. Qualsiasi proposta operativa deve avere un assenso esplicito separato e backup+restore verificati. La posizione BTC SHORT ancora aperta su Bull all'ultima fotografia deve essere lasciata alla gestione protettiva della pausa.

## 1. Contesto, ambiente e fotografia più recente

- Repository pubblico: `alexiptv82/SuperBot-Trading`. Ramo operativo classici: `rule-pool`. Diario condiviso: `diario`. Nuovo laboratorio isolato: `work/classics-12oct-selective-lab-20261029`. VPS Singapore, Hawk e Bull PAPER separati. Brain Scalp è un progetto distinto sotto revisione Claude: NON sovrapporre modifiche.
- **Screenshot 29/10 ore 08:07, Italia**: entrambi mostrano `PAPER MODE` e runtime `vdc16e01`. Hawk #7: equity 698,86; variazione -301,14 (-30,11%) da 1.000; P&L **oggi** -145,89; cassa 698,86; margin 0; 8 trade chiusi; 0/10 aperte; Salvadanaio 0; stato **IN PAUSA**.
- Bull #6: equity 673,48; variazione -326,52 (-32,65%) da 1.000; P&L **oggi** -205,67; cassa 522,49; margine 150; floating +0,99; 7 trade chiusi; 1/3 aperte; Salvadanaio 0; stato **PAUSA IN CORSO**.
- Posizione Bull residua al 29/10 08:01: BTC SHORT 15x, margine 150, entrata 79.943,31, SL 80.563,81, TP 78.871,05, valore liquidazione 84.873,15; floating momentaneo +0,21 all'08:01 e +0,99 alle 08:07. Aperta approssimativamente 03:19 italiane (durata 4h42 alle 08:01), quindi **dopo** il rollover UTC delle 01:00 italiane.
- Sommando le due equity visibili: 1.372,34 contro 2.000 base, ossia **-627,66 PAPER (-31,38%)**. Non sappiamo se i valori siano cambiati dopo lo screenshot. Dati non finali: Bull ha una posizione ancora aperta.
- Alle 08:00 entrambi erano marcati `Nuovi trade bloccati: stop giornaliero raggiunto`, con motori in funzione, non arrestati. Il conteggio trade tra 28/10 ore 21:56 e 29/10 ore 08:07 passa Hawk 6→8 e Bull 4→7: si sono verificate nuove chiusure. Lo SHORT BTC Bull è nuovo dopo mezzanotte UTC; probabile, ma da provare con trade log, che la protezione si sia riarmata con il nuovo giorno e poi abbia bloccato di nuovo.
- Il budget AI visibile 0,000/0,70 non prova assenza di chiamate DeepSeek o assenza di decisioni AI: il contatore potrebbe riferirsi a un canale differente.

**Riscontri:** `diario/2026-10-29_classici-pausa-equity-0807.md`; `diario/2026-10-29_classici-screenshot-0800-halt.md`. Queste sono osservazioni da screenshot, non un'ispezione live dei file di stato.

## 2. Cronologia prestazioni: dalla golden alla prima crisi

**Unità corretta:** una *posizione completa* comprende tutti i realizzi parziali; la dashboard talvolta conta le singole realizzazioni. Non scambiare il WR degli eventi di close per win rate di posizioni indipendenti. Lo storico 27/10 riconcilia 357 posizioni complete delle run concluse e 404 realizzi.

| Bot / run | Intervallo indicativo | Posizioni complete | Netto PAPER | WR per posizione | Profit factor netto |
|---|---|---:|---:|---:|---:|
| Hawk #2 GOLDEN | 12–16/10 | 76 | **+1.090,61** | 60,5% (46/76) | 2,12 |
| Hawk #3 prima crisi | 16–19/10 | 38 | **-284,87** | 26,3% | 0,54 |
| Hawk #4 | 19–22/10 | 18 | **-335,60** | 16,7% | 0,23 |
| Hawk #5 | 22–26/10 | 112 | **-50,81** | 37,5% | 0,97 |
| Bull #1 GOLDEN | 12–16/10 | 17 | **+770,75** | 70,6% (12/17) | 5,21 |
| Bull #2 prima crisi | 16–19/10 | 15 | **-144,68** | 26,7% | 0,52 |
| Bull #3 | 19–21/10 | 4 | **-312,41** | 0% | 0 |
| Bull #4 | 21–26/10 | 77 | **-214,02** | 36,4% | 0,89 |

Dashboard Bull #1 mostrava 24/30 = 80% su **realizzi**, non 24/30 ingressi completi; le posizioni complete sono 12/17 = 70,6% positive. Prima golden: Hawk 74/76 SHORT, Bull 17/17 SHORT. Le run successive rimangono prevalentemente SHORT, con P&L in deterioramento. Molte posizioni e simboli sono correlati, quindi campione statisticamente meno indipendente del conteggio apparente.

**29/10 ulteriori perdite:** Hawk #7 e Bull #6 in corso già -30,11%/-32,65% rispetto al nuovo conto 1.000. Queste NON si sommano indiscriminatamente alle run archiviate: sono run differenti con reset PAPER e non risultati cumulativi di un solo conto continuo.

## 3. Problema di diagnosi causale: nessuna singola modifica spiega il primo crollo

La prima coppia negativa inizia il **16/10**, prima di Fix A (23/10), Capital V1 (24/10), riduzione scoring P1, correzione fallback P2 e modifiche successive. Il file `backend/desk/signals.py` ha lo **stesso oggetto Git identico** nelle revisioni `a0afc63`, `7ced3a6`, `5818aee`, `18d145f`, `b4709d1`. Provenienza certificata da GitHub Actions **40815650805**.

Le GOLDEN non giravano su un solo commit. Sequenza runtime Hawk #2: `a0afc63 → 7ced3a6 → 5a4e383 → 9fa667f → 5818aee` (Bull simile, con un'apertura iniziale di versione incerta). Il 12 ottobre ha introdotto anche split reale delle posizioni, poi audit AI, calendario Claude e in seguito macro gate. La SHA mostrata a fine run non identifica il codice che ha eseguito ogni singola operazione. `9fa667f` è anche un trigger deploy; non necessariamente differenza nel modulo scoring.

**Ipotesi fattoriali da tenere distinte**: (a) regime/cambiamento di direzionalità e volatilità; (b) disponibilità Claude, sue decisioni o veto, che possono modificare candidati e uscite; (c) esecuzione/ritmo dei cicli, gestione split/DCA, stop/TP e feed OHLC; (d) input a15m, 4h e 1d e score che cambia composizione nelle run successive; (e) rischio aggregato di posizioni correlate; (f) commissioni rispetto all'edge reale. Non affermare causalità senza replay controfattuale fedele.

Un vecchio SL `1,2×ATR` **esisteva già dall'11/10**, prima dei profitti golden. Quindi non correggere una presunta restrizione SL 1,5→1,2 successiva alle golden: sarebbe una falsa diagnosi.

## 4. Evidenze sui segnali, sul mercato e sui costi

### 4.1 Il punteggio simile nasconde setup diversi

- Hawk score medio ingresso 70,57 golden → 69,29 tarda (#5); Bull 70,00 golden → 68,82 tarda (#4). Ma Hawk breakout 54/74 → 20/112, volume significativo 53/74 → 29/112, contributo trend daily 0/74 → 39/112. Bull breakout 9/15 → 11/77, volume 8/15 → 14/77, daily 0/15 → 29/77.
- Stesso score >=75: WR Hawk 83,3% golden → 32% tardi, Bull 100% su soli 3 ingressi → 29,4%. Score non calibrato come probabilità. Non ripristinare ciecamente la soglia 70 o forzare breakout/volume: nelle run negative anche breakout+volume ha performance molto scadenti.
- Mix delle altcoin C aumenta, ma il rendimento peggiora anche **all'interno degli stessi tier/simboli**. La prima crisi aveva ancora C=70; le modifiche 70→63 sono successive. 1d diventa disponibile in run successive con 4h native/serie più lunghe, cosa che cambia l'origine dello stesso score numerico.

### 4.2 Mercato cambiato ma non è spiegazione completa

- Finestre corrispondenti alle run: BTC golden 83 ore circa -0,59% e volatilità giornaliera 2,18%; prima crisi circa -0,06% e volatilità 1,29%. Quasi tutti SHORT: un contesto più laterale, meno volatile e con rimbalzi può danneggiare quell'edge. **Correlazione, non causalità dimostrata.**
- 21–26/10 torna mercato ribassista (BTC circa -3,45% e ETH -5,08% sulle finestre calendariali), ma i bot continuano a perdere: il solo trend bearish non rende la strategia valida.
- Nelle golden alcune vincite enormi di pochi asset pesano molto (es. singola UNI Bull +202,80 netti). Quattro giorni e 17 posizioni Bull non bastano per dichiarare un vantaggio stabile.

### 4.3 Lordo prima dei costi crollato

| Indicatore | Hawk #2 | Hawk #5 | Bull #1 | Bull #4 |
|---|---:|---:|---:|---:|
| Lordo medio per posizione | +17,02 | +2,02 | +50,05 | +1,52 |
| Fee media per posizione | 2,67 | 2,47 | 4,72 | 4,29 |
| Netto medio per posizione | +14,35 | -0,45 | +45,34 | -2,78 |
| Posizioni/giorno | 21,72 | 24,72 | 4,86 | 13,69 |

Fee roundtrip ~12 bp nozionale, quasi invariata. Il problema principale non è una commissione improvvisamente aumentata, ma la riduzione del movimento favorevole netto. In Hawk #3 e Bull #2 il **lordo totale era già negativo prima delle fee** (rispettivamente circa -179,20 e -77,38), quindi il deterioramento era reale prima dei costi. Bull moltiplica per 2,82 le posizioni/giorno fra golden e #4 senza recuperare l'edge. Aumentare leve o margini amplificherebbe le oscillazioni e il rischio, non crea valore atteso.

### 4.4 Chiudono diversamente, ma la colpa di Claude NON è provata

Audit sulle prime golden Hawk #2 + Bull #1: 93 posizioni +1.861,3621 nette; cause finali **54 TP** (+2.742,5785), **34 SL** (-911,3879), **4 model-or-rule labeled Claude** (-39,2171), 1 manuale (+69,3886). Prima crisi Hawk #3 + Bull #2: 53 posizioni -429,5490; **14 TP** (+486,2971), **20 SL** (-660,2772), **16 chiusure modello-o-regole** (-225,4920), 3 manuali (-30,0769).

Le chiusure ambiguamente etichettate passano **4/93 (~4,3%) → 16/53 (~30,2%)**. È un grande cambiamento descrittivo, non prova che Claude abbia chiuso volontariamente le 16 posizioni. Label ambigua significa agente chiusura **UNKNOWN** fino a verifica dei log della decisione. **93/93 versioni di uscita `exit_code` mancanti** nelle golden; 4/93 aperture senza eventi/metadati completi.

Tutte le **146 aperture** dei due gruppi sono `source=rules` nel registro; questo non identifica chi ha deciso una chiusura, né quanti candidati siano stati scartati da Claude. Tra Hawk #2 e #3 cambia la disponibilità di risposte Claude parsabili (storico audit 1/47 vs 56/56), fattore da controllare, non verdetto causale. Le variazioni di frequenza delle chiusure possono essere effetto del regime o della gestione, non di una API.

CI forense **40824613230, 3/3 test PASS** su 357 posizioni archiviate (sottoinsieme studiato 146), SHA256 input `0d1252e15d5d07c7dc7fa61789648e0a45d9383e7efc783852439ceaf95ff281`. Modulo riproducibile `backend/rollback_lab/tape_audit.py` del ramo di laboratorio.

### 4.5 Liquidazioni e ambiguità intrabar

Due casi rilevanti già prima Fix A: Hawk #4 NEAR SHORT -101,50 PAPER e Bull #3 INJ LONG -194,88. Nel motore OHLC una barra che attraversa sia liquidazione sia stop è valutata con una precedenza deterministica, non con percorso tick ricostruito. Verificare se il modello dà priorità alla liquidazione rispetto allo SL, se la gestione stop aggiorna livelli prima/dopo la barra e se ciò sovrastima la perdita. Sono due casi importanti per la diagnosi, ma non certificati come bug senza dati intrabar autentici. Il trattamento contabile `LIQ` ha eccezioni note nel confronto gross/fee/net.

## 5. PROTEZIONE GIORNALIERA: punto di massima priorità operativa

**Codice attuale di `backend/desk/engine.py` su `rule-pool`:** `PaperAccount.roll_day(day, prices)` pone `day_start_equity = equity(prices)` al cambio giorno; `PaperAccount.halted(prices)` blocca nuove aperture se equity <=450 USD, oppure equity <=0,88 × `day_start_equity` (12% legacy). **Nel percorso legacy la condizione è ricalcolata**, non è evidente un flag `halt_latched` persistente fino al giorno seguente. Se la floating equity recupera sopra soglia nello stesso UTC day, il blocco potrebbe cessare e riabilitare nuove entrate: verificare il flusso completo del ciclo e i log, non attribuire automaticamente quel comportamento alle perdite del 29.

Il daily stop **non forza la chiusura delle posizioni preesistenti**; il P&L di giornata può quindi superare il 12% anche se il gate ha funzionato per nuove aperture. Esempio screenshot 29/10: Hawk -145,89 oggi, Bull -205,67 oggi; Bull ha tuttora 1 SHORT BTC aperto in pausa. Potrebbero essersi prodotte perdite importanti su posizioni aperte prima del trigger; serve il timestamp di ogni nuova apertura e ogni chiusura, oltre a riferimento di equity di mezzanotte e prezzi del rollover.

**Domande puntuali per Claude:** (i) lo stop legacy consente reinserimenti intra-day dopo rimbalzo? (ii) gli ingressi sono bloccati sempre anche durante tutte le condizioni di split/DCA e nuove gambe? (iii) l'equity base include correttamente floating, vault, fee e funding? (iv) i dati possono essere stale / mancanti al rollover e falsare il riferimento? (v) un gate giornaliero *latched* fino alla mezzanotte avrebbe evitato riaperture documentabili? (vi) va introdotto in futuro un limite di **rischio aggregato agli stop, correlazioni e perdita per singola posizione** distinto dal daily stop senza liquidare automaticamente posizioni? Rispondere con diff concettuale, test riproducibile e rischio migrazione, NON modificare codice.

**Attenzione:** alcuni audit anteriori mostrano configurazioni 10% o Capital V1 20% in finestre distinte; non confondere tali profili con l'attuale 12% legacy indicato dagli screenshot e dal `rule-pool` corrente. Il diario e gli artefatti distinguono i periodi ON/OFF.

## 6. Perché il rollback integrale al 12 ottobre NON è sicuro

- Prima crisi già dal 16/10, con stesso `signals.py` e SL1,2×ATR delle golden. Un rollback di scoring da solo non corregge automaticamente il problema.
- Le golden attraversano **più versioni** (split, calendario Claude, macro), non una singola SHA vittoriosa. Alcuni SHA sono solo trigger deploy.
- Vecchio loader e schema dello stato conto non sono retrocompatibili garantiti; il vecchio reset poteva ripartire permissivamente da `{}` per JSON non valido, mentre versioni moderne fanno verifiche più severe. Non usare vecchio bot sulle directory attuali né vecchio workflow di deploy.
- Proteggere dati: `state_v2.json`, `trade_history.jsonl`, `learning_log.jsonl`, `lessons.md`, `errors.md` se esistente, `salvadanaio-journal.jsonl`, outbox, cronologia run, database Brain. Richiesto backup consistente + restore provato, un solo writer per portafoglio.
- Reset PAPER solo dopo apposita approvazione e quando flat/in pausa, con archivio della run e verifica Salvadanaio. **Non azzerare oggi solo per sbloccare lo stop**: si nasconderebbe il deterioramento osservato.

## 7. Esperimenti offline eseguiti, e perché non bastano

Il laboratorio isolato `work/classics-12oct-selective-lab-20261029` ha eseguito confronto scorer storico/moderno × engine di uscita storico/moderno, simulando sui **medesimi prezzi pubblici Bitget** (15m/4h/1d, conto 1.000 PAPER, 30 min tra scansioni, senza AI, DCA/split e intero flusso di produzione). Test CI sintesi PASS e reali PASS.

**7 mercati, 12–29/10:** `40821658014` PASS. Simulazione scorer vecchio: Hawk 115 posizioni net -443,70; Bull 69 -585,40. Simulazione scorer moderno: Hawk 14 -10,00; Bull 14 -20,40. Le uscite old/new hanno coinciso solo nel modello semplificato su questo campione.

**26 mercati, 12–29/10:** `40822151627` PASS, checksum identico dati Hawk/Bull `1e9b32793bb965513c53a4098456542b4d2ec94243286a032d25410fd1629dff`. Old scorer: Hawk 22 chiuse -550,10; Bull 7 -585,70 (blocca quasi ogni ingresso successivo dopo forti perdite simulate). Modern scorer: Hawk 70 -273,70; Bull 56 -3,80. Le differenze di rischio e di composizione restano grandi; nessuna variante è un candidato deploy dimostrato.

**FALLIMENTO DEL GATE DI FEDELTÀ:** le vere golden PAPERS erano Hawk 76 posizioni +1.090,61 e Bull 17 +770,75, quasi tutte SHORT. La simulazione non ricrea queste posizioni, le direzioni e il P&L: nel solo periodo golden, con modello 26 mercati, vecchio scanner Hawk 22 circa -550 e Bull 7 circa -585; con moderno Hawk +167 e Bull +197 su quantità differenti. Anche a sette asset si nota disallineamento forte tra entrate reali e simulate. Quindi **non usare i risultati del laboratorio per concludere che il vecchio motore è peggiore o che quello moderno è migliore**. Il test verifica dati identici e plumbing tecnico, non la verità controfattuale.

Una parte del backtest precedentemente esistente sul repository aveva C=63 invece di C=70 e capitale 100.000 invece di 1.000, oltre a scorer preP1: corretta la configurazione per il confronto isolato, ma la replica completa richiede ricostruire **ranking candidate, frequenza e orari reali, fonte AI e veto, fee/fill, SL/TP spostati, split/DCA, latenza, storico prezzi point-in-time, liquidazione e ordini di priorità intra-bar**. I replay da sole candele 1h o da dati futuri reintrodotti sono inadeguati.

## 8. Percorso di prova raccomandato — ordinato per valore diagnostico

**Fase A — inventario e congelamento prove (READ-ONLY):** snapshot di stato PAPER al 29/10 e copia consistente di trade_history/learning log e run, senza riavviare container. Verificare esistenza di tutti i log, qualità dei timestamp, orari mezzanotte UTC, equity/day_start_equity e conti chiusi. Non leggere segreti. Verificare che i file originali siano protetti e che ogni acquisizione restituisca fingerprint.

**Fase B — diagnosi prioritaria delle perdite 29/10 e daily stop:** ricostruire in UTC ogni apertura/uscita con equity precedente/successiva, leva/margine, simbolo/direzione, stop, causa di close, circuito di apertura e stato `halt`. Distinguere primo stop, eventuale sblocco intraday, rollover e trades ancora in essere. Fornire tabella causale per ogni perdita e prova di ciascun superamento.

**Fase C — attribuzione uscite golden/crisi:** trovare per i **20 close ambigui** (4 golden +16 crisi), e 4 manuali, rispettive risposte AI/regole/eventi in log/outbox ove presenti; marca chiaramente `UNKNOWN` per i casi non identificabili. Non imputare responsabilità a Claude dal solo nome dell'exit.

**Fase D — replay condizionato su aperture REALI:** con le entrate che sono realmente avvenute, alimentare a parità di prezzi e timestamp i soli gestori di uscita storici e moderni; misurare matching tempo di close, prezzo, tipo, parziali, P&L netto e drawdown. Per conflitto SL+TP nella stessa candela usare ipotesi conservativa e analisi di sensibilità, non una sequenza falsa. Questo isola exit da selection.

**Fase E — replay completo scanner:** soltanto dopo ricostruire i candidati di allora (15m chiuse, score, volume, BTC regime, ranking, macro, tempistica API Claude/DeepSeek, budget, fallback). Misurare matching `(simbolo,lato,finestra 15m)`, entry price, margin/lev, tempi, filtro per cui candidati furono scartati, nette dopo costi. Congelare golden e fare holdout 16–20 e 21–29 senza adattamenti sui risultati.

**Fase F — proporre modifiche MINIME e isolabili:** prediligere prima protezioni/rischio e monitoraggio, poi segnali/uscite migliorate solo dopo evidenza. Niente aumento generalizzato di leva, reset ripetuti o slot forzati; il valore atteso netto per setup e la correlazione contano più del numero di trade. Test dei diversi regimi bullish/bearish/range, daily-loss latch, restart cooldown e contaminazione tra Hawk/Bull.

## 9. Domande dirette: richiediamo una strategia ALTERNATIVA da Claude

1. **Causa più probabile del primo deterioramento 16–19 ottobre?** Separa effetto mercato, disponibilità AI, prompt, calendario, execution, uscita e dimensione del campione; assegna livello di confidenza e cosa falsificherebbe l'ipotesi.
2. **Perdita del 29/10:** il -205,67 di Bull entro 08:07 con stop12% è coerente con posizioni già aperte o risulta un bug? Quali log esatti e test leggere, solo in read-only?
3. **Stop legacy:** proporresti latch fino a 00:00 UTC, cap sul rischio aggregato di portafoglio e controllo alle aperture/split/DCA? Descrivi invarianti e test, non fare patch operativa.
4. **Sistema d'uscita:** che meccanismo ha causato l'aumento 4→16 close decisionali ambigui? Come provarlo senza usare la label Claude come verità? Rende opportuno separare profit-taking AI dai close protettivi?
5. **Un'altra via al rollback?** Per esempio shadow di strategia golden riprodotta su snapshot reali, classificatore regime da validare senza lookahead, filtro expected-value netto, orizzonte diversi per Hawk/Bull, disattivazione setup dimostrabilmente dannosi. Metti pro/contro e costo implementazione per ciascuna.
6. **Come superare gate di fedeltà?** Specifica set minimo di informazioni necessarie e tolerance test (entry, exit, contabilità, tempo, side, costo), distinguendo dati mancanti definitivamente da recuperabili.
7. **Se tu fossi il responsabile del progetto, cosa faresti come prossimo STEP 1, 2, 3?** Per ogni passo: file da leggere/modificare solo su branch isolato, test off-line, criterio di successo, rischi, eventuali prerequisiti e decisioni che deve prendere l'utente.
8. **Quali rischi non abbiamo identificato?** Cerca errori di staleness/UTC/timezone, duplicazione writer, correlazione comune ai bot, accounting vault, latenza, split/partial, fee/funding e ordini di chiusura all'interno della candela.

## 10. Fonti e artefatti — leggibili nel repository

- Audit forense completo: [REPORT.md](analisi-run-2026-10-27/REPORT.md); record trade: [positions.csv](analisi-run-2026-10-27/positions.csv); [run_metrics.json](analisi-run-2026-10-27/run_metrics.json); [source_provenance.json](analisi-run-2026-10-27/source_provenance.json).
- [Analisi delle aperture](analisi-run-2026-10-27/ENTRIES.md), [commissioni](analisi-run-2026-10-27/FEES.md), [mercato storico](analisi-run-2026-10-27/market_hourly.csv), [cronologia versioni](analisi-run-2026-10-27/deployments.csv), [cambi codice](analisi-run-2026-10-27/code_changes.json).
- [Foto 29 ottobre](2026-10-29_classici-pausa-equity-0807.md), [stato stop alle 08:00](2026-10-29_classici-screenshot-0800-halt.md), [proposta rollback selettivo](2026-10-29_proposta-rollback-pulito-12-ottobre.md).
- [Esiti A/B lab 29 ottobre](2026-10-29_chatgpt-classici-laboratorio-ab.md), [gate 146 trade](2026-10-29_classici-golden-tape-gate.md). Branch: `work/classics-12oct-selective-lab-20261029`.
- CI verificati: [provenienza segnali](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40815650805), [replay 7 mercati](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40821658014), [replay 26 mercati](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40822151627), [regressioni trade tape](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40824613230).
- Codice da verificare su `rule-pool`: `backend/desk/cli.py` (reset, rollover, gestione pausa, AI, ingressi), `backend/desk/engine.py` (`roll_day`, `halted`, `on_bar`, close/partial/split), `backend/desk/signals.py`, `backend/desk/brain.py`, `backend/desk/deepseek_classics.py` o moduli equivalenti nella versione effettiva.

## 11. Vincoli finali / come consegnare il parere

Claude, scrivi una valutazione indipendente e concreta, dividendo **fatti verificati, ipotesi, alternative, bug certo vs rischio e priorità**. Se trovi una contraddizione in questo rapporto, correggila con prova riproducibile e riferimenti a file/riga. Per ora **non modificare il ramo operativo, non resettare, non attivare deploy e non cambiare alcuna strategia**. Puoi proporre lavori offline su un tuo branch, ma coordinate con ChatGPT e senza duplicare i componenti in scrittura.

**Stato al momento dell'invio:** Hawk #7 in pausa e senza posizioni, Bull #6 in pausa in corso con uno SHORT BTC PAPER; nessuna garanzia che sia ancora aperta dopo le 08:07. Il reset a 1.000 $ per portafoglio è soltanto una possibilità dopo backup e chiusura naturale, NON un comando autorizzato. Brain Free e Brain Scalp totalmente indipendenti.

AI: chatgpt (chat normale)