# Memoria classici — 31 ottobre 2026

Ramo candidato, PAPER, DESK_MANUAL_TEACHING=on abilita il nuovo ciclo;
default off. Scorer, engine, rischio e SYSTEM AI invariati.

Le nuove chiusure manuali accodano una ricevuta nello stato del conto prima del
salvataggio. File e directory sono sincronizzati su disco. Il recovery legge
soltanto ricevute dal file già salvato; non attesta una chiusura dallo storico
scritto prima di un salvataggio fallito. Le vecchie righe senza ricevuta non
vengono promosse automaticamente a esempi verificati.

Ogni minuto, dopo il ciclo di mercato, il proprietario del conto registra gli
esempi idempotenti, consuma al massimo cinque conferme dalla coda separata e
pubblica manual_operator_reviews.json. Non chiude trade durante il recovery.
La coda predefinita è DATA_DIR/manual.confirmations.sqlite3; override esplicito
DESK_TEACHING_INBOX_PATH. Il nome deve terminare .confirmations.sqlite3.
L'app deve montare il solo file di pubblicazione in lettura e la directory della
coda in scrittura: non deve poter modificare il wallet o i file della memoria.

L'app usa DESK_HAWK_OPERATOR_REVIEWS_PATH/INBOX_PATH e gli analoghi BULL,
DESK_OPERATOR_ALLOWED_ORIGIN esatto. Le conferme includono account_id con numero
run: un comando per un'altra run è rifiutato. TTL coda due minuti, conferma
esempio due ore. Esiti incerti non sono rispediti automaticamente.

Gli esempi positivi confermati della run corrente sono consultabili nella
successiva analisi opzionale AI; rules_only non avvia chiamate AI né modifica
regole. Le note storiche restano append-only. Non è retraining automatico.

La patch test legacy già verificata su e859b4f è inclusa senza cambiare token,
timeout o budget: originale 92/95, patch95/95. Per nuovi dati insegnamento non
validi, la chiusura finanziaria continua e il campione non è accettato.

Nessun deploy/avvio/reset o messaggio Telegram reale in questo collaudo.
