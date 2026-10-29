# Brain: contesto AI DeepSeek + Claude e riferimento tecnico storico

29 ottobre 2026. Sviluppo offline, ramo work/brain-ai-context-20261029.
Base48808a6aa5cd9d2a4a1933b27ebc7828fd3ac480. Nessun rilascio operativo.

## Cosa è collegato

Il nuovo percorso prepara il contesto di un wallet, incorpora il riferimento tecnico storico già realizzato, riceve una proposta dal provider principale e può chiedere un secondo parere. Prima di prenotare un piano ricontrolla account, esposizione, scadenza e guardie esistenti.
Non è un servizioH24 e non contiene una nuova implementazioneHTTP. Le prove usano callback sintetiche, senza chiavi o costi.

Percorso:
BrainPair.prepare_ai_request -> AIRequest immutabile -> ai_analysis.evaluate fuori dal tick -> BrainPair.accept_ai_analysis con timestamp e quote aggiornati -> accept_ai_plans già esistente -> tick PAPER già esistente.

## Contesto di un solo account

ai_context.build_request richiede stato/spec coerenti PAPER e digest del mandato corrispondente. Non somma saldi o cronologie diHawk/Bull.
Include capitale iniziale, cassa, equity solo se marcata con quote fresche, posizioni, margine usato/prenotato, stato pausa/daily stop e limiti espliciti. Non sceglie nuovi limiti finanziari.
Il contesto può rappresentare un singolo account da2000USDT: test sintetico presente. BrainPair continua però a possedere i due wallet attuali nel laboratorio. Non è stata creata una classe di wallet operativo unico, né eseguita migrazione/reset/somma dei database o cambiata la soglia rischio.
Il passaggio al conto unico reale del progetto richiederà mandato finanziario completo e procedura dati separata. Il fixture2000 non è una configurazione attivata.

## Mercato e riferimento LONG/SHORT

Per ogni candidato dello scanner esistente:
- simbolo/direzione/setup e timestamp del segnale;
- quote con freschezza d'ingresso già definita;
- ultime6candele chiuse1m e6chiuse5m, dopo validazione delle finestre richieste dallo scanner;
- vincoli contrattuali selezionati;
- classica lettura consultiva prodotta da legacy_reference.build_reference, con entrambi i punteggi e avvisi del codice storico.

Candidati con quote/serie/contratto mancanti o scaduti vengono esclusi con motivo; candele future e colonne extra non entrano nel prompt. Lo scanner attuale resta breakout1m/5m: questa integrazione non aggiunge automaticamente reversal/bounce o autorizzazioni a direzioni non eleggibili.
Un riferimento storico mancante/errato è dichiarato unavailable, non fabbricato o trasformato in ordine. Se un riferimento usato scade durante l'analisi, occorre nuova analisi prima di ammettere l'ingresso.
La verifica dei blob dello scorer effettivamente eseguito resta responsabilità del chiamante descritta nel dossier precedente; non si pretende che metadati copiati dimostrino il calcolo.

## Prompt e risposta

Prompt comune: confrontare LONG/SHORT e timing, calcolare costi netti, scegliere congiuntamente margine/leva/stop/target entro mandato, HOLD ammesso, nessun obiettivo rigido20%, nessuna quota di trade.
I testi di mercato/memoria/riferimento sono dati, non istruzioni. Non si richiede ragionamento interno esteso; si chiedono brevi casi ed evidenze verificabili.
JSON richiede context_id, plans, assessments, summary. Assessments copre i simboli eleggibili con long_case, short_case, decision e opzionali review_flags normalizzati.
Plans conserva il contratto già esistente con ttl_ms; ID e timestamp assoluti forniti dalmodello sono scartati. Un piano malformato resta un rifiuto individuale nelcoordinator: non si perde tutto il resto della risposta.
Nessuna confidenza AI viene convertita in rischio o size.

## DeepSeek e Claude

evaluate richiede callback esplicite (system,user), senza selezionare trasporti o leggere variabili segrete:
- il trasportoDeepSeek esistente restituisce content/usage/finish_reason;
- call_claude esistente restituisce(text,usage).

Entrambi i formati sono gestiti senza modificarne i file operativi. La configurazioneScalp ora indica REVIEW_PROVIDER=claude; l'IDSol precedentemente predisposto è rimosso da questo ramo secondo decisione utente. ModelloClaude e credenziali rimangono nel trasporto già configurato: non inventati o letti in questa prova.

Revisione selettiva:
- un piano contraddice la preferenza non neutrale del riferimento storico;
- oppure per un simbolo proposto sono presenti timing_uncertain/timeframe_conflict.

