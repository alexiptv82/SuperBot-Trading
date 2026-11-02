# SuperBot V3 — 2026-11-02 18:41 Europe/Rome — Audit reale multi-run 534 chiusure riconciliate

## Autorizzazione e vincoli
L'utente ha scritto «ok procediamo» per continuare F1 sul ramo `work/v3-foundations-event-risk-20261102`. Nessun merge, deploy, reset, attivazione di motori AI né transazione LIVE/PAPER è stato compiuto. Falco, Toro, Brain Free, Pool, AI Shadow, Turbo e Sidecar rimangono fermati (restart=no, ultima verifica di arresto), dashboard presente. Backup originale `/opt/superbot-v3-backups/20261102T144010Z` resta sulla VPS; copia esterna POST-stop non ancora attestata.

## Sviluppo
- PR #29 ancora DRAFT: https://github.com/alexiptv82/SuperBot-Trading/pull/29.
- `backend/v3/legacy_audit.py`: primo audit rigoroso su singola run, fail closed. Sul reale mostra divergenza perché `trade_history.jsonl` cumula più run mentre `state_v2.json` contiene soltanto la corrente; non è corruzione.
- `backend/v3/legacy_multirun.py`: confronta i record del cumulativo con gli eventi `close` del `learning_log.jsonl` (che contengono `run_no`), assegna ogni chiusura a una run, rifiuta match ambiguo, differenze rilevanti e incongruenze di P&L/stato run corrente. Il campo `start_equity` può essere presente solo nel trade history: viene CONSERVATO dalla sorgente, ignorando esclusivamente l'assenza nel learning; eventuali valori discordanti sulle due sorgenti BLOCCANO.
- `plan_classic_multirun_events()`: prepara eventi V3 **solo in RAM**, ID per riga (distingue chiusure parziali), digest SHA256, senza scritture.
- `backend/tests/test_v3_legacy_multirun.py` nuovo + controlli `start_equity`: test fixture per run multiple, unmatched, duplicate, field mismatch, metadata mismatch, nessuna scrittura originale.

## Evidenza su backup reale (workflow sola lettura)
- https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41493073676 — SUCCESS: Falco **348/348** chiusure mappate alle run **2-8**; Toro **186/186** alle run **1-7**; current run subset e NET coincidono per entrambi; `MULTIRUN_ISSUES=NONE`.
- https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41493242680 — SUCCESS: **348** eventi Falco e **186** Toro preparati e validati nella memoria Python, senza scritture nel journal V3; nessuna collisione di event_id, totale **534**.
- Data source storico dei classici: 59 closed + 6 posizioni PAPER OPEN nella corrente run Hawk 8; 23 closed + 2 OPEN nella Bull 7. Learning Log contiene 7 run per ciascuno; le 534 chiusure sono cumulativi, non 534 trade della run corrente.
- Brain Free: SQLite integrity PASS, 8447 eventi, 182 `trade_closed`, zero posizioni aperte. Ancora **import_eligible=False**: serve riconciliazione P&L/funding e schema specifico Brain. Non chiamare 182 'trade unici' senza verifica.
- GitHub CI https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41492985727: **35 test PASS Python 3.10 e 35 PASS Python 3.11**, test sintetici e controlli invarianti.
- Lo storico originale nella VPS e l'archivio verificato non sono stati modificati dai workflow. Le diagnosi SSH sono state eseguite in `python3 -` con codice in memoria, sul percorso `restore-test` congelato; nessun record utente, P&L numerico individuale o credenziale pubblicati nei log.

## Cosa resta prima della vera importazione
1. Riconciliare stato account, equity, movimenti di cassa, open positions/saldi, archivio V3 e run; non solo closed trade.
2. Sviluppare importazione L0 su DB V3 SEPARATO e offline, con idempotenza, confronto hash e backup esterno certificato.
3. Brain Free richiede adapter specifico per eventi, P&L, funding e partial close, senza improvvisare equivalenza con classici.
4. Non toccare PR legacy #26/#27/#28, non riavviare bot/AI, e non distribuire V3 prima del collaudo e nuovo OK.
