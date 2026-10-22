# Step 6 — revisione indipendente e sintesi delle review

Data: 22/10/2026. Oggetto: `fe50c2ff2f459e4260d7f2f4907ad0f7c590a478`.
Autore: ChatGPT. Stato: **revisione propria completata; sintesi esterna provvisoria**.

## 1. Raccomandazione attuale

**Mantenere draft. Nessuna oos_start_utc proposta o impostata in questa fase.**
Prima occorrono le correzioni indicate sotto, la definizione della valutazione
finale, la diagnostica long/short e la revisione dell'archivio OHLC offline.
Una data sara' scelta dopo approvazione e congelamento del codice corretto,
successiva al commit registrato e alla disponibilita' del processo di raccolta.

La precedente consegna con 19 test verdi non dimostrava che il workflow potesse
eseguire un piano approved: la revisione ha identificato un test incompatibile
con quella transizione. Non viene modificato il codice esaminato durante la review.
Solo questa relazione, il diario e STEP6-REVIEW.md vengono aggiornati.

## 2. Fonti e disponibilita' delle revisioni

Letti STATO.md, LEGGIMI.md, MANUALE-OPERATIVO.md e i diari del 22 ottobre.
Controllati script, workflow, piano, test e motore nelle versioni revisionate.
Rami osservati: director-chatgpt fe50c2ff, director-claude 40157c3,
rule-pool 7a5e795. Nessun accesso al VPS o esecuzione di Actions.

| Revisione | Disponibilita' | Uso nella sintesi |
|---|---|---|
| ChatGPT su fe50c2ff | Completa, codice letto e prove sintetiche locali | Rilievi verificati sotto |
| E1, autore non indicato | Ricevuto successivamente; dichiara assenza del sorgente | Riscontro critico in sezione 8, nessuna attribuzione nominativa |
| E2, autore non indicato | Ricevuto contributo metodologico su bootstrap, Holm e direzione | Riscontro in sezione 9; nessuna attribuzione nominativa senza conferma |
| Claude su Step 6 | Testo non presente nel diario letto o nei messaggi ricevuti | In attesa; la review PR #1 riguarda Step 5 e non e' sostitutiva |
| DeepSeek su Step 6 | Non ancora ricevuta | In attesa |
| Kimi K3 su Step 6 | Non ancora ricevuta | In attesa |

Non e' possibile attribuire accordo, dissenso o novita' rispetto a Claude finche'
non sono disponibili i testi Step 6. La matrice sara' completata sui contenuti
effettivamente ricevuti, distinguendo segnalazioni da difetti riprodotti.

## 3. Rilievi della revisione indipendente

I riferimenti di riga sono quelli del commit esaminato, prima di modifiche documentali.

| ID | Gravita' / stato | Punto e prova | Correzione o decisione necessaria |
|---|---|---|---|
| R1 | Bloccante operativo, riprodotto | Il workflow righe 31-32 esegue tutta la suite. Il test righe 246-249 impone draft e data nulla. Con piano approved la suite fallisce prima di SSH. | Separare l'asserzione di consegna draft dai test del runner; provare l'intero percorso approved senza VPS. Il trigger deve riferire un commit approvato precedente alla sua creazione, se si mantiene il test di assenza trigger. |
| R2 | Integrita' coorte, riprodotto | Script righe 345-348: version_gate osserva solo open/close. Aggiungendo un claude_call di una versione diversa nel periodo, resta unchanged_in_recorded_events. Un deploy senza nuovi trade puo' quindi sfuggire. | Invalidare versioni divergenti su tutti gli eventi pertinenti; attestare continuita' e configurazione effettiva del periodo, compresi parametri esterni al codice. Una singola verifica corrente non ricostruisce la storia. |
| R3 | Classificazione statistica, riprodotto | Con 100 trade, 100 interventi, 42 giorni trascorsi ma un solo episodio, IC=null; sample_gate=review_sample_reached e hypothesis_gate=not_supported. | Distinguere evidenza insufficiente da fallimento dei criteri: pochi episodi o IC non calcolabile devono restare pending/inconclusive, con motivazione. |
| R4 | Disegno confermativo da completare, letto nel codice | Il piano ha min_days/min_trades/min_changed, senza termine della coorte o regola di valutazione finale. Il gate puo' essere ricalcolato a ogni run; Bonferroni sui bot non corregge le osservazioni ripetute. | Predefinire termine di arruolamento, maturazione dei trade e una sola valutazione finale, oppure un metodo sequenziale esplicito. Le statistiche intermedie restano descrittive. |
| R5 | Domanda operativa non osservabile nell'output, verificato | analyze/summarize eliminano side dai gruppi; esistono solo storico e prospective per bot. | Aggiungere diagnostica per direzione e relative esclusioni prima della registrazione; definire se i sottogruppi sono solo descrittivi. |
| R6 | Congelamento workflow incompleto, rilevato staticamente | Il workflow caricato da Actions e' quello del commit che modifica il trigger. git checkout allo SHA congelato cambia i file del checkout, non la definizione del job gia' caricata. Il blob YAML eseguito non viene confrontato con quello approvato. | Verificare identita' del workflow del commit trigger e di quello congelato, o usare un percorso approvato che fissi anche il codice operativo del workflow. Nessun problema attivato nella presente review. |

