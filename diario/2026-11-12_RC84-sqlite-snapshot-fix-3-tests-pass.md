# RC84 — 12 novembre 2026, ore 10:22 Europe/Rome — correzione SQLite backup: 3 test PASS

## Evidenza Termius fornita dall'utente
- 4 unità PAPER attive: `superbot-v3-paper-falco`, `superbot-v3-paper-toro`, `superbot-v3-paper-brain-runner`, `superbot-v3-paper-brain-exit`. Il precedente `RC84_SNAPSHOT_FAILED_ATTEMPTED_PAPER_RESTART=True` si è quindi risolto nel riavvio di tutte e quattro le unità, almeno al momento del controllo.
- `pause.flag` delle 3 run presenti: `classic-hawk-paper20261111`, `classic-bull-paper20261111`, `brain-v3-paper20261111`: tutti `PAUSED=YES`.
- Script e test isolati scaricati da ref esatto `4a005937863dc540010b748e051dcbf58cd54e77` della [PR Draft #86](https://github.com/alexiptv82/SuperBot-Trading/pull/86), controllati hash Git blob `8b52c6df567032d5db74e078f4cdf1203fb804c1` per lo script e `b10d599f7dc116c2238b36a4b831bf6d1ff04496` per test.
- Test stdlib su **soli dati sintetici**: `Ran 3 tests in 0.070s — OK`; casi WAL/SHM snapshot immutato (`RC84_SNAPSHOT_SQLITE_VERIFIED_IN_ISOLATION=PASS`), database corrotto rifiutato, database mancante rifiutato.

## Stato effettivo
- La patch `verify_sqlite_copies` è in GitHub, branch `work/rc84-snapshot-sqlite-isolation-20261112`, PR #86 Draft, SHA `4a005937863dc540010b748e051dcbf58cd54e77` e blob `8b52c6df567032d5db74e078f4cdf1203fb804c1`. La copia SQLite isolata usa file DB e sidecar temporanei, non apre i DB del backup originale. Verifica finale hash delle tre run e stopper fail-closed restano.
- **Backup REALE ANCORA NON CERTIFICATO**. La prova 3/3 non è `RC84_SNAPSHOT_VERIFIED=PASS` sul wallet reale: ripetere una volta lo script corretto con `--check` poi `--freeze-snapshot`, su VPS Singapore, con hash verifica e preflight. Su successo 4 servizi restano **stopped intenzionalmente**, incluse uscite Brain; `pause.flag` conservati. Su errore ritorno non garantito benché script tenti restart.
- Dati e portafogli ancora PAPER, 8 posizioni Falco e 3 Toro riportate dal preflight delle 09:14, Brain mandate approvato e posizioni Brain non ancora contate. Nessun reset/deploy/merge autorizzato prima di manifest e backup.
- Strategie RC84 PR Draft #85 su SHA `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`, 239+156+70 test eseguiti superati (465 test eseguiti con ripetizioni), **non installate**. No LIVE, Fable OFF.

## Prossimo checkpoint
Invitare l'utente a eseguire `curl` pinned e SHA-check nuovo script (non vecchio) in `/root`, `python3 -I script.py --check` e poi `--freeze-snapshot`. Verificare solo in presenza di output `RC84_SNAPSHOT_VERIFIED=PASS` con percorso/manifest SHA. Se rifiuta ancora, **non** tentare reset né ripetere senza analizzare.
