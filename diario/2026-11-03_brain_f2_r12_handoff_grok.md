# SuperBot V3 — 2026-11-03 — Grok handoff Brain F2 R1.2, offline (no deploy)

## Stato verificato
- ChatGPT ha esaminato tarball Grok R1.1 effettivamente ricevuto: SHA256 `f71026faa5f329d578aaba43ca778e80ede0617a9c74fbcd6bed2bf1b17fe4d4` (non coincide con hash dichiarato da Grok `caa97c27711ef5358a968dc9b1e5142296a539398d59c060db2203cf32595dec`).
- Il tarball è stato ispezionato; file F1 `events.py` e `risk.py` equivalenti al branch PR #33.
- Test inclusi R1.1 eseguiti localmente Python 3.13.5: 16/16 PASS.
- Controlli indipendenti avversariali: 8 FAIL, 1 PASS. Nessuna verifica indipendente delle affermazioni 121 PASS su Python 3.10 / 3.11.
- PR #33 base F1, DRAFT; codice R1.1 NON pubblicato/integrato nella PR.
- Rapporto completo: `diario/2026-11-03_brain_f2_r11_independent_audit_blockers.md`.
- Test eseguibili con dati sintetici: `diario/2026-11-03_brain_f2_r12_independent_negative_tests.py`. Questi test dipendono dalle API R1.1 e non vanno eseguiti direttamente sul vecchio engine della PR #33 senza includere R1.1.
- R1 ticket di partenza: `docs/v3/brain-f2-r1-remediation-ticket-20261103.md` sul branch `work/v3-brain-f2-grok`.

## Mandato Grok — R1.2 (solo offline)
Riprendi DAL PROPRIO CODICE R1.1, NON dal prototipo originario; se il workspace R1.1 non esiste più, chiedi i sorgenti al proprietario anziché ricostruirli da memoria.

Correggi TUTTI i blocker riprodotti:
1. Niente `OPEN/APPROVED` senza un journal realmente persistente e append riuscito; chiarisci fase proposal/approval/EXECUTED_PAPER.
2. `paused` e `daily_loss_latched` obbligatori, bool stretti; missing/None/altro -> NO_TRADE.
3. Validazione difensiva di tutti i Decimal (solo finiti), policy/versione/snapshot e parametri di mercato PRIMA di usarli; fail-closed senza eccezioni.
4. Eccezioni AI/reviewer/risk manager: codici di errore allowlist, mai `str(exc)` o dati sensibili in rationale o journal.
5. Confine Brain: rifiuta `portfolio_id != brain`, richiedi run_id esplicito e idempotency key stabile attraverso restart.
6. Validazione outputs Analyst/Reviewer, incluso `None`, campi malformati, enum/confidenza/symbol/timestamp e nessun fallback.
7. Elimina `assert True` e `or True` dai test; esercita davvero CLOSE/MODIFY_STOP come non eseguibili e isolati.
8. Registra la prova con EventJournal SQLite reale: append, replay/restart, duplicate exact, conflict ID, contaminazione portfolio/run e fault di write.

Accettazione: test indipendenti allegati PASS (o equivalenti più robusti con comportamento identico); suite intera F1+F2 Python 3.10 e 3.11 senza xfail sui tre safety gate, test addizionali per edge case; nessun cambio a `backend/v3/events.py` o `backend/v3/risk.py`. Nessuna chiamata AI reale, nessun PAPER execution né operazioni VPS.

Consegna tarball **realmente scaricabile**, includendo engine R1.2, test, README, manifest SHA256 calcolato dopo l'ultima ricompattazione e test logs. Niente write GitHub se integrazione 403; non chiedere ampliamento privilegi. **Non dichiarare pronto per il deploy.**

Il codice R1.2 deve essere verificato da ChatGPT PRIMA di aggiornare la PR #33 come implementazione accettata. NO merge, NO deploy, NO reset, NO restart, NO VPS.
