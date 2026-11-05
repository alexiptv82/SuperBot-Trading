# Brain V3 PAPER — pacchetto di rilascio A4 (5 novembre 2026)

Autore: Claude Sonnet 5.5 (coordinatore). **Stato: pronto OFFLINE, NON avviato, NON distribuito.**
Regole in vigore (CLAUDE.md): nessun redeploy senza OK esplicito dell'utente; `DESK_MODE=paper`; nessuna modifica a strategia, soglie, limiti di rischio e prompt senza decisione dell'utente; il cervello (`trade_history.jsonl`, `lessons.md`, `errors.md`, `learning_log.jsonl`, journal) solo cresce; nessuna chiave nel codice; mai toccare HI-TV / `hitvprime`; repository pubblico (nessun saldo o importo reale in codice, log, commit).

## 1. Cosa fa il Brain PAPER

Un processo (`python -m backend.v3.runner.wiring`) che, ogni minuto, controlla le uscite delle posizioni PAPER e, ogni 15 minuti, fa decidere il Brain su ogni simbolo senza posizione aperta.

| Pezzo | Modulo | Cosa fa |
|---|---|---|
| Uscite | `runner/exits.py`, `monitor.py` | stop, take-profit (2R), durata massima (60 h) sulle candele da 1 minuto; ogni minuto, anche in pausa |
| Candele e prezzi | `runner/feed.py` | sola lettura del feed pubblico Bitget (nessuna chiave), cache incrementale, buchi gestiti |
| Regole dei contratti | `runner/contracts.py` | passo di quantità, nozionale minimo, leva massima dal feed pubblico |
| Ciclo del Brain | `runner/cycle.py` | vista di mercato (L5) → DeepSeek → motore (risk gate, mandato) → apertura PAPER con slippage avversa |
| Spesa del modello | `runner/metering.py` | registra la spesa reale (o una stima prudente) e **ferma** il Brain al tetto giornaliero |
| Direttore | `runner/runner.py` | orologio a 1 minuto / 15 minuti, `heartbeat.json`, `pause.flag` |
| Montaggio | `runner/wiring.py` | assembla tutto; rifiuta di partire se `DESK_MODE` non è `paper` |

Nessun ordine verso l'exchange: tutte le esecuzioni sono simulazioni scritte sul journal. Il motore del Brain (`brain_f2/engine.py`) **non è stato modificato**.

## 2. Verifiche fatte (offline)

* Test del runner: 752 test (parametrizzati) in 7 file `test_v3_runner_*.py`, tutti verdi in pochi secondi.
* Mutazione sui moduli di collegamento: ciclo 33/33, direttore 30/30, contatore di spesa 26/26, configurazione 26/26, montaggio 28/28, uscite 30/30 (un mutante alla volta, tutti uccisi).
* Una prova end-to-end con candele registrate (finte) e un modello finto: senza mandato resta fermo e **non spende**; con il mandato apre, il monitor chiude (take-profit e stop), l'esito si lega alla decisione e alla strategia dichiarata, il giro dopo il modello vede il proprio tabellone; tetto di spesa, pausa, riavvio con recupero delle uscite.
* **Non verificato** (da questa macchina Bitget e DeepSeek non sono raggiungibili): tutto ciò che è elencato al punto 5.

## 3. Valori PROPOSTI (da confermare dall'utente — oggi sono default miei)

