# Brain V3 PAPER — pacchetto di rilascio A4 (5 novembre 2026, aggiornato 20:10)

Autore: Claude Sonnet 5.5 (coordinatore). **Stato: pronto OFFLINE, NON avviato, NON distribuito.**
Regole in vigore (CLAUDE.md): nessun redeploy senza OK esplicito dell'utente; `DESK_MODE=paper`; nessuna modifica a strategia, soglie, limiti di rischio e prompt senza decisione dell'utente; il cervello (`trade_history.jsonl`, `lessons.md`, `errors.md`, `learning_log.jsonl`, journal) solo cresce; nessuna chiave nel codice; mai toccare HI-TV / `hitvprime`; repository pubblico (nessun saldo o importo reale in codice, log, commit).

## 1. Cosa fa il Brain PAPER

Un processo (`python -m backend.v3.runner.wiring`) che: ogni minuto controlla le uscite delle posizioni PAPER; ogni ~5 secondi controlla i comandi dell'utente (chiusura manuale); **ogni ora** (decisione dell'utente) fa decidere il Brain su ogni simbolo senza posizione aperta.

| Pezzo | Modulo | Cosa fa |
|---|---|---|
| Uscite | `runner/exits.py`, `monitor.py` | stop, take-profit (2R), durata massima (**24 h**) sulle candele da 1 minuto; ogni minuto, anche in pausa |
| Candele e prezzi | `runner/feed.py` | sola lettura del feed pubblico Bitget (nessuna chiave), cache incrementale, buchi gestiti |
| Regole dei contratti | `runner/contracts.py` | passo di quantità, nozionale minimo, leva massima dal feed pubblico |
| Ciclo del Brain | `runner/cycle.py` | vista di mercato (L5) → DeepSeek con ragionamento esteso → motore (risk gate, mandato) → apertura PAPER con slippage avversa |
| Spesa del modello | `runner/metering.py` | registra la spesa reale (o una stima prudente) e **ferma** il Brain al tetto giornaliero |
| Direttore | `runner/runner.py` | orologio a 1 minuto, giro ogni `cycle_minutes`, `heartbeat.json`, `pause.flag`, comandi a ogni controllo |
| Chiusura manuale | `runner/manual_close.py` | `close_request.json` → chiusura `manual` → `close_result.json` (punto 6) |
| Montaggio | `runner/wiring.py` | assembla tutto; rifiuta di partire se `DESK_MODE` non è `paper` |

Nessun ordine verso l'exchange: tutte le esecuzioni sono simulazioni scritte sul journal. Il motore del Brain (`brain_f2/engine.py`) **non è stato modificato**.

## 2. Verifiche fatte (offline)

* Suite V3+Brain: 5678 test verdi (3 errori `fastapi` preesistenti, solo perché qui manca il pacchetto).
* Mutazione sui moduli di collegamento: ciclo 33/33, direttore 30/30, contatore 26/26, configurazione 26/26, montaggio 28/28, uscite 30/30, chiusura manuale 39/39, ritmo orario e ragionamento 32/34 (2 equivalenti).
* Prova end-to-end con candele e modello finti: senza mandato resta fermo e **non spende**; con il mandato apre, il monitor chiude (take-profit, stop), l'esito si lega alla decisione e alla strategia dichiarata, il giro dopo il modello vede il proprio tabellone; tetto di spesa, pausa, riavvio con recupero delle uscite; chiusura manuale a Brain in pausa; **ritmo orario con ragionamento esteso (parametri nella richiesta, spesa registrata) e risposta troncata = nessuna decisione ma spesa registrata**.
* **Non verificato** (Bitget e DeepSeek non sono raggiungibili da qui): tutto ciò che è al punto 5.

## 3. Valori (stato delle decisioni dell'utente, 5/11)

