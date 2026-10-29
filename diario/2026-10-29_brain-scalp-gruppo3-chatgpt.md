# Brain Scalp dual PAPER — Gruppo 3 I5/I1 COMPLETATO OFFLINE

**29 ottobre 2026 — ChatGPT (chat normale)**  
Mandato: autorizzazione utente «Okay, procedi» successiva al Gruppo 2. Specifica integrale Claude: `claude/prompt-chatgpt-brain-scalp-completo-2026-10-29.md` sul branch `diario`.

## Esito e autorizzazioni

**CI finale: [GitHub Actions 40899772032](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40899772032) — SUCCESS su Python 3.10 e 3.11, 71 test PASS ciascuno (142 esecuzioni).** Sono stati verificati i test dei Gruppi 1, 2 e 3, senza network, API keys, ordini o connessioni reali.

Lavoro esclusivamente sul ramo `work/brain-scalp-dual-20261028`; motore `backend/director/brain_scalp/`, test dedicati e workflow CI offline. **Non sono stati modificati `backend/director/brain_free/`, `backend/desk/`, deploy, classici Hawk/Bull, PWA app, `rule-pool`, VPS Singapore, Brain Free, journal né portafogli PAPER. Nessun merge o deploy.**

## I5 — Stop giornaliero a latch fino al cambio UTC

### Comportamento implementato
- Stato SQLite per wallet inizializzato con `daily_stop_triggered=False` e `daily_stop_day` (giorno UTC intero). Nel tick si usa `now//86400000`, **non** l'orologio reale della macchina: replay deterministico, senza lookahead e coerente con il `last_ms` monotono.
- Quando l'equity completa, valutata da quotazioni **recenti e valide**, attraversa la soglia `start_equity × (1-daily_stop_pct)`, il wallet scrive `daily_stop_latched` una sola volta. Anche se l'equity recupera, le nuove aperture restano bloccate fino al giorno UTC successivo. **La gestione protettiva delle posizioni già aperte non viene disattivata**.
- Il rollover UTC ripristina il diritto a nuove aperture solo quando tutti i simboli aperti hanno marcature valide e recenti; un prezzo None, NaN o stale non può stabilire una base giornaliera falsa. Scrive `daily_stop_reset_utc` con il nuovo riferimento di equity.
- Anche `submit()` respinge i piani quando lo stop è latched e richiede che, al nuovo giorno, sia già avvenuto un tick di rollover. In nessun caso la prenotazione manuale è un bypass del latch.
- Si ricontrolla l'equity **dopo** le uscite fisiche/di profitto e **prima** dei nuovi ingressi dello stesso tick: fee, slippage e realizzi possono fare superare la soglia anche se la valutazione precedente era ancora sopra.
- Mantiene invariati i limiti di rischio già fissati nel `WalletSpec` (daily_stop_pct 20%, kill equity 450 USDT PAPER); non introduce la chiusura forzata di posizioni al raggiungimento dello stop.

### Config hash: niente reset impliciti
- `store.py`: nuovo `wallet_spec_digest()` SHA256 deterministico sui parametri di slot, margini, capitale, budget rischio, stop, kill equity e scadenza piani. Ogni nuovo wallet SQLite memorizza il digest invece della stringa fissa.
- Se un file esistente presenta una fingerprint precedente/mismatch o manca lo schema del latch, `WalletStore.load()` rifiuta l'apertura con `explicit_config_migration_required` o `explicit_daily_stop_migration_required`. **Non azzera, non converte automaticamente e non elimina dati o posizioni.**
- ⚠️ I wallet offline creati con i commit precedenti del laboratorio necessitano quindi **migrazione esplicita e verificata dopo backup**, prima di poter essere riaperti con questa versione. Nessuna migrazione è stata effettuata sui dati preesistenti. È un gate di compatibilità, non un'istruzione ad azzerare.

## I1 — Protezione profitti con contabilità del netto

### Break-even dinamico
- Aggiunta `_breakeven_observed_quote()`, che risolve il prezzo teorico di pareggio netto usando **fill d'ingresso, qty, commissioni in ingresso, commissioni previste all'uscita, slippage modellato all'uscita e funding accumulato**. Non è il semplice `entry*(1+fee+slippage)` del pseudocodice: quello non copre correttamente il ciclo completo di costi.
- Quando `peak_net >= breakeven_after_usd` (default al valore esistente `protect_after_usd`), si stringe monotonicamente lo stop e lo si normalizza al tick di prezzo dell'exchange. Il costo funding viene ricontrollato ai tick successivi e, se aumenta, lo stop netto si può stringere ancora. Se la soglia è già stata attraversata al prezzo osservato, si chiude alla quotazione osservata (senza creare uno stop impossibile).
- **Non garantisce profitti reali**: gap di mercato, nuove commissioni, variazioni di funding o fill peggiore dello slippage stimato possono comunque portare il netto sotto zero.

