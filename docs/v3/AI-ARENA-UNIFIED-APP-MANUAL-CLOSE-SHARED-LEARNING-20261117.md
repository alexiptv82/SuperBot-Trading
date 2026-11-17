# AI Arena V3 — interfaccia unica, chiusure manuali e memoria verificata
17 novembre 2026 — ramo di laboratorio `work/arena-classic-archive-learning-foundation-20261117`

## Obiettivo utente (fonte del requisito)

Un'unica applicazione SuperBot aggiornata, NON un link Chrome o un secondo frontend:
- Home PAPER con tre schede DeepSeek / Qwen / MiniMax, ciascuna con 2.000 USDT PAPER e la stessa presentazione del Brain attuale: posizioni aperte, prezzi e P&L verificati, storico delle chiusure, performance, statistiche, leverage, stop e motivi.
- Falco SHORT preservato come strategia riattivabile. Toro conservato. Entrambi accessibili tramite un pulsante distinto `Falco / Toro`. Nasconderli nel menu **non** equivale a metterli in pausa; i runner restano intatti finché non viene autorizzata una procedura operativa con backup.
- Chiusura manuale **singola** su ogni portafoglio PAPER, con conferma e verifica dell'esito del worker. Il clic non è già una chiusura eseguita.
- Apprendimento da tutti i trade e NO_TRADE dei tre modelli; annotare separatamente la chiusura voluta dall'utente, senza presumere la ragione guardando soltanto il risultato.
- Al termine dei 14 giorni, il nuovo principale potrà usare un *archivio comune verificato* che include l'evidenza di tutte e tre. Nessun trasferimento di prompt o informazioni fra concorrenti durante la misurazione.

## Progressi su questo ramo isolato

1. `frontend/src/components/NavBar.js`: nella modalità AI Arena opt-in è visibile il pulsante `🦅 Falco / Toro` verso `/classic`. Rimangono accessibili tutte le route storiche, e la vecchia barra PAPER rimane invariata quando l'opt-in è disattivato.
2. `frontend/src/pages/BrainArena.js`: componente esistente `BrainCloseControls` riutilizzato SOLO per lo storico DeepSeek quando `REACT_APP_ARENA_EXISTING_CLOSE=1` **e** `overview.portfolios[].manual_close_allowed=true` sul `brain`. Limite `allowCloseAll=false`. L'API per questa sola run resta `POST /api/v3/brain/close`, che il backend già protegge con heartbeat/bridge e PAPER.
3. `frontend/src/brainArenaModel.js`: il permesso di chiusura è acquisito solo dall'overview della run Brain storica; i wallet trial hanno sempre `manual_close_allowed=false`. **NON** inoltrare mai il comando DeepSeek a Qwen/MiniMax. Le relative chiusure richiedono tre canali dedicati e singolo exit-worker owner.
4. `backend/v3/arena/learning_evidence.py`: funzione `collect_arena_learning_evidence(plans, now_ms)`, **sola lettura** e non attivata in alcun servizio. Verifica tre scope indipendenti, T0 uguale, journal completi e catena hash, provenance e linkage degli outcome. Conserva tutti i `brain_decision`, inclusi `NO_TRADE` e rifiuti, e tutti i risultati chiusi, senza limitazione alle 100 righe UI. Conta le posizioni ancora aperte. Revalida i digest per rilevare cambiamenti durante la lettura. Risponde con un digest complessivo; non altera alcun modello.
5. Ogni chiusura `manual` è memorizzata come evidenza `human_manual_exit` con `user_reason=null` e `AWAITING_USER_ANNOTATION`: **un PnL positivo non dimostra che l'utente volesse proteggere un profitto, né un PnL negativo che volesse limitare una perdita**. Non viene promossa automaticamente a regola.
6. Test di contratto: `backend/v3/arena/test_learning_evidence.py` e `frontend/src/components/NavBar.test.js`, oltre a due test di gating UI su `BrainArena.test.js`. NON sono ancora stati eseguiti sulla VPS. Build precedente 31 test React PASS appartiene al ramo precedente, NON certifica queste nuove modifiche.