Non sono soglie di probabilità calibrata. I flag sono valutazioni del primo modello, non prove indipendenti; il routing è esplicito e misurabile. HOLD senza nuovi piani non attiva inutilmente il secondo provider.
Claude riceve lo stesso contesto immutabile e la proposta primaria come dato non attendibile. Può restituire HOLD o piani corretti entro gli stessi vincoli; il riferimento non ha potere di veto assoluto.
Se revisione richiesta manca/fallisce, nessun fallback automatico al pianoFlash, a una size dimezzata o alle regoleclassiche. Risposte malformate, tronche, con JSON non finito/chiavi duplicate o context_id estraneo non sono eseguibili.
L'iniezione delle callback reali sarà un atto esplicito del futuro supervisore, dopo autorizzazione e accounting budget: nessuna chiamata a pagamento è avvenuta.

## Controlli dopo l'attesa

AIRequest contiene JSON immutabile e IDsha256, account, orari e fingerprint dell'esposizione.
Il fingerprint include cassa, quantità/lati/prezzi/stop/target/margini/funding delle posizioni, prenotazioni, stato daily/pausa/coverage e identità dell'esperimento. Non include heartbeat, quote, metriche o cursori candela che possono avanzare normalmente durante l'attesa.
Prima dell'ammissione:
- richiesta e corpo devono corrispondere al loro hash;
- account/mandato devono ancora corrispondere;
- clock non deve tornare indietro e il deadline non deve essere superato;
- esposizione e protezioni non devono essere mutate;
- la revisione necessaria deve essere completata;
- reference deve essere ancora valido;
- i piani passano comunque dalle guardie correnti con quote aggiornate, daily stop, cap, overshoot e stop/costi.

Il controllo della richiesta alterata avviene anche prima di invocare callback. Il clock corrente pre-chiamata e budgetAPI rimangono responsabilità del supervisore: evaluate non interroga un orologio globale né può certificare quanto durerà il trasporto. Le callback non devono bloccare il thread dei tick protettivi.
Un marker persistente last_ai_context_id cambia il fingerprint dopo una risposta consumata: ripetere anche unHOLD già processato dopo restart non genera un secondo ciclo ammissibile. Nessuna migrazione di schemaDB; statoJSON esteso compatibilmente.

## Memoria e osservabilità

prepare_ai_request legge soltanto le ultime10chiusure del wallet selezionato. Il prompt filtra episodi futuri o esplicitamente di account diverso, inoltra una whitelist di campi e dichiara memory_is_not_retraining.
Non è una libreria persistente di lezioni validate e non prova che il modello stia migliorando.

Il nuovo evento ai_context_processed registra ID, ruolo finale, revisione, orari, conteggi accettati/rifiutati e soli contatori token riconosciuti. Non salva rawprompt, testo integrale risposte, messaggi di errore o chiavi.
Usage assente è ignota, non costo zero. I token non sono una stimaUSD né un ledger di spesa reserve/settle. Prima di collegare chiamate reali servono budget crash-safe, misure di latenza/costo e gestione credenziali esterna.

## Verifiche

25nuovi test di integrazione con callback sintetiche:
- contesto di un account e fixture2000 senza fusioneDB;
- punteggi e costi, memoria causale, esclusione dati scaduti/colonne extra;
- DeepSeek -> prenotazione -> esecuzionePAPER con motore esistente;
- Claude stesso snapshot/HOLD o piano rivisto, selettività e mancanza/errore;
- JSON corrotto/duplicato/troncato, richiesta alterata e assenza di chiamate;
- posizioni/prenotazioni/cassa/stop/funding cambiati, heartbeat/metriche innocui;
- expiry, quote correnti oltre trigger, re-invio dopo restart;
- validazione indipendente dei piani e audit senza dati sensibili.

CIisolataPython3.10/3.11 esegue anche125test precedenti, quindi150perinterprete. Stato e commit finali nel diario.
GuardiaGit protegge backend/desk, brain_free, deploy, frontend e Dockerfile operativo rispetto alla base48808.

## Stato operativo e seguito

Sono stati aggiunti il contesto e il percorso di ammissione offline; nessun providerH24 o supervisore avviato, nessun merge/deploy/VPS o modifica alBrainattivo.
Mancano attivazione account unico con mandato esplicito, reader causale del riferimento nel feed runtime, supervisore/trasporti autorizzati/accounting API, audit recenti tradeBrain su dati disponibili e prove paper comparabili. Restano successivi, non dichiarati completati da questi test.
Ripristino del codice con nuovo revert, base48808preservata; mai reset dei dati o forcepush.

AI: chatgpt
