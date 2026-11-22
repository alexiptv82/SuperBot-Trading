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

## Falco e Toro: modalità del cervello
È la stessa scelta del `run.sh` dell'extbackup installato, fatta con `docker inspect` e mai dedotta dai file:
- **entrambi i container fermi:** si usa `--bot-stopped`. `backup_brain.py` riverifica, per ciascun portafoglio, che il container sia fermo e che il battito sia vecchio, e rifiuta un battito fresco;
- **entrambi attivi:** backup normale, con il confine di ciclo;
- **stati diversi o non verificabili:** NO-GO.

## Coerenza di Falco e Toro nel ripristino
La prima prova reale (20/11) è terminata con 4 problemi, riprodotti offline sulla forma dei dati scritta dal bot:
- le righe di `trade_history.jsonl` non hanno `run_no` (`engine.py`) e lo storico attivo viene archiviato a ogni nuova run (`cli.py`): le righe senza etichetta sono quindi della run corrente;
- il salvadanaio sposta denaro dalla cassa al vault e viceversa, conservando la somma: il controllo verifica cassa + salvadanaio = capitale iniziale + risultati.

Tutti gli altri controlli sono invariati. Restano errori: trade diversi tra stato e storico, run successive, contabilità errata e saldo del salvadanaio illeggibile o negativo.

## Componenti separati (dal 21/11/2026)
La prova crea **due archivi cifrati indipendenti**, ciascuno con il proprio ripristino ed esito:

| Componente | Contenuto | Esito accettato |
|---|---|---|
| `indispensabili` | database dell'app e del pool; Brain V3 attivo e 3 run Arena (journal V3 obbligatori) | solo **0** (certificato); altrimenti NO-GO |
| `storici` | Falco e Toro (cervello classico), Brain storico, run V3 preparate, Brain libero, adattivo, ai-data | 0, oppure **3** (integro ma non certificato) |

- **Indipendenza:** un difetto degli storici non impedisce di verificare gli indispensabili. L'esito generale però è OK solo se entrambi sono certificati, ed è NO-GO se uno dei due ha un difetto tecnico.
- **Divisione in parti:** un archivio cifrato oltre `--part-mib`, cioè 90 MiB, si divide in parti `.part000`, `.part001`, … sotto il limite di 100 MB di GitHub. Il manifesto pubblico elenca ogni parte con SHA-256 e dimensione. Verifica remota e ripristino controllano ogni parte e poi il file ricomposto, che resta cifrato.
- **Retention:** si applica separatamente per componente.
- **Compatibilità:** senza `--component` il comportamento è quello di prima (`completo`). Il `run.sh` di produzione non cambia finché non sarà installato con consenso.

## Integrità tecnica e coerenza semantica: esiti separati
Il ripristino ha tre esiti:
- **0, OK:** tutto verificato e certificato.
- **1, FALLITO:** un difetto **tecnico** in cifratura, estrazione, impronte, SQLite, catene e journal V3 obbligatori o file del cervello.
- **3, INTEGRO MA NON CERTIFICATO:** l'integrità tecnica è verificata, ma Falco o Toro hanno anomalie **semantiche** (righe `ANOMALIA SEMANTICA:`). L'archivio li conserva così come sono, senza certificarli. La prova termina con `ESITO PROVA: INTEGRITA' TECNICA OK, SEMANTICA DI FALCO/TORO NON CERTIFICATA` e codice 3: **non** è un successo.

I controlli delle quattro run V3 restano tecnici e rigorosi.

