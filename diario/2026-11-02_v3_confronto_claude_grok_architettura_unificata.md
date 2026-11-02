# 2026-11-02 — SuperBot V3: confronto indipendente Claude vs Grok e bozza di architettura combinata

**STATO: PROPOSTA IN REVISIONE.** Il seguente è un confronto tecnico. Nessun merge, deploy, reset, riavvio, cambio di soglie o chiamata AI di trading autorizzato da questo documento. La V3 va prima approvata dall'utente.

## Sorgenti
1. Prima revisione: PDF allegato dall'utente `SuperBot-Trading V3 — Revisione tecnica indipendente.pdf` (Claude, 25 pp, 2 nov 2026). Riepilogo e audit preliminare già salvati in `diario/2026-11-02_v3_claude_independent_review_first_audit.md`.
2. Seconda revisione: testo fornito direttamente dall'utente in chat (Grok, “Valutazione tecnica indipendente – SuperBot-Trading V3”, 12 sezioni e tre miglioramenti originali).
3. Evidenza operativa attuale dai workflow GitHub, NON dai due rapporti (datati prima dello stop): [stop e backup PASS](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41464111891), [audit indipendente stop PASS](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41465049997).

## Consenso delle due revisioni
- Tre portafogli PAPER separati: **Falco 1000, Toro 1000, Brain 1000 USDT**, contabilità per portfolio_id e run_id; gli storici precedenti restano intatti.
- Un Brain centrale di coordinamento e ricerca, con DeepSeek analista principale attivo ad eventi, Claude revisore per casi selezionati, senza chiamate AI cieche H24.
- AI genera **intenzioni/proposte** e ragionamenti, non ordini; rischio e fattibilità deterministicamente controllati, NO_TRADE valido; classici meccanici restano sotto proprie strategie e forniscono dati osservabili read-only.
- Event log append-only, episodio, memoria delle statistiche e delle ipotesi; promozione nuove strategie solo dopo OOS/walk-forward/shadow e successivo OK dell'utente.
- Dashboard mobile unica con controlli per ogni portafoglio: pausa/riprendi, apri PAPER, chiudi per ID, chiudi parziale, SL/TP, stato dei servizi, ricevute e registro errori.
- Distinzione tra chiusure volontarie dell'utente (preferenze e teaching) e manutenzione (non teaching), con controfattuali e statistiche.
- Confronti con stessi costi e condizioni, valutazione normalizzata per rischio e drawdown; nessun presunto auto-apprendimento solo perché un LLM riceve log nel prompt.

## Differenze utili da combinare
1. Claude: regime direzione × volatilità con stati transizione/stress, isteresi, regole di cambio e modello a 5 livelli L0..L4. Grok: **probabilità** di regime anziché sola etichetta hard; proporre V3: feature oggettive, probabilità calibrate, stato di transizione/stress, isteresi e cooldown; se l'incertezza è elevata, NO_TRADE o rischio ridotto. Verificare la predittività OOS.
2. Claude: **gemello Brain deterministico senza AI**, stesse strategie, dati, tempi, rischio. Grok: **Brain blind** che usa la stessa AI ma NON vede le decisioni dei classici, per isolare il valore delle osservazioni. V3: entrambi in `shadow` senza quarto/quinto wallet operativo. Tre confronti prospettici: Brain normale vs gemello non-AI (effetto AI), Brain normale vs Brain blind (effetto peer observation), Brain vs Falco/Toro (benchmark complessivo). Note: il confronto non è randomizzato e non dimostra in modo assoluto causalità, servono finestre/blocchi e analisi statistiche pre-registrate.
3. Claude più dettagliato su criteri economici, budget e fasi; Grok più cauto su non-stazionarietà, leakage, complessità e tempi. Tempi 5–7 settimane per una prima costruzione + test vs 6–9 mesi per maturità completa NON devono essere presentati come promesse; milestone/test concreti prima di date.
4. Claude suggerisce catalogo iniziale SHORT classici e LONG shadow. Correzione: SHORT classici sono **candidati** non ancora validati fuori campione e con funding LONG/SHORT asimmetrico nei classici; il Pool ha tutte R sotto i CTL. Catalogo prod iniziale può essere solo NO_TRADE finché non esiste vantaggio OOS.
5. Claude propone limiti tipo 1,5% equity stop per trade, 6% rischio open, 4% daily, floor 450 USDT; questi numeri sono **proposte da definire** (non applicare automaticamente). Rispettare preferenza utente per scalp ma rischio calcolato in base allo stop e ai costi, non leva o margine da soli.
6. Esito operazioni manuali: mostrare sia `Brain puro` (senza override operatore, shadow/controfattuale) sia `Brain+utente` (eseguito PAPER). La riduzione del rischio e la chiusura singola manuale non devono essere bloccate dal validation gate delle nuove aperture; validare identità/duplicazioni invece.
7. Criticità note nel codice classici: sizing non vincolato al rischio a SL, daily halt non latched, funding simulato solo LONG. In V3 valutare **guardrail comuni** per confronto nuovo, pur registrando Falco/Toro come strategie meccaniche immutate sul piano dei segnali; i dati legacy rimangono benchmark storico separato.

