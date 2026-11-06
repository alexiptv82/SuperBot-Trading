# SuperBot V3 — bootstrap PAPER separato (non eseguito su VPS)

Stato verificato il **6 novembre 2026**, PR #62 in bozza. Questa procedura è **documentazione di preparazione**; non è un'autorizzazione al deploy o all'avvio. Il controllo runtime read-only GitHub Actions #42295014067 è completato con successo come **raccolta dati**, ma ha rilevato blocchi operativi: vedere la sezione «Gate runtime effettivo».

## Stato server verificato in sola lettura

- `superbot` web attivo in PAPER; Falco/Toro e vecchi container Brain fermati e con pause flag.
- Falco ha **6** posizioni registrate aperte; Toro **2**: sono storico PAPER da preservare, non da chiudere automaticamente.
- Il vecchio Brain conserva `/opt/superbot-desk-data/brain/brain.sqlite3`, NON il nuovo `journal.db` V3.
- Backup protetto salvato in `/opt/superbot-backups/rc-v3-20261106T150730Z` (tarball storici leggibili e copie SQLite con integrity_check OK). Prima del cutover, verificare uno snapshot aggiornato e recuperabilità.

## Gate capitale e run

**Capitale confermato dall'utente per V3:** Falco **1.000 USDT**, Toro **1.000 USDT**, Brain **2.000 USDT**, tutti PAPER, tre equity indipendenti, vecchi storici preservati. Il nuovo file approvato per Brain è `backend/v3/runner/runner_config_brain2000_paper.json` sul ramo della PR #62: **rischio aperto 12%**, **margine totale 55%**, leva 20x–50x, **75 USDT di perdita stimata su 350 USDT di margine**; floor 450 USDT invariato. Non riutilizzare il profilo Brain2k creato prima di tali modifiche.

## Bootstrap di una run Brain V3 completamente nuova

Solo **dopo consenso di avvio, backup verificato e scelta capitale**, un operatore può usare il modulo `backend.v3.runner.prepare_paper_run`. Non è un servizio e non apre trade. Crea una cartella **prima inesistente** (errore se esiste), un journal V3 con evento `run_prepared`, un budget SQLite, il file `PREPARED_PAUSED_ONLY.json` e la configurazione utilizzata, `mandate.json` predefinito **NON approvato** e `pause.flag` presente. Verifica che l'equity dichiarata coincida con la configurazione. Non legge, migra, azzera o modifica i vecchi dati.

Esempio illustrativo, NON eseguire adesso:

```sh
DESK_MODE=paper python -m backend.v3.runner.prepare_paper_run \
  --parent /percorso/cartella-runs-esistente \
  --run-name brain-v3-nuova-001 \
  --run-id brain-v3-20261106-001 \
  --config /percorso/config-approvato.json \
  --expected-initial-equity 2000 \
  --prepare-paper-paused
```

Il valore `2000` è **approvato**. L'esempio resta **illustrativo**, perché il nome e l'ID della nuova run sono solo segnaposto: non ripetere quelli della run Brain già preparata né eseguire il bootstrap fino alla certificazione dei backup e a un nuovo gate operativo. Dopo il bootstrap, prima di attivare il Brain: verificare `check_existing_data`, mandati, ownership unica EXIT, heartbeat del sidecar, controlli di perdita, pause, API UI e backup della nuova run. Il primo avvio dovrebbe avvenire con `pause.flag` presente, poi solo dopo verifica operativa e consenso esplicito togliere la pausa. Il CLI legacy non deve avviare EXIT insieme al sidecar.

## Falco e Toro

Non eseguire `docker start` sui vecchi container con 6+2 posizioni ancora registrate. È necessario un piano separato di run nuove per i classici, con directory e capitale indipendenti. Conservare i vecchi stati read-only per rendicontazione; l'app deve distinguere storico vecchio da run nuova. Nessuna chiusura forzata a mezzanotte, nessuna cancellazione o sovrascrittura dello storico.

## Perché ancora NO-GO

Il bootstrap risolve **solo** la lacuna del journal Brain V3 al primo avvio. Restano da verificare il montaggio reale del sidecar e il monitor durante guasti, l'unicità del proprietario OPEN/CLOSE, la UI delle tre run e il rollback. La CI di GitHub è verde sul ramo RC, ma non certifica un deploy VPS.
**Consolidamento:** il solo comando di preparazione è `prepare_paper_run.py`, testato da `test_v3_rc_prepare_paper_run.py`; il modulo duplicato è stato eliminato. La run resta in pausa e senza approvazione.


