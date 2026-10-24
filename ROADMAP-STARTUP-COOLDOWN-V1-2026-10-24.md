# ROADMAP — Startup Cooldown V1 (Hawk + Bull)
**Stato: PROPOSTA APPROVATA PER LA ROADMAP, NON IMPLEMENTATA / NON DEPLOYATA**  
**Aggiunta:** 24 ottobre 2026, in seguito a un batch di aperture SHORT dopo il rollback PAPER di Capital Management V1.

## Problema osservato
Dopo manutenzione e riavvio dei due bot PAPER sul codice `297b126`, l'assenza di un periodo di stabilizzazione ha portato a un'esposizione sincrona SHORT. Audit VPS sola lettura al 24/10/2026 18:54 UTC: 10 posizioni Hawk e 6 Bull, tutte SHORT e a ROI netto stimato negativo. Dai journal: **12 aperture Hawk + 8 Bull** dall'ultimo avvio, con **2 chiusure stop loss per bot** (XRP e SOL), **16 posizioni residue**. Le 20 aperture storiche non sono 20 posizioni contemporaneamente aperte, ma il fenomeno di riempimento/rimpiazzo slot permane. Gli SL sono presenti su tutte le posizioni; non erano attraversati ai prezzi contemporanei registrati. Sei cicli completati per bot senza errori. Fonte: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40122819557

## Obiettivo
Garantire che, dopo qualsiasi arresto (deploy, rollback, manutenzione, crash, riavvio host, nuova istanza), Hawk e Bull **rivalutino da zero il mercato e la validità di ogni ingresso**, senza riutilizzare in massa segnali stantii o occupare slot solo perché liberi. L'attività 24/7 resta voluta: il problema è la qualità e il tempismo delle decisioni, **non** il numero di ore operative. **Uno slot vuoto è una scelta intelligente.** Nessuna chiusura forzata delle posizioni esistenti: stop, liquidazioni, TP e gestione delle posizioni devono proseguire durante il blocco di nuova esposizione.

## Requisiti utenti da preservare
1. Periodo minimo di attesa **15–30 minuti** senza nuove posizioni.
2. Raccolta di un ciclo completo di candele **1h chiuse dopo il riavvio** per tutti i simboli monitorati.
3. Confronto con l'ultimo segnale affidabile salvato prima dello stop; se almeno **3 simboli** hanno cambiato direzione, alert Telegram *prima* dello sblocco.
4. Aperture scaglionate: al massimo **2–3 per ciclo**, distanza di **almeno un ciclo da 15 minuti** tra batch.
5. Applicazione al riavvio qualunque ne sia la causa, anche con portafoglio in perdita e posizioni già aperte.

## Proposta conservativa di implementazione
**Fase STARTUP_FREEZE**: sempre all'avvio, blocca SOLO nuova esposizione (nuove posizioni, DCA/split che aumentino la posizione) a livello di motore/portafoglio, prima che vengano elaborate decisioni di ingresso. Le uscite protettive restano operative senza interruzioni. Debounce di riavvii ripetuti; lo stato del gate è persistente, crash-safe, datato e legato a bot/run; NON ricrea denaro, NON tocca il Capital Management V1 e NON avvia bot duplicati.

**Condizione temporale e di dati:** attesa minima iniziale proposta = **30 minuti**, più almeno una candela 1h *interamente successiva all'avvio* e già chiusa (non candela in formazione), per ciascun simbolo rilevante. Nota imprescindibile: queste condizioni combinate richiedono generalmente **da 60 a quasi 120 minuti**; 15–30 minuti da soli NON soddisfano la richiesta di una candela oraria interamente nuova. Se i dati mancano/stale, si resta in freeze. Un'alternativa ibrida (prima candela 1h che si chiude dopo il restart, benché iniziata prima) richiederebbe separata approvazione esplicita, perché non è la stessa garanzia.

**Confronto pre/post:** conservare l'ultimo segnale affidabile COMPLETATO prima dell'arresto, con ora UTC, timeframe, confidenza e versione schema; ai successivi snapshot chiusi confrontare solo simboli con dati validi in entrambe le finestre, identico timeframe e definizione del segnale. Un cambio su >=3 simboli univoci => `STARTUP_REGIME_SHIFT_ALERT` Telegram (dedup, invio registrato); fino a invio confermato non sbloccare gli ingressi. Se il pre-stop non è disponibile (es. primo avvio) non inventare segnale: freeze esteso e alert `BASELINE_MISSING`, con percorso di recovery da definire.

**Riapertura graduale:** non usare un backlog dei segnali formati prima o durante freeze. Rigenerare candidate, scores, spread, regime, rischio e liquidità usando dati nuovi. Limite PROPOSTO condiviso **max 3 nuove posizioni globali Hawk+Bull ogni 15 minuti**, non 3 per bot: altrimenti 3+3 riaperture simultanee continuerebbero il problema. Max **2 per bot** in ciascuna finestra; controllo unico con lock/dedup, resistente a riavvii/crash e a due processi concorrenti. Il cap è sul numero delle nuove esposizioni, indipendentemente dagli slot liberi; le posizioni chiuse da SL non liberano l'intero limite per un nuovo batch nello stesso intervallo. Il limite di rischio/cap già presente resta vincolante, non viene aumentato. In assenza di coordinatore globale, bloccare nuove esposizioni anziché consentire cap parziali divergenti.

**Telegram**: messaggio compatto con count flip, simboli, direzioni prima/dopo, qualità dati, tempo fino al prossimo batch. Nessun ordine né modifica automatica della posizione a seguito del solo alert. Fail-closed al confine di nuova esposizione se la notifica obbligatoria non è inviata.

