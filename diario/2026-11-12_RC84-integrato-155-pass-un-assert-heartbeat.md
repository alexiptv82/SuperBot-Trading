# RC84 — collaudo integrato PAPER, 12 novembre 2026, ore 06:18 Roma

Screenshot Termius inviati dall'utente: eseguito nel clone isolato `/root/rc84-tests-UKXAJfmd/src` il comando con `PYTHONPATH="$PWD:$PWD/backend"`, virtualenv `.venv` e cinque suite `test_v3_runner_e2e.py`, `test_v3_runner_cycle.py`, `test_v3_split_runtime_integrated.py`, `test_v3_rc84_brain_single_exit_owner.py`, `test_v3_rc82_active_paper_stops.py`.

**Risultato realmente osservato: `155 passed, 1 failed in 12.53s`**. Unico errore `backend/tests/test_v3_runner_e2e.py::test_the_whole_loop_open_close_learn` alla riga 149. **Non è prova di un errore di esecuzione di trade**: il test precedente pretendeva che l'heartbeat fosse un dizionario identico senza il nuovo campo `last_cycle`. Il runner ora scrive correttamente `last_cycle: {at_ms: G+25_000, decisions:2, opened:2, errors: []}`; la traccia del test ha già confermato all'interno dello stesso caso due payload `deepseek-flash` simulati, due eventi `paper_open` BTC LONG/ETH SHORT, slippage validato e spesa simulata. Non usare questi risultati sintetici per dire che DeepSeek LIVE è già stato chiamato sulla run PAPER della VPS.

**Correzione GitHub STAGED:** nel branch `work/rc84-fix-classic-divergence-brain-market-20261111`, commit `d131fe871be50627fcb5a9e127cefd02ccddc19e`, file `backend/tests/test_v3_runner_e2e.py` adegua l'atteso al **nuovo contratto heartbeat**, includendo `last_cycle` senza allentare altri assert. **Nessuna modifica al motore trading**, nessun riavvio, deploy, reset, merge o alterazione di posizioni. PR Draft #85.

**Non ancora verificato:** il rerun aggiornato delle cinque suite, atteso 156 PASS se non emergono altri errori. Per eseguirlo dallo stesso percorso:
```bash
 git pull --ff-only origin work/rc84-fix-classic-divergence-brain-market-20261111 && test "$(git rev-parse HEAD)" = "d131fe871be50627fcb5a9e127cefd02ccddc19e" && PYTHONPATH="$PWD:$PWD/backend" PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q backend/tests/test_v3_runner_e2e.py backend/tests/test_v3_runner_cycle.py backend/tests/test_v3_split_runtime_integrated.py backend/tests/test_v3_rc84_brain_single_exit_owner.py backend/tests/test_v3_rc82_active_paper_stops.py
```
I 239 test precedenti (feeds/S25/contracts/runner) sono PASS, ma il collaudo live reale e la differenziazione strategica effettiva dei classici restano da validare. Le `pause.flag` PAPER sono state create via Termius alle 05:05, NON riavviare senza conferma. Fable OFF, NO LIVE.
