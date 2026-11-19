# Brain Unico — Fase 0: conservazione degli storici (runbook)

Stato: **PREPARAZIONE**. Nessun passo è stato eseguito su dati o servizi reali. Strumenti collaudati solo su fixture sintetiche (49 test). Riferimento: Issue #113 (decisione del 19/11/2026 09:00), PR #114.

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
| `phase0.py` | un comando per passo, una riga GO / NO-GO |
| `sources.example.json` | spec d'esempio con i percorsi pubblici del repository, **da verificare** |

## 3. Come si protegge ciò che gira

- **SQLite**: solo `Connection.backup()` da connessione `mode=ro`, 64 pagine per volta, attesa massima 1 s sul lock (se occupato: abbandona e riprova, mai code dietro l'exit service); la copia è standalone (nessun `-wal`/`-shm`) con `integrity_check`. Mai `cp` di DB/WAL.
- **Finding verificato in laboratorio (cambia la procedura):** aprire un DB in WAL, anche `mode=ro`, **crea `-shm`/`-wal` nella directory sorgente** se non esistono e **fallisce** (`readonly_wal_needs_shm`) se `-shm` esiste ma non è scrivibile dall'utente. Regola implementata, decisa dal preflight leggendo solo i primi 100 byte:
  - DB non-WAL → `backup()`;
  - WAL **vivo** (`-shm` esiste e scrivibile) → `backup()`; se `-shm` non è scrivibile → **NO-GO `wal_shm_not_writable_by_snapshot_user`**;
  - WAL **fermo** (né `-wal` né `-shm`) → copia del file con doppia lettura, senza aprirlo;
  - `-wal` con dati e senza `-shm` → **NO-GO** (servirebbe un recovery che scrive).
- **JSONL append-only**: si legge la dimensione vista all'inizio, si taglia all'ultimo a-capo completo (la riga parziale **non** entra), poi si rilegge il prefisso della sorgente: se l'hash cambia, file sostituito o troncato → nuovo tentativo, mai "OK".
- **File piccoli**: doppia lettura, confronto hash/size/mtime/inode.
- Solo file regolari, nessun symlink, nomi sensibili (`.env`, chiavi, token…) esclusi, copie 0400 in directory 0700, destinazione fuori da qualunque repo.

## 4. Passi

Esecutore di tutti i passi: **Claude Code via Remote Control**, utente non-root `superbot-agent`. Dal Samsung serve solo scrivere in chat **`AUTORIZZO STEP n`** (nessun comando da incollare). Ogni passo termina con una riga `GO` o `NO-GO: <causa>`.

| # | Passo | Legge (reale) | Scrive | Rischio | Consenso |
|---|---|---|---|---|---|
| 1 | **Discovery non privilegiata**: processi, unità systemd, metadati dei percorsi, impronta del codice vs commit | elenco processi (argomenti redatti), proprietà unità (senza Environment), `lstat` dei percorsi. **Nessun file di dati/journal/DB aperto** | `reports/step1_*.json` (0600) | minimo | **sì, separato** |
| 2 | **Preflight**: leggibilità, spazio, sonda WAL (100 byte di intestazione per DB) | `lstat` + intestazione dei DB | niente | minimo | sì |
| 3 | **Snapshot** per file (§3) | contenuto delle sorgenti, in sola lettura | `snapshot/` + log | basso (I/O, lock di lettura brevi) | **sì, esplicito, con spazio verificato** |
| 4 | **Manifest sulla copia** (`--include-db --sqlite`) | solo la copia | `reports/step4_*` | nullo | no (dopo step 3) |
| 5 | **Ripristino su directory vuota + audit** | solo la copia | `restore/`, `reports/step5_*` | nullo | no (dopo step 3) |
| 6 | Relazione: esito, buchi, decisioni (backup esterno cifrato, uso di Falco/Toro/Arena) | — | Issue/PR (solo numeri) | nullo | — |

Rollback: tutto ciò che i passi producono sta in una directory di laboratorio; annullare = eliminarla. Le sorgenti non sono mai modificate (test: stato dell'albero sorgente identico prima/dopo).

## 5. GO / NO-GO

- **Step 1 GO** se i processi e le unità sono elencati; ciò che non è leggibile (container Docker, directory di altri utenti) è riportato come `non_readable`, **mai aggirato**. Un percorso `non_readable` diventa una decisione per l'utente (§7).
- **Step 2 GO** se: tutte le sorgenti leggibili; destinazione nuova e fuori dalle sorgenti e da repo git; spazio libero ≥ 2 × totale + 512 MB; nessun DB WAL con `-shm` non scrivibile o `-wal` orfano.
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

`python3 ops/brain-unico/phase0/test_phase0.py` (49 test) e `python3 ops/brain-unico/test_inventory.py` (29 test), tutti PASS. Includono: scrittori concorrenti reali su DB WAL e su JSONL, DB bloccato in esclusiva (abbandono senza attesa), file riscritto/sostituito durante la copia, preflight (spazio, overlap, symlink, permessi), audit su manomissioni (payload alterato, evento cancellato, file mancante/extra, SQLite corrotto, troncamento di coda con ancora), redazione degli argomenti dei processi, assenza di aperture di `environ`/file di dati nella discovery, comandi non in lista rifiutati, e il confronto del verificatore di catena con la **vera** `EventJournal` della PR #112 (stesso count e head, manomissione rilevata da entrambi).
