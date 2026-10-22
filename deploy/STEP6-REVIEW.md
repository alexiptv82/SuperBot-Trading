# Step 6 — versione corretta proposta per review Claude

22/10/2026, ChatGPT. Stato **draft**, data OOS nulla, nessun trigger.
Questa proposta sostituisce il protocollo del commit fe50c2ff; la cronologia
delle revisioni resta nel ramo diario, in
`diario/2026-10-22_step6-review-sintesi_chatgpt.md`.

## Obiettivo e confini

Due confronti primari: differenza appaiata di R netto medio, uno per Hawk e uno
per Bull. Target: trade puliti della coorte registrata, pesati allo stesso modo,
con il mix direzionale osservato. Nessuna standardizzazione 50/50 implicita.
Long/short e regime BTC all'ingresso sono diagnostiche descrittive, non nuovi
test primari. Non si sceglie a posteriori il lato sul quale adottare la variante.

Il candidato resta identico: dopo una **chiusura** 15m interamente post-ingresso
ad almeno +1,5R di prezzo, uscita di meta' alla prossima apertura; dopo questa
attivazione, uscita del residuo alla prossima apertura se la sua valutazione
netta a chiusura barra e' non positiva. `liquidation()` significa valutazione
netta dell'uscita, non liquidazione forzata a margine. Low/high non sostituiscono
il close. Resta il confine terminale dell'uscita baseline, con esclusione della
sua barra SL/TP per ambiguita' intrabarra. Nessun fill oltre quel confine.

Non e' un replay di portafoglio: ingressi e uscita terminale registrati sono
esogeni. Non simula reingressi, slot, equity, saldo, drawdown del conto o
stagionalita' economica. Un long che non raggiunge +1,5R non viene protetto.
Non fornisce una diagnosi causale certa di bug vs regime di mercato.

## Correzioni rispetto a fe50c2ff

| Rilievo | Implementazione proposta | Stato residuo |
| --- | --- | --- |
| R1: test obbligava draft | Suite valida entrambe le fasi; preflight `--check-plan` prima dell'SSH rifiuta draft e approvazioni incomplete. | Confermare suite anche in CI Python 3.11. |
| R2: controllo versione limitato a open/close | Tutti i tipi di evento con timestamp nel periodo; versione assente/diversa invalida. Richiesto anche ledger esterno per continuita' della configurazione. | Origine e completezza del ledger da revisionare, non dimostrate dai soli log. |
| R3: pochi episodi apparivano esito negativo | Almeno 30 episodi e 25 episodi con intervento, oltre a 100 trade e 50 interventi; altrimenti inconclusivo. | Soglie euristiche proposte, non garanzia di precisione o potenza. |
| R4: arresto/valutazione non fissati | Ingressi su 42 giorni, maturazione di 14, una valutazione finale; effetti OOS nascosti prima del termine. | Registrazione e congelamento operativo prima dell'avvio. |
| R5: manca long/short | Metriche, censura, esclusioni per coorte/direzione, incrocio descrittivo con regime BTC. | Verificare rappresentativita' e conteggi su archivio autorizzato. |
| R6: checkout non fissa YAML caricato | Uguaglianza dei blob YAML fra `github.workflow_sha` e commit congelato, prima del checkout e dell'SSH. | Review del workflow corretto e normale controllo dei permessi del repo. |

Nessuna modifica al motore, alle soglie operative o ai prompt. Il modello PAPER
resta fee 6bp/lato, slippage 2bp base, funding 1bp/8h solo long. Corrisponde alla
contabilita' revisionata; non rappresenta funding reale. La divisione 50/50
ripartisce entry fee una volta, exit fee per fill e funding per durata di ciascuna
meta'. L'inverso `exit/(1-side*2/10000)` e' coerente con lo slippage d'uscita.

## Registrazione e valutazione unica

Piano schema 2. `draft` deve avere data OOS e fingerprint configurazione nulli;
non e' eseguibile. Dopo review e OK separato, `approved` deve indicare:

- un inizio futuro a mezzanotte UTC, successivo al commit congelato completo;
- baseline confermata e fingerprint non segreti per entrambi i bot;
- tutti i parametri proposti, identici a quelli accettati dal runner.

`baseline_version=4aabeb8` resta un riferimento documentale da confermare prima
dell'approvazione: il HEAD rule-pool 7a5e795 non prova quale immagine sia attiva.
Versioni storiche revisionate: 5818aee, b4709d1, b6b9911, fa3e220, 4aabeb8.
Questa sessione non ha verificato container o configurazioni sul VPS.

