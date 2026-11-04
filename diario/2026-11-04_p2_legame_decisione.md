# 04/11 (mattina) — P2: legame decisione → posizione → chiusura, PR #42 DRAFT

**AI:** Claude Sonnet 5.5 (coordinatore) · codice del motore di **Grok** (consegnato come diff, Modalità B) · **Branch:** `work/v3-p2-decision-link-grok-20261104` (3 commit: `e863c6e` Grok, `773168c` e `411e51e` Claude) · **PR:** #42 DRAFT, impilata su #41

---

## Cosa è stato fatto

Catena `brain_decision.event_id → paper_open.decision_event_id → paper_close.decision_event_id`: ora un esito si può attribuire alla decisione che l'ha generato (prerequisito di F7).

- **Grok** (`engine.py`, `contracts.py`): `BrainDecision.journal_event_id`, `_append_durable` che ritorna l'id dopo la verifica del claim, `symbol` e `regime` nel payload con allowlist. Grok non può fare push (403): ha consegnato un diff come testo. Applicato **senza modifiche** in `e863c6e` (+31/−6, identico a quanto dichiarato).
- **Claude**: 46 test indipendenti sul motore (il file di test di Grok non è arrivato), correzione di un difetto, lato esecutore (`execute_paper` copia l'id in `paper_open`; `close_paper` valida il campo) e 24 test di catena completa con i produttori veri.

## Difetto trovato nel diff di Grok

`_normalize` conservava `journal_event_id` per qualsiasi decisione: un analista ostile poteva far arrivare un id finto su NO_TRADE, HOLD o decisioni respinte dal risk gate. Corretto in `773168c` (l'id si conserva solo per OPEN/APPROVED, stessa condizione di `proposal`/`risk_quote`). Il test ha mostrato il problema (4 su 46 fallivano) prima della correzione.

## Verifica

- Suite V3: **441 PASS** (371 + 46 + 24).
- Mutazione: **motore 10/10**, **esecutore 8/8**. Una variante (claim non verificato) sopravviveva finché non ho aggiunto i test "scrittura persa" e "claim estraneo".
- Dichiarazioni di Grok **non verificabili**: "375 passed" e "3/3 mutanti" riguardano un file di test che non ho ricevuto. Il suo diff funziona nel caso normale, ma aveva il difetto sopra. Sul finding di concorrenza di `close_paper` ha ammesso che contava le ricevute, non gli eventi nel journal (coincide con la verifica di Claude).
- Sonda extra su `close_paper`: 20 corse con 8 **processi** sullo stesso file SQLite → mai più di un `paper_close`, nessun crash, catena valida.

## Limiti dichiarati

- `execute_paper` non verifica che l'evento puntato esista nel journal: controllo dei legami penzolanti previsto in P3.
- Il Brain rifiuta ancora CLOSE/MODIFY_STOP.
- Stile: `__import__("re")` nel codice di Grok (non funzionale, lasciato).

## Prossimo

**P3** (mio): `TradeOutcome` immutabile + estrattore puro sul journal (net_bp, costs_bp, R, hold_ms, exit_reason, regime, decision_event_id, legame verificato). Appena lo schema esiste, prompt a Grok per i moduli F7 (P4) con l'interfaccia già fissata, così non la inventa.

⛔ Nessun merge/deploy · DESK_MODE=paper invariato · Hawk/Bull non toccati · cervello intatto · nessuna modifica a strategia, soglie, limiti di rischio o prompt.
