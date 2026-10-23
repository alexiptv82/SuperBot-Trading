# Capital Management V1 — specifica tecnica per approvazione
23 ottobre 2026 · autore: ChatGPT Work · stato: DESIGN COMPLETO PER REVIEW, NON IMPLEMENTATO.

## 1. Ambito e decisioni
L'utente autorizza la progettazione tecnica dei quattro componenti, non codice operativo, merge o deploy.
Baseline bot: f87f2d63c5849b177dbd33ee43c5be05ca58c8ed. PAPER obbligatorio.
Ultima verifica runtime registrata: Actions 39922740438; nessun nuovo controllo VPS in questa attività.

Decisioni riconfermate: Hawk 10%; Bull 25%; rollover 00:00 UTC; posizioni aperte preservate e accantonamento in attesa; protezione assoluta 450 invariata.
Restano le decisioni già registrate: target operativo 1000 per bot, vault separati, nessun reintegro automatico, stop futuro 20% del budget giornaliero, slot Hawk 10/Bull 6. Lo stop runtime resta 12% fino al rilascio autorizzato.
Importi in questa specifica sono parametri/esempi sintetici PAPER, non saldi reali.

Tre scelte raccomandate, da includere esplicitamente nell'approvazione del piano:
A. 10%/25% è cap totale di margine della singola posizione, includendo DCA e split.
B. Trasferimento manuale al conto operativo non cambia budget/cap/soglia di perdita del giorno e non cancella lock.
C. Equity operativa può superare temporaneamente 1000 con posizioni aperte; budget per nuove attività resta al massimo 1000. Pending non aumenta disponibilità né patrimonio totale.

## 2. Modello contabile comune
Valori monetari nuovi serializzati come stringhe decimali; calcoli Decimal con precisione esplicita e arrotondamento conservativo alla precisione del conto. Adattatore per la contabilità legacy: non cambiare implicitamente formule fee/funding, leva o risultati storici. Riconciliare con tolleranze dichiarate; incongruenze bloccano nuove esposizioni e trasferimenti.

Definizioni:
- cash: cassa operativa effettiva; M: margine già impegnato; U: P&L non realizzato netto dei costi già contabilizzati, senza sottrarli due volte.
- E = cash + M + U: equity operativa.
- V: saldo vault realizzato. Totale = E + V. Pending NON si somma al totale.
- E0: equity operativa al confine giornaliero dopo eventuale trasferimento immediato.
- B = min(1000, max(0,E0)): budget giornaliero fisso. Può differire da E0 quando esistono posizioni/pending.
- F: flusso netto cumulato vault->operativo nel giorno (entrate positive, uscite negative).
- pnl_day = E - E0 - F; perdita limite = 0.20 * B.
- Stop scatta a pnl_day <= -0.20*B e resta agganciato fino al rollover valido. Se B=0, ingressi bloccati.
- Guardrail assoluto 450 applicato all'equity operativa secondo la semantica della baseline; il vault non lo maschera e non viene usato per finanziare perdite. Nessuna nuova politica di liquidazione automatica introdotta.

Invariante trasferimento x operativo->vault: cash diminuisce x, V aumenta x, F diminuisce x, E+V e pnl_day invariati. Movimento inverso simmetrico. Non registrare trasferimenti come trade o profitto.

## 3. Capital Manager
Modulo proposto backend/desk/capital_manager.py.
Responsabilità: riferimenti del giorno UTC, stato di readiness, budget, perdita depurata dai trasferimenti, lock giornaliero, esposizione complessiva.

Contratti:
- prepare_rollover(snapshot, boundary, valuation): produce piano contabile senza effetti.
- commit_rollover(plan, expected_revision): applica una volta soltanto.
- risk_view(snapshot): restituisce B, E, pnl_day, loss_limit, headroom, lock_reason, freshness.
- validate_exposure(request): unico ingresso per open/DCA/split; non decide segnali o direzione.

