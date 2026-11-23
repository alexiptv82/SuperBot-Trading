# 2026-11-23 — Revisione pre-avvio Brain Unico: distinzione fra memoria, feedback e training

## Richiesta del proprietario
- Dashboard Brain Unico in stile Classici approvata visivamente sul Samsung; proprietario chiede verifica finale strumenti e soprattutto memoria che impari, non soltanto archivi, prima di avviare PAPER 72h.

## Verifica di ChatGPT su codice GitHub dell'integrazione (head 9b153278) e branch UI (cd56fb71)
- **Memoria online realmente collegata al prompt LLM:** `backend/v3/runner/wiring.py` inietta `outcomes_source=lambda: extract_outcomes(journal, 'brain', run_id).outcomes` nel `DeepSeekL5Analyst`. In `backend/v3/brain_market/deepseek_l5.py`, ogni decisione ottiene `scoreboard=build_scoreboard(...)` e il prompt istruisce DeepSeek a preferire strategie storicamente positive, evitare negative, poter tentare non misurate.
- **Qualità del feedback:** `outcomes.py` verifica legame decisione/posizione, costo e PnL netto, regime e strategy_id. `brain_view/view.py` esclude `manual` e non-linked dal punteggio di strategia; manual close conservata ma non imitata. `view_params.json`: `min_trades=15`, `min_days=4`, confidence 0.90 per classificazione della singola cella strategia/lato/regime; una run nuova ha ancora poco o nessuno storico. Con 72h si collauda soprattutto la registrazione, non si dimostra miglioramento del modello.
- **Non è auto-training:** `docs/v3/BRAIN-UNICO-TRAINING-DATASET-BUILDER-20261119.md` dichiara builder solo offline, prove sintetiche, nessun modello addestrato/prodotto. API `backend/v3_api.py` campo `learning.training_authorized=False`, `model_active=False`. `valid_examples_collected` conta decisioni tracciate (`cov.valid`), NON esempi attestati e ammessi dal builder; non spacciarlo per training effettivo.
- **Memoria storica di Arena/classici non inserita automaticamente:** scoreboard legge gli esiti della *sola run nuova*. Storici Falco/Toro restano esclusi da training poiché non certificati semanticamente. Arena e Brain precedenti conservati, ma nessun transfer automatico nell'LLM.
- **Claude automatico NON attivo:** in `backend/v3/runner/cycle.py`, `BrainEngine(..., reviewer=NoReviewer())` e `engine.step(context, 0.0)`; Claude oggi resta consulente esterno, non modello secondario nel ciclo.
- **Protezioni operative implementate:** nuovo PAPER 2000 USDT, profilo B 1% perdita stimata per trade, 4% rischio aperto, 4 posizioni, stop nuove aperture a 4% daily loss, leva 1-30x, margine massimo 50%, equity floor 1600, budget AI $0.75/die, ciclo 60 min; exit owner indipendente. Precollaudo PASS e installazione dashboard PASS da screenshot utente precedenti. NON è prova di rendimento.
- **Non verificabile da GitHub da solo:** stato LIVE della chiave DeepSeek e risposta API, qualità feed proprio ora, eventuali errori journal dopo deploy. La presenza della chiave nel file controllata da `80-paper.sh attiva` non certifica che provider accetti payload/modello.

## Verdetto
- GO condizionato per **test PAPER tecnico** dopo unico controllo minimo live key/provider, exit service, dashboard run, stato, configurazione e mandato. No claim di auto-learning completo né di prestazioni positive; 72h solo primo segmento e poi osservazione più lunga per feedback con min giorni.
- Non aprire altri progetti di backup o training e non modificare algoritmo prima di vedere i risultati.
- `approved:false` fino al comando di avvio condizionato. Proprietario ha espresso volontà di iniziare test se i punti essenziali sono verificati; comando di attivazione da eseguire con consapevolezza dopo report finale.

## Continuità
- Questo documento è una REVISIONE statica, non un'esecuzione su VPS o autorizzazione automatica a attivare la run.