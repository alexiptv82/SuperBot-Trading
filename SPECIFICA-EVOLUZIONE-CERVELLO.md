# Specifica — Evoluzione del Cervello Professionale (promemoria dell'utente)

**Stato: DA VALUTARE.** Ricevuta dall'utente il 19/10/2026 alle ~11:51 (ora di Roma), come promemoria dell'integrazione che vuole fare. Il testo è rivolto a Claude e a ChatGPT. L'utente ha detto: "poi la valutiamo insieme" e ha mandato intanto a ChatGPT il messaggio di Claude sul secondo giro di revisione.
**Non autorizza nessuna modifica.** Il passo richiesto è un **piano tecnico** (i 12 punti in fondo), da presentare all'utente e a ChatGPT; il primo intervento concreto lo autorizza l'utente dopo il confronto. Valgono sempre le regole inviolabili di `LEGGIMI.md` (paper, niente redeploy dei bot senza OK, il cervello non si tocca, nessun segreto nel repository).

Il testo che segue è riportato così come l'ha consegnato l'utente.

---

Ciao Claude. Ti consegno nuovamente la specifica concordata per la fase Evoluzione del Cervello Professionale di SuperBot-Trading.

Stato di partenza

La migrazione a Singapore è conclusa. L’app Android è stata provata dall’utente e mostra dati aggiornati di Hawk e Bull.

Non bisogna:

- ripetere la migrazione;
- creare un nuovo run per nascondere le perdite;
- azzerare database, stati, posizioni, storici o memoria;
- intervenire su HI-TV;
- avviare doppie istanze;
- abilitare ordini reali.

Hawk e Bull devono rimanere esclusivamente in PAPER. La baseline da conservare è Hawk run 3 e Bull run 2.

L’audit del weekend ha attribuito la parte principale delle perdite alla concentrazione di posizioni short correlate, ai rimbalzi del mercato, alla leva e ai costi. Sono emersi anche problemi tecnici da correggere o neutralizzare: cronologia delle protezioni, gestione del blocco giornaliero, timestamp delle barre, osservazione delle barre successive all’ingresso e alcuni casi limite tra stop, liquidazione e DCA.

Il run attuale deve essere conservato come riferimento storico.

Obiettivo principale

Costruire un sistema che protegga i profitti già maturati senza chiudere troppo presto le posizioni sane.

Il sistema deve distinguere tra:

- normale oscillazione del prezzo;
- rallentamento temporaneo;
- deterioramento reale del setup;
- inversione probabile;
- profitto che rischia di essere restituito al mercato;
- posizione che occupa uno slot senza più valore atteso sufficiente.

Non vogliamo una singola soglia fissa del tipo “chiudi al +X%”. Vogliamo un Profit Manager dinamico, spiegabile e verificabile.

1. Profit Manager di Hawk

Il Profit Manager deve lavorare sul profitto netto liquidabile, calcolato considerando:

- prezzo corrente realistico di uscita;
- commissione di chiusura;
- slippage stimato;
- spread;
- funding;
- eventuale chiusura parziale;
- profitto massimo raggiunto;
- give-back dal massimo;
- volatilità e ATR;
- regime di mercato;
- momentum;
- segnali di inversione;
- durata della posizione;
- tempo trascorso senza nuovi progressi;
- esposizione già presente sullo stesso simbolo o su asset correlati;
- valore dello slot occupato.

Comportamento richiesto:

1. Finché il profitto non copre costi e rumore normale, il Profit Manager osserva senza anticipare l’uscita.
2. Quando il profitto diventa significativo, attiva una protezione dinamica.
3. La distanza della protezione deve dipendere da volatilità, ATR e regime.
4. Se il trend continua, deve lasciare correre il profitto.
5. Se momentum e struttura si deteriorano, deve ridurre il give-back consentito.
6. Se viene riconosciuta un’inversione credibile, può proporre o eseguire l’uscita secondo la modalità validata.
7. Uno stop protettivo non deve essere automaticamente allargato dopo essere stato stretto.
8. Ogni decisione deve essere registrata con dati, motivazione, versione dell’algoritmo e risultato successivo.

