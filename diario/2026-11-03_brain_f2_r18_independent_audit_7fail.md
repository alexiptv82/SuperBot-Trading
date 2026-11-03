# SuperBot V3 — 3 novembre 2026 — audit indipendente Brain F2 R1.8: NO-GO

**Archivio verificato:** `v3-brain-f2-r1.8-20261103.tar.gz`, 20.823 byte, SHA256 `2e391068e11f8a7985ced978071ab236712095906f5d27081d390e2433de56f5`, 18 membri, estrazione sicura.

**F1 invariata:** Git blob `events.py` = `cd4ce09233cdfc41be43dd7083aac791e8e2c56d`; `risk.py` = `514159b990c99740aee4f73b3bdd8839226e65bc`. Base confrontata con PR #33.

**Test realmente eseguiti:** Python 3.13.5, F2 contenuti nel pacchetto **76 PASS**, `compileall` PASS; ulteriori 9 controlli di sicurezza indipendenti **7 FAIL, 2 PASS**. Grok dichiara 181 PASS su Python 3.10 e 3.11; non riprodotti indipendentemente. Suite F1 completa non presente nell'archivio.

## Fallimenti riprodotti

1. **Mandato senza scope (3 FAIL):** `_mandate_ok` accetta `portfolio_id=None`, `run_id=None` (entrambi assenti, uno dei due assente) e consente `OPEN/APPROVED` con callback test che ritorna True. Mandato deve dichiarare **esplicitamente** `portfolio_id='brain'` e `run_id=self.run_id`, non ammettere valori omessi.
2. **Mandato senza identità approvatore (1 FAIL):** mancando `approved_by`, callback True può approvare. Il verificatore di test dimostra solo contratto booleano; un'integrazione autentica esige receipt/autorità verificata, senza auto-attestazione.
3. **Journal assente (1 FAIL):** ramo di errore ritorna `NO_TRADE/REJECTED` **senza** _normalize; `proposal` e `risk_quote` rimangono allegati.
4. **Append journal fallita (1 FAIL):** stesso bypass della normalizzazione, con proposta/quote su un NO_TRADE.
5. **MarketContext.symbol tipo intero (1 FAIL):** input malformato può ottenere `OPEN/APPROVED`; validare simbolo str conforme a contratto prima del risk gate.

**Due PASS:** MarketContext totalmente assente è rifiutato senza eccezione; con mandato scoped valido (fittizio, callback True solo per test), Journal SQLite e contesto valido si ottiene OPEN/APPROVED come proposta, non come esecuzione PAPER.

## Root fix per Grok R1.9, niente patch isolate

- Rendere _normalize/ricostruzione output **unico gate di uscita per tutti i percorsi**, compresi errori Journal, eccezioni, errori input e policy. Invariante: ogni decisione non OPEN/APPROVED ha proposta e risk_quote NULL in memoria/return.
- Mandato con scope portfolio e run **obbligatorio, non opzionale**; validare identità e attestazione con fonte di fiducia esterna. Il motore non può certificare da solo chi approva: in assenza di trust anchor genuino, NO_TRADE.
- Validare rigorosamente contesto/simbolo/tipo timestamp e input prima di analista/risk quote.
- Preservare TUTTI i test precedenti, includere i nuovi nove; test F1+F2 su Python 3.10/3.11 in CI; archiviare log e SHA256 del tarball finale. Nessuna modifica a F1.

Test indipendenti: `diario/2026-11-03_brain_f2_r19_independent.py`.

**Decisione:** R1.8 NON integrata in PR #33. La PR rimane DRAFT, nessun merge, deploy, reset, riavvio, accesso VPS, wallet o API AI.
