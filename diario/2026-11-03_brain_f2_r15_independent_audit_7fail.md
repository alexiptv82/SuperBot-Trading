# SuperBot V3 — 2026-11-03 — Brain F2 R1.5 audit indipendente: NO-GO

## Archivio e verifiche

Archivio ricevuto: `v3-brain-f2-r1.5-20261103.tar.gz`, 15 elementi, SHA256 reale `ad8ac275d0b107653ba8708184f341d6db36c9f010c031887897bff7bdb97eb5`. Estrazione isolata senza symlink/path traversal. File F1 invariati: `backend/v3/events.py` Git blob `cd4ce09233cdfc41be43dd7083aac791e8e2c56d`; `backend/v3/risk.py` Git blob `514159b990c99740aee4f73b3bdd8839226e65bc`. PR #33 DRAFT, non integrata.

Python 3.13.5: **52/52 test F2 consegnati PASS**; nove nuovi test avversariali indipendenti: **7 FAIL, 2 PASS**. I `157 PASS` dichiarati da Grok in Python 3.10/3.11 non sono stati riprodotti indipendentemente; suite F1 completa non inclusa in tarball.

## Rilievi con test riproducibili

1. `OpenProposal.rationale` non sanitizzata: testo sensibile sintetico restituito in `BrainDecision.proposal` e in `self.memory`, nonostante sanificazione di `BrainDecision.rationale`. FAIL.
2. `OpenProposal.originating_ai` accetta provider non autorizzato; OPEN approvato. FAIL.
3. `BrainDecision.occurred_at_ms` può essere un giorno più vecchio del `MarketContext.timestamp_ms`; OPEN approvato e Journal timbrato con altro timestamp. FAIL.
4. `policy_mandate` non è vincolato all'hash/valori della RiskPolicy: cambiando max_loss_fraction senza cambiare mandato si ottiene OPEN/APPROVED. FAIL.
5. `approved_by='unverified-stranger', approved=True` è accettato come attestazione nonostante nessuna verifica dell'autorità operatore. FAIL. Il campo da solo non prova approvazione.
6. `complexity_threshold='0.7'` è interpretato come float e può approvare OPEN, malgrado il contratto dichiari tipo float stretto. FAIL, hardening di tipo, non bypass di review nel caso soglia numerica valida.
7. `run_id` predefinito `brain-f2-offline` può approvare OPEN senza run esplicito del chiamante. FAIL, hardening di scope.
8. `policy_mandate.approved=False` non approva: PASS.
9. OPEN valido con journal persistente è solo APPROVED, mai EXECUTED_PAPER: PASS.

Il codice completo dei nove test viene pubblicato nel branch diario come `diario/2026-11-03_brain_f2_r16_independent_audit.py`. I test presuppongono API R1.5 e vanno eseguiti su quel codice, non direttamente sul prototipo originale PR #33.

## Nuovo mandato Grok R1.6

Riprendere da **R1.5**, non da zero. Priorità: sanificare ogni campo non attendibile anche dentro proposta/risposta/memoria, imporre identità e timestamp AI coerenti con MarketContext, vincolare immutabilmente il mandato alla RiskPolicy e ad autorizzazione operatore verificabile (se manca trust anchor, **NO_TRADE**; nessun finto approvatore). In seconda battuta irrigidire tipi soglia e run_id esplicito. Non cambiare F1, non indebolire test precedenti, non inventare budget/rischio/prezzi/approvazioni.

Accettazione: nove test indipendenti PASS, tutte le suite F1+F2 su Python 3.10/3.11, e altri casi di replay policy/versione, dati malformati, origini e timestamp. Consegna tarball scaricabile con SHA256 finale e report. **NO MERGE/DEPLOY/VPS/RESET/RESTART**. R1.5 NON integrata in PR #33.
