# Risultato audit remoto — 18 ottobre 2026, 09:50 Europe/Rome

Branch isolato: work/backend-singapore-audit. Nessuna modifica operativa ai VPS.
Ultima esecuzione: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/39109165046

## Singapore
- Accesso SSH verificato tramite known_hosts già predisposto; comandi eseguiti in sola lettura.
- Hawk/Bull running e healthy, restart count 0. DESK_MODE confrontata con paper: true; con live: false.
- Heartbeat aggiornati ogni pochi secondi, mount dedicati corretti. Zero posizioni aperte al campione.
- Codice cli.py e engine.py nei container identico agli hash del branch rule-pool ispezionato.
- Giorno persistente di entrambi: 2026-10-18. Limite daily_stop persistente 0.12; run Hawk 3, Bull 2.
- Hawk: 111 trade JSON e 1835 eventi AI; Bull: 46 trade e 2447 eventi AI. Nessuna riga completa non valida; file stabili durante lettura.
- Backup cutover presente, 310711 byte, 24 file regolari. SHA256 archivio: 9b35c626213ca13cc2c90bc8aaeda2cd541be158a7d6880f8870232bc8a44c95.
- Tutti e quattro gli storici trade/AI del backup sono prefissi byte-esatti dei file attuali: dati pre-migrazione conservati e nuovi dati aggiunti.
- Copie database cutover e ripristinata: 65536 byte, integrity_check OK su copie in memoria, 6 tabelle, nessun WAL rilevato; hash esposti nei log coincidono (parzialmente mascherati da GitHub).
- Nessun file estratto o scritto sui VPS. Questa verifica del backup esistente non sostituisce un backup coerente aggiornato pre-intervento e un restore completo isolato.

## Strasburgo
Job fermato prima della connessione: SSH_KNOWN_HOSTS assente. Chiave di autenticazione presente ma non esposta.
Nessun known_hosts per Strasburgo presente nelle home root/ubuntu di Singapore.
Contesto precedente: impronta del sistema normale vista ma esplicitamente non verificata indipendentemente; non utilizzata come trust.
Serve impronta pubblica ottenuta da console web/KVM OVH autenticata, senza reboot/rescue. Comando read-only: ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub.

## Questioni aperte
App non ancora corretta; backend ancora da ispezionare direttamente. HI-TV non toccato e verifica end-to-end non completata.
Assenza globale writer duplicati, scheduler e listener Telegram non ancora certificata.
Stop giornaliero: giorno aggiornato; comportamento completo da verificare con codice e stato effettivi. Nessun reset.
Tentativo test locali selezionati non eseguito: pytest non installato. Script audit compilato con py_compile e workflow eseguito su Singapore.

Prossima modifica operativa richiede consenso distinto dopo audit Strasburgo, backup verificati e piano rollback.
