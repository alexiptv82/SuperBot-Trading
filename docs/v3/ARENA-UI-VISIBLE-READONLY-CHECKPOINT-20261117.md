# SuperBot Brain AI Arena — frontend visibile, solo lettura (17 novembre 2026)

## Risultato pubblico del controllo delle ore 11:06
L'utente ha eseguito dalla VPS Singapore la prova `arena-public-marketcap-preview-20261116.py --probe`. Output confermato da screenshot Termius:
- `crypto_found=23/23` — sono 23 **candidati provvisori**, non 23 contratti autorizzati;
- `excluded_obvious_nonnative=11`;
- `excluded_ambiguous_tickers=0`;
- `contracts_unavailable_or_illiquid=6`;
- `metals_reserved=XAUUSDT,XAGUSDT`; prenotati, ma verifica contratti/candele ancora da completare;
- `tradable_or_approved=NO`, `RESULT=PROVISIONAL_LIST_CATEGORY_AND_CANDLES_PENDING`.
Nella stessa sessione risultano già verificati 14/14 test della nuova ricerca 8-vs-25. Non sostituire la lista operativa del Brain 2.000 senza gate asset-ID, feed e budget.

## Obiettivo prioritario dell'utente
Aprire l'app SuperBot su Samsung e vedere **tre portafogli PAPER DeepSeek/Qwen/MiniMax** separati con apertura/chiusura trade, equity, PnL, win-rate, confrontabili dal T0 comune di 14 giorni. Non confondere Falco/Toro/Brain (pagina V3 corrente) con le tre AI del trial. Nessun numero inventato per Qwen/MiniMax prima dell'avvio.

## UI già sviluppata, ora più facilmente accessibile
Branch `work/arena-dashboard-discoverable-readonly-20261117` basato sul precedente `work/brain-arena-readonly-wallets-ui-fix-20261116`.

- `frontend/src/pages/Overview.js`: inserito un link evidente ad `/arena` sopra le card V3 Falco/Toro/Brain; non rimuove la dashboard, i comandi manuali, la pagina Classici, la navigazione né i servizi di uscita.
- `frontend/src/pages/BrainArena.js`: mostrata la dicitura **in attesa di attivazione comune**, capitale *previsto*, stato `Storico precedente` per il Brain DeepSeek che preesiste al trial; Qwen/MiniMax senza journal restano `Non avviato`. Nessun ordine inviabile dalla schermata.
- `deploy/scripts/arena-ui-navigation-preflight-20261117.py`: verifica statica delle due pagine, dei link e dei gate. **Non è un test React build/browser**.

## Integrazione backend già preparata ma disattivata
La pagina AI Arena esisteva già in `App.js` con Route `/arena`. `frontend/src/brainArenaModel.js` espone i 3 wallet e impedisce PnL finto: storico DeepSeek non entra nel totale comparativo. Frontend legge `/api/v3/arena` solo con `REACT_APP_BRAIN_ARENA_SHADOW_API=1`; backend monta il router solo con `V3_ARENA_READONLY_ENABLED=1`, due env PAPER e data T0 valida. L'API rifiuta journal non riconciliati e identità forzate. **Non attivare i due flag su app corrente finché i tre journal non sono presenti e verificati**.

## Ordine di lavoro
1. Verificare staticamente e poi eseguire **React build in un clone isolato**; nessun deploy, nessuna GitHub Action.
2. Preparare staging dell'interfaccia da sottoporre all'utente: il Brain attuale può essere visibile come storico, mentre Qwen/MiniMax devono indicare `Non avviato` (non 0 PnL).
3. Completare il selettore condiviso 25-asset con categorie native/verificate, equità dei dati, limiti di budget e candidati, evitando 25 chiamate DeepSeek per ciclo.
4. Predisporre 3 run PAPER isolate, servizi uscite indipendenti, budget separati, journal e un T0 comune. Valutare OpenRouter DeepSeek come modello di ricerca diverso da Brain `deepseek-flash`. Esigere test di uscita, rischio e autenticazione.
5. Soltanto dopo approvazione dell'utente, pubblicare la UI in app e attivare il trial PAPER 14 giorni. **Finora NON è stato fatto**.

## Garanzie
Nessun merge/deploy/publish; repo rule-pool e VPS invariati; Falco SHORT preservato; Toro non toccato; Brain attuale con 8 simboli configurati da GitHub è ancora baseline storico (runtime VPS da verificare). Nessuna chiamata a pagamento o ordine per l'implementazione UI.
