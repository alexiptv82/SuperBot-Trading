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

---

## Aggiornamento (pomeriggio): verifica del report di Grok sulla concorrenza

**AI:** Claude Sonnet 5.5 (coordinatore) · **Commit:** `59f835a` su `work/v3-f5b-paper-close-20261104` (PR #41 DRAFT)

**Cosa è arrivato:** l'utente ha incollato un report di Grok ("Task A e B completati": P2 con 349 test e 3/3 mutanti; finding P1 "concorrenza non protetta", 4 chiusure simultanee tutte riuscite).

**Cosa si è potuto verificare, e cosa no:**
- ❌ I branch indicati da Grok (`work/v3-p2-decision-link-grok-20261104`, `work/v3-f5b-grok-review-20261104`) **non esistono sul server** (`git ls-remote`). Nessun commit, commento PR o voce di diario suo oggi; la sezione "Deliverable" del report era vuota. "349 passed", "3/3 mutanti" e il test `test_concurrent_close_only_one_succeeds` sono **non verificati**. P2 (Task A) resta da consegnare.
- ✅ Il finding sulla concorrenza l'ho riprodotto io con thread reali (8 thread, 3 scenari, 10 esecuzioni = 30 corse): il journal contiene **sempre un solo** `paper_close`, catena di hash valida. **Nessuna doppia chiusura** (`event_id` UNIQUE + `BEGIN IMMEDIATE` esistono già; la correzione suggerita da Grok è già nello schema). Può aver visto più chiamate "OK": richieste identiche sovrapposte ricevono la stessa ricevuta.

**Due punti minori reali, sistemati in `59f835a`:**
1. Chi perdeva la corsa riceveva `journal_write_failed` (fuorviante) → ora `position_already_closed`.
2. Semantica delle richieste identiche sovrapposte documentata nel docstring: chi somma i PnL legge gli eventi del journal, non le ricevute. Un retry identico dopo la chiusura fallisce con `position_already_closed`.

**Test e mutazione:** 112 test (erano 102); 4/4 mutanti uccisi; sul mutante "doppia chiusura vera" i test con thread lo rilevano in 20/20 esecuzioni (singolo test ~75-90%: dipende dalla sovrapposizione dei thread). Suite V3 (test_brain_f* esclusi i legacy, test_v3_events, test_v3_risk): **371 PASS**. Il numero non è confrontabile con i "345" di prima: l'insieme di file misurato è diverso.

**Correzione a me stesso:** nel messaggio del commit ho scritto "24 esecuzioni"; il conteggio corretto è 10 esecuzioni della sonda (30 corse). Segnalato sulla PR; storia del branch non riscritta.

**Prossimo:** serve che Grok faccia push del suo lavoro (o incolli il diff). Poi: `execute_paper` copia `decision.journal_event_id` in `paper_open.decision_event_id` (mio), poi P3 `TradeOutcome`.

⛔ Nessun merge/deploy · DESK_MODE=paper invariato · Hawk/Bull non toccati · cervello intatto · nessuna modifica a strategia, soglie, limiti di rischio, prompt.

### Nuovo prompt per Grok (09:40)

Dopo la verifica sopra, prompt di consegna nel Project Claude: `claude/prompt-grok-consegna-p2-2026-11-04.md`. Punto di partenza ora `59f835a` (371 PASS attesi). Chiede: (1) FASE 1, 5 domande su cosa Grok può eseguire davvero (comandi, push, origine dei numeri del suo report); (2) Task A = P2 con contratto preciso (`journal_event_id`, `_append_durable` che ritorna l'id dopo verifica del claim, `_normalize` che lo conserva, `symbol`/`regime` con allowlist, NO_TRADE → `None`); (3) Task B = chiarire se i "4 successi" erano ricevute o eventi nel journal, rieseguire `TestConcurrency`, elencare cosa ha provato; (4) due modalità di consegna: A (push + `git ls-remote` come prova) o B (diff unificato come testo, risultati marcati `NON ESEGUITO`), e rapporto finale a schema fisso.
Regola: da ora ogni lavoro affidato a Grok viene accompagnato da un prompt preciso.
