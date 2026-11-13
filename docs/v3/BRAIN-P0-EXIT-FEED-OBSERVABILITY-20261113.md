# Brain V3 — laboratorio fix P0 feed uscite, 13/11/2026

## Stato
- Solo branch isolato work/brain-exit-observability-20261113 da commit base 0e29a73a36f668643da4088178bacb8616a45ac0.
- NON DEPLOYATO. NESSUN MERGE. Nessuna modifica ai servizi della VPS e nessun GitHub Actions.
- L'utente ha segnalato di aver messo Brain PAPER in pausa; non verificato direttamente sul server da GitHub.
- Solo backend/v3/runner/monitor.py, feed.py e test di regressione interessati. Falco, Toro, Brain AI/risk/strategia invariati.

## Problemi e correzioni candidate
1. Il monitor su feed 1m vuoto con posizione PAPER aperta poteva tornare checked=1 errors=[]; heartbeat sano ingannevole.
   Fix: con almeno una candela valutabile ormai chiusa, se la posizione resta aperta e l'intervallo valutabile non ha copertura continua 1m, aggiunge errore exit_feed_incomplete. Questo produce stato degradato e rifiuta nuove aperture dal gate senza compromettere le chiusure esistenti.
2. last_minute_close accettava un prezzo con apertura fino a 5m prima dell'ultimo minuto atteso.
   Fix: rifiuta stale_minute_bar se timestamp dell'ultima candela non coincide esattamente con il minuto chiuso immediatamente precedente.
3. Nella VPS le tre uscite PAPER a stop LINK/SOL/ETH del 13/11 mostrano corrispondenza con la candela successiva al primo attraversamento dello stop nello storico recuperato EX POST. NON provata causa (lag, disponibilità feed, modello). Nessuna alterazione retroattiva.

## Test predisposti, non ancora eseguiti
- Nuovo backend/tests/test_v3_brain_exit_feed_observability_20261113.py: otto test sintetici senza rete su empty feed, ultimo minuto mancante, gap interno, opening partial minute, feed sano, stop ancora eseguibile, stale vs fresh manual quote.
- Un test preesistente ora richiede degradazione anziché sanezza in caso di storia troncata su posizione aperta.
- È obbligatorio eseguire la suite isolata (P0 + regressioni exit_service/exit_worker/runner feed/manual close) prima di considerare valido il fix.

## Vincoli rigidi
- Nessuna posizione LIVE o PAPER operativa va aperta, modificata o chiusa dai test.
- La stage VPS contiene già due hotfix Bitget applicati manualmente: non sostituire checkout o 72 commit di altri componenti. Per eventuale deploy successivo verificare diff puntuale e interazione con hotfix locali.
- Backup, rollback, verifica ownership sidecar e pause flag; richiedere autorizzazione utente per ogni deploy e successiva ripresa delle nuove aperture.
- Stato degraded è allarme e gate di nuove aperture, NON ordine stop reale; con feed mancante la chiusura non è garantita.
- Nessuna PR aperta per non attivare eventuali workflow GitHub Actions.

## Baseline runtime precedente
- Prima della pausa: 62 decisioni, 15 OPEN approvati, 6 paper_open e 6 paper_close, 0 posizioni aperte nel campione verificato, PnL PAPER realizzato -56.43945680 USDT.
- I controlli delle 23:11 mostrano fill storico sulla candela successiva al primo stop ex post, in tutti i 3 perdenti.
- L'attuale stato reale di pause e exit service richiede conferma READ-ONLY; il codice GitHub da solo non può certificarlo.