Sia S l'inizio registrato. Ingressi OOS: S <= open < S+42 giorni.
Scadenza finale F=S+56 giorni; chiusure ammesse solo fino a F. Nessun prolungamento
per raggiungere significativita'. Trade iniziati prima di S e chiusi dopo S sono
purgati; quelli aperti da S+42 in poi non entrano. Una posizione della coorte
non univocamente chiusa a F rende il gate inconclusivo, anziche' sparire dal
campione. Il vincolo sui soli trade puliti mantiene comunque un rischio di selezione.

Prima di F: conteggi di raccolta e qualita', nessun delta, attivazione o risultato
prospettico. Storico pre-S descrittivo separato. A F: una valutazione su snapshot
immutabili da archiviare prima di leggere gli esiti, senza pubblicare dati grezzi.
Il workflow non crea l'archivio o un registro immutabile di valutazioni: questa
procedura deve essere organizzata e verificata prima dell'approvazione.
Gli hash di tutti gli input sono nel report; una ripetizione tecnica deve usare
quegli stessi byte, non una coorte aggiornata. La finestra di candele e gli eventi
sono comunque tagliati a F anche con manifest successivi; dati post-F non
possono recuperare lacune oltre la scadenza. Una revisione dei dati pre-F puo'
cambiare il risultato: occorre conservare lo snapshot originale e dichiararla.

Una modifica di baseline/configurazione durante [S,F] invalida la coorte.
Il timestamp Git non e' un'autorita' temporale indipendente: approvazione e
registrazione vanno documentate prima di S. Nessuna retrodatazione.

## Statistica proposta, da approvare

- Minimi per bot: 42 giorni di ingressi, maturazione 14 giorni; 100 trade puliti,
  50 interventi, 30 episodi, 25 episodi con almeno un intervento. Si combinano,
  non si sostituiscono. Una scadenza insufficiente da' inconclusivo, non estensione.
- Episodi: giorni UTC espansi e sovrapposizioni transitive delle posizioni.
  Uno stesso episodio puo' contenere entrambi i lati: non viene spezzato.
- Bootstrap del delta appaiato, includendo gli invariati con delta zero.
  Ricampiona episodi interi e ricalcola la media per trade (non media delle medie).
  10000 repliche, seed principale 20261022 e ripetizione diagnostica 20261023.
  Implementazione stdlib su somme e numerosita' degli episodi.
- IC percentile 97,5% per ognuno dei due confronti primari, Bonferroni. Quantile
  empirico inverso: indice Python ceil(B*p)-1. Nessun passaggio a Holm senza
  implementare e revisionare test/p-value validi; nessuna selezione automatica BCa.
- Differenza massima fra endpoint dei due seed <=0,02R; altrimenti inconclusivo.
  Anche questa tolleranza e' una proposta. Non aumentare B fino a ottenere l'esito
  desiderato. Piu' repliche non risolvono pochi episodi o dipendenza di regime.
- Per supportare ulteriore shadow review: limite inferiore IC >0, delta medio
  >=0,10R, delta positivo in entrambe le meta' temporali della finestra fissa,
  togliendo i tre migliori trade e togliendo separatamente ogni episodio.
- Scenari di stress predefiniti: slippage 2/4/8bp con ritardo zero e 2/8bp con
  ritardo aggiuntivo di una barra. Delta medio positivo in tutti; non si sceglie
  lo scenario vincente. IC solo sul primario slip2/delay0; sensibilita' descrittive.
- Il bootstrap e' approssimato: Bonferroni non garantisce da solo copertura in
  presenza di pochi cluster, dipendenza residua o cambi di regime.

Esiti distinti: pending_fixed_final, invalidated_baseline_change,
inconclusive_sample_or_coverage, inconclusive_runtime_evidence,
inconclusive_bootstrap_precision, not_supported, supports_further_shadow_review.
Nessun esito autorizza deploy o cambi ai bot; automatic_promotion resta false.

## Diagnostica per direzione e regime

Per ogni bot/coorte/scenario: n, giorni di ingresso, episodi, episodi attivati,
interventi, R medio baseline/candidato/delta, win rate, media vincite e perdite,
profit factor in R, durata baseline, leva, distanza stop e costo baseline in R.
Il profit factor e' somma R positivi / valore assoluto somma R negativi; se il
denominatore e' zero restituisce null e un flag, mai Infinity. E' un rapporto di
R normalizzati, non necessariamente il profit factor monetario del conto.

Le durate riportate sono quelle baseline, non holding time della variante.
Episodi dei sottogruppi contati sul partizionamento congiunto, senza IC
indipendenti per lato. Incrocio direzione x proxy BTC noto all'ingresso:
down <-1%, up >+1%, flat altrimenti; unknown se assente. Non e' il regime del
singolo asset o una diagnosi strutturale. Il campione OOS impone una versione;
lo storico aggrega versioni revisionate, senza stima causale dei loro effetti.
Nessuna stratificazione per singolo run implementata in questa versione.

