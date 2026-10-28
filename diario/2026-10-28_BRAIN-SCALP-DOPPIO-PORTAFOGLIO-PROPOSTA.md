# Nuova direzione utente — Brain Scalp con due portafogli — 28/10/2026

Stato: richiesta/proposta progettuale; NON autorizzati implementation, merge, restart, deploy o reset. La chat normale ha verificato codice GitHub, NON runtime VPS fresco.

## Cambio di priorità esplicito
- **Hawk e Bull CLASSICI non devono essere toccati**. L'utente li vede riprendere ad aprire e vuole osservarli almeno qualche ora/1–2 giorni. Nessuna modifica a motori, parametri, limiti, prompt, conti, posizioni, job o UI specifica dei classici.
- L'utente vuole il comportamento scalp 1m/5m, H24, multisymbol, long e short, profit-taking dinamico e uso degli slot quando ci sono setup, applicato **al Brain**, con **due portafogli PAPER distinti** come i classici: Brain Hawk (nell'audio «Walk») e Brain Bull. Vuole confrontare risultati e soprattutto comportamento/frequenza dei nuovi Brain con i classici.
- Ambiguità da chiarire prima di sviluppare un cutover o inizializzare i conti: mantenere l'attuale Brain Free V2 da $2000 come terza baseline separata oppure trasformarlo/sostituirlo con Brain Hawk e Brain Bull da $1000 ciascuno? Suggerimento tecnico della chat normale: se l'intento è davvero clone, **conservare l'originale intatto** e aggiungere due nuovi conti PAPER isolati, ognuno $1000 come i classici. Il proprietario deve confermare.
- Nessuna obbligazione di aprire N trade al giorno o profitto garantito. Misurare opportunità, trade, staleness, veto, motivo del rifiuto, rotazione, net ROI e drawdown.

## Verifica repo
- rule-pool HEAD c1a7c91924c92ff7a2a48988dfa0c3bda96aad48; main HEAD 2283bfb1c63959015658904a75d68d6587cca314; Brain runtime V2 code SHA e0021488b47e8b245954a708b139bc4785a4b644 (esito VPS verificato solo precedentemente da Work).
- Brain V2 code in branch work/brain-free-scalp-reframe-20261028/backend/director/brain_free. Config un solo conto 2000 start_cash, max_slots5, max_margin1750, full scan AI ogni 300s, manage ogni 120s, protect poll5s. Esistono circa 26 mercati. Nessun vero pipeline scanner1m5m→AI piano→trigger condizionale.
- Store hardcode `account_id='brain-free-paper'` e `/out/brain.sqlite3` con unico writer lock per root; per 2 nuovi wallet implementare identity+root parametrizzati, senza condividere volume/SQLite né semplicemente avviare due processi sullo stesso percorso. `Runtime` e `Store` impediscono mismatch config: migrazioni esplicite.
- App main `backend/brain_free_api.py` serve soltanto GET /api/brain/free usando BRAIN_FREE_DATA_DIR e `brain_free_view.py` controlla account_id; `frontend/src/App.js` espone /brain con BrainDashboard, BrainFreePanel. Occorrono proiezioni ro isolate, autorizzazione di accesso, navigazione Brain Originale/Brain Hawk/Brain Bull e confronto.
- Lasciare integri tutti i dati, store e archivi del Brain Free V2 esistente; il ramo Brain V2 è divergente da rule-pool, niente merge automatico o rollout di vecchi installer.
- Maggiore frequenza: scanner market data 1m/5m e trigger rapidi; AI valuta shortlist/ragioni e propone piani brevi; esecutore PAPER deterministico e controlli rischio/stop/profitto locale ogni 1–5 sec. Timeframes alti per regime. Leve non artificialmente gonfiate: rispettare tier/fill/liquidazione, loggare motivo del sizing. Per test iniziale si propongono slot10/3, size100–250/150–350 se capitale1000 per wallet, SENZA modificare classic configs.
- Condividere *solo feed* di mercato dove conveniente, MA non il ledger/esecutore/flag di pausa/budget/spesa AI; distinguere log di ciascun wallet e budget/correlazione. Unico writer per singolo account. Evitare doppie istanze che agiscono sullo stesso DB.
- Suddivisione suggerita: ChatGPT nuova architettura Brain multi-wallet e modello piani condizionali; Claude revisione indipendente, replay long/short e rischio; lavori su branch/file separati e confronto via diario. Nessuno assume ownership attiva del codice finché non è concordato il nuovo perimetro.

## Prossimo passo
Chiarire destinazione del Brain originale e del capitale di test. Poi specifica frozen, prenotazione componenti, codifica offline e suite/replay, app read-only, backup e restore prima di qualsiasi futura attivazione. Deploy sempre con OK separato, PAPER only.

AI: chatgpt (chat normale)


## 28 ottobre — preferenza aggiornata e raccomandazione (chat normale)
Il proprietario manifesta netta preferenza per opzione **B**, non mantenere tre Brain attivi: Brain Free V2 attuale è un test che non soddisfa per frequenza, risultati e leva; teme spesa API, carico dati e riduzione qualità se lasciato operativo accanto a due nuovi Brain. Chiede un consiglio; non è ancora un'autorizzazione ad arresto, chiusura posizioni, reset o deploy.
**Raccomandazione ChatGPT: B con archivio, non distruzione.** Alla futura autorizzazione: misurare conto/posizioni attuali, interrompere nuove aperture (se necessario lasciare gestione protettiva delle aperte fino a chiusura tracciata), backup completo SQLite via API e restore verificato, preservare log decisioni, richieste, spese, memoria, foto delle versioni e report; ritirare il processo originale, senza riavviarlo in parallelo. Creare separatamente Brain Hawk e Brain Bull PAPER da **1.000 USD nuovi di prova ciascuno**, con id, database, volumi, budget/spesa e writer distinti: nuova baseline di esperimento virtuale da etichettare apertamente, senza spacciare la ricostituzione del capitale per recupero delle perdite del vecchio Brain. Il precedente equity/saldo rimane congelato nel report di archivio. Uno scanner e feed di mercato condivisi, due valutazioni AI su shortlist compatte invece di analisi duplicate dell'intero universo, due esecutori e conti indipendenti; protezioni locali 1–5s, budget AI con limiti e metriche di token/latenza/costi per wallet. Memoria precedente usata solo come dataset storico attribuito, non iniettata integralmente nei prompt di entrata; nessun veto direzionale permanente basato su vecchie perdite.
**Classici Hawk/Bull invariati** per osservazione 1–2 giorni. Stato: proposta/suggerimento, non modifica tecnica. Decisione operativa/deploy da richiedere separatamente.

AI: chatgpt (chat normale)
