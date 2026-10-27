# Rollback selettivo classici — diff da approvare prima del deploy

Stato: codice preparato, nessun deploy. Solo PAPER. Autorizzazione operatore del 27 ottobre 2026.

## Basi e perimetro

- Metodo richiesto: `5818aee1e587f103d222510e761b30e02776ff15`.
- Questo ramo parte da `rule-pool` `d1701f22f2a615ac3ef05f96b9d1d3b297abf0bc`.
- Ultimo runtime classico verificato nella precedente indagine: `89b0dca3e259c548ed82754c2301c7b024d18ff5`. Non è stata effettuata una nuova ispezione del VPS in questa implementazione.
- Le run positive hanno attraversato più revisioni: la baseline richiesta non equivale a una ricostruzione di tutti i loro ingressi e non promette di ripeterne i risultati.
- Backup codice già presenti: `backup/classici-2026-10-27` e `backup/rule-pool-2026-10-27`. Non sostituiscono backup dei dati e immagini prima del futuro rilascio.

## Cambiamenti effettivi

| Area | Risultato preparato |
| --- | --- |
| Soglie esecutive | Tier A/B 60, C 70; scoring senza P1/bonus successivi |
| Slot e sizing | Hawk 10 slot, massimo 100 per trade; Bull 3 slot, massimo 350 per trade; formule fisse della baseline |
| Stop giornaliero | 12%; esclusa gestione Capital V1 a percentuali e stop 20% |
| Segnali | Pesi storici, niente regime BTC successivo, veto Bull aggregato o fallback P2 |
| Dati | Niente feed daily nativo aggiunto dopo la baseline; disponibilità minima 200 barre daily conservata per correttezza. Trend 4h su vere barre 4h, parità neutrale, RSI piatto neutrale |
| Macro e stagionalità | Logica originale ripristinata, incluso filtro macro attivo quando il calendario è disponibile e penalità +5 nella finestra 12h; non la successiva modalità osservazione |
| SL | Resta 1.2 ATR come nella baseline scelta; nessuna modifica opportunistica a 1.5 ATR |
| Motore e LONG | Conservati cursore barre, gestione barre chiuse e stop nella barra di ingresso, DCA senza allargare stop, stato posizioni moderno, score del proprio lato e metriche nette nel prompt |
| Chiusure | Conservate gestione protettiva e chiusure semplici/anticipate/parziali; Profit Guardian avanzato non importato né attivato |
| Brain adattivi | Nessuna modifica ai loro rami, container o dati; questi file riguardano i classici |
| Archivi operativi | Nessuna modifica a trade_history.jsonl, lessons.md, errors.md, learning_log.jsonl |

`engine.py` mantiene il motore corrente: unica variazione è il default stop giornaliero da 10% a 12%. Il prompt usa il metodo storico con le correzioni matematiche/LONG/DCA e i campi diagnostici corretti. Questo è un rollback selettivo, non un checkout integrale del vecchio motore.

## Salvadanaio

- Attivo automaticamente solo in PAPER. Il ramo rifiuta avvio in modalità live.
- Confine giorno UTC. Trasferisce solo eccedenza realizzata netta sopra 1000 operativi, senza generare denaro e senza prelevare dal saldo protetto.
- Decisione esplicita dell'operatore: dopo perdita si mantiene il residuo; nessun rabbocco. Un conto che passa da 900 a 950 resta a 950, senza accantonare 50.
- Fee già detratte dalla contabilità. Il Salvadanaio non sottrae fee una seconda volta.
- Non forza chiusure a mezzanotte; profitti non realizzati o capitale vincolato restano eventualmente in attesa, esclusi dal saldo protetto. Il trasferimento avviene solo quando finanziabile.
- Preserva posizioni, memoria e saldo già esistente. Prima attivazione senza ricostruire accantonamenti storici inesistenti.
- Registro accrediti per giorno UTC con giorno origine, timestamp e saldo dopo accredito. Nessuna funzione di reinvestimento o trasferimento manuale aggiunta.
- Stato e vault nello stesso snapshot atomico con journal `salvadanaio-journal.jsonl`, outbox append-only e recupero dopo crash. Vecchio `capital-v1-journal.jsonl` lasciato intatto, non usato come snapshot finanziario corrente.
- Gap di giorni, barre di confine mancanti o stato incoerente richiedono riconciliazione: niente ricostruzioni inventate. Gestione protettiva separata dal permesso di aumentare rischio.
- Primo avvio senza file inizializza il conto una volta; stato esistente vuoto/corrotto non viene ricreato automaticamente.

## Dashboard separata

Ramo `work/classici-salvadanaio-dashboard-20261027` basato su main `4cf41d23bb94f7a868b25dd1c89b3e4e8993d9a8`:

- Carta “Salvadanaio” separata per Hawk/Bull: saldo, accredito odierno UTC, storico ultimi 60 giorni di accredito, somme in attesa distinte, avvisi offline/non disponibile.
- P&L totale include il saldo protetto, equity/cash operativi restano distinti.
- Lettura del solo stato PAPER, nessun endpoint di scrittura o comando di trasferimento; reset bloccato quando il vault è presente.
- Per vedere e usare la funzione completa serviranno in futuro rilascio bot e app, entrambi da autorizzare. Non fondere main e rule-pool per ottenere questo diff.

## Verifiche

- 317 controlli bot e sicurezza rilascio: 138 base/macro/orari/journal, 49 rollback/correzioni, 86 adattatori simulati/rule pool, 44 guardie deploy.
- 43 test lettore app; 3 prove React SSR sul componente; bundling sintattico dell'intero grafo frontend con dipendenze esterne.
- Test CI del nuovo contratto aggiornati: gli assert delle successive policy dismesse non rappresentano il metodo approvato. Conservati test delle correzioni motore.
- Build CRA completa, image build e suite CI da verificare dopo il push: non dichiarate eseguite localmente. Nessun test invia ordini reali.
- Workflow sui due rami di lavoro: solo test/build, nessun deploy automatico. Nessuna modifica ai trigger del deploy operativo.

## Condizione prima del rilascio

Attendere conferma separata dell'operatore sul diff finale. Prima del futuro deploy: ispezione runtime corrente, backup dati/immagini verificabile, gestione delle posizioni esistenti senza reset, coordinamento app/classici. Nessun deploy Brain adattivo o tocco ai dati classici è autorizzato da questo commit.
