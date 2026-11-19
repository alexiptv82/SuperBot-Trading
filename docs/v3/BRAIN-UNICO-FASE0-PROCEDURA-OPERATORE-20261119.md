# Brain Unico — Fase 0, opzione B: procedura dell'operatore (bundle sigillato)

Stato: **PREPARAZIONE, non eseguita**. Nessun comando privilegiato è stato lanciato; nessun dato o servizio reale è stato toccato. Strumenti collaudati solo su fixture sintetiche. Riferimenti: Issue #113 (decisione opzione B, 19/11/2026), PR #115 (strumenti di Fase 0).

## 1. Che cosa si ottiene

Una **copia consistente per file** degli storici (Falco, Toro, Brain storico, tre Arena) in una directory **privata di root**, con manifest SHA256, ripristino provato su directory vuota e audit di quadratura, **senza fermare alcun servizio** e **senza concedere accesso permanente** a `superbot-agent`. L'agente legge solo un riepilogo pubblico con numeri e codici.

Due comandi, ciascuno una riga incollabile dal Samsung:

| | Comando | Quando | Cosa fa |
|---|---|---|---|
| **A** | `preflight` | dopo il tuo consenso (anche subito: sola lettura) | metadati, spazio, permessi, fonti, stato WAL, quiescenza, stato dei servizi. **Nessuna copia** |
| **B** | `full` | **dopo la fine dell'Arena** (stop 21/11/2026 18:03:12, posizioni chiuse) e nuovo consenso | preflight + snapshot + manifest + ripristino + audit |

## 2. Requisiti → meccanismo → test

| # | Requisito | Meccanismo | Test |
|---|---|---|---|
| 1 | Solo codice revisionato e fissato per hash | un **unico file** `phase0_sealed.py` generato in modo deterministico dai moduli revisionati (`build_sealed.py --check` fallisce se non coincide); l'operatore lo scarica da un **commit fissato** e ne verifica lo `sha256` (comunicato fuori da GitHub, nel messaggio); il bundle ricontrolla il proprio hash (`--expect-sha256`) | `BundleIntegrity`, `CodeTrust` |
| 2 | Nessuno script modificabile da `superbot-agent` eseguito come root | il file vive in una directory **creata da root** (`mktemp -d` in `/root`, 0700); all'avvio il bundle rifiuta di girare se il file o un antenato non è di root, è scrivibile da gruppo/altri o è un symlink; `python3 -I` ignora ambiente e directory corrente; **nessun input dall'agente**: la spec delle fonti è incorporata nel bundle (coperta dall'hash) | `CodeTrust`, `test_privileged_commands_refuse_non_root…` |
| 3 | Preflight di spazio, permessi, fonti, WAL | spazio ≥ 2 × totale + riserva e tetto assoluto (10 GB, `--max-total-gb`); ogni sorgente non opzionale deve esistere, ogni gruppo (Falco, Toro, Brain storico, tre Arena) deve avere **file di dati** (sqlite/jsonl) e non solo codice; antenati dei percorsi di root e non scrivibili da altri; sonda WAL sulla sola intestazione; **quiescenza verificata a runtime** (§4) | `ExecuteFull.*`, `SealedSupportFeatures` |
| 4 | Copie coerenti senza fermare i servizi | SQLite solo con `Connection.backup()` in sola lettura a passi di 64 pagine con attesa massima di 1 s sul lock (se occupato: abbandona e riprova); JSONL tagliato all'ultimo a-capo e verificato; priorità `nice 19` + `ionice` classe idle; **stato dei servizi letto prima e dopo** (`systemctl list-units/show`, nient'altro) e dichiarato in `services.unchanged`; nessuno stop/restart/start possibile (comandi ammessi: solo `list-units` e `show`) | `test_default_runner_allows_only…`, `test_services_drift…` |
| 5 | Originali privati, ripristino verificabile | tutto ciò che contiene dati sta in `private/` (0700 root); `public/` (0755) ha solo numeri, codici e hash, **mai percorsi, ID o contenuti** (verificato da un test che cerca percorsi e nomi nel testo); restore su directory vuota + audit, poi la copia di prova viene rimossa | `test_public_area_contains_no_paths…`, `AuditRestore` |
| 6 | Copia esterna cifrata come fase successiva | §7; `certifies_backup` è **sempre false** e il blocco `external_encrypted_copy_not_done` è sempre dichiarato | `test_full_run_success…` |
| 7 | Minimo intervento dal Samsung | una riga per passo; nessun file da creare, nessuna modifica di permessi, nessun comando intermedio | — |

