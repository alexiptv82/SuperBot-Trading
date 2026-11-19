# Requisiti di compatibilità per il router LLM (PR #120) — analisi di Claude

**Ruolo:** analizzo e definisco i requisiti; **non** sviluppo il router (resta a Grok, laboratorio #123). DeepSeek resta il decisore principale. Nessuna integrazione fatta.

## Cosa fa la PR #120 (`f4f7457`, letta e provata)
- Si attiva solo con `BRAIN_LLM_PROVIDER=free_router`; **senza variabile il comportamento resta quello di DeepSeek** (default OFF). Correggo il mio giudizio del mattino: non è "non integrabile" per costruzione.
- Con la variabile, il router (`FreeLLMAPI`, `auto:smart`) **diventa il decisore**; DeepSeek è il fallback a pagamento (una volta per simbolo e ciclo, se il router fallisce).
- Tocca `brain_f2/engine.py`, `brain_f2/contracts.py`, `brain_market/deepseek_l5.py`, `runner/wiring.py`; aggiunge `free_router` agli `_ALLOWED_ORIGINS` e il campo `llm_route`.
- **Prova di compatibilità tecnica:** merge di prova sul ramo di integrazione senza conflitti (`wiring.py` si fonde da solo con la P0); suite V3 **5105 superati** (= 5087 + i 18 test della PR), 0 falliti. Non integrata.

## Perché non è conforme alla decisione del proprietario
1. **Ruolo invertito:** la decisione approvata è DeepSeek decisore, modelli economici come consulenti sperimentali **in shadow**. In `free_router` il modello gratuito decide e DeepSeek ripiega.
2. **`auto:smart`:** il router sceglie il modello da solo; la decisione è modelli fissati per identità/provider/versione, niente auto-routing né fallback silenzioso fra modelli.
3. **Attribuzione:** `free_router` entra negli `_ALLOWED_ORIGINS`; un'apertura potrebbe essere attribuita a un'origine non identificabile, rovinando analisi, Dataset Builder e apprendimento.
4. **Nessuna modalità shadow** e nessun confronto con la decisione di DeepSeek.
5. **Modifica il contratto della decisione e file critici** (`engine.py`, `contracts.py`) per una funzione sperimentale.

## Requisiti che qualunque integrazione deve soddisfare
| # | Requisito | Verifica |
|---|---|---|
| R1 | Interruttore spento di default; senza interruttore comportamento **identico** a oggi | test di equivalenza delle decisioni e dei payload |
| R2 | **Shadow prima**: l'output del consulente va in un evento separato (es. `llm_advisor_shadow`), non crea né modifica decisioni; si esegue solo la decisione di DeepSeek | test: nessuna apertura dal consulente, con qualunque risposta |
| R3 | Modelli **fissati** (provider, modello, versione); nessun `auto`; nessun fallback silenzioso fra consulenti | test sul client + configurazione validata |
| R4 | Registrare modello effettivo, provider, versione del prompt, istante, latenza, errori, fallback, token, costo stimato, validità JSON | schema dell'evento |
| R5 | **Contratto della decisione invariato**; `originating_ai` = chi ha davvero deciso (DeepSeek); nessuna nuova origine esecutiva senza approvazione del proprietario | test sui contratti |
| R6 | RiskManager ed ExitService non importano né dipendono dal router | test di import e di indisponibilità del router |
| R7 | Tetto di costo/giorno anche per i piani gratuiti, timeout, rate limit, circuit breaker; se il router è spento il Brain resta completo, con degrado visibile | test con server finto |
| R8 | Solo loopback, nessuna chiave nei log, nessuna chiamata all'import, nessuna rete nei test | test offline |
| R9 | **Confronto pre-registrato**: DeepSeek da solo contro DeepSeek + consulente in shadow (concordanza, qualità dei NO_TRADE e delle aperture con le etichette a posteriori, costo, latenza, affidabilità) prima di qualsiasi ruolo attivo | protocollo scritto prima dei dati |
| R10 | Modifiche confinate in un modulo nuovo; `engine.py`/`contracts.py` toccati il meno possibile | revisione del diff |

## Come integrare quando Grok consegna
Riuso del client HTTP di #120 e del laboratorio #123 come sorgente degli eventi shadow; riscrittura del collegamento secondo R1–R10 (non il blocco `free_router` come decisore); poi gate completo e merge nel ramo di integrazione. Costi e installazione di FreeLLMAPI: **richiedono la tua autorizzazione**.
