# 2026-11-19 — router LLM gratuito, solo preparazione

Diario su questo branch, non sul branch canonico `diario`.

Base scelta: `work/brain-exit-observability-20261113` @ `33a0de73a9903ba1ff76326aa4cb7c688a1e4aca`. Il diario del 19 novembre parla di PR di inventario, dataset e Guardian, ma il runner PAPER del Brain resta fermo all'ultimo riscontro su questo SHA. I rami successivi non risultano installati.

Si aggiunge un analista L5 verso un router OpenAI-compatibile di soli provider gratuiti. `BRAIN_LLM_PROVIDER` resta `deepseek` se non si cambia. Con `free_router`, DeepSeek è il fallback a pagamento, acceso di default, una sola volta per simbolo e ciclo, e solo se il router fallisce. Un `NO_TRADE` valido non scatena il fallback. Tetto di spesa DeepSeek invariato. Nessun merge, deploy o VPS.