R4/R6 sono analisi del disegno, non risultati di una run su GitHub/VPS.
R1/R2/R3/R5 sono riprodotti con input sintetici. Per nessuno si puo' ancora dire
che sia una novita' rispetto a Claude: manca il testo della sua review Step 6.

## 4. Parti confermate e limiti residui

**Contabilita' delle due meta' — verificata.** La somma di 0,5 volte il netto della
prima uscita e 0,5 volte quello della seconda attribuisce una sola commissione
di ingresso complessiva. Le commissioni di uscita e il funding sono pesati per
quantita' e durata di ciascuna meta'. Un calcolo manuale indipendente coincide
con il replay. Per i trade ammessi, qty=margin*leverage/entry coincide con engine.open.

**Cronologia — verificata nel codice e nei test.** Usa il close della barra per
la decisione e un open successivo per il fill; la sensibilita' aggiunge una barra.
Non usa gli estremi precedenti all'ingresso per l'attivazione. Il confine baseline
esclude prudenzialmente la barra del suo SL/TP. Non e' un ordine limite a +1,5R.
Il residuo che non esce prima mantiene meta' della baseline: le future decisioni
discrezionali restano esogene. Quindi e' un overlay condizionato agli ingressi e
alle uscite registrate, non un backtest completo del conto o delle decisioni AI.

**reviewed_versions — controllo sorgenti effettuato.** Le cinque versioni
5818aee/b4709d1/b6b9911/fa3e220/4aabeb8 hanno default fee 6 bp, slip 2 bp e funding
1 bp/8h solo long; le formule di _close esaminate sono coerenti con il runner.
Le versioni sono ammissibili per quel modello di costi, non prova di equivalenza
strategica o dei parametri effettivi storici. Lo storico multiversione resta
esplorativo. baseline_version=4aabeb8 e' coerente con il rilascio riportato nel
diario; non va sostituita con 7a5e795 solo perche' quest'ultimo e' HEAD rule-pool.
Nessun container corrente e' stato interrogato per confermarla.

**Workflow — controlli letti e harness locale passato.** PAPER da env dei container,
SSH con host key verificata, immagine locale fissata all'ID, rete container assente,
filesystem read-only, mount ro, risorse limitate, trap di invarianza su successo/errore,
artifact aggregato. Non emergono comandi di stop/restart/ordine o scritture nel
cervello. L'invarianza confronta ID/immagine/StartedAt, non dimostra continuita'
della configurazione durante tutta la coorte. Hash input attestano byte, non
autenticita' OHLC; il collector e il suo archivio devono ancora essere revisionati.

**Bootstrap — struttura plausibile, precisione non certificata.** Ricampiona
episodi interi e ricalcola la media pesata per trade; seed deterministico e IC
97,5% nominale per due confronti primari. Bonferroni non richiede indipendenza
tra bot, ma presume validita' delle inferenze marginali. Non risolve pochi cluster,
dipendenza seriale residua, selezione dei soli trade chiusi o controlli ripetuti.
Cinque episodi sono un minimo computazionale, non una giustificazione di potenza.

## 5. Asimmetria short/long del 22 ottobre

**Riportato dall'utente, non verificato oggi sui registri:** short spesso positivi,
long con perdite rilevanti. Nessun dato di giornata e' stato acquisito in questa
review, in conformita' al divieto di esecuzione sul VPS.

Un singolo giorno puo' riflettere regime di mercato, asset correlati, differenti
orari o esposizioni. Importi di perdita diversi possono dipendere anche dal
rischio iniziale, oltre che dall'esito in R. Non bastano a dimostrare che tutti
i long siano strutturalmente sbagliati o che gli short siano quasi infallibili.

