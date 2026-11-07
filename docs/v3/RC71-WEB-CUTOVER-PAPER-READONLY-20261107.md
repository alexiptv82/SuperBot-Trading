# RC71 — nuova dashboard V3 pubblicata in PAPER READ-ONLY (7 novembre 2026)

**Stato: web pubblicato con autenticazione originale, CI PASS, trading NON riavviato, nessuna chiusura.**
**Ambito:** upgrade solo app web, con DB login persistente e rollback. Le PR e la V3 rimangono DRAFT e non sono state mergeate.

## 1. Prova di pubblicazione

- Release **esattamente dal commit `fb4c200cb9aef5068dbe195df385d715c9b4f453`** del ramo `work/v3-rc71-safe-web-cutover-20261107`. Il ramo può aver ricevuto commit successivi di workflow di audit, senza cambiare l'app installata.
- [Deploy controllato GitHub Actions #42372319817](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42372319817): SUCCESS. Build frontend same-origin, dry-run preflight obbligatorio, creazione nuova immagine, backup SQLite online + restore integrity, sostituzione del **solo container web**, frontend atomico, verifiche API/prod, rollback automatico in caso di errore.
- [CI RC71 #42372319840](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42372319840): frontend **52 test / 5 suite** e build production PASS; backend **23 test guard + 79 regressioni** PASS.
- [Audit indipendente successivo #42372616899](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42372616899): PASS su risorse reali della VPS.
- Test pubblico HTTPS dalla runner: root `https://superbot-trading.duckdns.org/` raggiungibile, `/api/health` risponde PAPER e `/api/v3/overview` risponde 401 senza token. Non sostituisce un login reale da smartphone.

## 2. Continuità account e conservazione della vecchia versione

- Database originale **non sostituito né copiato nello staging**: nuovo backend monta lo stesso `/opt/superbot/data/superbot.db` e la stessa configurazione di autenticazione. Audit indipendente verifica uguaglianza di **password hash, versione token e chiave JWT** fra backup SQL prima del cutover e stato attuale, senza mai stampare valori.
- Il backup applicativo RC71 è sotto `/opt/superbot-backups/rc71-app-db-*/superbot.db` (nuova directory privata), con `PRAGMA integrity_check` e prova lettura. Gli storici Falco/Toro sono inoltre salvati nello snapshot locale RC69 certificato, 38+36 file e restore test.
- Vecchio web container `superbot-rc71-previous` conservato **stopped/restart=no**, vecchia build frontend `/opt/superbot-web/build.rc71-previous` conservata. Non sono stati cancellati.
- Reverse proxy nginx pubblico mantiene lo stesso HTTPS e lo stesso backend loopback `127.0.0.1:8002`, con codice frontend/Backend V3 aggiornato.

## 3. Condizioni obbligatorie, verificate POST-DEPLOY

- `TRADING_MODE=paper`, `DESK_MODE=paper`, `TELEGRAM_COMMANDS_ENABLED=false`, `V3_BRAIN_PEER_OBSERVATIONS=disabled`, `V3_CUTOVER_READONLY=1` nel web in produzione.
- Il middleware `backend/v3/cutover_gate.py` blocca tutte le mutazioni HTTP dei prefissi `/api/bot`, `/api/desk`, `/api/v3`, `/api/brain`, `/api/supervisor` con risposta HTTP **423**. Login, WebAuthn, cambio password e chiamate GET restano permessi. Il blocco è temporaneo, solo per il collaudo della nuova dashboard; non è un motore di trading.
- `superbot-desk-hawk` e `superbot-desk-bull` sempre stopped + restart=no + pause.flag presente; **6+2 PAPER storici ancora aperti**, nessuna richiesta close/reset pendente.
- `superbot-v3-falco-exit.service` e `superbot-v3-toro-exit.service` installati ma **DISABLED+INACTIVE**; quindi manual-close non disponibile finché il collaudo autenticato non è completato.
- Brain nuova run **2.000 USDT PAPER, PAUSED e mandate non approvato**, montata in sola lettura per la dashboard; non viene avviato alcun processo analista/esecutore. In assenza di quotazioni affidabili o strategie realmente in esecuzione l'app deve mostrare indicatori di assenza dati, non prezzi fittizi.
- Il vecchio app container è stato sostituito e rimane come rollback; **non** è stato riavviato nessun container motore di trading.

## 4. Prova che deve fare l'utente sul telefono (non ancora verificata)

1. Aprire `https://superbot-trading.duckdns.org/` oppure l'app PWA. Se la versione vecchia resta in cache, aprire il dominio da Chrome e aggiornare la pagina. Non cancellare automaticamente i dati del sito, per non perdere la sessione.
2. Verificare login con **le credenziali esistenti** (o sessione già attiva). L'audit certifica chiave JWT invariata ma non può collaudare il telefono dell'utente.
3. Confermare tre schede con la stessa grafica: **Falco, Toro e Brain**; posizioni aperte Falco 6, Toro 2, Brain run preparata in pausa; leva, margine, TP/SL, PnL e storico solo se i dati sono disponibili e attendibili.
4. **Non tentare di chiudere i trade** finché il sistema dichiara collaudo read-only. Qualsiasi azione di apertura/chiusura/reset deve essere bloccata. Segnalare schermate vuote, errori di login o dati incongruenti.
5. Dopo conferma utente: nuova fase tecnica separata per abilitare esclusivamente la **chiusura manuale PAPER** con workers exit-only e API autorizzate, verificando ancora snapshot, ownership e comando/risultato su dataset di test. L'utente sceglierà in app se/quale dei 6+2 trade chiudere.

## 5. Rollback (non eseguito)

In caso di errore grave, tornare al vecchio web container preservato e rimettere `/opt/superbot-web/build.rc71-previous` sul percorso `build`. **Prima** verificare le condizioni attuali e il nome dei container; non avviare i motori Falco/Toro. Non ripristinare automaticamente il backup del database se lo stesso DB originale è integro: farlo cancellerebbe eventuali modifiche legittime intervenute dopo la copia.

## 6. Rimanenti gate V3

La pubblicazione dell'interfaccia non significa che Brain, Toro e Falco stiano già facendo trading. Restano la conferma login/visibilità mobile, il collaudo delle chiusure manuali, i processi reali della nuova run PAPER e la validazione dei collegamenti AI, mantenendo separati capitali, rischi e storici. Il backup esterno cifrato è ancora una miglioria raccomandata; l'attuale copia è **locale** sulla stessa VPS.
