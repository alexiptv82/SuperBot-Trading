# Brain Unico — Fase 0: conservazione degli storici (runbook)

Stato: **PREPARAZIONE**. Nessun passo è stato eseguito su dati o servizi reali. Strumenti collaudati solo su fixture sintetiche (85 + 29 test; correzioni della revisione PR #115 in §10). Riferimento: Issue #113 (decisione del 19/11/2026 09:00), PR #114.

## 1. Obiettivo e perimetro

Ottenere, per ogni storico (Falco, Toro, Brain storico, Arena DeepSeek/Qwen/MiniMax): (a) il commit che gira davvero; (b) una **copia consistente per file** in una directory di laboratorio; (c) un manifest SHA256 **sulla copia**; (d) un ripristino provato su directory vuota con audit di quadratura.

**Mai**: scrivere o bloccare le sorgenti, fermare/avviare servizi, usare sudo/root/gruppo docker, leggere env/segreti, unire o ricostruire journal, mettere manifest o percorsi nel repository. L'Arena e l'exit service non vengono interrotti.

## 2. Strumenti (`ops/brain-unico/phase0/`)

| Strumento | Funzione |
|---|---|
| `discover.py` | processi, unità `superbot-*`, metadati dei percorsi (solo `lstat`), impronta del codice vs commit del clone |
| `snapshot.py` | preflight + copia consistente per file, log privato `snapshot_log.json` |
| `audit.py` | ripristino su directory vuota + audit (hash, integrità SQLite, catena `v3_events` ricalcolata, conteggi) |
| `../inventory.py` | manifest SHA256 **sulla copia** (PR #114) |
| `phase0.py` | un comando per passo, una riga GO / NO-GO; la directory di lavoro deve essere **nuova** (mai `chmod` o scritture su directory esistenti, nessun symlink) |
| `sources.example.json` | spec d'esempio con i percorsi pubblici del repository, **da verificare** |

## 3. Come si protegge ciò che gira

- **SQLite**: solo `Connection.backup()` da connessione `mode=ro`, 64 pagine per volta, attesa massima 1 s sul lock (se occupato: abbandona e riprova, mai code dietro l'exit service); la copia è standalone (nessun `-wal`/`-shm`) con `integrity_check`. Mai `cp` di DB/WAL.
- **Finding verificato in laboratorio (cambia la procedura):** aprire un DB in WAL, anche `mode=ro`, **crea `-shm`/`-wal` nella directory sorgente** se non esistono e **fallisce** (`readonly_wal_needs_shm`) se `-shm` esiste ma non è scrivibile dall'utente. Regola implementata, decisa dal preflight leggendo solo i primi 100 byte:
  - DB non-WAL → `backup()`;
  - WAL **vivo** (`-shm` esiste e scrivibile) → `backup()`; se `-shm` non è scrivibile → **NO-GO `wal_shm_not_writable_by_snapshot_user`**;
  - WAL senza `-wal`/`-shm` → **NO-GO `wal_quiescence_unproven`**, perché l'assenza dei sidecar **non prova** che nessuno stia scrivendo (un servizio può aprire il DB un istante dopo). Si procede solo con `quiescence_evidence` nella spec (riferimento a una prova esterna, es. unità verificata inattiva nello step 1): allora si copia il file senza aprirlo, con doppia lettura, e se durante la copia compare un sidecar l'esito è `wal_sidecar_appeared_during_copy` e la copia viene scartata. Due hash uguali non bastano come prova;
  - `-wal` con dati e senza `-shm` → **NO-GO** (servirebbe un recovery che scrive).
- **Vincolo esatto "nessuna scrittura sulla sorgente":** nessun byte dei file di dati (DB, `-wal`, JSONL, file) viene scritto. Con un DB WAL vivo, SQLite in lettura può però aggiornare il **wal-index in `-shm`** (memoria condivisa volatile, mai dato durevole) e per questo richiede che `-shm` sia scrivibile; se non lo è, si ferma con NO-GO invece di aggirare. Il preflight non apre mai SQLite sulla sorgente.
- **JSONL append-only**: si legge la dimensione vista all'inizio, si taglia all'ultimo a-capo completo (la riga parziale **non** entra), poi si rilegge il prefisso della sorgente: se l'hash cambia, file sostituito o troncato → nuovo tentativo, mai "OK".
- **File piccoli**: doppia lettura, confronto hash/size/mtime/inode.
- Solo file regolari, nessun symlink, nomi sensibili (`.env`, chiavi, token…) esclusi, copie 0400 in directory 0700, destinazione fuori da qualunque repo.

## 4. Passi

Esecutore di tutti i passi: **Claude Code via Remote Control**, utente non-root `superbot-agent`. Dal Samsung serve solo scrivere in chat **`AUTORIZZO STEP n`** (nessun comando da incollare). Ogni passo termina con una riga `GO` o `NO-GO: <causa>`.

| # | Passo | Legge (reale) | Scrive | Rischio | Consenso |
|---|---|---|---|---|---|
| 1 | **Discovery non privilegiata**: processi, unità systemd, metadati dei percorsi, impronta del codice vs commit | elenco processi (argomenti redatti), proprietà unità (senza Environment), `lstat` dei percorsi; per `codefp` **legge i soli file `.py`** della directory di codice indicata. **Nessun file di dati/journal/DB aperto** | `reports/step1_*.json` (0600) | minimo | **sì, separato** |
| 2 | **Preflight**: leggibilità, spazio, sonda WAL (100 byte di intestazione per DB) | `lstat` + intestazione dei DB | niente | minimo | sì |
| 3 | **Snapshot** per file (§3) | contenuto delle sorgenti, in sola lettura | `snapshot/` + log | basso (I/O, lock di lettura brevi) | **sì, esplicito, con spazio verificato** |
| 4 | **Manifest sulla copia** (`--include-db --sqlite`) | solo la copia | `reports/step4_*` | nullo | no (dopo step 3) |
| 5 | **Ripristino su directory vuota + audit** | solo la copia | `restore/`, `reports/step5_*` | nullo | no (dopo step 3) |
| 6 | Relazione: esito, buchi, decisioni (backup esterno cifrato, uso di Falco/Toro/Arena) | — | Issue/PR (solo numeri) | nullo | — |

Rollback: tutto ciò che i passi producono sta in una directory di laboratorio; annullare = eliminarla. Le sorgenti non sono mai modificate (test: stato dell'albero sorgente identico prima/dopo).

## 5. GO / NO-GO

- **Step 1 GO** solo se processi e unità sono **leggibili**; se `ps` o `systemctl` non rispondono, o un `show` fallisce, l'esito è **NO-GO (INCOMPLETO)** (il report privato viene comunque scritto). L'assenza di unità `superbot-*` è legittima e viene solo annotata (`no_matching_units`). Ciò che non è leggibile (container Docker, directory di altri utenti) è riportato come `non_readable`, **mai aggirato**: un percorso `non_readable` diventa una decisione per l'utente (§7). `codefp` è NO-GO se non produce impronte o se un riferimento non è risolvibile.
- **Step 2 GO** se: tutte le sorgenti leggibili; **almeno un item** e **ogni sorgente non opzionale produce almeno un item**; **ogni gruppo di `required_groups`** (Falco, Toro, Brain storico, ciascuna Arena) è coperto; radici `tree` non symlink; destinazione **nuova** (mai una directory esistente, neanche vuota), senza symlink nel percorso, fuori dalle sorgenti e da repo git; spazio libero ≥ 2 × totale + 512 MB; nessun DB WAL con `-shm` non scrivibile, `-wal` orfano o quiescenza non provata. Il resoconto separa i file scartati per sorgente (nomi sensibili, sidecar, symlink, speciali).
- **Step 3 GO** solo se step 2 è GO **e** c'è `--auth-ref` (riferimento al tuo consenso). Il successo richiede tutti gli item `OK`; un item `FAILED` rende NO-GO l'intero snapshot (si ripete quell'item, mai si dichiara completo).
- **Step 5 PASS/WARN/FAIL**: FAIL se manca/avanza un file, hash diverso, `integrity_check` ≠ ok, conteggi diversi dal log, catena `v3_events` rotta o ancora esterna non coincidente. WARN per tentativi ripetuti, riga parziale esclusa, finestra di cattura > 15 min, catena senza ancora esterna.

## 6. Limiti dichiarati

- **Non è uno snapshot atomico fra fonti**: ogni file è coerente al proprio istante; il log riporta `captured_at_ms` e la finestra. Con la gara Arena attiva lo snapshot è una fotografia intermedia; quella **definitiva** si fa dopo lo stop delle nuove aperture (21/11/2026 18:03:12) e la chiusura delle posizioni, previo nuovo consenso.
- La catena di hash rileva manomissioni e troncamenti **interni**, non il troncamento di coda: servono count/head attesi da un riscontro **indipendente** (`--expect-v3`).
- La copia in laboratorio sta sullo **stesso host**: non sostituisce il backup esterno cifrato, che resta da installare/attestare con consenso separato.
- Il mapping commit↔runtime confronta i soli `.py` per blob SHA1 con i commit **presenti nel clone**: un deploy da un commit non scaricato appare come "nessuna corrispondenza esatta".
- Fixture sintetiche: non provano l'idoneità sui filesystem e sui permessi reali; per questo lo step 1–2 precede qualunque lettura di dati.

## 7. Decisioni che potrebbero servire dopo lo step 1–2

1. Se le sorgenti non sono leggibili da `superbot-agent`: (A) tu concedi una lettura mirata e reversibile (richiede un intervento privilegiato **non autorizzato ora**), oppure (B) lo snapshot lo esegue l'utente proprietario dei dati con un solo comando (lo preparo), oppure (C) si resta alla sola discovery.
2. Se un DB WAL vivo ha `-shm` non scrivibile da noi: stessa scelta (A/B/C); non si usa mai `immutable=1` su un DB vivo (leggerebbe il solo file principale, incoerente).
3. Dove conservare il backup esterno cifrato (fuori host) e chi custodisce la chiave.

## 8. Primo passaggio proposto

**Step 1 — discovery non privilegiata** (§4). Rischio minimo: nessun contenuto di dati, nessun file di ambiente, nessuna scrittura sulle sorgenti, nessun servizio toccato. Produce: stato reale di processi/unità, commit che corrisponde al codice in esecuzione, e quali percorsi sono leggibili. Da lì dipende il percorso (A/B/C) per lo snapshot.

## 9. Verifica degli strumenti

`python3 ops/brain-unico/phase0/test_phase0.py` (85 test) e `python3 ops/brain-unico/test_inventory.py` (29 test), tutti PASS. Includono: scrittori concorrenti reali su DB WAL e su JSONL, DB bloccato in esclusiva (abbandono senza attesa), file riscritto/sostituito durante la copia, preflight (spazio, overlap, symlink, permessi), audit su manomissioni (payload alterato, evento cancellato, file mancante/extra, SQLite corrotto, troncamento di coda con ancora), redazione degli argomenti dei processi, assenza di aperture di `environ`/file di dati nella discovery, comandi non in lista rifiutati, e il confronto del verificatore di catena con la **vera** `EventJournal` della PR #112 (stesso count e head, manomissione rilevata da entrambi).

## 10. Correzioni dalla revisione della PR #115 (commento del 19/11/2026 09:31)

| Rilievo | Difetto | Correzione | Test |
|---|---|---|---|
| P0-A | `prepare()` faceva `chmod` su directory preesistenti, anche tramite symlink; lo stesso valeva per destinazione dello snapshot e directory di ripristino | `safe_new_dir()`: solo directory **nuove** (0700 per costruzione, nessun `chmod`), genitore esistente e senza symlink; una directory di lavoro preesistente è accettata solo con marcatore `.phase0-workdir`, stesso utente, non symlink; i sotto-livelli si creano uno a uno con 0700. Trovato in più: un `id` `..` nella spec avrebbe fatto uscire le copie dalla destinazione → rifiutato (anche per gruppo e percorso senza nome file) | `P0A_DirectorySafety` (12) |
| P0-B | la discovery stampava `GO` con `ps` o systemd non disponibili; la redazione degli argomenti lasciava passare querystring in percorsi, valori incollati alle opzioni corte (`-psecret`) e token puntati | `completeness` (NO-GO INCOMPLETO con causa, `no_matching_units` solo annotata, codice di uscita 1 con report scritto); redazione: URL, `?`/`#`/`;`/`=` nei percorsi, segmenti lunghi, opzioni corte → `-p<arg>`, modulo solo dopo `-m` | `P0B_DiscoveryCompleteness` (9) |
| P0-C | con zero item, `all([])` dava successo; un `tree` vuoto, di soli symlink o escluso passava | NO-GO `no_items`, `source_yields_no_items`, `required_group_without_items`; `required_groups` **obbligatorio** nella spec; `optional` esplicito; radice `tree` symlink/file → NO-GO; esito finale richiede `results` non vuoto e uguale agli item; resoconto per sorgente | `P0C_RosterCompleteness` (8) |
| P0-D | l'assenza di `-wal`/`-shm` non prova la quiescenza | `wal_quiescence_unproven` senza `quiescence_evidence`; con evidenza, controllo che nessun sidecar compaia durante la copia; vincolo "nessuna scrittura" documentato con precisione (§3) | `P0D_WalQuiescence` (5) |
| P1 | `GO` anche con verdetto WARN | `certifies_backup=false` e `certification_blockers` (`same_host_copy`, `capture_not_atomic_across_sources`, `no_external_anchor`) in report, riepilogo e riga di uscita; schema delle fonti con i sei gruppi espliciti | `P1_AuditDoesNotCertify` (2) |

Ogni correzione è stata verificata anche per mutazione: reintroducendo il difetto in una copia di scratch, almeno un test nuovo fallisce (17 mutazioni su 17 rilevate).
