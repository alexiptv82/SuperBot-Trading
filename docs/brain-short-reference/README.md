# Brain: riferimento SHORT storico e ricostruzione delle run positive

29 ottobre 2026. Autore ChatGPT. Solo ricerca e sviluppo offline, nessun deploy.
Ramo: work/brain-short-reference-20261029, base856a5ed095d4066840a5b05d71817c1c35aea4e8.

## Risultato principale

Il contributo SHORT delle run positive è confermato dai registri originali PAPER, dopo riconciliazione per posizione completa:

| Periodo | Direzione | Posizioni | Vincenti | Netto USDT |
|---|---|---:|---:|---:|
| Golden Hawk2 + Bull1 | SHORT | 91 | 58 | +1992,7949 |
| Golden Hawk2 + Bull1 | LONG | 2 | 0 | -131,4328 |
| Prima crisi Hawk3 + Bull2 | SHORT | 48 | 14 | -373,6318 |
| Prima crisi Hawk3 + Bull2 | LONG | 5 | 0 | -55,9172 |

Golden totale93posizioni, netto+1861,3621. Il confronto non è un esperimento di profittabilità: stessi simboli e momenti possono essere condivisi tra wallet; le osservazioni non sono indipendenti.
I due LONG golden riguardano entrambi OP: non bastano a valutare un metodo LONG generale.

Lo screenshot Bull mostra30realizzi e24positivi, comprese parziali; i registri riconciliati sono17posizioni complete,12positive e netto770,7485. Hawk76posizioni/46positive/netto1090,6136. La differenza è l'unità di conteggio, non una smentita del netto mostrato.

## Versioni: quale metodo preservare

Attribuzione degli ingressi golden nell'export:
- a0afc63:6posizioni.
- 7ced3a6:35posizioni.
- 9fa667f:51posizioni,49SHORT e2LONG.
- Fonte ignota:1posizione.
- Nessun ingresso golden attribuito a5818aee nell'export. La versione finale mostrata da una run non è necessariamente quella di tutte le aperture.

Le attribuzioni sono inferite dagli intervalli di deploy, non tutte registrate direttamente dal processo. Non inventare una provenienza esatta per l'ingresso ignoto.

Confronto dei blob originali recuperati daGitHub: signals.py e seasonal.py sono identici in a0afc63,7ced3a6,9fa667f,5818aee, nel rollback0ad6893 e nella versione della prima crisi b4709d1.
Questo identifica precisamente il componente tecnico da preservare. Non significa che l'intero sistema, gestioneAI, disponibilità dati e ambiente fossero uguali.

Fonte di riferimento scelta:
9fa667ff1103f037bec06f9131996366d27370c4

SHA256 signals.py:
3c398e4be0335896b30f09426e5d8567cefd064907290b71b13860b8d54ec5bf

SHA256 seasonal.py:
47c12da1abbe51be0c826fc03b7609af40407e2e101911ded3444def5d6912c7

Nessun file storico modificato o copiato in un nuovo motore operativo. Git e impronte permettono di recuperare il riferimento; i test verificano gli oggetti originali.

## Componenti tecnici trovati nel riferimento

| Componente | Contributo storico |
|---|---|
| Trend4h EMA50/EMA200 |20punti al lato individuato |
| Trend1h EMA20/EMA50 |15punti |
| Trend1d se disponibile |15punti |
| Prezzo rispetto EMA50 1h |8punti |
| Momentum24h |fino a12punti |
| Breakout massimi/minimi20h |10punti |
| RSI1h |8punti nella fascia prevista |
| Volume relativo |4punti |
| Pattern candela |fino a8punti; doji penalizza entrambi |
| Stagionalità |bonus non calibrato fino a15punti |

Il punteggio non è una probabilità di vincita.
Negli87SHORT golden con feature registrate, trend4h/prezzoEMA/momentum compaiono87volte, trend1h86, breakoutminimi62 e volume60.
Negli48SHORT della prima crisi i relativi conteggi sono48/48/48/48/37/36: componenti simili non garantiscono lo stesso risultato. Le frequenze sono descrittive, non nuovi filtri ottimizzati.

