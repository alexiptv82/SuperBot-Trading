# SuperBot V3 — AI Arena: tre Brain PAPER separati (16 novembre 2026)

**Stato del lavoro:** UI sperimentale su branch isolato `work/brain-ai-arena-ui-shadow-20261116`. **Nessun deploy, nessuna modifica ai servizi, nessuna API nuova chiamata, nessun merge.** Le chiavi Qwen e MiniMax non sono state fornite.

## Scelta dell'utente

Per almeno 14 giorni mettere a confronto tre AI *contemporaneamente*, ciascuna con un **proprio portafoglio virtuale di riferimento da 2.000 USDT**:
- Brain DeepSeek: attuale `deepseek-flash`, thinking `high` nella configurazione repository; **non modificarne intanto il prompt o le condizioni di rischio**.
- Brain Qwen: modello da verificare `qwen3.7-plus`, account Alibaba Cloud Model Studio **Singapore**.
- Brain MiniMax: modello API pay-as-you-go da verificare dopo creazione account; **non assumere che il modello M3.1 Flash del piano interattivo sia disponibile nel piano API a consumo**.

Falco e Toro vanno **messi in pausa per nuove aperture**, con i loro journal e backup intatti; NON interrompere i servizi di uscita finché ci sono posizioni aperte. L'utente vuole nasconderli temporaneamente dall'interfaccia principale, non cancellarne dati o strategie. Riattivarli in seguito deve essere possibile.

## Architettura corretta (obiettivo non ancora implementato)

1. Ingresso dati: un singolo snapshot *immutabile* per simbolo/ciclo, identico per tutti i modelli, solo candele chiuse, stesso regime/indicatori ed eventuali segnali di contesto. DeepSeek e sfidanti NON vedono le risposte degli altri.
2. Tre processi/journal indipendenti: `brain-deepseek-paperYYYYMMDD`, `brain-qwen-paperYYYYMMDD`, `brain-minimax-paperYYYYMMDD`; nessuna condivisione di SQLite, slot, capitale, budget AI o conteggio del rischio. Un unico codice di esecuzione **PAPER**, monitor delle uscite e contabilità uguali e testati, ma istanze separate.
3. **Stop e capitale comparabili**: stesso profilo di rischio approvato, stessi dati, fee, slippage, latenza misurata, size/stop/leva determinati dalle stesse regole. Nessun vincolo di leva modificato per favorire un modello. Se l'AI produce una proposta invalida, registrare `REJECTED` senza forzare un fill.
4. Le tre AI sono valutate sia per `NO_TRADE` sia per operazioni effettivamente aperte e chiuse: schema immutabile `decision_event_id` → `paper_open` → `paper_close`, motivi del rifiuto distinti (pre-risk/post-AI), nessuna sovrapposizione non documentata.
5. Costo AI: variabili segrete solo nel servizio VPS, mai frontend, frontend bundle, GitHub o log. Contatore token/costo e tetto giornaliero **per provider**; se una API fallisce, soltanto quell'istanza va in NO_TRADE, senza contaminare gli altri journal.
6. UI/API: GET autenticato in sola lettura `/api/v3/arena`, protetto dalla stessa sessione dell'app, restituisce `portfolios.qwen/minimax` con `source=arena_independent_journal_v1`, `mode=paper`, `portfolio_id`, `state`, `initial_capital=2000`, `run_id=brain-<provider>-paperYYYYMMDD`, `open_positions`, `closed_trades`, `realized_pnl`, `unrealized_pnl`, `equity`, `settled_equity`, `win_rate`, `margin_in_use`, `day_pnl`, `updated_ms`. La UI rifiuta qualsiasi dato con run ID non coerente.
7. Chiudi ora: comando PAPER **separato per provider/position_id**, con log e permessi equivalenti all'attuale Brain. Nessuna chiamata alla route DeepSeek per chiudere una posizione Qwen o MiniMax. Non aggiungere un pulsante fintamente funzionante finché il servizio shadow close non è collaudato.
8. Performance del test: punto di partenza `T0` comune e visibile nella UI, cronometro 14 giorni dal momento in cui tutti e tre i runner paper sono pronti. Distinguere storico antecedente (archivio) da risultati **misurati dopo T0**. Le operazioni ancora aperte alla fine si riportano come `floating`, non si chiudono a mezzanotte o a fine test.
9. Bilancio 2.000 ciascuno: **non reinterpretare il saldo della run Brain esistente come 2.000 se è già cambiato**. Preferire una nuova run Brain DeepSeek con 2.000 allineata alle due shadow (preservando la run precedente come archivio) oppure, previo accordo esplicito, una baseline T0 normalizzata senza alterare il journal. Verificare e gestire posizioni ancora aperte **prima del cutover**. No reset silenziosi.