La pressione sugli slot non deve causare chiusure arbitrarie. Una posizione può essere liberata per una nuova opportunità solo quando:

"EV netto nuova opportunità > valore residuo atteso posizione attuale + costi di sostituzione + margine di sicurezza"

La semplice presenza di un nuovo segnale non è sufficiente.

Hawk resta inizialmente a 10 slot. L’eventuale passaggio a 12–13 sarà studiato solo dopo la validazione.

2. Profit Manager di Bull

Bull deve avere una gestione separata e più conservativa.

Non deve ereditare automaticamente i parametri di Hawk. Deve valutare:

- protezione del profitto;
- deterioramento del trend;
- inversione;
- durata;
- costi;
- eventuale uscita parziale;
- gestione della parte residua;
- valore dello slot;
- rischio aggregato con Hawk.

Bull resta inizialmente a 3 slot. L’aumento a 5 è soltanto un’ipotesi futura da simulare e validare.

3. Riconoscimento delle inversioni

L’inversione non deve dipendere da un singolo indicatore.

Il modello deve combinare, senza look-ahead:

- struttura multi-timeframe;
- EMA e loro pendenza;
- RSI e divergenze utilizzabili in tempo reale;
- ATR e variazione della volatilità;
- rotture e recuperi di livelli;
- volume e liquidità;
- funding;
- open interest;
- rapporto long/short, dopo aver riparato gli endpoint che oggi restituiscono dati mancanti;
- deterioramento del setup originale;
- momentum;
- tempo senza progresso;
- regime di mercato.

Le barre in formazione devono essere identificate chiaramente e non trattate come informazioni definitive.

4. Cervello AI professionale

Il Cervello deve partire come osservatore e consigliere. Non deve modificare autonomamente strategia, rischio o prompt.

Deve comprendere:

Regime di mercato

Classificazione probabilistica di:

- trend rialzista;
- trend ribassista;
- range;
- alta o bassa volatilità;
- espansione o compressione;
- liquidità normale o ridotta;
- condizioni anomale di funding/open interest;
- regime incerto.

Ogni classificazione deve avere confidenza e prove utilizzate.

Memoria delle decisioni

Registro append-only e versionato contenente:

- contesto disponibile al momento;
- decisione;
- alternative;
- probabilità stimate;
- valore atteso;
- rischio;
- costi;
- motivazione;
- esito successivo;
- massimo profitto;
- massimo drawdown;
- give-back;
- versione di strategia e modello.

Nessuna informazione futura deve entrare nelle feature della decisione originale.

Opportunità scartate

Registrare anche le opportunità non eseguite:

- segnale;
- motivo dello scarto;
- prezzo teorico;
- rischio;
- risultato successivo calcolato offline;
- presenza di falsi positivi o falsi negativi.

Questi dati servono per capire se i filtri evitano perdite oppure eliminano opportunità valide. Non devono trasformarsi automaticamente in nuove regole.

Probabilità e valore atteso

Usare:

"EV netto = P(vittoria) × guadagno medio − P(perdita) × perdita media − costi non già inclusi"

Le probabilità devono essere valutate con:

- Brier score;
- curve di affidabilità;
- numerosità del campione;
- intervalli d’incertezza;
- split temporali;
- walk-forward;
- out-of-sample;
- controllo del drift.

5. Gestione professionale del rischio

Creare un livello deterministico indipendente dall’AI che controlli:

- rischio effettivo agli stop;
- commissioni e slippage;
- funding;
- esposizione totale Hawk + Bull;
- esposizione per simbolo;
- esposizione per cluster correlato;
- concentrazione long/short;
- drawdown giornaliero e del run;
- buffer di liquidità;
- dati stale o mancanti;
- qualità e sufficienza dello storico.

Con dati insufficienti o non affidabili deve bloccare nuovi ingressi, continuando però a proteggere e gestire le posizioni già aperte.

6. Turbo Scalp