Il precedente rapporto Step 4 nel diario (letto, non ricalcolato dai registri in
questa sessione) includeva 9 long Hawk e 4 long Bull, nessuno positivo. E' un
segnale da approfondire, con campione piccolo e multiversione. Nello stesso
storico anche gli short avevano perdite; non equivale all'osservazione di oggi.

**Il runner attuale non rende visibile questa differenza.** La direzione e'
usata nella contabilità, ma non esposta come gruppo. Inoltre un long che non
raggiunge +1,5R a barra chiusa non riceve interventi: un overlay di profitto
non risolve da solo un problema di ingresso o selezione long.

**Aggiunta richiesta prima dell'approvazione:** bot x lato x coorte con n,
giorni/episodi, interventi, R baseline/candidato e delta appaiato; win rate,
vincita/perdita media in R, costi in R, durata, stop e leva; esclusioni e posizioni
ancora aperte per lato. Confrontare il dimensionamento con rapporti normalizzati
senza pubblicare importi. Incroci con regime BTC all'ingresso e versione/run
restano descrittivi quando i campioni sono piccoli. Dichiarare giorno di apertura
o chiusura e fuso della giornata, senza mescolare le due attribuzioni.

Mantenere due test primari per bot e sottogruppi descrittivi e' una proposta
coerente. Se si vogliono quattro conclusioni confermative bot x lato, occorre
ridefinire numerosita', famiglia di confronti e correzione prima dell'OOS.
Non scegliere solo il lato favorevole dopo aver visto gli esiti.

Il requisito e' ora aggiunto a deploy/STEP6-REVIEW.md. Non e' ancora implementato
nell'output dello script esaminato.

## 6. Matrice della sintesi esterna — da completare

| Tema | ChatGPT | Claude Step 6 | DeepSeek | Kimi K3 |
|---|---|---|---|---|
| Contabilita' e tempi | Confermati con limiti dichiarati | In attesa | In attesa | In attesa |
| Transizione draft/approved | R1 bloccante | In attesa | In attesa | In attesa |
| Continuita' baseline e workflow | R2/R6 da correggere | In attesa | In attesa | In attesa |
| Episodi, test ripetuti, coorte | R3/R4 da completare | In attesa | In attesa | In attesa |
| Long/short | Segmentazione necessaria, diagnostica proposta | In attesa | In attesa | In attesa |
| Approvazione e data OOS | No; mantenere null | In attesa | In attesa | In attesa |

**Accordi fra le tre revisioni esterne:** non determinabili finora.
**Divergenze non risolte:** non confrontabili finora; aperti i punti R1-R6.
**Bug nuovi rispetto a Claude:** non attribuibili senza il testo originale.
La presenza di limiti gia' nella specifica ChatGPT non equivale a una review Claude.

## 7. Prove riproducibili eseguite localmente

Python 3.12.14. Suite originale: 19/19 passati; py_compile passato.
Nessuna run Actions o esecuzione sul VPS.

1. Eseguire solo test_plan_shipped_as_non_executable_draft fornendo tramite mock
   il piano sintetico approved dei test: failures=1.
2. Generare con le fixture esistenti 100 trade tutti nella stessa giornata,
   OHLC complete e asof a start+42 giorni: n=100, changed=100, episodes=1,
   ci=null, sample_gate=review_sample_reached, hypothesis_gate=not_supported.
3. Aggiungere un evento claude_call con codice differente nel periodo OOS:
   version_gate rimane unchanged_in_recorded_events.
4. Verificare i gruppi generati: nessun gruppo long/short.
5. Calcolare separatamente le due meta' con qty/2, fee iniziale ripartita,
   fee su ciascun fill e funding fino a ciascuna uscita: coincidenza <1e-12 in R.

Le prove aggiuntive sono dimostrazioni sintetiche, non una nuova misura dei bot.
La chiusura della sintesi e' subordinata alla ricezione dei tre report Step 6.


## 8. Primo contributo esterno ricevuto — E1, autore non indicato

Il messaggio del 22/10 dichiara esplicitamente di non aver ricevuto il sorgente.
E' un'analisi condizionale delle specifiche, non una verifica indipendente delle
righe del commit. L'autore non e' indicato: non viene attribuito a DeepSeek o Kimi.
Resta da ricevere una revisione con accesso al codice, oltre alle altre review.

