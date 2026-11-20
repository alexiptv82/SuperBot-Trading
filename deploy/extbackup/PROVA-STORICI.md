# Prova dell'extbackup sugli storici reali (senza trasferimento)

**Scopo:** dimostrare sui dati reali che l'extbackup copre **tutti** gli storici e che il ripristino funziona, **senza** inviare nulla fuori dalla VPS.
- **Storici coperti:** Falco e Toro, database dell'app e del pool, tutte le run Brain V3 in `/opt/superbot-v3-paper-runs/*`, le run Arena in `/opt/superbot-ai-arena-paper/*/*` e il Brain libero.

**Come funziona:**
- l'extbackup gira verso un repository git **locale** in `/root`, con una **chiave di prova** generata sul momento;
- il ripristino lo fa lo script ufficiale `restore_external_backup.py`;
- all'uscita tutto viene cancellato: archivio di prova, chiave, repository e copie.

**Cosa non fa:** nessun servizio fermato, nessun permesso cambiato, nessuna rete. Le sorgenti si aprono in sola lettura: SQLite in `mode=ro`, copia dei file JSONL.

**Novità rispetto all'extbackup installato:** l'opzione `--run-dir`, ripetibile.
- Le basi SQLite si copiano con l'API di backup e si controlla l'integrità.
- Lock, WAL, SHM e file temporanei sono esclusi.
- Se una cartella manca, non parte nulla.
- Collaudo: `deploy/scripts/test_external_backup.py`, 34 test da non-root, tra cui la prova completa dello script con i percorsi sostituiti.

## Comandi (una sessione, utente con sudo)
```
sudo install -d -m 700 -o root -g root /root/extbackup-strumenti
sudo install -m 500 -o root -g root /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/external_backup.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/restore_external_backup.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/backup_app_db.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/backup_brain.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/extbackup/prova_storici.sh /root/extbackup-strumenti/
printf '%s\n' \
  '639b6fa4c1120ef15f29735c89a56c9e112a8ea12f05a9fda0721e2acfa5f1ed  /root/extbackup-strumenti/external_backup.py' \
  'fa86e0cf41a380b21b467e6e51db1d7d523f144eab95726a04fd878c1a8c5532  /root/extbackup-strumenti/restore_external_backup.py' \
  '6bd6ebc209400c7a0b222c62690e2c2f11b6f0a927b83fa937a35dcaac0700c6  /root/extbackup-strumenti/backup_app_db.py' \
  '4a92e7daa6cff9fbf339f471656df8ba44067b6927d15b411b50313de0cb5d2c  /root/extbackup-strumenti/backup_brain.py' \
  'b8b70c57ee2cbdfe33ad2fd41c9abf292b82ee0ff2861e067fe72e668c0bde61  /root/extbackup-strumenti/prova_storici.sh' \
  | sudo sha256sum -c -
sudo sh /root/extbackup-strumenti/prova_storici.sh /root/extbackup-strumenti
```
Se una riga di `sha256sum -c` non dice `OK`, **non** lanciare l'ultimo comando.

**Esito atteso:**
- l'inventario: nomi, dimensioni e numero di file per ogni run;
- `RISULTATO: OK` del backup e del ripristino;
- una riga `ripristinata …` per ogni run;
- `ESITO PROVA: OK`.

Ogni errore produce `NO-GO: …`, e la cartella di prova viene comunque cancellata. `/root/extbackup-strumenti` resta: contiene solo gli script.

**Dopo:** il backup vero, cifrato con la chiave del proprietario e inviato al repository privato `superbot-backups` con la deploy key esistente, richiede un'autorizzazione specifica. Comprende anche l'aggiornamento dell'extbackup installato con `--run-dir`. La verifica di ripristino con la chiave privata si fa sul PC del proprietario.
