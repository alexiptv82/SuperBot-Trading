# Laboratorio costi LLM — rapporto tecnico

Data: 19 novembre 2026. Il laboratorio è SHADOW e offline. Non è collegato al Brain, non apre posizioni e non ha chiamato provider veri.

## Baseline

`work/brain-exit-observability-20261113` @ `33a0de73a9903ba1ff76326aa4cb7c688a1e4aca`.

È lo stesso SHA su cui poggiano le bozze del router (#120), del freno prezzi (#121) e del registro v2 (#122), ed è l'ultimo Brain di cui risulta il riscontro di esecuzione. La PR #118 (dataset) parte da `main` e non è il runner. Non ho unito quelle bozze: il fallback DeepSeek della #120 non è approvato, e questo laboratorio non deve avere un fallback operativo.

Il nome richiesto `grok/brain-llm-cost-lab-20261119` non è ammesso da questo ambiente. Il ramo usato è `cursor/brain-llm-cost-lab-20261119-31c4`. Il commit del laboratorio è `cacedcc4e8a0e325a384fdc7514d55342e0f3d29`.

## Cosa è stato riusato, senza copiarlo nei servizi vivi

- Il prompt e il contratto JSON di `backend/v3/brain_market/deepseek_l5.py` (sola lettura).
- La formula `usage_units` / `estimate_units` di `backend/v3/runner/metering.py`, per non inventare un secondo calcolo.
- La tabella prezzi e il modello `deepseek-flash` di `backend/v3/runner/runner_config.json` (0,30 USD / 1,20 USD per milione di token, tetto configurato 0,75 USD). È una configurazione del repository, non una fattura.

Non sono stati modificati Brain, RiskManager, ExitService, EventJournal, strategie, rischio, leva, size o capitale. Il registro del laboratorio è un JSONL in una cartella scelta dal test. Rifiuta una cartella che contiene `journal.db`, `budget.db` o il nome `superbot-desk-data`.

Le PR #118, #121 e #122 restano il posto giusto per dataset, prezzi mancanti e snapshot decisionali. Questo ramo non le include.

## Modelli fissi

Niente `auto`, `auto:smart`, `auto:reliable` o `fusion`. La documentazione REST di FreeLLMAPI dice che un nome Gemini nudo può essere rimappato sulla catena automatica; per questo il candidato B usa l'id di catalogo.

| Braccio | Id | Versione | Fonte | Prezzo |
|---|---|---|---|---|
| A | `deepseek-flash` | id del file di config | `backend/v3/runner/runner_config.json` | 0,30 / 1,20 USD per milione, non misurato su una fattura |
| B | `google/gemini-2.5-flash` | Gemini 2.5 Flash | esempio esplicito in `docs/en/api/01-rest-api.md` di FreeLLMAPI | 0 nella tabella del tier gratuito, non misurato |
| C | `groq/llama-3.3-70b` | Llama 3.3 70B | stesso documento, header `X-Fallback-Trail` | 0 nella tabella del tier gratuito, non misurato |

Fonte letta il 19 novembre 2026: README e API REST su `github.com/tashfeenahmed/freellmapi`. Autenticazione: `Authorization: Bearer` con la chiave unica locale. Le chiavi dei provider restano nel router, non nel codice. Non ho verificato dal vivo l'elenco `GET /v1/models`: gli id possono uscire dal catalogo firmato. I limiti RPM per modello stanno su freellmapi.co/models e non sono stati ricopiati perché non li ho misurati.

## Benchmark

Stessi input sintetici per A, B e C. Un tentativo ciascuno. Nessun fallback. I numeri di latenza e di token dei test sono quelli del mock.

Manca, ed è dichiarato incompleto:

- costo misurato su un provider;
- consumo giornaliero reale;
- latenza media, mediana e p95 su rete vera;
- concordanza su decisioni reali;
- qualità rispetto a esiti di mercato successivi verificati.

La formula del repository, su un payload sintetico che contiene il prompt L5 e un utente minimo (non la vista di mercato completa), stima 567 micro-USD per una chiamata DeepSeek, cioè 0,567 USD per 1.000 chiamate di quella dimensione. Non è un risparmio misurato. Il prompt vero del ciclo, con candele e scoreboard, è più grande: la cifra è un pavimento di calcolo, non il costo del bot.

## Le cinque domande

### 1. FreeLLMAPI è utilizzabile qui?

Sì, come router locale OpenAI-compatibile per una prova SHADOW, se gira solo su loopback e se si fissa un id di catalogo. No come decisore del Brain. Il progetto stesso scrive di essere per esperimenti personali, senza SLA, e che un sistema reale va spostato su un'API a pagamento prima di andare in produzione. Il software è MIT; il catalogo live aggiornato è un servizio a parte (19 USD l'anno oppure 49 una volta). I tier gratuiti hanno tetti, cambiano e restano soggetti ai termini di ogni provider. Questa utilizzabilità non è stata provata con una chiamata vera.

