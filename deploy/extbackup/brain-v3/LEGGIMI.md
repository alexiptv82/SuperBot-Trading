> **Aggiornamento V2 (revisione 2):** il wrapper `run-v3.sh` resta in `/opt/superbot-extbackup-v3/`, ma da V2 **lavora in `/opt/superbot-extbackup-v2/brain`** (clone, stato, cancello del timer) e cifra per i destinatari V2 verso il repository
> `superbot-backups-v2`. I dati V1 in `/opt/superbot-extbackup-v3/{v3,brain-free}` non si toccano. Una installazione V1 esistente si aggiorna con `upgrade` (vedi `deploy/extbackup/age-v2-migration/LEGGIMI.md` §4bis); il cancello del timer richiede una
> prova verificata con le API di GitHub (un rapporto locale vale solo con `--accept-unsigned-certificate`). La pulizia `ExecStopPost` gira solo se prende lo stesso `.lock` dei backup (non può toccare i file di un backup manuale in corso). I percorsi `/opt/superbot-extbackup-v3/v3/…` nel testo sotto sono quelli V1.

# Backup esterno cifrato di Brain V3 (estensione affiancata a quello di Falco/Toro)

**DESTINATARIO E REPOSITORY: dal commit di migrazione age V1→V2 questa estensione cifra verso i destinatari V2 (`/opt/superbot-extbackup-v2/recipients.txt`, con impronta fissata nel wrapper) e pubblica nel repository V2 `superbot-backups-v2`. Gli archivi V1 restano nel repository `superbot-backups`, separati e intatti. Procedura completa: `deploy/extbackup/age-v2-migration/LEGGIMI.md`.**

**Stato: PREPARATO E PROVATO SOLO OFFLINE. NON INSTALLATO. Nessun accesso alle VPS è stato fatto per scriverlo. Revisione di sicurezza ChatGPT applicata (vedi sotto).**
Installare solo dopo revisione di ChatGPT e OK esplicito dell'utente. Il backup di Falco e Toro (`external_backup.py`, `run.sh`,
timer 03:20 UTC) **non viene modificato né chiamato**: questa è una componente separata, con cartella di lavoro, ramo git,
famiglia di archivi e (se voluto) timer propri.

## Che cosa protegge

| Famiglia | Contenuto | Ramo nel repo privato V2 `superbot-backups-v2` | Cadenza proposta |
|---|---|---|---|
| `v3` | ogni cartella `/opt/superbot-v3-paper-runs/brain-v3-*`: `journal.db`, `budget.db`, `runner_config.json`, `PREPARED_PAUSED_ONLY.json`, `mandate.json`, `pause.flag`, `daily_loss.json`; come *transient* `heartbeat.json`, `exit_heartbeat.json`, richieste/esiti di chiusura; eventuali file piccoli non previsti in `extra/` | `brain-v3` | giornaliera, solo se lo stato è cambiato |
| `brain-free` | il solo `brain.sqlite3` storico (Brain Free/V2), **separato** dalle run V3 | `brain-free` | a mano, una volta; poi solo se cambia |

I lock (`.exit_service.lock`, `.brain-paper-open.lock`) non si copiano mai: sono lease del kernel. Una richiesta di chiusura in sospeso viene
copiata ma **non torna mai attiva** al ripristino (resta in `transient/`).

### Dati osservati, configurabili, futuri (nessuna assunzione che Brain V3 sia installato)
* **Osservati dalla documentazione** (non riletti da me sulla VPS): la run `/opt/superbot-v3-paper-runs/brain-v3-rc20261106` preparata in pausa, mandato non
  approvato (06/11); `brain.sqlite3` di Brain Free di 469.327.872 byte con 8.447 eventi (03/11).
* **Configurabili**: `--runs-root`, `--run`, `--legacy-db`, `--work`, `--remote`, `--branch`.
* **Creati dalla futura run**: `heartbeat.json`, `exit_heartbeat.json`, `daily_loss.json`, `close_request.json`/`close_result.json`, nuove righe di journal e budget.
  Se `--runs-root` è assente o vuoto e non c'è un backup precedente: uscita 3 «niente da proteggere» (non un errore, non un successo muto).

