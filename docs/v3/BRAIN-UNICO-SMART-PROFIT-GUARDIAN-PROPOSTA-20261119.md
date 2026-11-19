# Smart Profit Guardian: revisione indipendente e proposta (19/11/2026)

**Natura del documento:** analisi e specifica di laboratorio. Nessun parametro è approvato e nulla è stato eseguito su dati o servizi reali. Nessun merge, deploy, stop di runner o cambio di rischio in runtime.
**Fonti:** report "SuperBot Smart Profit Guardian" v1.0 (19/11), prompt dell'utente dello stesso giorno, Issue #113 (commento delle 12:32), roadmap `BRAIN-UNICO-ROADMAP-AGGIORNATA-20261119.md`, PR #118.
**Numeri:** tutti i numeri sotto vengono da `ops/brain-unico/guardian/sim_policies.py`, una simulazione **sintetica** (stdlib, nessun dato reale). Servono a mostrare proprietà matematiche, non a stimare i rendimenti di SuperBot.

---

## 0. Sintesi in cinque punti

1. **L'idea è giusta nel comportamento, ma non nella leva su cui agisce.** Un blocco al raggiungimento di +400/+500 non tocca le sessioni peggiori, perché quelle non arrivano mai a +400. Nella simulazione il 5° percentile di sessione resta identico (−429 USDT) con qualunque profit lock. La crescita del capitale dipende prima di tutto dal **lato delle perdite**: rischio per trade e perdita massima di sessione.
2. **Una regola di arresto non crea vantaggio.** Se i trade successivi hanno la stessa qualità dei precedenti, fermarsi dopo un guadagno riduce il profitto atteso: −3 % nello scenario S1 per la soglia fissa. Il Guardian aumenta il rendimento **solo se** i trade aperti dopo un guadagno sono statisticamente peggiori, come i "4° e 5° reingressi" che avete osservato. In quello scenario (S3) la soglia fissa migliora la media del +9 %. **Questa condizione si misura sui dati storici prima di costruire qualunque cosa.**
3. **Il problema che avete descritto è il reingresso, non la soglia.** L'anti-reingresso per `thesis_id` agisce direttamente sul meccanismo che erode i profitti. La soglia di sessione ne è solo un indicatore indiretto. Per valore atteso, l'anti-reingresso viene prima.
4. **La leva deve essere un risultato del calcolo, non una scelta.** Con i limiti attuali dell'Arena (perdita massima 85,71 USDT per posizione su 2.000) e 400 USDT di margine, a 50× lo stop deve stare entro lo 0,25 %. I costi stimati valgono allora il 42 % del rischio, e con target a 2× serve un win rate del **57,5 %** solo per andare in pari (contro il 34,8 % a 5×). La leva alta resta disponibile, ma vale la pena solo in rari casi di stop molto stretto e giustificato.
5. **Al posto delle soglie fisse 400/500 propongo un budget di rischio unico.** È un floor mobile sul picco di equity mark-to-market (tipo CPPI), che riduce *automaticamente* la size delle nuove aperture man mano che il margine sopra il floor si consuma. Va affiancato da un limite di perdita di sessione e da un drawdown globale dall'high-watermark. Gli stati NORMAL/SELECTIVE/PROTECTED/LOCKED diventano etichette *derivate* dal budget, non soglie da raggiungere. Le soglie 400/500 restano come braccio di confronto negli esperimenti.

---

## A. Critica professionale

### Cosa funziona
- **NO_TRADE è una decisione valida**, senza quote di trade né slot da riempire. È il cambiamento più importante rispetto a Toro/Falco e all'Arena.
- **Separare il PnL realizzato dall'equity mark-to-market** ed escludere le chiusure forzate al cambio di data è corretto.
- **Il veto deterministico prevale sull'LLM.**
- **`thesis_id` e il conteggio dei reingressi** colgono il difetto osservato.
- **Il report stesso dichiara** che 400/500 non sono un obiettivo e che il floor non è garantito.

