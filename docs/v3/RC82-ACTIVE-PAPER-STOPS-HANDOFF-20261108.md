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

2. Prezzi operativi. `run_cycle` non usa più `get_prices` per aperture e DCA. `operational_prices` prende l'ultima chiusura con timestamp non futuro e OHLC accettato da `_bar_usable` (niente low/close ≤ 0, niente range incoerente). Una candela solo futura o invalida non apre e non aumenta il margine. Se davanti c'è una candela valida, l'ingresso usa quella chiusura, non il close futuro. Una candela valida resta utilizzabile anche se il ciclo successivo è più tardi: è il comportamento che `test_desk.py` già verificava. Lo stop sulle barre vecchie ma valide non cambia.

Questo testo è nel commit figlio di `49b1a73f92904cac63c31c51ef2537254172d2ad`. Lo SHA da revisionare è il HEAD di `cursor/rc82-active-paper-stops-31c4` dopo il push, riportato nella descrizione della PR #79.

## Comportamenti verificati e non modificati

- La candela da 15 minuti ancora aperta, se i prezzi sono coerenti, continua a far scattare lo stop sul minimo/massimo. È il modello OHLC del motore attivo, diverso dal monitor RC80 che usa solo la chiusura del minuto chiuso.
- La candela dentro cui la posizione è stata aperta non viene usata: da OHLC non si sa se il minimo era prima o dopo l'ingresso. Usarla creerebbe stop falsi.
- Cadenza del ciclo: 900 s con uno scalp aperto o in svuotamento, 1800 s altrimenti. Il primo passaggio di stop ora avviene prima della chiamata a Claude; non è un controllo a ogni secondo.
- Senza chiave, o fuori dal calendario, Claude non è chiamato e decidono le regole. Con chiave sintetica e senza calendario, la funzione di chiamata viene usata una volta. Nessuna richiesta reale.
- Falco e Toro condividono il ciclo. Il caso della barra futura è eseguito anche con `DESK_PORTFOLIO=bull`.

## Test eseguiti su questa VM, secondo giro

cwd `/tmp/rc82-work`, `PYTHONPATH=backend`, `python3 -m pytest -q -p no:cacheprovider --tb=line`.

- `backend/tests/test_v3_rc82_active_paper_stops.py`: 17 passed, 0 failed, 0.34 s, exit 0.
- `backend/tests/test_desk.py`: 84 passed, 0 failed, 564.93 s, exit 0.
- `backend/tests/test_v3_classic_exit_only.py` + `test_v3_rc78_paper_stop_monitor.py` + `test_v3_rc80_paper_stop_hardening.py`: 67 passed, 7 warning, 1.17 s, exit 0. Warning: deprecazione AnyIO in Starlette e `app=` shortcut di httpx su 6 test exit-only.

Non è una CI GitHub e non certifica gli stop in produzione né un riavvio.

## Residui

- Fra un ciclo e l'altro lo stop non è osservato. Con uno scalp l'attesa arriva a 15 minuti, più la durata del ciclo. Non è un controllo a ogni tick.
- Il wick della candela di ingresso resta invisibile.
- RC81 legge `exit_only_heartbeat.json`, non `stop_feed` del bot attivo. La dashboard RUNNING non mostra ancora quell'allarme.
- Il healthcheck resta verde se il processo scrive il heartbeat, anche con `stop_feed.alarm=true`.
- Una candela valida ma vecchia può ancora essere il prezzo di un'apertura: non è futura e l'OHLC è coerente. L'allarme di feed vecchio resta sullo stop, non blocca da solo l'ingresso.
- Se il secondo passaggio chiude dopo un DCA solo in memoria e la prova dei registri fallisce, il conto non viene salvato. La riga già scritta di quella chiusura resta. Il giro dopo riparte dallo stato precedente e può registrare un fill diverso. Il caso provato è la chiusura del primo passaggio, prima del DCA.
- Nessuna modifica a PR #77 o alla PR #78. Prossimo passo: revisione indipendente, senza merge né riavvio.
