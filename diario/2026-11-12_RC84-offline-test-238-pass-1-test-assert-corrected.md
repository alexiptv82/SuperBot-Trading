# 12 novembre 2026 ore 06:03 Europe/Rome — RC84, 238 PASS, 1 test-only FAIL corretto nel ramo Draft

L'utente ha eseguito sul server Singapore i test Python **in directory separata**, branch `work/rc84-fix-classic-divergence-brain-market-20261111`, SHA iniziale `83b970c797b1765be0307c99ded1b8d368e379b1`, venv isolata con pytest/NumPy. Il primo tentativo falliva in raccolta per mancanza di NumPy; dopo installazione nella venv il risultato reale nello screenshot ore 06:03: **238 passed, 1 failed in 2.80s**.

Unico test fallito:
`backend/tests/test_long_s25.py::test_rc84_toro_s25_new_entries_default_off`, riga 717: `assert "last_open_ms" not in state`. La produzione di test ha correttamente **0 posizioni**, cassa e margine invariati a 1000/0; `cli.run_cycle` però scrive in ogni ciclo `state["last_open_ms"] = last_open_ms` anche quando non ci sono ingressi. Quindi la chiave esiste ma ha valore **`{}`**. Il test pretendeva una forma di stato non garantita; non è prova di apertura indesiderata.

**Fix SOLO al test su ramo**:
- test ora verifica `state.get("last_open_ms") == {}`, cioè nessun timestamp di apertura registrato;
- facoltativo ulteriore assert sul learning log: nessun evento `ev=open` con `source=rules_long_s25`;
- commit finale `557f3ea30828d9ddeba0b2b171f255540686d90c`, branch `work/rc84-fix-classic-divergence-brain-market-20261111`;
- NON cambia la logica operativa, non modifica motori live, non esegue reset, non riavvia servizi.

**Stato verificato**: 238 test PASS nel commit precedente; il test corretto NON è ancora stato rieseguito, dunque non dichiarare 239 PASS. Per test sulla cartella preesistente `/root/rc84-tests-UKXAJfmd/src` usare `git pull --ff-only origin work/rc84-fix-classic-divergence-brain-market-20261111`, verificarne lo SHA esatto, poi `.venv/bin/python -m pytest` mirato e suite completa già selezionata. I tre portafogli PAPER erano stati messi in pausa per nuovi ingressi via `pause.flag` Termius il 12/11 ore 05:05; non rimuovere flags prima di backup, regressione e piano di rilascio. PR Draft #85 invariata e NON deployata.
