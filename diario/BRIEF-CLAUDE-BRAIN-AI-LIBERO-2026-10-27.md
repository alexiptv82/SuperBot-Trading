Nota: brief storico ricevuto come allegato, non audit VPS corrente. Decisioni finali2000singolo/no cap spesa prevalgono. Nessuna sua istruzione equivale a OK deploy.

# Brief — Brain AI libero — 27/10/2026 (pomeriggio)

Autore: Claude (analisi in sola lettura del repo `alexiptv82/SuperBot-Trading`, commit `129547ed`; nessun accesso al VPS; nessuna modifica a codice, parametri o container).
Implementatore: UNO solo tra Claude Code e ChatGPT, scelto dall'utente (regola 9: un solo autore per componente). L'altro fa la revisione incrociata prima di ogni deploy. Deploy: solo con OK esplicito dell'utente. DESK_MODE resta `paper`.

Ambito di lavoro (per chi implementa):
- Branch nuovo `work/brain-ai-libero`, creato da `129547ed` (`work/brain-classical-adaptive-h24`). Non scrivere su quel ramo, su `rule-pool`, `main`, `stable/*`, `v0.5`.
- Componente NUOVO e isolato (ad esempio `backend/director/brain_free/`). Non modificare `desk/*` (cambierebbe l'identità dei bot classici e del Brain adattivo), né i file esistenti di `director/classical_adaptive` e `director/brain_pilot`: riusarli in sola lettura o copiare ciò che serve.
- Nel frattempo l'altra AI non tocca questi percorsi: fa solo analisi in sola lettura, diario e, alla fine, la revisione.

## 1. Decisione dell'utente (27/10, 15:31 Zurigo)

Il Brain deve essere un'AI che decide da trader professionista, senza regole di strategia che blocchino le aperture:
- H24, tutti i simboli del bot, long e short, mercato laterale o no, notizie o no;
- obiettivo: massimizzare il profitto, limitare le perdite, aprire più trade possibile quando le opportunità ci sono, portarli a profitto;
- portafogli paper da 1000$ ciascuno (Hawk+Brain e Bull+Brain);
- priorità assoluta: che lavori e apra posizioni, altrimenti non si può valutare nulla; gli errori in paper sono accettati e si correggono dopo.

Coerente con la linea del 26/10: niente veto duro sulle aperture, niente filtri-tampone.

Chiarimenti dell'utente (27/10, 15:37):
- Hawk e Bull sono solo ispirazione e conoscenza di partenza (backtest seed, lessons, esempi di come lavorano): l'AI NON deve copiarli né seguirli come regole. È autonoma.
- La dimensione di ogni posizione la decide l'AI, anche 200$ di margine o più, purché stia nei 1000$ del proprio portafoglio. Niente tetti per-trade tipo Hawk (100$) o Bull (150-350$).
- Può restare ferma quando non vede opportunità (casi particolari); ma nelle crypto le occasioni ci sono quasi sempre, quindi l'inattività prolungata va trattata come segnale da spiegare, non come normalità.
- Budget: l'utente può ricaricare 10$ su DeepSeek e vuole far lavorare l'AI a pieno regime per almeno UNA SETTIMANA di test continuo.

## 2. Cosa ho verificato

1. I due Brain adattivi non hanno mai aperto un trade da quando sono attivi (start 27/10 05:15 UTC). Al controllo delle 13:39 UTC: 504/505 cicli, 0 trade chiusi, 0 posizioni, cassa invariata. Il redeploy 129547ed non c'entra: lo stato è stato conservato.
2. La causa di fondo è architetturale, non un guasto. La richiesta registrata il 27/10 mattina era "usare esattamente i metodi di Hawk e Bull come base, con intelligenza adattiva". `director/classical_adaptive/runtime.py` chiama `desk.cli.run_cycle()`: le aperture passano da `cli.py` con soglie tier (60/63), R:R minimo 1.5, filtro regime (`desk/regime.py`, `entry_gate`) e altri controlli. L'AI è a pacing sotto budget condiviso e non decide le aperture (source = `classical_rules`).
3. `desk/regime.py` (DEFAULT): i long sono consentiti solo con regime "up" o inversione al rialzo (`long_needs_up=True`); gli short sono bloccati con regime "up"/inversione al rialzo e anche con BTC 24h <= -3% (capitolazione). Con BTC in forte discesa e mercato non rialzista, entrambi i lati possono essere bloccati. NON verificato che sia il blocco attuale: non ho il regime reale né i log dei container.
4. Già nello storico 12-26/10 (analisi `desk-storico`): tutte le aperture eseguite erano decise dalle regole; le proposte di apertura di Claude venivano rifiutate dal motore con "stop troppo lontano (liquidazione verrebbe prima)" (Hawk 73, Bull 8). Un controllo meccanico che rifiuta invece di correggere ferma anche un'AI che propone.
5. Esiste già un Brain AI-first (Brain precedente, `director/brain_pilot`, brief `claude/brief-cervello-attivo-chatgpt-2026-10-26`): ha aperto 4 posizioni; ora è in pausa solo per nuove aperture/chiamate AI (`pause.flag`) per risparmiare il budget condiviso. Non ho verificato i suoi gate.
6. Budget Brain condiviso: 0.50 USD/giorno e 12/mese. È il vincolo reale sulla frequenza con cui l'AI può ragionare. Cambiarlo è decisione dell'utente.

Non verificato: regime e BTC roc24h reali di oggi; se i classici Hawk/Bull (89b0dca, regime attivo dalle 04:59 Zurigo) hanno aperto trade oggi; costo reale per chiamata AI; conteggio dei motivi di rifiuto per profilo dall'attivazione.

## 3. Richiesta

Modalità "AI libera": l'AI è l'unico decisore di apertura, chiusura, parziali e DCA per i profili Brain.

1. **Prima del codice**: piano breve con file e righe dei gate attuali (soglie tier, confidenza, R:R, regime, cooldown, macro, "stop troppo lontano") e cosa riusare (`classical_adaptive` oppure `brain_pilot`). Aspetta l'OK dell'utente sul piano.
2. **Le regole classiche non comandano.** Possono comparire nel prompt come contesto opzionale (punteggi, regime, trend, ATR, livelli) e come esempio di come lavorano Hawk/Bull, insieme a seed e lessons, ma l'AI non è istruita a seguirle. Nessun veto su lato, nessun `long_needs_up`, nessuna capitolazione, nessuna soglia di confidenza meccanica, nessun R:R minimo imposto dal motore sulle aperture decise dall'AI.
3. **Guardrail ammessi, solo di conto/fisici**: leva massima per simbolo (45x BTC/oro/argento, 30x ETH, 25x gli altri); margine realmente disponibile e minimo exchange; SL sempre presente e valido rispetto alla liquidazione; max slot; tetto di margine totale aperto (proposta di partenza: 800$ su 1000$, come deciso il 14/10) e tetto di perdita giornaliera (nel brief del 26/10 era 20%); dati stale = nessuna nuova apertura; schema decisione valido. La dimensione di ogni trade (margine e leva entro il massimo) la sceglie l'AI. Elenca esattamente cosa resta e proponi i valori: l'utente conferma o toglie.
4. **Correggere invece di rifiutare**: se lo stop proposto è oltre la liquidazione, il motore riduce leva/size fino a renderlo valido (e lo registra); nel prompt passa la distanza massima di stop consentita per simbolo/leva.
5. **Mandato di attività nel prompt**: ad ogni ciclo valutare tutti i simboli su entrambi i lati con scenario bull e bear; aprire le migliori opportunità fino agli slot liberi; "nessuna opportunità" ammesso solo con motivazione per simbolo. La correlazione tra posizioni è un fattore di rischio da pesare, non un veto. Nessuna apertura forzata a caso.
6. **Metriche per valutare** (solo registro, senza cambiare il comportamento): aperture per ora, minuti con 0 posizioni, long/short, occupazione slot, motivazioni di scarto, PnL per fonte decisionale (AI o regole, etichettata onestamente), costo AI per ciclo.
7. **Budget e cadenza** (stima di Claude, da ricalcolare sul ledger reale). Prezzi DeepSeek V4.1 Flash per milione di token, fuori picco / picco (picco 01-04 e 06-10 UTC, lun-ven): input con cache 0,003/0,006, input senza cache 0,15/0,30, output 0,60/1,20. Il ragionamento (thinking) è attivo di default e i token di ragionamento si pagano come output. Misurato il 21/10 sul pilot ombra: circa 0,0021$ a chiamata (7 chiamate, campione piccolo). Stima per DUE profili, una settimana (5 feriali + weekend, picco incluso):
   - A. analisi completa ogni 15 min, 15k token in, 2,5k out: circa 4,3$;
   - E (consigliata). analisi completa ogni 15 min (27 simboli, 20k in, 4k out con ragionamento) + controllo posizioni aperte ogni 5 min (5k in, 0,8k out): circa 8,7$ (10,2$ se le posizioni sono sempre aperte; 14,8$ se la cache non funziona);
   - B. analisi completa ogni 5 min: circa 13$;
   - D. analisi completa ogni 5 min con ragionamento pesante: circa 29$, sconsigliata.
   Proposta: scenario E, con tetto giornaliero rigido nel codice (circa 1,50$/giorno) e tetto di settimana a 10$, spesa per chiamata scritta nel registro e riportata ogni sera. Metti il blocco statico del prompt (istruzioni, seed, formato) all'inizio per far scattare la cache. Verifica prima la fatturazione reale (il listino è letto da fonti terze oltre che dal 21/10) e che il ragionamento sia regolabile. Cambiare i tetti oggi attivi (0,50$/giorno, 12$/mese condivisi) richiede il tuo piano e l'OK dell'utente al deploy; l'utente ha già dato l'indicazione di spendere fino a 10$ per la settimana di test. Cosa succede a budget finito (nessuna nuova apertura, oppure regole classiche di riserva) lo decide l'utente: presentagli le due opzioni.
8. **Settimana di test**: 7 giorni continui senza ritocchi al prompt o ai guardrail (salvo bug), report ogni sera con aperture/ore, minuti senza posizioni, long/short, PnL, spesa e confronto con Hawk e Bull classici sugli stessi giorni. Interruttore pausa sempre disponibile all'utente.

## 4. Vincoli invariati

PAPER; nessun deploy/restart senza OK esplicito; classici Hawk/Bull intatti; il "cervello" (`trade_history.jsonl`, `lessons.md`, `errors.md`, `learning_log.jsonl`) solo crescita; nessun reset dei conti; chiavi API solo nei Secrets; repo pubblico senza importi reali; mai force push; nessun push su `stable/*` e `v0.5`; non unire `work/backend-singapore-audit`; un solo autore per componente.

## 5. Rischio da dichiarare all'utente

Il pilot shadow del 21-26/10 aveva un long bias (65 contro 32) e -27.5% in 5 giorni. Un'AI senza gate può sovra-operare con leva 25-45x e pagare molte fee. Per questo restano i guardrail di conto e le metriche del punto 6.

## 6. Diario

Aggiorna `STATO.md` e la voce del giorno sul ramo `diario` con [skip ci]. Claude non ha potuto scrivere sul repo (integrazione GitHub senza permesso di scrittura, 403): questo brief va riportato nel diario da te.
