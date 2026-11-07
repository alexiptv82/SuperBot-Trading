# RC73 — chiusura manuale singola PAPER attiva (Singapore, 7 novembre 2026)

**Stato confermato dalla VPS:**
- App `https://superbot-trading.duckdns.org/` aggiornata, autenticazione/sessione originale preservata, dashboard `Classici` ancora a 3 wallet Falco/Toro/Brain e storico `Trade` separato.
- Due servizi `superbot-v3-falco-exit.service`, `superbot-v3-toro-exit.service` **ACTIVE, ma DISABLED** al boot, solo chiusure manuali PAPER (mai nuove aperture). Versione `desk.exit_only` RC73 aggiornata nella directory RC70, con precedente versione conservata.
- Web `TRADING_MODE=paper`, `DESK_MODE=paper`, `TELEGRAM_COMMANDS_ENABLED=false`, `V3_CUTOVER_READONLY=1`, `V3_ALLOW_CLASSIC_SINGLE_CLOSE=1`. **Solo** HTTP POST `/api/desk/close-position` e `/api/desk/bull/close-position` superano il gate generico e richiedono sessione valida (401 senza autenticazione). I comandi `close-all`, `resume`, `reset`, `bot/start`, `brain/close` sono bloccati (423); GET rimangono autenticati.
- Web frontend `Classici`: `Chiudi ora` sulla singola posizione compare soltanto con permesso server e heartbeat del worker exit-only, anche se il vecchio motore è fermo. È richiesta una conferma esplicita per ogni posizione. Il bottone `Chiudi tutte` resta disabilitato; nessuna chiusura automatica per arrivo del giorno successivo.
- Backend `desk_view.py`: directory flock cross-process non bloccante; il secondo click, e i conflitti `close-position` vs `close-all`, ritornano 409 senza riscrivere un flag già in coda. Worker `desk.exit_only` usa lo stesso lock mentre consuma il file. Chiusure su posizioni inesistenti: 404. Worker spento: 409 senza creare flag. Posizione e storico vengono aggiornati solo dall'esecutore PAPER dopo controllo di prezzo 1m fresco <=120 secondi.
- Lo storico deve aggiungere `closed_by=utente`, profitto netto e costi, e `manual_learning` con `profit_protection_example`, `loss_reduction_example` o `break_even_example` in funzione dell'esito reale. Non promuovere il singolo esempio a strategia automaticamente.
- Brain V3 PAPER con run 2.000 USDT **ancora in pausa**, nessuna posizione; l'endpoint chiusura Brain non è sbloccato finché il runner non è stato collaudato e attivato.

## Evidenze

| Prova | Riferimento | Esito |
|---|---|---|
| Test concorrenza e doppio tap su dati sintetici | [RC73 queue test #42377385160](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42377385160) | 84 PASS |
| Regressione finale backend/UI | [RC73 #42377741276](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42377741276) | 122 backend + 85 frontend PASS; build React PASS |
| Fonte prezzi PAPER Bitget API 1m su VPS | [RC73 price readiness #42377805776](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42377805776) | 8/8 posizioni, 6/6 simboli unici freschi; nessun ordine |
| Attivazione soli worker exit-only | [RC73 #42378126580](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42378126580) | SUCCESS: 2 service ACTIVE/DISABLED, nessun comando, 6+2 storici intatti |
| Cutover autenticato e smoke pubblico | [RC73 #42378313198](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42378313198) | SUCCESS: solo single-close 401 senza token; close-all/avvio/Brain 423 |
| Audit indipendente della VPS dopo cutover | [RC73 #42378505277](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42378505277) | **PASS**: 6+2 posizioni e 8 storici invariati, unità/heartbeat pronti, auth/JWT invariati, rollback web disponibile |

Il *commit esatto installato nell'app* è `48be5cc51688e7be921942203e19d7be17ddb702`; i commit successivi sul ramo di lavoro documentano e verificano la release e non mutano il runtime già installato.

## Operatività utente sul telefono

1. Aprire normalmente `https://superbot-trading.duckdns.org/` e accedere con le credenziali abituali.
2. `Classici → Falco` o `Toro`: trovare la singola posizione, premere `Chiudi ora`, controllare simbolo e dettagli, confermare `Sì, chiudi`. Solo la conferma crea la richiesta PAPER; NON premere ripetutamente in caso di ritardo.
3. Controllare la scomparsa della posizione dagli aperti, il `last_action` e la registrazione in `Trade → Falco/Toro` fra i chiusi. Il prezzo/pnl finale non è garantito uguale al PnL latente precedente; sono necessari dati 1m recenti. Se manca il prezzo, la posizione resta aperta e l'app deve riportare il fallimento.
4. Ripetere selettivamente per gli altri trade soltanto se desiderato. **Nessuna posizione è stata chiusa dall'assistente in questa fase.**

## Istruzioni di emergenza, rollback e prossime fasi

- Kill switch operativo dei soli servizi: `systemctl stop superbot-v3-falco-exit.service superbot-v3-toro-exit.service` (non riavviare gli storici). Sul web, sostituire `V3_ALLOW_CLASSIC_SINGLE_CLOSE=1` con `0` in un cutover protetto oppure ripristinare il vecchio container web `superbot-rc73-previous` e la build `/opt/superbot-web/build.rc73-previous`. Non cancellare il DB di login.
- Backup locale certificato RC69: `/opt/superbot-backups/rc69-paper-legacy-20261107T110255Z-142218`. Backup SQLite web RC73 e prova restore. **Backup esterno ancora non disponibile**, non considerarlo esistente.
- Dopo la chiusura verificata delle posizioni storiche, una fase distinta potrà archiviare run e inizializzare nuovi conti PAPER: Falco 1.000, Toro 1.000, Brain 2.000; conservarne tutti gli storici e gli esempi manual-learning. Nessun reset automatico autorizzato qui.
- RESTA da completare e testare: uso diretto dell'app da smartphone (PWA/cache, pulsanti), activation della run Brain e meccanismi AI DeepSeek/Claude, piena parità di chiusura per Brain quando operativo. **Nessun merge, nessun restart dei due bot trading storici, nessuna nuova apertura PAPER.**
