# AI Arena — lettura isolata dei tre wallet e correzione UI (16/11/2026)

**Branch:** `work/brain-arena-readonly-wallets-ui-fix-20261116`  
**Base:** `work/brain-arena-selective-advisors-falco-preservation-20261116`  
**Stato:** laboratorio in GitHub, **nessun deploy, merge, riavvio, modifica di Falco/Toro/Brain in esecuzione e nessuna spesa API**.

## Risultati di questa fase

### 1. Corretta un'anomalia reale del frontend

Il file preesistente `frontend/src/brainArenaModel.js` conteneva **un blocco duplicato nella funzione `sanitizedShadow` e un'espressione RegExp interrotta**: era JavaScript invalido e avrebbe bloccato la compilazione. Riscritto mantenendo le funzioni pubbliche, aggiungendo `sanitizedTrial` e `trialTotalPnl`.

- I wallet con journal non disponibile mostrano campi **null** / trattino, non un saldo o PnL inventato.
- La nuova run DeepSeek `brain-deepseek-paperYYYYMMDD` viene accettata solo se la sorgente API e la run ID corrispondono, mentre la vecchia `brain-v3-paper20261111` rimane visibile soltanto come **storico**, non come nuovo wallet appena azzerato.
- Il PnL aggregato compare solo se **tutti e tre** hanno un `trial_start_ms` identico, sono dichiarati comparabili e hanno PnL verificato.
- Qwen e MiniMax non possono mostrare dati con run ID DeepSeek o tra loro scambiati.
- L'app `frontend/src/pages/BrainArena.js` ora rispetta lo stesso contratto.

**Verifica realmente eseguita:** il modello JS effettivamente recuperato da GitHub e' stato compilato/valutato in un interprete V8 isolato, con **11 controlli PASS**, tra cui parse, T0 comune, rifiuto di PnL storico, rifiuto run sbagliata, e nessun PnL finto per run non avviata. Non equivale a una build React completa.

### 2. Lettore backend multi-journal, senza scritture

`backend/v3/arena/read_view.py` e `read_router.py`.

- Tre cartelle PAPER distinte descritte dal piano `trial_plan.py`, con `portfolio_id=brain` all'interno di ciascun journal ma `provider` separato all'esterno.
- Necessario un `arena_manifest.json` per ogni wallet, con `trial_start_ms`, `run_id`, `model`, `experiment=independent`, `mode=paper`, capitale iniziale `2000`. **Non viene creato da queste funzioni**: servira' un avvio autorizzato del runner.
- Lettura via `EventJournal.list_run`, `verify_chain` e `extract_outcomes`. Qualsiasi journal con hash errati, eventi di altri run/portafogli, close invalidi o provenienza AI sbagliata e' rifiutato, invece di esporre profitti parziali.
- Ogni `brain_decision` di una run Arena deve avere `payload.originating_ai` coerente, cosi' una serie di NO_TRADE di DeepSeek non puo' essere scambiata con una serie Qwen. Anche `paper_open` deve riportare il provider corretto.
- PnL realizzato netto letto solo dai trade chiusi ricostruiti e riconciliati. `settled_equity = 2000 + realized_pnl` quando verificabile. **Se ci sono posizioni aperte e non esiste un mark verificato, `equity=null` e `unrealized_pnl=null`.**
- Esposizione limitata a 100 posizioni/storici per wallet nell'API, senza testo libero o credenziali.
- Dati mancanti, journal non inizializzato, heartbeat invalido o directory non autorizzata rimangono `NOT_CONFIGURED / UNVERIFIED_JOURNAL`, senza trade inventati.
- Nessuna chiamata OpenRouter, nessuna creazione di directory, nessuna azione contro Bitget, nessun reset o chiusura.

### 3. API GET esplicitamente opt-in

`backend/v3_api.py` registra l'endpoint autenticato `GET /api/v3/arena` soltanto con tutte e tre le condizioni:
- `V3_ARENA_READONLY_ENABLED=1`
- `V3_ARENA_TRIAL_DAY=YYYY-MM-DD` valido
- `DESK_MODE=paper` **e** `TRADING_MODE=paper`