## Schema definitivo proposto (ancora non approvato)
- `Market Data + Data Quality`: dati candela chiusa, prezzi, funding, OI, notizie con provenienza.
- `Feature + Probabilistic Regime Service`: probabilità 3 direzioni × 3 volatilità + transizione/stress; isteresi e test OOS.
- `Immutable Event Log`: un writer per portfolio, run_id, event_id, versioni di codice e costi; import legacy read-only; L0 eventi, L1 episodi, L2 statistiche, L3 ipotesi, L4 catalogo approvato.
- `AI Orchestrator`: DeepSeek valuta contesto/regime/candidati validati, gestisce posizioni e propone ipotesi; Claude revisiona a trigger; budget hard e schema di output validato, fallback NO_TRADE nuove aperture.
- `Strategy Catalog + Selector`: la AI può cambiare dinamicamente fra strategie **già approvate** in risposta a un cambio di regime confermato. Le nuove strategie entrano solo dopo replay/OOS/shadow e nuova versione approvata.
- `Deterministic Risk and Execution`: size dalla perdita a stop, risk budgets per posizione/lato/portafoglio/correlazione, buffer liquidazione, hard kill floor 450 USDT, chiusure locali indipendenti dalla disponibilità AI, una coda di comandi per esecutore, idempotenza e ricevute.
- `3 Portafogli PAPER`: Falco e Toro con regole meccaniche, Brain AI adattivo; contabilità isolata ma archivio comune consultivo.
- `2 Shadow Twins`: uno senza AI, uno Brain blind senza informazioni dei classici; alimentazione dati, fill/costi e periodi allineati al Brain.
- `Unified PWA`: tre schede, stato dei worker, grafici equity normalizzati e risk, controlli manuali per ID, motivi di take-profit e teaching.
- `Evaluation`: protocollo pre-registrato, capitale uguale, costi coerenti, rapporti netti per rischio e drawdown, controlli su più regimi, distinzione del contributo utente, AI e peer observations.

## Roadmap consigliata e gate
- **F0 già parzialmente completata**: worker Falco, Toro, Brain Free, AI Shadow, Turbo, Sidecar, Pool fermati e restart=no; dashboard SuperBot running. Backup locale generale completo e restore/diff/SQLite PASS, ma **backup esterno cifrato da verificare**. Vecchio stato F0 nel PDF prima dello spegnimento è superato. Falco PAPER 6 posizioni aperte in file stato, Toro 2, nessuna chiusura o reset forzato.
- **F1** Inventario audit degli storici e riconciliazione; schema eventi; Risk Gate puro testabile, modello costo/funding comune.
- **F2** Comandi e idempotenza (PR #27 + teaching), controlli di chiusura e pausa, ricevute.
- **F3** Dashboard mobile unificata; prima reader, poi comandi autenticati.
- **F4 in parallelo** regime probabilistico, catalogo SHORT/LONG validati OOS, shadow OOS, baseline; se zero strategie validate, Brain NO_TRADE e i test continuano.
- **F5** Brain DeepSeek/Claude in SHADOW, gemello no-AI e blind, budget controllato.
- **F6** nuova run PAPER 1000/1000/1000 con test preregistrati, almeno più regimi e statistiche robuste; confronto non su singoli giorni o PnL assoluti.
- **F7** post-mortem, ipotesi, sfidanti/shadow, approvazione utente per promozioni; non cambia le regole nella stessa run comparativa.

## Dati del report esterno da non interpretare come fatti verificati
- “Due terzi del software esiste” non è stato misurato.
- Tempi 5–7 settimane/6–9 mesi, costi AI 20–35 USD/mese, campioni minimi es. 30/100/300 trade, soglie rischio proposte vanno pianificati/testati e non sono garanzie.
- Il modello AI non si auto-riaddestra solo dalla memoria; apprendimento continuo = archivio + ipotesi + validazione + promozione controllata.
- Evitare inserire secrets, wallet veri, dataset privati o PDF allegati con informazioni sensibili nel repository pubblico.

## Prossima decisione
Presentare comparazione al titolare e raccogliere OK per *solo sviluppo isolato* su ramo V3 con test, **senza** riavviare trading o provider AI live e senza merge/deploy. Nessuna implementazione effettuata con questa nota.
