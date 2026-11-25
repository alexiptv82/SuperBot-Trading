# SuperBot-Trading — checkpoint di continuità Brain Unico V2

**Aggiornamento:** 25 novembre 2026, dopo il test Termius delle 06:35 (ora italiana).  
**Repository:** `alexiptv82/SuperBot-Trading`.  
**Fonti:** conversazione di progetto, risultati comunicati da Claude, screenshot Termius dell'operatore, verifiche del codice GitHub. I risultati di VPS sono quelli osservati negli screenshot, non una nuova verifica SSH diretta.

## 1. Stato operativo confermato

- **Brain Unico V2 PAPER avviato**, capitale iniziale della nuova sessione **2.000 USDT**, run tecnica `brain-scalp-paper-p1`, dieci slot, universo 25 criptovalute + oro e argento (27 strumenti).
- Ultimo rilascio Brain: pacchetto `brain-unico-6a96e599`, ramo `claude/live-evolution-20261124`. Il deploy della nuova run è stato effettuato il 24/11; `RIPARTENZA_RESULT=BRAIN_UNICO_PAPER_RUNNING`, ma la parte web era rimasta precedente (`RIPARTENZA_EXIT_CODE=5`). **Non ripetere `--nuova-sessione`**.
- Falco Evoluto resta fermo/disattivato. Vecchia run archiviata integralmente con **539 eventi** e controllo integrità; **3 sessioni archiviate** collegate in sola lettura per l'apprendimento. Le perdite storiche non devono sparire dal cumulativo.
- **Dashboard corretta il 25/11** tramite aggiornamento *solo web*. Termius: `PAPER_APP_WEB live_RESULT=PASS_LIVE`, `BRAIN_UI_RESULT=SUCCESS_UI_BRAIN_UNICO`, `APP_BRAIN=runner, uscite e bridge di chiusura non riavviati`, `APP_RESULT=APP_PAPER_INSTALLATA_E_VERIFICATA`, **`WEB_EXIT_CODE=0`**. L'utente ha aperto la dashboard e confermato **«funziona ✅»**. Cinque archivi leggibili e verifica della disponibilità del canale chiusura manuale senza eseguire chiusure.
- Stato VPS corrente successivo a tale screenshot **non ricontrollato da SSH**. Ultima prova comunicata: Brain operativo, servizi delle uscite sani. Non dichiarare nuovi profitti o posizioni senza una lettura aggiornata.

## 2. Configurazione V2 e Brain Live Evolution

- DeepSeek analista principale; Claude revisore attivo delle decisioni importanti, **veto mantenuto**; `NO_TRADE` valido.
- Ciclo ingressi **30 minuti**; leva dinamica **15–50×**, margine massimo per trade 400 USDT, margine totale massimo 55%, rischio per trade 4,3%, rischio aperto massimo 12%, stop giornaliero 25% (valori della configurazione candidata/installata).
- Confidenza minima DeepSeek **0,56**, selezione consulti con soglie 0,60 (BTC/ETH/XAU/XAG) e 0,70 (altcoin), modalità senza risposta Claude a rischio dimezzato **disattivata**. LONG filtrati da trend favorevole 1h e 4h. Costi+slippage proposti non oltre 30% di 1R. Stop AI non allargabili e guardia contro stop troppo stretti. Guardian selettivo da +300 USDT netti e protettivo da +400; salvadanaio e limiti di rischio conservati.
- Unica apertura iniziale per idea; eventuale secondo ingresso a prezzo migliore e a rischio invariato; chiusure parziali su medesima posizione. Uscite automatiche indipendenti dalle scansioni di ingresso.
- **Live Evolution**: versioni di strategia registrate nel journal e associate alle nuove posizioni, con politica di uscita e impostazioni originali per le vecchie; nuove versioni dal ciclo successivo, approvazione umana, rollback per sole nuove aperture. CLI `sudo superbot-strategia ...` installato col rilascio. La prova V2→V3 con posizione aperta è passata in integrazione simulata, ma una prova operativa completa sulla VPS resta da programmare senza chiudere posizioni.
- Nessun cambio strategico ulteriore approvato dopo l'avvio V2. Non fare reset/deploy/merge senza richiesta specifica dell'utente.

## 3. Diagnosi BTC 24/11 e confronto storico

- Prima run BTC SHORT: una **idea** suddivisa originariamente in **due quote**; aperta circa 14:35 UTC, ingresso 60.201,16, leva 19×, margine 398,67. Claude in revisione propose stop 60.250, accettato dall'arbitro; candela 15:33 UTC massimo 60.274, quindi stop toccato. Il monitor precedente non rilevò la candela; chiusura registrata al riavvio alle 16:53:52 UTC, prezzo 60.262,05. Risultato reale: lordo **−7,66**, commissioni **9,09**, netto **−16,75 USDT**. Non riscrivere il journal storico. La causa della mancata rilevazione è coerente con cache candele non riconvalidata, ma la candela provvisoria specifica non fu dimostrata.
- Riparazione V2: rilettura delle candele recenti e tracciamento `exit_late`, candela che attiva lo stop e ritardo; guardia sugli stop stretti. Resta importante distinguere prezzi teorici PAPER e prezzi realmente disponibili al momento di una rilevazione tardiva.
- Storici ricostruiti da Claude: Brain V3 `brain-v3-paper20261111` **98 trade distinti**, netto **−199 USDT** dopo **857** commissioni (lordo +658); Brain libero **182 trade**, netto −1.030; Falco classico **335 trade**, netto +334; Toro **151**, netto −304. Non confondere 98 trade V3 con 96 segnali SHORT dei classici. Campioni e condizioni di mercato non sono comparabili senza cautela.
- Simulazione delle 37 proposte del 24/11: 2 decisioni approvate BTC/ICP; solo BTC eseguita, in 2 quote; ICP scaduta (`decision_stale`, 383 secondi >120). Le contestazioni di Claude risultavano spesso protettive. Scenario solo DeepSeek negativo anche con filtri: V2 simulata circa **−34 USDT** sui trade chiusi, campione breve e non predittivo. Decisione: mantenere veto Claude, non aumentare aperture per forza.

