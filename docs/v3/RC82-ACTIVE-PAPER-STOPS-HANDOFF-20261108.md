# RC82 — stop PAPER attivo di Falco e Toro

Base: `29eb75750625a8819cd2db71dc2459d164c3199c` (PR #78, branch `cursor/rc81-stop-telemetry-ui-chatgpt-20261108`).
Branch: `cursor/rc82-active-paper-stops-31c4`. PR draft verso quel branch RC81. Nessun merge, deploy, riavvio, VPS o ordine.

Questo lavoro riguarda il ciclo PAPER **attivo** (`desk/cli.py` + `desk/engine.py`), non il monitor di manutenzione RC80/RC81. Non cambia strategie, prompt, leve, size, capitale, formule di costo o il prezzo di uscita calcolato da `PaperAccount.on_bar`.

## Difetti dimostrati prima della correzione

Riproduzione sintetica, senza rete, sul codice della base:

1. Una candela con timestamp futuro e minimo sotto la liquidazione chiudeva il long come liquidazione.
2. Un minimo a zero, OHLC impossibile, liquidava.
3. Feed assente o vecchio di ore: la posizione restava aperta e il heartbeat non diceva che il controllo stop era cieco. Il healthcheck guarda solo l'età del file, quindi il processo risultava vivo.
4. Lo stop veniva valutato **dopo** il DCA. Una candela già chiusa con minimo 97 e stop 98 restava aperta perché il DCA dello stesso ciclo spostava lo stop a 95.
5. Se il salvataggio dello stato falliva dopo la scrittura dello storico, il ciclo successivo richiudeva e lo storico PAPER aveva due righe dello stesso stop.

Priorità già corretta e lasciata com'è: liquidazione, poi stop, poi take-profit. Il gap oltre lo stop esce all'apertura, non a un prezzo inventato migliore. LONG e SHORT usano lo stesso motore.

## Correzione minima

`apply_paper_protective_exits` in `backend/desk/cli.py`:

- scarta barre future o con OHLC non finito, non positivo o incoerente;
- applica le barre valide, anche se il feed è vecchio, così uno stop già stampato chiude;
- segna `heartbeat.stop_feed` (`missing`, `unusable`, `future`, `stale`, `latest_rejected`) e `stop_certified=false`;
- gira una volta prima di Claude/DCA e una volta dopo, così uno stop già toccato non viene allargato e uno stop stretto nello stesso ciclo vale subito;
- non rende durevole la chiusura se storico e learning non sono entrambi riletti.

`stop_certified` non è mai true. Il healthcheck non è stato modificato: un feed cieco non deve far riavviare il container. L'allarme è nel contenuto del heartbeat, non nell'età del file.

## Secondo giro, due P0 della revisione su `49b1a73`

Funzioni: `_prove_protective_close`, `_jsonl_has_close`, `_close_row_matches` e `operational_prices` in `backend/desk/cli.py`. Scrittura su file: `_append_json_line` in `backend/desk/brain.py`, usata anche da `log_event` in `backend/desk/learning.py`.

1. Persistenza. Una chiusura protettiva è provata solo se storico e learning hanno la stessa identità (`symbol`, `id`, `open_ms`, `close_ms`, `why`, `net`; `run_no` se presente, e sempre nel learning). Se manca un lato si scrive solo quello, poi si rilegge. Se uno dei due non si può provare si alza `close_not_durable` e non si salva il conto: la posizione resta aperta sul disco e il giro dopo riprova. Una riga già completa non si riscrive. Una riga troncata o parziale non conta come prova e non si cancella: la riga nuova va a capo, così non si incolla al frammento. Casi coperti: storico ok e learning no, il contrario, entrambi no, frammento troncato, recupero dopo il fallimento, secondo giro senza duplicati.

2. Prezzi operativi, primo giro. `operational_prices` scartava solo timestamp futuri e OHLC invalidi. Una candela valida ma vecchia poteva ancora aprire. Quel comportamento è stato tolto nel giro sotto.

## Terzo giro, residui su `bccfddfb98e6ee0213962951879426fc61ef6f13`

1. Freschezza. `_quote_fresh` in `backend/desk/cli.py`: l'ultima riga deve essere OHLC valida e non più vecchia di due candele da 15 minuti. Se è futura, invalida o stale non si usa una barra precedente per aprire o fare DCA. `new_exposure.blocked_symbols` elenca quei simboli e `stop_feed.alarm` resta true. Gli stop sulle barre storiche valide restano.

2. Ripartenza dopo DCA. Prima del secondo passaggio il conto modificato viene salvato. Se il learning della chiusura fallisce, il disco ha la posizione col DCA ancora aperta e lo storico ha quel fill. Il giro dopo, letto dal disco, chiude con lo stesso netto. `_scan_close` non aggiunge un altro fill terminale per lo stesso simbolo, id, open_ms e lato se il netto non coincide, e non cancella la riga già scritta.

`test_desk.py`: `_rows_asof` aggiunge una candela piatta sull'ultimo close quando l'orologio del ciclo è più avanti delle barre. Il test della seconda gamba abbassa il minimo dell'ultima candela, non ne aggiunge una nel futuro.

Lo SHA da revisionare è il HEAD del branch dopo il push, figlio di `bccfddfb98e6ee0213962951879426fc61ef6f13`.

## Comportamenti verificati e non modificati

- La candela da 15 minuti ancora aperta, se i prezzi sono coerenti, continua a far scattare lo stop sul minimo/massimo. È il modello OHLC del motore attivo, diverso dal monitor RC80 che usa solo la chiusura del minuto chiuso.
- La candela dentro cui la posizione è stata aperta non viene usata: da OHLC non si sa se il minimo era prima o dopo l'ingresso. Usarla creerebbe stop falsi.
- Cadenza del ciclo: 900 s con uno scalp aperto o in svuotamento, 1800 s altrimenti. Il primo passaggio di stop ora avviene prima della chiamata a Claude; non è un controllo a ogni secondo.
- Senza chiave, o fuori dal calendario, Claude non è chiamato e decidono le regole. Con chiave sintetica e senza calendario, la funzione di chiamata viene usata una volta. Nessuna richiesta reale.
- Falco e Toro condividono il ciclo. Il caso della barra futura è eseguito anche con `DESK_PORTFOLIO=bull`.

## Test eseguiti su questa VM, secondo giro

cwd `/tmp/rc82-work`, `PYTHONPATH=backend`, `python3 -m pytest -q -p no:cacheprovider --tb=line`.

Terzo giro, stessi comandi:

- `backend/tests/test_v3_rc82_active_paper_stops.py`: 19 passed, 0 failed, 0.45 s, exit 0. Due fallimenti intermedi, poi corretti: il take-profit long condivideva id e open_ms con uno short precedente ed era letto come fill discordante (ora il lato entra nell'identità); l'allarme di una candela futura senza posizione aperta non restava nel heartbeat (ora `new_exposure` lo riaccende).
- `backend/tests/test_desk.py`: 84 passed, 0 failed, 565.26 s, exit 0.
- exit-only + RC78 + RC80: 67 passed, 7 warning, 1.02 s, exit 0. Stesse deprecazioni AnyIO e httpx.

Non è una CI GitHub e non certifica gli stop in produzione né un riavvio.

## Residui

- Fra un ciclo e l'altro lo stop non è osservato. Con uno scalp l'attesa arriva a 15 minuti, più la durata del ciclo. Non è un controllo a ogni tick.
- Il wick della candela di ingresso resta invisibile.
- RC81 legge `exit_only_heartbeat.json`, non `stop_feed` del bot attivo. La dashboard RUNNING non mostra ancora quell'allarme.
- Il healthcheck resta verde se il processo scrive il heartbeat, anche con `stop_feed.alarm=true`.
- Una candela valida ma più vecchia di due barre da 15 minuti non apre e non fa DCA. Lo stop su quella barra, se lo stop è già stampato, chiude ancora.
- Se esiste già un fill terminale discordante per la stessa posizione, non se ne scrive un altro e non si cancella il primo. Il conto non viene dichiarato chiuso con un netto diverso.
- Nessuna modifica a PR #77 o alla PR #78. Prossimo passo: revisione indipendente, senza merge né riavvio.
