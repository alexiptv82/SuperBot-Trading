# Piano preliminare — rollback selettivo dei classici Hawk/Bull

27 ottobre 2026. Stato: **solo verifica e piano; attesa conferma dell'utente**. Nessun rollback, modifica al codice trading o redeploy eseguito.

## Salvataggi creati e verificati

- [backup/classici-2026-10-27](https://github.com/alexiptv82/SuperBot-Trading/tree/backup/classici-2026-10-27) punta esattamente a `89b0dca3e259c548ed82754c2301c7b024d18ff5`, versione dei classici nell'ultima verifica diretta disponibile.
- [backup/rule-pool-2026-10-27](https://github.com/alexiptv82/SuperBot-Trading/tree/backup/rule-pool-2026-10-27) punta a `d1701f22f2a615ac3ef05f96b9d1d3b297abf0bc`, HEAD operativo attuale del repository, comprendente anche lavoro successivo non deployato nei classici.

Sono riferimenti al codice, non backup dei dati o delle immagini Docker. Non è stato riscritto alcun branch. Nessun push su main, rule-pool, stable/*, nessun force push. Il runtime non è stato nuovamente interrogato da questa verifica: nessun trigger operativo è stato scritto, in conformità al nuovo vincolo. Le versioni in esecuzione restano quelle dell'ultima verifica, da riconfermare prima di un eventuale rilascio.

## Non esiste un unico commit delle run positive

La cronologia deriva dai deploy e dagli eventi già riconciliati, non dalla data autore dei commit.

| Codice | Finestra deploy UTC | Ora italiana del completamento | Ruolo nelle golden |
| --- | --- | --- | --- |
| a0afc63 | 12/10 14:48–14:49 | 12/10 16:49 | Prima parte |
| 7ced3a6 | 12/10 16:50–16:51 | 12/10 18:51 | Parte successiva |
| 5a4e383 | 13/10 06:36–06:37 | 13/10 08:37 | Audit chiamate Claude |
| 9fa667f | 13/10 07:51–07:52 | 13/10 09:52 | Parte centrale/finale, maggioranza ingressi |
| 5818aee | 15/10 19:45–19:47 | 15/10 21:47 | Ultima versione prima della fine run del 16/10 |

Le golden non sono quindi un esperimento eseguito integralmente su5818. La prima apertura Bull cade nello switchover iniziale43c79/a0 ed è incerta. Da precedente attribuzione: Hawk #2 apre42/76posizioni sotto9fa,30sotto7ced,4sottoa0; Bull #1 ne apre9/17sotto9fa,5sotto7ced,2sottoa0 e1incerta. Le attribuzioni golden sono da intervalli deploy, non code_version negli eventi open. Non risultano ingressi delle golden attribuiti al5818: quest'ultimo può incidere sulle successive gestioni/chiusure.

**Base candidata, da approvare:** `5818aee1e587f103d222510e761b30e02776ff15`, ultimo codice effettivamente presente nel periodo positivo e riferimento richiesto. Non lo presento come il codice che ha generato da solo quei profitti. Se l'obiettivo è invece ricostruire il codice della maggioranza degli ingressi, l'alternativa è `9fa667ff1103f037bec06f9131996366d27370c4`: comprende meno funzioni, perché il pacchetto5818 aggiunge macro, trading-hours, risposta Claude3000token, correzioniTP e comandi app. Non scelgo silenziosamente una baseline diversa.

Fonti: [audit cronologico](analisi-run-2026-10-27/REPORT.md), [eventi versione](analisi-run-2026-10-27/version_events.csv), [diff integrale5818→89](https://github.com/alexiptv82/SuperBot-Trading/compare/5818aee1e587f103d222510e761b30e02776ff15...89b0dca3e259c548ed82754c2301c7b024d18ff5).

## Cosa c'è nella baseline e cosa cambierebbe

| Voce | Baseline5818 | Classici89, ultima versione verificata | Piano selettivo da approvare |
| --- | --- | --- | --- |
| Soglia BTC/ETH/oro/argento | 60 | 60 | 60 |
| Soglia altcoinC | 70 | 63 | Ripristino70 |
| Slot Hawk | 10 | 10 | 10 |
| Slot Bull | 3 | 6 | Ripristino3 |
| Margine massimo Hawk/Bull | 100/350 PAPER | 100/350 PAPER | Invariato |
| Margine totale Hawk/Bull | 1000/1050 PAPER | 1000/1050 PAPER | Invariato |
| Leva per asset | 45 BTC/oro/argento,30 ETH,25altri | Stessi cap motore | Baseline, nessun nuovo cap |
| Daily stop legacy | 12% | 10%, CapitalV1off | Ripristino12%; non importare20% diV1 |
| Kill equity | 450 PAPER | 450 PAPER | Invariata |
| SL tecnico | 1,2ATR, clip0,3–3,5% | Identico | Identico |
| TP tecnico fallback | 1,8×SL | Identico | Identico |
| Pesi4h/1d | 20/15 | Classic20/15; P1opzionale | Baseline20/15, nessun bonusP1 |
| Regime mercato, rischioBull250, vetoSHORT | Assenti | Presenti | Esclusi se non approvati separatamente come dipendenza della correzioneLONG |
| Stagionalità | Formula originale | Formula additiva e confrontoBTC3giorni | Originale |
| Daily nativo | Assente; ricampionamento breve | Feed1d vero >=200barre | Nessun feeddaily aggiuntivo automatico |
| LONG e neutralità indicatori | LONG supportati, ma con difetti sulle uguaglianze/dati | CorrezioniFixA; bonusrimbalzoP1 spento nel profilo classic | Conservare anti-bias e correttezza del lato, da delimitare |
| Barre e gestioneDCA | Motore storico | Cursor, barre chiuse, DCA non allargaSL, barra ingresso controllata | Scelta esplicita richiesta: un ritorno letterale li rimuoverebbe |
| Chiusure e parziali | Close/partial_close già presenti | Presenti | Conservazione di base |
| Vault | Assente | Implementato, maV1off nell'ultima verifica | Recupero selettivo e test, senza cambiare sizing/rischio |

Il cooldown scalp è10minuti sia nella baseline sia nel codice89; il ciclo di revisione con scalp è15minuti. Una precedente descrizione nel rapporto di audit che indicava15minuti anche per il cooldown va letta come errore descrittivo: non è un parametro da modificare qui.

## Verifica delle tre funzioni richieste

### 1. Correzione LONG: presente, non coincide con un interruttore open_long

Entrambi i lati esistevano già in5818: le golden includono anche LONG. Le correzioni successive riguardano neutralità delle uguaglianze, RSIpiatto, medie4h coerenti con il periodo dichiarato e lettura del punteggio del lato della posizione.

In89 `signals.py` contiene `direction`, RSIpiatto=50 e EMA50/2004h su almeno200barre vere. `cli.position_info` separa il punteggio proprio e opposto. Il bonusrimbalzoLONG diP1 è disponibile ma NON attivo nel profilo classic; non va riattivato spacciandolo per correzione già operativa. La selezione del lato consentito dal regime è una funzione separata: conservarla significherebbe mantenere anche parte del regime, da approvare esplicitamente.

Proposta: riportare solo correzioni anti-bias e corretta gestione LONG/SHORT, con feed4h sufficiente se si mantiene EMA200vera. Questo modifica necessariamente alcuni input rispetto alle golden: non sarà una replica bit-per-bit della strategia storica. Nessun nuovo bonus direzionale o soglia inventata.

### 2. Salva profitto / chiusura anticipata: base presente, modulo avanzato non operativo

La baseline ha già:
- `brain.rules_decisions`: chiusura quando lo score del proprio lato scende sotto35 o quello opposto raggiunge60; può chiudere anche in perdita, perché è gestione del segnale, non garanzia di profitto.
- Prompt Claude che valuta hold/close/partial_close, gestioneTP1/residuo; motore eCLI eseguono le parziali.
- Fee, slippage e funding nel contoPAPER.

Non c'è invece un Profit Guardian avanzato attivo da “tenere”:
- `profit_guardian.py` dichiara **SHADOW ONLY**, senza connessione a engine/CLI o provider; gli esiti restano applied=false.
- `regime.py` ha ratchet e flip_exit, ma il profiloDEFAULT li tiene spenti salvo overrideenv; ultima configurazione descritta come solo filtro.

Quindi mantenere la capacità di chiusura anticipata/parziale già presente è possibile. Garantire una nuova valutazione continua del profittoNETTO, trailing o GuardianAI richiederebbe completare/attivare una funzione: non è un semplice rollback e NON è considerato approvato. Non abilito i moduli shadow automaticamente.

### 3. Protezione profitto giornaliero: esiste, ma è disattivata e accoppiata ad altre policy

`vault_manager.rollover/settle_pending`, `capital_runtime.rollover_today` e journal permettono accantonamento virtualePAPER alle00:00UTC, senza chiusura forzata delle posizioni e senza doppio accantonamento al riavvio. L'ultima verifica haCapitalV1off: non affermo che stia accantonando oggi.

Importare l'interoCapitalV1 porterebbe anche daily stop20%, sizing10%Hawk/25%Bull e altri controlli: contrario al vincolo di mantenere solo il salvadanaio. Serve separare la contabilità vault dalle policy aggiuntive e provarne migrazione/persistenza.

Interpretazione coerente con il vincolo di non reintegrare le perdite:
- contoPAPER1100 senza posizioni aperte →100nelvault,1000operativi;
- conto900 →nessun accantonamento/ricarica,900operativi;
- partenza900 e chiusura950, pur giornata positiva →950operativi, non1000inventati. Si accantona l'eccedenza oltre1000, non qualsiasi profitto rispetto al mattino.
- con posizioni aperte o profitto non realizzato non si può garantire cash1000esatti a mezzanotte senza chiudere trade: si usa la liquidità distribuibile e si completa l'accantonamento quando disponibile. Nessuna chiusura forzata implicita.

Queste precisazioni sono parte del piano da confermare, non nuove azioni eseguite.

## Compatibilità e dipendenze che impediscono un checkout cieco

Lo stato attuale delle posizioni contiene `last_bar_ms`, assente nel dataclassPosition5818. Quel motore costruisce `Position(**v)`: uno stato moderno con quel campo non è caricabile direttamente. Non si risolve cancellando campi dal file operativo o resettando portafogli: serve adattatore conservativo nel codice, testato su copie.

Un rollback integrale del motore ripristinerebbe inoltre difetti già documentati: possibile riesame delle barre con livelli nuovi, mancato controllo della barra contenente l'ingresso e DCA che può allargareSL. La prioritàLIQprimaSL è già nel vecchio motore; non è una correzione profitto da importare di nascosto. Nessuno di questi punti viene modificato in questa fase.

Non è corretto chiamare le correzioni motore “salva profitto” e mantenerle tutte senza dichiararlo. Sono una possibile quarta eccezione tecnica da decidere esplicitamente. Per preservare gli stati un adattatore di compatibilità è comunque requisito, non una strategia aggiuntiva.

## Sequenza proposta dopo la conferma del piano

1. Creare SOLO un ramo di lavoro isolato, senza spostare main/rule-pool/backup. Non resettare l'intero repository al5818: cambiare solo il perimetro classici, lasciando separati app, Brain e infrastruttura.
2. Ripristinare la baseline approvata per segnali, sizing e configurazioni; fare un diff a lista chiusa delle sole eccezioniLONG, chiusure/parziali e vault, più adattatori conservativi dichiarati. Guardianavanzato rimane fuori finché non approvato.
3. Decidere esplicitamente la sorte delle correzioni motore e del filtroregime: nessuna inclusione automatica. Conservare i workflow di backup/verifica e i contratti di stato senza usarli come canale per cambiare strategia.
4. Test offline mirati: LONG/SHORT simmetrici, neutralità, confini score, limiti storici, close/parziali con costi, vault sopra/sotto1000, mezzanotteUTC con posizioni aperte, crash/restart/idempotenza, caricamento stati moderni e continuità delle posizioni. Nessuna prova scrive sui dati bot.
5. Presentare commit/diff e risultato test per un secondo controllo. Nessun merge o push su main/rule-pool/stable senza il relativo OK.
6. Solo con OK separato al redeploy: riconfermare runtime/PAPER/env, ottenere backup dati con restore verificato e immagine precedente, piano per posizioni aperte/stati/vault, rilascio pinned e verifica. Il solo branch di codice non sostituisce questa procedura. Non resettare conti o memoria per simulare una run nuova.

## Stato finale di questa fase

Creati solo i due riferimenti di salvataggio del codice; letture del repository e piano. Aggiornamento documentale del ramo diario con[skip ci]. Nessun sorgente classico modificato, nessun rollout, ordine, reset, migrazione o scrittura ai dati operativi. Non è dimostrato che il codice storico riproduca i profitti nel mercato attuale.

**Conferme da ottenere:** baseline5818 oppure9fa; se “salva profitto” significa capacità base esistente o nuovoGuardian da completare; trattamento delle correzioni motore fuori dalle tre eccezioni; vault come sola eccedenza sopra1000 senza reintegro perdite. Fino alla conferma il lavoro si ferma al piano.