Stati: READY, ROLLOVER_PENDING, RECONCILIATION_REQUIRED. Nuova esposizione e trasferimenti bloccati fuori READY; gestione protettiva delle posizioni continua secondo le regole operative esistenti.
Stop giornaliero, protezione assoluta, pausa operativa e budget AI sono stati distinti nella UI e nel ledger.

Rollover:
1. Prima di qualsiasi mutazione verificare data UTC e revision; il controllo leggero gira anche fuori dal ciclo mercato di 30 minuti.
2. Acquisire snapshot coerente, valorizzare posizioni al confine 00:00 UTC con fonte/istante/prezzi di riferimento registrati, costi maturati fino al confine secondo PAPER.
3. Se manca una valorizzazione attendibile, attendere: non usare il prezzo di adesso fingendo che sia quello di mezzanotte.
4. Riconciliare pending precedente, trasferire parte eleggibile, creare/alimentare lotto di accantonamento senza contare due volte quello esistente.
5. Fissare E0/B, nuovo giorno, F=0, cap percentuali; sbloccare solo il lock giornaliero, non pause o protezioni indipendenti.
6. Commit unico per bot/giorno, pubblicare snapshot.

Riavvio dopo giorni saltati: nessun profitto storico inventato né trasferimento multiplo sui medesimi fondi. Ricostruire confini solo se eventi e prezzi consentono una prova completa; altrimenti RECONCILIATION_REQUIRED con operatività protettiva preservata e intervento esplicito. Precisione temporale dichiarata: rollover logico UTC applicato al primo controllo utile, non promessa di esecuzione fisica al millisecondo.

## 4. Vault Manager
Modulo backend/desk/vault_manager.py. Vault virtuale distinto per bot, nessuna chiamata di trasferimento Bitget.

Al rollover calcolare surplus S=max(0,E-1000).
Trasferibile immediato T limitato contemporaneamente da:
- surplus ancora coperto dall'equity;
- surplus realizzato netto ricostruito dal ledger, esclusi apporti manuali e importi già accantonati;
- cassa libera dopo obblighi, fee e riserve per ordini/split già accettati.
Non basta cash>0: il margine liberato è capitale, non necessariamente profitto.

T=min(S, surplus_realizzato_eleggibile, cassa_trasferibile), con ciascun termine non negativo. Trasferire T una sola volta; parte restante è pending, non vault.
Ogni lotto conserva giorno origine, residuo massimo, posizione/coorte di origine quando identificabile, revision e trasferimenti già eseguiti. Ogni unità di eccedenza appartiene a un solo lotto.

Dopo close/partial: prima contabilizzare P&L netto, commissioni e margine liberato, poi riconciliare pending. Pagare solo fino al residuo del lotto e alla nuova eccedenza realizzata ancora disponibile. Nessuna nuova eccedenza intraday va automaticamente oltre il diritto già accantonato; sarà valutata al prossimo rollover.
Perdite possono ridurre/cancellare pending; non esiste garanzia che il profitto osservato a mezzanotte venga conservato. Al nuovo rollover un eventuale nuovo surplus crea un nuovo diritto, senza duplicare il precedente.
Con più posizioni, il ledger deve separare capitale restituito, profitto realizzato e apporti manuali; un deposito non può finanziare artificialmente il pending. L'algoritmo dei lotti è requisito bloccante dei test di integrazione, non una semplice sottrazione dal saldo.

Nessuna chiusura forzata a mezzanotte. Se E<1000, nessun prelievo automatico dal vault.

## 5. Persistenza e singolo autore dei saldi
Unico writer: processo bot proprietario del portafoglio. Dashboard/API inviano comandi, non scrivono cash, state_v2 o vault.
Snapshot versionato include schema_version, state_revision, day_id, E0, B, F, V, pending_lots, daily_stop_latched, ultimo evento e hash.
Ledger append-only contiene event_id, bot, UTC, tipo, idempotency_key, revision attesa, movimenti, pre/post hash, reason_code.