## Gate runtime effettivo — audit READ-ONLY del 06/11/2026, 21:14 UTC

Fonte: workflow `.github/workflows/v3-rc-readonly-runtime-gate.yml`, run GitHub Actions **42295014067** sul ramo PR #62. L'audit ha effettuato solo query ai servizi e letture di stato, **non modifiche** a VPS/container/journal.

| Controllo | Dato letto | Impatto |
|---|---|---|
| Test CI del codice, ultimo commit prima dell'audit `027307c` | classici + backend + frontend + 4.073 PASS / 1 SKIP V3 | Test automatici **verdi**, non un GO per VPS |
| WEB `superbot` | in esecuzione, PAPER | Applicazione ancora **senza** `V3_JOURNAL_PATH`, `V3_RUN_ID`, `V3_HEARTBEAT_PATH`, `V3_BUDGET_DB_PATH`, `V3_PAUSE_FLAG_PATH` |
| WEB classici | `DESK_DATA_DIR`, `DESK_DATA_DIR_BULL` ancora puntano alle cartelle legacy | La dashboard installata non può rappresentare le nuove run |
| Classici legacy | contenitori fermati; Falco **6** e Toro **2** posizioni PAPER storiche; pause flag presenti | **NON riavviare né riciclare** i volumi vecchi |
| Brain precedente | run `brain-v3-rc20261106` PAPER, capitale2k, `pause.flag` presente, mandato **non approvato**, journal integrity OK | **NON modificare in-place**; hash della configurazione **non coincide** con PR #62 e rischio aperto ≠12% |
| Backup locale | archivio `rc-v3-20261106T150730Z` presente, restore rehearsal #42252417296 PASS | Recupero locale testato, non sostituisce offsite |
| Backup esterno cifrato | `superbot-extbackup.service` in stato **failed**, exit=1, timer attivo; ultimo backup riuscito **2026-11-02T03:28:45Z** | **NO-GO operativo**: diagnosticare/riparare e ottenere prova recente di backup offsite ripristinabile |

L'ultimo messaggio di errore del servizio esterno è classificato **UNCLASSIFIED_CHECK_PRIVATE_LOGS** dal controllo sicuro: **non stampare** i log completi, configurazioni, percorsi remoti, token o chiavi in GitHub Actions. Un operatore autorizzato deve verificare localmente la causa, correggerla con un intervento separato, ripetere backup cifrato offsite e test di restore. `systemctl reset-failed` da solo NON ripara il backup.

### Ordine obbligatorio dei prossimi passaggi

1. Riparare **backup esterno** e attestare una copia off-VPS valida, indipendente e recente, poi verificare un ripristino isolato. Conservare snapshot locale e tutte le fonti storiche.
2. Preparare sotto percorso **nuovo e inesistente** una Brain2k PAPER con configurazione esatta della PR #62 (rischio12%/margine55%). Stato iniziale `PAUSED`; mandato `approved=false`. Non riscrivere né spostare la run preparata sul profilo vecchio.
3. Preparare **due nuovi volumi** Falco/Toro separati da quelli storici, capitale1.000 per portfolio, Claude e SHORT originali invariati, LONG S25 abilitata soltanto sulla nuova run e trend advisory consultivo; default PAUSED prima dell'avvio.
4. Verificare il layout processo OPEN / CLOSE: un **solo proprietario** per l'esecuzione PAPER; il servizio EXIT sidecar deve avere heartbeat, lock e rollback affidabili. Non fare start del runner legacy EXIT insieme al sidecar.
5. Solo dopo i precedenti gate, progettare e autorizzare **deploy separato** della dashboard V3 collegata alle nuove directory e a tutti i `V3_*`, con test funzionale da smartphone e desktop. Endpoint di sola lettura e pulsanti chiusura manuale PAPER vanno provati sulle nuove run senza scrivere sui volumi legacy.
6. Attestare politica di cooldown, floor equity450, controllo perdita, log eventi, gestione run e backup; sbloccare i worker **solo con autorizzazione esplicita dell'utente per l'avvio PAPER**, dopo report finale GO/NO-GO.

**Non eseguire automaticamente vecchi workflow** di deploy classici, che possono puntare a host o volumi legacy. Ogni comando che modifica la VPS va valutato rispetto alla specifica host e al suo perimetro; niente merge o deploy implicito.
