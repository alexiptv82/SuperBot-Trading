# 2026-11-01 — DECISIONE UTENTE: Brain AI vincolato da regole + chiusure manuali insegnabili

**Origine**: dichiarazione diretta dell'utente nella chat SuperBot il 1 novembre 2026, successiva al lavoro LONG Shadow sulla PR Draft #26. Utente riferisce che il portafoglio Brain ha perso circa il 50% dall'avvio. Questo dato proviene dall'utente, **non** da un audit indipendente completo degli storici; NON attribuire la causa alla sola libertà AI senza analizzare operazioni/rischio/regimi.

## Decisioni dell'utente (vincolanti per la prossima proposta)

1. Brain AI attuale, completamente libero, **bocciato come politica per futura messa in funzione**. NON proporre di rilasciarlo senza rivederne il controllo dei rischi e le strategie. Non cambiare/fermare automaticamente un servizio oggi in esecuzione: stato runtime non verificato e manca mandato di operazione.
2. **Prima completare il LONG** condiviso da classici Falco/Toro e Brain; mantenere LONG Shadow in preparazione e nessun merge/deploy senza OK esplicito.
3. Successivamente riprogettare Brain con **portafoglio unico**, operatività sia LONG sia SHORT sotto **regole simili ai classici**, AI con utilità mirata nelle lacune del sistema meccanico, anziché decidere liberamente size, leve, ingressi e uscite senza limiti. NON assumere che imitare i classici dia automaticamente profitti: il confronto va misurato.
4. Introdurre/rafforzare **chiusure manuali** di posizioni per Brain e Falco/Toro, così l'utente può prendere profitto quando lo reputa sufficiente e liberare slot anche se il bot non chiude.
5. Le chiusure manuali devono alimentare un processo di **apprendimento dalle preferenze** dell'utente: conferma intenzione di chiudere, motivo, percentuale/profitto e contesto; i bot devono migliorare il timing delle uscite in modo misurabile, senza copiare ciecamente ogni chiusura o alterare automaticamente le soglie di rischio.

## Ricognizione codice esistente (verificato su GitHub)

- Classici su `main`: API `backend/desk_api.py` POST autenticato `/close-position`, `backend/desk_view.py` valida comando, frontend `Dashboard.js` e `LiveParts.js` contengono controllo `Chiudi ora` a doppia conferma. N.B. la presenza nel codice **non dimostra** che una determinata installazione/server sia aggiornata.
- Ramo `work/classics-teaching-completion-20261031`: `backend/desk/manual_teaching_service.py`, `backend/desk/manual_teaching_bridge.py`, `backend/director/manual_teaching.py` per registrare SOLO chiusure PAPER confermate/persistite, deduplicare, richiedere conferma utente, lesson append-only. Esiste già il ponte; non ricrearlo senza audit e senza aggiornare gli owner.
- Ramo `work/brain-completion-20261031`: `backend/director/brain_free/execution.py` contiene azioni `close` e `partial_close`, ma il servizio Brain autonomo con teaching completo UI→evento→conferma→memoria deve essere verificato end-to-end prima di dichiararlo presente o rilasciato.
- Ramo `work/brain-completion-app-20261031`: UI e API conferme operatore (`backend/brain_operator_api.py`, componenti React) preparate e distinte dall'esecuzione trading.
- Il diario precedente documenta conti PAPER, backups, queue e test su altri rami: **non** si presume merge o deploy implicito.

## Proposta tecnica NON ancora autorizzata/parametrizzata

A. *Rischio deterministico esterno al modello*: modalità PAPER, size/limiti di margine e leva, esposizione complessiva e per direzione, drawdown, numero posizioni, SL protettivi e limiti nuovi ingressi. Nessuna AI può allargare stop, forzare slot o aggirare rischio. In stress, nuove aperture sospese, ma gestione protettiva delle aperte resta attiva.
B. *Candidati di strategia*: SHORT classico come baseline da confrontare e LONG nuovo solo dopo validazione; l'AI può selezionare, filtrare e gestire posizioni entro vincoli, con motivazione, tracciabilità e NO_TRADE. Brain resta un solo wallet, non clona profitti dei classici.
C. *Chiusura manuale*: distinguere `Chiudi ora` (azione utente effettiva, con ack del wallet), `Chiudi parziale` e `Aggiorna SL` (funzioni da auditare/definire separatamente). Evitare confusione tra stop protettivo SL e presa profitto manuale. Eventi attestati con id, portfolio, simbolo, timestamp, ROI netto sul margine, PnL, leva, fee, MFE/MAE se disponibili; motivo utente `profitto_sufficiente`, `trend_cambiato`, `rischio_eccessivo`, `altro`. Registrare anche quando la chiusura è fatta per motivo diverso dal profitto.
D. *Apprendimento con controllo*: l'evento manuale NON modifica regole subito. Richiesta di conferma del motivo; storico append-only; proposta AI valutata shadow/counterfactual e fuori campione; solo modifiche promettenti e approvate divengono regole dopo test. Confronto con chiusure alternative a costi/spread/slippage e contesto; niente curve fitting su esempi isolati.
E. *Dati importanti ancora mancanti*: non è stata ancora scelta una soglia numerica di ROI o PnL. Distinguere sempre profitto netto sul margine vs movimento prezzo vs profitto totale e free-slot policy; non fissare soglie fittizie. Niente nuove leve aggressive come default solo perché richieste in passato; prima audit perdita ~50%.

## Sequenza e gate

0. Conservare PR LONG Shadow #26 in DRAFT, nessun merge/deploy/PAPER da questa indicazione.
1. Chiudere la parte LONG read-only, collegamento feed e wallet consultivi con test senza ordini, verifica CI e compatibilità.
2. Analisi post-mortem della perdita Brain: trade storico, long vs short, fee, effetto leva/size, drawdown, SL, tempi di uscita, opportunità di prendere profitto, campioni sufficienti; non usare solo il PnL aggregato.
3. Disegnare Brain rules-governed con parametri concreti, un wallet unico, revisione dei limiti e differenza AI rispetto ai classici.
4. Riutilizzare e completare il teaching manuale dei classici ed estenderlo al Brain, con guardie su doppie conferme, timestamp, eventi, deduplica, auth e nessun cambio immediato di strategia.
5. Shadow/replay, confronti A/B e quindi PAPER solo con nuova autorizzazione; produzione LIVE non autorizzata.

**Stato**: questa voce registra una decisione di direzione, NON è permesso di modificare code Brain, threshold numerici, prompt/strategia classici o servizi operativi. Brain_FREE_AS_IS_REJECTED_FOR_RELEASE=YES; NEW_BRAIN_RULES_SPEC_PENDING=YES; MANUAL_TEACHING_END_TO_END_PENDING_AUDIT=YES; LONG_SHADOW_PR26_DRAFT; NO_DEPLOY/NO_MERGE.