# RC84 12 novembre 2026 10:31 CET — snapshot verificato, successivo replay rifiutato (atteso)

## Evidenza diretta dallo screenshot Termius, SOLO PAPER
Il PRIMO tentativo con versione corretta dello script `deploy/scripts/rc84-freeze-verify-paper-snapshot-20261112.py` (commit pin `4a005937863dc540010b748e051dcbf58cd54e77`, Git blob `8b52c6df567032d5db74e078f4cdf1203fb804c1`) ha stampato:
- `RC84_SNAPSHOT_SQLITE_VERIFIED_IN_ISOLATION=PASS`
- **`RC84_SNAPSHOT_VERIFIED=PASS`**
- `RC84_SNAPSHOT_DIRECTORY=/opt/superbot-backups/rc84-current-paper-before-fix-20261112T092631Z-15704`
- `RC84_SNAPSHOT_MANIFEST_SHA256=a18aff67032605045dd3ef3888f5d225fdd8930b49d89d780aa676aca8f6c8fa`
- `RC84_SNAPSHOT_PAPER_SERVICES_STOPPED=4`
- `RC84_SNAPSHOT_PAPER_PAUSE_FLAGS_RETAINED=3`
- `RC84_SNAPSHOT_NO_RESET_NO_TRADE_NO_LIVE=PASS`

**Snapshot certificato locale alla stessa VPS.** Non affermare che sia anche esterno/off-site. Quattro servizi PAPER rimasti stopped INTENZIONALMENTE (compreso owner uscite Brain); tre flags pause conservati. Le eventuali posizioni aperte non sono più monitorate automaticamente finché le unità restano ferme; rimane tutto simulato.

Subito dopo l'utente ha eseguito NUOVAMENTE `--check && --freeze-snapshot` e ottenuto:
- `RC84_SNAPSHOT_FALCO_OPEN=7` (dato puntuale del secondo check, precedentemente preflight 08:30 aveva 8, possibile chiusura prima dello snapshot; verificare il journal, NON inventare spiegazioni);
- `RC84_SNAPSHOT_REFUSED=paper_service_inactive:superbot-v3-paper-falco.service`.
Questo è corretto e previsto: al termine di uno snapshot riuscito i quattro servizi sono già stati fermati, dunque un secondo freeze richiede prerequisiti non più presenti e si blocca. NON invalida il manifest del primo snapshot e non è segno di nuovo guasto. Non ripetere lo script né riavviare servizi senza procedura di aggiornamento.

## Stato lavoro al checkpoint
- PR [Draft #85](https://github.com/alexiptv82/SuperBot-Trading/pull/85) su `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`, **395 test selezionati prima della correzione fallback e 70 test post-fix = 465 esecuzioni riuscite, con ripetizioni**. Gli aggiornamenti non sono ancora installati: lo stage originale `/opt/superbot-v3-rc84-stage` è pin `0e29a73a36f668643da4088178bacb8616a45ac0`.
- PR [Draft #86](https://github.com/alexiptv82/SuperBot-Trading/pull/86) correzione del backup (3/3 test isolated + primo snapshot reale verificato), NON mergiata.
- Snapshot certificato conserva dati delle tre run prima della correzione; non è una copia remota e non dimostra che successivi aggiornamenti siano sicuri senza rollback.
- **Nessun RESET, MERGE, DEPLOY o ordine LIVE** in questo checkpoint. User ha chiesto rapidamente ripartenza dei 3 bot PAPER senza bug conosciuti. Fable OFF.

## Prossimi passi reali
1. Leggere/riconoscere il manifest dello snapshot locale senza modifiche; mantenere servizi fermi e flag pause intatti.
2. Preparare una **nuova cartella di codice** sul commit esatto `ab7e0b7...` senza alterare `/opt/superbot-v3-rc84-stage`; verifica SHA e dipendenze Python. Script di primo provisioning vecchio è PINNED a `0e29...`, NON riutilizzarlo per aggiornare run esistenti con posizioni aperte.
3. Verificare i 4 unit reali e le directory dati come protezioni paper-only; staging via drop-in unit `WorkingDirectory`/`PYTHONPATH` (non edit diretti distruttivi), rollback alla vecchia directory versione `0e29...` e SHA del manifest. Non avviare nessun ingresso finché pause presenti.
4. Collaudo attivo SOLO PAPER dopo switch sotto pause; attenzione alle posizioni Falco/Toro pregresse e Brain exit owner single. Reset eventuale solo se autorizzato e gestito dopo snapshot.
