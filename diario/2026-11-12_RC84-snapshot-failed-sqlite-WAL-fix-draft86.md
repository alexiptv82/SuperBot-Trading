# 12 novembre 2026, ore 09:50 Roma — RC84 freeze/snapshot RIFIUTATO su SQLite Brain

## Evidenza VPS diretta utente (Termius)
Il comando verificato Git blob `86e6cec61342a8e33ebc562b7f821b80f299a7d6`, `deploy/scripts/rc84-freeze-verify-paper-snapshot-20261112.py --freeze-snapshot`, ha eseguito preflight e tentato il freeze.
Output:
- `RC84_SNAPSHOT_FALCO_OPEN=8`, `...ACTIVE_PAUSED_PAPER=True`
- `RC84_SNAPSHOT_TORO_OPEN=3`, `...ACTIVE_PAUSED_PAPER=True`
- `RC84_SNAPSHOT_BRAIN_MANDATE_APPROVED=True`, `RC84_SNAPSHOT_BRAIN_ACTIVE_PAUSED_PAPER=True`, `RC84_SNAPSHOT_BRAIN_EXIT_ACTIVE_PAPER=True`
- **`RC84_SNAPSHOT_REFUSED=sqlite_check_or_other_writer_modified_snapshot:brain`**
- `RC84_SNAPSHOT_FAILED_ATTEMPTED_PAPER_RESTART=True`
- `RC84_SNAPSHOT_NO_RESET=True`

**Nessun `RC84_SNAPSHOT_VERIFIED=PASS`**: il backup non è certificato, l'esecuzione è abortita; il codice ha tentato di far ripartire i 4 servizi PAPER, ma non ha verificato né stampato il successo. Non ripetere `--freeze-snapshot` con vecchio script. Flags di pausa sono rimasti (il codice non li cancella); verificare l'effettiva esistenza e lo stato dei 4 servizi PRIMA di altro stop.

## Ipotesi specifica ricavata dal codice (non ancora dimostrata causa esclusiva)
La versione iniziale faceva `sqlite3.connect(mode=ro)` e `PRAGMA integrity_check` **direttamente** sui DB `journal.db` e `budget.db` dentro la copia che voleva rendere byte-per-byte identica all'origine. Su SQLite WAL/SHM il driver può alterare sidecar/checkpoint quando apre e chiude; il secondo hash di tutti i file del wallet Brain diventa diverso e il controllo lo blocca. Un writer esterno rimane possibile: non concludere che il database reale è corrotto.

## Fix preparato in GitHub e prove
- PR **[Draft #86](https://github.com/alexiptv82/SuperBot-Trading/pull/86)** branch `work/rc84-snapshot-sqlite-isolation-20261112`, head `4a005937863dc540010b748e051dcbf58cd54e77` (base main `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`). **Non mergiata, non distribuita**.
- Script file blob `8b52c6df567032d5db74e078f4cdf1203fb804c1`: funzione `verify_sqlite_copies` crea copia **temporanea isolata** di DB e sidecar `-wal/-shm/-journal` vicino allo snapshot, verifica integrità lì, elimina temporanei, non apre mai DB originali della copia con SQLite. SHA prima/dopo della copia certificata mantiene il controllo e blocca ancora eventuali writer esterni. Nessun cambiamento ai 4 unit, ai wallet, al trading o ai backup esistenti.
- Test stdlib separato file blob `b10d599f7dc116c2238b36a4b831bf6d1ff04496`: test WAL/SHM e confronto hash ripetuto, file DB corrotto e DB mancante, senza accesso alla VPS o rete.
- Simulazione locale indipendente (non la suite esatta del repo) ha dimostrato che il doppio controllo integrità sulla copia temporanea preserva i DB originali e riconosce un file database corrotto: `ALL LOCAL ISOLATION CHECKS PASS`.
- Ancora non eseguito sulla VPS il test esatto presente sul ramo. **Non dichiarare snapshot PASS** finché un nuovo `--freeze-snapshot` non emette `RC84_SNAPSHOT_VERIFIED=PASS` e manifesta SHA.

## Prossimo passo minimo
In Termius eseguire un unico controllo READ-ONLY su `systemctl is-active` per 4 unit e presenza dei `pause.flag` tre wallet; poi test Python stdlib scaricato da GitHub con commit e git-blob hash pinnati, in directory temporanea `/root/rc84-snapshot-check-*`. Se PASS, pianificare un solo nuovo tentativo di backup PAPER con script corretto, **solo** con i 4 processi verificati come PAPER e pause presenti; nessun reset/merge/ordine LIVE. Fable OFF. Non ripetere vecchi pytest (395 + 70 già confermati su RC84 trading).
