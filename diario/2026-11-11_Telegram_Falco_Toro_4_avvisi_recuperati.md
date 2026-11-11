# SuperBot RC84 — Telegram Falco/Toro ripristinato 11 novembre 2026

**Problema segnalato:** l'utente vede **due posizioni PAPER aperte su Falco e due su Toro** ma non riceve alcuna notifica Telegram.

## Diagnosi reale dalla VPS

[GitHub Actions #43062323214](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43062323214), SUCCESS, sola lettura:
- FALCO_OPEN_PAPER_POSITIONS=2, TORO_OPEN_PAPER_POSITIONS=2, pause flag assenti.
- Entrambi i processi e gli envfile correnti hanno `ANTHROPIC_API_KEY`, ma **NON** `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
- Le credenziali Telegram originali sono ancora presenti nel vecchio contenitore Docker `superbot-desk-hawk` e nella vecchia configurazione backend. Nuovo processo Brain ugualmente senza Telegram, ma il ripristino in questa fase copre **solo i classici**.
- `backend/desk/notifier.py` esegue un **no-op silenzioso** in assenza del token/chat_id. L'ultimo rekey Claude, completato dall'utente via Termius, aveva riscritto gli envfile Falco/Toro con la sola chiave Anthropic. Questa è la causa confermata dei mancati avvisi.

## Soluzione SENZA riavviare i trader o toccare le 4 posizioni

- PR [Draft #84](https://github.com/alexiptv82/SuperBot-Trading/pull/84), ramo `work/rc84-telegram-paper-alert-relay-20261111`, commit finale `aa52043c3ee0c6f46c5014861d2ed3bf64473390`. Il codice e l'unità sono stati installati **separatamente** dalla versione dei motori correnti; PR non mergiata.
- Nuovo notifier indipendente `/opt/superbot-v3-telegram-relay-code/relay.py` (`deploy/scripts/rc84-paper-telegram-alert-relay.py`); unit systemd attiva `superbot-v3-paper-telegram-alert-relay.service`. Legge ogni **15 s** `state_v2.json` delle **due nuove run PAPER** e `trade_history.jsonl` per chiusure. Non invoca API trading, non possiede accessi Bitget, non scrive state/mandate/journal né effettua riavvii.
- Telegram bot/chat originari recuperati **solo all'interno della VPS** da `docker inspect superbot-desk-hawk` e depositati in `/etc/superbot-v3-paper/telegram-relay.env` con permessi 0600. Nessun segreto stampato in log, GitHub o chat.
- Ledger root-only deduplicato `/opt/superbot-v3-telegram-notifier/sent.sqlite3`. Le posizioni già aperte vengono notificate come **APERTURA — AVVISO RECUPERATO (PAPER)**, non confuse con nuovi ingressi. Da ora in poi le nuove aperture e chiusure PAPER vengono notificate nello stesso canale. Le richieste non accettate vengono riprovate con rate limit; se Telegram riceve una richiesta ma la connessione cade prima del commit, un duplicato può comunque essere possibile (Telegram non offre idempotenza end-to-end).
- Unità con `ProtectSystem=strict`, root service limitato, accesso alle cartelle trader in sola lettura, `ReadWritePaths` esclusivamente nel ledger del notifier, nessun intervento ai PID trader. Verifica attiva di unità PAPER e envfile; se in futuro l'envfile trader abilita notifiche native, il relay si ferma per evitare doppi messaggi. Brain rimane separato e **non ha ancora alert OPEN/CLOSE**.

## Test, tentativi e prova conclusiva

- Primo collaudo offline fallito per assert test su `P&L` anziché testo HTML `P&amp;L`; codice corretto, test adeguato, nessuna modifica VPS.
- Primo deploy #43064461989 ha verificato Telegram `getMe` e 2+2 posizioni, ma è stato **rifiutato con rollback** prima di inviare avvisi: lo script cercava di leggere l'environment di un altro PID mentre la sandbox proibiva `CAP_SYS_PTRACE`.
- [Diagnostica sandbox #43065180489](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43065180489): `PROBE_VALIDATE_WALLETS_ERROR=PermissionError`. Non sono stati concessi ulteriori privilegi: corretta la logica per leggere l'identità dall'unità systemd e dal file AI locale invece dell'environ di altri processi.
- **Rilascio conclusivo [#43065837958](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43065837958), SUCCESS**: 8 test offline PASS; `RC84_TELEGRAM_LEGACY_BOT_VALID=PASS`, `RC84_TELEGRAM_FALCO_POSITIONS_BEFORE=2`, `RC84_TELEGRAM_TORO_POSITIONS_BEFORE=2`, `RC84_TELEGRAM_SANDBOX_PREFLIGHT=PASS`, `RC84_TELEGRAM_PAPER_RELAY_ACTIVE=PASS`, **`RC84_TELEGRAM_RECOVERED_MESSAGES_CONFIRMED=4`**, `RC84_TELEGRAM_NO_TRADING_WORKER_RESTARTS=PASS`, `RC84_TELEGRAM_NO_TRADE_FILE_MUTATIONS=PASS`, `RC84_TELEGRAM_PAPER_NOTIFICATIONS_RESTORED=PASS`.
- Questi 4 sono accettati dall'API Telegram (`ok=true`), **non prova del push visto sul telefono**: l'utente deve confermare di averli ricevuti nella chat Telegram ed eventualmente verificare se la chat è silenziata. Data verifica successo ~17:13 UTC / 18:13 Europe/Rome 11/11/2026.

## Stato/prossimi passi

- 2 posizioni aperte per Falco, 2 per Toro al momento del ripristino, tutti i capitali PAPER e i bot invariati; nessun LIVE, nessun riavvio, nessuna chiusura forzata.
- Al prossimo trade PAPER, verificare la singola notifica di apertura e la chiusura nello storico; se il bot viene riavviato con notifiche native, non lasciare in parallelo il relay.
- Brain ancora senza notifiche Telegram automatiche open/close: implementazione successiva separata, senza alterare Brain decision/risk/exit.
- Evitare ulteriori Actions superflue fino al 1 dicembre (quota minuti); il relay ora funziona autonomamente sulla VPS senza Actions periodiche.

**Non confondere l'API Telegram accettata con la conferma visiva dell'utente.**
