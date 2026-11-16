# SuperBot AI Arena — primo bootstrap persistente (16 novembre 2026)

## Conferma VPS effettiva

Screenshot dell'utente ore 17:47: `ARENA_DELTA SELFTEST=PASS_OFFLINE` su 25 mercati sintetici, `simulated_delta_GETs=100`, verifiche gap/duplicato/OHLC/scadenza; `BTCUSDT_1m/15m/1h/4h_CLOSED=VERIFIED`, quattro richieste pubbliche reali, e `RESULT=BTC_DELTA_SOURCE_VERIFIED_NO_DEPLOY`. Zero ordini, chiamate AI a pagamento, servizi cambiati.

**Attenzione:** la verifica storica dei 25 mercati (575 pagine) è stata completa ma VOLATILE: terminato lo script non è rimasta una cache sfruttabile, solo un digest SHA. Nessuno può ricostruire i dati dal digest.

## Nuovo file (branch di ricerca isolato)

`deploy/scripts/arena-first-private-cache-20261116.py` — tre comandi distinti:

1. `--selftest`: nessuna rete; costruisce uno snapshot sintetico a 25 simboli, prova una scrittura atomica e la lettura con verifica integrale del digest, confronta i tre provider, prova blocco di sovrascrittura e file corrotti. Usa unicamente una directory temporanea con prefisso `/tmp/superbot-arena-research-` e la elimina alla fine.
2. `--preflight`: diagnostica in sola lettura la cartella `/var/lib/superbot-arena-research`, proprietà di scrittura/permessi e spazio disponibile. Se ancora non esiste, segnala `directory=NOT_CREATED`, senza crearla. Se c'è già una cache non deve sovrascriverla.
3. `--bootstrap --confirm-public-download=YES`: richiesta esplicita separata; crea `/var/lib/superbot-arena-research` a permessi 0700 solo se assente, acquisisce lock non bloccante, rifiuta cache esistente, recupera il catalogo dinamico (3 GET pubblici) e 575 pagine storiche Bitget max, costruisce una nuova immagine temporale completa e coerente, convalidandone l'età (massimo 10 minuti). Salva il file privato `arena-market-research-cache.json` attraverso il modulo `save_research_cache` (064? **0600**, fsync e os.replace) e lo rilegge verificando identità completa di contenuto/hash/simboli. Se fallisce, non registra il successo. Lo snapshot rimane soltanto per ricerca e non può autorizzare scambi.

La modalità `--bootstrap` non parte con `--selftest` o `--preflight`. La ricostruzione da 575 pagine è necessaria **una volta** perché i dati precedenti erano solo RAM. Non fare nuovi 575 GET a ogni ciclo. L'adattatore delta deve leggere questa cache e scriverne una nuova solo con le candele mancanti.

## Test e approvazioni

Il nuovo file è stato salvato su ramo separato; la sua esecuzione `--selftest` e `--preflight` su VPS è ancora **da eseguire**. Nessun merge, deploy o API AI eseguite dallo sviluppo su GitHub.

Dopo PASS della preflight si potrà offrire al proprietario il comando separato per il bootstrap effettivo, tenendo registrato il nuovo digest. Controllo categorie CoinGecko/Bitget ancora provvisorio, quindi nessun permesso a tradare: `PROVISIONAL_NOT_TRADE_APPROVED`.

Falco SHORT non va toccato e deve conservare il ramo/backup operativo prima di un futuro cambio. Toro e Brain DeepSeek attuale non cambiano; le tre AI non sono ancora in gara PAPER e nessun portafoglio da 2000 USDT è stato attivato.
