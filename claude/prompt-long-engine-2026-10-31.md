# Incarico — motore LONG per Falco/Hawk e Toro/Bull, consiglio consultivo per Brain
31 ottobre 2026. Progetto: alexiptv82/SuperBot-Trading.

## Obiettivo e divisione del lavoro
Progetta un motore deterministico LONG completo: ricerca opportunità, ingresso, invalidazione, gestione e uscita. Deve essere compatibile con Falco e Toro e fornire un contesto consultivo al nuovo Brain.
ChatGPT Work completa servizio Brain, gestione posizioni, dashboard, memoria e integrazione dei classici. Il tuo perimetro è il nuovo modulo LONG isolato e il suo laboratorio: non modificare in parallelo i componenti condivisi. Non effettuare merge, deploy, avvii o chiamate AI a pagamento.

L'utente ritiene che gli SHORT dei classici funzionino bene nei ribassi: è un'ipotesi da misurare con costi e drawdown. Non presentarla come vantaggio dimostrato. Non costruire il LONG semplicemente invertendo segni e soglie dello SHORT.

## Leggi prima e fissa le versioni
Repository: https://github.com/alexiptv82/SuperBot-Trading
Sul ramo diario leggi LEGGIMI.md, STATO.md, MANUALE-OPERATIVO.md, SINCRONIZZAZIONE-WORK-CHAT.md e le voci più recenti pertinenti.
Ispeziona il codice effettivo dei classici su rule-pool e sul candidato work/classics-structural-advisory-20261030, inclusi backend/desk/signals.py, engine.py, cli.py, config e test. Registra SHA completi, dipendenze e differenze. Se un file o ramo manca, dichiaralo senza inventarne l'interfaccia.
Sul ramo candidato trovi docs/structural-advisory-and-short-methodology-2026-10-30.md.
Work sta usando work/brain-completion-20261031 e work/brain-completion-app-20261031: sono componenti riservati a Work.

## Vincoli
- Solo PAPER. Preserva conti, journal, memoria e storici; nessun reset.
- SHORT esistente e relativo scorer devono restare invariati. Dimostralo con diff e regressioni.
- L'attuale avviso cambio trend resta consultivo: non trasformarlo implicitamente in ingresso LONG, blocco SHORT o aumento del punteggio.
- La nuova strategia LONG sarà un modulo separato, opt-in/default off. Il riuso dell'esecutore e delle protezioni deve essere esplicito.
- Sizing, leva, slot, limiti di perdita e buffer di liquidazione appartengono alla gestione del rischio, non al sensore LONG. Leggi i valori reali e distingue impostazioni attuali da desideri storici. Non cambiarli per migliorare un backtest; se una proposta non è fisicamente eseguibile, viene rifiutata.
- Slot vuoto e NO_TRADE sono risultati validi. Nessuna quota obbligatoria di LONG, recupero perdite, martingala o riempimento forzato.
- Le chiusure manuali confermate sono esempi consultivi, non regole TP automatiche.

## Disegno richiesto
Parti da un modello semplice e spiegabile, preferibilmente non oltre due famiglie di setup:
1. Continuazione rialzista dopo pullback/reclaim, con struttura e invalidazione.
2. Inversione anticipata confermata, distinguendola da un rimbalzo fragile in ribasso.
Puoi proporre alternative motivate: non accumulare indicatori senza misurarne il contributo.

Definisci per ogni setup:
- timeframe di contesto, setup e trigger; dati e warmup minimi;
- condizioni esatte di attivazione e disattivazione, espresse con formule o pseudocodice;
- momento in cui ciascun dato è disponibile e prima esecuzione lecita;
- invalidazione, stop iniziale, target, eventuale uscita parziale/trailing/breakeven, uscita temporale e uscita per cambio struttura;
- scadenza del segnale, cooldown e condizioni di nuovo ingresso;
- comportamento con spread ampio, volatilità estrema, liquidità scarsa e gap;
- cosa succede se esistono già posizioni o segnali SHORT sullo stesso simbolo.