**Contabilità ricostruita dal motore** (`engine.py`, `vault_manager.py`):
- cassa + salvadanaio + (margine + commissione d'apertura delle posizioni aperte) = capitale iniziale + Σ variazioni di cassa dei trade;
- una chiusura vale `max(net, −(margine + commissione d'apertura))`, perché il motore non toglie dalla cassa più del margine anche quando `net` registra una perdita maggiore.

## Diagnostica in sola lettura (Falco e Toro): SUPERATA
**Non più da eseguire:** decisione del proprietario del 21/11 (Falco e Toro conservati come non certificati, nessuna indagine). Le impronte qui sotto si riferiscono a una versione precedente degli script.

Non scrive nulla e stampa solo conteggi, id, date, motivi e importi PAPER aggregati.
```
sudo install -d -m 700 -o root -g root /root/extbackup-diagnosi && sudo install -m 500 -o root -g root /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/restore_external_backup.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/extbackup/diagnosi_classici.py /root/extbackup-diagnosi/ && printf '%s\n' 'c1a8f4b641c4ccacddb7447e49313ef120902020f04d2ee5500ee1fe696771e9  /root/extbackup-diagnosi/restore_external_backup.py' 'f8fa4e295b53c19f292f0c2e9be68224aecc45d8ecb5c8d6382f60f85c548663  /root/extbackup-diagnosi/diagnosi_classici.py' | sudo sha256sum --strict -c - && sudo python3 -I /root/extbackup-diagnosi/diagnosi_classici.py /root/extbackup-diagnosi /opt/superbot-desk-data /root/extbackup-prova-storici-20261120T153630Z.log
```

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
sudo install -d -m 700 -o root -g root /root/extbackup-strumenti && sudo install -m 500 -o root -g root /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/external_backup.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/restore_external_backup.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/backup_app_db.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/scripts/backup_brain.py /home/superbot-agent/brain-unico-lab/wt-ext/deploy/extbackup/prova_storici.sh /root/extbackup-strumenti/ && printf '%s\n' '331d44b4266a719c5ce7854b867b2f0a25b401c8c605cfca349063860753d1ee  /root/extbackup-strumenti/external_backup.py' 'faa73399a7fa2bf28fa7768f73e4fc9978d0b5b7f84739dd1e261b49efca835f  /root/extbackup-strumenti/restore_external_backup.py' '6bd6ebc209400c7a0b222c62690e2c2f11b6f0a927b83fa937a35dcaac0700c6  /root/extbackup-strumenti/backup_app_db.py' '4a92e7daa6cff9fbf339f471656df8ba44067b6927d15b411b50313de0cb5d2c  /root/extbackup-strumenti/backup_brain.py' 'deb7d6c32263f0e0e844506dc467f434cc80973959286bf5e2a51a4a31a80127  /root/extbackup-strumenti/prova_storici.sh' | sudo sha256sum --strict -c - && sudo sh /root/extbackup-strumenti/prova_storici.sh /root/extbackup-strumenti
```
**Esito atteso:**
- inventario con dimensioni, file e sottocartelle;
- riga dello spazio;
- `RISULTATO: OK` di backup e ripristino;
- una riga `journal V3 …: N eventi, catena verificata` per ogni journal;
- una riga `ripristinata …` per ogni archivio;
- `ESITO PROVA: OK`.

Ogni errore produce `NO-GO: …` preceduto da **tutte** le righe `ERRORE:` del passo fallito. In caso di NO-GO restano solo i due registri testuali in `/root/extbackup-prova-storici-<data>.log` (permessi 600): nomi di file, conteggi ed esiti, senza contenuti né chiavi. I dati in chiaro vengono sempre cancellati. La cartella di prova viene cancellata in ogni caso; `/root/extbackup-strumenti` resta e contiene solo gli script.

## Dopo la prova (ciascun punto con un'autorizzazione specifica)
- Aggiornare l'extbackup installato con queste versioni e i percorsi delle run.
- Backup reale con la chiave pubblica del proprietario verso `superbot-backups`. **Attenzione:** `brain.sqlite3` del Brain libero da solo pesa 469 MB, e GitHub rifiuta i file oltre 100 MB, quindi serve dividere l'archivio o usare un altro deposito.
- Ripristino con la chiave privata sul PC del proprietario.
