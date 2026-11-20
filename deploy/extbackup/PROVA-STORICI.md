# Prova dell'extbackup sugli storici reali (senza trasferimento)

**Scopo:** dimostrare sui dati reali la copertura degli storici e il ripristino, **senza** inviare nulla fuori dalla VPS.

**Come funziona:**
- l'extbackup gira verso un repository git **locale** in `/root`, con una **chiave di prova** generata sul momento;
- il ripristino lo fa lo script ufficiale `restore_external_backup.py`;
- all'uscita tutto viene cancellato: archivio di prova, chiave, repository e copie.

**Cosa non fa:** nessun servizio fermato, nessun permesso cambiato, nessuna rete, sorgenti aperte in sola lettura. L'extbackup installato **non** viene modificato: gli script verificati vengono copiati in `/root/extbackup-strumenti`.

## Archivi
| Tipo | Archivi | Se manca |
|---|---|---|
| **Obbligatori** | con EventJournal V3 (journal.db, `v3_events`, catena verificata, registrato e riverificato dopo il ripristino): Brain V3 attivo `brain-v3-paper20261111`, Arena `brain-{deepseek,qwen,minimax}-paper20261118`; senza formato V3 imposto: Brain storico `/opt/superbot-desk-data/brain`; Falco `hawk/` e Toro `bull/` (tramite `backup_brain.py`); database dell'app e del pool | **NO-GO**, prima di qualunque copia |
| **Facoltativi** | le altre run in `/opt/superbot-v3-paper-runs/*`; `/opt/superbot-brain-free`; `/opt/superbot-brain-adaptive` (con `hawk/`, `bull/`); `/opt/superbot-ai-data` | inclusi se presenti |

## Copia e controlli
- **Copia:** ricorsiva, comprese le sottocartelle.
- **Escluse**, e solo contate per categoria:
  - link simbolici e file non regolari;
  - file e cartelle nascosti;
  - lock, `-wal`/`-shm`/`-journal`, file temporanei;
  - **possibili segreti**: `.env`, `*.pem`, `*.key`, nomi che contengono `secret`, `token`, `credential`, `password`, `id_rsa`, `id_ed25519` o `api_key`.
- **Basi SQLite:**
  - copiate con l'API di backup, sorgente in sola lettura: il contenuto confermato del WAL è incluso;
  - copia autonoma, senza file WAL o SHM;
  - `integrity_check` su ogni copia.
- **Journal V3:**
  - verifica della catena degli eventi;
  - verifica che la copia sia un **prefisso** dell'originale, che è append-only;
  - numero di eventi e testa registrati nell'archivio (`runs/_journal_v3.json`).
- **Dopo il ripristino:**
  - SHA-256 e dimensione di ogni file contro il manifest interno;
  - `integrity_check` dei database;
  - catena, numero di eventi e testa di **ogni** journal V3 uguali ai valori originali.
- **Spazio:** controllato prima di iniziare. Serve 6 volte la dimensione delle sorgenti più 1 GiB: copie temporanee, `tar.gz` in chiaro, cifrato, repository, clone, ripristino. Se non basta, NO-GO.
- **Test:** `deploy/scripts/test_external_backup.py`, 42 da non-root. Comprendono:
  - vettori di riferimento della regola di hash del journal del progetto;
  - troncamento, catena manomessa, journal mancante, originale riscritto;
  - archivio obbligatorio mancante;
  - la prova completa dello script con i percorsi sostituiti.

## Comando unico (Termius, utente con sudo)
Si ferma da solo se un'impronta non coincide: i comandi sono concatenati con `&&`.
```
sudo install -d -m 700 -o root -g root /root/extbackup-strumenti && sudo install -m 500 -o root -g root /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/external_backup.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/restore_external_backup.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/backup_app_db.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/backup_brain.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/extbackup/prova_storici.sh /root/extbackup-strumenti/ && printf '%s
' '999bbbfe0d1482f3f965856169b69ab8af70c75b82d93e7a622deb395b2af6a8  /root/extbackup-strumenti/external_backup.py' '8f4e39fb5c24c031bbe65069b8251b9a2d7acc8bba7a4429ed8aa7fd457da47f  /root/extbackup-strumenti/restore_external_backup.py' '6bd6ebc209400c7a0b222c62690e2c2f11b6f0a927b83fa937a35dcaac0700c6  /root/extbackup-strumenti/backup_app_db.py' '4a92e7daa6cff9fbf339f471656df8ba44067b6927d15b411b50313de0cb5d2c  /root/extbackup-strumenti/backup_brain.py' 'e4566373dc7c4f103da2e1d63c96ae013163d8a7da413393616dba64ae9e3bb6  /root/extbackup-strumenti/prova_storici.sh' | sudo sha256sum --strict -c - && sudo sh /root/extbackup-strumenti/prova_storici.sh /root/extbackup-strumenti
```
**Esito atteso:**
- inventario con dimensioni, file e sottocartelle;
- riga dello spazio;
- `RISULTATO: OK` di backup e ripristino;
- una riga `journal V3 …: N eventi, catena verificata` per ogni journal;
- una riga `ripristinata …` per ogni archivio;
- `ESITO PROVA: OK`.

Ogni errore produce `NO-GO: …`. La cartella di prova viene cancellata in ogni caso; `/root/extbackup-strumenti` resta e contiene solo gli script.

## Dopo la prova (ciascun punto con un'autorizzazione specifica)
- Aggiornare l'extbackup installato con queste versioni e i percorsi delle run.
- Backup reale con la chiave pubblica del proprietario verso `superbot-backups`. **Attenzione:** `brain.sqlite3` del Brain libero da solo pesa 469 MB, e GitHub rifiuta i file oltre 100 MB, quindi serve dividere l'archivio o usare un altro deposito.
- Ripristino con la chiave privata sul PC del proprietario.
