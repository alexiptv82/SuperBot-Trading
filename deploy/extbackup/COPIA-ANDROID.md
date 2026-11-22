# Copia cifrata degli indispensabili per lo smartphone e ripristino con Termux (DA AUTORIZZARE)

**Stato:** preparato e provato in laboratorio; **nulla eseguito sulla VPS.** Codice al commit `0789e8af`.

## Che cosa fa `copia_android.sh` (VPS, root)
- **Archivi:** gli indispensabili della prova certificata: Brain V3 attivo, 3 run Arena (journal V3 obbligatori), database dell'app e del pool. Se ne manca uno: NO-GO prima di copiare.
- **Cifratura:** **solo** per la chiave pubblica Android `age1kpdfwmlpjmmwre34kg5zpdjlrc3kjw7syymzax8tg2jm892wa5sqnzc9nm`.
- **Produzione invariata:** `/opt/superbot-extbackup/recipient.txt` è letto solo per controllo (deve restare la sola chiave approvata), la sua impronta è confrontata prima e dopo; l'extbackup periodico e le sue impostazioni non si toccano. Non parte se il backup periodico è in esecuzione.
- **Isolamento nel repository `superbot-backups`:** l'archivio va in `copie/android/AAAA/MM/`, fuori da `archives/`.
  - prima del commit: ogni modifica deve stare sotto `copie/android/`, altrimenti nessun commit e nessun push;
  - dopo il push: il commit tocca solo `copie/android/`; gli archivi in `archives/` sono gli stessi di prima;
  - `recipient.txt` e `LEGGIMI.md` della radice non vengono riscritti;
  - **nessuna retention**, né ora né in futuro: la retention periodica guarda solo `archives/` (test dedicato).
- **Verifica:** clone nuovo da GitHub, SHA-256 dell'archivio e di ogni parte da 90 MiB.
- **Strumenti certificati non modificati:** `copia_aggiuntiva.py` riusa le funzioni di `external_backup.py` (impronta invariata `331d44b4…`).

## 1. Comando Termius (utente con sudo); si ferma se un'impronta non coincide
```
sudo install -d -m 700 -o root -g root /root/extbackup-strumenti && sudo install -m 500 -o root -g root /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/external_backup.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/backup_app_db.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/extbackup/copia_aggiuntiva.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/extbackup/copia_android.sh /root/extbackup-strumenti/ && printf '%s\n' '331d44b4266a719c5ce7854b867b2f0a25b401c8c605cfca349063860753d1ee  /root/extbackup-strumenti/external_backup.py' '6bd6ebc209400c7a0b222c62690e2c2f11b6f0a927b83fa937a35dcaac0700c6  /root/extbackup-strumenti/backup_app_db.py' '0aabba3664407a541679f169ac4886bfceb802a0e265c746daeeecf7b1f9d7b9  /root/extbackup-strumenti/copia_aggiuntiva.py' '6c1216e2a1a2fb8a2a145ae1b96a83eac1b62f61c779ff34945348d39982ff81  /root/extbackup-strumenti/copia_android.sh' | sudo sha256sum --strict -c - && sudo sh /root/extbackup-strumenti/copia_android.sh /root/extbackup-strumenti
```
**Esito atteso:** `RISULTATO: OK  copia aggiuntiva android  archivio copie/android/…  N byte (in chiaro M)  sha256 …`, poi `nessuno tolto; retention non applicata`, `recipient.txt di produzione invariato`, `ESITO: COPIA ANDROID … VERIFICATA DA UN CLONE NUOVO`. Registro in `/root/extbackup-android/` (solo nomi ed esiti).

## 2. Termux sullo smartphone (utente normale, senza root)
**Una volta sola** (installa gli strumenti; `termux-setup-storage` chiede il permesso Android per leggere Download):
```
pkg update -y && pkg install -y python age coreutils curl && termux-setup-storage
```
**Spazio libero** (il valore richiesto lo calcola e lo controlla anche lo script: circa 3 volte l'archivio cifrato + i dati in chiaro + 256 MiB):
```
df -h $HOME
```
**Scaricare l'archivio:** nel browser del telefono, con l'account GitHub, aprire `github.com/alexiptv82/superbot-backups/tree/main/copie/android/AAAA/MM` e scaricare (Download raw file) il `…manifest.json` e l'archivio `.tar.gz.age` oppure **tutte** le parti `.part000`, `.part001`, … I file finiscono in `Download`. I nomi devono restare identici (nessun "(1)"), e in Download deve esserci un solo manifesto `superbot-backup-indispensabili-*`.

**Ripristino verificato** (sostituire `CHIAVE` con il percorso del file della chiave privata Android in Termux, es. `~/android-age.txt`):
```
mkdir -p ~/superbot-script && cd ~/superbot-script && curl -fsSLO https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/0789e8af8acd6f84746d1dc80cdacff84b196d0a/deploy/scripts/restore_external_backup.py && curl -fsSLO https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/0789e8af8acd6f84746d1dc80cdacff84b196d0a/deploy/extbackup/ripristino_termux.sh && printf '%s\n' 'faa73399a7fa2bf28fa7768f73e4fc9978d0b5b7f84739dd1e261b49efca835f  restore_external_backup.py' 'a873ec4681315e19eaaa0cdb40d9af9be2d2482f6c90e4ee2f1bae58b24fe6a2  ripristino_termux.sh' | sha256sum --strict -c - && sh ripristino_termux.sh ~/storage/downloads CHIAVE
```
Lo script:
1. controlla `python`, `age`, `age-keygen`, `sha256sum` e i moduli Python;
2. controlla che la chiave privata corrisponda alla chiave pubblica Android (con `age-keygen -y`, senza mostrarla);
3. controlla il manifesto (destinatario Android, componente indispensabili) e la presenza di tutte le parti;
4. **controlla lo spazio libero** prima di copiare qualunque cosa;
5. copia i file cifrati nella memoria **privata** di Termux (`~/superbot-ripristino`) e ripristina lì: i dati in chiaro non vanno mai nella memoria condivisa;
6. esegue `restore_external_backup.py`: SHA-256 delle parti e dell'archivio, decifratura autenticata, manifesto interno, `integrity_check` dei due database, **quattro catene EventJournal V3 obbligatorie**;
7. con esito positivo **cancella i dati in chiaro** e conserva solo il registro.

**Esito atteso:** `catene EventJournal V3 obbligatorie verificate: 4` e `ESITO: RIPRISTINO SU ANDROID CERTIFICATO`.
**Da mandare a Claude:** le righe del riepilogo stampato (nessun dato in chiaro vi compare).

## Compatibilità con Termux (verificata in laboratorio, non ancora su un telefono)
- Il ripristino degli indispensabili usa solo la libreria standard di Python (`sqlite3`, `hashlib`, `tarfile`, `gzip`, `json`) e il programma `age`: nessun `backup_brain.py`, nessun repository SuperBot, nessun privilegio. Termux è un ambiente Linux: anche `fcntl` è disponibile.
- La prova di laboratorio esegue lo script Termux con `sh` (dash, come Termux), in una HOME finta e da utente normale, con il solo `restore_external_backup.py` accanto: archivio in 4 parti, 4 catene verificate, dati in chiaro cancellati. Rifiuti provati: chiave privata sbagliata, spazio insufficiente, parte mancante.
- Python provato: 3.12. Il codice non usa API rimosse nelle versioni successive. La versione di `age` in Termux non è stata verificata: se `pkg install age` non lo trovasse, segnalarlo prima di procedere.