| Punto di E1 | Riscontro sul commit fe50c2ff | Esito per la sintesi |
|---|---|---|
| Ripartire entry fee/funding e separare exit fee | liquidation calcola il costo dell'intera posizione alla durata richiesta; replay ne prende meta' per ciascuna uscita. Le quote si sommano senza duplicare il costo iniziale. Gia' verificato con calcolo indipendente. | Principio condiviso; nessun nuovo bug di doppio addebito dimostrato. |
| Controllare low/high per la liquidazione forzata | La funzione liquidation e' una valorizzazione netta d'uscita, non il controllo del margine o del prezzo di liquidazione. I trade baseline con why=liquidazione sono esclusi. Il close e at+BAR indicano la valorizzazione al termine della barra del segnale; il fill usa l'open successivo. | Rilievo inapplicabile alla funzione presente. Non sostituirla con la formula exchange proposta. Rinominare la funzione puo' ridurre l'ambiguita' documentale. |
| All'ultimo indice scartare l'episodio o forzare una chiusura | window richiede gia' una serie completa fino al bucket baseline; replay conserva il trade e il risultato baseline, o meta' baseline se il parziale e' gia' eseguito. Non elimina l'episodio per fill_i fuori finestra. Il confine baseline vieta uscite successive. | Nessun difetto dimostrato dal solo controllo di indice. Una lacuna prima del confine e' invece un'esclusione conteggiata. Forzare l'ultima chiusura cambierebbe la specifica. |
| Inverso dello slippage dipende dalla convenzione | engine._close usa exit_fill=exit_ref*(1-side*2/10000), con i default revisionati; l'inverso nel runner e' coerente per long e short. | Conferma condizionale verificata nel nostro motore PAPER; non e' un'affermazione sullo slippage reale di Bitget. |
| Bootstrap a episodi e Bonferroni sui due confronti | Il delta delle due meta' e' gia' riunito per trade; gli episodi raggruppano poi piu' trade dello stesso giorno/sovrapposti. Vengono ricampionati interi episodi. IC 97,5% nominale per bot coerente con due confronti prefissati. | Principio condiviso. Non risolve pochi episodi, dipendenza seriale, campione selezionato o controlli ripetuti. |
| 2000 repliche sarebbero sufficienti | Un numero di repliche non garantisce validita' o precisione. Con code all'1,25%, ogni coda contiene circa 25 repliche attese; serve valutare stabilita' Monte Carlo e soprattutto numero/dipendenza degli episodi. | Giudizio generale di E1 troppo forte; nessuna certificazione di adeguatezza statistica. |
| Un giorno non prova asimmetria strutturale; segmentare | Coerente con l'analisi gia' registrata. L'output fe50c2ff aggrega i lati e l'overlay non interviene se non si raggiunge +1,5R. | Accordo metodologico con ChatGPT, non ancora consenso fra tutte le review esterne. |
| Mancata riproduzione implica problema live; persistenza storica implica difetto strutturale | I bot sono PAPER. Gruppi assenti, esclusioni, diversi orari/coorti, rischio e regime possono spiegare differenze nel confronto. Una persistenza descrittiva non identifica da sola una causa. | Deduzioni causali non giustificate da E1. Nessuna diagnosi nuova sul bot. |
| Usare funding storico exchange | Il runner riproduce il modello PAPER 1 bp/8h solo long; short a zero. Anche le uscite candidate sono modellate a mercato con fee 6 bp, non una miscela di ordini maker/taker. | Funding storico e altre fee sono estensioni di realismo da studiare separatamente; non correzioni automatiche del confronto col modello esistente. |

Le formule, tariffe correnti Bitget e il caso Freqtrade citati da E1 non vengono
convalidati da questa integrazione: non sono necessari per il riscontro sul
codice PAPER e non vengono usati come prova di un difetto. Nessun parametro
dei bot o del runner viene cambiato in base a queste affermazioni.

Accordi identificabili finora: E1 e ChatGPT condividono proporzionalita' dei costi,
unita' di ricampionamento aggregata, cautela sul singolo giorno e segmentazione.
Divergenze: significato di liquidation, gestione della fine finestra, adeguatezza
di 2000 repliche e inferenze su live/strutturalita'. Nessun nuovo bug concreto
riprodotto a partire da E1. I rilievi R1-R6 restano aperti; E1 non li verifica.

Raccomandazione invariata: draft e oos_start_utc=null. Matrice Claude/DeepSeek/Kimi
ancora aperta: E1 non riempie una colonna nominativa senza attribuzione dell'autore.
Solo documentazione aggiornata, nessuna nuova esecuzione sui dati dei bot.


## 9. Secondo contributo esterno — E2, metodologia statistica