## Come garantisce la sola lettura e la coerenza
* SQLite si copia con l'API di backup (transazione consistente, include il WAL già confermato). Tre casi, tutti provati nei test:
  * `journal.db` (modalità rollback): `mode=ro`, nessuna scrittura;
  * **WAL pulito** (nessun `-wal`/`-shm`): `immutable=1`, nessun file creato;
  * **WAL con `-wal` e `-shm`** (processo vivo *oppure* residuo di un arresto brusco): la sorgente **non viene mai aperta con SQLite** (una apertura, anche
    `mode=ro`, può far ricostruire il `-shm` a SQLite). Si copiano database e `-wal` in una cartella privata (`<work>/<modo>/scratch`, 0700), leggendo ogni file una volta
    con SHA-256 e ricontrollando poi dimensione, data e SHA-256 della sorgente (se è cambiata: `source_changed_during_capture`); SQLite recupera il WAL sulla **copia**.
    Database, `-wal` e `-shm` originali restano identici per byte, data e dimensione (provato con WAL pulito, residuo dopo crash, scrittore inattivo e scrittore attivo).
    Con uno scrittore **attivo** la copia riesce solo se nulla cambia durante la lettura; altrimenti rifiuto esplicito (mai una copia incoerente).
* Nessun database vuoto viene creato al posto di uno assente: file mancante = **rifiuto** (`file_missing`).
* Catena hash del journal ricalcolata evento per evento (stessa formula di `backend/v3/events.py`), id unici, trigger di immodificabilità presenti, una sola identità
  (`brain` + `run_id`), primo evento `run_prepared` coerente, posizioni PAPER coerenti (nessuna chiusura senza apertura).
* Coerenza *tra* i file: configurazione (SHA-256) = marcatore = evento `run_prepared`; mandato della stessa run e con l'impronta dei limiti della configurazione;
  heartbeat della stessa run; spese del budget né anteriori alla creazione della run né nel futuro.
* Dati in modifica: la copia vale solo se, rileggendo la sorgente dopo la copia, l'impronta è identica (poche riprese, poi `source_changed_during_capture`).
* Ancore: eventi/hash di testa del journal e righe/hash del budget dell'ultimo backup riuscito (nel manifesto in chiaro). Un journal più corto, riscritto, o una run sparita =
  **rifiuto** (`anchor_regressed`, `run_missing_since_last_backup`). Nulla viene sovrascritto né cancellato; `--prune` esiste ma richiede anche `--confirm-prune`.
* **File sconosciuti** nella cartella di una run (es. un file di memoria): se sono file normali (≤ 16 MiB ciascuno, ≤ 64 MiB in tutto) vanno in `extra/`; nel manifesto interno
  ogni file ha nome, **percorso originale**, dimensione, SHA-256, modo e data di modifica; sono compresi nell'impronta di stato (una modifica genera un archivio nuovo) e nel
  controllo «sorgente cambiata durante la copia». Directory, collegamenti o file più grandi dei limiti = rifiuto (`unexpected_entry`), mai omessi in silenzio.
  Al ripristino restano **solo** in `extra/` (verificati byte per byte, data di modifica ripristinata, modo originale nel rapporto): nulla viene rimesso nella cartella della run.
* **Interruzioni**: SIGTERM/SIGINT ripuliscono staging, scratch, archivio in chiaro e cifrato parziale prima di uscire. Dopo un arresto brusco (SIGKILL, spegnimento) restano solo
  file temporanei nostri in una cartella 0700 con file 0600, mai nel clone che si pubblica; il primo avvio successivo li toglie (`ripulito il residuo temporaneo`) e, per il timer,
  `ExecStopPost` li toglie comunque. I dati originali non sono mai toccati.
* Cifratura age con la sola chiave **pubblica** (quella già usata dal backup di Falco/Toro); la chiave privata di recupero è dell'utente e non è sul server.
* Verifica remota: dopo il push, clone nuovo e indipendente del ramo e ricalcolo dello SHA-256 di ogni file inviato.

