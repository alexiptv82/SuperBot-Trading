# Brain V3 — FRRD: protocollo di ricerca SHADOW (15/11/2026)

**Ambito:** solo ricerca su branch isolato. Nessun collegamento al runner, nessuna modifica di rischio, nessun ordine, nessuna modifica a Falco/Toro o alla dashboard.  
**Base:** `work/brain-rc84-market-data-hotfix-20261113`.

## Motivazione fondata sul journal VPS

Dal report read-only dell'utente (run `brain-v3-paper20261111`, 11–15 novembre):
- SHORT in `EXPANSION`: 16 chiusi, **5 vincenti** (~31%), **−221,20 USDT**.
- SHORT in `TREND_DOWN`: 6 chiusi, 5 vincenti, **+400,69 USDT**.
- SHORT in `RANGE`: 3 chiusi, 3 vincenti, **+185,11 USDT**.
- 14 stop, PnL **−1.111,60 USDT**; 13 TP, **+1.338,77 USDT**. LONG 2, entrambi persi.
- 30 aperture effettive su 50 approvazioni del modello, 199 rifiuti dal rischio: indagine causale separata.

Sono **solo 27 trade chiusi** e si tratta di un periodo eccezionalmente ribassista. La differenza per regime e' ipotesi, non un filtro pronto per produzione. `EXPANSION` classifica espansione di volatilita', non automaticamente rally.

## Scopo

Identificare PRIMA dell'ingresso SHORT le fasi in cui il ribasso sta esaurendosi o si sta sviluppando un rimbalzo locale. Il modulo FRRD deve produrre **osservazioni** che si possano confrontare con gli ingressi di Brain e un controllo casuale appaiato. Non deve chiudere trade, bloccare LONG/SHORT o sovrascrivere DeepSeek.

## Input consentiti

- Candele **15m chiuse**, contigue e timestamp UTC; serie `Bar` esistente in `backend/v3/features/indicators.py`.
- Candele **1h e 4h chiuse** per contesto del trend, disponibili nel `MarketView` esistente; lo stato `EXPANSION` deriva dal base 15m di `backend/v3/features/regime.py`.
- Candele 1m solo per l'analisi **ex-post** delle escursioni contro posizione; non creare nuove API nel runner.
- Journal in **sola lettura**; associare eventi `paper_open` a `brain_decision` tramite `decision_event_id` quando presente.
- Mai usare la candela in formazione o conoscere `paper_close` per calcolare il segnale di un ingresso storico.

## Segnali da studiare, distinti

1. **CONTINUAZIONE_SHORT**: struttura di minimi/massimi decrescenti su 15m, chiusura sotto un minimo significativo precedente, senza segnale di recupero; anche in `EXPANSION` potrebbe essere uno SHORT valido.
2. **RIMBALZO_LOCALE**: minimo locale seguito da due chiusure 15m coerenti in recupero, accelerazione contro SHORT e ripresa di almeno una soglia ATR; non definirlo cambio trend principale.
3. **INVERSIONE_CANDIDATA**: rottura confermata della struttura ribassista 15m (CHoCH/BOS) con contesto 1h piu' forte; esigere conferma su barra chiusa e documentare il ritardo del segnale.
4. **INCERTO**: dati insufficienti, gap, serie stale, conflitto multi-timeframe o segnali instabili; non prendere decisioni con informazioni mancanti.

La misura del rimbalzo deve essere normalizzata su ATR e pre-registrata PRIMA dell'analisi storica. Le soglie che ottengono il miglior PnL sul campione 11–15 novembre sarebbero overfitting.

## Qualita' del rilevatore

- **No repaint:** stesso segnale rieseguito al medesimo `as_of_ms` con le stesse candele chiuse = stesso risultato; dati futuri non modificano il segnale precedente.
- **Hysteresis:** richiedere due evidenze consecutive o una rottura di struttura forte; ritorno da `RIMBALZO_LOCALE` a `CONTINUAZIONE_SHORT` non immediato per un singolo tick.
- **Fail closed:** senza 15m e 1h validi segnalare `INCERTO`, non `CONTINUAZIONE_SHORT`; il modulo e' soltanto osservatore e non blocca neanche in questo caso.
- **No tuning operativo:** non introdurre nuovi parametri di leva, stop, take-profit, costi AI o nuove chiamate API.

## Confronti da eseguire

A ogni `brain_decision` e `paper_open` ricostruire l'informazione conosciuta a quell'istante:
- Simbolo, lato, timestamp UTC, regime 15m/1h/4h, ATR relativo, segnale FRRD e motivo del segnale.
- Esito trade reale PAPER, MFE/MAE, tempo fino allo stop/TP e fee gia' contabilizzate.
- Per ogni SHORT eseguito, controllo SHORT su **stesso simbolo/stesso timestamp/stesso stop e size**, con schema di uscite identico; un controllo a ora casuale e' solo ausiliario, non prova l'abilita' del modello.
- Matrice: `EXPANSION+CONTINUAZIONE_SHORT` vs `EXPANSION+RIMBALZO_LOCALE` vs `EXPANSION+INVERSIONE_CANDIDATA` e baseline senza filtro.
- Falsi allarmi: numero di SHORT vincenti che il segnale avrebbe sconsigliato, perdita di profitto potenziale, robustezza su BTC/ETH/BNB e giornate distinte.
- Stessa analisi su dati **successivi** alla definizione delle soglie, non usare i 16 SHORT per validare il filtro disegnato dai loro esiti.

## Gate per sviluppare codice osservatore

1. Implementare funzione pura nel laboratorio, **non importata** da `cycle.py`, `wiring.py`, `engine.py` o `exits.py`.
2. Test sintetici per continuazione, rimbalzo, CHoCH/BOS, sequenze incomplete, gap, barre future, no repaint, dati insufficienti e regime in conflitto.
3. Produrre CSV/JSON di osservazioni riproducibili e statistiche con almeno un secondo campione non usato nella progettazione.
4. Solo dopo prove robuste, valutare con l'utente se usare il rilevatore come informazione per DeepSeek, come overlay di rischio o un'azione indipendente. **Non abilitare alcun veto automaticamente.**

## Stato aggiornato dei lavori

- Fix dashboard Brain `O_RDONLY`: installato, codice verificato da Termius, **pulsante «Chiudi trade» funzionante secondo l'utente**. Nessun trade chiuso come prova; il percorso di chiusura end-to-end non e' collaudato.
- GitHub `work/brain-close-ro-web-preflight-20261115`: commit `401a621` riporta il collaudo UI.
- FRRD: **solo questo protocollo di ricerca**; non implementato e non installato.
- Toro LONG H3: rimane esperimento separato, nessun deploy.
