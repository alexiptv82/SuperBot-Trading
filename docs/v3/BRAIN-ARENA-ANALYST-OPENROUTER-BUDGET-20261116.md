# AI Arena — Qwen/MiniMax L5 offline e budget OpenRouter (16/11/2026)

**Ramo:** `work/brain-arena-dual-analyst-offline-20261116`  
**Stato:** codice di ricerca su GitHub; **nessun deploy, nessun nuovo modello attivo, nessun ordine o chiamata API in questa fase**. Falco/Toro invariati; Falcon SHORT ha archivio dedicato nel ramo `archive/falco-short-before-ai-arena-20261116`.

## Domanda dell'utente: serve ricaricare le due API?

Le API **non contengono** credito. L'utente ha creato due chiavi OpenRouter con tetto **2 USD ciascuna**, che non significa 2 USD di saldo disponibile. Il credito dell'**account** OpenRouter e' condiviso tra le due chiavi. Qwen e MiniMax hanno gia' risposto a una chiamata di prova a pagamento, per cui e' ragionevole che al momento delle prove ci fosse credito disponibile (eventualmente promozionale); non e' stata verificata la cifra residua effettiva.

Fonte ufficiale OpenRouter: dashboard Credits/Activity e documentazione `https://openrouter.ai/support/`, `https://openrouter.ai/docs/api/api-reference/credits/get-credits`, `https://openrouter.ai/pricing` e `https://openrouter.ai/terms`. L'endpoint `GET /api/v1/credits` per il saldo totale richiede una **management key**: non chiedere all'utente di creare o inviare una chiave di gestione; usare il sito OpenRouter per la verifica. La ricarica minima indicata attualmente da OpenRouter e' **5 USD** piu' eventuali commissioni; **nessun acquisto ora** e disabilitare eventuale auto top-up.

Le chiavi da 2 USD non devono essere alzate ne' disabilitate finche' il test non e' completamente pianificato.

## Cosa e' stato implementato sul ramo di ricerca

1. `backend/v3/brain_market/deepseek_l5.py`: aggiunti solo piccoli hook sovrascrivibili nel precedente L5, il cui **default continua a essere DeepSeek**. Le stringhe, il tipo di chiamata, le analisi di mercato, il contesto e la provenienza della vecchia run rimangono identici senza subclass.
2. `backend/v3/arena/l5_analyst.py`: nuovo `ArenaL5Analyst`, utilizzabile **solo** per provider Qwen/MiniMax con ID modello esatto e run ID `brain-<provider>-paperYYYYMMDD`. Disattivato di default. Condivide gli indicatori di candele chiuse, lo scoreboard e il menu strategie di L5; nessun accesso alla rete/ordini intrinseco. L'output e' sottoposto a validazione JSON, classificato NO_TRADE/OPEN, associato all'AI corretta, altrimenti rifiutato. Formato richiede una variante strict schema per entrambi e almeno 1024 token di output, massimo 8192; predefinito 2048.
3. `backend/v3/arena/openrouter_transport.py`: schema completo fissato e condiviso con l'analista; `response_format` e' consentito **solo** nella variante strict schema della Arena (niente payload arbitrari, tools, parametri provider non verificati o routing dinamico). Richiede PAPER, opt-in, verifica per-chiave e gate budget software, senza fallback o retry.
4. `backend/v3/arena/cost_forecast.py`: stima offline trasparente e modificabile, usa i prezzi per milione di token rilevati dal catalogo OpenRouter sulla VPS il 16/11/2026. **Non conosce e non pretende di conoscere il credito reale dell'account** e non puo' pagare o fare richieste.
5. `test_l5_analyst.py`, `test_openrouter_transport.py`, `test_cost_forecast.py`: simulazioni senza chiamate API; test creati per provider errato, NO_TRADE, SHORT, schema, budget e regressione DeepSeek. **Non ancora eseguiti su VPS/CI**, da collaudare in checkout isolata prima del rilascio.

### Equivalenza del confronto

Un identico `MarketContext`, stesso menu e stessi indicatori sono trasmessi alle AI. Qwen e MiniMax usano un formato JSON strict con otto campi obbligatori (utilizzato per compatibilita' di trasporto), trasformato nelle classi Brain esistenti prima del rischio. **Non** e' un confronto scientifico concluso: saranno necessari test per confermare il supporto del formato con entrambe le API a `reasoning` normale, verificare le metriche token e comparare eventuali differenze dovute ai formati. Il test API Qwen precedente ha dimostrato JSON valido **soltanto con reasoning disattivato** e su NO_TRADE sintetico.

### Proiezione 14 giorni con le due chiavi attuali

*Scenari indicativi, non costi reali e senza includere DeepSeek, reasoning extra, retry, commissioni e variazioni di prezzo.*

| Parametro | Scenario A: 8 asset ogni ora | Scenario B: 8 asset 4 volte/giorno |
|---|---:|---:|
| Chiamate per AI, 14 giorni | 2688 | 448 |
| Token input/output per chiamata | 3000 / 1000 | 3000 / 2000 |
| Qwen, stima 14 giorni | **6,02112 USD** | **1,57696 USD** |
| MiniMax, stima 14 giorni | **2,82240 USD** | **0,73920 USD** |
| Budget chiave 2 USD (riserva 0,20 USD) | **NO** per entrambe | **SÌ, teoricamente**, se il saldo account basta |

La seconda frequenza riduce il consumo ma *non* prova la qualità dello scalp intraday: prima dell'avvio si devono approvare un calendario comune, il numero di simboli, e il budget reale sufficiente. Una soluzione alternativa e' campionare dinamicamente i simboli ma **sempre in modo identico per tutte e tre le AI**, registrando la selezione, in modo da non falsare il confronto. Non confondere cap per chiave e costo reale.

### Passaggi mancanti prima di avviare nuovi runner

- Eseguire test Python e regression dei sorgenti appena modificati in checkout isolata, poi test reale API con crediti esistenti **solo previa autorizzazione** e budget controllato.
- Completare collegamento fra nuovi analisti e controller runner/exit *uno per provider*, con budget separati, mandato di rischio, protezione equity 450 e nessuna chiamata live exchange.
- Validare `schema` su Qwen e MiniMax con input mercato realistico, NO_TRADE/OPEN e ragionamento esteso, e assicurare che JSON troncato/non valido si trasformi in **nessuna apertura**.
- Verificare e salvare backup Falco presente sulla VPS prima di decidere eventualmente pausa nuove aperture.
- Rendere la dashboard `/api/v3/arena` disponibile solo dopo l'installazione di journal/servizi veri e autorizzazione; gli attuali moduli leggono dati isolati senza inventare il saldo.
- Concordare T0 comune e capitale 2000 USDT nuovi per tre wallet. Nessuna run PAPER Arena iniziata adesso.

## Avvertenza

Un'AI costosa o piu' potente non garantisce profitti. Il confronto deve misurare il valore netto rispetto a baseline opportunita'/caso appaiata; le tre AI potrebbero condividere gli stessi errori. La modalita' di consulenza fra AI resta separata, shadow-only, e disattivata.