### Cosa è ingenuo o pericoloso
| Punto | Problema | Conseguenza |
|---|---|---|
| Soglie in USDT fissi | Cambiano significato con l'equity: +500 vale il 25 % su 2.000, il 12,5 % su 4.000 ed è irraggiungibile vicino al floor di 450 | La politica smette di funzionare man mano che il conto cambia |
| +500 come stato da raggiungere | Se lo stato è visibile al decisore, diventa un'ancora ("mi mancano 80 USDT") | Si incentiva proprio la rincorsa che si vuole evitare |
| Giveback 20–25 % senza soglia di attivazione | Su un picco di +60 si fermerebbe dopo −15 USDT, cioè meno di un trade | Si blocca a ogni piccolo guadagno; serve una soglia di armamento |
| Si protegge solo il lato destro | Le sessioni peggiori non arrivano mai a +400 | Il drawdown non migliora: nella simulazione il p5 è invariato con tutti i profit lock |
| Limiti dell'Arena ereditati | 4,29 % per trade, blocco giornaliero al 50 %, equity minima 450 | Con circa 6 trade per sessione, il p5 sintetico vale −21 % in **una sola** sessione. Questo è il vero rischio per la crescita |
| Esempio del report: 400 margine a 50×, prezzo −0,5 % = −100 | −100 supera già il limite di 85,71 per posizione | Lo stesso esempio viola i limiti esistenti, che va detto esplicitamente |
| Eccezioni "con evidenza fuori campione" | Oggi non c'è nessun modello calibrato né dataset reale (PR #118 non ancora eseguita su dati reali) | Il gate dell'eccezione non avrebbe dati: diventerebbe di fatto una scelta discrezionale dell'LLM |

### Conflitto matematico tra leva, margine, stop e rischio
Rischio monetario fisso = 1R = 85,71 USDT. Margine 400 USDT. Costi ipotetici: 0,06 % di commissione taker e 0,03 % di slippage per lato, **da verificare** sulle tariffe effettive.

| Leva | Nozionale | Costi a/r | Costi/R | Stop massimo | Win rate di pareggio (TP a 2× stop) |
|---|---|---|---|---|---|
| 5× | 2.000 | 3,6 | 4,2 % | 4,11 % | 34,8 % |
| 10× | 4.000 | 7,2 | 8,4 % | 1,96 % | 36,4 % |
| 20× | 8.000 | 14,4 | 16,8 % | 0,89 % | 40,1 % |
| 35× | 14.000 | 25,2 | 29,4 % | 0,43 % | 47,2 % |
| 50× | 20.000 | 36,0 | 42,0 % | 0,25 % | 57,5 % |

**Lettura:** a rischio fisso, la leva non aumenta il guadagno per trade, che è dato da R e dal multiplo di R raggiunto. Aumenta soltanto il nozionale, quindi i costi, e restringe lo stop. Uno stop dello 0,25 % su un'alt con ATR a 15 minuti dello 0,5–1,5 % sta dentro il rumore. **Non si possono avere insieme 50×, 400 di margine, uno stop ragionevole e una perdita contenuta: uno dei quattro deve cedere.** La regola corretta, già scritta nel report e qui resa vincolante, è: invalidazione → stop → rischio monetario costi inclusi → nozionale → **leva minima** che rispetta i limiti di margine e una distanza di liquidazione di sicurezza.

---

## B. Architettura proposta (Brain Unico)

```
MarketData ─► FeatureBuilder (point-in-time, log schema v2)
                 │
                 ▼
          Guardian.precheck ──LOCKED──► NO_TRADE(reason=guardian_locked), nessuna chiamata LLM
                 │ budget>0
                 ▼
          DeepSeek: LONG/SHORT/NO_TRADE + tesi (invalidazione, target, orizzonte, confidenza)
          [senza PnL di sessione nel prompt]          ▲ Falco SHORT: feature + flag di conflitto
                 │
                 ▼
          ThesisRegistry: thesis_id, reentry_count, cooldown ──blocco──► NO_TRADE(reason=reentry)
                 │
                 ▼
          Scorer EV netto (shadow → poi vincolante; prima del modello: soglia R:R minima)
                 │
                 ▼
          RiskManager (deterministico, veto): size dal budget del Guardian, leva minima ammissibile,
          rischio aggregato per cluster di correlazione, stress di gap
                 │
                 ▼
          OrderManager (PAPER) ─► ExitService (indipendente; il Guardian non lo ferma né lo modifica)
                 │
                 ▼
          Journal (eventi): decision, guardian_state, guardian_block (con candidato completo),
                            thesis_open/close, sizing_breakdown ─► Dataset Builder (PR #118)
                 │
                 ▼
          Dashboard: stato, budget residuo in R, floor, picco, motivo dell'ultimo blocco
```

