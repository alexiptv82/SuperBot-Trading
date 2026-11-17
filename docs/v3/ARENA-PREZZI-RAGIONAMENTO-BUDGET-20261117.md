# AI Arena — prezzi, ragionamento e budget (evidenze del 17/11/2026)

Nessuna inferenza pagata. Fonti pubbliche lette senza chiave:
`https://openrouter.ai/api/v1/models` (estratto in `docs/v3/arena_model_pricing_20261117.json`) e documentazione
DeepSeek (`deepseek-flash` oggi servito da DeepSeek-V4.1-Flash-1017).
**Prezzi, tetti e cadenza nelle config NON sono stati modificati**: decisione dell'utente.

## 1. Listino reale e config

| Modello | Listino (USD / 1M token, input / output) | In config | Ragionamento: parametri supportati |
|---|---|---|---|
| DeepSeek `deepseek-flash` (API diretta) | 0,30 / 1,20 (stesso modello su OpenRouter `deepseek-v4.1-flash`) | 0,30 / 1,20 ✅ | nativo `thinking` + `reasoning_effort`; config: `enabled`, `high` |
| Qwen `qwen/qwen3.7-plus` | 0,32 / 1,28 (oltre 256k token di prompt: 0,96 / 3,84) | 2,00 / 8,00 (≈ 6× sopra) | `reasoning`, `include_reasoning`; **non** `reasoning_effort` |
| MiniMax `minimax/minimax-m3.1-flash` | **varia per orario**: 0,15 / 0,60 (01–15 UTC), 0,075 / 0,30 (15–01 UTC) | 2,00 / 8,00 (≈ 13× sopra) | `reasoning`, `reasoning_effort`, `include_reasoning` |

Con prezzi in config più alti del listino il tetto giornaliero scatta **prima** del dovuto. È sicuro sul piano della
spesa, ma Qwen e MiniMax verrebbero fermati prima di DeepSeek: il confronto sarebbe falsato.

## 2. Costo giornaliero per modello, sul listino reale

Universo 27 simboli × 24 cicli = **648 valutazioni/giorno** se nessun simbolo ha posizioni aperte (caso massimo). Prompt
2.500 token. Le colonne sono i token di uscita per chiamata, ragionamento compreso.

| Modello | 100 | 1.000 | 3.000 | 6.000 (max_tokens) |
|---|---|---|---|---|
| DeepSeek | 0,56 | 1,26 | 2,82 | 5,15 |
| Qwen | 0,60 | 1,35 | 3,01 | 5,50 |
| MiniMax (fascia cara) | 0,28 | 0,63 | 1,41 | 2,58 |
| MiniMax (fascia economica) | 0,14 | 0,32 | 0,70 | 1,29 |

Tetto attuale: **0,75 USD/giorno** per modello. Con il nuovo universo e ragionamento attivo il tetto viene superato
già con circa 1.000 token di uscita: il runner va in `BudgetHalt` e registra NO_TRADE per il resto del giorno UTC.

## 3. Ragionamento: cosa succede davvero

* DeepSeek riceve `{"thinking": {"type": "enabled"}, "reasoning_effort": "high"}` (formato nativo DeepSeek).
* Qwen e MiniMax hanno `thinking: "omit"`: **non viene inviato alcun parametro**, quindi vale il comportamento
  predefinito del modello su OpenRouter. Non si sa se ragionano senza una chiamata reale.
* Nuova misura (`backend/v3/arena/inference_trace.py`): ogni chiamata registra in `inference_trace.jsonl` i parametri
  di ragionamento inviati, i token (compresi `reasoning_tokens` se il fornitore li riporta), la latenza, il
  `finish_reason` e il costo riportato dal fornitore. Non registra mai prompt né risposte. Dopo il primo giorno l'asimmetria
  sarà misurata, non supposta.

## 4. Contabilità, concorrenza e chiave

* Un runner per AI con chiamate in sequenza. Il cancello di spesa viene controllato prima di ogni chiamata, quindi lo
  sforamento massimo è di **una** chiamata: circa 0,01 USD con 6.000 token di uscita.
* Le chiamate fallite sono addebitate a stima (`estimate_failed_call`). Il trasporto non fa tentativi ripetuti.
* `openrouter_transport` rifiuta chiavi con limite **> 2 USD** (`KEY_LIMIT`). A circa 1,3 USD/giorno la chiave si
  esaurisce in 1–2 giorni: per 14 giorni il limite va alzato (modifica di codice) oppure la chiave va ricaricata.
* MiniMax ha prezzo per fascia oraria, mentre il metering usa un prezzo unico: conviene la fascia cara (stima prudente).

## 5. Proposta di politica (da decidere)

**A — stesse opportunità (consigliata).** Stesso universo e stessa cadenza per tutti. Prezzi in config = listino
(MiniMax alla fascia cara). Tetto uguale per tutti e sopra il caso a 3.000 token, per esempio **3,50 USD/giorno**:
massimo teorico circa 49 USD per AI in 14 giorni, realistico circa 15–20 USD. Ogni `BudgetHalt` resta registrato e le
ore in halt vanno escluse dal confronto per tutte e tre le AI.

**B — stesso budget in dollari.** Tetto uguale e basso (per esempio 1 USD/giorno): chi costa meno decide più a lungo.
Il confronto misura costo-efficacia, non qualità della decisione.

**Ragionamento (ChatGPT, punto 2):** lasciare le modalità native, cioè DeepSeek `enabled/high` e Qwen/MiniMax al
predefinito OpenRouter, misurare con la traccia e documentare l'asimmetria. Se dopo un giorno risulta che Qwen o
MiniMax non ragionano, decidere se inviare `reasoning: {"enabled": true}`. Oggi la config non sa inviarlo: servirebbe
una piccola estensione, non fatta senza decisione.

**Cadenza 60 minuti:** le uscite non dipendono dal ciclo delle decisioni (servizio uscite separato, controllo ogni
minuto). Accorciare il ciclo moltiplica i costi senza prove di beneficio: non va cambiata senza dati.
