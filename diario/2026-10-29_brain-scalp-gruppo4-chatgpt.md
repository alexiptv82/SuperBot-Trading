# Brain Scalp dual PAPER — Gruppo 4 I6 + tre bug Code: completato offline

**Data:** 29 ottobre 2026. **Autore:** ChatGPT (chat normale). **Autorizzazione:** utente «Okay, procedi» dopo il report conclusivo del Gruppo 3.  
**Fonte specifica:** `claude/prompt-chatgpt-brain-scalp-completo-2026-10-29.md` sul ramo `diario`, sezione Gruppo 4 (I6 + tre bug Code).

## Sintesi verificata

**GitHub Actions [40902066955](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40902066955): SUCCESS su Python 3.10 e 3.11. 89/89 test per interprete, 178 esecuzioni totali.**  
Ramo modificato: solo `work/brain-scalp-dual-20261028`. HEAD al test: `cbdbefa1e972c07e2cc33e6b2c59c06d711b520b`.  
La CI verifica anche l'immutabilità di `backend/desk`, `backend/director/brain_free`, workflow e file di deploy originali. **Non è stato eseguito alcun deploy, merge, reset, ordine, accesso operativo alla VPS, modifica ai bot classici, Brain Free, PWA, dati o portafogli.** Sempre PAPER offline.

## Modifiche e verifica dei quattro punti del Gruppo 4

### 1. I6 — Risposta AI con elementi malformati; piani indipendenti

**File:** `backend/director/brain_scalp/coordinator.py`

- `BrainPair.accept_ai_plans` gestisce ogni piano individualmente: `symbol` non stringa/non hashable, payload non oggetto, side incompatibile, timestamp e TTL invalidi producono un singolo rifiuto tracciato e non bloccano i successivi.
- L'identità e il timestamp NON vengono più fidati dal modello: `plan_id=uuid4().hex`, `created_ms=now`. La durata è convalidata dalla `ttl_ms` o dalla differenza originaria `expires_ms-created_ms`, altrimenti default 120s; TTL massimo rimane quello già configurato nel wallet.
- Duplicati della stessa coppia `wallet/symbol` vengono rifiutati senza abbandonare il resto della risposta. I due wallet generano ID distinti e mantengono database separati.
- Persistenza eventi `ai_plan_rejected` e `ai_response_processed` con motivi sintetici e conteggi **senza memorizzare i payload grezzi del modello**, che potrebbero contenere informazioni non attendibili o confidenziali.
- Payload enormi: processa al massimo 32 proposte e registra `ai_plans_truncated` con conteggio delle proposte saltate, evitando che il troppo-pieno scarti tutte le prime proposte valide.
- Restano **PAPER e offline**: il modello non viene chiamato in questa funzione, e il codice non crea ordini reali.

### 2. Bug Code — Prezzo già troppo oltre il trigger

**File:** `backend/director/brain_scalp/engine.py`

- Introdotta protezione `MAX_ENTRY_OVERSHOOT=0.0005` (0,05% oltre il trigger nel verso del trade). Se la quota corrente è troppo lontana, il piano viene rifiutato con `trigger_already_breached`, includendo trigger, prezzo osservato e scostamento.
- Controllo **sia al momento di prenotare**, sia subito prima del fill di un piano pendente: impedisce acquisto LONG a 101,2 con trigger 100 e analogo problema SHORT.
- Se la condizione viene rilevata a fill, la prenotazione viene cancellata e l'evento `plan_rejected` conserva la motivazione. Un piccolo overshoot sotto soglia resta ammissibile.
- L'esempio del Gruppo 2 che verificava il rifiuto economico a 100,25 è stato spostato a 100,04: oltre lo 0,05% la nuova protezione scatta correttamente **prima** della verifica I2. Il test I2 continua a verificare il rifiuto del target inadeguato quando l'ingresso è ancora nel limite overshoot.

### 3. Bug Code — Stop troppo stretto rispetto ai costi

**File:** `backend/director/brain_scalp/engine.py`