Turbo Scalp sarà una terza strategia indipendente, sviluppata successivamente e soltanto in PAPER.

Dovrà avere:

- portafoglio separato;
- run separato;
- memoria separata;
- limiti di rischio separati;
- metriche separate;
- kill-switch;
- nessuna interferenza con gli slot di Hawk e Bull.

Prima dello sviluppo operativo servono studi offline su commissioni, spread, slippage, liquidità, latenza e fill realistici.

Ordine di implementazione richiesto

1. Rendere sicuri backup e rollback.
2. Ottenere uno snapshot coerente del cervello a fine ciclo.
3. Separare integrazione del codice e deploy automatico.
4. Correggere i problemi di cronologia, timestamp e protezioni emersi nell’audit.
5. Congelare e documentare la baseline attuale.
6. Aggiungere osservabilità e registro delle decisioni senza cambiare il comportamento.
7. Eseguire il Profit Manager di Hawk in modalità shadow.
8. Confrontare baseline e shadow.
9. Solo dopo approvazione, attivare una singola modifica su Hawk in PAPER.
10. Ripetere il processo per Bull.
11. Integrare regime detector, memoria delle opportunità scartate e probabilità calibrate.
12. Valutare gli slot aggiuntivi solamente dopo risultati sufficienti.
13. Studiare Turbo Scalp come progetto indipendente.

Metriche di confronto

Misurare almeno:

- P&L netto;
- drawdown massimo;
- profitto massimo raggiunto;
- profitto effettivamente conservato;
- give-back medio e massimo;
- uscite premature;
- perdite evitate;
- durata delle posizioni;
- commissioni, funding e slippage;
- percentuale di utilizzo degli slot;
- slot liberati utilmente;
- rendimento delle opportunità aperte dopo una liberazione;
- correlazione dell’esposizione;
- precisione dei segnali di inversione;
- calibrazione delle probabilità;
- comportamento nei diversi regimi.

Il Profit Manager non sarà promosso soltanto perché riduce il give-back: dovrà migliorare il risultato netto senza aumentare in modo ingiustificato chiusure premature, costi o rischio.

Backup e rollback obbligatori

Prima di qualsiasi deploy operativo:

- backup coerente e verificato;
- prova di ripristino isolata;
- controllo semantico dello stato, non soltanto hash dei file;
- conservazione di database, run, posizioni e memoria;
- immagine precedente;
- configurazione precedente;
- commit esatto da distribuire;
- procedura di rollback documentata;
- verifica che resti una sola istanza operativa.

Il backup del cervello deve rappresentare un unico punto coerente tra "state_v2.json", "trade_history.jsonl", "learning_log.jsonl", "lessons.md" e gli altri dati collegati. Una semplice copia dei file mentre il ciclo scrive non è sufficiente.

Branch e deploy

Non eseguire merge ciechi tra "main" e "rule-pool".

Preparare un ramo "work/<tema>" partendo da "main", preservando app, autenticazione, frontend e moduli "desk_api", "desk_view" e "live_view".

Integrare selettivamente i componenti dei motori provenienti da "rule-pool", dopo aver corretto il bug dell’import mancante di "Request".

L’integrazione del codice non deve provocare automaticamente un deploy. Il deploy deve utilizzare un commit preciso e approvato.

Richiesta per questa fase

Prima di modificare il progetto, prepara:

1. mappa dei moduli esistenti riutilizzabili;
2. architettura proposta del Profit Manager;
3. formato degli eventi append-only;
4. macchina a stati della protezione del profitto;
5. soluzione per lo snapshot coerente a fine ciclo;
6. soluzione per separare merge e deploy;
7. file che verrebbero modificati;
8. test unitari, replay e shadow previsti;
9. criteri di promozione;
10. rollback;
11. rischi residui;
12. divisione del lavoro proposta tra Claude e ChatGPT.

Non eseguire ancora deploy dei bot e non cambiare strategia, rischio, prompt o numero di slot. Presenta prima il piano tecnico completo a me e a ChatGPT. Dopo il confronto, l’utente autorizzerà il primo intervento concreto.