## Cosa esiste già sul branch

- `frontend/src/brainArenaModel.js`: mapping di DeepSeek da endpoint PAPER già esistenti. Qwen/MiniMax sono assenti finché non esiste il GET autenticato e i loro journal; i risultati assenti rimangono trattini, non 0.
- `frontend/src/pages/BrainArena.js`: nuova pagina con tre card selezionabili e schede `Panoramica / Posizioni aperte / Storico / Performance`. Se la sorgente dei dati è assente, informa chiaramente che non sono disponibili trade.
- `frontend/src/App.js`: route `/arena` inserita senza modificare quelle classiche; redirect dalla home solo con `REACT_APP_BRAIN_ARENA_PREVIEW=1`.
- `frontend/src/components/NavBar.js`: con la stessa flag, barra PAPER focalizzata su `AI Arena` e `Agenti`; le pagine /classic, /overview, /trades, /performance restano **accessibili per archivio**.
- `REACT_APP_BRAIN_ARENA_SHADOW_API=1` abiliterà in futuro il nuovo endpoint read-only, MA non va abilitata finché il backend e le istanze shadow non sono verificati.
- `frontend/src/brainArenaModel.test.js`: 5 test unitari scritti. **Non eseguiti** su GitHub Actions; frontend non compilato né distribuito.

## Gate necessario per il rilascio

1. API keys create dall'utente e inserite sulla VPS in variabili/secret file privato con accesso del servizio, **mai in chat**; piccole chiamate di connettività separate, costi misurati, modello MiniMax effettivo verificato. Non esiste garanzia di accesso gratuito.
2. Backend multi-run isolato + tre monitor uscite/test journal SQLite WAL/backup/risposte scadute/stop e chiusura manuale; nessun ordine vero.
3. Audit delle 3 unit PAPER (portfolio/run ID, bound risk, no shared journals, startup cooldown, equity floor 450, stop service sano); test sintattici e di integrazione, senza consumare Actions.
4. Controllare Falco e Toro: conteggio posizioni aperte, mettere in pausa **solo nuove aperture**, mantenere exit service attivo, preservare storico; nessuna chiusura forzata.
5. Build & preview UI poi pubblicazione separata **solo dietro autorizzazione dell'utente**; recupero rapido della precedente dashboard con backup.
6. Avvio contemporaneo della competizione T0 dopo che i tre wallet hanno **2.000 USDT veri PAPER** iniziali. Non confondere il fatto che le tre card oggi visualizzino 2.000 come riferimento con un runner già attivo.
7. Durante le due settimane, app aggiornata ogni 30s, confronto di win rate, PnL realizzato/floating, commissioni, numero di trade, drawdown, rischio, NO_TRADE, costi API e latenze. Nessun vincitore automaticamente dopo 14 giorni: servono condizioni di mercato diverse e controllo fuori campione.

## API ufficiali

- Qwen: [Alibaba Cloud Model Studio](https://modelstudio.console.alibabacloud.com/?apiKey=1), regione Singapore `ap-southeast-1`. Usare chiave **pay-as-you-go**, non Coding Plan, endpoint compatibile iniziale `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`. Con workspace dedicato usare il dominio del workspace.
- MiniMax: [MiniMax Open Platform Global](https://platform.minimax.io), Account → API Keys; API OpenAI-compatible indicativa `https://api.minimax.io/v1`. Per confronto H24 utilizzare chiave **pay-as-you-go** (non subscription interattiva).
- DeepSeek: chiave già presente nel runner attuale, **non riutilizzarla per gli altri due fornitori**.

**Stato nel presente:** solo prototipo UI, nessuna AI sfidante operativa, Falco/Toro non fermati e nessuna modifica ai bot PAPER.
