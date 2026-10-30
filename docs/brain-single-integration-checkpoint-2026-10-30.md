# Brain single account — checkpoint integrazione offline 30/10/2026

## Perimetro e sicurezza

- Ramo: `work/brain-single-integration-20261030` derivato da `work/manual-teaching-deepseek-20261030` (base `168cb9f127f43d349570edeb1cdc47eb9bf38bd3`). Non e' un merge su `main` o `rule-pool`.
- Il servizio **non e' avviato** e non e' installato sul VPS. Nessuna API a pagamento, nessun ordine, reset, import da Brain Free / Falco / Toro, nessuna modifica agli storici.
- `service.py` richiede `DESK_MODE=paper`, `BRAIN_SINGLE_ENABLED=paper`, mandato finanziario completo e prezzi token dichiarati esplicitamente: non prende 2000 USDT / 1600 USDT dalle fixture di test.
- `--initialize-new` richiede `BRAIN_INIT_ACK=CREATE_NEW_EMPTY_PAPER_ACCOUNT` e una cartella vuota. `--serve` richiede un nuovo backup verificato prima del primo tick e `BRAIN_SERVE_ACK=PAPER_ONLY_EXPLICIT_START`. Questi sono gate nel codice, NON autorizzazioni gia' concesse al deploy.

## Lavoro implementato

1. `market_bridge.py`: riusa feed PUBBLICO Bitget di Brain Free; dati mancanti restano mancanti. Backfill 1m limitato a massimo 200 barre da endpoint storico V2, restituisce solo serie causali complete e lascia il motore in quarantena in caso di dati parziali.
2. `transports.py`: DeepSeek `deepseek-flash` e ragionamento `high`; Claude opzionale solo come revisore selettivo (mai fallback a regole), nome modello e chiave espliciti. Timeout e max output, tetto input in byte, prenotazione conservativa del costo massimo primario+revisore. Prezzi e budget in ambiente obbligatori, nessun costo fatturato realmente misurato qui.
3. `service.py`: loop 5s del proprietario unico del wallet SQLite PAPER, supervisore AI asincrono gia' collaudato, snapshot v2 pubblicato ogni 5s. No apertura se dati, mandato, cost policy, identita' conto o backup non rispettano i gate.
4. `operator.py`: chiusure PAPER manuali solo tramite owner thread e con ID posizione/quote fresche; `all` atomico in una transazione, evita replay su posizione nuova; registra `trade_closed` con fonte `manual_user` e ricevuta. Le lezioni sono una fase successiva, recuperabili dalla transazione nel database.
5. `telegram_commands.py`: parser soltanto offline di update Telegram gia' autenticati (chat ID e user ID), clock 2min, idempotenza persistita prima della mutazione. Richiede /chiudi **brain** BTCUSDT motivo=profitto_ok oppure /chiudi **brain** all motivo=profitto_ok: l'ambito globale implicito e' rifiutato. /insegna_si e /insegna_no accettati soltanto per eventi PAPER verificati. **Non e' stato implementato/avviato alcun getUpdates poller su Telegram**.
6. `ManualLessons`: log append-only, raggruppamento 5m, TTL 2h, nessuna promozione automatica nel prompt; 20 esempi non sono prova di profitto, l'apprendimento operativo richiede un futuro OK.

## Test e risultati

- Run `41034998490`: SUCCESS Python3.10/3.11: **175 unit test motore** e **22 pytest nuovi** per interprete, comprese chiusure manuali, autorizzazione update, nonce replay, saldo finanziario obbligatorio e quote stale.
- Ramo PWA separato `work/brain-single-app-20261030` aggiornato al commit `22f9394cff2c21755747c9aa1d6d97f89fdbcd64`, run `41034603881` SUCCESS backend/frontend con producer pin al commit `11ca3610487b5613e3067395f3894ecefa3c25d5`. La struttura snapshot v2 e' compatibile; **PWA non deployata**.
- Fix DeepSeek sul ramo base, CI `41032428460` SUCCESS 53 test per interprete. La verifica del saldo e l'avviso Telegram sono per Brain Free: non confondere con le notifiche operative del nuovo Brain Scalp, che devono ancora essere collegate.

## Bloccanti per rilascio

1. Approvazione esplicita del mandato reale del nuovo conto unico (capitale, margine, slot, rischio trade e aggregato, daily stop, kill equity, altri limiti). I test 2000/1600 sono SOLO fixture.
2. Conferma dei prezzi correnti token DeepSeek e Claude, modello revisore, budget disponibile, segreti configurati senza esposizione. Budget prenotato e' limite preventivo, non rendicontazione fatturata.
3. Test end-to-end su alimentazione pubblica reale in staging/ambiente autorizzato, gap repair, interruzioni API e rate limits (il CI usa mock senza rete).
4. Un SOLO Telegram update consumer per chat/token, con lock e autorizzazione, worker di rete separato dal tick finanziario; outbox e notifica di esito effettivo. Il parser offline **non** abilita comandi Telegram nel bot.
5. Build e distribuzione separate del producer Python e della PWA React senza fondere rami con storia diversa; backup restore verificato, no doppie istanze, nuovo OK al deploy.
6. Controllo dashboard stale, metriche/P&L reali PAPER, tolleranza a stop e flussi interrotti durante la prova operativa.
7. Classici accantonati; il ramo di teaching classici e' separato e non attivo. Nessun rollback della strategia o del lettore regime non idoneo.

## Fonti tecniche pubbliche

- Bitget V2 storico candele futures: `/api/v2/mix/market/history-candles`, massimo 200 per richiesta.
- Claude Messages API: `/v1/messages`, `anthropic-version: 2023-06-01`.
- I test API del presente ramo sono mock: le fonti documentali non sostituiscono la verifica end-to-end in staging.

AI: chatgpt (chat normale)
