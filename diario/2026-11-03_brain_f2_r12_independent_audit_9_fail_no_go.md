# SuperBot V3 — 2026-11-03 — audit Brain F2 R1.2, NO-GO (9 regressions)

## Provenienza verificata
Tarball Grok ricevuto `v3-brain-f2-r1.2-20261103.tar.gz`: SHA256 calcolato `900335744875420176f6eb3cc65c9267ac8a1f2fddbeaf84f0df219a0a274466`, **coincidente** con l'hash comunicato dall'utente. Il rapporto INSERITO nell'archivio contiene invece un hash discordante `5051c3e541bf9e3d27e751456b3d83624a2750c7d9723ac819c41f78edd4bee8`: il rapporto deve essere aggiornato in una nuova confezione. Tarball estratto con controlli di sicurezza. F1 `events.py` (Git blob cd4ce09233cdfc41be43dd7083aac791e8e2c56d) e `risk.py` (514159b990c99740aee4f73b3bdd8839226e65bc) identici a quelli di PR #33.

## Test svolti da ChatGPT
- Python 3.13.5 locale: **25/25 PASS** nei tre moduli F2 contenuti nel tarball.
- Nove test avversariali indipendenti su dati sintetici: **9/9 FAIL** (regressioni reali, non sui sistemi operativi). Il motore non ha contatti con VPS, exchange o API AI reali.
- Affermazione Grok `130 PASS` su Python 3.10 e 3.11: **non riprodotta da ChatGPT** perché queste versioni e la suite F1 completa non erano disponibili nel runtime di audit.

## Nove problemi evidenziati
1. OPEN/APPROVED ottenuto usando un oggetto con `append()` no-op, senza persistenza su SQLite (engine.py:_append_event).
2. Context `BTCUSDT`, proposta `ETHUSDT` → OPEN/APPROVED: manca vincolo simbolo/quotazione.
3. Confidence `NaN` elude reviewer e può approvare OPEN.
4. NO_TRADE può essere restituito con status `EXECUTED_PAPER` senza alcuna esecuzione.
5. `decision.sources` non sanificate finiscono direttamente in payload EventJournal (potenziale leak informazioni sensibili).
6. Due istanze dopo restart, stesso run/timestamp e contatore `self.cycle=1` → due OPEN/APPROVED con **un solo evento**; chiave richiesta/idempotenza non adeguata. La semantica definitiva del duplicate request va precisata.
7. Context.price negativo non rifiutato; OPEN basato su prezzo proposto differente.
8. Test `test_independent_portfolio_observation` contiene ancora `or True`.
9. Test CLOSE/MODIFY_STOP contiene ancora `assert True`, non esercita casi reali.

## Prossimo gate, R1.3 (solo offline)
Grok deve riprendere dal tarball R1.2, correggere questi problemi senza toccare F1. Gate obbligatori: journal realmente persistente o protocollo equivalente verificabile, identità evento richiesta durevole ed esplicita, coerenza simbolo/prezzo/timestamp, confidence finita, rigorosa matrice decision kind/status e nessun EXECTUED_PAPER, sources allowlist, test CLOSE/MODIFY_STOP reali, policy/versione/snapshot/pausa ancora fail-closed. Test avversariali e F1+F2 Python 3.10/3.11 da riportare con prove; tarball finale e SHA coerente.

**Decisione:** R1.2 NON approvata, NON integrata nella PR #33. PR #33 resta DRAFT, senza merge/deploy. Nessun comando VPS, reset wallet, stop/restart o modifica dati eseguita. Questo checkpoint documenta un audit, non un rilascio.
