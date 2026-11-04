# 04/11 (mattina) — P1 / F5b: esecutore di chiusura PAPER, PR #41 DRAFT

**AI:** Claude Sonnet 5.5 (coordinatore)
**Branch:** `work/v3-f5b-paper-close-20261104` (commit `33b36d6`, parte dalla testa di F6) · **PR:** #41 DRAFT

---

## Cosa è stato fatto

Primo passo del piano F7: `backend/v3/executor/paper_close.py` → `close_paper(...)`. Scrive `paper_close` nel journal con PnL lordo, costi round-trip e PnL netto in `Decimal`.

- `exit_price` e `fee_bps` sono argomenti espliciti: nessuna soglia, costo o limite di rischio hardcoded nel modulo.
- `reason` ∈ {`stop`, `brain_close`, `manual`, `liquidation`}. `manual` resta distinguibile (decisione dell'utente: le chiusure manuali contano come trade veri, ma il Brain non deve copiarle alla cieca).
- Fail-closed con codici esatti e nessuna scrittura in caso di errore; una posizione non si chiude due volte.
- La perdita **non è troncata al margine**; flag `loss_exceeds_margin`. Simulare la liquidazione è una scelta di modello: lasciata all'utente.
- La dashboard F6 ora legge il produttore vero (test `open → close`).

## Verifica

82 test nuovi. Prova di mutazione: 8 difetti introdotti uno alla volta (segno, costi solo in entrata, unità bps, doppia chiusura, chiusura prima dell'apertura, ragione non validata, prezzo non positivo, vincolo portafoglio/run): **8/8 individuati**. File ripristinato identico.
Suite F2–F6 + F5b: **325 PASS**.

## Cosa NON fa (limiti dichiarati)

- Non decide **quando** chiudere: riceve il prezzo dal chiamante. Il monitor degli stop richiede un feed di prezzi, componente a parte non ancora pianificato in dettaglio.
- Il Brain rifiuta ancora CLOSE/MODIFY_STOP (`close_modify_not_executable`): è lavoro su `engine.py` (Grok), passo P2.

## Status gate

- ⛔ Nessun merge/deploy · DESK_MODE=paper invariato · Hawk/Bull non toccati · cervello intatto
- Nessuna modifica a strategia, soglie, limiti di rischio o prompt.
- Prossimo: **P3** `TradeOutcome` (record immutabile + estrattore sul journal, mio). **P2** (legame decisione→posizione) richiede una modifica a `engine.py` di Grok: da coordinare, un solo autore alla volta.

---

## Aggiornamento (06:50): difetti trovati prima della revisione esterna

Sonda su casi limite numerici (prima di coinvolgere Grok) ha trovato 3 problemi in `close_paper`, corretti nel commit `6ed0695`:
1. valori finiti ma estremi facevano uscire `decimal.InvalidOperation`/`Overflow` invece di `ExecutionError` (nessuna scrittura nel journal, ma contratto violato) -> `numeric_out_of_range`;
2. `float`/stringhe accettati come prezzo o costo -> solo `Decimal`/`int`;
3. `side=1.0` e `leverage` mancante accettati nel payload della posizione -> rifiutati.

Test 102 (erano 82), mutazione 12/12, suite completa 345 PASS.

## Richiesta a Grok

Prompt unico nel Project (`claude/prompt-grok-p2-review-f5b-2026-11-04.md`), punto di partenza `6ed0695`:
- **Task A (P2):** nel suo `engine.py`: `BrainDecision.journal_event_id`, `_append_durable` che ritorna l'id, id che sopravvive a `_normalize`, `symbol`/`regime` nel payload di `brain_decision` con allowlist. Branch `work/v3-p2-decision-link-grok-20261104`.
- **Task B:** revisione indipendente di `close_paper`, soprattutto la concorrenza fra due chiusure simultanee (finora solo ragionata). Branch `work/v3-f5b-grok-review-20261104`, nuovo file di test.
Dopo P2, Claude aggiorna `execute_paper` per copiare l'id in `paper_open.decision_event_id`.