| Voce | Valore | Stato | Dove |
|---|---|---|---|
| Simboli | BTC, ETH, SOL, XRP, BNB, DOGE, ADA, LINK (USDT) | **confermato** | `runner_config.json` |
| Capitale PAPER | 1000 (soglia minima 450) | **confermato** | `runner_config.json` |
| Costo per lato / slippage | 6 bp per lato (12 bp a giro) + 2 bp | **confermato** | `runner_config.json` |
| Uscite | take-profit 2R · slippage di stop 2 bp · **durata massima 24 h** | **confermato** | `exit_policy.json` |
| Margine di manutenzione | 0,005 | **confermato** | `runner_config.json` |
| **Ritmo delle decisioni** | **ogni ora** (`cycle_minutes: 60`); uscite ogni minuto | **deciso dall'utente** | `runner_config.json` |
| **Modello e ragionamento** | `deepseek-flash`, `thinking: enabled`, `reasoning_effort: high`, `max_tokens: 6000` (include i token di ragionamento) | **ragionamento esteso deciso dall'utente**; sforzo e tetto di token scelti da me, da tarare | `runner_config.json` |
| Prezzi per il tetto | 0,30 $/M in ingresso, 1,20 $/M in uscita (prudenti) | da rivedere con il modello vero | `runner_config.json` |
| **Tetto giornaliero** | **0,75 $** | **deciso dall'utente** | `runner_config.json` |
| **Freni di rischio** | oggi 2 % perdita · 5 % rischio aperto · 10 % margine per posizione · 30 % margine totale · buffer 0,5 | **l'utente vuole allargare; numeri NON ancora chiariti** (proposta: 3 / 8 / 20 / 50 %). Non applicato. | `runner_config.json` |

I limiti di rischio sono legati al mandato (punto 4): cambiarli invalida il mandato. Il mandato non è ancora firmato.