Ogni controllo di sicurezza è stato verificato anche per **mutazione**: reintroducendo il difetto in una copia di scratch (con bundle ricostruito), almeno un test fallisce. Risultato: **28 mutazioni su 28 rilevate** (catena di fiducia, hash del codice, whitelist dei comandi, quiescenza, percorsi, permessi di `private/`, assenza di percorsi nell'area pubblica, consenso per il passo B, rimozione del ripristino, confronto dei servizi, esclusioni, dati obbligatori, tetto).

## 3. Modello di minaccia

Il bundle protegge da: codice sostituito o alterato tra revisione ed esecuzione; esecuzione come root di file scrivibili dall'agente; percorsi sorgente reindirizzati con symlink/rinomine da chi controlla una directory; fuga di percorsi o contenuti verso l'area leggibile dall'agente; copie "riuscite" ma vuote o parziali; scritture accidentali sulle sorgenti.

**Non** protegge da: un operatore o un account root compromessi; un canale di verifica dell'hash compromesso (per questo l'hash va confrontato con il messaggio ricevuto in questa conversazione, non con GitHub); un `curl` verso un host sbagliato prima del controllo dell'hash (il controllo avviene **prima** dell'esecuzione). La spec incorporata riporta percorsi **non verificati** (dal repository pubblico): se un percorso reale è diverso, il preflight dà NO-GO e va rigenerato un nuovo bundle con un nuovo hash.

## 4. Quiescenza dei DB WAL: provata a runtime, non dichiarata

L'assenza di `-wal`/`-shm` non prova che nessuno scriva. Per i DB in WAL senza sidecar il bundle richiede, per la sorgente interessata, che (a) le unità dichiarate nella spec risultino **non attive** secondo systemd e (b) **nessun processo** abbia aperto un DB (o i suoi sidecar) sotto quella sorgente (scansione di `/proc/*/fd` come root). Se systemd non risponde, o un'unità è attiva, o un file è aperto → `wal_quiescence_unproven` → NO-GO per quella sorgente. Le sorgenti con servizi attivi (Arena, uscita Brain) **non** dichiarano quiescenza: i loro DB si copiano solo con `backup()` (DB vivo con `-shm` scrivibile, ora garantito perché eseguito come root) o, se non in WAL, direttamente. Se compare un sidecar durante una copia di file, la copia è scartata.

**Vincolo esatto sulle scritture:** nessun byte dei dati sorgente (DB, `-wal`, JSONL, file) viene scritto. Leggere un DB WAL vivo può però aggiornare il **wal-index in `-shm`** (volatile, mai dato durevole). L'esecuzione come root rende `-shm` scrivibile; non si usa mai `immutable=1` su DB vivi.

## 5. Procedura

### Passo A — preflight (sola lettura)

L'operatore incolla una sola riga. I segnaposto `<COMMIT>` e `<SHA256>` sono quelli comunicati nel messaggio della conversazione:

```
sudo sh -c 'set -e; D=$(mktemp -d /root/sp0.XXXXXX); cd "$D"; curl -fsSL -o phase0_sealed.py "https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/<COMMIT>/ops/brain-unico/sealed/phase0_sealed.py"; echo "<SHA256>  phase0_sealed.py" | sha256sum -c -; chmod 0400 phase0_sealed.py; IO=""; command -v ionice >/dev/null && IO="ionice -c3"; nice -n19 $IO python3 -I phase0_sealed.py preflight --expect-sha256 <SHA256>'
```

Se si è già root, si omette `sudo`. Se `sha256sum -c` fallisce, **nulla viene eseguito** (`set -e`). Esito: una riga `PREFLIGHT_GO` o `NO-GO` e il file `/var/lib/superbot-phase0/<run>/public/summary.json`, che l'agente può leggere. Nessuna copia.

### Passo B — snapshot completo (solo dopo nuovo consenso e fine Arena)

Stessa riga, con `full` al posto di `preflight` e `--auth-ref <RIFERIMENTO>` (un token senza spazi che identifica il tuo consenso, per esempio `ISSUE113-STEP3-20261121`). Il bundle rifà il preflight e **si ferma se non è GO**; copia solo se tutto è GO.

### Dopo l'esecuzione

L'agente legge `public/summary.json`, `manifest_summary.json`, `audit_summary.json` e riferisce un riepilogo sanitizzato. La directory `private/` resta illeggibile all'agente. Se in futuro si vorrà far analizzare all'agente le **copie** (non gli originali), basterà una decisione separata, per esempio un'ACL di sola lettura su `private/snapshot`.

### Se è NO-GO

Il riepilogo elenca i codici (per esempio `source_missing`, `required_group_without_data_files`, `wal_quiescence_unproven`, `source_path_not_root_controlled`, `insufficient_space`). Nessuna copia è stata fatta. Si corregge la causa o si rigenera il bundle con una spec diversa (nuovo hash, nuova revisione).

## 6. Impatto sui servizi di trading

- Nessuno stop, start o restart. Il bundle può eseguire **solo** `systemctl list-units` e `systemctl show`.
- Carico: lettura sequenziale a bassa priorità; l'Arena ha journal piccoli. I DB in rollback-journal tengono un lock di lettura per pochi millisecondi a passo; chi scrive attende (i writer del journal V3 hanno 10 s di timeout). I DB in WAL non bloccano i writer.
- Verificabile: `summary.json → services` riporta stato, PID e `NRestarts` di ogni unità `superbot-*` prima e dopo; `unchanged=false` evidenzia qualsiasi differenza (anche non causata dallo snapshot).
- Il passo B va eseguito **dopo** la fine dell'Arena per non toccare la gara e perché gli storici siano stabili; il passo A può precedere.

