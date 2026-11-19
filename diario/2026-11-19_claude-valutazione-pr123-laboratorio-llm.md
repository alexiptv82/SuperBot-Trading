# Valutazione tecnica PR #123 — laboratorio SHADOW costi LLM (Grok) e primo confronto attendibile

**Verificato da Claude, offline:** branch `cursor/brain-llm-cost-lab-20261119-31c4` @ `c51c7520b35640518baea217404da9657702d4f5`, base `33a0de7`. Letti `docs/LLM_COST_LAB.md`, la voce di diario e tutto il codice (`models`, `schema`, `shadow`, `benchmark`, `store`). **13/13 test superati**, confermati. DeepSeek resta il decisore; la PR #120 non è attivata né integrata.

## 1. Cosa funziona già
- **Isolamento:** il pacchetto non importa runner, journal, rischio, uscite né librerie di rete; `post_once` solleva `live_calls_disabled`; ogni record ha `may_open: false`, `shadow: true`, `fallback: false`; nessun riferimento dal runtime (verificato nel ramo di integrazione).
- **Modelli fissi:** `deepseek-flash`, `google/gemini-2.5-flash`, `groq/llama-3.3-70b`; rifiuto di `auto`, `fusion`, id con `:` o fuori catalogo.
- **Errori:** timeout, connessione, HTTP ≠ 200, 429, JSON incompleto, `finish_reason` ≠ stop, dati mancanti/vecchi/futuri ⇒ `NO_TRADE` non valido; un tentativo per braccio; nessun fallback a catena.
- **Dati:** il registro rifiuta le cartelle operative (`journal.db`, `budget.db`, `superbot-desk-data`) e righe che contengono segreti; la confidenza dichiarata dal modello non viene usata.
- **Metriche:** validità dello schema, latenza media/mediana/p95, 429, errori, costo da formula del repository, concordanza con DeepSeek marcata esplicitamente come **non** correttezza.
- **Onestà del rapporto:** distingue sempre misurato / non misurato; nessun risparmio dichiarato.

## 2. Cosa è testato solo con dati sintetici
Tutto: latenze, token e costi sono quelli del mock; nessuna chiamata a provider; la "qualità" usa etichette sintetiche (`simulated_labels_only`).

## 3. Cosa mancava e cosa ho aggiunto (branch `claude/brain-llm-lab-equivalent-20261119`, integrato)
| Problema | Correzione |
|---|---|
| **Input semplificato** (solo simbolo, prezzo, regime): non è ciò che vede il decisore | `equivalent.capture_l5_request`: la richiesta la costruisce il **vero `DeepSeekL5Analyst`** con un trasporto che la cattura (nessuna rete). Ogni braccio riceve la stessa richiesta, cambia solo `model`; `request_sha256` registrato |
| Rischio di dati futuri nella richiesta | candele chiuse entro t ed esiti chiusi entro t filtrati **prima** dell'analista (test con candele/esiti successivi) |
| Equivalenza solo presunta | `matches_recorded_context`: per ogni apertura storica, SHA-256 del messaggio = `paper_open.context_hash` registrato dal vero analista ⇒ **identità provata**; se non coincide il campione è escluso |
| La proposta (entry/stop/leva) non era registrata | ora sì, con `executable` (stop dal lato sbagliato = non eseguibile, come farebbe il motore di rischio) per etichettarla con esiti veri |
| Dati del conto verso provider esterni | controllo esplicito: nessuna chiave di importi/equity/segreti nella richiesta (il prompt L5 contiene solo il **numero** di posizioni aperte) |

Test: 13 di Grok invariati + 13 miei = 26; mutazioni 9/9 rilevate; il ramo di integrazione passa da 5095 a **5121**, 0 falliti. Una richiesta L5 reale (3 timeframe, menu completo, scoreboard vuoto) misura ~4.300 caratteri ≈ **1.200 token** in ingresso.

