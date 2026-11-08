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

Terzo giro, partenza `bccfddfb98e6ee0213962951879426fc61ef6f13`. Due residui della seconda revisione:

- Aperture e DCA rifiutano l'ultima candela se è vecchia di oltre due barre da 15 minuti, futura o OHLC invalida. Non si ripiega su una barra obsoleta. Gli stop storici restano. I test di `test_desk.py` che spostavano l'orologio senza aggiornare le candele ricevono una candela piatta sul bucket corrente.
- Prima del secondo passaggio lo stato col DCA viene salvato. Se il learning della chiusura fallisce, il riavvio dal disco riproduce lo stesso netto. Un fill terminale diverso non viene duplicato.

Test: RC82 19 passed; desk 84 passed; exit-only+RC78+RC80 67 passed e 7 warning. Workflow senza `cursor/**` e senza `pull_request_target`. Lo SHA da revisionare è il HEAD dopo il push. Non è una certificazione di stop né un via libera al riavvio. PR #77 e #78 non vanno toccate.