## 7. Rischio extbackup e copia esterna cifrata (fase successiva, non attivata)

**Rischio:** `superbot-extbackup.service` risulta `inactive/dead`. Non distingue un servizio a timer mai eseguito da uno spento, e nessun backup esterno risulta attestato. Finché non c'è una copia **fuori host**, la copia locale di questa procedura protegge da errori logici e da corruzione, **non** dalla perdita del disco o dell'host. Non lo attivo né lo modifico: serve una decisione separata.

**Progetto della fase successiva** (nulla di questo è implementato nel bundle):
1. Impacchettare `private/snapshot` in un archivio deterministico (ordine, mtime e proprietari normalizzati) e registrarne lo SHA256.
2. Cifrare con `age` verso una **chiave pubblica dell'utente**; la chiave privata non è mai sulla VPS.
3. Portare il file cifrato fuori host (PC/Samsung o storage esterno) e registrare **fuori host** lo SHA256 del cifrato, il `manifest_digest` e le **ancore** (conteggio e testa di ogni catena `v3_events`, già calcolati in `private/reports/anchors.json`, riassunti in `anchors_digest`).
4. Prova di ripristino indipendente: decifrare, verificare gli hash, rieseguire l'audit con le ancore esterne (`--expect-v3`): solo allora `PASS` può diventare una certificazione.
Serve da te: la chiave pubblica `age`, la destinazione e chi custodisce la privata.

## 8. Limiti dichiarati

- Snapshot **non atomico fra fonti**: ogni file è coerente al proprio istante; il log riporta la finestra.
- La catena di hash non rileva da sola il troncamento di coda: servono le ancore fuori host.
- Stesso host: non è un backup.
- I test sintetici non provano il comportamento sui permessi e sui filesystem reali; il preflight esiste per questo.
- `source_path_not_root_controlled`: se un antenato di una sorgente non è di root o è scrivibile da altri, il bundle non legge (fail closed).

## 9. Verifica indipendente

```
python3 ops/brain-unico/sealed/build_sealed.py --check      # il bundle committato coincide con i sorgenti
sha256sum ops/brain-unico/sealed/phase0_sealed.py            # = <SHA256> del messaggio
python3 -I ops/brain-unico/sealed/phase0_sealed.py selftest  # versioni e hash dei moduli, senza privilegi né dati
python3 ops/brain-unico/sealed/test_sealed.py                # 76 test sintetici
python3 ops/brain-unico/phase0/test_risk_audit.py            # 24 test sintetici
python3 ops/brain-unico/phase0/test_phase0.py                # 90 test sintetici
python3 ops/brain-unico/test_inventory.py                    # 29 test sintetici
```

Il bundle è un file di testo: i moduli incorporati compaiono come commenti `#|`, leggibili in review; `selftest` stampa lo SHA256 di ciascun modulo, confrontabile con i file del repository.

## 10. Comandi aggiunti dopo la decisione "Brain Unico prioritario" (19/11/2026, 10:20) e corretti dopo la revisione della PR #117

Stesso bundle, stessa riga di avvio, stessi controlli di fiducia. Dettagli, GO/NO-GO e valutazione del rischio MiniMax in `BRAIN-UNICO-ARENA-FINALIZZAZIONE-ANTICIPATA-20261119.md`.

| Comando | Effetto | Consenso |
|---|---|---|
| `status-services` | **solo systemd**: nessun database, nessun file di dati. Esito `SERVICES_OK` (exit 0) oppure `INCOMPLETE` (exit 1) | operatore |
| `full --groups arena_minimax` | copia del solo gruppo indicato (azione autorizzata a parte) + **audit dei limiti** dalle copie, solo numeri; posizioni aperte, età e ritardi di uscita vengono **da qui** | operatore |
| `full … --ended-early-reason TOKEN` | registra motivo e durata effettiva rispetto alle 72 ore | operatore |
| `stop-openings --checkpoint-run <run_id> --providers … --ended-early-reason TOKEN --auth-ref … --confirm-stop-runners` | ferma **solo** i runner indicati; richiede un **checkpoint coerente PRE-stop recente e completo** (un `full` valido di tutti i provider selezionati); le uscite restano attive; idempotente | **consenso operativo esplicito** |

Il vecchio comando `status` (che apriva i journal) **non esiste più**: leggere un DB in WAL può aggiornare o creare `-shm`, quindi nessun comando eseguito come root lo fa senza un'azione autorizzata a parte.

**`--auth-ref` non è un'autorizzazione né un'autenticazione:** è soltanto un riferimento per la tracciabilità. Il consenso è quello esplicito dell'utente nella conversazione; il bundle non può verificarlo.

**Verifica indipendente dell'hash.** Calcolarlo sui byte del commit pubblicato, non sul file scaricato da altre fonti: `git show <commit>:ops/brain-unico/sealed/phase0_sealed.py | sha256sum`. Dopo qualunque patch l'hash cambia: un hash vecchio non vale per il bundle nuovo.
