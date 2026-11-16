# AI Arena — verifiche credenziali e catalogo (16 novembre 2026)

Fonte: screenshot Termius dell'utente, circa 11:13 Europe/Rome. Nessuna chiave segreta riportata.

## Verificato sulla VPS

- Chiavi separate Qwen e MiniMax con `GET /api/v1/key`, valide, limite 2 USD e limite residuo 2 USD ciascuna, `reset=None`, scadenza 16 dicembre 2026. Questo **non e' una conferma del credito prepagato totale**.
- Salvataggio root-only in `/etc/superbot-brain-ai-arena/openrouter-keys.json`, file mode 0600 e directory 0700.
- Catalogo OpenRouter `GET /api/v1/models`: `qwen/qwen3.7-plus` **FOUND**, `minimax/minimax-m3.1-flash` **FOUND**; JSON strutturato dichiarato disponibile per entrambi.
- Tariffe confermate dal catalogo, in USD per milione di token input/output: Qwen 0,3200/1,2800; MiniMax 0,1500/0,6000. Sono tariffe per questo snapshot e possono cambiare.
- `ARENA_CATALOG RESULT=CATALOG_VERIFIED_NOT_ACTIVATED`, `model_inference_calls=0`, `services_modified=0`, `trading_actions=0`.

## Prossima fase: un solo test piccolo per modello

Script `deploy/scripts/brain-arena-openrouter-one-shot-20261116.py`, **non eseguito** sulla VPS al momento di questo rapporto. Richiede `--probe` e conferma manuale `SI` prima di qualsiasi chiamata a pagamento. Prima di ciascuna chiamata fa `GET /api/v1/key` e rifiuta una chiave il cui limite eccede 2 USD o ha meno di 0,02 USD disponibili; esegue poi **un solo POST `/api/v1/chat/completions` senza retry** per provider, con massimo 512 token di risposta e prompt sintetico privo di dati di trading reali. Esito corretto: `{\"action\":\"NO_TRADE\",\"reason_code\":\"NO_MARKET_DATA\"}`. Nessun ordine, nessun dato privato nel prompt e nessuna modifica al trading.

Questo e' un controllo di autenticazione/JSON/latency & token API, **non** un test di superiorita' nell'analisi finanziaria. Il codice e i test sono stati rivisti staticamente; la suite Python locale non ha potuto essere eseguita nell'ambiente dell'assistente per indisponibilita' di rete verso raw GitHub; nessun GitHub Actions avviato.

## Vincoli

Non attivare runner Qwen/MiniMax, non nascondere o fermare Falco/Toro, non azzerare Brain, non aprire posizioni, non fare merge/deploy senza consenso specifico. I 14 giorni inizieranno solo quando tre journal PAPER separati siano verificati, con portafogli da 2.000 USDT ciascuno e T0 comune concordato.