Per evitare una falsa atomicità tra file diversi:
- un unico journal di transazioni copre sia conto operativo sia vault;
- append record completo con checksum e fsync prima di applicare;
- scrittura snapshot tramite file temporaneo, fsync, rename e fsync directory;
- snapshot operativa e capitali sono proiezioni della stessa revision; nuove operazioni interdette fino a riallineamento;
- recovery riapplica soltanto transazioni non materializzate; ultima riga incompleta non viene eseguita, corruzione intermedia blocca;
- inclusi eventi trade che cambiano cash/margine: nessun percorso di scrittura parallelo non coordinato;
- process lock per bot, sequence monotona e controllo revision impediscono doppio writer/doppio comando.

Non introdurre un secondo servizio che modifichi stato del bot. Nessun file del cervello è trasformato in ledger né riscritto. Nuovi file solo nel volume del rispettivo bot, nomi da congelare nella PR di implementazione.

## 6. Position Sizer
Modulo backend/desk/position_sizer.py. Contratto size_request(bot, day_budget, positions, reservations, available_cash, requested_margin) -> accettato/ridotto/rifiutato + reason_code.
Hawk cap=0.10*B; Bull cap=0.25*B. Esempi: B1000 ->100/250; B900 ->90/225.

Con scelta A:
- somma margine già investito nella posizione + richieste DCA/split impegnate + incremento <= cap;
- totale margine/reserve <= min(B, limite aggregato esistente); controllo ulteriore su cassa realmente disponibile, fee e buffer legacy;
- nessun aumento di leva per aggirare cap;
- mantenere stop/TP, segnali, RR, quote minime e slot approvati;
- se il cap è sotto il minimo esistente, saltare il trade e registrare motivo; nessun forced entry sopra cap;
- se una posizione esistente supera il nuovo cap dopo rollover, non chiuderla: bloccare incrementi. Eventuali split non ancora eseguiti devono passare di nuovo i controlli prima del fill; questa modifica comportamentale fa parte della scelta A.
- la stessa funzione controlla proposte rules e AI; esposizioni simultanee riservate prima di accettare.

cli.make_account non deve sovrascrivere il budget persistito con default statici. I numeri nei prompt/schede devono essere coerenti con cap aggiornato; qualsiasi diff ai prompt sarà limitato alla rappresentazione dei parametri autorizzati e presentato in review. Nessuna modifica alla tesi di ingresso.

## 7. Dashboard Capitali e comandi
App su storia main, ramo futuro work/capital-dashboard-v1, base SHA main da leggere e fissare al momento; nessun merge fra storie bot e app.
Per bot: PAPER, code_version, freshness/revision, equity operativa, cash, margine, non realizzato, vault, pending, totale, B, cap, pnl_day, limite/consumo stop, protezione assoluta, prossimo rollover UTC.
Pending etichettato “profitto in attesa, non garantito”; separare stop trading da budget AI.

API proposte:
- GET /api/desk/capital: snapshot aggregata coerente e stato migrazione; non interrogare saldi live.
- POST /api/desk/capital/transfers: solo vault->operativo, bot/importo/idempotency_key/expected_revision; autenticazione e autorizzazione proprietario, protezione CSRF se sessione cookie, validazione Decimal e limite saldo.
- GET /api/desk/capital/transfers/{id}: stato richiesto/eseguito/rifiutato con reason_code e revision.

API mette comando in coda persistente; il bot lo esegue sotto lock dopo validazione aggiornata. UI conferma successo solo dopo ACK committed del bot; timeout = “in attesa”, non ritentare con ID nuovo. Stessa chiave/stesso payload restituisce stesso risultato; stessa chiave/payload diverso rifiutata. Bot offline: comando in attesa con scadenza, nessuna modifica fittizia al saldo.
Con scelta B, top-up non resetta pnl_day né lock e non alza B/cap fino al giorno successivo. Quanto rimane disponibile segue comunque tutti i controlli di rischio.

