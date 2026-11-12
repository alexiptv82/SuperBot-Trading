# 12 novembre 2026, ore 10:49 Europe/Rome — sorgente RC84 corretta staged, nessun cutover

## Evidenza diretta da screenshot Termius (solo PAPER)

Dopo il freeze/snapshot locale certificato, l'utente ha preparato la sorgente candidata senza modificare unità o wallet.

- Primo staging manuale alle 10:36 in `/opt/superbot-v3-rc84-fixed-ab7e0b7`: commit esatto `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`, manifest del backup verificato e output `RC84_CORRECTED_SOURCE_STAGED=PASS`, `RC84_NO_SERVICES_STARTED=PASS`.
- Script versionato della [PR Draft #87](https://github.com/alexiptv82/SuperBot-Trading/pull/87), branch `work/rc84-paused-release-stage-20261112`, HEAD `de06bbccac335ff59650829047deaa8f27ed355e`, file hash Git `302f27c8e36b5aaea90aa6c6db215fcd59617bfe`.
- Il primo `--check` dello script ha completato il preflight read-only (4 servizi inattivi, identità PAPER e 3 pause presenti, manifest certificato, 25 file backup riverificati, Falco 7 e Toro 3 nello snapshot) ma è poi terminato con `No such file or directory` perché la directory attesa `/opt/superbot-v3-rc84-repair-ab7e0b7` non esisteva ancora. Il fallimento riguarda il percorso di stage, non il manifest.
- Alle 10:45 è stato eseguito `--stage-source`: creata la directory attesa `/opt/superbot-v3-rc84-repair-ab7e0b7`, verificato HEAD `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`, output `RC84_STAGE_NEW_SOURCE_READY=PASS`, `RC84_STAGE_NO_SERVICE_OR_PAPER_WALLET_CHANGES=PASS` e `RC84_CORRECTED_SOURCE_READY=PASS`.

## Stato consolidato e limiti

- Snapshot locale sulla stessa VPS: `RC84_SNAPSHOT_VERIFIED=PASS`, SQLite verificato in copia isolata, manifest SHA-256 `a18aff67032605045dd3ef3888f5d225fdd8930b49d89d780aa676aca8f6c8fa`; 4 servizi PAPER fermati intenzionalmente, 3 pause conservate. Non è una copia off-host.
- Il dato snapshot più recente è Falco 7, Toro 3; il preflight 08:30 aveva Falco 8. Non attribuire la differenza senza EventJournal.
- PR #85 resta Draft/non mergiata e non installata; PR #86 resta Draft, correzione snapshot; PR #87 resta Draft e prepara solo sorgente.
- Nessun cutover delle unità, avvio servizio, merge, deploy, reset, ordine o LIVE verificato. Le posizioni PAPER non sono monitorate automaticamente mentre i quattro servizi restano fermi.
- Storici, EventJournal, learning, pause e wallet devono essere preservati. Fable OFF.

## Continuità obbligatoria

RC84 PR #80 resta Draft e l'ultimo codice operativo precedente resta `0e29a73a36f668643da4088178bacb8616a45ac0`. Il backup esterno `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45` è preparato ma non installato. La verifica PC della copia cifrata age ha dato `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup o restore sulla VPS.

## Prossimo passo

Solo documentazione in questo checkpoint. Prima di qualunque cutover, verificare in sola lettura directory candidata, manifest, 4 unit, 3 pause e piano rollback; poi richiedere autorizzazione separata. Non avviare servizi e non rimuovere pause durante la preparazione.