## 4. Cosa manca ancora
- Esiti di mercato per giudicare le proposte (etichette a posteriori con costi: `learning/opportunity.py`, già nel V3).
- Prezzi, tetti RPM/RPD e affidabilità reali dei tier gratuiti: **non misurati**; il catalogo può cambiare.
- Installazione di FreeLLMAPI e chiavi dei provider gratuiti: non fatte (servono tua autorizzazione e credenziali create da te).
- Per i `NO_TRADE` storici non esiste `context_hash`: l'equivalenza per quei campioni è ricostruita ma non provata da hash (vanno tenuti in una classe separata).
- Nessuna duplicazione con #120: il client HTTP e i requisiti R1–R10 restano il riferimento per un eventuale collegamento futuro, sempre in shadow.

## 5. Primo confronto attendibile — proposta
**Idea chiave:** non serve richiamare DeepSeek. Le sue decisioni storiche (Arena e Brain V3) sono già registrate; per le **aperture** il journal conserva l'hash esatto di ciò che ha visto.
1. **Campione pre-registrato** (prima di vedere risultati): istanti di decisione storici DeepSeek dalle copie Fase 0, stratificati per regime, simbolo e lato; obiettivo ~300; due classi: `provata` (aperture con hash coincidente) e `ricostruita` (NO_TRADE e aperture senza hash coincidente, solo come analisi secondaria).
2. **Richiesta** ricostruita con `capture_l5_request` dagli stessi dati; per la classe `provata` si scartano i campioni il cui hash non coincide.
3. **Bracci:** A = decisione DeepSeek registrata (costo zero); B = Gemini 2.5 Flash; C = Llama 3.3 70B; un tentativo ciascuno, nessun fallback.
4. **Etichette** a posteriori con costi (TP/SL primo tocco a 15 min/1 h/4 h) per ogni proposta e per ogni `NO_TRADE` (ingresso sfavorevole evitato / occasione mancata).
5. **Metriche:** distribuzione LONG/SHORT/NO_TRADE; EV netto per proposta eseguibile; quota di ingressi sfavorevoli evitati; occasioni mancate; proposte non eseguibili; validità JSON; latenza p50/p95; 429 e indisponibilità; token; **costo per decisione valida**. La concordanza con DeepSeek è riportata ma non è un criterio.
6. **Criterio di utilità come consulente (pre-registrato):** migliorare l'EV netto o ridurre gli ingressi sfavorevoli rispetto a DeepSeek sullo stesso campione, con intervallo di confidenza a blocchi di giorni; altrimenti nessun ruolo.
7. **Dopo, piccolo esperimento SHADOW in avanti:** stessa richiesta del Brain a ogni ciclo, registro JSONL separato, budget e tetto di richieste fissati, nessuna apertura possibile; durata pre-registrata (es. 2 settimane).

## 6. Gratuito senza autorizzazioni vs autorizzazioni necessarie
| Attività | Costo | Serve la tua autorizzazione? |
|---|---|---|
| Revisione, estensione e test offline del laboratorio (fatto) | 0 | no (già autorizzato) |
| Costruzione del campione dalle copie **sintetiche** / pipeline completa con mock | 0 | no |
| Copie Fase 0 degli storici (journal Arena/Brain) per il campione reale | 0 | **sì** (accesso privilegiato per acquisire storici) |
| Scaricare candele pubbliche Bitget per le etichette | 0, dati pubblici | conferma consigliata (rete dalla VPS) |
| Installare FreeLLMAPI sulla VPS e creare chiavi dei tier gratuiti | 0 in denaro, ma credenziali e servizio nuovo | **sì** (credenziali/servizi; le chiavi le crei tu, mai in chat) |
| Chiamate reali a Gemini/Llama (~600 chiamate per 300 istanti) | 0 sul listino gratuito, soggette a tetti; i prompt escono verso i provider (solo dati di mercato) | **sì** |
| Richiamare DeepSeek (non necessario) | stima 0,22–2,27 USD per 300 chiamate | **sì** (spesa API) |
| Catalogo FreeLLMAPI a pagamento (19 USD/anno) | 19 USD | **sì**, e non serve: id fissati a mano |
| Esperimento SHADOW in avanti accanto al Brain | 0 sul gratuito | **sì** (processo nuovo sulla VPS) |