| Voce | Valore proposto | Dove |
|---|---|---|
| Simboli | BTC, ETH, SOL, XRP, BNB, DOGE, ADA, LINK (USDT) | `runner_config.json` |
| Capitale PAPER | 1000 (soglia minima 450) | `runner_config.json` |
| Costo per lato / slippage | 6 bp per lato (12 bp a giro) + 2 bp di slippage | `runner_config.json` |
| Limiti di rischio | perdita max 2 % · rischio aperto 5 % · margine per posizione 10 % · margine totale 30 % · costo stimato 16 bp · buffer di liquidazione 0,5 | `runner_config.json` |
| Uscite | take-profit 2R · durata massima 60 h · slippage sullo stop 2 bp | `exit_policy.json` |
| Margine di manutenzione | 0,005 (dal file di configurazione, non dall'exchange) | `runner_config.json` |
| Modello DeepSeek | `deepseek-flash`, ragionamento disattivato | `runner_config.json` |
| Prezzi usati per il tetto | 0,30 $/M token in ingresso, 1,20 $/M in uscita (prudenti) | `runner_config.json` |
| **Tetto giornaliero** | **0,60 $ al giorno (≈ 18 $ al mese al massimo)** | `runner_config.json` |

I limiti di rischio sono legati al mandato (punto 4): cambiarli invalida il mandato e il Brain si ferma finché l'utente non lo riapprova.

## 4. Il mandato (decisione dell'utente, non nostra)

Il motore apre solo con un mandato di rischio approvato dall'utente. Qui nessuno approva al posto suo.

1. `python -m backend.v3.runner.wiring --data-dir <cartella> --run-id <id> --print-mandate` stampa il modello (`approved: false`); non richiede `DESK_MODE`.
2. L'utente (o chi lui incarica) salva il contenuto come `<cartella>/mandate.json` con `"approved": true` e `"approved_by": "<nome>"`.
3. Finché il file manca, non è approvato o non corrisponde (limiti diversi, altra run) il runner resta `halted` con il motivo nel battito e **non chiama il modello** (nessuna spesa). Il file è riletto a ogni tick: l'approvazione ha effetto senza riavviare.

## 5. Da verificare alla PRIMA chiamata reale (ChatGPT sulla VPS, a sola lettura)

Questi fatti vengono dalla documentazione e non sono stati confermati dal vivo.

1. **Contratti Bitget**: `GET /api/v2/mix/market/contracts?productType=USDT-FUTURES` — i campi usati sono `symbol`, `symbolStatus == "normal"`, `sizeMultiplier`, `minTradeUSDT`, `maxLever`. Se un nome è diverso `parse_contract_rules` rifiuta il simbolo (fail-closed: nessuna apertura), quindi l'errore si vede subito nel battito come `no_market_rules`.
2. **Candele Bitget** (`history-candles`): nomi di granularità `1m`, `15m`, `1H`, `4H` (tabella in `lab_tools/fetch_candles.py`); il feed scarica a finestre da 200 barre (3700 minuti ≈ 19 richieste per simbolo al primo caricamento, 8 simboli): confermare che non scatti il limite di richieste del feed pubblico.
3. **DeepSeek**: nome modello `deepseek-flash`; il parametro `{"thinking": {"type": "disabled"}}` è accettato; la risposta contiene `usage` (`prompt_tokens`, `completion_tokens`); i prezzi sono quelli della tariffa corrente. Se `usage` manca il contatore usa una stima prudente (non zero).
4. **Orologio**: il server deve essere sincronizzato (la vista rifiuta dati più vecchi di una candela).

## 6. Checklist del primo avvio (fase C — serve l'OK esplicito dell'utente)

Prima di avviare:
- [ ] OK esplicito dell'utente all'avvio (regola 1) e al mandato.
- [ ] `DESK_MODE=paper` nei Secrets (il programma rifiuta altrimenti; non si cambia).
- [ ] Backup del cervello certificato (runbook `docs/v3/f0-backup-certification-runbook.md`); il journal del Brain V3 è un file nuovo (`journal.db`), il vecchio cervello non si tocca.
- [ ] Container separato, cartella dati dedicata sul volume persistente; **mai** toccare HI-TV / `hitvprime` (nginx, DNS, container di Strasburgo).
- [ ] `DEEPSEEK_API_KEY` solo nei Secrets/ambiente del container, mai nel repository.
- [ ] Controlli del punto 5 eseguiti e annotati.

Primo avvio:
1. `--once` **senza** `mandate.json`: atteso `state: halted`, `last_error: halted:no_mandate`, spesa 0.
2. Mandato approvato dall'utente → avvio normale; atteso `heartbeat.json` con `state: running`, `last_error: null` entro 15 minuti.
3. Primi giri: nel journal compaiono `brain_decision` e, se approvate, `paper_open`; la spesa giornaliera sta sotto il tetto.

Controlli nelle prime 24–48 ore: battito aggiornato ogni minuto; `last_error` assente o solo codici attesi; spesa del modello ≤ tetto; ogni posizione aperta chiude per `stop`, `take_profit` o `timeout`; nessun simbolo bloccato per `no_market_rules` / `feed_error` in modo permanente.

Emergenza: creare `pause.flag` nella cartella dati ferma le **nuove** aperture e la spesa del modello (le uscite proseguono); rimuoverlo le riattiva. Il tetto di spesa ferma da solo il Brain (`halted:budget`).

Chiusura manuale (decisione dell'utente: «deve essere inserita»): l'app scrive `close_request.json` nella cartella dati (`{"ts_ms": <ms UTC>, "position_ids": ["<id>", ...]}` oppure `{"ts_ms": <ms UTC>, "all": true}`); il programma lo esegue entro circa 5 secondi, **anche con il Brain in pausa o fermo e senza chiamate al modello**, chiude al prezzo dell'ultimo minuto chiuso con motivo `manual` e scrive `close_result.json` (`status` `done`/`expired`/`invalid_request`, id chiusi, fallimenti con codici brevi). Una richiesta più vecchia di 10 minuti scade. A mano, in emergenza: scrivere quel file con l'ora corrente e gli id delle posizioni aperte (si leggono nel journal o dalla dashboard). Il Brain riconosce l'esito `manual` nel tabellone e non lo copia alla cieca. Il pulsante nell'app è un lavoro a parte (dashboard).

## 7. Cosa non c'è ancora (volutamente fuori dalla prima versione)

Chiusure parziali, mediazione dell'ingresso, dimensione scelta dal Brain, notizie, MODIFY_STOP, importazione dei trade legacy. Il blocco giornaliero per perdita (`daily_loss_latched`) **non è definito per il Brain**: oggi è sempre spento; il freno vero sono i limiti di rischio per operazione, il margine totale e la soglia minima di equity (450).

## 8. Rischi da sapere

* Il Brain vede gli indicatori ma nessuna regola li applica: la strategia dichiarata è un'attribuzione, il tabellone dice come è andata.
* Il laboratorio ha dato esito negativo a tre strategie classiche a 15 m con 12 bp di costi: è probabile che molte schede risultino negative nel PAPER. È la misura, non un guasto.
* Le celle del tabellone diventano «misurate» in settimane (`min_trades 15`, `min_days 4`).
