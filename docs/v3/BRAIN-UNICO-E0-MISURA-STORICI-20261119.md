# E0: misurare sugli storici se reingressi e aperture dopo un guadagno peggiorano il risultato (19/11/2026)

**Natura:** proposta di misura e strumento offline (`ops/brain-unico/guardian/e0_measure.py`), collaudato **solo su dati sintetici**. Nessun dato reale letto, nessuna esecuzione autorizzata. L'esecuzione reale richiede il consenso alle copie (Fase 0) e la loro attestazione con ancora esterna (PR #118, `phase0_attestation_v2`).

## 1. Le due domande e che cosa decidono

| | Domanda (contrasto primario, pre-registrato) | Se la risposta è "peggiore" | Se "nessuna evidenza" |
|---|---|---|---|
| **H1** | I trade aperti quando la sessione ha già realizzato ≥ +4R rendono meno di quelli aperti con sessione in [−1R, +1R)? | Il Guardian (floor/soglia) **aumenta il rendimento atteso**: priorità al suo test in replay | Il Guardian si giustifica solo come **riduzione della varianza e del giveback**. Si tiene con parametri prudenti e non lo si presenta come fonte di rendimento |
| **H2** | I reingressi di indice ≥ 3 sulla stessa tesi rendono meno dei primi ingressi? | L'**anti-reingresso** è prioritario; il limite 2 (o 3) va testato per primo | Niente limite numerico rigido; resta solo la regola della nuova conferma, da verificare in shadow |

Tutto il resto è **esplorativo** e non può da solo cambiare una decisione:
- fasce intermedie di PnL di sessione e indice 2;
- reingressi dopo un TP o dopo uno SL;
- due o più posizioni aperte contemporaneamente;
- giveback dal picco.

## 2. Percorso, con chi fa cosa

1. **Copie** (consenso separato): `full` del bundle sigillato sulle fonti Falco, Toro, Brain storico e Arena. L'operatore registra `run_id` e lo SHA-256 di `public/summary.json` (solo numeri, per esempio nella Issue #113): questa è l'**ancora esterna**.
2. **Copia leggibile** (consenso separato): i file `private/` della run sono di root (0600). Serve un passaggio autorizzato che li renda leggibili all'utente del laboratorio senza modificarli (il loro SHA-256 deve restare quello attestato).
3. **Attestazione**: `attestation.py RUN_DIR --out att.json`; si confronta lo SHA stampato con l'ancora registrata.
4. **Dataset**: `builder.py --spec … --anchors ancore.json`. Le righe sono tutte conservate; E0 usa i trade **eseguiti e chiusi** delle fonti `attested`.
5. **E0**: `e0_measure.py --examples …/examples.jsonl --out <file nuovo fuori dal repo>`. Il rapporto contiene solo numeri: niente simboli, nomi di flusso, prezzi o saldi.
6. **Revisione**: si pubblicano i verdetti e i conteggi (pubblici) per la revisione di ChatGPT; il file completo resta privato.

## 3. Definizioni (fissate prima di vedere i dati)

| Termine | Definizione | Limite dichiarato |
|---|---|---|
| Trade usabile | `record_kind=executed`, `status=closed`, PnL netto noto, non sintetico, non duplicato, fonte attestata con ancora esterna | Le posizioni ancora aperte (censurate) restano escluse |
| r | `net_r` registrato; altrimenti PnL netto diviso per la **mediana delle perdite** del flusso (`r_proxy`, contato nel rapporto) | Il proxy non è il rischio pianificato; si riporta quanti trade lo usano |
| Flusso | `source_system` + `source_run` (es. una run Arena di un provider, un run di Falco) | Configurazioni di rischio diverse tra flussi: si usa l'effetto fisso di flusso |
| Sessione | Giorno locale **Europe/Rome dalle 08:00** (ora legale gestita, sessioni di 23 o 25 ore); sensibilità con 00:00 | — |
| PnL di sessione prima dell'apertura | Somma degli r dei trade dello stesso flusso **chiusi prima** dell'apertura e chiusi nella stessa sessione | **Solo realizzato**: gli storici non hanno l'equity mark-to-market per ciclo. Il PnL aperto in quel momento non è visibile |
| Tesi (proxy) | Stesso flusso, simbolo e lato; apertura entro 12 ore dall'ingresso precedente della tesi; un trade del lato opposto sullo stesso simbolo la chiude | Gli storici non hanno `thesis_id`. È un'approssimazione meccanica, con sensibilità a 6 e 24 ore |
| Esito precedente | Esito dell'ultimo trade della tesi **già chiuso** all'apertura (TP = r > 0) | — |

## 4. Metodo statistico

