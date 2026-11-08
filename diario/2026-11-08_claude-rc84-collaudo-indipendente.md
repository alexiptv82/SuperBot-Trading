# RC84 — Collaudo indipendente offline — Claude — 08/11/2026

**PR #80 Draft**, SHA verificato: `05935707b651de3e89fb35509ec708ad901ed282` (base RC82 `1e64684`, RC81 `29eb757`).
Checkout isolato (`git worktree`), nessun segreto, nessuna VPS, nessun ordine, nessuna modifica al codice della PR.

## Esito sintetico

| Area | Esito |
|---|---|
| Backend RC84+RC82+RC81+RC80+RC78+exit-only | **120/120 PASS** |
| Backend tutta la suite V3 | **4 887/4 887 PASS** (132 s) |
| Backend `test_desk.py` | **84/84 PASS** (vedi P2-3: tenta rete) |
| Jest mirati (ClassicStopNotice/Overview/ThreePortfolios) | **77/78 — 1 FAIL** |
| Jest completo | **107/108 — 1 FAIL** (stesso test) |
| Build React (`CI=true`) | **PASS** (`main.641ba25d.js` 125.68 kB) |

**Verdetto: NON PASS pieno.** 1 P1 riprodotto (Telegram), 1 test Jest rosso, 2 P2.

## Comandi eseguiti
```bash
git worktree add <scratch>/rc84/checkout 05935707b651de3e89fb35509ec708ad901ed282
PYTHONPATH=.:backend python3 -m pytest -q -p no:cacheprovider --tb=short \
  backend/tests/test_v3_rc84_running_stop_health.py backend/tests/test_v3_rc82_active_paper_stops.py \
  backend/tests/test_v3_rc81_classic_stop_health.py backend/tests/test_v3_rc80_paper_stop_hardening.py \
  backend/tests/test_v3_rc78_paper_stop_monitor.py backend/tests/test_v3_classic_exit_only.py   # 120 passed
PYTHONPATH=.:backend python3 -m pytest -q backend/tests/ -k v3 \
  --ignore=backend/tests/test_auth_flow.py --ignore=backend/tests/test_profiles_engine.py      # 4887 passed
HTTPS_PROXY=http://127.0.0.1:9 PYTHONPATH=.:backend python3 -m pytest -q backend/tests/test_desk.py  # 84 passed
cd frontend && yarn install --frozen-lockfile
CI=true npx --no-install react-scripts test --watchAll=false --runInBand --testPathPattern='ClassicStopNotice|Overview|ThreePortfolios'
CI=true npx --no-install react-scripts test --watchAll=false --runInBand
CI=true BUILD_PATH=<scratch>/rc84/build npx --no-install react-scripts build
```
(`test_auth_flow.py`/`test_profiles_engine.py` esclusi: richiedono `sqlalchemy`, non legati a RC84.)

## Verifiche richieste

**3. RUNNING vs RC80 manutenzione — PASS con riserva (P2-2).** `v3_api._classic` usa RC80 solo con `close_worker_mode == 'exit_only'`; altrimenti `running_stop_health` sul `heartbeat.json` del runner (scope `classic_runner_15m_ohlc`). Contratto verificato contro `cli.write_heartbeat`/`apply_paper_protective_exits`: `portfolio`, `exec_mode`, `ts`, `last_ok`, `last_end_ms`, `stop_feed{timeframe,bar_ms,alarm,stop_certified,symbols}`, `new_exposure`, `stop_certified=false` coincidono. `stop_certified`/`quote_coverage` sempre `false`. Test Jest «runner and maintenance monitors never display each other's model» PASS.

**4. Brain non disponibile — PASS.** `Dashboard.js` usa `Promise.allSettled`: overview indipendente da `/brain/status` e `/brain/trades`; se uno dei due Brain fallisce → `wallet:null, trades:null`. `Overview.js`: PnL Brain `null` (non «0»), nessun pulsante di chiusura Brain. Test Overview/ThreePortfolios PASS.

**5. Storico/salvataggio falliti → Telegram — PARZIALE (P1-1).** Corretto per stop/TP/liquidazione (`notify_close` dopo `_prove_protective_close` e `save_state`; i 3 test RC84 PASS). **Non corretto** sugli altri percorsi di chiusura PAPER.

**6. Autenticazione e sola lettura — PASS.** Nessuna nuova rotta; tutte le 6 rotte `/api/v3/*` hanno `Depends(require_session)`. Il classificatore è puro (nessuna scrittura/HTTP). Diff RC84 su `cli.py`: solo spostamento di `notify_close`. Diff RC82 incluso su `brain.py`/`learning.py`: solo scrittura append robusta. Nessuna modifica a strategie, prompt AI, leve, capitale, sizing o limiti di rischio.

## Problemi

### P1-1 — Telegram annuncia chiusure PAPER non confermate (percorsi non protettivi)
Riprodotto con sonda sintetica (`monkeypatch`, nessuna rete; file non aggiunto alla PR):

| Percorso | Guasto simulato | Telegram inviato | Storico |
|---|---|---|---|
| Chiusura regole/Claude (`cli.py:913`) | `save_state` fallisce | **sì** | — |
| Chiusura regole/Claude (`cli.py:913`) | `append_trade_history` no-op | **sì** | **0 righe** |
| Chiudi posizione manuale (`cli.py:1467`) | `save_state` fallisce | **sì** | — |

Per ispezione stesso schema in chiusura parziale (`cli.py:932`) e S25 a tempo (`long_s25.py:216`): `notify_close` prima di `record_close` e del salvataggio. Nessun effetto su conto/ordini (PAPER, notifica informativa), ma contraddice l'obiettivo RC84. **Raccomandazione:** stesso schema del percorso protettivo (prova storico+learning → salvataggio → notifica in `try`), con test per ciascun percorso.

### P2-1 — Test Jest rosso per maiuscola
`ClassicStopNotice.test.js:82` cerca `'non è monitoraggio continuo'`; il componente scrive «**N**on è monitoraggio continuo». L'avviso è presente: errore del test, ma la suite è rossa. Correggere l'attesa (o usare regex case-insensitive).

### P2-2 — Overview non disponibile: testo del modello sbagliato
Se `/api/v3/overview` fallisce, `stop_health = null` e `ClassicStopNotice` ricade nel ramo RC80: l'allarme resta visibile (fail-visible, corretto) ma descrive «chiusura della candela da 1 minuto», cioè il modello di manutenzione, anche con Falco/Toro RUNNING. Suggerito un messaggio neutro «Dati di protezione non disponibili» quando `health` è `null`.

### P2-3 — `test_desk.py` non ermetico
Durante la suite il runner tenta ~2 700 connessioni a `api.bitget.com` (dati pubblici). In sandbox con rifiuto lento la suite non termina in 10 min; con rifiuto immediato PASS in 68 s. Stub mancanti per alcune letture di mercato/contesto.

## Raccomandazioni
1. Correggere P1-1 e P2-1 nello stesso ramo, poi nuovo collaudo sullo SHA risultante.
2. P2-2/P2-3 a scelta di ChatGPT/utente.
3. Restano aperti i gate del documento di handoff (browser autenticato/Android, sidecar Brain non installato, backup off-host, approvazione nuova run PAPER).

NO MERGE / DEPLOY / VPS / RIAVVIO / RESET / ORDINI.