### Giveback e trailing
- La protezione giveback scatta se `peak_net >= protect_after_usd` e `net <= 0,65*peak_net`, **anche quando net è negativo** (rimossa la vecchia guardia `net>0`).
- Opzionale `trail_bps`: trailing direzionale basato esclusivamente sul miglior prezzo **effettivamente osservato** in quote recenti, senza utilizzare massimi/minimi futuri delle candele. Non allenta mai lo stop; i livelli sono normalizzati a `price_step`.
- Gli stop e target fisici su candele 1m chiuse mantengono precedenza sulle protezioni euristiche a quote. Il feed con coverage gaps irrisolti non autorizza nuove modifiche strategiche basate su prezzi storici incompleti.

### Schema piani e opzioni
- `plans.py` aggiunge campi **opzionali con default None** e validazione conservativa:
  - `breakeven_after_usd` numerico non negativo, facoltativo;
  - `trail_bps` intero in intervallo ammissibile, facoltativo;
  - `scale_out` elenco ordinato di max 3 step `{net_usd, fraction}`, soglie crescenti e frazioni cumulative non superiori a 1; le frazioni eseguibili si applicano **alla quantità residua** e sono vincolate ai minimi contratto;
  - `invalidate_price` livello sul lato opposto all'ingresso che, se attraversato prima del trigger, annulla il piano anche quando il wallet è in pausa; dopo l'ingresso chiude la posizione, qualora lo stop fisico non abbia già agito.
- Nessuna nuova impostazione strategica obbligatoria: piani precedenti senza campi opzionali continuano a essere parsabili, nel nuovo schema wallet. `scale_out` produce eventi tracciabili e non ignora limiti quantità/notional.

## Test Gruppo 3 e percorsi critici

Nuovo `backend/tests/test_brain_scalp_group3.py`, **17 test** (71 totali nell'intera suite, contro 54 pre-Gruppo3) su:
- Latched dopo perdita, non si sblocca sul rebound, resta dopo chiusura/reapertura SQLite.
- Reset soltanto al giorno UTC e soltanto con mark fresco e completo; blocco submit prima del rollover.
- Migrazione necessaria per fingerprint rischio modificata o snapshot legacy, mantenendo il DB originale.
- Stop dopo chiusura con costo realizzato (prima di nuovi piani), tolleranza a quote stale che non creano finti latch.
- LONG e SHORT break-even netto considerando fee/slippage/funding; riaggiustamento BE per funding successivo.
- Giveback da profitto a perdita; trailing monotono; parziale e persistenza dopo riapertura SQLite.
- Invalidazione condizionale prima e dopo apertura; rigetto parametri opzionali scorretti.

Le regressioni introdotte dalle prime versioni del nuovo test erano **errori di fixture** (helper del piano non accettava keyword, valore protect_after oltre i bound), non bug osservati nella produzione: corrette prima dell'esito finale verde. L'ultima CI ha inoltre verificato i gate Git che impediscono modifiche al codice classico, al Brain Free originale e ai workflow di deploy.

## Limiti e prossimi gate

1. **Resta una simulazione PAPER offline.** Non ci sono websocket REST Bitget H24, worker produttivo, chiamate DeepSeek, matching testato contro trade reali o certificazione di profittabilità. Nessuna apertura è stata eseguita su exchange o VPS.
2. La protezione daily stop non forzerà la chiusura delle posizioni aperte: la perdita giornaliera finale può superare il limite in caso di gap o perdita successiva. È un gate nuove aperture, non un tetto garantito a saldo finale.
3. Prima di integrare il ramo motore con altri rami o dati esistenti, occorre progettare una **migrazione SQLite con backup/restore e revisione manuale**, senza cancellare storico/pending plans.
4. Il Gruppo 4 (I6 + bug scanner/plans) **non è iniziato**: richiede l'OK separato dell'utente dopo il Gruppo3. L'opzione I8 A/B/C del Gruppo6 rimane non decisa.
5. Claude può eseguire revisione indipendente e proporre test offline senza modificare i classici, la PWA o autorizzare un deploy.

**Riferimenti:**  
- [GitHub Actions 40899772032](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40899772032) — CI verde 71/71 per Python.  
- [Ramo motore](https://github.com/alexiptv82/SuperBot-Trading/tree/work/brain-scalp-dual-20261028).  
- Documento sorgente Claude: `claude/prompt-chatgpt-brain-scalp-completo-2026-10-29.md`.

AI: chatgpt (chat normale)