Analizza medie mobili, struttura, volatilità e volume solo dove aggiungono informazione. Funding/OI/order flow sono facoltativi e richiedono dati storici verificabili disponibili a quel momento.
Non inventare CVD o assorbimento VSA da sole candele OHLCV. Se usi proxy, etichettali e misura separatamente il loro contributo. Dati assenti o vecchi devono produrre uno stato esplicito.
Se contesto e trigger discordano, specifica se è NO_TRADE o un diverso setup: nessuna decisione implicita.

## Contratto di integrazione
Proponi una funzione pura e causale, per esempio evaluate_long(context, as_of_ms, parameters), con output versionato:
schema_version, strategy_version, symbol, as_of_ms, data_cutoff_ms, valid_until_ms, setup, regime, decision (NO_TRADE/CANDIDATE), trigger, invalidation, exit_policy, reasons, missing_data, input_quality.
Evita numeri chiamati probabilità/confidenza se non calibrati fuori campione.
Valori non applicabili devono essere null, non inventati.

Il motore dei classici riceverà eventuali candidati attraverso un adapter da integrare successivamente da Work. Proponi una politica esplicita per conflitti LONG/SHORT; non introdurre hedge o chiusure forzate senza una decisione separata.
Per Brain fornisci un secondo adapter long_advisory: fatti, setup, invalidazione, età e limiti del dato. È un consiglio: Brain può scegliere HOLD o SHORT senza veto e senza esecuzione diretta del modulo.

## Verifica prima dei risultati
Prima di vedere i risultati scrivi una preregistrazione: ipotesi, varianti consentite, dati, split temporali, costi, metriche e criteri di promozione/scarto.
Usa dati reali con provenienza, timestamp, hash, copertura, buchi e universo degli strumenti documentati. Non dichiarare backtest se non puoi eseguirlo.
I dati Bitget 16–23 ottobre 2026 già utilizzati nel progetto sono sviluppo, non holdout nuovo.
Il periodo 1 novembre–1 dicembre è stato indicato nel laboratorio strutturale: non dichiararlo disponibile o completato prima che esista.

Esegui confronto con LONG classico attuale, specchio meccanico dello SHORT e baseline semplice. Aggiungi ablation dei singoli filtri, walk-forward e holdout intatto, sensibilità ai parametri e stress sui costi.
Considera commissioni andata/ritorno, spread, slippage, funding, limiti di lotto, liquidazione e tempi di esecuzione. Segnali su barre chiuse; fill solo dopo disponibilità del segnale. Se TP e SL sono toccati nella stessa barra senza dettaglio sufficiente, usa un criterio conservativo dichiarato.
Evita look-ahead, selezione retrospettiva dei simboli e ottimizzazione sul test. Valuta dipendenze fra trade e correlazioni fra monete.
Riporta numerosità, expectancy netta, profit factor, drawdown, turnover, esposizione, perdite di coda e intervalli d'incertezza. Il win rate da solo non basta. Se i dati sono insufficienti, il verdetto deve essere “evidenza insufficiente”.
La promozione va valutata anche sull'intero portafoglio LONG+SHORT a slot e capitale invariati: il LONG non deve migliorare solo isolatamente sottraendo risorse agli SHORT.

## Consegna
1. Diagnosi del codice esistente con SHA e limiti osservati.
2. Specifica autonoma e tabella di ingresso/uscita/NO_TRADE.
3. Modulo isolato, adapter proposti e test causali, buchi, dati scaduti, bordi e determinismo.
4. Preregistrazione, comandi riproducibili, dati e risultati effettivi separati dalle ipotesi.
5. Diff e lista file toccati, regressioni SHORT invariate.
6. Rapporto per Work con punti d'integrazione, rischi, decisioni aperte e verdetto: scartare, raccogliere altri dati o candidato PAPER.
Non promettere segnali sempre affidabili o profitti. Prima di modificare file condivisi consegna a Work il modulo e il contratto.
