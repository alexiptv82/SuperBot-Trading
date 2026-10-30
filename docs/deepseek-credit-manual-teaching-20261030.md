# 30 ottobre 2026 — DeepSeek credito + insegnamento chiusure manuali (offline)

Ramo: `work/manual-teaching-deepseek-20261030`, base `a472c5327e8f9334c5677f5243c28095282faed2`.
Autorizzazione: due prompt forniti dall'utente, con fix DeepSeek e insegnamento da chiusure manuali.
**Nessun merge, deploy, trigger operativo, accesso VPS, ordine, reset o modifica ai dati.**

## Parte A — Brain Free DeepSeek: pronta al test di integrazione (NON rilasciata)

- `backend/director/brain_free/balance.py`:
  - `unavailable_message`: codice balance=credito DeepSeek esaurito, rate, auth e altri codici sicuri; niente exception raw in Telegram.
  - `GET /user/balance` in sola lettura con timeout 8s; analizza `is_available` e solo la riga USD, numeri Decimal finiti; CNY non viene trattato come USD.
  - Soglia `DEEPSEEK_LOW_BALANCE_USD` default 2.0, normale env var non segreta. **NON e' stato creato un GitHub Secret.**
- `backend/director/brain_free/runtime.py`: monitor con worker indipendente dal tick degli stop; prima verifica dopo attivazione con chiave, poi ogni 6h o 50 richieste completate; throttling 4h persistito sullo stato; outbox Telegram durable. Errori rete/lettura ignoti non bloccano le protezioni e non autorizzano fallback alle regole.
- Il monitor viene abilitato da `runtime.main()`; il runtime costruito nei test senza callback non effettua chiamate di rete. Nessun check live e' stato effettuato.

## Parte B — Insegnamento manuale: solo motore offline, NON integrato

`backend/director/manual_teaching.py` e `backend/tests/test_manual_teaching.py`.

- `ManualLessons.register` richiede un **evento PAPER completo verificato** dopo chiusura eseguita e persistita dal motore, con `source=manual_user`. Una sparizione di posizione sull'exchange non e' un evento valido del paper wallet.
- Idempotenza per posizione/account/close timestamp; revisione per gruppo entro 5 minuti e identificatore esplicito; `/insegna_si [id]`, `/insegna_no [id]`; risposta senza ID ammessa solo se un unico gruppo attende.
- Accettazione entro 2h, poi `no_response`; `learning_log.jsonl` append-only con etichetta, `lessons.md` append-only solo se confermato e profittevole; nessuna memoria viene cancellata o modificata.
- Il `yes` su trade in perdita NON diventa una falsa lezione `profit_ok_free_slot`. `training_applied=false` sempre, e nessuna variazione alla strategia.
- Stato di revisione append-only su `manual_close_reviews.jsonl` per recovery, separato per bot.

**Non ancora collegato a Falco, Toro, Brain Free o Brain Scalp. Non c'e' un Telegram inbound controller e nessun comando /chiudi attivo.** Non attribuire chiusure reali Bitget a portafogli PAPER, non costruire un watcher "sparita dal ciclo N" senza riconciliazione con provider e receipt.

### Blocchi per integrare davvero la Parte B

1. Classici `rule-pool`: il vecchio codice 13/10 supporta `reset.flag` (chiudi tutto) ma non l'endpoint singolo `close_position.flag`, che l'app blocca tramite heartbeat. Serve nuova implementazione isolata che usi il medesimo writer PAPER, registri solo una chiusura compiuta e invii ricevuta.
2. Brain Free: nessun listener Telegram di comandi o endpoint operator close, sebbene il motore PAPER possa chiudere posizioni; niente comandi effettivi creati qui.
3. Brain Scalp conto unico: ha schema/writer e dashboard solo-read-only; definire percorso autenticato di comandi e collaudo simultaneo con protezioni senza duplicare writer.
4. Telegram: un **solo lettore** degli update per bot/chat condivisa con verifica chat ID, deduplica update_id e identificatori univoci; mai due poller in concorrenza sullo stesso token. Se /chiudi all sara' supportato, specificare il bot oppure rendere esplicito l'ambito globale, evitare esecuzioni implicite.
5. Per apprendimento effettivo: almeno 20 esempi utente confermati, valutazione fuori campione e nuova autorizzazione per cambiare prompt/strategia. 20 esempi non provano di per se' un miglioramento del P&L.

## Test e perimetro

GitHub Actions run `41032428460` SUCCESS, **53 test Python 3.10 + 53 test Python 3.11**, includendo le suite storiche Brain Free; gate immutabilita' su desk/classici, Brain Scalp, Brain Pilot, frontend, deploy, Dockerfile. Nessuna chiave reale, rete DeepSeek/Bitget, o dato live in CI.

I branch precedenti Brain Scalp `work/brain-resume-20261030` e PWA `work/brain-single-app-20261030` rimangono invariati. E' necessaria una decisione di release separata prima di qualsiasi deploy.
