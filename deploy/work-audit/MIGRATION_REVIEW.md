# SuperBot — verifica e intervento app proposto
Aggiornato il 18 ottobre 2026, 09:35 UTC. Stato: analisi e backup completati; collegamento applicativo NON ancora modificato. Questo documento non è uno script di deploy.

## Risultati verificati
Accesso SSH confermato ad entrambi i VPS attraverso GitHub Actions, utilizzando i segreti esistenti e controllo rigoroso della chiave host. Nessuna chiave privata estratta o pubblicata. La connessione SSH diretta da questo ambiente non è disponibile.

A Singapore Hawk e Bull sono attivi, sani e in PAPER; un motore per portafoglio. I rispettivi bind mount puntano alle cartelle operative corrette. Nell'audit gli heartbeat avevano età di pochi secondi. Gli storici trade e AI del cutover sono prefissi byte per byte degli storici attuali, che hanno continuato a crescere. Il database ripristinato ha superato integrity_check.

A Strasburgo i tre container motore desk sono fermi con restart=no. Il backend dell'app è attivo ma legge le vecchie cartelle locali: questa è la causa degli stati obsoleti/offline nell'app. Il suo codice corrisponde al main 41a418265fb37612282486d84eb6a9d4d9a6c58f. TRADING_MODE è paper, mentre DESK_MODE del backend è live: questo flag dell'interfaccia va corretto; non dimostra da solo esecuzioni reali.

Il database corrente di Strasburgo è integro ma diverso dalla copia trasferita a Singapore. Va conservato come autorità per autenticazione e sessioni. Non sovrascriverlo con il database del cutover.

HI-TV è attivo e sano. Il suo endpoint HTTPS /api/ risponde 200; la homepage 404 non indica un guasto. Il proxy Nginx è condiviso: la proposta seguente non richiede modifiche né reload di Nginx.

## Backup già verificati
Run GitHub Actions: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/39115392774

| VPS | Copia protetta | Controlli |
| --- | --- | --- |
| Strasburgo | /root/superbot-work-backups/20261018T092724Z-12de44ad | 109 elementi, archivio 1023033 byte, restore e SQLite OK |
| Singapore | /root/superbot-work-backups/20261018T092725Z-984794a4 | 26 elementi, archivio 304731 byte, restore e SQLite OK |

Le copie comprendono dati Hawk/Bull, storici e memoria AI, database e metadati protetti; a Strasburgo anche codice backend attivo, frontend e configurazione proxy pertinente. Manifest SHA-256 e ripristino in directory separate verificati. File e archivi privati: permessi 600, directory 700. Nessuna copia di segreti nei log o negli artifact Actions. Snapshot dei file bot verificato stabile prima/dopo la lettura, database copiato con SQLite online backup. Nessun originale o servizio modificato per creare queste copie.

## Intervento operativo richiesto — ancora da autorizzare
1. Preparare e testare su dati sintetici il gateway e l'inoltro; nessun test invia comandi ai bot. Verificare compatibilità di tutte le rotte desk, risposte e autenticazione prima dell'attivazione.
2. Avviare a Singapore una sola API desk separata, senza engine, polling Telegram o credenziali di trading. Usare le cartelle operative esistenti di Hawk/Bull; nessuna copia di stato bidirezionale. L'API espone letture e comandi già presenti nell'app, con autenticazione interna. Imporre PAPER; nessuna modalità live.
3. Creare un canale SSH persistente dal vecchio VPS alla sola porta API locale di Singapore. Chiave nuova dedicata, senza shell interattiva e limitata alla destinazione del tunnel. Verifica della chiave host già fidata; API non pubblicata su Internet.
4. Aggiornare soltanto il backend SuperBot sul vecchio VPS: autenticazione e database correnti rimangono sul posto; tutte le richieste /api/desk vengono inoltrate a Singapore dopo il controllo della sessione esistente. Nessuna credenziale utente trasmessa al gateway. In caso di guasto del canale, errore esplicito e nessun ripiego sui vecchi dati. L'indirizzo del tunnel deve essere raggiungibile dal container backend senza esporre una nuova porta pubblica: verificare la rete Docker e predisporre un accesso privato dedicato prima del passaggio.
5. Impostare DESK_MODE=paper per il backend dell'app. Conservare immagine, comando e configurazione precedenti per ritorno immediato. Arrestare il backend precedente prima di avviarne il sostituto per evitare duplicazione del listener Telegram. Possibile breve indisponibilità del solo login/API SuperBot; nessun riavvio VPS o HI-TV.
6. Validare la risposta pubblica e autenticata, heartbeat freschi su più cicli, corrispondenza stato/storici con Singapore, assenza di motori duplicati e PAPER. Controllare HI-TV senza modificarlo. Non eseguire pause, resume, reset, close-all o ordini come test.
7. La prova finale nell'app Android potrebbe richiedere soltanto l'apertura dell'app da parte dell'utente: non è disponibile controllo diretto del suo telefono. Verificare se sia la PWA osservata o un wrapper prima di promettere assenza di aggiornamento APK.

La preparazione del codice e i test del nuovo collegamento non sono ancora completati: l'autorizzazione riguarda questo intervento circoscritto, con attivazione subordinata ai test e ai controlli preliminari. Non autorizza modifiche ai motori o agli stati.

## Piano di ritorno
Se la verifica prima del passaggio fallisce, lasciare il backend pubblico invariato e non attivare il collegamento.
Se fallisce dopo il passaggio, ripristinare immagine e configurazione precedenti del solo backend mantenendo il database corrente; rendere indisponibili esplicitamente le rotte desk finché il collegamento non è sano, senza usare le vecchie cartelle come dati correnti. Disabilitare il nuovo servizio e il tunnel dopo aver fermato l'inoltro. Non ripristinare snapshot sopra i dati Singapore e non riavviare i vecchi motori. Conservare tutte le copie e gli originali. Un eventuale ripristino dati per corruzione richiede un intervento distinto.

## Limiti della verifica
Nessun test su ordini reali. Nessun reset degli stop, budget, run, database o memoria AI. Il controllo cron/systemd svolto in rescue ha esaminato file regolari, saltando symlink: non costituisce da solo una prova esaustiva dell'assenza di scheduler. Inventario Docker e processi attuali ha trovato i due motori operativi solo a Singapore. La migrazione dei motori è verificata; la migrazione complessiva rimane aperta fino al collegamento e alla verifica dell'app.