Interfacce essenziali, deterministiche e testabili:
- `Guardian.state(now) -> {state, budget_R, floor, peak, session_id, reasons[]}`, letto da equity MTM *stressata*, rischio a stop delle posizioni aperte e limiti globali.
- `ThesisRegistry.classify(candidate) -> {thesis_id, is_new, reentry_index, cooldown_until, reason}`.
- `RiskManager.size(candidate, budget_R) -> {approve|veto, qty, leverage, liq_distance, cost_R, reasons[]}`.

Integrazione con le AI:
- **DeepSeek decide** la direzione e la tesi, ma **non riceve il PnL di sessione**: niente effetto "soldi della casa" né ancoraggio al target.
- **In LOCKED non viene chiamato affatto**, il che fa anche risparmiare costi API.
- **Claude** resta a zero chiamate dal Brain (decisione in Issue #113). In futuro, se approvato, potrà fare una revisione offline giornaliera dei blocchi e delle eccezioni, con un tetto di costo.
- **Falco SHORT** è una feature con flag `SHORT_conflict`. Nello stato SELECTIVE un LONG contro un allarme Falco richiede un EV minimo più alto. Falco non apre mai posizioni.

---

## C. Tre politiche di profit lock

| Politica | Regola | Pro | Contro |
|---|---|---|---|
| **B. Soglia fissa** (report) | ≥ +400: metà del rischio; ≥ +500: stop alle nuove aperture | Semplice e comprensibile | Dipende dalla scala del conto; limita il lato destro; non protegge il p5 |
| **D. Floor mobile in R / % equity** (raccomandata come primo test) | Si arma quando il picco MTM netto è ≥ A (es. 4,67R ≈ +400 oggi, o +8 % dell'equity d'inizio sessione). Floor = inizio + (1−g)·(picco−inizio), solo crescente. Rischio di ogni nuova apertura (costi e stress inclusi) ≤ equity_MTM − floor − rischio_aperto_a_stop. Sotto 0,25R: LOCKED | Un solo meccanismo; il giveback massimo è rispettato *per costruzione* (salvo gap); la size si riduce gradualmente invece di passare da tutto a niente; scala con il conto | Due parametri (A, g); serve un'equity MTM affidabile |
| **V. Adattiva a volatilità/regime** | Come D, con g e A funzione dell'ATR di portafoglio o del regime | In teoria la più efficiente | Più parametri, rischio di overfitting; da tentare solo con molti dati |

**Raccomandazione: testare per prima la D** (con g = 25 % e A ≈ +400 come ipotesi), affiancata da un limite di perdita di sessione. La B resta come braccio di confronto, perché è il modello mentale dell'utente. La V va rimandata a quando il dataset avrà almeno 1.000 esempi e 45 giorni.

Risultati sintetici (40.000 sessioni, ~6 occasioni per sessione, R = 85,71, valori in USDT per sessione):

| Scenario | A baseline | B fissa | D2 floor 25 % (att. 400) | E solo stop −3R | F = D2 + stop −3R |
|---|---|---|---|---|---|
| S1 edge costante +0,10R: media | 49,9 | 48,4 | 49,3 | 42,1 | 39,8 |
| S2 edge nullo: media | −0,6 | −0,5 | −0,7 | −1,2 | −1,4 |
| S3 edge che decade dopo +4R: media | 39,6 | **43,2** | 41,6 | 32,0 | 32,3 |
| p5 di sessione (S1) | −428,6 | −428,6 | −428,6 | **−257,1** | **−257,1** |
| Sessioni chiuse sotto il 75 % del picco, se il picco ≥ 400 (S1) | 21,8 % | 5,2 % | **0,0 %** | 21,5 % | **0,0 %** |

Cosa insegna la simulazione:
1. **Nessuna regola di arresto aumenta la media se i trade sono indipendenti** (S1, S2). Le regole spostano soltanto la forma della distribuzione: è un costo in rendimento atteso pagato per ridurre la varianza.
2. **I lock guadagnano solo se esiste il decadimento** (S3). Va quindi misurato su dati reali.
3. **Il floor D2 garantisce il giveback** (0 % delle sessioni sotto il 75 % del picco, senza gap simulati) **quasi senza costo in S1** (−1 %). La soglia B invece taglia anche il lato destro e lascia comunque un 5 % di sessioni sotto il 75 % del picco.
4. **Solo il limite di perdita di sessione migliora il p5** (−40 %). Costa media se l'edge è costante, quindi va calibrato, ma è l'unico che protegge il capitale nelle giornate cattive.

Limiti della simulazione: esiti binari e indipendenti, nessun gap, nessuna correlazione tra posizioni contemporanee, costi fissi. **Non è una stima del comportamento reale.**

---

## D. Macchina a stati e priorità dei gate

Ogni candidato passa i gate in quest'ordine. Il primo che fallisce produce NO_TRADE con il suo motivo registrato.

1. **Integrità dati**: feed fresco, candela chiusa, nessun errore di riconciliazione → altrimenti LOCKED(data_fault).
2. **Limiti globali** (mai azzerati dal reset): equity minima; drawdown dall'high-watermark globale. Ipotesi: −10 % → rischio dimezzato; −20 % → nessuna nuova apertura fino a revisione umana.
3. **Limite di perdita di sessione**: ipotesi −3R di equity MTM dall'inizio sessione.
4. **Budget del floor** (politica D, se armato).
5. **Rischio aggregato**: somma del rischio a stop delle posizioni aperte, con stress di gap, più quello del candidato, entro il tetto di portafoglio. Per cluster correlati (stessa direzione, correlazione dei rendimenti orari a 7 giorni > 0,7) il limite è 2R.
6. **Tesi e reingresso** (sotto).
7. **Qualità**: R:R netto dopo i costi ≥ soglia; quando esisterà lo scorer, EV netto ≥ soglia, che cresce con lo stato.
8. **Sizing e leva** (RiskManager): leva minima ammissibile; liquidazione ad almeno 2× la distanza dello stop più un buffer di gap; altrimenti veto.

Stati, derivati dal budget e mostrati in dashboard:

| Stato | Condizione | Effetto |
|---|---|---|
| NORMAL | Nessun vincolo di sessione attivo | Size fino a 1R_base |
| SELECTIVE | Floor armato, budget ≥ 1R | Soglia di qualità più alta (es. +0,1R di EV), reingressi a metà size |
| PROTECTED | Budget tra 0,25R e 1R | Size = budget; solo tesi nuove e indipendenti dalle posizioni aperte |
| LOCKED | Budget < 0,25R, oppure limite di sessione o globale, oppure errore dati | Nessuna nuova apertura e nessuna chiamata LLM; uscite sempre attive |

Le transizioni verso stati più restrittivi sono immediate. Quelle verso stati meno restrittivi avvengono solo al reset di sessione, salvo l'aumento di budget dovuto a chiusure in profitto, mai a ribassi di prezzo.

### Anti-reingresso
- **`thesis_id`** = hash di (simbolo, direzione, livello di invalidazione arrotondato a 0,5·ATR(1h), epoca di regime). Due candidati hanno la stessa tesi se coincidono simbolo e direzione e se l'invalidazione cade entro 1·ATR(1h) da quella della tesi attiva o chiusa nelle ultime N ore (ipotesi N = 12).
- **Nuova tesi** su simbolo e direzione già usati solo con un *evento di reset* verificabile: ritracciamento di almeno 1·ATR(1h) oltre la zona d'ingresso precedente con formazione di un nuovo swing, cambio di regime, oppure scadenza di N ore.
- **Scala dei reingressi** (ipotesi da confrontare): 1° ingresso a size piena; 2° a metà size e con nuova conferma oggettiva; 3° bloccato (variante "max 3": 3° a un quarto della size). Si confronta con "nessun limite" e con "solo conferma, senza limite numerico".
- **Cooldown**: dopo uno SL la tesi è chiusa, e serve una nuova tesi con evento di reset. Dopo un TP, divieto di inseguire: un nuovo ingresso nella stessa direzione richiede un pullback di almeno 0,5·ATR dal prezzo d'uscita.
- **SHORT contro rimbalzo**: con un flag di inversione (Falco o feature di trend) uno SHORT richiede EV più alto e non può essere un reingresso.

### Eccezioni
**Nella prima versione non ci sono eccezioni.** Oggi nessuna misura fuori campione le può giustificare, e un gate vuoto diventa una scelta discrezionale dell'LLM. Si attivano solo quando lo scorer è calibrato (almeno 1.000 esempi, 45 giorni) e alle seguenti condizioni insieme:
- limite inferiore al 90 % dell'EV netto ≥ +0,3R;
- tesi indipendente da ogni posizione della sessione (altro cluster);
- size ≤ 0,5R_base ed entro il budget del floor;
- mai in LOCKED;
- al massimo una per sessione;
- valutate a parte come braccio C.

### Sessione e reset
- Tutti i timestamp in UTC; i confini di sessione si calcolano con `zoneinfo("Europe/Rome")`. Nei giorni del cambio d'ora le sessioni durano 23 o 25 ore, con test dedicati.
- **PnL di sessione = equity_MTM(t) − equity_MTM(reset).** Le posizioni che attraversano il reset entrano nella base della nuova sessione al loro valore mark-to-market: niente doppio conteggio, e realizzato/non realizzato servono solo per il report.
- Il reset riabilita *solo* la valutazione delle nuove aperture se i gate 1–2 lo consentono. Non chiude posizioni e non azzera high-watermark globale, drawdown, cooldown di tesi o limiti globali.

| Confine | Vantaggi | Svantaggi |
|---|---|---|
| 00:00 Europe/Rome | Intuitivo | La sessione si riattiva mentre l'utente dorme: un blocco di sera viene tolto senza supervisione |
| **08:00 Europe/Rome** (consigliato per la prima prova) | Il blocco serale dura tutta la notte; la riattivazione avviene con l'utente presente | Nel tempo di mercato (UTC) il confine si sposta di un'ora tra ora legale e solare |
| Ora fissa UTC (es. 07:00 UTC) | Stabile rispetto ai funding e alle sessioni di mercato | Meno intuitivo per chi supervisiona |

La redditività dei confini non è dimostrata da nessuna parte: si confrontano 00:00 e 08:00 nel replay. Io sceglierei le 08:00 per la sola ragione di sicurezza (blocco notturno), non per il rendimento.

---

## E. Piano di esperimenti (contro una baseline invariata)

| Fase | Cosa | Dati | Criterio per passare oltre |
|---|---|---|---|
| **E0. Misurare prima di costruire** | EV netto dei trade condizionato a: PnL di sessione al momento dell'apertura (fasce in R), indice di reingresso per simbolo e direzione, tempo dall'ultimo TP/SL. Distribuzione dei picchi di sessione e del giveback; frequenza delle sessioni ≥ +400 | Copie certificate (Fase 0) di Falco, Toro, Brain storico e Arena, tramite Dataset Builder | Se l'EV dopo un guadagno o al 3°+ reingresso **non** è peggiore (con intervallo di confidenza), il Guardian si giustifica solo come riduzione della varianza, e lo si dice chiaramente |
| **E1. Test sintetici** | Macchina a stati, ordine dei gate, floor solo crescente, DST 23/25h, carry-over senza doppio conteggio, LOCKED senza chiamate LLM, ExitService mai toccato, thesis_id e reset | Fixture | 100 % dei test passati, più i test di mutazione |
| **E2. Replay sovrapposto** | Le politiche A, B, D, E, F e le regole di reingresso applicate alle *sequenze di trade storiche* (si rimuovono o ridimensionano trade, senza simulare il mercato) | Come E0 | Bootstrap a blocchi giornalieri; limite dichiarato: si ignora la dipendenza dal percorso (un trade saltato avrebbe potuto liberare margine) |
| **E3. Replay causale** | Per i candidati bloccati o ridimensionati: esito controfattuale dalle candele (`label_origin=counterfactual_simulation` in PR #118) | Candele attestate | Misura del costo opportunità |
| **E4. Shadow** | Nel Brain Unico il Guardian calcola stato e budget e registra "avrei bloccato / ridimensionato", senza agire | PAPER forward | Almeno 20 sessioni, regimi diversi |
| **E5. PAPER attivo** | Guardian vincolante con i criteri pre-registrati | PAPER forward | Confronto con E4 e con E2; nessun LIVE senza consenso separato |

Metriche: PnL netto; max drawdown e CVaR 5 % per sessione e per giorno; giveback dal picco; EV e numero dei trade dopo l'armamento; perdita dei reingressi per thesis_id; costo opportunità dei blocchi; profit factor, expectancy e win rate per LONG/SHORT e per regime; tempo trascorso in LOCKED. **I tre giorni dell'Arena non bastano per ottimizzare**: servono come una delle fonti, mai come set di calibrazione unico. I criteri di adozione si fissano *prima* di guardare i risultati di E2.

---

## F. Dati mancanti e decisioni da prendere insieme (valori = ipotesi, NON autorizzati)

Dati mancanti:
- Copie certificate degli storici (Fase 0, consenso separato).
- Equity MTM per ciclo dei runner (il journal V3 non salva feature, MFE/MAE, funding al momento della decisione; serve il log in avanti di schema v2).
- Commissioni effettive e slippage misurato.
- Tempi dei funding.
- Correlazioni tra simboli.
- Una definizione operativa di "regime".
- Motivi delle chiusure manuali.

| Decisione | Ipotesi iniziale |
|---|---|
| Rischio base per trade (R_base) | **1–1,5 % dell'equity** durante la validazione PAPER (oggi 4,29 %); da aumentare solo con EV misurato (es. frazione di Kelly sul limite inferiore dell'EV) |
| Limite di perdita di sessione | −3R |
| Drawdown globale dall'HWM | −10 % rischio dimezzato; −20 % stop alle nuove aperture e revisione |
| Armamento del floor (A) | Due candidati da confrontare: % dell'equity d'inizio sessione (es. +8 % = +160 su 2.000) oppure +400 fisso come nel report (= +20 %). Va espresso anche in R: con R_base all'1,5 % (30 USDT), +400 equivale a circa 13R e si raggiungerebbe raramente. **Da scegliere** |
| Giveback g | 25 % (confronto con 20 % e 35 %) |
| Confine di sessione | 08:00 Europe/Rome (confronto con 00:00) |
| Reingressi | max 2 per tesi (confronto con 3 e con "solo conferma") |
| Leva | Calcolata: minima ammissibile; massimo tecnico 50×; liquidazione ≥ 2× la distanza dello stop |
| Eccezioni | Disattivate nella v1 |
| Tetto del blocco giornaliero | Sostituire il 50 % dell'Arena: decisione esplicita richiesta |

Domande per l'utente:
1. Il rischio per trade del 4,29 % è una scelta voluta per il Brain Unico, o un'eredità dell'Arena?
2. L'armamento del floor va espresso in USDT fissi o in % di equity?
3. Accetti di **non** avere eccezioni nella prima versione?

---

## G. Idee che ritengo migliori delle nostre, e perché

1. **Un budget di rischio, non una soglia.** Un solo meccanismo che parte dal floor e riduce la size elimina il salto tra "tutto" e "niente", non crea un obiettivo da inseguire e scala con il conto.
2. **Mettere il limite di perdita di sessione e il rischio per trade prima del profit lock.** È l'unica leva che migliora il p5. Proteggere +500 serve a poco se una sessione cattiva costa il 20 %.
3. **Misurare l'E0 prima di scrivere codice.** Decide con i dati se il Guardian aumenta il rendimento o è solo una riduzione della varianza (legittima, ma da chiamare con il suo nome).
4. **L'anti-reingresso prima della soglia di sessione.** Colpisce il meccanismo osservato direttamente.
5. **L'LLM non vede il PnL di sessione e non viene chiamato in LOCKED.** Si eliminano bias e costi.
6. **La leva come risultato, con la scelta della minima ammissibile.** La "leva alta" resta possibile, ma la tabella di §A mostra quando costa più di quanto renda.
7. **Ogni blocco registra il candidato completo.** Il Dataset Builder potrà così misurare il costo opportunità reale del Guardian, invece di supporlo.

### Rischi residui dichiarati
- Il floor non è garantito: gap, slippage e liquidazione possono superarlo. Lo stress di gap va incluso nel rischio aperto.
- Il replay sovrapposto sottostima gli effetti di percorso.
- Con pochi dati storici le soglie restano ipotesi a bassa confidenza.

## Riproduzione
```
python3 -I ops/brain-unico/guardian/sim_policies.py --sessions 40000 --seed 7
```
