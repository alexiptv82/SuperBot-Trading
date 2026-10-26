# Upgrader Brain PAPER con posizioni — review prima di esecuzione

Base rule-pool7c859391a79700b8de71f5d3c0b97159e1e5e9dc.
Branch work/brain-pilot-stateful-upgrader. Nessun deploy/pausa/riavvio eseguito.
Ultimo report osservato: Brain2c977c46,5posizioni PAPER; target applicativo resta
1f2edeb6182029adc96ba7218ad145a7503472a3 (PR#9 già integrata da Claude).

## Problema risolto
Il wrapper upgrade precedente chiamava ancora brain_pilot_repair_daily.py, che
richiede conto flat. Rimuovere l'allowlist del workflow non toglie quel requisito.
Il nuovo script brain_pilot_upgrade.py NON modifica/bypassa il repair: implementa
un protocollo diverso con posizioni aperte, preservando lo stato già persistito.

## Due SHA distinti
- BRAIN_SHA: codice applicativo da costruire (target1f2edeb6).
- BRAIN_PREVIOUS: versione che DEVE corrispondere al container attuale (2c977c46).
- BRAIN_CONTROL=github.sha: commit immutabile del controller/workflow. Il nuovo
  script sta qui, non nel target precedente che ancora non lo conteneva.
Il workflow controlla ancestry dei due SHA applicativi e crea due checkout
separati: controller per script/helper, worktree target per Docker build.
La strategia/immagine target non vengono cambiate per aggiungere il deploy tool.

## Sequenza
1. Verifica approvazione, chiave presente (solo booleano), SHA, PAPER, volume
   canonico, sandbox e assenza di altri writer. Il sidecar padre RO è ammesso.
2. Costruisce immagine target mentre il vecchio processo continua a gestire il
   conto. Ricontrolla SHA/container/conflitti prima di fermare SOLO il Brain.
3. Stop con timeout60s, writer lock esclusivo, SQLite quick_check e verifica log
   JSONL completi. Nessuna richiesta che account.positions o pending siano vuoti.
4. Backup raw della directory brain con rilettura e hash. Copia separata dei log
   e snapshot SQLite tramite backup API (include WAL COMMITTATO).
5. Prova l'immagine reale sulla COPIA: no rete, nessuna API key, solo costruttore
   Pilot+checkpoint, mai run_once. Confronta account/posizioni/cash/ID/stops/DCA,
   prefisso eventi storici, log e spesa. Ammesse solo migrazione policy20%,
   metadata additive e filtro dei pending legacy di NUOVA esposizione. Pending
   protettivi devono rimanere; nessuna posizione può sparire durante la prova.
6. Conserva il vecchio container fermo con nome rollback, senza rimuoverlo,
   immagine e dati. Avvia quello nuovo sullo stesso unico volume brain.
   Container rollback riconosciuti sono ammessi solo se fermati e verificati
   PAPER/sandbox; writer lock runtime impedisce un secondo processo scrivente.
7. Gate running/healthy/zero restart/heartbeat successivo all'avvio, paper e
   applied=false. Verifica policy20%, storia eventi immutata e log append-only.
   Ogni vecchia posizione deve ancora esistere con lo stesso ID oppure avere
   una chiusura effettivamente registrata dal motore dopo l'avvio. Non vengono
   forzate chiusure dall'upgrader; SL/TP normali possono scattare nel recupero barre.
8. Manifesto SHA vecchio/nuovo, backup, container rollback e conteggi posizioni.

## Rollback compatibile, senza perdita di dati
Non viene MAI ripristinato un vecchio snapshot sopra un DB più recente.
- Errore build: vecchio processo non viene fermato.
- Errore backup/prova migrazione prima dell'avvio: riparte la vecchia versione
  solo se i byte autorevoli del volume sono identici al checkpoint verificato.
- Nuovo processo fallisce senza cambiare stato: si ferma/conserva il candidato,
  si rinomina e riavvia il vecchio container con la configurazione originale.
- Se sono cambiati DB/WAL, journal, spesa, latch o altri dati: candidato fermato,
  tutti i dati e i due container conservati; ROLLBACK_BLOCKED_STATE_CHANGED.
  Serve verifica esplicita: il vecchio codice non conosce il latch20% e non deve
  leggere alla cieca nuove decisioni/stato. Nessun rewind di trade o budget.
- Writer occupato o stato non verificabile: nessun nuovo processo viene avviato.
  Il precedente resta fermo in conservazione. Non si riavvia contro un writer ignoto.
La memoria SQLite -shm e un WAL di dimensione0 sono esclusi dal confronto byte:
non contengono transazioni; DB e qualsiasi WAL non vuoto sono sempre protetti.

## Validazione
Test offline: conto sintetico legacy con5posizioni e2pending, storia e spesa.
Coprono successo, build/backup/probe falliti, reset simulato rifiutato, WAL
committato, blocco su writer, SHA errato, altra istanza scrivente, perdita silente
di posizione e log riscritto, rollback prima/dopo mutazione. Un test Docker
separato usa l'immagine reale su una copia dello stesso conto: si esegue in CI
senza rete/chiavi. Nessun test usa dati del VPS o chiama DeepSeek/exchange.
CI mantiene la suite Brain precedente e i test3.10/3.11, build Docker e prova
di migrazione del container. Docker non disponibile localmente.

## Uso futuro, solo dopo review e autorizzazione pertinente
Il trigger SU QUESTO BRANCH è disarmato: action=none, approved=no. Il trigger
su rule-pool era armato da Claude; non è stato modificato da questa preparazione.
Merge di questa PR sostituirà il trigger con la versione disarmata.
Per eseguire, dopo review e decisione utente: action=upgrade, approved=yes e i
due SHA completi verificati. Nessuna sequenza [skip ci] deve apparire IN ALCUN
PUNTO del commit che attiva il trigger. Commit di semplice preparazione/diario
possono invece usarla per non avviare workflow.
Il tool non riavvia mai Hawk/Bull, sidecar o vecchio pilot DeepSeek shadow; non
contiene chiavi di trading, ordini exchange, reset capitale o chiusure forzate.