Limiti tecnici da non trasferire silenziosamente:
- Confronti >else assegnanoSHORT anche a uguaglianza per alcuni indicatori.
- EMA4h può usare meno di200barre pur essendo descritta comeEMA200.
- Nel ramo daily30–49barre EMA200 coincide conEMA50 e il confronto produce trendSHORT.
- Le motivazioni restituite daReading descrivono solo il lato selezionato; non ricostruire spiegazioni del lato opposto inesistenti.
- Tempi e qualità dei dati originali devono essere controllati separatamente.

## Modulo preparato per il Brain

backend/director/brain_scalp/legacy_reference.py

build_reference proietta un Reading già calcolato con il componente storico in un contestoJSON:
- punteggi LONG eSHORT distinti e preferenza originale;
- prezzo osservato, timestamp e anzianità;
- feature e spiegazione disponibili, con provenienza;
- avvisi sui limiti storici;
- authority=advisory_only ed execution_permission=false.

Non contiene plans, non apre posizioni, non cambia rischi/soglie/stop, non decide quale lato eseguire e non sostituisce lo scanner. Non è stato collegato a un providerAI o alBrain attivo.
Il chiamante deve fornire Reading da dati disponibili al timestamp e verificare le impronte del codice effettivamente usato: metadati copiati da soli non provano il calcolo. L'adattatore non esegue o duplica lo scorer.

Il modulo preserva entrambi i punteggi, riconosce pareggi neutrali e rifiuta contesti scaduti/futuri, incoerenti o con sorgente diversa. Non inoltra campi sconosciuti, esiti futuri, APIkey o dati operativi arbitrari. I controlli d'ingresso e il daily stop delBrain restano indipendenti.
Max_age_ms è esplicito: freschezza del riferimento tecnico non equivale al controllo delle quote d'esecuzione.

## Provenienza e riproducibilità

Input: export27/10 di357posizioni complete, senza nuovo accessoVPS.
SHA256:
0d1252e15d5d07c7dc7fa61789648e0a45d9383e7efc783852439ceaf95ff281

Si riutilizza tape_audit.py esistente dal ramo del laboratorio, fissato a:
e9fafa2373af3c0aab935108b30f2f62805e33e5
SHA256:
e7a2bd43ec79db5f7d5958dd11daca57528477d1497f27b8d49fd63607866f92

Il nuovo script research/brain_short_reference/reconcile.py legge gli oggetti con git show, controlla gli hash, usa il validatore precedente e aggiunge la separazione per direzione.
Non scarica mercato, non importa un motore trading e non modifica archivi:
PYTHONPATH=backend python research/brain_short_reference/reconcile.py --repo . --output-dir /tmp/brain-short-audit

Richiede checkoutGit con storia completa. Nel dossier:
- audit_summary.json: direzioni, contributi, conteggi e impronte del codice.
- original_tape_audit.json: risultato dell'auditor precedente riutilizzato.
- entry_provenance.csv: cronologia93aperture e livello di evidenza, senza esiti futuri da usare come inputAI.

## Ciò che resta non dimostrato

Mancano4log d'ingresso golden e tutti93exit_code. Quattro chiusure golden hanno etichetta ambigua modello-o-regole: non attribuirle automaticamente aClaude. Nessun nuovo replay dei prezzi o delle decisioniAI è stato eseguito.
Senza traiettorie complete e snapshot originali non possiamo certificare controfattualmente quali ingressi fossero tardivi, né come cambierebbero risultati con altre uscite.
Il fallimento del replay precedente rimane valido: questo audit non lo trasforma in un backtest fedele.
La prima crisi non viene usata come test intatto: era già stata analizzata. Per nuove regole serve una nuova finestra di valutazione non utilizzata per scegliere parametri.

## Test e ripristino

CIisolata suPython3.10/3.11: suiteBrain114 test più11test delriferimento e delle fonti. Esito e SHA finali nel diario.
Prove: tipi/tempi/provenienza, LONG/SHORT/NEUTRAL, nessuna autorità d'ordine, nessuna mutazione wallet, nessun esito futuro inoltrato, hash codice originali e riconciliazione reale.
Nessuna duplicazione dei classici o di un writer. Ripristino del solo codice con revert del nuovo commit, base856a5ed conservata. BrainFree, PWA, dati/storici, VPS e deploy immutati.
Wallet unico2000 e DeepSeek+Claude restano il mandato progettuale successivo; il riferimento tecnico non è apprendimento automatico già operativo.

AI: chatgpt
