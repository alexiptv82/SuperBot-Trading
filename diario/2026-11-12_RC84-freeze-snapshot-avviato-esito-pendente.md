# 12 novembre 2026, ore 09:14 Europe/Rome — Freeze/snapshot PAPER avviato, esito ancora pendente

## Evidenza diretta accessibile

Una schermata Termius dell'utente mostra l'esecuzione del comando dello script pinned `rc84-freeze-verify-paper-snapshot-20261112.py --freeze-snapshot`, prelevato dal commit `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e` e verificato contro il blob `86e6cec61342a8e33ebc562b7f821b80f299a7d6`.

Nella schermata sono visibili i controlli iniziali:

- `RC84_SNAPSHOT_FALCO_OPEN=8`
- `RC84_SNAPSHOT_FALCO_ACTIVE_PAUSED_PAPER=True`
- `RC84_SNAPSHOT_TORO_OPEN=3`
- `RC84_SNAPSHOT_TORO_ACTIVE_PAUSED_PAPER=True`
- `RC84_SNAPSHOT_BRAIN_MANDATE_APPROVED=True`
- `RC84_SNAPSHOT_BRAIN_ACTIVE_PAUSED_PAPER=True`
- `RC84_SNAPSHOT_BRAIN_EXIT_ACTIVE_PAPER=True`

Questi output confermano l'avvio del flusso e la riuscita dei controlli preliminari su identità PAPER, pause e servizi. Confermano ancora 8 posizioni Falco e 3 Toro; non misurano le posizioni Brain.

## Limite essenziale

La schermata non mostra il ritorno al prompt né gli output finali `RC84_SNAPSHOT_VERIFIED=PASS`, `RC84_SERVICES_STOPPED=PASS` o equivalente conclusivo. Non è quindi provato che:

- i quattro servizi PAPER siano stati fermati;
- la copia dei tre wallet sia terminata;
- hash, SQLite e manifesto siano stati verificati;
- il rollback o l'eventuale riavvio su errore siano terminati.

Stato corretto: **freeze/snapshot avviato, esito pendente**. Non chiamare il backup riuscito e non procedere a deploy/reset/rimozione pause senza una schermata finale completa.

## Continuità

PR Draft #85 resta non mergiata e non distribuita, HEAD `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`. Le due vecchie Actions restano accodate e non sono fonte di questa prova. PAPER esclusivo, Fable OFF, LIVE vietato. Preservare EventJournal, storico e learning.

Restano invariati: PR #80 @ `0e29a73a36f668643da4088178bacb8616a45ac0`; extbackup `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45` preparato ma non installato; verifica locale age `ESITO: VERIFICA OK`, che non certifica backup o restore VPS.

## Prossimo passo

Attendere o acquisire soltanto l'output conclusivo dello stesso comando. Se compare PASS, documentare directory/manifesto in forma non sensibile, servizi realmente fermati e integrità; se compare errore, documentare il rollback e lo stato finale dei servizi. Nessun altro comando operativo è parte di questo checkpoint.
