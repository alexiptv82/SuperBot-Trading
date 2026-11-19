# Handoff — router LLM gratuito

Branch `cursor/brain-free-llm-router-31c4`, base `work/brain-exit-observability-20261113` @ `33a0de73a9903ba1ff76326aa4cb7c688a1e4aca`. Il diario del 19 novembre non installa un Brain più nuovo: il runner resta su questo SHA. Nessun merge o deploy.

`BRAIN_LLM_PROVIDER` default `deepseek`. Con `free_router`, DeepSeek è il fallback a pagamento (default acceso, `DEEPSEEK_FALLBACK=false` lo spegne), una volta per simbolo e ciclo, solo se il router fallisce. Un `NO_TRADE` valido non chiama DeepSeek. Tetto di spesa invariato.

Guida: `docs/FREE_LLM_ROUTER.md`. Diario di branch: `diario/2026-11-19_brain-free-llm-router.md`.
