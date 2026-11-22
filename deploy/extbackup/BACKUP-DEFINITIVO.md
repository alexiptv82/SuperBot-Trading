# Backup cifrato ESTERNO definitivo e ripristino sul PC (DA AUTORIZZARE)

**Stato:** preparato; **nulla eseguito.**

**Prerequisito soddisfatto:** prova reale del 22/11 (registro `/root/extbackup-prova-storici-20261122T190332Z.log`):
- **INDISPENSABILI CERTIFICATI**;
- **STORICI INTEGRI MA NON CERTIFICATI** semanticamente (Falco e Toro, decisione del 21/11).

## Che cosa fa `backup_definitivo.sh`
- **Archivi:** gli **stessi** della prova certificata, con la selezione copiata da `prova_storici.sh`:
  - **indispensabili:** Brain V3 attivo, 3 run Arena con i journal V3 obbligatori, database dell'app e del pool;
  - **storici:** Falco, Toro, Brain storico, run preparate, Brain libero, adattivo, ai-data.

  Se manca un archivio obbligatorio: NO-GO prima di qualunque copia.
- **Cifratura:** con la chiave **pubblica approvata** `age142uj5c8xx4d9csj2dsy2uvda6e0kt9y8xln3xpetemzhts6ljaqq40qy6u`, la stessa di `deploy/extbackup/recipient.txt`. Se `/opt/superbot-extbackup/recipient.txt` non contiene esattamente quella chiave: NO-GO.
- **Invio:** due archivi al repository privato `superbot-backups`, con la deploy key di root **già esistente**. Nessuna credenziale nuova.
  - Prima gli indispensabili: se falliscono, non si prosegue.
  - Ogni invio è riverificato da un **clone nuovo da GitHub**: SHA-256 dell'archivio e di **ogni parte**.
- **File grandi:** oltre 90 MiB il file cifrato si divide in parti (GitHub rifiuta i file oltre 100 MB). Il manifesto pubblico elenca ogni parte con SHA-256 e dimensione. Lo storico (circa 117 MB nella prova) sarà diviso.
- **Che cosa NON fa:**
  - non installa e non modifica l'extbackup periodico (timer `superbot-extbackup.timer`, codice in `/opt/superbot-tools`);
  - **non parte** se quel backup è in esecuzione;
  - non tocca servizi, bot, Brain o mandato;
  - **non decifra nulla:** la chiave privata è solo sul PC del proprietario.
- **Retention:** la stessa politica del backup periodico (14 recenti, 8 settimanali, 6 mensili), **separata per componente**. Riguarda solo la punta del ramo: la storia git conserva tutto.

## Comando (Termius, utente con sudo); si ferma se un'impronta non coincide
```
sudo install -d -m 700 -o root -g root /root/extbackup-strumenti && sudo install -m 500 -o root -g root /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/external_backup.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/restore_external_backup.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/backup_app_db.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/backup_brain.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/extbackup/backup_definitivo.sh /root/extbackup-strumenti/ && printf '%s\n' '331d44b4266a719c5ce7854b867b2f0a25b401c8c605cfca349063860753d1ee  /root/extbackup-strumenti/external_backup.py' 'faa73399a7fa2bf28fa7768f73e4fc9978d0b5b7f84739dd1e261b49efca835f  /root/extbackup-strumenti/restore_external_backup.py' '6bd6ebc209400c7a0b222c62690e2c2f11b6f0a927b83fa937a35dcaac0700c6  /root/extbackup-strumenti/backup_app_db.py' '4a92e7daa6cff9fbf339f471656df8ba44067b6927d15b411b50313de0cb5d2c  /root/extbackup-strumenti/backup_brain.py' '56014d59f46df2d926050e8f671dd36d2ff9e28704210dd5df4b4f7e79b655ad  /root/extbackup-strumenti/backup_definitivo.sh' | sudo sha256sum --strict -c - && sudo sh /root/extbackup-strumenti/backup_definitivo.sh /root/extbackup-strumenti
```
Branch `claude/extbackup-storici-20261121`. Gli script `external_backup.py`, `restore_external_backup.py`, `backup_app_db.py` e `backup_brain.py` sono **identici** a quelli della prova certificata.

