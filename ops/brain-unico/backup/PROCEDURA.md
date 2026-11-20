# Backup cifrato della run Brain: procedura amministrativa (una sola esecuzione, da autorizzare)

**Perché serve root:** la cartella della run (`/opt/superbot-v3-paper-runs/brain-v3-rc20261106`, run `brain-rc-2000-20261106`) e la chiave pubblica dell'extbackup (`/opt/superbot-extbackup/recipient.txt`) sono leggibili solo da root. Nessun permesso viene cambiato, nessun servizio fermato, nessuna rete.

**Cosa esegue root:** solo `brain_run_backup_root.py`. È uno script autonomo, con la sola libreria standard e `tar`/`age`, che non importa codice del ramo di laboratorio. È collaudato da non-root (`backend/tests/test_v3_brain_run_backup_root.py`) e vincolato a questa impronta:

`SHA-256 = 1e0a3a3e3b7ba008f7012b8c72399e5c967d7f0e19882dfa04c5bcbce9e240a3`

## Fasi dello script
1. **Copie in chiaro temporanee:** cartella di lavoro nuova 0700 (umask 077). Backup SQLite coerente con la sorgente aperta in sola lettura, integrità, file di stato ammessi (mai i lock), manifest con impronte, numero di eventi e testa della catena.
2. **Ripristino in chiaro:** impronte, catena e integrità uguali al manifest.
3. **Cifratura in streaming:** `tar | age` verso la chiave pubblica approvata più una chiave di prova effimera.
4. **Prova del file cifrato:** decifrato con la chiave effimera, poi impronte e catena di nuovo uguali al manifest.
5. **Pulizia:** cartella di lavoro cancellata, cioè copie in chiaro e chiave effimera. Restano `<nome>.tar.age` e `<nome>.manifest.json`, quest'ultimo con soli nomi, impronte e conteggi. La cancellazione è quella del filesystem, senza sovrascrittura sicura.

## Comando esatto (da un utente con sudo, nel terminale della VPS)
```
sudo install -d -m 700 -o root -g root /root/brain-run-backup
sudo install -m 500 -o root -g root /home/superbot-agent/brain-unico-lab/wt-int/ops/brain-unico/backup/brain_run_backup_root.py /root/brain-run-backup/brain_run_backup_root.py
echo "1e0a3a3e3b7ba008f7012b8c72399e5c967d7f0e19882dfa04c5bcbce9e240a3  /root/brain-run-backup/brain_run_backup_root.py" | sudo sha256sum -c -
sudo python3 -I /root/brain-run-backup/brain_run_backup_root.py backup --source /opt/superbot-v3-paper-runs/brain-v3-rc20261106 --out-dir /root/brain-run-backup --recipient-file /opt/superbot-extbackup/recipient.txt --name brain-rc-2000-20261106-$(date -u +%Y%m%dT%H%M%SZ)
```
Lo script viene copiato in una cartella di root e verificato **dopo** la copia, così una modifica successiva non conta. Se l'impronta non coincide, il terzo comando fallisce: non lanciare il quarto. Atteso: una riga `OK eventi=… cifrato=… sha256=…`. Ogni errore produce `NO-GO: …`, senza file in chiaro residui.

**Destinazione:** `/root/brain-run-backup`, nuova e solo di root. Non è la cartella di lavoro dell'extbackup, per non far partire alcun trasferimento verso GitHub. Nessun archivio storico viene toccato.

## Verifica del ripristino dal file cifrato
- **Al momento del backup (automatica):** fase 4, decifratura con la chiave effimera e controllo completo. Prova che il file cifrato contiene esattamente il backup verificato.
- **Con la chiave del proprietario (dopo la copia fuori dalla VPS, da autorizzare):** `python3 brain_run_backup_root.py verify --input X.tar.age --manifest X.manifest.json --identity <chiave privata>`. La chiave privata non arriva mai sulla VPS.

## Non incluso
Trasferimento su GitHub o altrove, backup di Falco, Toro e Arena, modifiche all'extbackup: richiedono decisioni separate.
