# Completamento Brain — 31 ottobre 2026

Base servizio 288c838; app base 2e82ac6. Preparazione PAPER, azioni default off.

## Riduzioni parziali riconciliate

Il ramo precedente Work 750f06c proponeva partial_close con frazione. Il nuovo
contratto conserva il controllo a due provider: SUGGEST_REDUCE richiede stessa
azione e stessa frazione. Lotto arrotondato per difetto al qty_step, minimi sul
lotto chiuso e sul residuo; sotto minimo viene rifiutato, mai convertito in una
chiusura totale. Contabilità, audit e ricevuta nella stessa transazione. Peak
netto assoluto scalato per quantità residua, stop/target/ID conservati. Il ramo
precedente resta conservato; non viene unito ciecamente né dichiarato equivalente.

## Errori osservabili

last_ai_attempt registra separatamente l'ultimo tentativo dall'ultima revisione
eseguita. Campi: ts_ms, purpose entry/review, status, provider deepseek/claude,
failure_code da vocabolario chiuso. Nessun corpo risposta, prompt o eccezione
grezza. La dashboard mostra provider e motivo senza confondere un errore nuovo
con il successo precedente. Non è un monitor del saldo esatto o una prova di
salute H24. Gli errori non attivano fallback a regole.

Se poll solleva, il supervisore riceve feed vuoto e conserva le guardie sui dati
mancanti; non riutilizza quote vecchie come fresche. Un prezzo assente impedisce
una decisione; il software non può garantire esecuzione stop senza dati.
Il log del loop stampa il tipo d'eccezione, non traceback o testo arbitrario.

## Ancora aperto per il completamento complessivo

Notifiche Telegram dei failure e relativa coda, teaching classici completo,
ricerca autonoma con valutazione fuori campione, analisi multitimeframe estesa,
mandato e budget provider definitivi, packaging/staging e backup/restore del
rilascio finale. Il nuovo motore LONG è affidato dall'utente a un'altra AI, su
componente separato e solo consultivo per Brain fino a valutazione.

Nessun deploy, avvio nuovo conto o reset autorizzato da questo documento.