**Costo atteso del ragionamento (stime mie, da misurare):** fino a 8 simboli × 24 giri = 192 chiamate al giorno (meno quando ci sono posizioni aperte). Ingresso circa 2500 token ≈ 0,00075 $; uscita con ragionamento da ~1500 a 6000 token ≈ 0,002–0,0072 $. **Caso peggiore ≈ 0,008 $ a chiamata: il tetto di 0,75 $ si raggiunge dopo circa 94 chiamate, cioè a metà giornata.** Caso tipico (≈2500 token di uscita): ≈ 0,0038 $ a chiamata ≈ 0,7 $ al giorno, al limite del tetto. Quando il tetto scatta il Brain smette di aprire fino a mezzanotte UTC (le uscite proseguono): è un freno, non un guasto. Se le misure reali dicono che serve più spazio: alzare il tetto (decisione dell'utente) o scendere a `reasoning_effort: low`.

## 4. Il mandato (decisione dell'utente, non nostra)

Il motore apre solo con un mandato di rischio approvato dall'utente. Qui nessuno approva al posto suo.

1. `python -m backend.v3.runner.wiring --data-dir <cartella> --run-id <id> --print-mandate` stampa il modello (`approved: false`); non richiede `DESK_MODE`.
2. L'utente (o chi lui incarica) salva il contenuto come `<cartella>/mandate.json` con `"approved": true` e `"approved_by": "<nome>"`.
3. Finché il file manca, non è approvato o non corrisponde (limiti diversi, altra run) il runner resta `halted` con il motivo nel battito e **non chiama il modello** (nessuna spesa). Il file è riletto a ogni tick.

## 5. Da verificare alla PRIMA chiamata reale (ChatGPT sulla VPS, a sola lettura)

Questi fatti vengono dalla documentazione e non sono stati confermati dal vivo.

1. **Contratti Bitget**: `GET /api/v2/mix/market/contracts?productType=USDT-FUTURES` — campi usati `symbol`, `symbolStatus == "normal"`, `sizeMultiplier`, `minTradeUSDT`, `maxLever`. Se un nome è diverso `parse_contract_rules` rifiuta il simbolo (fail-closed): l'errore si vede nel battito come `no_market_rules`.
2. **Candele Bitget** (`history-candles`): granularità `1m`, `15m`, `1H`, `4H`; il feed scarica a finestre da 200 barre (1500 minuti ≈ 8 richieste per simbolo al primo caricamento, 8 simboli): confermare che non scatti il limite di richieste.
3. **DeepSeek, ragionamento esteso** (documentazione ufficiale: `{"thinking": {"type": "enabled"}}`, `reasoning_effort` `low|high|max`, `max_tokens` fra 1 e 393216; il ragionamento torna in `reasoning_content`, la decisione in `content`; `usage.completion_tokens_details.reasoning_tokens` opzionale): verificare con una chiamata vera che (a) il nome del modello `deepseek-flash` sia accettato, (b) i due parametri siano accettati insieme a `response_format: json_object`, (c) **`max_tokens` includa i token di ragionamento e quanti ne servono per chiamata** (misurare 20–30 chiamate: se spesso `finish_reason` è `length` la decisione manca e si spende comunque), (d) `usage` contenga i token di ragionamento (il contatore paga `completion_tokens`), (e) i prezzi siano quelli della tariffa corrente.
4. **Orologio**: il server deve essere sincronizzato (la vista rifiuta dati più vecchi di una candela).

## 6. Checklist del primo avvio (fase C — serve l'OK esplicito dell'utente)

Prima di avviare:
- [ ] OK esplicito dell'utente all'avvio (regola 1) e al mandato.
- [ ] `DESK_MODE=paper` nei Secrets (il programma rifiuta altrimenti; non si cambia).
- [ ] Backup del cervello certificato (runbook `docs/v3/f0-backup-certification-runbook.md`); il journal del Brain V3 è un file nuovo (`journal.db`), il vecchio cervello non si tocca.
- [ ] Container separato, cartella dati dedicata sul volume persistente; **mai** toccare HI-TV / `hitvprime` (nginx, DNS, container di Strasburgo).
- [ ] `DEEPSEEK_API_KEY` solo nei Secrets/ambiente del container, mai nel repository.
- [ ] Controlli del punto 5 eseguiti e annotati.
- [ ] Freni di rischio confermati dall'utente scritti in `runner_config.json` **prima** di stampare il mandato.

Primo avvio:
1. `--once` **senza** `mandate.json`: atteso `state: halted`, `last_error: halted:no_mandate`, spesa 0.
2. Mandato approvato dall'utente → avvio normale; atteso `heartbeat.json` con `state: running`, `last_error: null` subito (il primo giro parte appena avviato, poi a ogni ora).
3. Primi giri: nel journal compaiono `brain_decision` e, se approvate, `paper_open`; la spesa giornaliera sta sotto il tetto.

Controlli nelle prime 24–48 ore: battito aggiornato (ogni ~5 s); `last_error` assente o solo codici attesi; spesa del modello ≤ tetto **e quanti token di ragionamento per chiamata (punto 5c)**; ogni posizione aperta chiude per `stop`, `take_profit`, `timeout` (24 h) o `manual`; nessun simbolo bloccato per `no_market_rules` / `feed_error` in modo permanente.

Emergenza: creare `pause.flag` nella cartella dati ferma le **nuove** aperture e la spesa del modello (le uscite proseguono); rimuoverlo le riattiva. Il tetto di spesa ferma da solo il Brain (`halted:budget`).

**Chiusura manuale** (decisione dell'utente: «deve essere inserita»): l'app scrive `close_request.json` nella cartella dati (`{"ts_ms": <ms UTC>, "position_ids": ["<id>", ...]}` oppure `{"ts_ms": <ms UTC>, "all": true}`); il programma lo esegue entro circa 5 secondi, **anche con il Brain in pausa o fermo e senza chiamate al modello**, chiude al prezzo dell'ultimo minuto chiuso con motivo `manual` e scrive `close_result.json` (`status` `done`/`expired`/`invalid_request`, id chiusi, fallimenti con codici brevi). Scade dopo 10 minuti. A mano, in emergenza: scrivere quel file con l'ora corrente e gli id delle posizioni aperte. Il Brain riconosce `manual` nel tabellone e non lo copia alla cieca. Il pulsante nell'app è un lavoro a parte (secondo giro per ChatGPT).

## 7. Cosa non c'è ancora (volutamente fuori dalla prima versione)

Chiusure parziali, mediazione dell'ingresso, dimensione scelta dal Brain, notizie, MODIFY_STOP, importazione dei trade legacy, pulsante «Chiudi» nell'app. Il blocco giornaliero per perdita (`daily_loss_latched`) **non è definito per il Brain**: oggi è sempre spento; il freno vero sono i limiti di rischio per operazione, il margine totale e la soglia minima di equity (450).

## 8. Rischi da sapere

* Il Brain vede gli indicatori ma nessuna regola li applica: la strategia dichiarata è un'attribuzione, il tabellone dice come è andata.
* Il laboratorio ha dato esito negativo a tre strategie classiche a 15 m con 12 bp di costi: è probabile che molte schede risultino negative nel PAPER. È la misura, non un guasto.
* Le celle del tabellone diventano «misurate» in settimane (`min_trades 15`, `min_days 4`); con una decisione all'ora ci vorrà più tempo che con una ogni 15 minuti.
* Con il ragionamento esteso il costo reale può superare le stime; il tetto giornaliero ferma le nuove aperture (fail-closed), le uscite proseguono.
