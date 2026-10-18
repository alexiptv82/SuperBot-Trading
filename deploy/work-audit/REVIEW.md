# Audit backend SuperBot, 18 ottobre 2026 — preparazione locale

Documento storico superato. Per risultati verificati, backup e intervento proposto leggere [MIGRATION_REVIEW.md](MIGRATION_REVIEW.md).

Nessun file di questa directory è stato pubblicato o eseguito sui VPS.

## Evidenze attuali
- Repository letto: rule-pool a47ea407 e main 41a41826. Il codice main contiene desk_api.py/desk_view.py e il messaggio Android osservato; non assumere che rule-pool coincida con il backend distribuito.
- HTTPS pubblico superbot-trading.duckdns.org risponde. /api/health: status=ok, mode=paper, desk_mode=live, build=2026-10-15-live-needs-live-bot.
- /api/desk/health e /api/desk/bull/health: HTTP 200, available=true, bot_online=false, version=b4709d1. Hawk halt=stop giornaliero raggiunto; Bull halt=null. Sono dati del backend, non verifica diretta Singapore.
- /api/desk/status e /api/desk/bull/status restituiscono 401 senza sessione.
- Il repository configura una PWA; il manifest pubblico è disponibile. Non è ancora verificato se l'installazione Android sia questa PWA o un wrapper.
- Nginx del repository indirizza /api a localhost:8002 sul vecchio host. La configurazione distribuita va ispezionata.
- main: desk_view.py considera heartbeat vecchio oltre 300 secondi offline; desk_api.py legge stati e scrive comandi su directory locali.
- Workflow desk-status.yml non è realmente solo lettura: include auto-restart. Non eseguirlo.
- Rete diretta ai due IP: Network is unreachable. HTTPS pubblico invece raggiungibile. Nessuna chiave SSH locale o agente.
- GitHub Actions: precedenti controlli sui due VPS riusciti il 17 ottobre; validità attuale dei segreti/accessi non confermata. Le chiavi non vanno estratte.

## Prossimo intervento da autorizzare
Pubblicare su branch isolato basato su setup/singapore-vps-readonly un workflow dedicato che esegua soltanto backend_readonly.py sui due VPS, usando i segreti SSH già configurati in Actions. Nessun trigger di deploy, riavvio, container nuovo, scrittura dati o modifica nginx. Per Singapore usare SINGAPORE_SSH_KNOWN_HOSTS e verifica host rigorosa. Per Strasburgo recuperare una fingerprint fidata: non trattare ssh-keyscan come verifica indipendente.

Il programma qui preparato raccoglie solo metadati selezionati. Non prova da solo l'assenza di writer duplicati: servono anche inventario scheduler/systemd/processi con argomenti filtrati e codice effettivamente distribuito. Non è un backup né una verifica di restore.

## Scelta architetturale da chiudere dopo audit
Mantenere l'origine HTTPS dell'app e autenticazione esistente. Valutare API desk dedicata a Singapore, senza avvio dei motori nel processo API, dietro canale autenticato. Letture e comandi devono raggiungere la stessa autorità Singapore. Nessuna sincronizzazione bidirezionale di stati, nessun riavvio dei vecchi Hawk/Bull, nessun cambio globale DNS che coinvolga HI-TV. Nessuna modifica operativa è ancora autorizzata.

## Prerequisiti prima di modificare servizi/configurazioni
1. Verificare un solo motore scrivente per portafoglio, PAPER effettivo, task schedulati e listener Telegram; HI-TV intatto.
2. Preparare backup coerenti di tutti i dati Hawk/Bull, archivi, memoria AI e database (SQLite online backup o snapshot coerente), codice/configurazioni e proxy. Un elenco o hash di file che cambiano non è uno snapshot coerente.
3. Manifest SHA-256 del backup e ripristino isolato senza rete e senza motori; integrity_check, schema/conteggi SQLite, JSON/JSONL e continuità storici. Proteggere configurazioni contenenti segreti; non pubblicarle su repository, log o artifact Actions.
4. Acquisire consenso sull'intervento preciso solo dopo backup verificati. Nessun reset, close-all, resume o abilitazione live come test.
5. Rollback: ripristinare solo routing/configurazione backend precedente; dati operativi Singapore rimangono l'autorità e non vengono sovrascritti da copie vecchie. Vietato riavviare i motori Strasburgo durante rollback backend.
6. Verifica: autenticazione/sessioni/WebAuthn, stato fresco per più cicli, API/app coerenti, ordini sempre simulati, protezione posizioni durante halt, reset giornaliero, Telegram senza listener duplicati, endpoint HI-TV osservato senza modifiche.

Limite attuale: nessun backup remoto creato/verificato in questa sessione; nessuna correzione applicata; migrazione non chiusa.
