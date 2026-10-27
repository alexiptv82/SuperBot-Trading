# Fee Hawk e Bull — confronto run concluse, 27 ottobre 2026

Analisi dei soli dati PAPER già acquisiti e riconciliati nell'audit del 27/10, snapshot 14:30 UTC (15:30 Zurigo). Fonti: [positions.csv](positions.csv), [realizations.csv](realizations.csv), [run_metrics.json](run_metrics.json). Nessuna nuova lettura/scrittura ai dati operativi, nessun cambio di codice trading, prompt, parametri o deploy.

## Conteggi e costi

Una posizione include tutte le sue chiusure parziali. I realizzi sono le righe contate dalla dashboard; non equivalgono a ingressi indipendenti.

| Run | Posizioni | Realizzi dashboard | Fee totale PAPER | Fee media/posizione | Fee media/realizzo | Posizioni/giorno |
| --- | --- | --- | --- | --- | --- | --- |
| Hawk #2 positiva | 76 | 76 | 203,03 | 2,67 | 2,67 | 21,72 |
| Hawk #5 negativa | 112 | 131 | 276,98 | 2,47 | 2,11 | 24,72 |
| Bull #1 positiva | 17 | 30 | 80,17 | 4,72 | 2,67 | 4,86 |
| Bull #4 negativa | 77 | 89 | 330,25 | 4,29 | 3,71 | 13,69 |

Le run durano rispettivamente 3,499 / 4,531 / 3,501 / 5,623 giorni: confrontare solo i conteggi totali sovrastima l'aumento di frequenza. Hawk aumenta le posizioni/giorno del 13,8%; Bull del 182,0%, circa 2,82 volte.

## Size effettiva

| Run | Margine medio per posizione | Margine mediano | Notional medio con leva | Leva media |
| --- | --- | --- | --- | --- |
| Hawk #2 | 99,60 | 100,00 | 2.236,41 | 22,46x |
| Hawk #5 | 97,92 | 100,00 | 2.061,36 | 21,04x |
| Bull #1 | 174,29 | 182,00 | 3.954,71 | 22,35x |
| Bull #4 | 170,29 | 165,00 | 3.575,42 | 20,74x |

Margine qui = somma dei margini effettivamente chiusi nelle tranche della posizione; non somma delle proposte né solo ultima tranche residua. Notional = somma margine realizzato × leva. Questo confronto copre tutte le posizioni, comprese le prime due golden per profilo prive di evento open. Il margine iniziale loggato copre 74/76 Hawk #2 e 15/17 Bull #1; le altre due run hanno copertura completa. Non imputo valori mancanti.

Size media leggermente inferiore: margine circa -1,7% Hawk e -2,3% Bull; notional circa -7,8% e -9,6%. Non emerge una prevalenza di micro-posizioni come causa principale. La fee media per posizione scende, coerentemente con il minore notional.

## Guadagno lordo e assorbimento dei costi

| Run | Lordo medio/posizione | Fee media/posizione | Netto medio/posizione | Lordo totale | Fee/lordo totale |
| --- | --- | --- | --- | --- | --- |
| Hawk #2 | 17,02 | 2,67 | 14,35 | 1.293,74 | 15,7% |
| Hawk #5 | 2,02 | 2,47 | -0,45 | 226,28 | 122,4% |
| Bull #1 | 50,05 | 4,72 | 45,34 | 850,91 | 9,4% |
| Bull #4 | 1,52 | 4,29 | -2,78 | 116,96 | 282,4% |

Lordo totale = somma dei P&L lordi positivi e negativi, prima di fee e funding registrati. Nei fill PAPER lo slippage è già incorporato. Lordo medio significa media di tutti gli esiti, non media dei soli vincitori.

Anche i risultati lordi positivi medi si riducono: Hawk 47,55→37,80; Bull 84,58→63,67. Le perdite lorde medie sono Hawk 29,79→21,13 e Bull 32,80→33,99. Il profit factor lordo passa da 2,45→1,16 Hawk e da 6,19→1,07 Bull. Il vantaggio prima delle fee è diventato molto sottile, pur restando leggermente positivo sulle run intere.

Fee/notional complessivo di ingresso: circa 11,95 / 12,00 / 11,92 / 12,00 punti base per andata e ritorno. Configurazione PAPER uguale: 6 punti base per lato; differenze minime del rapporto dovute anche al notional di uscita. Nessuna evidenza di tariffa sproporzionata o aumentata. Le parziali non dimostrano da sole una duplicazione delle fee: la commissione è proporzionale alla quantità, e il rapporto fee/notional resta comparabile.

Il rapporto fee/lordo totale oltre 100% è una relazione contabile, non una quota causale identificata o una simulazione senza commissioni. Funding totale: 0,09 / 0,11 / 0,00 / 0,73, rispettivamente; arrotondamenti spiegano differenze al centesimo.

## Posizioni positive lorde diventate negative nette

| Run | Posizioni lordo>0 e netto<0 | Realizzi con lo stesso fenomeno |
| --- | --- | --- |
| Hawk #2 | 0/76 | 0/76 |
| Hawk #5 | 2/112 | 2/131 |
| Bull #1 | 0/17 | 0/30 |
| Bull #4 | 0/77 | 0/89 |

I due casi Hawk #5 sono:
- ATOM, id64: lordo +2,3464; fee 2,9986; funding 0; netto -0,6522.
- XAU, id75: lordo +0,1711; fee 2,3999; funding 0; netto -2,2288.

Entrambi sono effettivamente ribaltati dalle sole fee; somma netta -2,8810. Il ramo finale è quello decisionale etichettato “chiusura Claude”, ma la fonte effettiva di quell'azione non è identificabile: non attribuirli al modello sulla sola label. I due casi non spiegano la perdita complessiva di Hawk #5 e non rappresentano un risultato controfattuale se si fosse atteso. Nessun caso analogo in Bull #4: lì il costo aggregato elimina il piccolo saldo lordo del complesso di vincite e perdite.

## Conclusione e proposta, NON implementata

Dimostrato: costi unitari simili, size solo moderatamente ridotta, forte aumento della frequenza Bull e crollo del lordo medio per posizione. Non dimostrato: quale singola modifica di strategia o condizione di mercato abbia causato il crollo dell'edge. Non basta evitare le due piccole chiusure, aumentare size/leva o alzare una soglia di score senza calibrazione.

Proposta concreta da sottoporre a OK: filtro di ingresso sul valore atteso NETTO, prima da misurare in ombra PAPER. Ammettere un candidato solo se:

p × guadagno lordo atteso − (1−p) × perdita lorda attesa − costi attesi > 0.

La probabilità p deve essere stimata e verificata su esiti comparabili, separando profilo/direzione/contesto, non derivata leggendo uno score70 come 70% di successo. Costi = fee ingresso+uscita, slippage e funding attesi; 6+6bp fee e 2+2bp slippage sono circa 0,16% del notional prima del funding nel modello corrente. Se guadagni/perdite stimati già incorporano lo slippage dei fill, non sottrarlo due volte. Parametri e affidabilità statistica della stima restano da validare; non dichiaro questo filtro profittevole prima della prova.

Per le sole prese di profitto discrezionali, mostrare e verificare il netto stimato dopo costi, invece di considerare sufficiente un lordo positivo. Nessun blocco a SL, invalidazione del setup, rischio o chiusure protettive; non trattenere una posizione perdente solo per “recuperare le fee”. Nessun taglio meccanico del numero di trade: mantenere quelli con edge netto verificato.

Tutto resta una proposta; nessuna implementazione o modifica operativa senza nuovo OK esplicito dell'utente.
