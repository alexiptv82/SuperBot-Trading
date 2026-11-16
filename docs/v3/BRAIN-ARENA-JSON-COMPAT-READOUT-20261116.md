# SuperBot V3 — AI Arena: correzione JSON per provider (16 novembre 2026)

## Riscontro reale VPS (14:01 Europe/Rome)

Screenshot utente: script `deploy/scripts/arena-funded-schema-preflight-20261116.py`:
- Test offline: `SELFTEST=PASS_OFFLINE`; nessun ordine / nessuna modifica servizi.
- Qwen `qwen/qwen3.7-plus`: risposta HTTP riuscita, `finish_reason=stop`, input 109 token, output 98; errore di applicazione **`SCHEMA_OR_DECISION_MISMATCH`**. Poiché lo script scarta/maschera il contenuto, **non sappiamo ancora quale campo fosse sbagliato**.
- MiniMax `minimax/minimax-m3.1-flash`: `FAILED_HTTP_400`; il precedente test con `response_format=json_object`, `temperature=0`, senza `reasoning` e senza provider filter era riuscito, quindi HTTP400 **potrebbe essere** legato all'imposizione del nuovo `json_schema` o ad altri parametri. Il singolo codice HTTP non dimostra quale.
- `passed=0/2`, nessun bot Arena attivato.
- Limite residuo Qwen 1.9992688 USD, MiniMax 1.99995125 USD; **questi sono residui del limite chiave, NON saldo conto**. Utente ha precedentemente dichiarato ricarica 10 USD, senza verifica indipendente del saldo.

## Conferma documentale

OpenRouter: `https://openrouter.ai/minimax/minimax-m3.1-flash` e `https://github.com/OpenRouterTeam/docs/blob/main/guides/features/structured-outputs.mdx`. La compatibilità JSON-schema è **specifica dell'endpoint/provider**, non soltanto del modello. MiniMax supporta output JSON; in alcuni endpoint il formato JSON semplice non fornisce enforcement dello schema. Qwen supporta schema rigoroso ma il risultato deve comunque essere validato localmente; schema stretto non è garanzia universale di rispetto dei valori semantici.

## Correzione nel ramo, non installata

- `backend/v3/arena/openrouter_transport.py`: **Qwen** continua a richiedere `response_format=json_schema` e `provider.require_parameters=true`. **MiniMax** accetta soltanto `response_format=json_object`, `temperature=0`, senza parametri `reasoning` né override provider, coerente con la precedente chiamata riuscita. Il controllo dei dati ricevuti resta sempre dentro `ArenaL5Analyst` e `BrainEngine`; una risposta fuori schema non può diventare OPEN/APPROVED.
- `backend/v3/arena/l5_analyst.py`: adatta il formato **solo** al provider, lasciando invariato il contesto di mercato, le feature e la policy PAPER. Resta disabilitato di default e non collegato ai runner operativi.
- `test_l5_analyst.py` e `test_openrouter_transport.py`: regressioni offline, incluse negazioni di `json_schema` per MiniMax e di `json_object` per Qwen.
- `deploy/scripts/arena-provider-json-compat-20261116.py`: prova esplicita limitata ad **una richiesta per ciascuna AI**, dopo `--selftest` offline e conferma manuale `SI`; controlla chiavi/limite 2 USD, usa dati puramente sintetici. **Non stampa le risposte o i segreti**: per Qwen, in caso di mismatch, comunica soltanto `field_issues` con nomi noti e `_TYPE/_VALUE`, `missing_fields`, `extra_field_count` e token/finish_reason; non mostra testo generato. Per MiniMax usa la forma che già funzionava, ma richiede ora otto campi. Non esegue ordini e non modifica servizi.

## Come interpretare il prossimo test

- Se entrambe superano `PASS_NO_TRADE_EIGHT_FIELDS`: protocollo base NO_TRADE verificato per le forme JSON attuali, **non** qualità del trading e **non** capacità OPEN o modalità di ragionamento attivo.
- Se Qwen risponde con `field_issues`: affrontare solo i campi effettivamente divergenti. Non ignorare automaticamente semantica per OPEN, non forzare trade.
- Se MiniMax dà nuovamente HTTP 400: controllare il provider/route con test **mirato e separato**, non avviare retry automatici.
- Dopo prove provider, eseguire suite Python completa offline e collaudare OPEN sintetico prima di abilitare qualunque runner PAPER.

## Vincoli invariati

Falco SHORT ha il suo ramo archivio `archive/falco-short-before-ai-arena-20261116`; ancora da verificare backup dati runtime VPS **prima** della pausa. Toro non toccato. Brain DeepSeek corrente non cambiato; 14 giorni Arena non iniziati, Qwen e MiniMax non collegati ai servizi. Universo 23 crypto + XAU + XAG rimane ricerca disattivata. Nessun merge, deploy, Actions o spesa API generata da questo lavoro GitHub.
