# SuperBot — collegamento Singapore completato lato server
18 ottobre 2026, verifica conclusiva alle 12:32 CEST (10:32 UTC).

## Risultato
Hawk e Bull continuano a funzionare a Singapore esclusivamente in PAPER. L'app usa lo stesso indirizzo HTTPS e la stessa autenticazione, ma ora tutte le richieste desk raggiungono le directory operative Singapore tramite un canale privato cifrato.

Il vecchio VPS conserva frontend, autenticazione e database corrente. La migrazione dei motori e il collegamento server dell'app sono completati e verificati. Resta la prova visiva sul telefono Android, non controllabile dagli strumenti disponibili.

## Topologia applicata
- Strasburgo: Nginx/TLS e HI-TV invariati; container API SuperBot sostituito mantenendo immagine, database, ambiente e mount precedenti, aggiungendo l'inoltro autenticato e DESK_MODE=paper.
- La nuova rete Docker privata superbot-app-link collega il solo backend e il contenitore che mantiene il namespace del tunnel. Nessuna nuova porta è pubblicata sul vecchio host. Il tunnel ascolta nel namespace privato, non sulle interfacce pubbliche del VPS.
- Servizio systemd superbot-api-tunnel.service attivo e abilitato; chiave SSH dedicata limitata al canale API, origine limitata al vecchio VPS, destinazione verificata con known_hosts fidato. Le chiavi temporanee dei tentativi precedenti sono state revocate; una nuova autenticazione con la chiave attiva è stata verificata.
- Singapore: nuova API superbot-desk-api, pubblicazione solo 127.0.0.1:18002, un processo API, senza engine o listener Telegram e senza credenziali private exchange nel processo. Usa le due directory già operative, senza copiare indietro stati.
- Gli errori del canale restituiscono 503; nessun ripiego sui dati vecchi. I comandi non sono ritentati automaticamente. Per i comandi l'API verifica heartbeat fresco e modalità PAPER.
- Persistenza verificata: API vecchio VPS restart=always; gateway Singapore e namespace del tunnel restart=unless-stopped; servizio SSH Restart=always. Nessun riavvio aggiuntivo dei VPS eseguito.

## Verifiche passate
1. Nove test isolati: autenticazione, separazione Hawk/Bull, letture senza modifiche, inoltro dei comandi su dati sintetici, nessun inoltro di bearer/cookie al gateway, errore senza fallback o retry, rifiuto di comandi con bot offline/live, conservazione della configurazione e negoziazione Docker.
2. 34 richieste GET autenticate verso backend locale e HTTPS pubblico, ripetute nella verifica finale. Stato, trade, performance, diario, run, lezioni, orari e overview disponibili. Richieste senza sessione rifiutate correttamente.
3. /api/health conferma mode=paper e desk_mode=paper. /api/desk/health e /api/desk/bull/health rispondono 200, bot_online=true, intestazione x-superbot-desk-source=singapore.
4. Heartbeat avanzati tra due osservazioni; nel controllo finale gli stati autenticati mostravano heartbeat vecchi di 1–4 secondi.
5. Identificativi container dei due motori e restart count invariati (zero riavvii). Vecchi motori desk a Strasburgo fermi con restart=no. Nessun motore è stato avviato dal nuovo processo API.
6. Run e limiti preservati: Hawk run 3, Bull run 2; daily_stop=0.12 per entrambi; day_start_equity invariata rispettivamente 896.369985416869 e 1066.178801047889.
7. Storici trade e learning_log precedenti all'intervento sono rimasti prefissi identici dei file attuali. Già verificata anche la continuità byte per byte rispetto al cutover originale. Memoria AI e storici non azzerati.
8. SQLite integro; hash dello stato di autenticazione e delle credenziali biometriche invariato. Nessuna password cambiata, credenziale eliminata o versione delle sessioni incrementata.
9. HI-TV: stesso container e restart count, ancora in esecuzione; endpoint pubblico /api/ HTTP 200. Fingerprint delle configurazioni Nginx invariate.