Conteggi per direzione di aperture, non ancora chiuse univocamente, ingressi
pre-OOS ancora esposti e ingressi oltre la finestra. Esclusioni del parser e
della copertura per coorte/direzione, piu' classe unattributable. Identita'
invalide restano conteggiate globalmente, senza inventare un lato. Le classi di
esclusione possono sovrapporsi; non sommarle come partizione dei trade.

## Input offline e continuita' operativa

Read-only: learning_log.jsonl da /data/{hawk,bull}; candele e manifest da
/market, sul VPS /opt/superbot-step6-market. Nessun collector installato qui.
Archivio e provenienza non verificati. Nessun download nel container senza rete.
JSON rigoroso, hash/rilettura input, symlink finali e directory non canoniche
rifiutati. Limite per file 16MiB e 200000 righe: oltre il limite si blocca,
non tronca. Prima di registrare 56 giorni verificare capacita' e procedura di
snapshot; una soluzione streaming/archivio diversa richiede review separata.

Candele JSONL: schema=1, symbol, open_ms, open/high/low/close; multipli 900000,
solo barre complete. Manifest schema=1, source=bitget_public_15m,
timestamp_semantics=open_ms, interval_ms=900000, asof_ms, bars_sha256.
Necessaria copertura continua fino al bucket d'uscita interamente chiuso.
Una chiusura esattamente a F puo' quindi risultare senza copertura; non viene
recuperata usando la barra successiva a F.

Nuovo input locale opzionale /market/runtime-ledger.json. Assente/incompleto:
nessun esito favorevole. Schema esatto:

- root: schema=1, source=reviewed_deployment_config_ledger, bots={hawk:[],bull:[]};
- ogni segmento: from_ms, to_ms (interi, from<to), code_version,
  config_sha256, paper=true, source_sha256 (64 hex);
- segmenti ordinati, non sovrapposti, senza lacune nell'intervallo da attestare;
- versione/configurazione coincidenti con piano approvato e modalita' paper.

La fonte deve essere un registro revisionato di deploy E cambi di configurazione,
non una sola fotografia finale. source_sha256 identifica i documenti operativi
sanificati sottostanti, da conservare fuori dal repo pubblico. Non inventare
segmenti per colmare assenze. Un file con dichiarazioni e hash non dimostra
l'autenticita' o che nessun evento sia stato omesso: il gate dice esplicitamente
attested_continuity_manual_review_required.

Prima dell'approvazione definire con Claude il documento canonico di configurazione
non segreta (configurazione effettiva bot/limiti, regole, prompt/calendario e altre
fonti modificabili che influenzano la baseline), serializzazione, raccolta e
copertura del registro. Non includere credenziali o hash di segreti. La memoria
che cresce naturalmente non va azzerata o congelata: resta parte dell'ingresso
registrato ed e' un limite del controfattuale. Nessun esportatore/collector di
questa evidenza viene installato da questa proposta.

## Workflow, verifica e consegna

Solo push del futuro deploy/desk-step6.trigger su rule-pool; file assente.
Confronto blob YAML caricato/congelato, test, py_compile e preflight approved
prima di caricare chiavi SSH. Sul VPS checkout temporaneo, PAPER prima e dopo,
invarianza ID/immagine/StartedAt in trap anche su errore. Immagine Hawk fissata
all'ID, --network none --read-only, mount :ro, capability ridotte e risorse limitate.
Output solo aggregati/hash, artifact, errori fissi senza traceback o dati grezzi.

Verifiche locali: 33/33 test con piano draft e 33/33 con piano sintetico approved
(ripristinato poi draft/null); regressioni di approvazione, finestra fissa,
pochi episodi, versione non-trade, evidenza runtime, privacy e bootstrap;
script shell effettivi con git/docker simulati per mismatch YAML, errori,
riavvii e cambio PAPER. Sintassi YAML/bash e py_compile.
Riferimento GitHub per il commit del workflow caricato:
https://docs.github.com/en/actions/reference/workflows-and-actions/contexts

Python locale 3.12.14; CI 3.11 predisposta su PR, non attestata in questa sessione.
Nessuna esecuzione operativa.

Per Claude: review indipendente di questa versione e decisione sulle soglie
proposte. Prima di approved restano conferma baseline, piano dati/snapshot,
provenienza e completezza ledger, evidenza CI e approvazione esplicita dell'utente.
Nessun merge, trigger o VPS finche' non arriva un OK separato.
