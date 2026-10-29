# Brain Scalp — Gruppo 5 I9/I7 completato come implementazione offline

**Data:** 29/10/2026. **Autore:** ChatGPT (chat normale). **Fonte specifica:** `claude/prompt-chatgpt-brain-scalp-completo-2026-10-29.md`, ramo `diario`, sezione Gruppo 5. **Autorizzazione utente:** «ok procediamo» dopo Gruppo 4.

## Esito verificato e vincoli
- **Motore PAPER** sul ramo `work/brain-scalp-dual-20261028`, HEAD `1f7a67906024b74f575c1c4bf469547abf8dfc60`. CI [40904255227](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40904255227) **SUCCESS** Python 3.10 + 3.11, **101/101 test per interprete** (202 esecuzioni). Controlli automatici che `backend/desk`, `backend/director/brain_free`, file deploy e workflow originari siano immutati: PASS.
- **PWA sperimentale** sul suo ramo separato `work/brain-scalp-dual-app-20261028`, HEAD `0587c081e87488597d772873eca4391dba38c72f`. CI [40904609621](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40904609621) **SUCCESS**: 12/12 test unitari backend Python e build frontend con Yarn, più guardie Git di immutabilità per codice classico e percorsi deploy.
- **Non è stato effettuato alcun merge/deploy**, avvio, accesso operativo al VPS, modifica ai classici Hawk/Bull, Brain Free, dati, journal o portafogli PAPER. Non è stato creato nessun worker H24, servizio WebSocket/REST, connessione a Bitget o chiamata API AI.

## I9 — Metriche del wallet persistenti e verificate

`backend/director/brain_scalp/metrics.py` e `engine.py`:
- Ogni tick calcola/persiste `state['metrics']` con timestamp, `opening_allowed`, `block_reason`, slot usati/liberi, margin used/available (sottraendo anche prenotazioni pendenti), equity solo se marcata da quote fresche, P&L netto realizzato, commissioni pagate, contatore trade giornalieri e complessivi, long/short aperti, durata media di posizioni chiuse e minuti a zero posizioni.
- `scalp_metrics_counters` persistente mantiene totali cumulativi e contatori temporali senza interrogare di continuo tutto il DB. All'UTC rollover si resetta il contatore degli ingressi di quel giorno, non il totale. L'equity incerta è **null**, non viene inventato un dato o portata artificialmente a 1000.
- Per ogni `partial_trade` o `trade_closed`, il realizzato netto somma **solo `event['segment']['net']`**, NON l'aggregato finale della chiusura intera: evita doppio conteggio delle uscite parziali. Le fee pagate sono incrementate dalle fee degli eventi di apertura e uscita (non dai totali delle chiusure che includono entry fee). Non sono dati finanziari certificati, ma metriche di laboratorio.
- Test sui casi: valori nel DB dopo tick, slot vuoti, apertura e chiusura senza duplicati, parziali, quote None/stale, rollover UTC, pausa e margine prenotato.

## I7 — Snapshot JSON atomico, publisher separato dal ledger

`backend/director/brain_scalp/snapshot.py`:
- `build_snapshot` accetta stati SQLite già confermati di entrambi i wallet con identità PAPER esatte; proietta solo campi destinati alla PWA (quote/strategie sensibili non incluse, nessun token API).
- `SnapshotPublisher.publish_if_due(pair,now)` pubblica un JSON completo a intervallo configurabile (default **5000 ms**) **solo quando un futuro supervisore lo invoca**. Lo stato è letto con le garanzie del singolo writer già posseduto da `BrainPair`, senza modificare il ledger.
- `atomic_write` crea temporaneo nella stessa directory, scrive JSON UTF-8 con `allow_nan=False`, `fsync`, `os.replace` atomico. Snapshot precedente non viene troncato in caso di errore pre-rename. Vietati symlink di file target e directory immediata; file max 2 MB. Percorso fornito esplicitamente dal supervisore, **non scritto automaticamente** sul server.
- `read_snapshot` offline valida schema, account e age. Uno snapshot vecchio rimane visibile come `stale` ma **mai come wallet online**; manca/corrotto non diventa un falso nuovo conto.
- Test: doppio wallet separato, throttling/cadenza 5s, writer fermo con snapshot storico, JSON corrotto, foreign account, target symlink e nessuna esposizione del testo completo del prompt/piano.

## Lettura snapshot dalla PWA sperimentale (ramo app separato)

`backend/brain_scalp_snapshot_view.py` e `backend/brain_scalp_view.py`:
- Il GET autenticato `/api/brain/scalp` privilegia lo snapshot verificato dal percorso `BRAIN_SCALP_SNAPSHOT_PATH`, se fornito, altrimenti cerca `<BRAIN_SCALP_DATA_DIR>/brain_scalp_snapshot.json`.
- Snapshot assente: lettura **read-only** SQLite legacy conservata per compatibilità. Snapshot **presente ma corrotto/di altro wallet**: risposta `unavailable` fail-closed, niente fallback silenzioso a un file potenzialmente differente.
- Snapshot non aggiornato (>60s): mantiene visibile l'ultima equity storica, ma `online=false` e `snapshot_stale=true`. La PWA `frontend/src/pages/BrainScalpDashboard.js` mostra un avviso esplicito sui dati storici, le metriche I9 e il timestamp del file. Non finge di conoscere le singole chiusure, che non sono incluse nel riepilogo JSON.
- Nessun endpoint di trading o scrittura aggiunto. I test app verificano snapshot senza DB, stale, corrotto, wallet estraneo, symlink, timestamp futuro e fallback legacy, autenticazione GET-only, e la build frontend.