**Esito atteso:**
- due righe `RISULTATO: OK  archivio superbot-backup-indispensabili-…` e `…-storici-… in N parti`, con SHA-256;
- l'ultima riga `ESITO: INDISPENSABILI E STORICI INVIATI E VERIFICATI DA UN CLONE NUOVO`.

**Altri esiti:**
- uscita **3**: indispensabili inviati, storici NO-GO;
- uscita **1**: NO-GO. I registri restano in `/root/extbackup-definitivo/` e contengono solo nomi ed esiti.

**Da mandare a Claude:** le due righe `RISULTATO` (nomi, SHA-256, numero di parti) e la riga `ESITO`.

## Ripristino sul PC del proprietario (la chiave PRIVATA resta solo sul PC)
**Serve sul PC:**
- `age`, già usato in PowerShell;
- `git`;
- Python 3 (python.org).

**Passi:**
1. **Scaricare i backup.** Clonare il repository privato:
   ```
   git clone git@github.com:alexiptv82/superbot-backups.git
   ```
   oppure, da GitHub: Code → Download ZIP. Gli archivi sono in `archives/AAAA/MM/`: file `.tar.gz.age` interi, oppure le parti `.tar.gz.age.part000`, `.part001`, … con il `…manifest.json` accanto.
2. **Scaricare i due script di verifica** dal repository pubblico, branch `claude/extbackup-storici-20261121`, e controllarne le impronte in PowerShell:
   ```
   Get-FileHash restore_external_backup.py, backup_brain.py
   ```
   Devono essere `faa73399a7fa2bf28fa7768f73e4fc9978d0b5b7f84739dd1e261b49efca835f` e `4a92e7daa6cff9fbf339f471656df8ba44067b6927d15b411b50313de0cb5d2c`.
3. **Indispensabili** (funziona anche su Windows nativo):
   ```
   python restore_external_backup.py --archive <percorso>\superbot-backup-indispensabili-<istante>.tar.gz.age --identity <percorso della chiave privata> --out <cartella NUOVA e vuota>
   ```
   - Se l'archivio è diviso, si indica comunque il nome **intero**: lo script trova le parti, le controlla sul manifesto e le ricompone.
   - **Atteso:** `RISULTATO: OK` e quattro righe `journal V3 …: N eventi, catena verificata (obbligatorio)`.
4. **Storici:** stesso comando sull'archivio `…-storici-…`, **in un ambiente Linux sul PC (WSL)**. Su Windows nativo `backup_brain.py` non si carica (usa `fcntl`). **Atteso:** `RISULTATO: INTEGRO MA NON CERTIFICATO`, con uscita 3 per Falco e Toro.
5. **Dopo la verifica:** cancellare la cartella di ripristino, che contiene dati in chiaro. La chiave privata non si copia mai sulla VPS né in alcun repository.

**Che cosa dimostra:** che la chiave privata del PC corrisponde **davvero** al destinatario dei backup. La verifica in PowerShell del 10/11 non lo provava. Dimostra inoltre che gli archivi esterni sono completi e integri. **Backup certificato e ripristino verificato** sono due dei requisiti per approvare il mandato.

## Limiti dichiarati
- **Windows:** la compatibilità con Windows nativo è dedotta dagli import (gli indispensabili non usano `fcntl`), non provata su un PC Windows. In caso di errore usare WSL anche per gli indispensabili.
- **Backup periodico:** quello installato continua a produrre archivi "completi" con il codice vecchio, senza run V3 e Arena, finché l'extbackup aggiornato non viene installato (autorizzazione separata).
