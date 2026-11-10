# Migrazione dei backup cifrati age V1 → V2 (e chiave personale)

**Stato: PREPARATA E PROVATA SOLO OFFLINE.** Nessun job con Secrets è stato avviato, la VPS non è stata toccata, il destinatario di produzione
(`/opt/superbot-extbackup/recipient.txt`, V1) e il backup V1 di Falco/Toro non sono stati modificati. Si procede solo dopo revisione di ChatGPT e OK esplicito dell'utente.

## 1. I fatti e che cosa implicano
* Verificato dall'utente sulla VPS: **gli ultimi archivi (Falco/Toro, Brain V3, Brain Free) sono cifrati per V1**; la chiave privata V1 non è disponibile; il Secret
  `SUPERBOT_AGE_RECOVERY_KEY_V2` appartiene a un'altra coppia; i dati originali sono sulla VPS; gli archivi V1 vanno conservati.
* age è cifratura a chiave pubblica: un archivio V1 si apre **solo** con la privata V1. Né la V2 né una chiave personale lo aprono e non esistono porte di servizio.
  Quindi i dati NON si «migrano» ricifrando gli archivi V1: si fanno **backup nuovi dei dati originali** verso i nuovi destinatari. Gli archivi V1 restano dove sono,
  intatti, apribili se mai si ritrova la V1.
* Finché il primo backup V2 non è fatto e ripristinato, i dati storici esistono solo sulla VPS (e negli archivi V1 non apribili): **il primo backup V2 è urgente**.

