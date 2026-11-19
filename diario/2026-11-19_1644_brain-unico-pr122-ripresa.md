# Brain Unico — checkpoint tecnico di ripresa (2026-11-19, 16:44 Europe/Rome)

## Decisioni e stato verificato
- Obiettivo Issue #113: un Brain PAPER; DeepSeek primario, Claude consulenza su eventi, Falco SHORT advisor non bloccante; storici Falco/Toro/Brain/Arena preservati, risk/exit indipendenti. Nessun deploy, merge, reset, stop Arena o uso di API a pagamento autorizzato.
- PR #118 [DRAFT] Dataset Builder offline, HEAD `0833c0d6b53949c8f92349bb64271e725e95cdf5`. Le correzioni simbolo/provenienza risultano presenti ma richiedono verifiche indipendenti e dati reali attestati.
- PR #121 [DRAFT] rischio prezzi mancanti, HEAD `b6acaf087498eece75a94734b71f25ae52b6e2f0`. I 5 test sono scritti ma non eseguiti in questa sessione; serve controllo contro feed stale e recheck prima delle aperture.
- PR #122 [DRAFT] https://github.com/alexiptv82/SuperBot-Trading/pull/122, branch `chatgpt/brain-unico-decision-snapshot-v2-20261119`, HEAD `a81cb8972f3c80960c4d76c1f89d57c860ba2452`. Aggiunti `backend/v3/decision_snapshot_v2.py` e `backend/v3/test_decision_snapshot_v2.py`. Adapter NON integrato nei runner: evento v2 append-only linkato a decisione V3 con hash, timestamp causale, sole feature Decimal, rischio tipizzato, NO_TRADE, no testo libero. Per sicurezza `inputs_verified=false` e `eligible_for_training=false` sempre.
- PR #122: 6 prove locali in laboratorio con shim dell'interfaccia EventJournal PASS; **non** test contro vero journal di repo, dataset, runtime o VPS. Nessun workflow GitHub Actions trovato sulla HEAD, nessuno status; PR mergeable ma draft.
- Nessuna verifica diretta di Arena o VPS: non affermare che lo stato runtime corrisponda ai rami GitHub.

## Passi successivi
1. Eseguire i test #121 e #122 con EventJournal V3 reale e regression suite pertinenti su clone offline, senza Actions; audit temporale e dei failure modes.
2. Contratto comune registro v2 ↔ Dataset Builder #118, snapshot acquisita prima/durante la decisione e attestata: impossibile promuovere una ricostruzione retroattiva a dato osservato.
3. Solo dopo test e controllo storici/backup, progettare collegamento al Brain PAPER; non collegare ora.
4. Mantenere checkpoint orario già attivo 'Checkpoint SuperBot doppio': ramo `diario` + /SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md, con evidenza di entrambi; non creare automazioni doppie.

Questa nota è un checkpoint documentale, non prova di backup VPS, addestramento reale o profitto.
