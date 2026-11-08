# 2026-11-08 — RC82 stop PAPER attivo

Diario sul branch RC82, non sul branch canonico `diario`.

Base verificata sul remoto: `29eb75750625a8819cd2db71dc2459d164c3199c`, branch `cursor/rc81-stop-telemetry-ui-chatgpt-20261108`, PR #78. Nessun commit su quella PR.

Audit del ciclo attivo Falco/Toro (`backend/desk/cli.py`, `backend/desk/engine.py`) con dati sintetici. Confermati, poi corretti in modo minimo:

- barra futura e minimo zero non possono più liquidare;
- il feed assente, vecchio o ultimo prezzo inutilizzabile mette `stop_feed.alarm` e `stop_certified=false` nel heartbeat;
- lo stop di una candela già chiusa è valutato prima del DCA che potrebbe allargarlo; un secondo passaggio applica uno stop stretto nello stesso ciclo;
- il riavvio dopo un salvataggio fallito non duplica la riga di storico.

Non sono stati cambiati formula, leva, size, capitale, prompt o il prezzo che `on_bar` assegna a stop, target e liquidazione. Claude resta consultato secondo chiave e calendario: lo stub non esce in rete.

Secondo giro, stessa PR #79, dopo la revisione sul commit `49b1a73`. Solo due P0:

- `_prove_protective_close`: storico e learning devono essere entrambi riletti (`symbol`, `id`, `open_ms`, `close_ms`, `why`, `net`, `run_no` se c'è). Se manca la prova non si salva il conto. Righe troncate restano e non si incollano alla riga nuova (`_append_json_line`).
- `operational_prices`: una candela futura o con OHLC inutilizzabile non apre e non fa DCA. Una candela valida mantiene il prezzo di prima.

Test locali, non CI: RC82 17 passed; `test_desk.py` 84 passed; exit-only+RC78+RC80 67 passed e 7 warning. Workflow: nessun `cursor/**` e nessun `pull_request_target`. `[skip ci]` non è la sola difesa.

Lo SHA da revisionare è il HEAD del branch dopo il push, scritto nella PR #79. Prossimo passo: revisione indipendente. Non è una certificazione di stop né un via libera al riavvio. PR #77 e #78 non vanno toccate.