- **Effetto fisso di flusso**: r meno la media del flusso. Senza questo, un bot migliore (molte sessioni sopra +4R) creerebbe un effetto spurio; c'è un test dedicato.
- **Differenza fra medie** (gruppo A − gruppo B), con intervallo al 95% da **bootstrap a blocchi di sessione** dentro ogni flusso: i trade della stessa sessione non sono indipendenti.
- **Correzione di Holm** sui due contrasti primari.
- **Campione minimo**: ogni gruppo deve avere almeno 30 trade e 10 sessioni, altrimenti il verdetto è `inconclusive_small_sample`. Non si abbassa la soglia dopo aver visto i dati.
- **Verdetti**:
  - `worse` / `better`: l'intervallo al 95% esclude lo zero e il p corretto è < 0,05;
  - `no_evidence`: **non** significa "uguale", ma che i dati non bastano a dirlo;
  - `inconclusive_small_sample`: campione sotto la soglia minima.
- **Sensibilità**, riportate ma non decisive: senza chiusure manuali (calcolata automaticamente); sessione alle 00:00; finestra di tesi a 6 e 24 ore; armamento a 2R e 6R; per singola fonte. Se una sensibilità rovescia il verdetto primario, il verdetto si declassa a "fragile" nella revisione.

## 5. Confondenti e limiti, da leggere prima dei risultati

1. **Regime**: i giorni di trend producono sia sessioni in forte profitto sia reingressi. Un H1 o H2 "peggiore" può riflettere la fine del trend più che il comportamento del bot. Per distinguerli serve una stratificazione per regime (rendimento giornaliero di BTC dalle candele attestate), da aggiungere quando le candele saranno disponibili.
2. **Solo PnL realizzato**: un trade aperto con +4R realizzati ma −3R non realizzati è classificato come "dopo il guadagno". Il floor del Guardian userà l'equity mark-to-market, quindi E0 risponde a una domanda vicina, non identica.
3. **Bot e periodi diversi**: Falco e Toro (mesi, regole classiche), Brain storico (epoche), Arena (tre run da circa tre giorni). L'Arena da sola quasi certamente non raggiunge il campione minimo.
4. **Chiusure manuali**: alterano gli esiti; da qui la sensibilità senza di esse.
5. **Nessuna ottimizzazione su questi dati**: E0 risponde sì/no. Le soglie (armamento, giveback, limite reingressi) si scelgono nel replay E2 sulla **prima metà cronologica** e si valutano sulla seconda.

## 6. Dopo E0

- **E2, replay sovrapposto**: si applicano le politiche A, B, D, E, F e le regole di reingresso alle stesse sequenze di trade. Si scelgono le soglie sulla prima metà, si valutano sulla seconda, con bootstrap a blocchi.
  - Limiti: effetti di percorso, e la posizione saltata che avrebbe liberato margine.
  - Con le candele attestate si aggiunge la ricostruzione dell'equity mark-to-market e lo stress sulle posizioni simultanee (sezione H della proposta).
- **E4, shadow**: il Guardian registra cosa avrebbe bloccato, insieme ai segnali leggeri di LOCKED (`screened_signal`), per misurare il costo opportunità.

## 7. Verifica dello strumento (sintetica)

`python3 -I ops/brain-unico/guardian/test_e0_measure.py`: **18 test PASS**, stabili su più esecuzioni, in circa 3,5 secondi. Coprono:
- **Rilevamento**: decadimento dopo il profitto "piantato" → `worse`; nessun decadimento → `no_evidence`; decadimento sui reingressi → `worse`; campione piccolo → `inconclusive`; effetto fisso che elimina l'effetto spurio tra flussi.
- **Causalità**: le chiusure successive all'apertura non contano; nessun riporto fra sessioni; flussi mai mescolati.
- **Calendario**: confini di sessione alle 08:00 Rome in inverno, estate e nella notte del cambio d'ora; alternativa a mezzanotte.
- **Tesi**: indice, finestra, lato opposto, esito precedente con posizioni ancora aperte.
- **Selezione e calcolo**: righe non attestate, duplicate, sintetiche, aperte o con PnL ignoto escluse e contate; proxy di R; Holm.
- **Rapporto e output**: determinismo; rapporto senza simboli né nomi; output nuovo 0600, mai sovrascritto, mai dentro git.

**Mutazioni:** reintroducendo ciascuno di 23 difetti in una copia di prova, **23 su 23** vengono rilevati. Tra i difetti: look-ahead, sessione, ora o fuso ignorati, nessun effetto fisso, non attestati o duplicati ammessi, PnL ignoto = 0, campione minimo o Holm assenti, verdetto senza intervallo, finestra o lato opposto ignorati, gruppi primari diversi da quelli pre-registrati, output sovrascritto o dentro git.
