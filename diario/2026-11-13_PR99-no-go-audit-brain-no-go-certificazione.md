# Checkpoint verificabile — PR #99 replay NO-GO; audit indipendente Brain NO-GO certificazione

**Data:** 13/11/2026 22:44 Europe/Rome  
**Perimetro:** sola documentazione; trading esclusivamente PAPER; nessun merge, deploy, GitHub Actions, riavvio, reset, ordine o modifica operativa eseguita da questo checkpoint.

## 1. Toro — PR #99 replay completato, NO-GO

La [PR Draft #99](https://github.com/alexiptv82/SuperBot-Trading/pull/99) resta aperta/non mergiata, ramo `work/toro-supertrend-last-study-20261113`, HEAD `4b06716546f91b1bb9f34bfc9256d57f321f1d84`. Il protocollo era stato preregistrato prima del test al commit `0c8471a8d189e09fbd7d3f39825a997f2c1cff65`.

Nel [commento PR delle 22:20 CET](https://github.com/alexiptv82/SuperBot-Trading/pull/99#issuecomment-6865638561) è registrato l'output Termius del replay:

- `REPLAY_COMPLETE trades=361`;
- media netta `avg_net_bp=-32.455` = **−0,32455% nozionale per trade**;
- profit factor **0,5938**;
- drawdown close-only `0.8973` = **89,73%**, non mark-to-market completo e quindi non stima precisa del DD reale;
- benchmark random matched p95 **−9,0233 bp**;
- stress 30 bp medio **−46,455 bp** = **−0,46455%**;
- soltanto **1/8** gate soddisfatto;
- `NO_AUTOMATIC_GO`, `paper_orders=0`, `no_bot_changes=1`.

Decisione conforme al prereg: **NO-GO per questa configurazione Toro LONG Supertrend 15m/1h**. Fermare questo tentativo rules-only e non ritoccare a posteriori EMA, ATR, stop, TP, timeframe o asset. Nessun shadow 30 giorni, promozione, integrazione o deploy. Il risultato non confuta ogni possibile strategia LONG, ma chiude questa ipotesi specifica.

Le metriche DD, fill, random matched e costi meriterebbero audit metodologico prima di deduzioni causali; tuttavia expectancy negativa e PF <1 bastano al NO-GO preregistrato.

## 2. Brain — audit indipendente disponibile

Fonte: [Audit_Indipendente_Brain_V3_2026-11-13.md](https://chatgpt.com/library?file_id=libfile_07126c23a3188191bfb229c512b03b0a&account_id=personal), creato il 13/11/2026 alle 22:37 Europe/Rome. Rapporto in sola lettura, marcato `[Non verificato]` per stato VPS e redditività; prove sul codice e riproduzioni locali sono identificate separatamente.

### Verdetto

**NO-GO alla certificazione dell'affidabilità delle uscite e alla dichiarazione di edge economico dimostrato.** Non è un ordine di arresto e l'audit non ha modificato Brain.

Versioni ispezionate:

- base `0e29a73a36f668643da4088178bacb8616a45ac0`;
- hotfix Brain `9b1abcc33533d1ac216892630ff5904351385987`;
- il ramo predefinito osservato `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e` non contiene `backend/v3` e non è la base corretta;
- il confronto hotfix mostra nel percorso operativo soltanto modifiche a `runner/contracts.py` e `lab_tools/fetch_candles.py`; i difetti riprodotti restano uguali sulle due versioni.

### Test effettivamente eseguiti

- Suite selezionata sulla base: **1.290 PASS in 6,45 s**.
- Suite dedicata hotfix: **4 PASS in 0,06 s**.
- Riproduzioni indipendenti: feed vuoto/healthy; prezzo 1m vecchio; rischio senza buffer costi; timestamp chiusura ritardato; minuto d'ingresso escluso; budget superato dall'ultima chiamata; tre quote con policy corrente.
- Checkout puliti al termine; nessun sorgente operativo modificato.

Questi test provano comportamenti costruiti, non frequenza reale, perdite VPS, uptime o redditività. Nessun backtest economico Brain su dati reali è stato eseguito.

## 3. Rilievi Brain verificati

1. **P0 — falso healthy delle uscite.** Con posizione aperta e feed vuoto, il monitor produce `checked=1`, zero errori, stato `healthy` e gate `exit_service_healthy=True`, senza prova che stop/TP siano stati valutati. Anche errori JSON Bitget possono diventare lista vuota.
2. **P1 — prezzo 1m vecchio.** `last_minute_close` può accettare una barra quattro minuti più vecchia di quella attesa e perde il timestamp; influenza ingresso, recheck e chiusura manuale.
3. **P1 — rischio aperto incoerente.** La nuova quota include distanza stop + buffer, mentre lo snapshot delle posizioni già aperte ricostruisce soltanto `abs(fill-stop)*quantity`. Esempio audit: 80 USDT contro 92,80 includendo 16 bp su 8.000 USDT nozionali. Non è stato dimostrato un superamento reale del limite complessivo con la policy corrente.
4. **P1 — PnL PAPER incompleto.** Il funding non è integrato; slippage di stop/TP/timeout/manuale non è uniforme; una chiusura recuperata usa prezzo storico ma timestamp del controllo.
5. **P1 — equity/floor non garantiti.** Snapshot senza floating; dati di prezzo mancanti possono far ignorare il floating nel daily loss. Il floor 450 non chiude posizioni e non protegge da gap/feed assente.
6. **P1 — apprendimento limitato.** L5 riceve etichette/famiglie/stili/regimi, non le regole operative complete; la scoreboard è limitata al `run_id` corrente. Non è dimostrato un ciclo versione→causa→correzione→misura fuori campione.
7. **P1 — Profit Guardian assente nel percorso Brain.** La policy osservata è stop fisso → TP 2R → timeout 24h; nessun trailing, massimo profitto, parziale o momentum exit. Un Guardian è solo esperimento proposto, non valore operativo approvato.
8. **P2 — budget AI non rigidamente prenotato.** Il gate controlla il consuntivo precedente e può superare il limite con l'ultima chiamata; la successiva viene bloccata.
9. **Limiti simulativi:** il minuto d'ingresso è escluso; cache storica sidecar 1.500 minuti; mark-to-market, expectancy, PF, drawdown reale, valore Guardian e frequenza dei difetti sulla VPS non sono verificati.

### Configurazione Brain verificata versus desiderata

- Il motore può elevare proposte sotto il minimo a 20×; profilo 20–50×.
- Con la configurazione corrente, la distanza stop massima derivata è circa 0,911% a 20× e 0,269% a 50×: valori algebrici, non raccomandazioni.
- “2R” è lordo rispetto alla distanza stop e non include automaticamente fee/funding; non equivale a 2× rischio netto.
- Qualsiasi modifica a leva, sizing, stop, Guardian, seconda AI o dati richiede esperimento preregistrato e autorizzazione separata.

## 4. Eseguito / preparato / rilasciato

- **Eseguito:** replay Toro #99 completato con NO-GO; audit Brain in sola lettura; 1.290+4 test PASS; riproduzioni dei difetti.
- **Preparato/proposto:** correzioni per copertura feed/health, quote con timestamp, ledger costi/funding, prenotazione budget, tracking trigger/observed/accounted, prove Guardian e learning OOS.
- **Rilasciato:** nulla.
- **Non implementato/non approvato:** tutte le soluzioni proposte dall'audit Brain, shadow Toro, modifica rischi, riattivazione Falco/Toro, cambi ai servizi Brain.
- **Stato live VPS:** non certificato dall'audit; nessun accesso indipendente a journal, log, heartbeat e prezzi correnti.

## 5. Tre portafogli PAPER

- **Brain:** ultimo stato documentale resta unpause guarded con runner attivo ed exit healthy, ma il nuovo audit dimostra che il solo `healthy` non certifica la copertura del feed/valutazione stop. Nessuna prova nuova di ciclo completo otto simboli, aperture/chiusure o PnL.
- **Falco:** SHORT congelato e non riattivato.
- **Toro:** sospeso; BB100 V1, funding proxy e Supertrend V1 risultano NO-GO nelle rispettive prove. Nessuna integrazione o ordine.

## 6. Backup, chiavi e conservazione

- Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup o restore VPS.
- `work/extbackup-bot-stopped-20261109`: backup esterno preparato, non installato.
- RC84 [PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80) resta riferimento storico.
- Solo PAPER; storici ed EventJournal preservati. Nessun segreto o dettaglio utile all'accesso VPS registrato.

## 7. Prossimi passi e ripresa

1. Non retunare o promuovere PR #99; conservare il risultato negativo.
2. Per Brain, priorità P0: progettare e testare stato `unobservable`, separare `checked/evaluated/unobservable`, copertura per posizione e health degradato senza chiusure inventate.
3. Poi correggere freschezza quote/timestamp e coerenza rischio/costi con test negativi.
4. Prima di dichiarare edge o introdurre Guardian/seconda AI: baseline forward PAPER osservabile, ledger analitico separato, split temporale OOS e confronto preregistrato.
5. Qualsiasi patch deve essere isolata, revisionata e autorizzata; nessun deploy o restart implicito.

## Limiti di accesso

Il checkpoint usa GitHub, i due file Library e i progressi recenti effettivamente accessibili. Non dispone di trascrizioni integrali di chat eliminate né di controllo live indipendente della VPS.
