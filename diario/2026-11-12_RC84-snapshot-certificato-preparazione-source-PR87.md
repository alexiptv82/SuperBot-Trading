# RC84 — 12 novembre 2026, ore 10:26 Roma — snapshot PAPER certificato con successo

## Stato reale verificato (screenshot Termius dell'utente)
L'utente ha eseguito `--check && --freeze-snapshot` della versione corretta del freeze su branch PR Draft #86 `4a005937863dc540010b748e051dcbf58cd54e77`, scaricata con hash blob `8b52c6df567032d5db74e078f4cdf1203fb804c1`.

Evidenza finale:
```text
RC84_SNAPSHOT_PREFLIGHT=PASS
RC84_SNAPSHOT_DRY_RUN_NO_CHANGES=True
RC84_SNAPSHOT_FALCO_OPEN=7
RC84_SNAPSHOT_TORO_OPEN=3
RC84_SNAPSHOT_SQLITE_VERIFIED_IN_ISOLATION=PASS
RC84_SNAPSHOT_VERIFIED=PASS
RC84_SNAPSHOT_DIRECTORY=/opt/superbot-backups/rc84-current-paper-before-fix-20261112T092631Z-15704
RC84_SNAPSHOT_MANIFEST_SHA256=a18aff67032605045dd3ef3888f5d225fdd8930b49d89d780aa676aca8f6c8fa
RC84_SNAPSHOT_PAPER_SERVICES_STOPPED=4
RC84_SNAPSHOT_PAPER_PAUSE_FLAGS_RETAINED=3
RC84_SNAPSHOT_NO_RESET_NO_TRADE_NO_LIVE=PASS
```
Conclusione: backup privato dei tre portafogli **certificato SHA file-per-file e SQLite**. Quattro servizi PAPER (Falco, Toro, Brain-runner, Brain-exit) **spenti intenzionalmente**, tre `pause.flag` conservati. Nessun reset, nessun cambio app, LIVE vietato.

**Differenza posizioni:** alle 09:14 Falco 8 e Toro 3; al backup delle 10:26 Falco 7 e Toro 3. Non attribuire senza log la chiusura Falco a stop/TP/manuale: potrebbe essere stata gestita automaticamente mentre il processo era attivo prima dello freeze.

## Correzione da distribuire, ancora NON installata
PR Draft #85 `work/rc84-fix-classic-divergence-brain-market-20261111`, commit **`ab7e0b7d991b8f4bd714fccfec23b09a936e6717`**. Test eseguiti su VPS clone isolato: 239+156+70 = 465 **esecuzioni** PASS (parte ripetuta); fix S25 duplicati, policy fallback separata tra Falco e Toro, NO_TRADE rispettato, feed Bitget candele allineate, parser maxLever BTC/ETH 150, heartbeat Brain last_cycle. Non dimostra ancora chiamate DeepSeek reali.

Versione vecchia installata in `/opt/superbot-v3-rc84-stage` e usata dai quattro unit PAPER: **`0e29a73a36f668643da4088178bacb8616a45ac0`**. GitHub compare ha verificato che è antenata della versione testata (ahead72, behind0).

## Passaggio prudente predisposto (NO switch/no servizi)
Creata [PR Draft #87](https://github.com/alexiptv82/SuperBot-Trading/pull/87), branch `work/rc84-paused-release-stage-20261112`, commit **`de06bbccac335ff59650829047deaa8f27ed355e`**, script `deploy/scripts/rc84-stage-tested-paper-source-20261112.py`, blob Git **`302f27c8e36b5aaea90aa6c6db215fcd59617bfe`**.

`--check` READ ONLY: esige 4 unità inattive, WorkingDirectory vecchio stage, 3 pause e identità PAPER, vecchio stage pulito pinned, sha del MANIFEST certificato, e RI-verifica tutti i file hash della copia privata. `--stage-source`: dopo le stesse verifiche, clona il commit testato in `/opt/superbot-v3-rc84-repair-ab7e0b7` **senza modificare il vecchio checkout**, la configurazione systemd, le unità, posizioni, snapshot, credenziali, la dashboard o la rete trading. Non attiva nulla.

**Prossimo step**: l'utente può eseguire pinned download + `python3 -I -c 'ast.parse(...)'` + `python3 -I script.py --check && python3 -I script.py --stage-source`. Se qualsiasi gate fallisce fermarsi, non forzare. Dopo staging separato preparare cutover PAPER controllato con rollback unità e heartbeat, **mai rimuovere pause prima della convalida**. Eventuale reset PAPER ammesso dall'utente ma solo dopo aver garantito ripristino/accounting e senza falsi report. Al momento nessuna operazione LIVE e Fable OFF.

**Non si richiede ripetizione dei 465 test o un secondo backup.** Il backup è già certificato, l'intervento successivo deve essere strettamente mirato.