Ricevuto il 22/10/2026, autore non indicato nel messaggio. Viene conservato come
E2 e non attribuito automaticamente a Kimi K3. Non certifica la lettura del
sorgente ne' verifica i bug operativi R1/R2/R6. Questa sezione distingue le
proposte metodologiche dai cambiamenti implementati: nessuna modifica al runner.

| Proposta o affermazione E2 | Valutazione rispetto al nostro disegno | Decisione proposta prima della registrazione |
|---|---|---|
| Bootstrap episodi e delta appaiato per trade | Accordo. Il codice calcola gia' candidate_R-baseline_R per trade prima di riunire gli episodi. | Conservare questa struttura; riportare numerosita', dimensioni e concentrazione degli episodi. |
| Aumentare B a 10.000 e controllare semi | Ragionevole per ridurre errore Monte Carlo; non aumenta l'informazione del campione originale. | Proposta accolta per revisione, con semi e tolleranza degli endpoint predefiniti; verificare durata/RAM nel limite del container. Non ancora implementata. |
| Passare automaticamente a BCa se la distribuzione e' asimmetrica | Non e' una garanzia generale. BCa richiede stime di influenza/accelerazione coerenti con l'unita' cluster; pochi episodi, cluster sbilanciati o degenerazione possono renderlo instabile. | Fissare in anticipo metodo principale, diagnostiche e gestione di IC non calcolabili. Eventuale jackknife rimuove episodi interi. Evitare selezione del metodo in base al risultato favorevole. |
| Sostituire Bonferroni con Holm | Holm controlla FWER con dipendenza arbitraria fra test validi ed e' almeno altrettanto potente. Il runner pero' produce IC percentile, non p-value da test calibrati sotto H0. | Non e' una sostituzione meccanica del livello degli IC. Se scelto Holm, definire H0, test cluster e p-value validi, famiglia e report IC coerente prima dell'OOS. Bonferroni resta utilizzabile finche' non viene approvato tale ridisegno. |
| Rimpiazzare minimi di trade con 30-40 episodi e 25-30 episodi attivati | Il numero di cluster e' essenziale; non e' pero' una misura esatta universale dell'effettiva informazione, che dipende anche da dimensioni, pesi e dipendenza residua. Quelle soglie sono proposte euristiche. | Aggiungere requisiti su episodi ed episodi attivati, senza cancellare automaticamente requisiti di durata, trade/esposizione ed interventi. Numeri finali da calibrare su precisione/potenza e fattibilita', non ancora approvati. |
| L'episodio cattura solo sovrapposizione diretta | Il codice raggruppa anche stesso giorno UTC e sovrapposizioni transitive attraverso piu' giorni. Resta vero che non cattura tutta la dipendenza di regime fra episodi. | Correggere la descrizione; misurare quanti episodi si ottengono davvero. Non presumere che 42 giorni forniscano 30-40 cluster o piu' regimi. |
| Influence check per episodio | Accordo, e' piu' coerente con l'unita' inferenziale del solo rimuovere tre trade migliori. | Aggiungere leave-one-episode-out, concentrazione dei pesi e variazione dell'effetto. Registrare cosa fare se un episodio determina la conclusione. Nessuna soglia scelta dopo aver osservato il risultato. |
| Il mix direzionale confonde necessariamente la differenza appaiata | Formulazione troppo forte. Il confronto corrente include tutti i trade ammessi, anche quelli senza intervento (delta=0). Non confronta campioni diversi fra bracci. L'effetto medio puo' comunque cambiare quando cambiano mix direzionale o effetti per lato. | Distinguere effetto sulla popolazione realmente osservata da trasferibilita' ad altri mix. Evitare l'analisi limitata a posteriori ai soli trade attivati. |
| I long che vanno male attiverebbero piu' spesso il parziale | Ipotesi non dimostrata. La regola richiede prima un close >=+1,5R: un long sempre sfavorevole non riceve alcun intervento. | Misurare tassi di attivazione, opportunita' di profitto e delta per lato; non assumere che l'overlay corregga perdite persistenti senza precedente profitto. |
| Pesi fissi long/short per i due test primari | Possibile, ma cambia il parametro stimato rispetto alla media naturale per trade. Richiede supporto sufficiente in entrambi i lati e pesi decisi prima. | Esplicitare popolazione obiettivo e gestione di uno strato scarso/assente. Non imporre automaticamente 50/50 a un sistema quasi solo short. |
| Bootstrap stratificato per bot x direzione | Va preservata la dipendenza dell'episodio. Un episodio puo' contenere long e short, e anche posizioni dei due bot. Ricampionare i lati in modo indipendente la distruggerebbe. | Ricampionare congiuntamente episodi interi, mantenere tutte le osservazioni e stimare gli effetti direzionali dentro la replica. Eventuale combinazione con pesi fissi. Repliche con strati assenti non vanno eliminate silenziosamente. |
| Bias da esecuzione live come spiegazione odierna | I bot studiati sono PAPER; non abbiamo letto i trade di oggi. L'affermazione non dimostra un guasto di esecuzione reale. | Mantenere la distinzione fra osservazione utente, modello PAPER, regime e verifiche tecniche; nessuna diagnosi causale aggiuntiva. |

