# Brain V3 — Registro controfattuale e audit post-AI (solo offline)

**Ramo:** `work/brain-counterfactual-postai-research-20261115`  
**Base:** ricerca Opus `work/brain-audit-opus-20261115` (comprende FRRD); **nessun merge/deploy**.

## Problema misurato

- Audit VPS del 15/11: **336** `brain_decision`, di cui **86** `NO_TRADE/DRAFT`, **199** `NO_TRADE/RISK_REJECTED`, **50** `OPEN/APPROVED`, un `ai_unavailable`; **30** `paper_open` nel run. I conteggi sono riferiti a quella **istantanea**, non sono stati letti ex novo sulla VPS.
- Dashboard alle 20:33: 31 chiusure (29 SHORT, 2 LONG) e PnL netto circa +424,14 USDT; e' una **istantanea successiva** e non va sommata ai vecchi conteggi.
- Il journal `brain_decision` **non conserva lato, stop, leva e confidenza** dopo `RISK_REJECTED`. Senza il file opzionale delle proposte, e' impossibile imputare LONG/SHORT scartati retroattivamente.
- Il controllo `post_ai_guard.py` puo' generare `risk_changed_after_ai` / `risk_rejected_after_ai`, ma il journal non registra il **codice di rifiuto associato a ciascun evento**. Il file `heartbeat.json` e' una fotografia sostituita a ogni tick, non uno storico.

## File creati

1. `ledger.py`: snapshot SQLite in `mode=ro` e `query_only`, unisce `brain_decision` e `paper_open` tramite `decision_event_id` (non per vicinanza temporale), collega il `paper_close` soltanto per PnL **reale**, non per determinare il segnale.
2. `ledger.py` crea per **ogni decisione**, anche `NO_TRADE` e `RISK_REJECTED`, scenari virtuali LONG/SHORT sullo **stesso simbolo** e timestamp con 0/1/3 minuti di ritardo ipotetico. Geometria preregistrata: stop allo **0,74%**, target 2R, orizzonte massimo 24h, fee **6 bp per lato**, slippage **2 bp** sull'apertura e stop. Stop prioritario se entrambe le soglie sono raggiunte nella stessa candela. Gap, candele future incomplete e serie con dati mancanti producono `CENSORED`/`CENSORED_GAP`/`UNAVAILABLE`, mai una vincita/perdita inventata.
3. `analysis.py`: confronta il **lato osservato** di Brain con SHORT permanente e controllo hash-coin agli **stessi** timestamp/simboli; riporta medie in R, **non** finti profitti in USDT. Mostra `paired_n`, copertura dei lati e avvertenze sulla dipendenza statistica.
4. `post_ai.py`: conta per simbolo le approvazioni, le aperture collegate e le `APPROVED_NOT_OPENED_CAUSE_UNKNOWN`. Eventuale `--heartbeat-snapshot` mostra i soli codici più recenti, **mai attribuiti** a una decisione storica. Non classifica automaticamente le 20 approvazioni non aperte come errori del guard.
5. `test_ledger.py`: regressioni sintetiche per snapshot RO, side assente, osservatore ambiguo, mismatch observer/fill, apertura orfana, costi, priorità stop, dati mancanti e report post-AI.

## Dati necessari (copia in area di ricerca, non nel runtime)

Un backup **consistente** in sola lettura del journal e candele 1m cronologicamente ordinate:

```text
/archivio/journal-snapshot.db
/archivio/bitget/BTCUSDT/1m.csv
/archivio/bitget/ETHUSDT/1m.csv
...
```

Ogni CSV deve avere l'intestazione esatta:

```csv
open_time_ms,open,high,low,close,volume
```

Gli intervalli devono coprire il timestamp della decisione fino alla chiusura ipotetica o al massimo a +24 ore, **anche dopo l'ultima decisione**. Se il file ha lacune, le singole simulazioni vengono censurate. Il programma non scarica candele e non chiama Bitget.

## Test locale (nessun GitHub Actions)

Da checkout del ramo isolato, con `pytest` già disponibile:

```bash
PYTHONPATH=. python -m pytest -q research/brain_counterfactual/test_ledger.py
```

Esecuzione da un computer di **ricerca separato dai processi PAPER**:

```bash
PYTHONPATH=. python -m research.brain_counterfactual.ledger \
  --journal /archivio/journal-snapshot.db \
  --run-id brain-v3-paper20261111 \
  --candles-dir /archivio/bitget \
  --out /tmp/brain-controfattuali-ricerca.jsonl

PYTHONPATH=. python -m research.brain_counterfactual.post_ai \
  --ledger /tmp/brain-controfattuali-ricerca.jsonl
```

Per integrare le **proposte future** se l'osservatorio è *separatamente autorizzato e installato*, aggiungere:

```bash
  --observer /archivio/proposal_observations.jsonl
```

L'osservatore non è installato da questa ricerca. In assenza del file, i lati delle proposte respinte resteranno `null`. Il join opzionale per simbolo e timestamp accetta solo corrispondenze **univoche**: qualsiasi collisione/contraddizione resta incerta.

L'output è un JSONL creato **solo se non esiste già** (`open('x')`) fuori dalle cartelle dei dati in lettura. Non crea nuove tabelle, non inizializza schemi, non aggiorna il journal e non modifica alcun parametro di rischio.

### Come leggere i campi