## 2. Esistono copie recuperabili della chiave V1? (indagine, senza leggere nulla di segreto)
Verificato nel repository (solo nomi, mai valori):
* nessun workflow su nessun ramo cita un Secret con una chiave V1 (i soli Secrets «age» sono `SUPERBOT_AGE_RECOVERY_KEY_V2` e `SUPERBOT_BACKUPS_READ_KEY`, quest'ultimo mai creato);
* nessuna chiave privata age in chiaro nella cronologia git di nessun ramo (0 corrispondenze);
* il diario del 19/10 dice che la V1 fu generata nella sessione di Claude, **mostrata all'utente in chat**, salvata dall'utente alle 14:09; la copia di Claude fu cancellata;
  non è sul server e non è in nessun repository.
**Dove può ancora esistere (solo il proprietario può controllare):** (1) la cronologia della conversazione Claude/ChatGPT del 19/10 e i file del Project; (2) il file salvato quel
giorno sul PC o sul telefono, nel gestore di password, nelle note, in cloud, nelle e-mail inviate a se stessi, nei backup dei dispositivi (Time Machine, iCloud, Google Drive);
(3) un Secret di GitHub con altro nome (l'elenco dei nomi è visibile solo dall'interfaccia). Ricerca che stampa solo nomi di file, non contenuti:
`grep -rIl "AGE-SECRET-KEY-1" <cartella>` (sul PC), e per riconoscerla senza leggerla: `age-keygen -y FILE | cut -c1-12` deve dare `age142uj5c8x`.
**Se la ritrovi:** non incollarla in nessuna chat. Va comunque considerata *esposta* (è passata dalla chat): serve la migrazione V2 in ogni caso; con la V1 si potranno anche
riaprire gli archivi vecchi sul tuo PC (`restore_external_backup.py`, `restore_brain_v3_backup.py`) ed eventualmente ricifrarli.

## 3. Architettura della migrazione (additiva: nulla di V1 viene toccato)
| | V1 (resta com'è) | V2 (nuovo) |
|---|---|---|
| Repository privato | `superbot-backups` | `superbot-backups-v2` (nuovo, vuoto) |
| Destinatari | `deploy/extbackup/recipient.txt` (V1) | `deploy/extbackup/recipient-v2.txt` (V2, documentato il 23/10; + chiave personale, §6) |
| File sul server | `/opt/superbot-extbackup/{recipient.txt,run.sh,work}` | `/opt/superbot-extbackup-v2/{recipients.txt,run-classic.sh,work}`, `/opt/superbot-extbackup-v3/run-v3.sh` |
| Chiave di deploy | `/root/.ssh/superbot_backup_ed25519` | `/root/.ssh/superbot_backup_v2_ed25519` (nuova, scrittura solo su `superbot-backups-v2`) |
| Codice | `external_backup.py` (invariato, impronta fissata) | lo stesso, tramite `external_backup_multi.py` (destinatari multipli + impronta); `external_backup_brain_v3.py` per Brain V3/Brain Free |
| Timer | `superbot-extbackup.timer` 03:20 UTC | `superbot-extbackup-v2.timer` 03:35, `superbot-extbackup-v3.timer` 03:50; senza `Persistent=true`, solo dopo la prova |
Coerenza garantita da **un'impronta unica dei destinatari** (sha256 delle chiavi ordinate) scritta in ogni wrapper: se il file `recipients.txt` sul server cambia (chiave sostituita,
aggiunta o tolta senza revisione) i programmi **rifiutano di cifrare** (`recipient_mismatch`) invece di produrre archivi che nessuno sa aprire. `check_recipient_consistency.py`
controlla nel repository che wrapper, unità, script e file dei destinatari usino la stessa impronta e nessun riferimento V1 (`--installed` lo ripete sui file installati sulla VPS, in sola
lettura); l'installatore lo esegue come precondizione e non sovrascrive mai un file esistente diverso. Il raggio d'azione dei nuovi script è limitato a `/opt/superbot-extbackup-v2` e
`/opt/superbot-extbackup-v3`; del V1 si legge soltanto `known_hosts` (chiavi pubbliche di GitHub).
Gli archivi V1 non possono essere «sovrascritti» né cancellati da questo lavoro: il repository V1 non viene nemmeno contattato (prova automatica: rami, oggetti e alberi V1 identici prima e dopo).

## 4. Procedura operativa minima (ogni passo dopo OK esplicito)
**A. Chiave personale prima di installare (PC del proprietario, ~15 minuti).** Così non servono aggiornamenti sul server. Creare la chiave come in §6, poi nel repository:
`python3 deploy/extbackup/v2/set_recipients.py --add age1…` (aggiunge la pubblica, riallinea l'impronta nei wrapper, verifica la coerenza), commit, revisione, nuova impronta di approvazione.
**B. Interfaccia GitHub.** (1) Creare il repository **privato vuoto** `alexiptv82/superbot-backups-v2`; attivare le regole che vietano force push e cancellazione dei rami `main`, `brain-v3`,
`brain-free`. (2) Deploy key **in scrittura** per la VPS (si genera al passo D). (3) Deploy key **in sola lettura** per le Actions: `ssh-keygen -t ed25519 -N '' -f lettura-v2` sul PC,
la `.pub` in Deploy keys di `superbot-backups-v2` senza «Allow write access», la privata nel Secret `SUPERBOT_BACKUPS_READ_KEY`, poi cancellare il file locale. (4) Ambiente protetto
`age-recovery` (revisore obbligatorio, rami consentiti).
**C. La chiave V2 è valida?** Avvio protetto del workflow `age-v2-key-check` (impronta di approvazione, vedi `age-v2-recovery/LEGGIMI.md`). Atteso `ESITO COMPLESSIVO: OK`. Se `NO`:
la V2 del Secret non è quella documentata: non usarla; basta la chiave personale (§6) come unico destinatario, e il workflow di ripristino non servirà (si ripristina sul PC).
**D. VPS (Termius, root), sola lettura prima.** Clone del commit approvato e controllo `git rev-parse HEAD`. `python3 -I deploy/extbackup/v2/check_recipient_consistency.py` (repository) e con
`--installed` (server). Creare la chiave di deploy V2 `ssh-keygen -q -t ed25519 -N '' -C superbot-backup-v2-vps -f /root/.ssh/superbot_backup_v2_ed25519` (non stampare la privata), aggiungere la
`.pub` come deploy key in scrittura di `superbot-backups-v2`. Poi, per ciascun profilo: `python3 deploy/extbackup/brain-v3/install_brain_v3_extension.py --profile classic install` (simulazione, stampa
l'impronta di approvazione), `… --profile classic install --apply --approve <IMPRONTA>`; stessa cosa con `--profile v3`. Nessun timer, nessun backup avviato.
**E. Primi backup V2 manuali.** `/opt/superbot-extbackup-v2/run-classic.sh` (Falco/Toro); `/opt/superbot-extbackup-v3/run-v3.sh --preflight`, `--plan`, poi senza opzioni; per Brain Free
`run-v3.sh --mode brain-free --plan` e poi reale. Ciascuno pubblica solo nel repository V2 e rilegge l'archivio da un clone nuovo.
**F. Ripristino indipendente.** Avvio protetto di `age-v2-recovery-verify` (legge `superbot-backups-v2`, decifra con la V2, ripristina, cancella). Atteso `ESITO COMPLESSIVO: OK` e una riga
`CERTIFICATO {…}` per famiglia (solo nomi e hash). Se c'è anche la chiave personale: ripetere il ripristino sul PC con quella (`restore_*`), perché la V2 è solo in un Secret.
**G. Timer.** Copiare le righe `CERTIFICATO` in un file sulla VPS e: `… --profile classic install --with-timer --restore-certificate FILE` (simulazione), poi con `--apply --approve`; idem `--profile v3`.
Il cancello pretende backup V2 reale + attestazione delle Actions con le impronte di questo repository.
**H. Spegnere il V1 (decisione del proprietario, dopo alcune notti V2 verdi).** `systemctl disable --now superbot-extbackup.timer` (reversibile con `enable --now`). **Attenzione:** la sentinella
`sg-extbackup-watch` guarda `/opt/superbot-extbackup/status.json` (V1): dopo lo spegnimento darà allarme; va adeguata o sostituita da una sentinella V2 (gate aperto, §8).

## 5. Rollback (nessun passo cancella dati)
* Installazione: `install_brain_v3_extension.py --profile … rollback --apply` — toglie solo i file V2 registrati e invariati (i file comuni solo quando nessun profilo li usa), ferma e toglie il solo timer
  del profilo e **sposta** la cartella di lavoro in `*.removed-<data>`. Il registro di installazione (scritto prima di ogni modifica) permette il recupero anche dopo un'interruzione brusca.
* Timer V2: `systemctl disable --now superbot-extbackup-v2.timer` (o `-v3`) e rollback. Il timer V1 non è mai stato nominato dall'installatore: se lo hai spento al passo H, `systemctl enable --now superbot-extbackup.timer`.
* Repository V2: gli archivi pubblicati restano (nessuna cancellazione automatica); i V1 non sono coinvolti.

## 6. Chiave personale e due destinatari (disegno)
* **Perché:** la V2 vive in un Secret di GitHub che nessuno può rileggere. Una chiave personale custodita dal proprietario fuori da GitHub rende il recupero indipendente da GitHub. Con age, un archivio cifrato per
  **due** destinatari (`age -r V2 -r PERSONALE`) si apre con ciascuna delle due private. Il supporto è già nel codice (`age_recipients.py`, usato da `external_backup_multi.py` e dalla pipeline V3/Brain Free) e provato:
  entrambe le chiavi aprono tutte e tre le famiglie, una terza no.
* **Creazione (sul computer del proprietario, non sulla VPS, non in chat):** `age-keygen -o chiave-personale.txt` (stampa la pubblica); proteggerla con passphrase `age -p -o chiave-personale.txt.age chiave-personale.txt` e
  rimuovere in modo sicuro il chiaro; **almeno due copie** in luoghi fisicamente diversi (gestore password + chiavetta cifrata offline o carta in cassaforte), passphrase separata; provarla cifrando e decifrando un file di prova.
  Alla creazione non va mai mostrata in una chat: se capita, è esposta e va rifatta.
* **Introduzione:** passo A di §4 (prima dell'installazione). Se la si aggiunge dopo, serve un aggiornamento controllato dell'installazione (l'installatore non sovrascrive file esistenti): nuova revisione, nuova impronta, sostituzione atomica dei tre file
  con copia di sicurezza e rollback — da preparare con una PR a parte.
* **Rewrap degli archivi V2 già fatti:** con la V2 nelle Actions un job protetto può decifrare e ricifrare verso V2+personale e pubblicare in un ramo separato; da fare solo se si aggiunge la personale dopo i primi backup.
* **Rotazione/revoca:** togliere un destinatario non rende illeggibili gli archivi già fatti per lui; si ruota aggiungendo il nuovo, ricifrando se serve, e poi togliendo il vecchio con un nuovo commit rivisto.

## 7. Strategia per certificare il recupero COMPLETO dei dati
**Copertura (che cosa deve poter tornare):**
| Dato | Famiglia di backup | Dove si prova |
|---|---|---|
| Database app (utenti, `password_hash`, configurazioni) e database pool | Falco/Toro | integrità SQLite nel ripristino |
| Storici, stato, apprendimento, `lessons.md`, `errors.md`, archivio di Falco e Toro | Falco/Toro | coerenza semantica per portafoglio + confine di ciclo/eccezione |
| Run PAPER di Brain V3 (journal, budget, configurazione, mandato, richieste di chiusura in sospeso) | Brain V3 | catena hash, identità, coerenza, posizioni, accettazione dal codice RC84 |
| Storico Brain Free/V2 (`brain.sqlite3`) | Brain Free | integrità + misura degli eventi |
| NON coperti (voluto): `.env`/Secrets di trading, immagini Docker, nginx, unità systemd, DNS, HiTV | repository + Secrets | si ricostruiscono dal repository e rimettendo i Secrets |
**Livelli di certificazione (ciascuno con prova verificabile):**
* **L0 custodia:** `age-v2-key-check` → la privata derivata coincide con il destinatario documentato e fa il giro cifra/decifra; per la personale: stessa prova sul PC.
* **L1 archivio:** manifest in chiaro + SHA-256 del cifrato (anche delle parti) + decifratura autenticata da un clone **nuovo** del repository.
* **L2 contenuto:** manifest interno (SHA-256 di ogni file), integrità SQLite, catena hash del journal, identità unica, coerenza configurazione/mandato/budget, coerenza semantica dei portafogli classici, accettazione dal codice RC84 vero.
* **L3 equivalenza con la sorgente:** le ancore registrate dalla VPS al momento del backup (eventi/hash di testa, righe e hash del budget, misura del database storico) devono coincidere con quanto ripristinato; per un testimone esterno,
  annotare nel diario (ramo pubblico, solo hash e conteggi) le impronte di stato di ogni backup di certificazione.
* **L4 ripartenza:** il ripristino di una run Brain V3 deve essere accettato da `check_existing_data`/`verify_prepared_run_config`/`build_summary` (già fatto con `--v3-src`), con le posizioni PAPER aperte uguali a quelle del manifesto;
  per Falco/Toro, riesame delle posizioni aperte con gli strumenti offline di RC84 (`assess_restart`) su una copia ripristinata, mai sui dati veri.
* **L5 prova periodica:** ripristino mensile con il workflow protetto (famiglia per famiglia) e una volta a trimestre una prova a freddo sul PC con la chiave personale. Il certificato scade: oltre 35 giorni senza prova, il recupero torna «non certificato».
**Criteri per dichiarare «recupero completo certificato»:** (1) L0–L4 superati per **tutte e tre** le famiglie sullo stesso ciclo di backup; (2) entrambe le chiavi (V2 e personale) hanno aperto lo stesso archivio; (3) nessuna famiglia in `NON CONFERMATO`;
(4) il numero di archivi, i timer e lo stato di `status.json` dopo almeno tre notti consecutive senza errori; (5) la prova ripetuta dopo ogni cambio di destinatari, di script o di versione di RC84.

## 8. Rischi residui e gate aperti
1. **Archivi V1 non apribili** senza la privata V1; i dati storici sono protetti solo dalla VPS finché non esiste (e non è ripristinato) il primo backup V2. Ritardare il passo E aumenta l'esposizione.
2. **V2 solo in un Secret**: la perdita del Secret o l'accesso di terzi al repository compromettono il recupero V2 → introdurre la chiave personale (§6) prima dell'uso in produzione. La V1 è passata dalla chat: considerarla esposta.
3. **Fiducia nelle Actions:** chi ha scrittura sul repository può far girare un workflow modificato che legge i Secrets; la mitigazione reale è l'ambiente `age-recovery` con revisore e rami consentiti (da creare). Impronta di approvazione e commit fissati proteggono dagli errori, non da un attore con scrittura.
4. **Attestazioni procedurali, non crittografiche:** le righe `CERTIFICATO` provano che il workflow ha detto OK; non sono firmate. L'installatore ne verifica le impronte del repository ma non può verificare la run. Rafforzamento possibile: controllare la run via API pubblica con il suo numero.
5. **Chiave di deploy V2 in scrittura sulla VPS:** se la VPS fosse compromessa potrebbe pubblicare archivi spazzatura; i vecchi restano (cronologia immutabile con le regole sui rami). Attivare le regole di protezione dei rami nel repository V2.
6. **Sentinella V2 assente** (gate aperto); la V1 darà allarme dopo lo spegnimento. **Aggiornamento dei destinatari dopo l'installazione** richiede un comando di aggiornamento non ancora fatto.
7. `external_backup_multi.py` sostituisce due funzioni di `external_backup.py` in memoria: sicuro finché l'impronta del file classico resta quella rivista (controllata a ogni avvio), fragile a un suo aggiornamento (va ripetuta la revisione).
8. **Mai eseguito su GitHub o sulla VPS:** workflow, wrapper e installatore sono provati con chiavi, repository e systemctl finti; Python 3.8–3.10 non provati; dimensioni e tempi reali ignoti (Brain Free ~470 MB: il `--plan` dà il numero esatto).
