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