**Telemetria:** heartbeat `startup_cooldown` con `active`, `restart_ms`, `earliest_release_ms`, `last_fresh_1h_bar_ms`, `regime_flip_symbols`, `notification_status`, `last_batch_ms`, `batch_count`, `ready_reason`; esporre in dashboard senza alterare le metriche Capital V1. Nessun utilizzo di chiavi exchange/live per i primi test.

## Decisioni ancora da approvare nel dettaglio
- L'utente ha proposto **15–30 minuti** di cooldown; per soddisfare una candela 1h completa *post avvio* il freeze effettivo va oltre. Approvare esplicitamente la precedenza del vincolo 1h completo (raccomandato).
- Confermare la proposta più prudente **3 aperture globali/15 min e max 2/bot**, versus 2–3/bot.
- Definire il fallback operatore per mancanza dello snapshot pre-stop o guasto persistente Telegram, senza aprire di nascosto.
- Con il mercato molto cambiato (>=3 flip), l'alert è obbligatorio, ma non è ancora richiesta approvazione manuale umana; se desiderata in live richiederà policy dedicata.

## Test e rilascio
1. Suite offline parametrica: restart da ciascuna causa; candele chiuse/non chiuse/stale; timezone UTC e riavvio 59 min prima dello scadere dell'ora; score invertiti >=3 su simboli distinti; prezzi mancanti; notifiche mancanti; doppio bot e doppio writer; dedup batch e crash recovery.
2. Replay del 24/10/2026 con gli stessi snapshot: misurare numero/valore delle aperture evitate o ritardate, *senza attribuire P&L controfattuale certo*.
3. Periodo shadow in PAPER per osservare tempi/costi; poi PAPER abilitato solo previa autorizzazione esplicita e backup/rollback certificati.
4. Valutare LIVE **solo come progetto futuro separato** con safety review, senza alcuna attivazione automatica. Hawk e Bull restano PAPER.

## Vincoli correnti
**Nessuna modifica al codice `297b126`, nessun redeploy, nessun merge su `rule-pool` e nessuna azione sulle posizioni** a seguito di questa annotazione. Fix B rimane sul branch separato in shadow; Capital Management V1 resta OFF. Questo è un requisito di roadmap, non una feature operativa.


## Addendum 24/10/2026 — Regola fondamentale di trading professionale (prioritaria)

**Correzione esplicita dell'utente:** il problema non è che il bot lavora 24/7 o che riapre dopo uno stop; è che non può aprire *senza rivalutare se il momento è adatto*. Non si persegue il riempimento degli slot. Un'opportunità valida può occupare uno slot liberato anche dopo SL, TP o futura uscita Fix B; se non c'è opportunità, si resta fuori dal mercato. Il tempo senza esposizione è una decisione legittima e spesso razionale.

### Procedura ideale per ogni nuova esposizione (proposta AI, non implementata oggi)
- Riesaminare al momento della decisione regime, trend aggiornato, possibile inversione, volatilità, volumi, liquidità, asimmetria del rischio, qualità del segnale e costi, come fosse la prima analisi del simbolo.
- Verificare anche opportunità **inverse** sul simbolo liberato (per es. da SHORT a LONG dopo un rimbalzo confermato), ma **non effettuare inversioni automatiche** e non riusare il segnale precedente.
- Evitare il bias di riempimento slot, il bias da capitale disponibile, l'inseguimento dopo SL e le trappole di mercato.
- Istruzione da includere esplicitamente nella **futura revisione del prompt Claude**, dopo approvazione e test: **«Puoi raccomandare di non aprire nessuna posizione. Slot vuoto = scelta valida.»**
- Lo **Startup Cooldown** rimane una protezione meccanica di difesa in profondità, NON il sostituto della capacità di decidere quando **non** fare trading.

### KPI della selezione degli ingressi — target, non garanzia
- Obiettivo strutturale utente: **70–80% delle posizioni definitivamente chiuse in profitto netto**, **20–30% o meno chiuse per stop loss**.
- Misurare con denominatori espliciti: tutti i trade definitivamente chiusi nel periodo; distinguere TP, Fix B intelligente, SL, liquidazione, chiusura manuale, parziali e costi. Segmentare per Hawk/Bull, regime di mercato e dimensione del campione, includendo intervalli d'incertezza.
- Affiancare al win rate valore atteso netto per operazione, payoff medio win/loss, perdita massima, drawdown, costi e concentrazione di esposizione: un 80% di vittorie può essere comunque perdente se le perdite residue sono troppo grandi. **Mai inseguire il KPI falsando la classificazione delle chiusure.**
- **Episodio odierno:** alle 18:54 UTC del 24/10 erano aperte 16 posizioni SHORT tutte con ROI netto stimato negativo; i journal mostravano quattro chiusure effettive per SL (due per bot), quindi **0 trade profittevoli su quelle quattro chiusure**. Il **0%** riguarda esclusivamente tale sottocampione di trade già chiusi, **non** il risultato finale delle 16 posizioni ancora aperte. La lettura causale «non è stata rivalutata la direzione/regime a sufficienza» è un'ipotesi di qualità da verificare col replay, non una prova che gli algoritmi non abbiano calcolato alcun segnale.

**Stato decisione:** questa è una lezione approvata per il cervello PAPER e un requisito di roadmap, **non** autorizzazione a cambiare ora `build_prompt`, `SYSTEM`, soglie, ingressi, strategie o limiti. Nessun deploy o ordine sul VPS. Capital V1 OFF; Fix B solo branch separato shadow; runtime `297b126` invariato.
