# Router LLM gratuito per il Brain

Il Brain continua a usare DeepSeek finché non si imposta `BRAIN_LLM_PROVIDER=free_router`. Il contratto della decisione non cambia: `NO_TRADE` oppure `OPEN` con lato, prezzi, leva, confidenza e strategia. Non si toccano formule, leva, size, capitale o soglie di rischio.

Il router previsto è [FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi): un solo endpoint OpenAI-compatibile, in ascolto solo su questa macchina, con provider gratuiti (Gemini AI Studio, Groq, NVIDIA NIM, OpenRouter con modelli `:free`, Mistral free, Cloudflare, Cerebras e simili) e fallback automatico fra di loro. Non vanno inserite chiavi di provider a pagamento.

## Installazione sulla VPS, quando sarà autorizzata

Questi comandi non vanno lanciati da questo incarico. Sono la procedura per un secondo momento, con consenso esplicito.

```bash
git clone https://github.com/tashfeenahmed/freellmapi.git
cd freellmapi
npm install
```

Nel file di configurazione del router si mettono solo chiavi dei piani gratuiti. La chiave unica che il Brain userà è quella locale del router, non le chiavi dei provider.

Avvio in ascolto solo sul loopback:

```bash
HOST=127.0.0.1 PORT=3001 npm start
```

Esempio systemd, utente non root, stessa cartella:

```ini
[Service]
WorkingDirectory=/opt/freellmapi
Environment=HOST=127.0.0.1
Environment=PORT=3001
ExecStart=/usr/bin/npm start
Restart=on-failure
```

In alternativa: `pm2 start npm --name freellmapi -- start` dopo aver esportato `HOST=127.0.0.1` e `PORT=3001`. Non aprire la porta sul firewall pubblico.

## Variabili

| Variabile | Significato |
|---|---|
| `BRAIN_LLM_PROVIDER` | `deepseek` (default) oppure `free_router` |
| `DEEPSEEK_FALLBACK` | Con `free_router`, se manca vale `true`. `false` spegne il fallback |
| `LLM_ROUTER_URL` | Default `http://127.0.0.1:3001/v1` |
| `LLM_ROUTER_KEY` | Chiave unica del router. Non va nei log |
| `LLM_ROUTER_MODEL` | Default `auto:smart` |
| `LLM_ROUTER_TIMEOUT_S` | Default 30, fra 1 e 120 |
| `LLM_ROUTER_ALLOW_REMOTE` | Default spento. Se acceso, accetta anche host pubblici |

Un host pubblico è rifiutato. Sono ammessi `localhost`, `127.0.0.1`, `::1` e indirizzi privati o link-local scritti in chiaro. Il nome DNS di un'altra macchina no, salvo l'override.

## Fallback a pagamento

Si chiama DeepSeek una sola volta per simbolo e per ciclo, e solo se il router fallisce: timeout, connessione, 429, 5xx, chiave assente, URL rifiutato, JSON illeggibile o schema non valido.

Un `NO_TRADE` valido del router è una decisione e non scatena il fallback. Non ci sono altri tentativi. Se anche DeepSeek fallisce, o se il suo tetto di spesa giornaliero è già raggiunto, la decisione è `NO_TRADE`. Il tetto di DeepSeek non è stato modificato. Il fallback acceso non apre due volte: il ciclo riceve una sola decisione.

Nel journal il campo `llm_route` dice `source` (`free_router` o `deepseek_fallback`), `router_failure` quando c'è, e `deepseek_cost_units` (unità già addebitate sul registro DeepSeek). Non ci finiscono la chiave né l'URL.

## Verifica

Con il router acceso sul loopback e `BRAIN_LLM_PROVIDER=free_router`:

```bash
curl -s http://127.0.0.1:3001/v1/models -H "Authorization: Bearer $LLM_ROUTER_KEY"
```

Poi un ciclo PAPER del Brain. Nel journal di una decisione si legge `llm_route`. Senza la variabile, il processo resta su DeepSeek.

I test di questo ramo usano un server HTTP finto e non chiamano provider veri.

## Rollback

Rimettere `BRAIN_LLM_PROVIDER=deepseek` oppure togliere la variabile, e riavviare il processo solo quando l'utente lo autorizza. Il codice di DeepSeek non è stato rimosso.

## Limiti dei piani gratuiti

Nessun SLA. Le quote si esauriscono durante la giornata e la qualità può peggiorare. Alcuni provider usano i dati per addestrare i modelli. Il router non va esposto su Internet.

## Altre chiamate AI, non instradate qui

Restano com'erano, per non cambiare Falco, Toro o i revisori:

- `backend/desk/brain.py`, `call_claude`: decisioni e lezioni dei classici, API Anthropic.
- `backend/desk/market_context.py`: notizie CryptoPanic, non è un LLM; il sentiment è un'etichetta del feed.
- `backend/v3/transport.py` e `backend/v3/brain_f3/providers.py`: trasporti DeepSeek e Claude del motore F3.
- `backend/v3/brain_view/deepseek_l4.py`: analista L4 isolato.

Un passaggio successivo può far usare anche a questi lo stesso client, dietro lo stesso interruttore.
