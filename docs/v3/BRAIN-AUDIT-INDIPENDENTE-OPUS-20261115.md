# Brain V3 — audit indipendente (15 novembre 2026, sera)

Solo analisi. Nessun deploy, merge, riavvio, ordine o modifica di rischio, stop, leva o filtri.
Etichette: **VERIFICATO** (misurato qui su codice o candele reali), **RIPORTATO** (dashboard o audit VPS forniti
dall'operatore, non riestratti), **IPOTESI**, **PROPOSTA** (non validata).

**Limite principale:** non ho accesso al journal. I dati di Brain sono quelli RIPORTATI (dashboard 15/11 20:33 e
`BRAIN-VPS-AUDIT-READOUT-20261115.md`). Tutti i confronti sono fatti contro ingressi di controllo costruiti su
candele reali Bitget (1m e 15m) con la geometria di Brain, non appaiati trade per trade: per l'appaiamento servono i
timestamp delle 31 operazioni.

Script riproducibili in `research/brain_audit_opus/` (candele pubbliche, nessun dato VPS):
`geometry.py`, `atr_stop.py`, `robust_oct.py`, `entry_timing.py`, `frrd_check.py`, `relative_weakness.py`.

---

## A. Diagnosi indipendente — i tre problemi principali

### 1. Non c'è prova che DeepSeek scelga meglio del caso; il profitto viene dalla discesa del mercato

- RIPORTATO: 29 SHORT, 16 vincenti (55%), +561,56 USDT, cioè circa **+19 USDT per operazione**.
- VERIFICATO: nella stessa finestra (13/11 15:00 → 15/11 19:00 UTC, esclusa la pausa) uno SHORT aperto **a ogni
  ora su ognuno degli 8 simboli**, con la stessa geometria di Brain (stop 0,74%, target 2R, 24 h, costi, stop eseguito
  al minuto successivo come osservato il 13/11): **58% vincenti, +0,53R, circa +32 USDT per operazione**.
  Probabilità che un selettore senza abilità faccia 16/29 o peggio: 45%. Brain non si distingue dal caso.
- VERIFICATO: in un mese ribassista **ordinario** (6/10 → 10/11, prezzi −12%/−35%), gli stessi SHORT casuali
  chiudono a **+0,03R** (±0,04) per operazione: zero. La finestra di Brain contiene un crollo di −6%/−12% in due giorni.
- Conclusione: il risultato positivo è compatibile con "qualunque SHORT durante un crollo". Non dimostra abilità e non
  dice nulla su come andrà quando il mercato smette di crollare.

### 2. La geometria del rischio decide l'esito più del segnale

Il profilo installato impone leva ≥20× e perdita ≤21,43% del margine: **stop ≤ 0,91% dal prezzo** (VERIFICATO, `risk.py`).
La dimensione è decisa dal tetto di margine (400 USDT × 20 = ~8.000 di nozionale), non dal rischio. Ne segue:

- Riconciliazione (VERIFICATO sui numeri riportati): 8.000 × 0,74% = 59 + commissioni ~9,5 + slippage ~3 + ritardo
  dello stop ~8 = **~80 USDT**, esattamente la perdita media osservata (−1.205,07 / 15 = −80,3). Vincita media 101,8.
  Pareggio al **44%** di vincenti; Brain è al 51,6%.
- Lo stop è uguale in percentuale per tutti i simboli e in tutti i regimi, ma la volatilità no: ATR a 15 minuti nella
  finestra **BTC 55 bp, BNB 55, ETH 72, SOL/XRP/DOGE/LINK/ADA 76–80** (VERIFICATO). Su ETH lo stop vale ~1 ATR, su BTC ~1,35.
- **EXPANSION** nel classificatore di Brain significa solo "ATR 15m nel 20% più alto degli ultimi 30 giorni"
  (VERIFICATO, `features/regime.py`): è la definizione stessa di "stop più vicino al rumore". Non significa rimbalzo.
- IPOTESI forte (verificabile con l'osservatorio delle proposte, ramo `work/brain-reject-observability-20261115`):
  dei 199 rifiuti del rischio, molti sono proposte con stop > 0,91%. Il prompt non comunica il limite. Il rischio
  approva quindi **solo le proposte con lo stop più stretto**, che in alta volatilità sono le peggiori.

### 3. Il controllo post-AI scarta le approvazioni in modo quasi casuale

VERIFICATO con il codice vero (`post_ai_guard.py` + `risk.py`, passi di quantità reali di Bitget):
- il prezzo d'ingresso è la chiusura dell'ultimo minuto. Se la risposta di DeepSeek arriva dopo il cambio di minuto,
  il controllo rifà la quotazione e **rifiuta se la quantità scende anche di un passo** (`risk_changed_after_ai`)
  oppure se lo stop, ormai al limite di 0,91%, lo supera (`risk_rejected_after_ai`);
- con la volatilità di 1 minuto reale, dopo un cambio di minuto passa solo il **14–59%** delle approvazioni secondo il
  simbolo; su XRP, DOGE e ADA quasi soltanto quelle in cui il prezzo è **sceso** durante l'attesa (SHORT più tardivi).
- RIPORTATO: 50 approvate, 30 aperte. Coerente.
- Non è un difetto di sicurezza (fallisce in modo chiuso), ma è un filtro casuale che decide **quali** SHORT entrano.

Altro, minore: lo stop viene eseguito all'apertura del minuto successivo al tocco (osservato il 13/11): costa in media
**~0,1R per stop**, cioè circa 8 USDT ogni stop (VERIFICATO in simulazione). Va ricontrollato dopo la patch P0.

---

## B. ETH e BNB

| | ETH | BNB | BTC |
|---|---|---|---|
| RIPORTATO Brain | 1/5, −292,80 | 2/5, −97,79 | 7/10, +515,64 |
| VERIFICATO: SHORT casuali stessa finestra, stop 0,74% | 54%, +0,42R | **69%, +0,87R** | 70%, +0,89R |
| VERIFICATO: stessi, stop 2×ATR15m e rischio fisso | 68%, +0,90R | 72%, +1,04R | 69%, +0,93R |
| ATR 15m nella finestra | 72 bp | 55 bp | 55 bp |

- **ETH:** il divario con BTC si riproduce anche con ingressi casuali e quasi sparisce quando lo stop è proporzionale
  alla volatilità. È geometria (stop dentro il rumore di ETH), non "ETH inadatto". 1/5 contro 7/10: p = 0,12 (test
  esatto), non significativo. Inoltre ETH è sceso meno di SOL, DOGE e ADA nella finestra (−6,7% contro −11/−12%).
- **BNB:** ha la stessa volatilità di BTC e gli SHORT casuali su BNB sono andati bene (69%). La volatilità **non**
  spiega le perdite di BNB: con 5 operazioni è varianza o tempismo, da verificare con i timestamp.
- Se l'unica vincita ETH vale quanto una vincita media (~+102), le perdite ETH valgono circa −99 USDT l'una contro −80 di media: sono compatibili con stop eseguiti peggio
  (ritardo di un minuto su un simbolo più veloce). IPOTESI, verificabile dal journal (`exit_price` vs `stop_price`).
- Nessuna lista nera: i dati non la giustificano e su 5 operazioni sarebbe adattamento al rumore.

## C. Qualità degli SHORT

Brain sta beneficiando della discesa, non c'è prova di un vantaggio proprio (punto A.1).

VERIFICATO sui SHORT casuali con la geometria di Brain, nella finestra di Brain:

| Regime all'ingresso (classificatore vero) | Vincenti | R medio |
|---|---|---|
| EXPANSION (n=241) | 50% | +0,28 |
| TREND_DOWN (n=67) | 75% | +1,05 |
| RANGE (n=50) | 62% | +0,65 |

- Il pattern RIPORTATO (EXPANSION 31%, TREND_DOWN 83%, RANGE 100%) **c'è anche negli ingressi casuali**. È strutturale,
  non un errore di DeepSeek. Brain in EXPANSION (5/16) è sotto il caso (50%), ma non significativamente (p = 0,10).
- Stop/ATR all'ingresso: stop < 0,95 ATR → 52% vincenti; stop ≥ 1,34 ATR → 75% (stessa finestra).
- Ingressi dopo la discesa contro dopo il rimbalzo: nel crollo vendere dopo un'ora di rialzo è andato meglio (+1,27R
  contro +0,70R dopo un'ora di calo); in ottobre **nessuna differenza** (+0,02 contro +0,01). Non è una regola.
- Forza relativa contro BTC (SHORT sul più debole): nessuna differenza in nessuno dei due periodi.
- LONG: i 2 LONG di Brain sono persi, ma nella finestra l'87% dei LONG casuali con la stessa geometria perdeva. Evitare i LONG era corretto.

**Errori nel ragionamento finora:**
1. "Brain sa guadagnare nei ribassi": nella stessa finestra gli SHORT casuali hanno fatto di più.
2. "EXPANSION è un rimbalzo": è volatilità alta.
3. "ETH perde sistematicamente": 5 operazioni, p = 0,12, spiegato dalla volatilità.
4. "20 approvazioni non aperte potrebbero essere controlli utili": sono in gran parte rumore del minuto.
5. Il problema non è un indicatore mancante: nessuna delle condizioni provate (regime, rendimento recente, posizione
   nel range, forza relativa, FRRD) separa gli SHORT buoni dai cattivi in un mese ordinario.

## D. FRRD

VERIFICATO: test del ramo 24/24 superati; il prototipo **non modificato** applicato a ogni ingresso orario:

| Stato FRRD | Ottobre (n, R medio SHORT) | Finestra di Brain |
|---|---|---|
| INCERTO | 74%, −0,00 | 78%, +0,83 |
| RIMBALZO_LOCALE | 21%, −0,05 (±0,08) | 20%, **+1,77, 98% vincenti** |
| CONTINUAZIONE_SHORT | 3%, +0,19 (±0,23) | 2%, +0,63 |
| INVERSIONE_CANDIDATA | 2%, +0,21 (±0,24) | — |

- **Funziona:** codice causale, nessun lookahead, prudente sui dati mancanti, ben testato.
- **Non funziona:** non distingue gli SHORT buoni dai cattivi in ottobre; nel crollo gli SHORT aperti **sul rimbalzo**
  sono stati i migliori in assoluto. Usato come veto avrebbe tolto le operazioni migliori. È INCERTO 3 volte su 4.
- **Velocità:** due chiusure 15m più un recupero di 0,85 ATR significano 30 minuti e circa 50–70 bp. Lo stop di Brain
  è a 74 bp: quando FRRD segnala il rimbalzo, lo SHORT aperto prima è quasi sempre già fermato. Troppo lento per
  proteggere uno scalp a 20×, e rifarlo su 1m/5m non risolve il problema di fondo: il rimbalzo non è il nemico.
- **Cosa cambierei:** nessun veto. Lo terrei solo come caratteristica registrata nel registro controfattuale (proposta E1).

## E. Soluzioni (almeno tre, realmente diverse)

### E1. Registro controfattuale delle decisioni ("misuratore di abilità")
- **Principio:** per **ogni** decisione di Brain (anche NO_TRADE e rifiuti), calcolare in ombra l'esito di SHORT e
  LONG con la stessa geometria e un controllo casuale appaiato (stesso minuto, altro simbolo). Brain impara da centinaia
  di esiti al giorno invece che dalle sue 30 operazioni, e si sa finalmente se una scelta batte il caso.
- **Dati:** journal, osservatorio delle proposte (già pronto), candele 1m pubbliche.
- **Benefici:** misura l'abilità per lato, regime e simbolo; valuta qualunque idea futura (FRRD, filtri, prompt) senza
  rischiare capitale. **Rischi:** nessuno sul trading. **Complessità:** bassa-media. **Frequenza:** invariata.
- **Validazione:** test sequenziale della differenza Brain − casuale; soglia fissata prima.

### E2. Generatore deterministico + DeepSeek come classificatore
- **Principio:** a ogni ciclo un generatore costruisce i candidati per gli 8 simboli × 2 lati, con stop e dimensione
  già decisi (volatilità e rischio). DeepSeek non sceglie stop e leva: **ordina** i candidati e dice prendi/scarta con
  motivi strutturati. Si aprono i primi k sopra una soglia.
- **Benefici:** elimina i rifiuti per stop incompatibile e la lotteria del controllo post-AI; l'abilità del modello
  diventa misurabile come correlazione fra ordine e esito. **Rischi:** se il modello non ha abilità, il risultato
  diventa quello del generatore (circa zero in un mese ordinario). Ed è proprio l'informazione che serve.
- **Complessità:** media. **Frequenza:** controllabile (k per ciclo), non dipende dal rumore.
- **Validazione:** ombra in parallelo; ordine di DeepSeek contro ordine casuale sugli stessi candidati.

### E3. Rischio in USDT, stop dalla volatilità, leva come conseguenza
- **Principio:** stop ≥ k × ATR (o fuori dalla struttura), perdita pianificata fissa (es. 72 USDT, la stessa di oggi),
  nozionale = rischio / stop. La leva risulta 10–20× invece di essere imposta. La perdita massima in USDT **non cambia**.
- **VERIFICATO nella finestra di Brain:** con stop 2×ATR15m, ETH, BNB e BTC danno lo stesso risultato
  (+0,90/+1,04/+0,93R): il divario fra simboli sparisce.
- **VERIFICATO in ottobre:** stop più larghi **non** migliorano il profitto (1,5×ATR −0,20R, 2×ATR −0,06R, fisso 0,74%
  +0,03R). Questa proposta toglie rumore e dispersione, **non crea vantaggio**.
- **Richiede:** cambiare leva minima 20× e il limite del 21,43% sul margine: è una decisione tua. In più due correzioni
  tecniche indipendenti: controllo post-AI che riduce la quantità invece di rifiutare (mai aumentarla), e stop eseguito
  al tocco. **Frequenza:** aumenta (meno rifiuti), con lo stesso rischio per operazione.

### E4. Meta-etichettatura calibrata (dopo E1)
- **Principio:** un modello statistico piccolo e calibrato (regressione logistica) stima, con i dati del registro E1,
  la probabilità di target prima dello stop per ogni candidato; si apre solo quando la probabilità supera il pareggio
  con margine. DeepSeek resta la fonte delle idee; il modello statistico misura e filtra.
- **Rischi:** adattamento al rumore. Si evita con validazione su periodi successivi e poche variabili fissate prima.
- **Frequenza:** riduce le operazioni solo dove la probabilità stimata è sotto il pareggio; quantificabile prima.

## F. Architettura preferita

**Misurare prima, decidere poi: E1 subito, poi E2 + E3, E4 solo se E1 mostra qualcosa da imparare.**

Un LLM che ogni ora inventa ingresso, stop e leva da un'istantanea di indicatori, filtrato da un rischio che non
conosce e da un controllo che scarta a caso, non può migliorare in modo misurabile: nessuno sa quale parte del
risultato è merito suo. Separerei le responsabilità:
- il **generatore** decide la geometria;
- il **rischio** decide la dimensione in USDT;
- **DeepSeek** fa ciò in cui un modello linguistico può aggiungere qualcosa, cioè ordinare e scartare con contesto;
- il **registro controfattuale** dice ogni giorno se quell'ordine batte il caso.

## G. Piano sperimentale (nessun impatto sull'operativo)

1. Attivare in PAPER l'osservatorio delle proposte (solo registrazione), previa autorizzazione: verifica l'ipotesi
   A.2 sui 199 rifiuti.
2. Esportare in sola lettura i timestamp delle 31 operazioni: confronto **appaiato** (stesso simbolo, stesso minuto,
   stessa geometria) Brain contro casuale; costo reale del ritardo dello stop.
3. Registro controfattuale E1 offline sul journal esistente, poi in ombra continua. Criterio fissato prima: almeno 300
   decisioni; Brain − casuale > 0 con intervallo che esclude lo zero su due finestre successive.
4. E2 ed E3 in ombra su candele reali, con le stesse decisioni. Confronto su almeno un mese **non** di crollo.
5. Nessuna lista nera e nessun veto finché 3–4 non danno risultati su un secondo campione.

## H. Conclusione

**Qual è il cambiamento più importante per smettere di perdere SHORT nei rimbalzi senza perdere i guadagni nei ribassi?**

La domanda parte da una premessa che i dati non confermano: i rimbalzi non sono il problema. Nel crollo gli SHORT
aperti sui rimbalzi sono stati i migliori. Le perdite vengono da uno stop fisso dello 0,74%, imposto dalla leva
minima 20×, che quando la volatilità sale finisce dentro il rumore normale del prezzo, qualunque cosa decida DeepSeek.

Il cambiamento più importante è quindi **togliere a DeepSeek e alla leva la scelta dello stop**: stop deciso dalla
volatilità, perdita fissa in USDT, leva come conseguenza (E3), dentro un sistema che misura ogni decisione contro il
caso (E1). Togliere lo stop dal rumore non crea profitto da solo (ottobre lo mostra); rende però i risultati
indipendenti dal simbolo e dal regime di volatilità, e permette finalmente di vedere se DeepSeek sceglie bene.

Nessuna promessa economica: tutto quanto sopra va confermato in ombra su un periodo diverso dal crollo dell'11–15/11.
