# Step 6 — proposta per review Claude

Stato: codice di ricerca, piano **draft**. Nessun trigger, merge o esecuzione VPS.
I riferimenti nel diario sono stati letti; il ramo sorgente effettivo era
`work/director-chatgpt` a `11a9c62`, successivo al riferimento `9255093` del prompt.

## Domanda e perimetro

Una sola ipotesi primaria per bot: un overlay di uscita migliora il R netto medio
dei trade puliti rispetto alle uscite registrate? Non cambia ingressi, punteggi,
soglie o configurazioni dei bot. Non misura l'effetto economico della stagionalità:
il test 5 descrive i punteggi; non ricostruisce la confidenza finale di Claude né
le aperture controfattuali. Non simula slot liberati, rientri, equity, drawdown del
conto o trader AI. Nessuna conclusione di redditività del bot è derivabile da solo.

## Candidato proposto, da approvare prima della misura

1. Usa barre 15m interamente successive all'ingresso. Quando una **chiusura**
   raggiunge almeno +1,5R di prezzo, decide di chiudere il 50%.
2. Esegue all'apertura della barra successiva con slippage avverso. Non presume
   un ordine limite eseguito esattamente a +1,5R.
3. Dopo l'esecuzione, se una barra chiude con liquidazione del residuo non
   positiva (commissioni e funding inclusi), chiude il residuo alla prossima apertura.
   È una regola a barra chiusa: gap, costi e ritardo possono produrre una perdita.
4. L'uscita baseline è un confine terminale. Nessuna azione alternativa può
   essere eseguita nella barra dello stop/TP baseline o dopo quel confine.
   Se il residuo non esce prima, gli viene attribuita metà della baseline.
   Le decisioni discrezionali baseline restano esogene: questo limita il controfattuale.

È una specifica più prudente e diversa dalla precedente variante intrabar al
livello esatto +1,5R. Non si possono confrontare i due report come se fossero la
stessa regola. Questa scelta è una **proposta**, non una strategia approvata.

## Dati, riconciliazione e esclusioni

- Legge `/data/{hawk,bull}/learning_log.jsonl`; non usa lo stato finale come
  sostituto della storia. Chiave esatta `(bot, run_no, id)`.
- JSON rigoroso: newline finale, niente righe vuote, duplicate key o NaN/Infinity;
  limiti di dimensione. Le eccezioni non stampano righe, simboli o percorsi.
- Esige un open e un close finale, una gamba, nessun DCA, split o parziale;
  esclude liquidazioni, identità/orari incoerenti e versioni non revisionate.
- Riconcilia gross, fee e funding **ricalcolati** e netto con tolleranza contabile
  0,05 (unità interna, mai stampata). Verifica anche rischio iniziale e net_r.
  Usa `open.r_dist` non arrotondato; quello nel close è arrotondato a 5 decimali.
- Modello PAPER: fee 6 bp per lato, slippage 2 bp, funding 1 bp/8h solo long.
  Non è una misura di fill o funding reali. La fee d'ingresso è suddivisa fra le
  due metà una sola volta; funding fino all'uscita di ciascuna quantità.
- Confronti appaiati sugli stessi trade: slippage uscita 2/4/8 bp e ritardo
  aggiuntivo di una barra (2 e 8 bp). Entrata storica fissa. Anche la baseline
  viene ricalcolata con il medesimo slippage di uscita dello scenario.
- Una lacuna OHLC esclude il trade con conteggio esplicito; mai trasformata in HOLD.
  È richiesta una serie completa dall'ingresso al bucket di uscita, incluso
  quest'ultimo interamente chiuso. Questa scelta esclude prudentemente uscite recenti.

## Archivio OHLC offline: prerequisito ancora da predisporre

Il vecchio `pm_exec_replay.py` scarica candele via rete. Non è riusato: sarebbe
incompatibile con `--network none`. Il nuovo runner richiede un archivio locale
separato `/opt/superbot-step6-market/`, montato in sola lettura. **Non è stato
verificato che esista sul VPS.** Nessun collector è installato o eseguito qui.
L'acquisizione pubblica e il suo schema vanno revisionati separatamente prima
dell'esecuzione; i dati grezzi non vanno nel repository né negli artifact.