- `opening_state=EXECUTED`: apertura realmente riscontrata e collegata alla decisione via ID.
- `APPROVED_NOT_OPENED_CAUSE_UNKNOWN`: approvata ma senza apertura collegabile. Non è prova di veto post-AI: possono esserci pause, feed, errore o altri fattori.
- `observed_side`: vero solo se riscontrato su `paper_open` o su osservazione opzionale univoca. **Mai** dedotto dal simulatore.
- `hypothetical_only`: esiti **fittizi** (LONG e SHORT) con gli stessi orari/simboli e una politica di stop fissa, non operazioni di Brain.
- `paired_hypotheses`: metriche descrittive del lato osservato contro SHORT e moneta, non alpha certificato; operazioni virtuali sovrapposte non rispettano i vincoli di capitale o correlazione.
- `post_ai_gap_audit`: conteggio delle approvazioni prive di apertura **con causa non nota**.

**Limite cruciale:** `brain_decision.occurred_at_ms` usa il timestamp del contesto costruito **prima** del completamento dell'inferenza DeepSeek. Anche con un file di candele perfetto, gli ingressi simulati a 0 minuti sono idealizzazioni non necessariamente eseguibili. Confrontare 0, 1 e 3 minuti non recupera il ritardo reale senza i log di richiesta/risposta. Non inferire la qualità del modello da uno solo di questi scenari.

## Condizioni prima di eventuali modifiche al motore

- Verificare su journal reale quanti `OPEN/APPROVED` sono collegati a `paper_open` e quanti restano sconosciuti.
- Registrare, **in un futuro intervento distintamente autorizzato**, un identificatore di decisione e un codice di diniego post-AI duraturo, preservando il controllo fail-closed.
- Validare confronti fuori campione per periodo e regime; i trade su BTC/ETH/BNB sono pochi. Non usare intervalli di confidenza ingenui su decisioni correlate.
- Non introdurre automaticamente blacklist ETH/BNB, veto FRRD, modifica della leva minima 20x, stop ATR, esecuzioni di ordini o training del modello.
- I registri controfattuali **non allenano automaticamente DeepSeek**. Una eventuale pipeline di apprendimento richiede una progettazione separata, un dataset verificato e autorizzazione.

**Stato:** implementazione offline e test locali sintetici; **nessuna esecuzione sul journal VPS e nessuna analisi su candele reali completata da questo codice**, perché i dati non sono presenti nel ramo. Nessun deploy, merge, modifica dei bot o GitHub Actions.

## Procedura VPS per il replay reale (senza esportare il journal)

E' disponibile `research/brain_counterfactual/replay_vps.py`: uno script **separato dai servizi di trading** che l'operatore puo' eseguire manualmente tramite Termius. Il codice e' solo Python standard, senza installazione di pacchetti, senza GitHub Actions e senza modifiche ai bot.

**Cosa fa:** verifica il journal Brain PAPER preesistente, crea con `sqlite3.Connection.backup` uno snapshot coerente in una directory privata `/tmp/superbot-brain-research-*`, recupera le versioni del laboratorio dallo **stesso commit GitHub immutabile**, verifica la raggiungibilita' dell'API pubblica Bitget, scarica le candele 1m di otto simboli e produce `counterfactual.jsonl` e `summary.json` *solo nella directory di ricerca*. Non invia il journal a servizi esterni: soltanto richieste GET per dati di mercato pubblici, e il download del codice dal repository GitHub dell'utente.

Per proteggere il runtime si rifiuta di usare un journal mancante o un link simbolico, legge con `mode=ro`, non esegue comandi Docker/systemd, non tocca `/opt/.../journal.db` in scrittura, non usa API autenticate e non esegue ordini. La copia dei dati resta locale alla VPS sotto permessi `0700` e **non viene caricata su GitHub**.

### Uso operatorio

Lo script richiede l'**identificativo completo di 40 caratteri** del commit immutabile. Scaricare lo stesso file da quel commit, validare la sintassi, poi:

```bash
sudo python3 /tmp/brain-replay-vps.py --revision FULL_GIT_COMMIT_SHA
```

Il comando costruisce un rapporto sulla run `brain-v3-paper20261111` e stampa soltanto:

- `BRAIN_REPLAY snapshot_decisions=...`
- `BRAIN_REPLAY candles_BTCUSDT=...` etc., con la **copertura effettiva** e i buchi;
- `BRAIN_REPLAY approvals=...`
- `BRAIN_REPLAY verified_opens=...`
- `BRAIN_REPLAY unexecuted_unknown_cause=...`
- `BRAIN_REPLAY model_side_unknown=...`
- `BRAIN_REPLAY paired_lag_0m/1m/3m=...`
- `BRAIN_REPLAY summary_file=/tmp/.../summary.json`
- `BRAIN_REPLAY RESULT=COMPLETED_WITH_COVERAGE_LIMITS`

`COMPLETED_WITH_COVERAGE_LIMITS` significa **programma eseguito**, non dataset completo e non validazione statistica. Controllare `coverage`, `UNAVAILABLE`, `CENSORED` prima di interpretare le medie R. Se il download di un simbolo fallisce, l'assenza di dati viene mantenuta esplicita. Se Bitget non risponde, si interrompe senza cambiare il runtime.

Per approfondire i risultati, aprire la copia privata di `summary.json` sulla VPS e condividere **soltanto un estratto o lo screenshot**, non il database intero o le credenziali. Lasciare la vecchia run PAPER intatta.

Test offline aggiuntivi:
```bash
PYTHONPATH=. python -m pytest -q research/brain_counterfactual/test_ledger.py research/brain_counterfactual/test_replay_vps.py
```

I test dello script VPS sono **scritti ma non eseguiti** da GitHub Actions. Il replay reale deve essere confermato da output Termius; non dichiariamo di aver avuto accesso SSH alla VPS da GitHub.