Le percentuali precise di copertura 93,6-94,6% / 94,6-95,4% riportate da E2 non
sono accompagnate da una fonte identificabile nel messaggio e non vengono
adottate come risultati universali per Step 6. Sono diversi errore Monte Carlo
degli endpoint ed errore di copertura dovuto a campione/metodo/dipendenza.
Con B=2000 le code all'1,25% contengono circa 25 repliche attese; con B=10000 circa
125. Questo calcolo non dimostra che la copertura sia corretta.

Fonti primarie consultate per verificare i punti metodologici:

- R stats, p.adjust: https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html — input p-value, FWER di Holm/Bonferroni e validita' con dipendenza arbitraria fra test marginalmente validi.
- R boot, boot.ci: https://stat.ethz.ch/R-manual/R-devel/library/boot/html/boot.ci.html — distingue percentile, studentizzato e BCa, con requisiti diversi.
- R boot, print.bootci: https://stat.ethz.ch/R-manual/R-devel/library/boot/help/print.bootci.html — diagnostica di instabilita' per endpoint estremi.
- Cameron, Gelbach, Miller, Bootstrap-Based Improvements for Inference with Clustered Errors: https://www.nber.org/papers/t0344 — evidenzia problemi con pochi cluster in regressione. Non stabilisce una soglia universale valida per il nostro overlay.

Convergenze ora osservabili fra ChatGPT, E1 ed E2: confronto appaiato, rispetto
della dipendenza, prudenza sul singolo giorno e diagnostica long/short.
Divergenza E1/E2: E1 considerava 2000 repliche generalmente adeguate; E2 propone
10000. ChatGPT propone piu' repliche e verifica Monte Carlo, senza equipararle a
piu' dati o a copertura garantita. E2 aggiunge proposte utili su episodi attivati,
influenza e metodo di correzione, ma non sostituisce una review del codice.

Per i confronti confermativi restano due opzioni da scegliere prima dell'OOS:
(a) due effetti primari per bot con target/mix esplicito e direzioni descrittive;
(b) quattro effetti primari bot x lato con nuova famiglia, correzione e precisione
richiesta per ciascuno. Non si passa da (a) a (b) dopo aver visto i risultati.
Un effetto eterogeneo non rende falsa la media aggregata per il suo target, ma
puo' renderla insufficiente per decidere dove applicare la variante.

Esito: nessuna approvazione automatica. R1-R6, protocollo di valutazione finale,
archivio OHLC e segmentazione implementata restano da risolvere. Draft e data
OOS nulla confermati. Le proposte E2 non sono ancora state applicate al codice.
Le attribuzioni nominative e la review Claude Step 6 restano da completare.


## 10. Replica esterna con lettura del sorgente dichiarata

Ricevuto un ulteriore messaggio che dichiara la lettura di fe50c2ff e include
gran parte dello script. Autore e indipendenza rispetto a E1 non attestati:
questo messaggio non prova un ulteriore revisore indipendente. I numeri di riga
citati non corrispondono al file immutabile di 415 righe; di seguito uso quelli
del commit verificato. Il testo incollato termina troncato, ma il sorgente
integrale e' disponibile al permalink gia' indicato.

| Rilievo ricevuto | Verifica sul commit fe50c2ff | Esito |
| --- | --- | --- |
| Funding solo long, bug grave | Righe 206 e 231: riproduce la stessa convenzione del motore PAPER gia' verificata; riga 312 dichiara che non e' funding reale. | Limite del modello, non nuovo errore di replica. |
| Liquidazione su close e at + BAR | Righe 227-232 e 260: valutazione netta ipotetica a chiusura barra, segnale di uscita alla prossima apertura. Non calcola una liquidazione forzata a margine. | Cambiare a low/high cambierebbe il candidato predefinito. |
| fill_i fuori finestra scarta l'episodio | Righe 252-263: continue salta solo la possibile decisione della barra; il trade ritorna comunque baseline oppure mezza uscita piu' mezza baseline. | Rilievo non confermato. La selezione dei soli trade chiusi resta un limite distinto. |
| Inversione slippage | Riga 203 e formula riga 228: inverse coerenti con la convenzione PAPER. | Accordo confermato. |
| IC: 24/1974 da sostituire con 25/1975 | Riga 290: 24 e 1974 sono gli indici Python corretti del quantile empirico inverso ai livelli 0.0125 e 0.9875, con B=2000. | Nessun off-by-one dimostrato; esplicitare la convenzione. |

