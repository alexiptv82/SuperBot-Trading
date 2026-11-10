# Verifica di recupero con la chiave age V2 (workflow isolato)

> **Aggiornamento (migrazione V1→V2):** i fatti sul destinatario sono stati verificati dall'utente sulla VPS: **tutti gli ultimi archivi (Falco/Toro, Brain V3, Brain Free) sono cifrati per V1** e la chiave V2 del Secret appartiene a un'altra coppia. Questo workflow legge quindi il repository **V2** (`superbot-backups-v2`, archivi nuovi cifrati per V2) e emette le attestazioni `CERTIFICATO` per i timer; il controllo che il Secret coincida con il destinatario V2 documentato il 23/10 e' il workflow separato `age-v2-key-check.yml`. Procedura completa: `deploy/extbackup/age-v2-migration/LEGGIMI.md`. Il testo sotto resta valido per le parti non toccate.

**Stato: PREPARATO, NON ESEGUITO.** Nessun job che usa un Secret è stato avviato. Pubblicare questo ramo non esegue nulla: il workflow parte solo con
`workflow_dispatch` (impronta di approvazione) oppure con il push del file `RUN.trigger` su un ramo di **esecuzione** diverso da quello di revisione (`work/age-v2-recovery-run-20261110`, che non esiste); il file `RUN.trigger` questo commit **non lo contiene**.

## Perché non si riusa il workflow del 23 ottobre
`age-v2-restore-check.yml` (ramo `safety/pre-capital-rule-pool-after-backup-20261023`, run 40010394710) **entra in SSH come root sulla VPS di Singapore**
(`SINGAPORE_SSH_PRIVATE_KEY`), copia script sul server, lancia un backup e scarica l'archivio da lì; tiene entrambi i Secrets nell'ambiente di tutto il job;
stampa i dettagli del ripristino (in un repository pubblico finirebbero nei log). Non si può usare senza accedere alla VPS. Il nuovo workflow
(`.github/workflows/age-v2-recovery-verify.yml`) non tocca la VPS, non ha azioni di terze parti, non carica artifact e stampa solo frasi fisse.

## Prima di tutto: controllo gratuito e senza chiavi (consigliato)
Il destinatario V2 (`age1dkwnnrng…`) esiste **solo** sul ramo di sicurezza del 23/10 e nessun ramo lo promuove a destinatario di produzione: quello di produzione
nel repository è `age142uj5c8x…` (V1, 19/10). Gli archivi di Falco/Toro, Brain V3 e Brain Free usano il destinatario del file `/opt/superbot-extbackup/recipient.txt`
della VPS. Se è ancora V1, **la chiave V2 non li può aprire**.
Aprire nell'interfaccia GitHub del repository dei backup (V1: `superbot-backups`; V2: `superbot-backups-v2`) il file `*.manifest.json` dell'archivio più recente di ciascun ramo (`main` → `archives/…`,
`brain-v3`, `brain-free`) e leggere `cifratura.destinatario`: confrontare solo l'inizio (`age142uj5c8x` = V1, `age1dkwnnrng` = V2). Il manifest non contiene segreti.
* se è **V2**: il workflow qui sotto può completare il ripristino;
* se è **V1**: serve la chiave privata V1. Se anche quella è persa, quegli archivi **non sono recuperabili da nessuno** (age non ha porte di servizio): i dati originali
  restano sulla VPS, quindi la correzione è fare **nuovi** backup verso un destinatario di cui si custodisce la privata (vedi «Copia di emergenza»).

## Prerequisiti (da fare nell'interfaccia GitHub, una volta)
1. **Lettura del repository privato dalla Actions.** La sessione di Claude non vede i repository dei backup (`add_repo`: «you don't have access»), e il token del repository
   `SuperBot-Trading` non lo legge. Serve una chiave di deploy **in sola lettura**: sul proprio PC `ssh-keygen -t ed25519 -N '' -f chiave-lettura-backups`;
   aggiungere la parte `.pub` in `superbot-backups-v2` → Settings → Deploy keys **senza** «Allow write access»; incollare la parte privata nel Secret
   `SUPERBOT_BACKUPS_READ_KEY` di `SuperBot-Trading`; cancellare il file privato locale. **Non** riusare la chiave di deploy della VPS (ha accesso in scrittura).
2. **Ambiente protetto `age-recovery`** (Settings → Environments): revisore obbligatorio = il proprietario; «Deployment branches» limitato a
   `work/age-v2-recovery-verify-20261110` (avvio con `workflow_dispatch`) e, se si vuole usare il push, `work/age-v2-recovery-run-20261110`. Il job lo dichiara, quindi non parte senza l'approvazione. (Senza questi controlli qualunque persona con scrittura sul repository
   potrebbe far girare un workflow modificato che legge i Secrets: è un limite di GitHub, non del workflow.)
3. Il Secret `SUPERBOT_AGE_RECOVERY_KEY_V2` esiste già (confermato dal proprietario). Il suo valore non è leggibile da nessuno, nemmeno dal proprietario.

