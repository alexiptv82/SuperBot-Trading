# Brain AI libero — piano, NON implementato, 27 ottobre 2026

Autore ChatGPT Work; brief Claude letto dall'allegato. Valgono le decisioni utente più recenti, non i precedenti due conti da1000, stop20%, noreset o budget10$ proposti dal brief.

## Ambito e conto
- Nuovo componente backend/director/brain_free/ su futuro ramo work/brain-ai-libero da129547ed43a9aaec935df31102bb4e8016c38e7c. Nessuna modifica desk/*, classical_adaptive/* o brain_pilot/*, né ramo adattivo attuale. App in ramo separato basato sul main aggiornato, senza merge cross-history.
- Singolo nuovo account PAPER2000; sostituisce i tre profili Brain attivi nella dashboard. Nuovo database/directory /opt/superbot-brain-free/, accountid ed experimentid distinti. Vecchi tre profili: backup/restore e snapshotfinali, poi arresto al futuro cutover e archivi di sola lettura. Nessuna cancellazione, nessun trasferimento implicito di posizioni o chiusure fittizie. Posizioni vecchie aperte conservate come snapshot archivio, escluse dai risultati della nuova run. Ledger e budget passati non azzerati. Classici Hawk/Bull e loro Salvadanaio intatti; AI ombra non inclusa nei tre profili.

## File previsti
- brain_free/config.py, mandate.py: guardrail e mandato versionati, hash congelato per esperimento.
- brain_free/runtime.py, execution.py, store.py: supervisore H24, account2000, unico writer SQLite, transazioni, idempotenza, riavvio conservativo. Motore PAPER indipendente: si possono copiare bugfix di contabilità/barre/ingresso/DCA senza importare strategy gate.
- brain_free/provider.py, prompt_builder.py, memory.py: DeepSeek diretto AI-only, contratto decisioni, ultimi10trade, decisione motivata persistita prima dell'esecuzione.
- brain_free/feeds.py, market_context.py: quotazioni/OHLC pubblici e contesto con fonte, data aggiornamento e stato disponibilità.
- brain_free/spend.py, notifications.py, reports.py: contatore persistente senza budget gate, outboxTelegram, report.
- Dockerfile.brain-free, deploy/scripts/brain_free_rollout.py, workflowCI e workflow rilascio con trigger disarmato fino a OKdeploy separato. Test dedicati in backend/tests/test_brain_free_*.py.
- App su ramo distinto: backend/brain_free_view.py e brain_free_api.py nuovi, wiringautenticazione in server.py; frontend/src/components/BrainFreePanel.js nuovo e collegamento in pages/BrainDashboard.js. Reader SQLite readonly, mountRO dedicato; classici e vecchi reader invariati.

## Gate verificati da NON ereditare (sorgente129547ed, non classici appena rollbati)
- classical_adaptive/runtime.py:321 chiama desk.cli.run_cycle; il nuovo runtime non lo chiamerà.
- desk/cli.py:1467 cooldown10/60min;1480-1501 soglie60/63 e macro;1502-1510 RR1.5;1513-1524 regime;1532e seguenti minimi/sizeforzati Hawk/Bull e bull_entry_gate. Nessuno di questi comanda il nuovo componente; i file originali restano invariati.
- brain_pilot/pilot.py:81-99 macroBTC obbligatorio/confidenza60/ATR/stopmassimo8%/RR1.5/parziale50%; portfolio.py:74-106 rischio1%equity, margine100 e sizepesata perconviction. Non si riusano questi percorsi esecutivi.
- brain_pilot/portfolio.py:20-46 stop20%/kill450, maxDCA/condizioni supporto/ATR e restrizioni strategiche: non ereditati. Nessun daily stop/kill monetario, soglia confidence, ATR, RR, fascia oraria, cooldownentrata, filtrocorrelazione o profittoguardian nascosto.
- classical_adaptive/budget.py:47e96-103 cap0.50/giorno,12/mese e pacing; provider.py:request usa reserve; runtime fallbackclassical_rules. Nuovo provider non usa questo budget e non apre via regole se l'AI manca.

## Soli vincoli esecutivi
- PAPERrigido, schema valido, simboli verificati, conti non negativi, quantità/minimi/ticksize degli strumenti; unico writer e nessun ordine duplicato.
- Leve massimo45BTC/XAU/XAG,30ETH,25altcoin; eventuale limite effettivo inferiore del contratto rispettato. Margine totale1600su2000, comprensivo aumentiDCA/split/riserve; cash deve coprire fee e margine. Nessun massimopertrade100/350, nessun rischio1% imposto.
- Proposta max10slot complessivi, una posizione netta per simbolo. AI sceglie quanto margine e leva entro il totale; nessun minimo di convinzione.
- SLobbligatorio dalla parte corretta dell'ingresso ed eseguibile prima della liquidazione con buffer fisico e costi. Proposta incompatibile: ridurre leva e, se serve per cassa/margine, size; mai spostare tacitamente lo stop o aumentare leva. Ridurre size da solo non risolve la distanza dalla liquidazione. Se nessuna combinazione fisica è valida, registrare impossibilità reale.
- Proposta freschezza: prezzo del simbolo <=30s al momento di eseguire; barre1m chiuse disponibili con età coerente <=90s dalla chiusura. Dati stale/gap non coperto: niente nuova esposizione sul simbolo interessato; non fermare simboli sani per contesto opzionale mancante. Gestione stop esistente sempre separata dal modello; nessun prezzo o fill inventato durante blackout.
- Fee/slippage/funding contabilizzati e visibili; limite1600 è margine, non perdita massima. Nessun Salvadanaio/ripristino capitale automatico nel nuovo conto.

## Cadenza e prompt
- ScenarioE per UNsolo conto: analisi di tutti i simboli LONG/SHORT ogni15min; controlloAI posizioni ogni5min se aperte. Supervisore locale, feed e stop su loop breve indipendente (obiettivo5s); nessun cooldownstrategico. Su APIerrore retry/backoff tecnico senza fallbackalle regole né tetto software finanziario.
- Prefisso statico cacheabile: mandato profittonetto/scalpadattivo/rotazione utile, autonomia, guardrail fisici, contrattooutput, contesto Hawk/Bull etichettato non vincolante. Seed backtest dichiarati sintetici/nonverificati, mai risultati reali certificati.
- Dati dinamici: account/cash/margine/slot/esposizione/costi; snapshotmercato per simbolo con timestamp; dominanceBTC, Fear&Greed, calendario e notizie macro prossime6h, fonti e missing espliciti; ultimi10trade completati della nuova run con motivazione originale, lato,size,leva,fee,lordo/netto,durata,uscita,esito. Parziali aggregate per posizione; se meno10, mostrare solo esistenti. Vecchie esperienze separate per provenienza, niente finte10righe iniziali.
- Output: sintesi decisionale esplicita e verificabile, scenario favorevole/contrario e invalidazione, azione, simbolo/lato/margine/leva/SL/TPeventuale/parziale. Ogni apertura richiede motivazione salvata prima di eseguire. Confidence descrittiva, mai soglia. Valutazione entrambi i lati; inattività motivata e misurata, nessun trade casuale forzato. Fonti/news/storico trattati come dati, mai istruzioni.
- Memoria esperienziale nel prompt, non retraining o certezza di miglioramento. Modello/parametri/prompt/guardrail con hash fissati; memoria e feed cambiano normalmente.

## Contesto, costo, Telegram, report
- DominanzaBTC da provider pubblico verificato; Fear&Greed ultimo valore pubblicato con timestamp/attributionAlternative.me (non tick live); eventi macro da calendario e fonti documentate. Mancanza o dato vecchio di contesto non blocca. Niente macroblackout/regimeauto generati da questi dati.
- DeepSeek deepseek-flash, thinking configurato e congelato per test; listino ufficiale verificato27/10: inputmiss0.15/hit0.003/output0.60 perMtoken fuori picco, doppio inpicco; reasoning a consumo. 1.50$/giorno riferimento di pianificazione, NONcapnépromessa per singolo conto. Ledger reale con tokenhit/miss/output/reasoning senza doppio conteggio, tariffaversionata, requestid; timeoutcostoignoto distinto da costo confermato, nessun falsozero.
- UIspesaoggiUTC+cumulato nuovoesperimento, separata dai ledgerlegacy e spese altriworker. Nessun capgiornaliero/mensile/settimanale o pacingmonetario. Credito esaurito/429/APIoffline sono limiti esterni reali: protezioni locali continuano, nessuna apertura attribuita falsamente all'AI, allarme e retry. H24 è obiettivo operativo, non garanzia contro guasti/API.
- Telegram ogni apertura/chiusura/variazione importante conprefisso[BRAIN], idtrade,simbollato, margine/notional/qty/leva,motivo, eventuale correzione, e alla chiusura lordo/fee/netto. Dispatcher fuori dal loop di protezione, retrypersistente; guastoTelegram non ferma conto o apre doppitrade.
- Proposta reportserale22:00Europe/Rome +un messaggioTelegramquotidiano: equity/cash/margine,realizzato/floating,fee,WR/PF/durata,attività/slot/minutiinattivo,LONG/SHORT,erroririfiuto,spesaoggi/cumulata e confronto descrittivo conclassici isolati. Intervalli e timezone espliciti; confronto non prova causale.

## Rilascio e test
- Ora SOLO piano/diario, nessuncodice, nessun branchimplementativo creato, nessun container o dato toccato.
- Dopo OK piano: implementazione/testoffline e revisione, poi diff e OKdeployseparato. Test avvio2000, cash/margine/fee, LONG/SHORT, adattamento leva/stop, assenza vecchigate, memoria10, reasonprimaesecuzione, stale/contestoopzionale, API senza budgetgate, crash/idempotenza,outbox,reader,restore/ritornoindietro.
- Cutover futuro: snapshotfinali e backupverificati dei tre Brain/ledger, controlloposizioniaperte, nuovaidentitàaccount,stopvecchi3senzaresetdistruttivo, startunicosoloPAPER, verificaapp/report/notifiche; classici e Salvadanaio non riavviati.
- Esperimento168ore dall'effettivo avvio verificato. Può iniziare27/10 solo se realmente rilasciato27/10; non retrodatare mentre è in progettazione. Prompt/guardrail congelati salvo bug con patchauditata ed eventuale separazione coorti. Riavvio automatico recupera stato, non ricrea conto; disponibilità misurata. A168ore rapporto finale, nessuna modifica automatica strategia.

Fonti: https://api-docs.deepseek.com/quick_start/pricing/ ; https://api-docs.deepseek.com/guides/thinking_mode/ ; https://alternative.me/crypto/fear-and-greed-index/ .
