# 12 novembre 2026, ore 08:30 Roma — Preflight manuale VPS, 11 posizioni aperte, pausa presente

## Evidenza screenshot Termius diretta dall'utente
L'utente ha eseguito uno script Python in sola lettura sulla VPS Singapore e ha mostrato:
```text
FALCO_SERVICE=active
FALCO_PAUSED=True
FALCO_OPEN=8
TORO_SERVICE=active
TORO_PAUSED=True
TORO_OPEN=3
BRAIN_SERVICE=active
BRAIN_PAUSED=True
BRAIN_MANDATE=True
BRAIN_EXIT_SERVICE=active
INSTALLED_SOURCE_SHA=0e29a73a36f668643da4088178bacb8616a45ac0
PREFLIGHT_READ_ONLY=COMPLETE
```

Quindi alla prova delle 08:30 esistono **11 posizioni PAPER classiche aperte** (8 Falco + 3 Toro), oltre a un numero **non determinato** di posizioni Brain: il comando non interrogava il journal di Brain. Non affermare che Brain sia certamente vuoto. Le pause `pause.flag` sono presenti, Brain ha il mandato approvato e il sidecar delle uscite è attivo. Le posizioni presenti non dimostrano aperture *dopo* l'attivazione della pausa: non confondere `open_count` con nuovi ingressi. Nei classici `pause.flag` significa **draining**: niente nuove aperture, ma le uscite delle posizioni continuano, salvo diversa condizione del gestore. Nel Brain la pausa del decision runner non ferma l'exit sidecar.

Il checkout attivo `/opt/superbot-v3-rc84-stage` resta pinned a `0e29a73a36f668643da4088178bacb8616a45ac0`, mentre la **PR Draft #85** con bugfix e **70 PASS + 239 PASS + 156 PASS** è allo SHA `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`. La PR non è distribuita, non mergiata; LIVE vietato.

## Preparazione del prossimo passaggio PAPER, nessuna esecuzione sui servizi
Per procedere più velocemente al reset/rilascio senza perdere lo storico corrente, è stato creato su `main` lo script conservativo `deploy/scripts/rc84-freeze-verify-paper-snapshot-20261112.py`, commit **`a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`**, Git blob SHA **`86e6cec61342a8e33ebc562b7f821b80f299a7d6`** (hash `git hash-object` da verificare su VPS prima dell'esecuzione).

Lo script:
1. Modalità `--check` di sola lettura per verificare che tutte e quattro le unità nuove siano attive, corrette, `DESK_MODE=paper`, tre cartelle e pause presenti, checkout ancora pinned. Non stampa chiavi. Controlla i portafogli ed il mandato Brain.
2. Modalità esplicita `--freeze-snapshot`: **ferma solo** `superbot-v3-paper-brain-runner`, `superbot-v3-paper-falco`, `superbot-v3-paper-toro`, `superbot-v3-paper-brain-exit`; NON riavvia alla fine se snapshot riuscito. Quindi copia integralmente le tre directory PAPER in una directory **NUOVA**, solo root, sotto `/opt/superbot-backups/rc84-current-paper-before-fix-<UTC>-<PID>/snapshot`. Controlla l'assenza di symlink, cap file/byte, disco libero, SHA256 di ogni file sia origine sia copia, integrità SQLite `journal.db` e `budget.db` Brain e che la copia rimanga identica dopo la verifica. Pubblica un MANIFEST.json root0600 contenente SHA dei singoli file, salva a video SHA manifest.
3. In caso di failure, prova a riavviare **solo** le unità PAPER che ha fermato, lasciando i tre `pause.flag` invariati; il messaggio indica esito e restituisce errore. Non modifica equity, chiusure, journal originale, nonce/chiavi o dati LIVE. Una copia parziale viene lasciata per ispezione senza sovrascrivere altri backup.

**Nota backup**: questa è soltanto una copia locale verificata sulla VPS, NON un backup off-host certificato. I vecchi script di snapshot RC77 sono dedicati a cartelle legacy senza posizioni e non possono essere usati per i nuovi 8+3 trade. Non chiamare `snapshot` riuscito prima di un output reale Termius `RC84_SNAPSHOT_VERIFIED=PASS`.

Dopo il risultato dello script: non riattivare le vecchie unità. Preparare sorgente versionata al commit esatto `ab7e0b7...`, conservare rollback `0e29a73...`, applicare aggiornamento PAPER con identità portafogli e storico preservati/reset PAPER solo su scelta dell'utente, smoke reali Brain/Claude/Telegram, poi rimuovere `pause.flag` dei tre solo dopo verifica finale. Rispettare protezione equity Brain 450 e PAPER 1k/1k/2k.

## Stato
**Nessun snapshot/freeze eseguito**, script soltanto creato e pubblicato. Non dichiarare servizi fermati o backup riuscito prima della risposta Termius. Il checkpoint ora riprende esattamente da questi gate. `Fable` resta OFF, nessun ordine LIVE.