La root dei journal e' fissata a `/opt/superbot-ai-arena-paper`; il contenuto non e' accessibile se non montato. Il GET imposta `Cache-Control: no-store` e usa la dipendenza sessione del router V3. Non esistono POST di apertura/chiusura su questa route. **Nessuna delle nuove flag e' stata attivata.**

### 4. Contratto di origine distinto nel BrainEngine

Il motore preesistente in `backend/v3/brain_f2/engine.py` accettava soltanto origini DeepSeek/Claude. L'estensione opzionale `arena_provider` vale **solo** se abbinata a run `brain-<provider>-paperYYYYMMDD` e `portfolio_id=brain`:
- Per le run storiche, senza parametro, `_ALLOWED_ORIGINS` e il vecchio comportamento rimangono invariati.
- Per le run Arena, il motore accetta proposte soltanto dalla AI di quel wallet. Una proposta di MiniMax arrivata al wallet Qwen non puo' superare questo confine.
- Le nuove decisioni appendono `originating_ai` nel payload del journal. Le vecchie decisioni storiche conservano il precedente formato.
- Nessun nuovo modello viene effettivamente connesso al motore da questa fase.

## Test di regressione introdotti, da eseguire su una checkout isolata

- `backend/v3/arena/test_read_view.py`: 10 test sintetici. Journal mancanti/alterati, hash chain, capitale non inventato, equity unmarked, run sbagliata e percorsi symlink.
- `backend/v3/arena/test_read_router.py`: 3 test. GET autenticato, nessuna route di scrittura, opt-in.
- `backend/v3/arena/test_engine_origins.py`: 6 test. Origine selettiva, regressione del motore DeepSeek, decisioni journal con provenienza.
- `backend/v3/arena/test_v3_integration_gate.py`: 5 test. Route assente di default, assente in LIVE, assente con data mancante/non valida, presente soltanto sotto flag PAPER.
- `frontend/src/brainArenaModel.test.js`: 8 test UI (5 precedenti + 3 nuovi); i controlli dinamici JS sopra sono **separati** da Jest.

Esecuzione prevista localmente sul ramo isolato (non su runner attivi):
```bash
python3 -m pytest -q backend/v3/arena/test_read_view.py backend/v3/arena/test_read_router.py \
  backend/v3/arena/test_engine_origins.py backend/v3/arena/test_v3_integration_gate.py
```
I 24 test Python nuovi sono **scritti ma non eseguiti** sulla VPS o in GitHub Actions. La build frontend e i test integrati del backend V3 rimangono da fare prima di proporre il rilascio.

## Ancora necessario prima della competizione di 14 giorni

1. Preparare un `ArenaL5Analyst` che produca proposte Qwen e MiniMax **con provenienza autentica** e gli stessi snapshot di candele chiuse di DeepSeek; validare JSON con e senza ragionamento, costi e ritardi. Non presentare Qwen come pronto all'inferenza ragionata: il test API precedente ha usato `reasoning: false`.
2. Realizzare le due nuove istanze PAPER con rischio, 20x–50x, capitale 2.000, exit service e journal separati, hard-limit 450 USDT, pause e stop con singolo owner. Nessun riuso di path Falco/Toro.
3. Bilanciare T0 comune, eventuali posizioni DeepSeek ancora aperte e archiviare senza reset silenziosi la vecchia run.
4. **Falco:** SHA GitHub archivato nel ramo `archive/falco-short-before-ai-arena-20261116`; occorre ancora verifica e backup coerente dei dati/configurazione effettivi della VPS. Non disattivare nuove aperture Falco/Toro prima dei controlli su posizioni aperte ed exit service.
5. Pubblicare frontend e API soltanto dopo compilazione, test offline, prova di rollback e autorizzazione. La UI Arena e' ancora su ramo separato.

**Comportamento operativo:** Falco, Toro e Brain rimangono esattamente come prima; nessun lavoro svolto in VPS.
