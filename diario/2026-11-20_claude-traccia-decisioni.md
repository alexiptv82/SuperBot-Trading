# 20/11/2026 — Claude: traccia causale di ogni decisione del Brain (snapshot v2 nel ciclo)

**Ramo:** `integration/brain-unico-20261119` @ `a5a920401e0259c63a316ceb6eea573b4a12ac8a` (prima `dd414831`). Solo laboratorio: nessun deploy, servizio, restart, parametro attivo, spesa o LIVE.

## Che cosa fa
Nel ciclo del Brain (`backend/v3/runner/cycle.py`), subito dopo che il motore ha scritto la `brain_decision` e **prima** di qualunque apertura, `backend/v3/runner/decision_trace.py` scrive uno snapshot v2 (adattatore #122 con il controllo d'ordine di scrittura):

| Requisito del proprietario | Come è soddisfatto | Test |
|---|---|---|
| Registrazione causale, prima dell'apertura | ordine nel journal `decisione < snapshot < paper_open`; istante di cattura = istante della decisione | `test_every_open_has_its_snapshot_after_the_decision_and_before_the_open` |
| Nessuna informazione futura | feature solo da candele **chiuse** entro l'istante di decisione; una barra ancora aperta viene ignorata; `feature_asof_ms ≤ decisione` (l'adattatore rifiuta il contrario) | `test_features_never_use_a_bar_…`, `test_the_cycle_does_not_decide_on_a_view_containing_an_open_bar` |
| NO_TRADE conservate | ogni decisione scritta (NO_TRADE del modello, fail-closed `ai_unavailable`, `policy_not_authorized`, rifiuti del rischio) riceve lo snapshot | 3 test dedicati |
| Nessuna duplicazione | id snapshot deterministico da id+hash della decisione; ripetere è idempotente; due decisioni candidate ⇒ `decision_ambiguous`, mai indovinare | `test_retracing_…`, `test_a_replayed_cycle_…`, `test_two_decisions_…` |
| Fallimento rilevabile e gestito | codice esplicito nel rapporto del giro e nel heartbeat (`snapshot_write_failed`, `snapshot_snapshot_written_late`, `decision_not_journaled`, …); una OPEN approvata **non si apre** (`open_blocked_untraced`). Il motore prima inghiottiva in silenzio il fallimento di scrittura di una NO_TRADE: ora è visibile | 4 test |
| Nessuna apertura presentata come tracciata senza evidenza | `trace_coverage` misura dal **solo journal** le decisioni e le aperture senza snapshot | `test_coverage_…`, `test_opens_without_a_snapshot_…` |
| RiskManager ed ExitService indipendenti | uscite, perdita giornaliera, guardia post-AI, apertura serializzata e `risk.py` non importano né traccia né snapshot (controllo statico sugli import); la traccia non tocca i controlli di rischio | 7 casi parametrizzati + suite |
| Snapshot esclusi dal training | payload `inputs_verified=false`, `eligible_for_training=false`; il Dataset Builder li **ammette** (legame e ordine corretti) ma restano bloccati da `snapshot_unverified` | `test_the_dataset_builder_admits_…` (lettore e regola reali del builder) |

Il runner cablato (`wiring.py`) usa `trace="required"`. Il valore predefinito della funzione resta `off` per i test e gli strumenti esistenti.

## Feature registrate (set v1)
Per 15m/1h/4h: `t<tf>_ret_1`, `t<tf>_ret_<finestra>`, `t<tf>_atr14_pct`, `t<tf>_rsi14`, più `fset_version=1`. Rischio: equity, margine in uso, rischio aperto, margine disponibile, gli stessi numeri visti dal motore. Sono ricalcolabili dalle stesse candele (test dedicato): è la base per la validazione indipendente, il prossimo passo.

## Limite noto (documentato, non nascosto)
La regola d'ordine considera "tardivo" uno snapshot se, tra la decisione e lo snapshot, un altro evento non-snapshot riporta un istante oltre decisione + 120 s. Con un giro lungo e il sidecar delle uscite che scrive proprio in quel momento (finestra di millisecondi), lo snapshot viene rifiutato. L'effetto è fail-closed: nessuna apertura per quel simbolo in quel giro, errore esplicito. Le uscite non ne sono toccate. Da misurare in collaudo PAPER.

## Verifiche
- Suite V3 completa offline: 5121 (su `dd414831`) → **5147 passati, 1 skipped, 0 falliti**.
- Test del Dataset Builder: 134 OK.
- Mutazioni 10/10 rilevate: niente blocco dell'apertura, traccia spenta, filtro delle candele chiuse, ricerca della decisione, decisione mancante, decisione ambigua, errore di scrittura, cablaggio, istante di cattura, copertura delle aperture.
- Rollback: commit singolo, `git revert a5a92040`.

## Prossimi passi
1. Validazione indipendente delle feature degli snapshot: ricalcolo da candele copiate e attestate. Senza esito positivo restano escluse dal training.
2. Anti-reingresso con `thesis_id` persistente.
3. Etichette degli esiti per il laboratorio LLM.
