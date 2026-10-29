# Brain Scalp dual PAPER — Gruppo 2 concluso offline (ChatGPT)
**Data:** 29 ottobre 2026. **Approvazione utente:** «ok procediamo» in risposta alla conclusione del Gruppo 1. **Fonte:** `claude/prompt-chatgpt-brain-scalp-completo-2026-10-29.md` nel ramo diario.

## Perimetro e vincoli
Lavoro esclusivo sul ramo motore `work/brain-scalp-dual-20261028`, nessun merge, deploy, chiamata AI reale, connessione Bitget o VPS. Intatti i classici `backend/desk/`, Brain Free V2 `backend/director/brain_free/`, app `main` e `work/brain-scalp-dual-app-20261028`, secrets, dati e journal. Confronto Git `e0021488..fed20869` registra variazioni solo in `backend/director/brain_scalp/`, test, documento di review e workflow CI offline. Il CI prova inoltre formalmente che i componenti protetti e la configurazione di deploy sono invariati.

## Correzioni, una per funzione con commit e test

### I2 — Target inferiori ai costi
- Commit `fb4dc030`: `engine.py` ora verifica che l'escursione lorda attesa verso TP copra **2× i costi roundtrip stimati** (entrata/uscita, fee + slippage). Con fee 0,06% e slippage 0,02% per lato, roundtrip conservativo 0,16% e minimo movimento lordo richiesto 0,32%. Il modello fa questo controllo **sia su submit/trigger iniziale sia prima del fill**, perché il prezzo reale potrebbe essere peggiorato rispetto al trigger.
- Il rifiuto è tracciato come `target_below_costs`; test per LONG/SHORT, target 0,05% rigettato, target 0,35% accettato al submit, ma rifiutato al fill quando la quota ha già consumato il margine. Non alterati gli stop/target dei piani, solo ammissibilità.