## Impronta di approvazione e avvio
L'impronta lega il lancio ai due file rivisti (workflow e script); se uno cambia, il job si ferma **prima** di usare qualunque Secret:
```sh
SHA=<commit approvato del ramo>
WF=$(git show $SHA:.github/workflows/age-v2-recovery-verify.yml | sha256sum | cut -d' ' -f1)
SC=$(git show $SHA:deploy/extbackup/age-v2-recovery/verify_recovery.py | sha256sum | cut -d' ' -f1)
printf '%s\n%s\n' "$WF" "$SC" | sha256sum | cut -d' ' -f1
```
Avvio (solo dopo revisione e OK esplicito): *Actions → «SuperBot age V2 - verifica di recupero…» → Run workflow* sul ramo, con l'impronta; oppure: creare dal commit approvato il ramo `work/age-v2-recovery-run-20261110`, aggiungere
`deploy/extbackup/age-v2-recovery/RUN.trigger` con la riga `approval=<impronta>` e fare il push di quel ramo. L'ambiente `age-recovery` chiede poi l'approvazione.

## Che cosa fa e che cosa stampa
Passi: (1) scarica per **commit fisso** gli script (`7b2aabe900d6ba6b032ab34e7568e4f4dd70d5ec`) e RC84 (`0e29a73a36f668643da4088178bacb8616a45ac0`), ne controlla le
impronte e l'approvazione; (2) clona in sola lettura i tre rami del repository privato (senza scaricare gli archivi); (3) scrive la chiave V2 su un file 600; (4) deriva
internamente la chiave pubblica e la confronta con il destinatario del manifest di ogni archivio; (5) per l'archivio **più recente** di ciascuna famiglia, solo se il
destinatario coincide, lo scarica, lo decifra e lo ripristina (Falco/Toro con `restore_external_backup.py`; Brain V3 e Brain Free con `restore_brain_v3_backup.py`; Brain V3
anche con il codice RC84 fissato), poi cancella subito il ripristino; (6) cancella chiavi e cartelle temporanee.
Il log contiene **solo** frasi fisse: `ESITO … OK/NO`, numero di archivi per ramo e quanti sono cifrati per questa chiave, nome dell'archivio più recente, e per ogni
controllo una frase booleana (decifratura, manifest e SHA-256, SHA-256 di ogni file, integrità dei database, catena hash del journal, coerenza dei portafogli, RC84).
Nessuna chiave, nessun destinatario, nessun importo, nessun conteggio di portafoglio. L'uscita completa degli script di ripristino non viene mai stampata né conservata.
Uscita 0 solo se i tre archivi più recenti sono ripristinati; 2 se qualcuno non è decifrabile o non è confermato (`ESITO COMPLESSIVO: PARZIALE/NO`).

## Copia di emergenza della chiave di recupero (fuori da GitHub, sotto il controllo del proprietario)
Il valore di un Secret non si può leggere: l'unico modo di «esportarlo» è far girare un workflow che lo emette, e in chiaro finirebbe nei log di un repository **pubblico**.
Quindi la copia di emergenza non si ottiene estraendo la V2: si crea una chiave nuova che il proprietario custodisce davvero.
1. **Su un computer del proprietario, non sulla VPS e non in chat:** `age-keygen -o chiave-recupero-V3.txt` (stampa la chiave pubblica `age1…`).
2. **Proteggerla con una passphrase** (non quella del gestore password): `age -p -o chiave-recupero-V3.txt.age chiave-recupero-V3.txt`, poi rimuovere in modo sicuro il file in chiaro.
3. **Almeno due copie in luoghi fisicamente diversi**, es. gestore di password + chiavetta cifrata offline o stampa su carta in cassaforte; la passphrase separata dalle copie.
4. **Provarla davvero:** cifrare un file di prova verso la pubblica e decifrarlo con la copia recuperata dal solo supporto di emergenza.
5. **Pubblicare solo la chiave pubblica** (nel file `recipient.txt` con revisione) e annotare nel diario solo l'impronta sha256 della pubblica. Mai la privata: né in chat, né in mail,
   né screenshot, né repository, né VPS, né come unica copia in un Secret.
6. Per non dipendere più da una sola chiave: cifrare i backup verso **due destinatari** (`age -r A -r B`, o `-R file`). Il tool attuale legge un solo destinatario: modifica da
   fare con revisione, non fatta qui.
7. Se serve proprio la V2 (per aprire archivi già cifrati per V2): un workflow **separato e rivisto** può cifrare l'identità V2 verso la NUOVA chiave pubblica del proprietario e
   pubblicare solo quel cifrato; la privata nuova resta al proprietario. Non è preparato in questo commit.

## Limiti e gate
Il workflow non è mai stato eseguito su GitHub; le prove sono locali (script e flusso con chiavi e repository finti). Non certifica il Falco/Toro «bot fermi» né la procedura di
installazione del timer (che richiede un certificato di ripristino scritto con `--certificate`: questo workflow non lo esporta, per non pubblicare dati). Il Secret
`SUPERBOT_BACKUPS_READ_KEY` va creato (o già esiste con altro nome: in tal caso adattare il nome prima della revisione).
