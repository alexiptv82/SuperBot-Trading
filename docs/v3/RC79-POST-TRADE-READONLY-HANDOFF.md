# RC79 — analisi post-trade PAPER, isolata

**7 novembre 2026. Solo sviluppo offline.** Nessun deploy, trading, merge, reset o API.

## Coordinamento
- RC78 / PR #75 resta di competenza dell'agente che implementa il monitor SL/TP e liquidazione. La revisione statica ChatGPT è nel commento PR #75.
- RC79 non modifica `backend/desk/exit_only.py` o `paper_stop_monitor.py`, né alcuna strategia.
- La nuova libreria pure-Python `backend/v3/observability/post_trade_review.py` esegue analisi deterministiche **in sola lettura**, a partire da eventi già normalizzati. Niente scritture o chiamate di rete.

## Cosa fa
1. Raggruppa più chiusure parziali di una posizione per `portfolio, run_id, symbol, id, open_ms`, senza contare erroneamente una posizione con quattro fill come quattro trade. Per i run ID legacy occorre indicare esplicitamente l'identificatore della run verificata; Brain richiede un adapter del Journal V3, ancora da realizzare.
2. Calcola il totale netto/commissioni/funding **solo quando presenti**; non inventa campi e rifiuta importi NaN o identità ambigue.
3. Individua perdita netta maggiore del margine dichiarato, uscita oltre stop iniziale se un documento originario verificato è fornito, e ingressi quasi simultanei su stessa coppia e direzione in portafogli distinti.
4. Fornisce verdict `evidenza_insufficiente` se manca una serie prezzi verificata. Un `problema_gestione` richiede *insieme* prova stop iniziale, monitor disattivato e attraversamento stop su percorso prezzi verificato. Non dichiara automaticamente un ingresso sbagliato.
5. Ogni esito include `can_autolearn=False`, `can_trade=False`; nessun incremento delle strategie in automatico.

## Test
`PYTHONPATH=backend python -m pytest -q backend/tests/test_v3_rc79_post_trade_review.py`: **15 PASS** su fixture sintetiche, inclusi ARB due wallet, doppio segnale, 4 fill una posizione, stop incerto, risalita memoria, DCA che varia entry, timestamp errati, NaN e mancanza costi. Nessuna rete.

## Limiti prima dell'uso effettivo
- L'analizzatore **non è ancora collegato all'app** né al journal V3 Brain; serve adapter verificato verso la sorgente dati ed evidenze open/monitor immutabili.
- Le chiusure manuali ARB RC77 sono già verificate: `-122,6256 / -226,8574 USDT` e totale 8 manual close `+433,4783 USDT` PAPER; i risultati test riproducono solo queste *cifre come fixture*, non leggono la VPS.
- Evidenza che RC73 non monitorava stop NON implica automaticamente stop-crossing timestamp o prezzo eseguibile: non è stato acquisito feed storico affidabile. Non introdurre training/causalità inventata.
- Prima di integrare: testare adapter su copie immutabili RC77, non toccare legacy; verificare allineamento run_id, idempotenza e coeval filters, poi approvazione distinta di eventuale UI o AI reporting.