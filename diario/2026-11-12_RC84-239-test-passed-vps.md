# RC84 — 12 novembre 2026, ore 06:08 Europe/Rome — 239 test selezionati PASS su VPS

L'utente ha eseguito manualmente, in `/root/rc84-tests-UKXAJfmd/src` (clone isolato, senza toccare motori PAPER attivi), `git pull --ff-only` sul ramo `work/rc84-fix-classic-divergence-brain-market-20261111`, verificato HEAD **`557f3ea30828d9ddeba0b2b171f255540686d90c`** e lanciato `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q` su:

- `backend/tests/test_v3_lab_fetch_candles.py`
- `backend/tests/test_v3_runner_feed_monitor.py`
- `backend/tests/test_v3_runner_contracts.py`
- `backend/tests/test_v3_runner_runner.py`
- `backend/tests/test_long_s25.py`

**Prova screenshot inviata dall'utente:** `239 passed in 2.80s`, ZERO FAIL, ZERO ERROR. È reale e non inferito da CI, anche se la VPS è quella dei bot (test eseguiti in clone isolato/venv).

Il primo run (06:03) aveva dato `238 passed, 1 failed` soltanto per un'asserzione erronea nel test S25: `cli.run_cycle` registra sempre `state["last_open_ms"] = {}` anche senza nuove aperture. Il test aggiornato verifica la mappa vuota e l'assenza di eventi OPEN S25, commit `557f3ea...`. **Non è stata modificata la logica operativa** per correggere questo unico fallimento. Il secondo run conferma esito pulito.

**Cosa questo NON prova:** non c'è ancora collaudo integrato end-to-end del nuovo wiring Brain con decisioni DeepSeek effettive, della proprietà unica delle uscite, delle API dashboard/Telegram e della ripartenza dai tre wallet resettati. Falco/Toro condividono inoltre una logica fallback rule oltre alla vecchia S25, quindi la completa differenziazione strategica richiede ancora una valutazione. Unità live non aggiornate; PR [Draft #85](https://github.com/alexiptv82/SuperBot-Trading/pull/85) resta aperta/non mergiata. Gli ingressi PAPER sono stati bloccati manualmente dall'utente alle 05:05 mediante `pause.flag` delle tre run; non rimuovere finché non abbiamo test integrati, backup e check VPS.

**Prossimo collaudo mirato proposto:** `test_v3_runner_e2e.py`, `test_v3_runner_cycle.py`, `test_v3_split_runtime_integrated.py`, `test_v3_rc84_brain_single_exit_owner.py` e `test_v3_rc84_same_cycle_exposure.py` usando venv già creata, senza nuovi GitHub Actions. Se PASS, considerare una verifica simulata di una decisione Brain e SHORT/long independent per classici, poi backup e rollout PAPER in sequenza con rollback documentato. Fable OFF, LIVE vietato.

**Vincolo espresso dall'utente:** evitare ulteriori settimane di gate non necessari, ma mantenere test sufficienti per non riavviare bot con difetti noti.