- Aggiunto `stop_inside_noise` quando la distanza dello stop, dal trigger o dal fill simulato, è **inferiore al costo roundtrip stimato** `2*(fee_rate+slippage)`. In configurazione attuale fee per lato 0,06% + slippage per lato 0,02%, costo roundtrip stimato 0,16%.
- Il rifiuto è tracciato con `stop_pct`, `cost_pct`, `ratio`, `min_stop_pct`, per comunicare all'AI perché il setup non è fisicamente sensato nei parametri del laboratorio.
- Test LONG e SHORT con stop 0,04% rifiutati; stop 0,20% resta ammissibile. Il rifiuto non modifica autonomamente i livelli proposti dall'AI.
- **Avvertenza:** stop a distanza superiore ai costi non garantisce valore atteso positivo o evita slippage superiore al modello. Questo è un filtro di qualità, non una certificazione di redditività.

### 4. Bug Code — Prenotazione durante uno stop giornaliero

**File:** `backend/director/brain_scalp/engine.py`

- Gruppo 3 aveva già introdotto il latch `daily_stop_triggered` e il blocco delle prenotazioni nello stesso giorno UTC; questo resta operativo e testato.
- Gruppo 4 aggiunge `opening_not_allowed:daily_stop_threshold` se, con quotazioni complete e fresche, l'equity è già sotto soglia **anche prima che il tick successivo abbia persistito il latch**. Analogamente non si prenota in stato `paused`, sotto `kill_equity`, né con equity non verificabile.
- Nessun nuovo piano/slot viene riservato quando il controllo fallisce. L'evento `daily_stop_latched` resta responsabilità del tick di gestione, che preserva gli audit e le uscite.
- Le posizioni già esistenti continuano a essere gestite da stop/TP e protezioni: il gate limita soltanto i nuovi rischi, non assicura che la perdita giornaliera complessiva termini esattamente alla soglia.

## Test e CI

Nuovo `backend/tests/test_brain_scalp_group4.py`: **18 test** dedicati a malformed/unhashable input, ID e timestamp generati dal motore, TTL bounded, due wallet separati, piani validi nella stessa risposta di piani invalidi, log sanitizzati, oversize bounded, overshoot LONG/SHORT in submit e tick, stop sotto il noise floor e prima del tick di stop quotidiano, pause e latch.

Il workflow dedicato `.github/workflows/brain-scalp-dual-ci.yml` ora esegue tutte le suite 1, 2, 3, 4 sia in Python 3.10 sia in 3.11, e verifica l'assenza di modifiche ai codici protetti.  
**CI finale SUCCESS:** [40902066955](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40902066955), **89 test × 2 interpreti**, nessun test rosso finale.

## Gate aperti, per Claude e per il progetto

1. Questi test sono **sintetici e offline**: non è dimostrata profittabilità su replay Bitget, reale tempistica delle risposte DeepSeek, resilienza di un supervisore H24 o disponibilità di un feed REST/WS. Non è un'autorizzazione al deploy.
2. Il vecchio SQLite Brain Scalp del laboratorio creato prima del Gruppo 3 usa una fingerprint non compatibile: prima di un riavvio servono backup verificato, analisi e migrazione esplicita. Nessun reset implicito.
3. Le quote 3 secondi per ingressi, 10 secondi per protezioni, limite overshoot 0,05%, costi 0,16% e controlli del Gruppo 4 devono essere stressati in replay contro volatilità, latenze e fee osservate, senza cambiare a posteriori i criteri guardando i risultati.
4. La decisione **Gruppo 6 I8 opzione A/B/C** sui budget di capitale rimane sospesa e **non è stata implementata**.
5. **Gruppo 5 (I9 metriche + I7 snapshot PWA)** non è iniziato: richiede separata autorizzazione utente. Claude può revisionare queste modifiche, ma non autorizzare da solo deploy, reset né modifica dei classici.

## Riferimenti

- Specifica Claude: https://github.com/alexiptv82/SuperBot-Trading/blob/diario/claude/prompt-chatgpt-brain-scalp-completo-2026-10-29.md
- Codice laboratorio: https://github.com/alexiptv82/SuperBot-Trading/tree/work/brain-scalp-dual-20261028
- CI verde: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40902066955

**AI: chatgpt (chat normale).**