### Funding e direzione: cosa si puo' concludere

Il funding long-only puo' influenzare le differenze fra direzioni nel modello
PAPER. Non e' pero' una distorsione introdotta dal solo replay: il runner deve
riconciliare la contabilita' registrata prima di confrontare le uscite. Nemmeno
si puo' affermare che il funding si cancelli sempre nel confronto appaiato:
uscite anticipate cambiano la durata esposta al costo, quindi anche delta_R.

Per studiare funding reale occorre un diverso modello coerente per entrambi
i bracci, con serie storiche, segno, tempi di addebito e quantita' residua.
Cambiare soltanto liquidation() romperebbe la coerenza con la riconciliazione
e con il target PAPER. L'osservazione odierna non e' stata misurata sui log in
questa sessione: non attribuiamo le perdite long al funding senza evidenza.

L'assenza di asimmetria nel replay non dimostrerebbe un bug di esecuzione:
coorte selezionata, copertura temporale, esposizioni e regole del modello
possono differire. La persistenza su piu' settimane non basta, da sola, a
dimostrare causalita' strutturale. Serve la segmentazione gia' richiesta in R5,
con numerosita', attivazioni, esclusioni, costi e risultati in R per direzione.

### Quantili: verifica riproducibile, non correzione arbitraria

Per il quantile empirico inverso, indice Python = ceil(B * p) - 1:
- B=2000, p=0.0125: indice 24;
- B=2000, p=0.9875: indice 1974.

La documentazione primaria R distingue nove convenzioni. Il tipo 1 e'
l'inverso della distribuzione empirica; il tipo 7 interpola invece alle
posizioni Python 24.9875 e 1974.0125. Non impone gli indici 25/1975.
Fonte: https://stat.ethz.ch/R-manual/R-devel/library/stats/html/quantile.html

Spostare entrambi gli endpoint di un posto verso l'alto non rende
necessariamente l'intervallo piu' ampio: su samples=range(2000), [24,1974]
e [25,1975] hanno la stessa ampiezza e diversa posizione. Con spaziature
irregolari l'ampiezza puo' aumentare o diminuire. La convenzione deve essere
esplicitata e verificata quando si parametrizzera' B; il problema dei pochi
episodi e della precisione Monte Carlo resta separato.

### Esito della replica

Nessun nuovo bug grave confermato da questo messaggio. Restano validi la
ripartizione proporzionale delle due meta', lo slippage inverso e il bootstrap
per episodi, con i limiti statistici gia' discussi in sezione 9. Non adottare
le correzioni proposte su funding, estremi intrabarra o indici senza cambiare
esplicitamente obiettivo e protocollo.

R1-R6 restano aperti: test incompatibile con piano approved; copertura del
version gate; gate campionario senza requisito di episodi; arresto e valutazione
OOS non congelati; diagnostica direzionale assente; equivalenza workflow
eseguito/revisionato non verificata. Confermata la raccomandazione: status
draft, oos_start_utc nulla. Nessun merge, esecuzione VPS o modifica funzionale.


## 11. Revisione Gemini — valutazione conclusiva delle revisioni ricevute

Attribuzione: Gemini, come indicato dall'utente. Il testo dichiara di non aver
letto il repository; costituisce un commento metodologico, non una verifica
indipendente del codice. La motivazione "protetto/non indicizzato" non prova
una restrizione del repo: questo e' pubblico e il sorgente e' stato letto
tramite GitHub al commit immutabile. Non confondere accesso dello strumento
del revisore con disponibilita' del file.