## 8. Migrazione e rollback
Nessuna migrazione ora. In futuro: backup verificato di stato/cervello/DB, snapshot coerente, hash e manifesto, copia offline di prova.
Migrazione additiva idempotente: vault iniziale zero, nessuna ricostruzione retroattiva dei profitti, storico e ID posizioni intatti. Bootstrap del primo giorno definito nel piano di rilascio, preferibilmente al confine UTC; non azzerare uno stop già attivo durante migrazione.
Vecchio reset_portfolio/state.clear deve rifiutare reset se rischia di perdere ledger/vault; un reset futuro richiede procedura separata autorizzata.
Rollback dopo trasferimenti NON significa ripristinare alla cieca vecchio state_v2: conservare ledger e saldi attuali, fermare nuovi ingressi, riconciliare e usare esportazione compatibile verificata. Vecchia immagine incapace di capire vault non può essere avviata sui nuovi stati senza procedura. Nessuna perdita di memoria, nessun rewind di trade.

## 9. Piano di test e criteri di accettazione
Test futuri, NON eseguiti in questa fase:
- flat E1120:120 trasferiti; flat E900:zero e nessun refill.
- cash+M=1000, U150: vault0/pending150; successiva chiusura con profitto netto120 -> trasferimento massimo120; chiusura in perdita -> niente profitto inventato.
- chiusure parziali/multiple, perdite concomitanti, depositi manuali: mai capitale iniziale o deposito spacciato per profitto.
- due rollover identici; riavvio in ogni punto di journal/snapshot; salto giorni; ora legale; prezzi stale; cambio data durante comando.
- invarianti E+V e pnl_day nei trasferimenti, pending escluso da totale, no negativi, no doppio conteggio tra lotti/giorni.
- stop a confine esatto20%, vault top-up non lo sblocca, kill450 indipendente dal vault.
- cap su open/DCA/split, prenotazioni concorrenti, cap sotto minimo, posizioni preesistenti sovracap, nessuna leva aggiuntiva.
- autenticazione, bot errato, importi zero/negativi/non finiti, doppio click, retry ACK perso, chiave riusata con payload diverso, saldo/revision obsoleti, bot offline.
- migrazione/riavvio/rollback preservano posizioni, contabilità e byte dei file del cervello preesistenti; successivi eventi solo in append.
- confronti con baseline su fixture sintetiche: differenze economiche soltanto nei comportamenti approvati.
- test unitari, integrazione, property tests contabili, py_compile, suite bot esistente, API/frontend build e test UI.
Nessun risultato di test dichiarato finché il codice non esiste; pubblicare solo fixture sintetiche e aggregati.

## 10. Sequenza e coordinamento
1. Review di questo piano da utente/chat normale/Claude; confermare A/B/C e autorizzare separatamente implementazione.
2. Prenotare file e owner in STATO; creare work/capital-management-v1 da f87f2d63c5849b177dbd33ee43c5be05ca58c8ed. Nessun codice su rule-pool. App su ramo separato da main con base fissata.
3. Prima ledger/Capital/Vault e test, poi Sizer/integration, quindi API/UI. Congelare contratto dati prima di dashboard. Un autore per componente.
4. PR con diff comportamento, prove contabili, test, migrazione e rollback. Nessun merge o trigger implicito.
5. Solo con OK specifico al rilascio: backup, verifica baseline corrente, singola istanza PAPER per bot, verifica versione e contabilità dopo rilascio. Nessun reset capitale.
6. Nuova versione invalida eventuale coorte Step6 già iniziata: mantenere S non fissata finché baseline definitiva non è stabile e autorizzata.

## 11. Evidenza e limiti
Letti protocollo, handoff e diario aggiornati. Questa specifica dettaglia l'audit precedente, non certifica nuova ispezione del runtime o implementazione.
Punti da provare nella futura PR: copertura di TUTTI i writer del conto; fonte affidabile della valorizzazione UTC; classificazione surplus realizzato/lotti; integrazione coda comandi/auth app; recovery/rollback.
Il documento è completo per review tecnica; A/B/C restano scelte esplicite da approvare, non autorizzazioni dedotte.
