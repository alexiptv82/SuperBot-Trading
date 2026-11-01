# SuperBot — chiudi SOLO il trade selezionato (Falco, Toro, Brain)

**Mandato utente 2026-11-01:** quando l'utente vede una posizione in profitto che vuole monetizzare, può chiudere QUELLA posizione; tutte le altre, LONG o SHORT, rimangono aperte. Funziona per Falco, Toro e Brain; una chiusura attestata può diventare un insegnamento dopo conferma. Nessun threshold percentuale imposto, non è `Chiudi tutto`, non è un comando per chiudere tutte le posizioni del medesimo symbol.

**Stato di implementazione:** pure contract `backend/director/single_trade_close_contract.py` su ramo `work/manual-single-trade-close-contract-20261101`, test in isolamento; NESSUN API/consumer operativo collegato, NESSUNA possibilità di inviare ordini. Non fare deploy, merge o modifica a `main` senza autorizzazione.

## Conclusioni della ricognizione sorgenti

- **Classici:** `backend/desk_view.py` in main offre `command_close_position(data_dir, symbol)` e app `frontend/src/components/LiveParts.js` ha conferma «Chiudi ora» su posizione. Il comando esistente usa `close_position.flag` con lista di **simboli**, non contiene ID della posizione. Il `backend/desk/cli.py` di main non chiama `_check_close_position_flag`: quindi non dichiarare l'esecuzione garantita nel bot oggi distribuito. La funzione che consuma la coda esiste invece sul ramo `work/classics-teaching-completion-20261031`, con `HB['close_position']=True`, ma è symbol-scoped: non ha controllo ID/stessa run. La presenza del codice nel ramo non equivale a rilascio.
- **Conto classico:** `backend/desk/engine.py` conserva `Position.id` e `open_ms`, con `positions[symbol]`; una stessa posizione può contenere più ingressi DCA o split. Per la richiesta dell'utente, «un trade» è una **posizione visibile**: tutti gli ingressi DCA aggregati appartengono a quel trade. Chiudere una sola gamba DCA richiederebbe un altro progetto. Nessuna chiusura parziale nel contratto iniziale.
- **Brain:** `backend/director/brain_free/execution.py` nel ramo `work/brain-completion-20261031` memorizza `positions[symbol]` con `id`, `open_ms`, `side`; la funzione `close(...)` attuale è un meccanismo di accounting PAPER del motore, non necessariamente un comando UI autorizzato dall'utente. I componenti operator/teaching precedenti non danno automaticamente un percorso di chiusura singola end-to-end.

## Nuovo contratto esatto (SOLO validazione, default no execution)

Richiesta confermata: `schema=superbot-single-trade-close-v1`, `request_id` idempotente (32 caratteri hex), `account_id` (hawk|bull|brain), `run_id` della run specifica (classici run_no intero, Brain experiment_id stringa), `position_id` intero, `symbol`, `side` -1/+1, `open_ms` originale, `created_ms`, `mode=paper`, `action=close_full`, `confirmed_by_user=true`, `intent` (profit_sufficient|trend_changed|risk_excessive|other).

Controlli fail-closed: presenza e freschezza dell'istantanea wallet autorevole (30s, temporaneo per test, da tarare su feed/heartbeat reali), no richiesta più vecchia di 90s, account/run/ID/lato/open_ms esattamente corrispondenti, un solo match sul simbolo, no posizione già scomparsa, quantità positiva, no comandi doppi secondo elenco ID già consumati. La validazione produce SOLO un ticket `may_execute_orders=false`, `may_change_wallet=false`, `needs_wallet_owner_recheck=true`. Non genera ordine né modifica stato.

**Elemento essenziale ancora da implementare prima dell'uso:** il bot che è **owner del wallet** deve ricevere ticket da API autenticata con protezione CSRF e doppia conferma, bloccare durabilmente la request (idempotenza attraverso riavvii), ricaricare posizioni e controllare ID/open_ms/run **all'ultimo istante sotto il suo lock**, poi eseguire una sola close PAPER, confermare la persistenza e rispondere `CLOSED` oppure `NOT_CLOSED`; gli altri simboli restano intatti. Un esito ambiguo non deve causare chiusure ripetute; mai tentativi live finché l'utente non li autorizza separatamente.

**Apprendimento:** solo una ricevuta dal writer, con `persisted=true`, `kind=trade_closed`, `source=manual_user`, request/account/run/position ID corretti, target non più nel wallet e PnL/margine netto verificati, può diventare una *bozza* lezione con ROI netto sul margine. `user_confirmation_required=true`, `changes_strategy=false`: mai cambiare la strategia dopo un singolo clic. Riutilizzare le code e le lezioni append-only già create in `work/classics-teaching-completion-20261031` senza cancellare memorie.

## UI desiderata, stesso comportamento nei tre portafogli

Scheda di ciascun trade: simbolo, LONG/SHORT, prezzo ingresso/attuale, margine, leva, PnL netto stimato, ROI netto stimato e pulsante `Chiudi QUESTO trade`. Conferma con ID e lato, profitto stimato, avviso slippage e commissioni. Al clic: `richiesta ricevuta` non equivale a `chiusura eseguita`; attesa di conferma definitiva wallet. Quando CLOSED, soltanto quella riga scompare dagli aperti, compare nello storico e propone scelta del motivo di chiusura da imparare. Altri trade non si toccano.

## Gate

Pure request/target/lesson contract + test = pronto in ricerca. API autenticata/operator inbox/owner-close e UI identica su classici + Brain = ancora da implementare. Staging app/PAPER = NON autorizzati. LONG Shadow PR #26 resta separata e NON mergiata. Brain attuale libero bocciato per futuro rilascio. Protezione 450 USDT e SHORT invariati.