| Punto Gemini | Riscontro sul sorgente fe50c2ff | Decisione |
| --- | --- | --- |
| Allocazione entry fee, exit fee e funding per meta' e durata | Le due valutazioni pesate .5 ricalcolano le fee e usano tempi distinti; l'entry registrata resta fissa. | Principio condiviso, implementazione gia' coerente con PAPER. Non aggiungere due volte lo slippage d'ingresso incorporato nel prezzo. |
| close e at + BAR sottostimano liquidazioni | liquidation() restituisce il netto di un'uscita ipotetica; il candidato usa intenzionalmente chiusure di barra e fill alla prossima apertura. | Non confermato. Una regola intrabarra sarebbe un candidato diverso; OHLC non identifica il momento esatto di un attraversamento. |
| Aggiungere controllo fill_i e forced close | Il controllo esiste alle righe 252-253; il fallback alle righe 262-263 mantiene la baseline per il residuo. | Nessun IndexError dimostrato. Forced close all'ultima close cambierebbe il confronto. |
| Segno errato in baseline_ref | Riga 228: fill=ref*(1-side*slip/10000). Riga 203 divide esattamente per lo stesso fattore con slip=2. | Rilievo errato per questa convenzione di uscita. Una convenzione d'ingresso non ne determina il segno. |
| Bootstrap per episodi e 10000 repliche | Raggruppa giorni UTC e sovrapposizioni; preserva quella dipendenza, non ogni dipendenza seriale fra episodi. | Utile aumentare B e verificare Monte Carlo; non garantisce copertura o adeguatezza dei pochi episodi. NumPy non e' una dipendenza del runner stdlib attuale. |
| Bonferroni garantisce rigorosamente FWER | Correzione per due confronti prevista, ma gli IC sono bootstrap approssimati; esistono problemi di dipendenza residua, pochi cluster e arresto/peeking. | Correzione valida condizionatamente alla validita' dei test/IC marginali; non garanzia incondizionata di questo runner. |
| Metriche per Hawk/Bull x long/short | Non ancora implementate. | Necessarie prima di approvare, come gia' richiesto in R5. |

### Verifica algebrica dello slippage

Esempio sintetico senza dati operativi: ref=100, slip=2 bp.
Long: fill=99.98, quindi 99.98/(1-0.0002)=100.
Short: fill=100.02, quindi 100.02/(1+0.0002)=100.
Il segno peggiora correttamente l'uscita di entrambi i lati. Dividere con il
segno opposto non invertirebbe questa funzione. Si confronta la formula
effettivamente usata nei log, non una convenzione "comune" ipotetica.

### Cosa aggiungere all'analisi direzionale

Accolta la proposta di win rate, R medio e profit factor per bot e direzione,
sempre insieme a n, giorni, episodi, attivazioni, esclusioni e costi in R.
Pre-specificare il profit factor (somma R positivi / valore assoluto somma R
negativi), riportando null e un indicatore quando il denominatore e' zero.
Non serializzare Infinity, importi reali, saldi, simboli o singoli trade.
Rendere esplicito che PF su R normalizzati descrive questo target e non
necessariamente il profit factor monetario del conto. Segmentazione descrittiva
e famiglia di confronti confermativi restano distinte come in sezione 9.

Non accolta l'affermazione di "risposta inequivocabile" o diagnosi istantanea:
questo runner non produce una curva equity di portafoglio, non simula rientri
e non separa causalmente bug, regime, selezione o esecuzione. Una curva negativa
in periodi rialzisti non dimostra da sola un errore di segno; una curva coerente
col regime non esclude errori. Servono controlli indipendenti su codice, coorti
e dati. Non sono stati letti i trade odierni durante questa sintesi.

### Sintesi finale dopo Gemini

Accordo osservabile fra contributi ricevuti: contabilita' per quantita' e
durata, confronti appaiati, bootstrap dell'unita' dipendente e diagnostica
long/short. Non attribuiamo questo accordo a una review Claude Step 6 non
disponibile; gli autori dei precedenti testi non sono stati confermati.

Divergenze risolte sul codice: nessun errore dimostrato nel segno dello
slippage, nella valutazione a close del candidato o nel guard sull'ultima
barra. La proposta 25/1975 non e' una correzione necessaria. Funding reale
resta fuori dal target PAPER dichiarato. Restano da scegliere e validare
B/metodo IC, requisiti sugli episodi, famiglia dei test e protocollo OOS.

Gemini non aggiunge nuovi bug verificati. Il piano NON e' pronto per approved:
risolvere R1-R6, verificare archivio OHLC e provenienza/configurazione della
baseline, congelare coorte, maturazione, arresto e analisi finale, e sottoporre
il codice modificato a test e review. Nessuna data OOS proposta retroattivamente:
oos_start_utc resta null fino alla registrazione di un piano completo e
approvato, con inizio futuro rispetto al commit di registrazione.

Aggiornata esclusivamente documentazione sul ramo diario. Nessun cambio
funzionale, merge, trigger, esecuzione VPS o push su stable/*.