### I3 — Ridimensionamento entro limiti immutati
- Commit `62dd09a4`: `_resize_for_budget` cerca, a partire dalla leva originaria verso il basso, una coppia leva/margine ammissibile, limitando spesa, margine allocato ad altri piani, risk/trade (50 USD), risk/portfolio (150 USD) e min/max margin del wallet. Margini arrotondati **per difetto** al centesimo, nessun incremento di leva o margine rispetto al piano AI.
- A dimensionamento riuscito, registrato `plan_resized` (prima/dopo margin, leverage, risk budget) e verifica sul **rischio effettivo dopo normalizzazione exchange**. Se neanche il minimo è fattibile: evento `below_min_margin_after_resize`, piano eliminato, **nessuna apertura e nessun capitale sottratto**.
- Il caso esistente che prima si aspettava un rifiuto (250 USD leva45 stop98) è aggiornato per verificare un ridimensionamento. Altri test provano nessuna riduzione sotto il minimo, persistenzza dopo riavvio, nessun incremento involontario.
- Nota: questa correzione non inventa una leva minima 20× nello spec Brain (attualmente non c'è). Può ridurre anche sotto 20× per rispettare le protezioni; vietare leve inferiori richiederebbe decisione successiva, potenzialmente aumentando rifiuti.

### B2 — Gaps di candele 1m e protezioni
- Commit `7e65ff0b` nuovo `backend/director/brain_scalp/gap_repair.py`: parser di barre 1 minuto *chiuse* e OHLCV validi, rilevamento lacune temporali (anche da cursor posizioni aperte), backfill **mediante funzione iniettata** `fetcher(symbol, start_ms, end_ms)`. Nessuna API/network/supervisore incluso. Rifiuta barre future, duplicati incompatibili, prezzi invalidi, ritorni parziali e gap troppo grandi; max 8 intervalli e 240 barre per intervallo. Merge soltanto atomico della serie completa di un simbolo (nessuna pubblicazione parziale se fallisce un intervallo).
- Commit `cc1b005c`, `96de32b1` integrano `BrainPair(candle_backfill=...)`: un medesimo snapshot di prezzi riparato viene passato a Hawk/Bull prima dei tick; usa cursor veri `last_bar_ms` dalle posizioni, senza duplicare scritture o chiamate network. Commit `c231f0de` integra gli eventi `gap_backfilled`, `gap_backfill_failed`, `gap_unresolvable` in transazione con il wallet.
- Se manca un tratto della storia e non si può fare backfill, **il simbolo viene quarantinato** via `coverage_gaps` e per una posizione aperta `coverage_complete=False`. Non si dichiara un prezzo fittizio. Se il backfill riesce prima che la candela mancante sia processata, lo stop storico può essere riconosciuto in modo corretto.
- **Limite intenzionale di sicurezza:** se un gap è già stato attraversato da una posizione aperta e il suo cursor è avanzato oltre l'intervallo ignoto, il flag resta bloccato finché un replay/procedura esplicita non verifica la protezione mancata. Non basta un feed sano successivo per dire che il passato è stato riconciliato. Il fix evita il lock quando il buco viene recuperato preventivamente; una procedura completa di reconciliation rimane prevista con il futuro supervisore.
- Non abbiamo aggiunto un fetch HTTP pubblico reale; **la capacità di backfill è ancora solo offline**, in attesa dell'integrazione feed Bitget nel prossimo lavoro autorizzato.

## Verifiche, CI, limiti
- Commits di test: `a7bfae1d` aggiorna asserzione preesistente del cap rischio; `fe614aa0` aggiunge `backend/tests/test_brain_scalp_group2.py`; `fed20869` corregge il generatore di piani usato da quei test.
- Workflow `.github/workflows/brain-scalp-dual-ci.yml` aggiornato con `backend.tests.test_brain_scalp_group2`, commit `c3b15c96`.
- **GitHub Actions RUN 40841694288: SUCCESS**, Python **3.10** e **3.11**, **42/42 test per interprete (84 esecuzioni PASS)**. Suite precedente Gruppo1 inclusa, più Gruppo2 (I2/I3/B2) e test di base. La prima esecuzione del gruppo aveva ERROR di test causati da fixture non parametrizzabile, corretto prima di certificare il run verde.
- Non è un replay di profittabilità su 60 giorni, né prova che Brain Scalp produca P&L positivi. Gli ingressi condizionali, feed pubblico/REST, AI H24 e runner deploy NON sono stati abilitati.
- Le modifiche I2/I3 sono garanzie di rischio, **non nuove soglie strategiche richieste dall'utente** al di fuori della specifica approvata.
- Il secondo stato `STATO.md` deve collegare questo report.

## Stato alla consegna
**Gruppo 2 completato e testato offline. Fermarsi e chiedere OK prima del Gruppo 3** (I5 stop giornaliero latched e config hash, I1 gestione profitti). Gruppo 6 ancora in attesa della scelta utente A/B/C. Nessun merge/deploy o intervento ai classici o Brain Free.

Link: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40841694288
Branch: https://github.com/alexiptv82/SuperBot-Trading/tree/work/brain-scalp-dual-20261028

AI: ChatGPT (chat normale)


## Aggiornamento test di sicurezza B2 — 29/10 (dopo prima CI verde)
Dopo la prima certificazione a 42 test, è stato individuato e corretto un rischio ulteriore: su un backfill non risolto, il lettore di barre protettive **poteva avanzare il cursore oltre il minuto ignoto**, precludendo la verifica retrospettiva dello stop. In `coordinator.py` ora si passa al motore soltanto il prefisso di barre chiuse **contiguo** fino al primo buco (commit `ba91eb2e`); in `engine.py` viene conservato `scalp_gap_cursor_ms` e la quarantena può essere rimossa **solo dopo** il replay consecutivo di tutte le barre mancanti, o la chiusura protettiva prodotta dal replay (commit `554873a3`). Non si liberano posizioni già marcate UNKNOWN in passato senza il nuovo cursore di quarantena.

Aggiunti 3 test nuovi nel file `backend/tests/test_brain_scalp_group2.py` (commit `0dfb2350`): (1) backfill fallito NON fa saltare il minuto, (2) riparazione tardiva ripercorre il minuto con uno stop reale e chiude il PAPER, (3) riparazione verificata senza stop ripristina la copertura soltanto al termine del replay.

**Nuova CI certificata:** [GitHub Actions 40859967271](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40859967271) — **SUCCESS Python 3.10 e 3.11, 45/45 test per interprete, 90 esecuzioni in totale**. Gate invarianti del workflow (classici, Brain Free, deploy) entrambi PASS. HEAD verificato del branch di laboratorio `0dfb2350e6875f728f84fd9b127256895d6b7467`. Il vecchio report riferito a 42/42 è superato da questa nuova prova, non va usato come CI finale.

**Limiti:** test su dati sintetici in runner isolati (no rete), non sostituiscono replay Bitget DEV/VAL/TEST o test d'integrazione con REST/backfill reale, API Claude e reale worker. La connessione al feed non è stata implementata e nessun deploy è autorizzato. Chiedere OK per il Gruppo 3 (I5/I1) soltanto dopo presentazione dei risultati.

AI: ChatGPT (chat normale)


## Verifica indipendente del 29/10 — chiusura definitiva Gruppo 2, recupero feed ripristinato

La verifica successiva ha trovato un ulteriore caso limite B2 dopo i 45 test PASS: quando una posizione PAPER era stata quarantinata per dati 1m mancanti e il feed upstream forniva poi **direttamente** la serie completa, senza invocare il provider di backfill, nessun evento `gap_backfilled` veniva emesso e il flag `scalp_gap_cursor_ms` poteva restare presente indefinitamente nonostante i dati fossero disponibili.

**Corretto solo nel motore Brain Scalp:**
- `engine.py` accetta anche `gap_history_complete` come **candidato a recovery**, non come permesso automatico di apertura; verifica che le barre successive al cursor originale siano contigue e siano state percorse da `protect()` **prima** di togliere la quarantena. Commit `0fd36a36`.
- `coordinator.py` riconosce le posizioni in quarantena e un feed ripristinato già verificato da `repair_markets`, genera l'evento `gap_history_complete` solo se non sono presenti errori/gap irrisolti. Il wallet conserva la verifica finale sulla sequenza reale. Commit `fc0ca0da`.
- Due nuovi test offline `test_b2_upstream_feed_restores_full_history_without_fetcher` e `test_b2_upstream_restored_stop_bar_is_replayed_before_unquarantine`: uno prova sblocco dopo replay senza attraversamento stop; il secondo prova la **chiusura protettiva** della posizione se lo stop risultava colpito nella candela recuperata. Commit `c5345f2b`.

**CI finale valida:** [GitHub Actions 40883165583](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40883165583), **SUCCESS Python 3.10 + 3.11, 47/47 test su ciascuno, totale 94 esecuzioni**. Inclusi i gate di immutabilità `backend/desk`, `backend/director/brain_free` e deploy. Supera i risultati precedenti di 42 e 45 test. Branch HEAD verificato `c5345f2b2f8dd12e5593d36df8aaadd6dd78c7ec`.

**Nessun merge, deploy, modifica alla VPS, classici, Brain Free, portafogli PAPER o worker.** Nessuna connessione HTTP/Bitget/Claude API aggiunta. I2/I3/B2 sono finiti sotto il perimetro offline. **Gruppo 3 (I5/I1) non avviato: richiede un nuovo OK esplicito utente.**

AI: ChatGPT (chat normale)
