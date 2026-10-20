# ChatGPT — Audit Bull 10 slot e consegna contratti Director v1
**20 ottobre 2026, dopo aggiornamento Claude 14:45 Roma** — verifica e consegna su rami separati, **NON merge/deploy/trigger**, nessuna modifica a Hawk/Bull/LIVE, nessun segreto.

## 1. Nuove decisioni ricevute

Hawk: 10 slot, conto iniziale e budget margine totale **1000 USD**, max 100 USD/trade. Bull: **10 slot**, conto iniziale e budget margine totale **1000 USD**, richieste di margine 150–350 USD in funzione della convinzione, max 350 USD/trade; gli slot non vanno riempiti automaticamente. Turbo: per ora **3 posizioni** in sola ombra. Questa configurazione **non autorizza** idea futura Bull5+Turbo5 e capitale 1500 USD. Ciclo Desk invariato: 30m normale, 15m con scalp aperto/in drain. Nuovo Director in processo separato con conto virtuale proprio.

## 2. Commit 75370e3 e 68145cb: audit del codice letto

**Confermato** (diff veri letti via GitHub): 
- `75370e3` modifica `backend/desk/cli.py:_make_bull_config` max_open 3->10 e `backend/desk/brain.py:SYSTEM_BULL` a 10 slot e intervallo 150–350; aggiorna commento workflow `desk-deploy.yml`, introduce 6 test `test_bull_slots_2026_10_20.py`.
- `68145cb` porta `max_margin_total` Bull 1050->1000, aggiunge `cli.account_snapshot` con i limiti veri e adatta `brain.build_prompt` per non inventare più 2000USD/10 slot quando mancano. Cinque test in `test_prompt_account_line_2026_10_20.py`, incluso un `run_cycle` con dati simulati. Soglie 60/63 invariate. Il codice del branch `work/salto-qualita` contiene i valori ricevuti.
- `backend/desk/cli.py:426-433` `make_account` sostituisce dopo `PaperAccount.from_dict` i limiti dello stato con `PORTFOLIO.limits`; quindi i limiti salvati a 3/1050 **non continuano a valere nel loop Desk dopo caricamento**, a condizione che il nuovo codice sia effettivamente in funzione. Nessuna verifica dello stato che gira su VPS.
- `backend/desk/engine.py:140-146` stop giornaliero12%, kill_equity450, invariati; numero di posizioni verificato con `len(self.positions)>=L.max_open` in `engine.py:159-162`, quindi si aggiorna dinamicamente. `backend/desk/live_connector.py` non contiene uno specifico limite Bull3/1050 nei percorsi letti; gestione delle quantità è indipendente da max_open.
- `.github/workflows/desk-deploy.yml:25-29,209-225` reagisce solo al trigger su `rule-pool`; imposta DESK_PORTFOLIO=bull, DESK_MODE default paper e DESK_BULL_CAPITAL default1000; nessun limite Bull3/1050 ancora fissato. File trigger NON toccato.
- `backend/server.py:930-972` legge dinamicamente `len(positions)` dallo stato per /api/desk/bull/status, nessuna limitazione a 3; non espone tuttavia `max_open` in questa risposta (se si vuole mostrare una barra x/10 in quell'endpoint occorre un dato effettivo versione/schema, da concordare). La Settings generalista `frontend/src/pages/Settings.js:195-213` usa `config.max_open_positions` del **bot V1**, non la configurazione dei portafogli Desk; allo stesso modo `.github/workflows/deploy.yml` (main) usa MAX_OPEN_POSITIONS=3 riferito al V1, non a Bull Desk. Non cambiare questi valori pensando di correggere Bull.
- La dashboard V2, `frontend/src/pages/Dashboard.js:12-20,347-365`, mantiene 27 simboli nel carosello, incluso `MATIC`, contro 26 in `desk/cli.SYMBOLS`; difetto preesistente, NON legato ai 10 slot, da sistemare con ownership frontend concordata. `frontend/src/api.js` sul ramo WORK corrente non contiene commenti Bull max3 (la ricerca GH sul ramo default può mostrare versioni obsolete).

**Rilievo concreto nuovo e importante — RISCHIO TAGLIA BULL SOTTO 150USD.** `engine.py:175-178` usa `room=min(max_margin_trade,max_margin_total-margin_in_use,cash*0.95)`, poi `mar=min(margin_richiesto,room)` e rifiuta soltanto se `mar<Limits.min_margin=30`. La riga "150–350 USD" in prompt e il gate 150USD in `cli.py` prima dell'apertura NON garantiscono un fill ≥150USD quando la cassa si esaurisce: il motore **riduce automaticamente** la taglia a 30–149USD. Mini-calcolo eseguito dalla formula del codice (fee di entrata 6 bp, leva10x, 1000USD iniziali, sette richieste consecutive da 150USD): i primi sei ingressi sono 150USD; il settimo e' limitato a circa **89,87USD**, non rifiutato. **Chiedo a Claude** test di regressione e scelta esplicita di Alexander: (A) rifiutare il settimo quando spazio<150, oppure (B) consentire sizing parziale sotto 150 e dichiararlo chiaramente. Per ora nessuna modifica di engine/cli.

**Ulteriore cautela**: il guardrail `cli.py:1038+` forza a **200USD/15x/medio** una proposta Bull inferiore al minimo o a leva troppo bassa. Quindi "dimensiona 150–350 in funzione della convinzione" è istruzione non una legge numerica deterministica; una formula di sizing del Director andrà progettata e misurata separatamente.

**Test attribuiti a Claude:** 6+5 test e mutation tests 10+8 sono dichiarati da Claude e visibili nel commit come codice, **NON rieseguiti** da ChatGPT nel checkout completo. La suite totale e lo stato VPS non sono stati verificati da ChatGPT.

## 3. Implementazione di ChatGPT, solo nel ramo work/director-chatgpt

Ramo creato esplicitamente da `work/salto-qualita`, che contiene entrambi i commit Bull. Diff verso base confermato **9 file nuovi, nessun file esistente modificato**, 9 commit nuovi, nessun workflow/installazione.

- `backend/director/contracts/v1.py`: dataclass frozen pure con validazione esplicita di `MarketFrame`, `Candidate`, `DirectorAdvice`, `PortfolioSnapshot`; supporto `DataQuality`, `PriceLevel`, `PositionView`. Versione schema 1, parsing/as_payload e check temporali, niente import di `desk.cli`, nessuna rete o ordini.
- `DirectorAdvice.hold_conviction_0_100`: valore soggettivo, obbligatorio su HOLD/REASSESS; NON è una probabilità calibrata. `review_after_bars` richiede `review_timeframe_ms`, produce `proposed_review_not_before_ms`; è consiglio, non rinvia risk-check/stop.
- `fixtures/contract_cases_v1.json` contiene esempi canonicizzati di mercato, opportunità, consiglio HOLD, conto virtuale Bull con 10 slot e limite 1000USD.
- `backend/director/contracts/outcomes.py` e `fixtures/outcome_cases_v1.json`: **convenzione comune labeler Claude/replay ChatGPT** e 8 casi obbligatori: long/short TP, stop+TP stessa barra (vince stop), gap avversi (riempimento sfavorevole open), uscita time, incompleto UNRESOLVED. Ingresso open barra successiva, costi roundtrip una sola volta, funding baseline long1bp/8h. **Non sostituisce** `desk.turbo_scalp.strategy.step` né il motore contabile `PaperAccount`.
- `backend/director/research/phase0_preregistration_v1.json` e `PHASE0_AND_TURBO_GATE_V1.md`: range detector preregistrato senza lookahead, 26 simboli, 5m/15m, costi 12/16/20/30 bp, holdout ultimi 60gg blind. Turbo sei simboli, cooldown 2 vs3, 90gg screening, **≥300 trade e ≥6 mesi per promozione**, costo **20bp** primaria decisione, ciascun simbolo con n/risultati e nessun simbolo >40% delle operazioni, test su entrambe le metà, controllo casuale abbinato e Bonferroni K2, day block bootstrap lower95% del vantaggio >0. Se una soglia non supera il test, restare shadow; decide Alessandro se, in un futuro separato, testare sottoconto vs Bull integrato. **Idea 5+5 /1500USD NON approvata.**
- `backend/tests/test_director_contracts_v1.py` standard `unittest`, 8 test. `CONVENTIONS_V1.md` descrive limitazioni e responsabilità.

**Eseguito personalmente** in ambiente locale isolato con **file identici ai blob GitHub** (sha verificate per i 7 file di codice/fixture/test/prereg): `PYTHONPATH=/mnt/data/director_build/backend PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s /mnt/data/director_build/backend/tests -p 'test_director_contracts_v1.py' -v` → **8 test passati**; roundtrip dei contratti, lookahead, stop/target, ambiguità, gap, unrisolved, funding, costo una volta. **Non eseguito** test end-to-end sul repository GitHub, pytest completo, fetch candele vere, replay, test su VPS, API provider o exchange. Clausola: le fixture non sono approvazione automatica alla produzione; chiedere a Claude la revisione del codice e degli invariant.

## 4. Fonti ufficiali per Qwen e Mistral da verificare prima del provider adapter

- **Qwen 3.7 Flash, Model Studio Singapore / International**: https://help.aliyun.com/en/model-studio/model-pricing, sezione `Qwen-Flash > Singapore`, identificatore `qwen3.7-flash`, soglie per *numero input token per singola richiesta*, con **prezzi in CNY per milione token**:
  - `0 < input <= 32K`: input 0,225 CNY/M, output 0,974 CNY/M;
  - `32K < input <= 256K`: input 0,749 CNY/M, output 2,998 CNY/M;
  - `256K < input <= 1M`: input 1,499 CNY/M, output 5,995 CNY/M.
  **Attenzione:** il superamento della soglia fa pagare alla tariffa nuova *tutti* i token della richiesta, NON solo quelli eccedenti. Alibaba dichiara quota gratuita in Beijing/China solo per alcuni modelli, **non** per Singapore/International; verificare account regione, privacy, trattamento dati, terminologia non-thinking vs thinking e limiti reali prima di usare lo stato anche minimizzato. Rate limits: https://help.aliyun.com/en/model-studio/rate-limit .
- **Mistral Small 4**, modello `mistral-small-2603`: https://docs.mistral.ai/models/mistral-small-4-0-26-03 — 256K contesto; prezzo dichiarato **USD 0,15/M input, USD 0,60/M output**, supporto structured outputs. Prezzi reali nel tenant/area e limiti da verificare prima della scelta.
- **Mistral privacy/training API**: https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training — policy del 03/09/2026: **Mistral Studio e API possono usare input/output in certi casi, esiste OPT-OUT** specifico in Admin > Privacy > Anonymous improvement data; non assumere opt-out attivo senza verifica. **ZDR** è un'opzione distinta: https://docs.mistral.ai/admin/monitor-comply/zero-data-retention . Distinguere minimizzazione dati, uso per training e retention operativa.
- Per tutti i provider le capacità di JSON non provano la qualità di trading. Benchmark stesso frame/candidati contro regole, random abbinato, astensione e placebo, valutazione costi/token reali prima di spendere €15–20 per mese shadow. DeepSeek Flash resta primo da provare, non vincitore decretato.

## 5. Richieste a Claude e stato finale

**Chiedo:**
1. Conferma o contesta con test il caso Bull 7ª posizione ridotta a ~89,87$ nonostante proposta150; esplicita opzioni reject vs partial sotto150 e chiedi decisione utente prima di eventuale modifica.
2. Conferma distinzione App V1 `MAX_OPEN_POSITIONS=3` vs Desk Bull10 e aggiorna in futuro **solo con OK frontend** il carosello 27/MATIC. Controlla eventuale bisogno di endpoint max_open.
3. Revisiona i quattro contratti e *condividi* l'esatta fixture `outcome_cases_v1.json` per il tuo etichettatore. Usa `outcomes.evaluate_path` oppure test di conformità; verifica anche la coerenza logica della preregistrazione e segnala casi limite (gap, timestamps e funding); non modificare file del mio ramo.
4. Test di impatto Bull su scenario reale registrato/VPS richiede autorizzazione lettura VPS distinta; non avviare trigger autonomamente.
5. Non sviluppare ancora l'integrazione Bull+Turbo o LIVE; il contratto Director non implica tali decisioni.

**STATO:** file del Director nuovi su ramo `work/director-chatgpt`, pronti per revisione Claude; file di audit separato in `diario`; nessun merge, deploy, trigger, modifica bot o compromissione delle chiavi. 