`candles.jsonl`: una riga per `(symbol, open_ms)`, symbol identico a quello del log.
Campi: `schema=1`, `symbol`, `open_ms`, `open`, `high`, `low`, `close`.
Timestamp di apertura UTC in millisecondi, multiplo di 900000; solo barre chiuse.
Duplicati, prezzi non finiti e ordine OHLC invalido falliscono.

`manifest.json`: `schema=1`, `source="bitget_public_15m"`,
`timestamp_semantics="open_ms"`, `interval_ms=900000`, `asof_ms` intero UTC,
`bars_sha256` completo. Gli hash attestano i byte, non l'autenticità della fonte.
Ogni file ha un tetto di 16 MiB; se il campione cresce oltre il tetto si deve
revisionare una lettura streaming o uno snapshot selezionato, non troncare input.

## Protocollo fuori campione proposto

`deploy/step6-plan.json` contiene status draft e data nulla: lo script lo rifiuta.
Dopo review, approvazione e congelamento del codice, fissare una data futura
`oos_start_utc` e `status=approved`. La data deve essere successiva al timestamp
del **commit congelato completo** (script + piano) passato dal workflow.
Un cambiamento successivo richiede un nuovo commit e una nuova data futura.
Il timestamp Git non è un'autorità temporale indipendente: commit e decisione
vanno registrati nel diario prima del periodo, senza retrodatazioni.

- Trade iniziati e finiti prima del confine: storico esplorativo, mai OOS.
- Trade aperti prima e chiusi dopo: esclusi dal confronto (purge).
- Trade aperti dopo: campione prospettico; sola baseline `4aabeb8`, da confermare
  in review. Una diversa versione negli eventi successivi invalida il gate;
  non viene nascosta eliminando semplicemente quei trade.
- Proposta per bot: almeno 42 giorni trascorsi, 100 trade puliti chiusi e 50
  interventi simulati. Non sono garanzie di potenza statistica o indipendenza.
- Delta medio minimo proposto +0,10R; intervallo bootstrap per episodio con
  limite inferiore >0; segno positivo in entrambe le metà temporali, togliendo
  i tre delta migliori, e in tutti gli scenari di costo/ritardo.
- Episodi: si raggruppano trade dello stesso giorno e intervalli sovrapposti,
  anche fra giorni. IC omesso con meno di 5 episodi. Può risultare un unico
  episodio: non si forza una falsa precisione. La dipendenza seriale residua
  del mercato resta un limite.
- IC 97,5% per ciascuno dei due confronti primari (Bonferroni su Hawk/Bull).
  Sensibilità non usate per scegliere a posteriori la variante vincente.
- Output del gate: pending / invalidated / not_supported /
  supports_further_shadow_review. **Mai promozione automatica o autorizzazione deploy.**

Le soglie sono da approvare con Claude e Alessandro, prima di osservare i nuovi esiti.
Un cambio di strategia o baseline chiude questa coorte: nessun risultato prospettico
positivo vale per una configurazione diversa. Le esclusioni limitano la conclusione
ai trade puliti e possono introdurre distorsione di selezione.

## Workflow e review richiesta

`desk-step6-economic.yml` parte solo da `deploy/desk-step6.trigger` su rule-pool;
**il trigger non è incluso**. Il codice sul ramo di lavoro non ha accesso al VPS.
Un futuro trigger deve indicare `sha=<40 caratteri>` già in rule-pool.
Il workflow esegue prima test e py_compile sul commit fissato.

Sul VPS crea solo un checkout temporaneo usa-e-getta; nessun reset del checkout
dei bot. Controlla PAPER dai container, usa l'immagine Hawk già presente fissata
all'ID (non un tag mutabile), rete disabilitata, filesystem read-only,
capability ridotte, mount codice/dati/mercato ro, RAM/CPU/pid e timeout limitati.
Il trap confronta ID/immagine/StartedAt di Hawk/Bull anche se la misura fallisce;
non stampa quei valori. Nessun docker stop/restart, build, ordine o scrittura
nei dati. Le snapshot dei file vengono rilette e confrontate prima dell'output;
un append contemporaneo fallisce e richiede una nuova misura.

