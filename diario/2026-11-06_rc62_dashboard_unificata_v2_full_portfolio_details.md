# SuperBot V3 RC #62 — dashboard unificata completa Falco/Toro/Brain

**Checkpoint:** 6 novembre 2026, solo sviluppo PR #62 DRAFT. **Non è stato fatto alcun deploy, merge, riavvio o reset VPS**. Le storie Falco/Toro/Brain restano intatte. Modalità PAPER.

## Intento utente

Una dashboard *nuova* con tre portafogli ben visibili, ma con tutte le informazioni e il livello di dettaglio delle pagine precedenti Falco/Toro, e Brain con una scheda ugualmente completa: **tutte le operazioni aperte, LONG/SHORT, simbolo, leva, margine, prezzi, P&L, stop, storico dei trade chiusi e controllo manuale PAPER**. Claude e la logica SHORT originale di Falco/Toro non devono cambiare; S25 LONG e segnale cambio-trend sono le sole migliorie alle strategie classiche.

## Audit e correzioni introdotte

- Baseline PR #62 da `f46b267d3ead008816383a2c1da513c5ff03307f`, ultimo commit al checkpoint `027307c4729f7981f4cbe40ee03d8ebd867ca510`.
- `backend/v3_api.py`: endpoint read-only `GET /api/v3/overview` aggiunge per i classici **equity, cassa, profitto giornaliero, posizione dettagliata (direzione/leva/margine/prezzo/scadenza/prezzi stop/obiettivo/liq/ROI/P&L) e ultimi venti trade chiusi**, riutilizzando **solo i lettori esistenti** di `desk_view.py`; restituisce informazioni di provenienza del prezzo per non spacciarlo come live se è un ultimo prezzo del bot o manca. I valori decimali sono stringhe; salvataggi del trading NON toccati.
- `GET /api/v3/brain/trades` aggiunge a tutte le posizioni aperte **margine reale, quantità, prezzo ottenuto dal ticker (se disponibile), apertura e ROI**; gli esiti chiusi riportano **leva, margine, prezzo ingresso/uscita, commissioni e P&L netto USDT** in aggiunta ai basis point già presenti. Non viene inventato un prezzo quando il ticker non risponde.
- Per la scheda Brain di overview sono stati aggiunti **conteggio trade chiusi e win-rate** da EventJournal; la UI somma soltanto P&L marcati con prezzo disponibile e mostra ‘—’ se è ignoto.
- `frontend/src/pages/Overview.js`: tre schede PAPER indipendenti con visualizzazione mobile-first e griglia a colonne adattive fino a 1200px. Falco/Toro mantengono le vecchie funzioni, accessibili alla rotta `/classic`, senza perdere trade aperti/chiusi. Brain presenta trade aperti, leva, margine, stop, prezzo corrente, P&L, ROI, strategia, ultimi trade chiusi e tabellone di apprendimento.
- `OverviewCloseControls.js`: **bug risolto**: quando un vecchio worker non annuncia `close_position`, la UI mostra comunque tutte le posizioni con dettagli; **nasconde solo i pulsanti**. Il prezzo del bot è etichettato ‘Ultimo prezzo bot’, non ‘Prezzo live’. Le chiamate manuali mantengono l'autenticazione e i canali esistenti.
- `frontend/src/App.js` e `NavBar.js`: la root PAPER `/` reindirizza alla nuova `/overview`; la dashboard classica prima alla root si trova a `/classic`, con tab dedicata. Le rotte LIVE restano inalterate.
- Test `backend/tests/test_v3_dashboard_unified.py` e nuovo `frontend/src/pages/OverviewPortfolioDetails.test.js`: dati fittizi, verifica di leva, margine, stima P&L, dati closed, tre portafogli, prezzo assente, compatibilità file del journal.

## CI, stato al checkpoint

- **Backend dashboard: SUCCESS** su `027307c`; test e controllo degli endpoint autenticati/read-only.
- **Frontend: SUCCESS** su `027307c`; rendering e interazioni Overview. Nessuna revisione grafica manuale di 390×844 su una build distribuita, quindi rimane un gate da completare prima del rilascio.
- **V3 suite / classics-rc: ancora in corso** sul commit `027307c` al momento di questo checkpoint. Non dichiarare success finché i job non finiscono.
- Il precedente commit `f46b267` aveva **classics-rc FAILED** a causa di due SHA pinned dei file `signals.py` e `brain.py` dopo l'addizione autorizzata trend advisory; PIN aggiornati nel test `test_long_s25.py` al commit `fef06db` dopo verifica dei nuovi hash e dei test di scoring senza variazioni. Controllare CI classics-rc sul nuovo commit.
- Commit principali: `676fc469` (UI e backend), `fef06db` (pin SHAs), `4125a302` (compatibilità risposte e test), `3b34970a` (griglia desktop, Brain stat), `027307c` (provenienza prezzo e test responsivi).

## Gate di rilascio

1. Il server attuale legge ancora le directory dei vecchi classici: **non basta aggiornare il frontend**. Prima dell'avvio vanno configurati `DESK_DATA_DIR` e `DESK_DATA_DIR_BULL` verso le nuove run PAPER, e `V3_JOURNAL_PATH`, `V3_RUN_ID`, `V3_BUDGET_DB_PATH`, `V3_HEARTBEAT_PATH` verso la nuova Brain2k con policy 12%/55%, tutto in run isolata e PAUSED.
2. Verificare che i tre servizi aggiornino heartbeat, operazioni aperte, prezzo corrente e chiusure manuali da endpoint autenticati nel nuovo contesto, senza toccare storici e vecchie 6+2 posizioni PAPER.
3. Fare un controllo visuale su telefono 390×844 e desktop, con i pulsanti abilitati **solo** se supportati dai worker. Niente ordini LIVE.
4. Prima del GO verificare snapshot esterno, exit sidecar, mandato Brain coerente, supervisione e rollback.

**NO MERGE, NO DEPLOY, NO RESTART, NO RESET eseguiti.** Archivi storici preservati.