## Pipeline di memoria necessaria prima del test reale

```text
Mercato congelato e identico
        │
        ├── DeepSeek  → decision journal D → posizioni D → esiti D
        ├── Qwen      → decision journal Q → posizioni Q → esiti Q
        └── MiniMax   → decision journal M → posizioni M → esiti M
              (separati, nessuna comunicazione durante trial)
                              │
                 EventJournal append-only
                              │
         Backup SQLite consistente + verifica e ripristino
                              │
           full outcomes + NO_TRADE + manual exits
                              │
         Archivio comune VERIFICATO, con SHA e tag AI
                              │
         Revisione umana / note motivazione chiusure
                              │
         Walk-forward e confronto fuori campione
                              │
          Memoria candidata per il Brain principale
```

Il file condiviso è una **proiezione** dei tre journal verificati e non la loro sostituzione. I database originali restano separati, con schema, run_id, modello, snapshot e catena integra. Non scrivere API key né posizioni personali su GitHub.

### Chiusura manuale da insegnare

Per OGNI run il contratto backend da implementare deve includere: `provider`, `run_id`, `position_id`, `request_id` idempotente, `requested_at_ms`, `exit_worker_owner`, `confirmed_at_ms`, `exit_reason=manual`, commissioni/PnL netto e hash della chiusura. Il server controlla la run, l'owner e il worker prima di accettare una richiesta; non basta vedere il pulsante. Dopo la chiusura confermata, l'app può chiedere facoltativamente `user_reason`:
- protezione profitto;
- riduzione perdita;
- cambio trend;
- altro / nota facoltativa.

Il motivo umano deve essere un evento di apprendimento autonomo, **append-only**, associato al `position_id` e non modificare il `paper_close` già registrato. Se l'utente non annota, l'esempio resta `unlabeled`. Se il worker rifiuta, non registrare un esempio di chiusura eseguita.

### Limite attuale

La funzione di collezione è una base **offline**, non equivale a un training, ad una memoria AI condivisa attiva o ad un nuovo servizio di archiviazione. Non è ancora possibile usare i tre pulsanti di chiusura come se le altre due run avessero exit-worker funzionanti.

## Gate prima di deploy o attivazione

1. Eseguire test locali isolati Python e React (senza nuove GitHub Actions), poi build frontend con nuove modifiche.
2. Verificare release branch, backup/restorable di Falco e Toro sulla VPS, senza cambi automatici ai processi.
3. Implementare runner separati e worker uscite per tutte e tre, con journal, API e allocazione 2.000 USDT verificati. Evitare T0 fake e reset DeepSeek silenzioso; preservare la storia pregressa.
4. Realizzare la registrazione della motivazione umana con review e idempotenza, più raccolta dei NO_TRADE e risultati. Verificare backup e restore di tutte le run e report di integrità periodici.
5. Eseguire un collaudo PAPER separato per chiusure manuali di DeepSeek, Qwen e MiniMax, recupero da crash, retry, prezzo mancante, duplicati e feedback; le richieste fallite non diventano esempi di successo.
6. Solo con consenso e rollback, aggiornare la webapp **esistente**, rendere Arena la home PAPER e tenere Falco/Toro visibili in una sezione distinta. Non creare nuova app o link esterno.
7. Avviare la prova comune di 14 giorni solo quando tutte e tre sono pronte. Nessun automatismo che scelga il vincitore dopo 14 giorni; la selezione deve tenere conto di mercati diversi, errori e costi.

**Stato:** nessun deploy, merge, stop/riavvio di Falco, Toro o Brain, apertura/chiusura di trade, crediti AI consumati o apprendimento automatico attivato da questo ramo.
