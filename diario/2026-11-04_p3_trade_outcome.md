# 04/11 (mattina) — P3: TradeOutcome + estrattore degli esiti, PR #43 DRAFT

**AI:** Claude Sonnet 5.5 (coordinatore) · **Branch:** `work/v3-p3-trade-outcome-20261104` (commit `1580cf8`, impilato su P2/#42) · **PR:** #43 DRAFT

---

## Cosa è stato fatto

`backend/v3/outcomes.py`: record immutabile `TradeOutcome` per ogni posizione PAPER chiusa + `extract_outcomes(journal, portfolio, run, brain_run_id=None) -> OutcomeReport`. È l'unico ingresso previsto per i moduli di apprendimento F7 (P4).

- Campi: `net_bp / gross_bp / costs_bp` (bp del nozionale di ingresso), `r_multiple`, `stop_distance_bp`, `hold_ms`, `exit_reason` (+ `is_manual`, `is_win` sul netto), `loss_exceeds_margin`, `decision_event_id`, `link_status`, `decision_regime`.
- Pura e di sola lettura. Niente si perde in silenzio: i record inutilizzabili vanno in `skipped` con codice esatto. I numeri si **ricalcolano** con la formula di `close_paper` e un close incoerente è scartato.
- Il legame con la decisione si verifica nel journal: `linked / unlinked / dangling / wrong_decision / symbol_mismatch / decision_after_open`. Solo `linked` è attribuzione affidabile.

## Verifica

- 84 test nuovi, suite V3 **525 PASS**. Catena completa con i produttori veri. Mutazione **25/25**.
- **Correzione al mio strumento di verifica:** le prove di mutazione usavano la cache del bytecode di Python; due mutanti consecutivi (file della stessa dimensione, stesso secondo) potevano eseguire un `.pyc` vecchio (visto: due mutanti diversi → stesso test fallito). Rifatte **tutte** con `PYTHONDONTWRITEBYTECODE` + `PYTHONPYCACHEPREFIX`: risultati invariati (P3 25/25, P2 motore 10/10, esecutore 8/8, concorrenza 4/4, `close_paper` 12/12; hardening F2: i test vecchi lasciano passare tutti e 3 i difetti, i nuovi li fermano 3/3/1).

## Limiti dichiarati

- Nel journal **non esiste un campo "strategia"**: il Brain non registra quale strategia ha generato la decisione. I moduli F7 raggruppano per `symbol / side / decision_regime / originating_ai / is_manual`, senza inventare etichette.
- `symbol_mismatch` confronta il simbolo in modo esatto: se in produzione i formati differissero (`BTCUSDT` vs `BTC/USDT:USDT`) quasi tutto uscirebbe come `symbol_mismatch`. Visibile in `link_counts()`; decidere guardando dati veri.

## Prossimo

Prompt a Grok per il primo modulo F7 (P4): `backend/v3/learning/expectancy.py` — expectancy netta per cella con intervalli a **blocchi di giorni** (bootstrap percentile con seme stringa deterministico; soglie come argomenti obbligatori, nessuna nel codice). Prompt nel Project: `claude/prompt-grok-p4-expectancy-2026-11-04.md`. Grok consegna come testo (non può fare push); Claude rilancia test e mutanti.

⛔ Nessun merge/deploy · DESK_MODE=paper invariato · Hawk/Bull non toccati · cervello intatto · nessuna modifica a strategia, soglie, limiti di rischio o prompt.