Codici di rifiuto (uscita 1) — in più: `identity_duplicated`, `timer_gate_missing`: `file_missing`, `file_unsafe`, `unexpected_entry`, `sqlite_not_a_database`, `sqlite_integrity_failed`, `hot_journal`, `sqlite_busy`,
`wal_sidecar_state_unexpected`, `journal_schema_unexpected`, `journal_chain_invalid`, `journal_duplicate_event`, `journal_identity_mixed`, `journal_not_prepared`,
`journal_empty`, `paper_incoherent`, `config_invalid`, `config_hash_mismatch`, `marker_invalid`, `marker_mismatch`, `mandate_invalid`, `mandate_run_mismatch`,
`mandate_policy_mismatch`, `heartbeat_run_mismatch`, `budget_schema_unexpected`, `budget_run_mismatch`, `source_changed_during_capture`, `snapshot_mismatch`,
`anchor_regressed`, `budget_regressed`, `run_missing_since_last_backup`, `legacy_*`, `runs_not_certifiable` (elenca le run difettose; una sola difettosa blocca tutto).
Uscite: 0 ok/invariato · 1 rifiutato o fallito · 3 niente da proteggere (**non certifica nulla**: nessun `ultimo_successo`/`ultima_verifica_ok`, e per systemd è un fallimento visibile).

## Dimensioni e conservazione (misure su giornali sintetici con il formato vero; non misure della VPS)
Archivio cifrato V3, una run, payload realistici (`brain_decision` ~0,3 KB, 3 % di aperture):

| Ritmo | 30 giorni | 90 giorni | 180 giorni | Crescita del repo con archivio *completo giornaliero* a 180 g |
|---|---|---|---|---|
| 24 decisioni/giorno | 0,10 MB | 0,28 MB | 0,56 MB | ≈ 50 MB |
| 240/giorno | 0,93 MB | 2,8 MB | 5,5 MB | ≈ 500 MB |
| 960/giorno | 3,7 MB | 11 MB | 22 MB | ≈ 2 GB |

* Poiché il journal è append-only, gli archivi completi giornalieri crescono in modo quadratico nella storia git (la retention toglie i file dalla punta del ramo, non la storia).
  Misura reale da fare nei primi giorni: `repo_byte` in `status.json`. **Guardie**: `--max-repo-mib` (1500), `--max-archive-mib` (400), `--max-file-mib` (45, oltre si spezza in parti).
  Se la crescita misurata proietta oltre ~1 GB in sei mesi: passare a cadenza settimanale o a segmenti incrementali (decisione aperta, vedi gate).
* Brain Free: 469 MB grezzi. Misure su database **sintetici** (la comprimibilità vera non è nota): 366 MiB puliti → 125 MiB cifrati in 3 parti, 20 s; 352 MiB + 25 MiB di `-wal` e `-shm`
  residui (il caso reale) → 122 MiB cifrati in 3 parti, 22 s, circa 370 MiB di RAM, sorgente identica per byte/data/hash (`-shm` compreso). Con i file collaterali presenti serve spazio per la copia
  privata (≈ database + `-wal`) oltre a staging, archivio e clone: il preflight stima 3× e ne chiede almeno 3 GB. `--plan` sulla VPS dà il numero esatto **prima** di inviare. Va pubblicato una
  volta e poi solo se cambia (`INVARIATO` altrimenti). Il clone del backup di Falco/Toro scaricherà quel ramo una sola volta.
* Retention proposta (non automatica): 14 recenti + 8 settimanali + 6 mensili per V3 (come Falco/Toro); Brain Free: tutto. Rotazione quando il repo si avvicina al limite:
  nuovo repo privato annuale (`superbot-backups-2027`) o ramo orfano nuovo, **dopo** un ripristino verificato dell'ultimo archivio. Nessuna cancellazione senza autorizzazione.

