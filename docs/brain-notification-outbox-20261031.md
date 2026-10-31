# Brain PAPER: notifiche degli errori AI

Le notifiche sono disattivate per impostazione predefinita. Per abilitarle servono
`BRAIN_NOTIFY_TELEGRAM=on`, `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` espliciti.
La validazione della configurazione non contatta Telegram. Questo sviluppo non
autorizza invii reali, deploy o avvio dei bot.

Dopo il tick protettivo e il recovery teaching, il proprietario del conto
accoda l'errore AI corrente. Se la telemetria finanziaria non è stata salvata,
usa l'esito corrente del supervisor; altrimenti può recuperare l'ultimo tentativo
persistito. Una coda indisponibile non cambia il risultato del tick protettivo.

La coda `brain.notifications.sqlite3` è separata dal conto. Ha un solo owner,
protezione da percorsi simbolici, massimo 100 messaggi pendenti e deduplica
persistente per provider, causa e finestra di 30 minuti del tentativo AI.
L'invio HTTP avviene in un worker dedicato; nessun worker accede al wallet.
Il messaggio include data UTC, provider, causa da vocabolario chiuso e NO_TRADE.
Il saldo residuo è dichiarato non disponibile: non viene inventato.
Corpi HTTP, prompt, chiavi ed eccezioni arbitrarie non entrano nei messaggi.

Un riscontro Telegram valido con message_id produce `delivered`. Solo il rifiuto
esplicito 429 consente un nuovo tentativo, con attesa crescente e massimo tre
invii totali. Timeout, risposte ambigue, errori di rete e 5xx producono `uncertain`:
potrebbe essere avvenuta la consegna, quindi non si ritenta automaticamente.
400/401/403/404 producono `rejected`. Dopo un riavvio, gli invii trovati
`inflight` diventano `uncertain`; gli eventi ancora `pending` restano recuperabili.
La deduplica evita ripetizioni nello stesso intervallo, non promette consegna
esattamente una volta. Gli stati incerti richiedono riconciliazione manuale.

Il backup finanziario esistente copre il wallet. La coda e il suo file owner
appartengono al packaging operativo ancora da completare: un futuro ripristino
deve conservare il registro delle consegne per evitare reinvii da un vecchio stato.
Non copiare il file SQLite mentre è attivo; usare SQLite backup o arresto verificato.

Collaudo offline: trasporto simulato, errore saldo provider, deduplica e riavvio,
limite coda, invio lento, retry 429, esiti incerti, owner unico, precedenza alle
protezioni e conto PAPER temporaneo. Nessun Telegram o provider AI reale usato.
