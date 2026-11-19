# 2026-11-19 — laboratorio costi LLM

Diario su questo ramo, non sul ramo canonico `diario`.

Baseline: `work/brain-exit-observability-20261113` @ `33a0de73a9903ba1ff76326aa4cb7c688a1e4aca`. Le bozze #120, #118, #121, #122 e l'issue #113 sono state solo lette. Nessuna è stata modificata. Il nome `grok/brain-llm-cost-lab-20261119` non è ammesso qui; il ramo è `cursor/brain-llm-cost-lab-20261119-31c4`.

Decisione: laboratorio SHADOW offline, senza fallback e senza scrittura sul journal del Brain. Modelli fissi: A `deepseek-flash` (tabella del repository), B `google/gemini-2.5-flash`, C `groq/llama-3.3-70b` (esempi della documentazione REST di FreeLLMAPI). Nessuna chiamata reale. Qualità, latenza vera e risparmio restano incompleti. Raccomandazione: non integrare; il decisore resta A; B solo come ipotesi di consulente futuro.

Test eseguito in locale: `PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider --tb=line backend/tests/test_v3_llm_cost_lab.py` → 13 passed, exit 0.

Limiti: catalogo FreeLLMAPI non interrogato dal vivo; prezzi gratuiti non misurati; esiti di mercato assenti. Nessun merge, deploy o spesa.