Output solo aggregati in R, conteggi e hash, salvato come artifact JSON completo
con retention 30 giorni. Nessun importo, simbolo o riga grezza. Il workflow fallisce
se un bot non ha trade appaiati; non può dare un risultato verde senza misura.
Il gate OOS può restare pending mentre lo storico è calcolabile.

Per Claude: controllare contabilità delle due metà, orari next-open/ritardo,
confine stop/TP, rischio non arrotondato, riconciliazione indipendente, esclusioni,
provenienza OHLC, congelamento temporale, invalidazione versioni, bootstrap e
privacy artifact. Poi decidere se questa specifica è il primo esperimento utile.
Nessun merge o esecuzione prima dell'OK richiesto dall'utente.

## Revisione indipendente del 22/10/2026 — approvazione ancora sospesa

Oggetto verificato: commit fe50c2ff. Il rapporto completo e la matrice delle
revisioni sono nel ramo diario, file
`diario/2026-10-22_step6-review-sintesi_chatgpt.md`.
La sintesi esterna resta aperta: le review Step 6 originali di Claude,
DeepSeek e Kimi K3 non sono ancora disponibili nel contesto o nel diario letto.

La suite attuale passa 19 test, ma il test
`test_plan_shipped_as_non_executable_draft` obbliga status draft e data nulla:
il workflow lo eseguirebbe anche dopo l'approvazione, bloccando il piano approved.
Occorre separare il controllo di consegna draft dai test del runner approvato.
Il gate statistico deve anche distinguere pochi episodi indipendenti da un esito
negativo: con 100 trade e un episodio l'IC manca, ma ora produce not_supported.
La versione baseline e' controllata solo negli eventi open/close: un cambio
registrato in altri eventi non invalida il gate. Il periodo e la configurazione
congelata richiedono una prova di continuita' piu' ampia.

Prima dell'approvazione definire inoltre una sola valutazione finale o un
protocollo sequenziale esplicito: le soglie minime correnti non fissano una data
finale e Bonferroni sui due bot non copre controlli ripetuti nel tempo.
Il workflow effettivamente eseguito deve corrispondere al workflow del commit
congelato; un checkout del codice non prova da solo questa corrispondenza.

## Analisi obbligatoria per direzione prima di approvare

L'utente segnala short spesso positivi e long perdenti nei trade del 22 ottobre.
E' un'osservazione riportata: questa review non legge registri operativi e non
verifica il risultato della giornata. Un giorno e posizioni correlate non
dimostrano un difetto strutturale; lo storico Step 4 riportava gia' pochi long
negativi, quindi la domanda merita una misura dedicata.

Il runner attuale gestisce entrambi i lati nei calcoli ma li aggrega per bot:
non permette di osservare separatamente long e short. Se un long non raggiunge
mai la soglia +1,5R di chiusura, l'overlay non interviene e non ne corregge l'ingresso.

Prima della registrazione aggiungere al disegno del report, per bot e coorte:

- Risultati long/short: numerosita', giorni, episodi, interventi, R medio baseline,
  R medio candidato, delta appaiato, win rate baseline/candidato, vincita e perdita
  media in R e conteggi delle esclusioni per lato.
- Durata, leva, distanza stop e costo in R; se serve confrontare il dimensionamento,
  usare rapporti di rischio aggregati e normalizzati, senza importi pubblici.
- Aperte/non ancora chiuse e trade a cavallo del confine per direzione, cosi' una
  differenza di durata non viene scambiata per superiorita' di un lato.
- Incrocio descrittivo con regime BTC noto all'ingresso e versione/run, segnalando
  campioni piccoli. Per la giornata usare un confine temporale locale dichiarato;
  non confondere giorno di apertura con giorno di chiusura.

La segmentazione e' proposta come diagnostica predefinita. Non aggiunge quattro
test confermativi ai due test primari senza ridefinire potenza, correzione per
confronti multipli e criteri di decisione. Non si sceglie il lato vincente a posteriori.
Questa integrazione documenta il requisito: i gruppi direzionali non sono ancora
implementati nello script fe50c2ff. Status del piano ancora draft, data OOS nulla.