## 4. Errore dashboard e correzione reale del 25/11

1. Rilascio Brain `6a96e599`: avvio PAPER riuscito; aggiornamento web rifiutato con `FAILED_archive_detail_mismatch` perché una vecchia idea BTC aveva **1 trade distinto ma 2 chiusure per quote**.
2. Pacchetto solo web `web-brain-unico-d1bc0628`: corretto il confronto archivio con `closes`, ma secondo tentativo fermato da `FAILED_trades_closed_count_mismatch_brain_scalp`, `WEB_EXIT_CODE=3`, rollback web automatico e Brain mai fermato.
3. Diagnostica Termius del **25/11 ore 06:22** su snapshot e journal vivo: 1.052 eventi, **3 aperture, 2 `paper_reduce`, 1 `paper_close`, 2 posizioni aperte, 3 voci di chiusura nel riepilogo ma solo 1 esito validato**, due scarti `inconsistent_close`. Il journal contabilizzava P&L realizzato **+170,48168336 USDT**, l'estrattore **+78,02204006**, scarto complessivo **+92,45964330**. Snapshot e due letture del vivo coincidevano: **non era un semplice cambio di dati tra letture**. Nessuna evidenza sufficiente per dichiarare il journal corrotto.
4. Causa individuata nel codice: `backend/v3/executor/paper_scale.py` usa arrotondamento **ROUND_DOWN** a 8 decimali per le chiusure parziali; `backend/v3/outcomes.py` validava anche `paper_reduce` usando **ROUND_HALF_EVEN** previsto per `paper_close`. Bastava lo scarto di 1e−8 per rifiutare un risultato altrimenti coerente.
5. Modifica GitHub su ramo isolato **`work/brain-v2-web-counts-20261125`**, commit **`6e305ed027e6aca132b0b3c1f27f42933ef902cd`**: verifica `paper_reduce` con ROUND_DOWN, `paper_close` con HALF_EVEN; test di regressione aggiunti e test di record alterato sempre respinto. Questa modifica al repository **non equivale a un merge nel ramo principale o a un aggiornamento automatico del runner**.
6. Installazione lato sola web confermata da screenshot Termius **25/11 ore 06:35**: `PAPER_APP_WEB live_RESULT=PASS_LIVE`, nuova UI pubblicata, **`APP_RESULT=APP_PAPER_INSTALLATA_E_VERIFICATA`, `WEB_EXIT_CODE=0`**. Runner, uscite e bridge di chiusura **non riavviati**. Utente: **«funziona ✅»**. Nessun reset PAPER, nessuna chiusura forzata.

## 5. Cosa resta aperto e ordine corretto di lavoro

1. **Verificare l'apprendimento del Brain e l'estrazione esiti lato runner**: la web è corretta, ma il codice del runner installato potrebbe ancora scartare i due `paper_reduce` nel dataset/memoria. Distinguere journal valido, esiti verificati e reale uso nella memoria. Eventuali correzioni devono preservare versioni delle posizioni e non richiedere reset.
2. Controllare lo stato operativo corrente con lettura non invasiva: RUNNING/heartbeat, posizioni, uscite, P&L, Telegram, costi AI, salvadanaio e contatori della web. Non assumere che il P&L del 06:22 sia ancora quello attuale.
3. Raccogliere un campione PAPER fuori dal giorno 24/11 prima di ritoccare filtri o veto; misurare segnali proposti, contestati, eseguiti, costi, ritorno netto e rischi.
4. Eseguire in seguito un test controllato Live Evolution V2→V3 con una posizione aperta e senza chiuderla forzatamente, prima di considerare la funzione dimostrata operativamente.
5. **Non** rilanciare `--nuova-sessione` né il vecchio pacchetto `d1bc0628`, non resettare/azzerare lo storico, non sospendere il Brain solo per la UI e non aggiornare moduli delle uscite senza un piano di compatibilità.

## 6. Riferimenti per ripresa

- Repo: https://github.com/alexiptv82/SuperBot-Trading
- Ramo Live Evolution: `claude/live-evolution-20261124`, versione rilascio Brain `6a96e599`.
- Correzione specifica conteggi: `work/brain-v2-web-counts-20261125`, commit `6e305ed0`, file `backend/v3/outcomes.py` e `backend/tests/test_v3_outcomes_partial_rounding.py`.
- Pacchetto web pubblicato tramite procedura solo web: ultimo esito `APP_PAPER_INSTALLATA_E_VERIFICATA`, `WEB_EXIT_CODE=0` (25/11 06:35).
- Identificatore run PAPER: `brain-scalp-paper-p1`; originale storico archiviato con 539 eventi. Percorso run: `/opt/superbot-v3-paper-runs/brain-v3-brain-scalp-p1`.
- **Regola di sicurezza:** PAPER soltanto; nessun deploy/merge/reset senza consenso esplicito; protezioni uscite e posizioni prioritarie; slot vuoto ammesso; aggiornamenti dinamici di strategia solo con approvazione dell'operatore.

**Riferimento pratico:** alla ripresa iniziare dal punto 5.1 (esiti parziali e memoria), senza rifare rilascio, dashboard o diagnosi BTC.