## LIMITI APERTI e condizioni di rilascio

1. **Manca ancora un processo/supervisore 24/7.** La cadenza 5s è una funzionalità della classe publisher, NON un servizio realmente avviato. Fino al suo collegamento, il backend API può restare sulla lettura SQLite legacy. Non presentare questo lavoro come PWA già aggiornata sul server.
2. Il writer engine e lettore PWA stanno in **due branch diversi**. Prima del rilascio serve una PR di integrazione controllata con test end-to-end, mapping runtime volume JSON e permessi su filesystem, stato di startup e restart, backup verificato e rollback.
3. Il watermark `heartbeat_ms` segnala aggiornamento del wallet; non garantisce disponibilità dell'API del provider. Le metriche modellate non dimostrano win rate o profitto su mercato.
4. La migrazione SQLite richiesta dal Gruppo 3 resta una condizione esplicita: no reset implicito e nessuna perdita di dati/storici.
5. **Gruppo 6 — I8 A/B/C** va scelto dall'utente e non è stato implementato in questo gruppo. Una scelta non autorizza comunque merge, deploy o avvio.
6. Claude può effettuare review indipendente e proporre test, ma per modificare il ramo operativo o attivare il supervisore sono necessarie autorizzazione utente e certificazione separata.

**AI: ChatGPT (chat normale).**


## 29/10/2026 — Gruppo 5: autorizzazione iniziale (attività conclusa, esito sotto)
- Utente: «sei autorizzato», dopo audit in sola lettura. ChatGPT Work prende in carico esclusivamente robustezza dei lettori snapshot contro strutture JSON errate e scadenza/indicatore Online nella PWA senza connessione, con test di regressione.
- Rami esistenti: motore work/brain-scalp-dual-20261028 da 1f7a67906024; app work/brain-scalp-dual-app-20261028 da 0587c081e874. Nessuna duplicazione del publisher o delle metriche già presenti.
- Supervisore H24, provider, merge, deploy, VPS, classici e Brain Free esclusi. Nessun reset/migrazione o modifica dati operativi. I rami e commit iniziali costituiscono i punti di ripristino codice.
- Prenotazione iniziale conclusa; esiti CI e SHA definitivi nel checkpoint successivo. Unico autore ChatGPT sui file di questa correzione.


## 29/10/2026 — Gruppo 5: correzioni post-audit completate, CI verde, NON DEPLOYATO
- Autorizzazione utente «sei autorizzato» eseguita solo per le due correzioni individuate nell'audit. Prenotazione ChatGPT su questi file CONCLUSA; nessuna attività operativa autorizzata.
- Motore: work/brain-scalp-dual-20261028, commit f097801b1836a3864807811c5f9c9e731a4cc789 (base 1f7a67906024). Solo snapshot.py e test_brain_scalp_group5.py: controlli di tipo prima di .get su radice JSON, profiles e wallet; strutture errate restituiscono unavailable senza modificare file/dati.
- CI motore https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40920574261 SUCCESS: 102/102 test Python 3.10 e 102/102 Python 3.11 (204 esecuzioni), guardie immutabilità classici/Brain Free/deploy PASS.
- PWA: work/brain-scalp-dual-app-20261028, commit 9251e6ddf2d68b607fffd73b8383da8f00c687fa (base 0587c081e874). Solo lettore snapshot, test reader, BrainScalpDashboard.js, nuovo BrainScalpDashboard.test.js e CI app isolata. Validazione contenitori JSON e liste wallet; snapshot errato presente non ripiega su SQLite.
- La PWA toglie Online al primo errore di connessione; conserva i saldi chiaramente come storico. Un timer indipendente fa scadere risposta, età snapshot e heartbeat anche se il GET successivo resta pendente; recupero con risposta fresca e cleanup timer/AbortController. Il tempo snapshot più age server evita dipendenza dall'orologio telefono per fonte snapshot.
- CI app https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40920589402 SUCCESS: 14/14 test backend incluse autenticazione/GET-only, 6/6 regressioni React (offline/recupero, GET bloccato/no overlap, age con clock telefono diverso, heartbeat, stale ricevuto, unmount), build frontend e guardie PASS.
- Verifica locale Python 3.12: 115 test motore+reader PASS (test endpoint non eseguito localmente perché FastAPI assente, verificato in CI). Prova sintetica engine reale -> snapshot -> lettore app PASS dopo chiusura writer, due wallet separati e stale offline PASS. Nessuna rete mercato/AI o dato operativo usato.
- Nessun duplicato di publisher/metriche. Confronti Git verificati: esattamente 2 file motore e 5 app; nessun cambio ai classici, Brain Free, strategie, rischio o parametri.
- Aperto: supervisore H24 che invochi publisher esistente, percorso/mount JSON e permessi runtime, verifica browser/dispositivo e ambiente reale, migrazione SQLite esplicita ove necessaria, scelta Gruppo 6. Tutto da autorizzare separatamente; nessun merge, deploy, VPS, reset, archivio o journal operativo toccato.
- Ripristino codice disponibile ai commit base sopra, senza riscrivere la storia. PWA in produzione NON aggiornata da questo lavoro.

AI: chatgpt
