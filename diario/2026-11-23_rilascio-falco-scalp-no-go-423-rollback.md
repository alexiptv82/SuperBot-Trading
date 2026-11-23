# 2026-11-23 14:10 Europe/Rome — Rilascio PAPER Falco Evoluto + Brain Scalp: NO-GO su negative close Falco

## Evidenza VPS (screenshot terminale inviato dal proprietario)
- Nuovo container web e bridge arrivati al collaudo; probe RC1: `live_RESULT=PASS_LIVE`, bridge RC1 negative close 404; RC1 paused, `open:1` nello status, uscite funzionanti dal precedente controllo.
- Due nuove run al momento del candidato: `live_compare_falco_evoluto=prepared_paused_close_ready`, `live_compare_brain_scalp=prepared_paused_close_ready`.
- Sonda attiva `POST /api/v3/compare/falco_evoluto/close` con position_id inesistente ha restituito **423**, previsto 404: `live_compare_RESULT=FAILED_bridge_negative_close_falco_evoluto_423`. Nessuna conclusione sulla causa dal solo status; la sonda non stampa il `detail.code`/messaggio.
- Il rilascio ha effettuato rollback automatico, con `web_rollback=DONE_PREVIOUS_WEB_RESTORED`, `bridge_restore=PREVIOUS_UNIT_RESTARTED`, poi `PREVIOUS_WEB_AND_BRIDGE_RESTORED`, nuove unità fermate e conservate; `ESITO RILASCIO: NO-GO (web e bridge)`. Run, journal e codice rimasti in pausa con mandati `approved:false`, RC1 invariato.

## Verifica GitHub effettuata da ChatGPT
- Commit codice rilasciato `393b38f61702c18ffc93a1a6fcc6046922df42bb` (branch successivo attuale `b67f760b`).
- `deploy/falco-evoluto/rilascio/compare_probe.py`: test negativo della run Falco aspetta HTTP 404; usa position id `probe-posizione-inesistente`, stampa solo HTTP status e maschera `code`/messaggio utili alla diagnosi.
- `backend/v3_api.py` route POST `/compare/{name}/close`: 423 se `close_all` o se flag single-close disabilitato, altrimenti verso bridge; 409 se sidecar non healthy.
- `backend/v3/close_bridge_server.py`: 423 per forma richiesta non single-position, `_queue_run_close` conserva 423 dagli handler; backend dovrebbe dare 404 per `position_id` inesistente quando identità, modalità e servizio sono validi.
- Con RC1 che ha restituito correttamente 404, sospettare differenza di routing o versione bridge lato nuovo wallet; non presumere una diagnosi certa. Non modificare test per far passare 423.

## Prossimo passo richiesto a Claude
- Non ri-eseguire l'installer originale e non eseguire rollback nuovamente. Trovare con soli permessi già autorizzati e dati non sensibili la sorgente precisa di 423 (codice HTTP JSON/detail, quale componente l'ha prodotto, confronto bridge RC1 vs EXTRA, unità realmente caricate al cutover, socket e route).
- Riprodurre in ambiente isolato con servizio bridge e web realistici, test del negative-close per ciascuna nuova run e controllo identità run; preservare vietato close-all.
- Patch minima su branch isolato, niente soppressione del gate; aggiungere probe diagnostico che distingua 423 'solo_chiusura_singola', 'solo_lettura', o bridge refusal senza segreti.
- Preparare **nuovo piano idempotente/ripresa**: al successivo tentativo run/pacchetto già esistenti in pausa e approved:false; preflight originale rifiuta run/stage già presenti, quindi non ripetere vecchio comando. Mai cancellare o resettare journal/mandati; preservare RC1.
- Richiedere nuovo OK proprietario prima di altro deploy. Eventuale wrapper sudo opzionale non ancora applicato; non concedere privilegi autonomamente.