Nessun ordine, pause, resume, close-all, reset-budget o reset-portfolio è stato inviato ai bot reali durante le prove. L'attività di trading futura non è simulata da questi controlli: sono stati verificati servizio, continuità dati, modalità e collegamento.

## Backup e ritorno
Ultime copie prima del passaggio, entrambe con ripristino isolato e integrity_check passati:
- Strasburgo: /root/superbot-work-backups/20261018T102616Z-cfa79c97
- Singapore: /root/superbot-work-backups/20261018T102620Z-c4ae7a2b

Restano disponibili anche i backup precedenti. Directory 700 e file 600, nessun archivio di dati privati caricato su GitHub. Queste copie risiedono sui rispettivi VPS; non sono una copia indipendente fuori host.

Release attiva su entrambi: /opt/superbot-app-link/releases/r39119231791a1, indicata anche dal link protetto /opt/superbot-app-link/current. Il backend originale è conservato fermo come superbot-work-rollback-r39119231791a1, restart=no. Anche immagini e configurazioni originali sono conservate.

Il ritorno previsto ferma il backend sostitutivo prima di avviarne un altro, riprende l'immagine e la configurazione salvate con un piccolo wrapper che mantiene indisponibili le rotte desk (503) per evitare dati obsoleti. Autenticazione e database corrente rimangono sul posto. Poi si fermano il nuovo canale e il gateway, se necessario. Non si ripristinano snapshot sopra i dati Singapore e non si riaccendono i vecchi motori.

La procedura automatica di ritorno era predisposta nel workflow del passaggio; non è stata necessaria durante l'attivazione riuscita. I primi due tentativi si erano fermati prima dell'attivazione pubblica: compatibilità Docker, poi raggiungibilità della rete del container. Risolti usando l'API Docker corrente e la rete privata dedicata, senza modificare il firewall di HI-TV.

## Prossimi rilasci
I vecchi workflow non sono compatibili con la nuova topologia:
- main/deploy.yml ora si ferma prima di qualsiasi modifica se rileva /opt/superbot-app-link: impedisce di cancellare l'inoltro e ripristinare dati vecchi nell'app.
- desk-deploy.yml su main e rule-pool blocca il deploy dei motori sul vecchio hostname: impedisce di riaccendere Hawk/Bull a Strasburgo.
Queste sole protezioni sono state registrate con [skip ci], senza avviare i vecchi deploy o toccare servizi.
Un futuro rilascio applicativo o dei motori deve usare una procedura compatibile con Singapore; non rimuovere i blocchi per riutilizzare il vecchio deploy. Il workflow di migrazione è specifico di questo passaggio e non va rilanciato su un sistema già collegato.

Commit protezioni main: 442583d6a97f3ec0c20285095ff330d10b864379
Commit protezioni rule-pool: c6749d1ec244046f0040e33618fbdced0bc4f84f

## Evidenze
- Attivazione e prove: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/39119231791
- Nove test e verifica finale della persistenza: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/39119640565
- Osservazione finale servizi, sola lettura: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/39119640531
- Codice di integrazione e strumenti: deploy/work-audit/app_link, app_link_remote.py, deploy_app_link.py.
- Nessun accesso SSH diretto da Work presunto: tutte le operazioni remote sono avvenute tramite gli accessi Actions verificati, senza estrarre le chiavi.

## Ultimo controllo utente
Chiudere e riaprire l'app Android e verificare entrambi i portafogli online con dati aggiornati. Indirizzo, password e credenziali biometriche restano quelli attuali. Non risultano necessarie modifiche DNS o alla configurazione dell'app. Non è stato verificato direttamente se l'app installata sia la PWA pubblica o un wrapper: eventuali problemi della schermata vanno distinti dalle API server già verificate.