## Installazione (Termius, sulla VPS di Singapore, come root) — SOLO DOPO OK
```sh
# 0. file approvati: clone anonimo del repo pubblico e controllo del commit approvato
git clone --depth 1 --branch work/extbackup-brain-v3-20261110 https://github.com/alexiptv82/SuperBot-Trading.git /root/extbackup-v3-src
git -C /root/extbackup-v3-src rev-parse HEAD            # deve essere ESATTAMENTE il commit approvato
cd /root/extbackup-v3-src
# 1. controlli sui SOLI METADATI (nessuna apertura SQLite, nessuna scrittura, nessun file creato)
python3 -I deploy/scripts/external_backup_brain_v3.py --mode v3 --preflight --work /opt/superbot-extbackup-v3 \
  --tools deploy/scripts --recipient-file deploy/extbackup/recipient-v2.txt \
  --expect-recipients-sha256 <impronta fissata nei wrapper> \
  --ssh-key /root/.ssh/superbot_backup_v2_ed25519 --known-hosts /opt/superbot-extbackup/known_hosts \
  --remote git@github.com:alexiptv82/superbot-backups-v2.git
# 2. simulazione dell'installazione: stampa l'IMPRONTA DI APPROVAZIONE (deve coincidere con quella approvata)
python3 deploy/extbackup/brain-v3/install_brain_v3_extension.py install
# 3. applicazione (NESSUN timer, nessun backup avviato)
python3 deploy/extbackup/brain-v3/install_brain_v3_extension.py install --apply --approve <IMPRONTA>
# 4. prova locale completa, senza rete e senza invio: stampa dimensioni e numero di parti
/opt/superbot-extbackup-v3/run-v3.sh --plan
# 5. primo backup vero (pubblica e verifica da GitHub)
/opt/superbot-extbackup-v3/run-v3.sh
cat /opt/superbot-extbackup-v2/brain/v3/status.json            # ultimo_successo, archivio, sha256, verifica, repo_byte (nessun segreto)
```
**Il timer NON si attiva senza la prova** (cancello verificato dall'installatore, non da una promessa):
1. un backup reale pubblicato e verificato (passo 5; un `--plan`, l'uscita 3 o un tentativo fallito non contano);
2. un ripristino **indipendente su un'altra macchina** con la chiave privata, che scrive il certificato:
   `python3 -I deploy/scripts/restore_brain_v3_backup.py --archive … --identity … --out /cartella/vuota --certificate cert.json [--v3-src /checkout/RC84]`;
3. si porta `cert.json` sulla VPS e: `install_brain_v3_extension.py install --with-timer --restore-certificate cert.json` (simulazione: dice se il cancello è soddisfatto), poi
   con `--apply --approve <IMPRONTA>`. Il certificato deve avere esito OK, lo stesso SHA-256 dell'archivio pubblicato, le stesse run (eventi e hash di testa) del suo manifesto, le
   impronte degli strumenti di ripristino di questo repository, e **non** essere stato prodotto su questa macchina.

Attivazione del timer: scrive le unità (senza `Persistent=true`), poi `daemon-reload`, `enable`, `start` del **solo timer** (mai `enable --now`, mai l'avvio del servizio) e controlla che
il timer sia attivo e il servizio no. Un passo che fallisce, un segnale o un errore: `stop`/`disable` del timer, unità e `timer-gate.json` tolti, registro ripulito. Il registro
`/root/extbackup-v3-install/INSTALL-MANIFEST.json` è scritto **prima** di ogni modifica (stato `in_corso`, poi `completo`): dopo un'interruzione brusca `status` lo segnala e
`rollback --apply` toglie tutto ciò che risulta presente e invariato. Una riattivazione (rollback poi nuova installazione) non lancia nessun backup arretrato.
Il programma, se avviato dall'unità (`SUPERBOT_V3_SCHEDULED=1`), rifiuta di partire senza `/opt/superbot-extbackup-v2/brain/timer-gate.json`.
Brain Free (a mano, una volta): `/opt/superbot-extbackup-v3/run-v3.sh --mode brain-free --plan`, poi senza `--plan` se dimensione e parti sono accettabili.

## Verifica con ripristino isolato (su un'ALTRA macchina, con la chiave privata di recupero)
```sh
git clone --branch brain-v3 git@github.com:alexiptv82/superbot-backups-v2.git bk && cd bk
git clone --depth 1 --branch work/extbackup-brain-v3-20261110 https://github.com/alexiptv82/SuperBot-Trading.git src
python3 -I src/deploy/scripts/restore_brain_v3_backup.py --archive brain-v3/AAAA/MM/superbot-brainv3-<data>.tar.gz.age \
  --identity /percorso/chiave-di-recupero.txt --out /cartella/vuota --certificate cert.json [--v3-src /percorso/checkout-RC84]
```
Esito atteso: `RISULTATO: OK` e il certificato `cert.json` (scritto **solo** se tutto è OK: archivio, SHA-256 del cifrato, macchina, data, run con eventi e hash di testa, impronte degli
strumenti). Il ripristino scrive solo in `--out` (rifiuta cartelle di produzione), non avvia nulla, forza `pause.flag` nella *copia*, lascia i file di `extra/` solo in `extra/` e
dichiara «NON ESEGUITO» il confronto col codice vero di RC84 se manca `--v3-src` (non è un PASS). Per rimettere in servizio una run servono solo i file durevoli, mai `transient/` né
`extra/`: operazione da autorizzare a parte.

## Annullare (rollback) la sola estensione
```sh
python3 deploy/extbackup/brain-v3/install_brain_v3_extension.py rollback            # simulazione
python3 deploy/extbackup/brain-v3/install_brain_v3_extension.py rollback --apply
```
Toglie i file installati (solo se invariati), ferma e toglie il solo timer V3 e **sposta** `/opt/superbot-extbackup-v3` in `.removed-<data>`. Gli archivi già inviati restano nel repo.
Il backup di Falco/Toro non è coinvolto in nessun passo.

## Checklist di preflight della VPS (SOLA LETTURA, da non eseguire senza autorizzazione separata)
1. `hostname; date -u; id -u` — macchina di Singapore e root. (Mai Strasburgo/HI-TV.)
2. `docker ps -a --format '{{.Names}} {{.Status}}'` e `systemctl list-units --all 'superbot-*' --no-pager` — nessun bot/servizio V3 inatteso in esecuzione.
3. `systemctl is-active superbot-extbackup.service; systemctl list-timers 'superbot-extbackup*' --no-pager; cat /opt/superbot-extbackup/status.json` — il backup di Falco/Toro è sano e non in corso.
4. `sha256sum /opt/superbot-tools/external_backup.py /opt/superbot-extbackup/run.sh` — uguali alle impronte riviste (`7cad7d8f…`, `e6dc3efc…`).
5. `ls -la /opt/superbot-v3-paper-runs/ /opt/superbot-v3-paper-runs/brain-v3-*/` — run presenti, `pause.flag`, `-wal`/`-shm`/`-journal`, nessun file inatteso.
6. `ls -l /opt/superbot-brain-free/` — `brain.sqlite3` (~469 MB), presenza di `-wal`/`-shm`; `fuser -v` sui database: nessun processo.
7. `df -h /opt` — almeno 3 GB liberi per il piano di Brain Free.
8. `age --version; git --version; python3 --version` (Python ≥ 3.8).
9. `ls -l /root/.ssh/superbot_backup_v2_ed25519` (modo 600, **non stamparla**), `grep -c '^age1' /opt/superbot-extbackup-v2/recipients.txt`, `test -s /opt/superbot-extbackup/known_hosts`.
10. Il comando `--preflight` del passo 1 dell'installazione: **solo metadati** (stat e prima pagina), nessuna apertura SQLite; per ogni database dice lo stato
    (`rollback_pulito`, `wal_pulito`, `wal_con_file_collaterali`, …), la strategia di cattura e quali processi lo tengono aperto (da `/proc`; servono i permessi di root per vederli tutti).
11. Per Brain V3: se i servizi exit-worker/runner esistono, che il proprietario delle chiusure sia uno solo (lease `.exit_service.lock` — **non** aprirlo né provarlo) e leggere solo `heartbeat.json`/`exit_heartbeat.json`.

## Limiti e gate ancora aperti
Vedi il rapporto di consegna: ripristino su macchina indipendente con la chiave vera, prima esecuzione reale e misura delle dimensioni vere, sentinella per `status.json` di V3
(quella esistente guarda solo il backup di Falco/Toro), decisione su cadenza/segmenti incrementali, copia non-git per Brain Free se necessaria, e la verifica di Python/age/git sulla VPS.