### 2. Quali modelli hanno il miglior rapporto qualità/prezzo?

Non si può dirlo. Non c'è una misura di qualità. A ha un prezzo scritto nel repository. B e C hanno un prezzo di listino zero e id espliciti, su due provider diversi, così un disservizio di uno non sembra il risultato di tutto il pool. Il prezzo zero non dice quale dei due sia migliore. La qualità contro esiti successivi è incompleta.

### 3. Quanto si risparmierebbe?

Non c'è una misura. La stima di formula sopra vale solo per il payload sintetico e solo se DeepSeek addebita davvero la tabella 0,30 / 1,20. Il listino gratuito porterebbe quel costo marginale a zero, ma non include i tetti che fermano le richieste, il tempo di gestione, né i 19 USD del catalogo live se lo si compra. Il consumo giornaliero del bot non è stato letto dalla VPS. Nel file di config ci sono cicli da 60 minuti e 8 simboli: sarebbe uno scenario, non un consumo verificato.

### 4. Quali rischi?

Nessun SLA e latenza variabile. Quote che finiscono e risposta 429. Un id rimappato su `auto` sceglie un modello diverso da quello provato. I prompt escono dalla macchina verso i provider abilitati; alcuni possono usare i dati per addestrare. I termini di ciascun provider restano validi. Il catalogo cambia senza un commit nostro. Una risposta incompleta può sembrare un segnale se non la si scarta: il laboratorio la scarta. Un fallback automatico, come quello proposto nella PR #120, può chiamare DeepSeek a pagamento: qui non c'è. Un timeout del modello non deve fermare rischio e uscite: questo codice non li chiama, ma non li protegge da un altro processo.

### 5. Che ruolo nel Brain Unico?

A, adesso. Il decisore resta DeepSeek finché una prova SHADOW con esiti veri non dimostra altro. B è il ruolo successivo da preparare, e solo come consulente selettivo, mai come apertura. C non va promosso perché costa zero: resta un secondo braccio di confronto, su un altro provider, finché non esiste una misura di qualità. Non promuovo nessun modello.

## Sicurezza provata in locale

Errore, timeout, HTTP non 200, JSON incompleto e dati mancanti, vecchi o futuri producono `NO_TRADE` non valido e `may_open: false`. Un `NO_TRADE` valido resta valido e non scatena un altro modello. Ogni braccio ha un solo tentativo. Il client vivo lancia `live_calls_disabled` e non apre un socket. Il registro rifiuta le cartelle operative. I sorgenti del pacchetto non nominano il journal, il motore, il rischio o le uscite.

## Prossimo passo, non fatto

Solo con un nuovo consenso: far girare il laboratorio accanto al Brain, su copie di dati, scrivendo nel suo JSONL e non nel journal, ancora senza ordini. Poi misurare costo, latenza ed esiti. Prima di allora non c'è un risparmio da dichiarare.
