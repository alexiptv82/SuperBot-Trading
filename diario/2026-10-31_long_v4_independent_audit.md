# SuperBot Long Lab V4 — Audit indipendente ChatGPT, 31 ottobre 2026

**Contesto:** ricevuto SuperBot_Long_Lab_v4.zip per esame finale dopo audit V2/V3 e sviluppo da altra AI/Grok. Nessuna autorizzazione di merge/deploy/PAPER dedotta.

**Verificato:** SHA256 ZIP `9cf393feb2454dfcbe49fa4aedcfdaefe8f207f0881c7cd22019ea4e501ca67a`; manifesti SHA256SUMS 35/35 corrispondenti; suite `PYTHONPATH=. python -m unittest discover -s tests -v` 82/82 OK, Python locale. Difetti V3 riprodotti in passato ora corretti: conflitto SHORT True vs payload False => unknown, equity +0.10 agli indici 3/5/120 respinta, drawdown dichiarato +0.04 respinto.

**Nuovo audit indipendente (11 test avversariali):** 9 FAIL e 2 ERROR sul V4. Problemi confermati:
- P0: il reader reale `backend/director/brain_free/feeds.py:candles` converte timestamps OHLCV in float; `adapters/brain_adapter.py` richiede int esatto e produce `MALFORMED_BAR` per timestamp float integrali validi.
- P1: `closed_rows` esamina availability prima di escludere una candela futura/incompleta. Un contesto con CANDIDATE diventa NO_TRADE/AVAILABILITY_UNKNOWN_1m con sola aggiunta di bar futuro.
- P1: `verify_run` ricalcola con ReplayPolicy default; replay autentici con capitale 1500 USDT o fee 7bps sono rifiutati `EQUITY_DRIFT_DETECTED`.
- P1: `verify_run` ritorna PASS con expectancy e profit_factor falsificati, stopped invertito, evento ledger REJECT inventato o signals svuotati.
- P1/P2: `observed_availability` accetta ancora mappe legacy solo close_ms, quindi un timestamp comune di chiusura fra 1H e 4H puo' essere attribuito a entrambe. `adapt_quote` permette available_at_ms anteriore a ts_ms.

**Compatibilità reale:** Feed Brain richiede normalmente 120 barre lenti, Lab LONG 200. Brain `ai_context` trasporta MTF riassuntivo non 200 barre e non dispone ancora di recorder/provenienza disponibilità osservata. Nessuna validazione economica con dati Bitget reali OOS / leva/liquidazione / portafoglio LONG+SHORT. Integrazione Brain ancora non esiste.

**Verdetti:** BRAIN_ADVISORY=DA_CORREGGERE; HAWK_LONG_SHADOW=DA_CORREGGERE; BULL_LONG_SHADOW=DA_CORREGGERE; PAPER_ELIGIBLE=NO; evidenza economica insufficiente. V4 base software utile, non approvata per il rilascio.

**Consegna locale nella chat:** `AUDIT_INDIPENDENTE_LONG_V4_2026-10-31.md`, `LONG_V4_REGRESSIONI_PER_GROK.py` (11 test negativi su V4), `PROMPT_GROK_CORREZIONI_LONG_V5_2026-10-31.md`. Allegare a Grok insieme allo ZIP V4. Solo verifica read-only GitHub, nessun codice repo modificato, nessun VPS/AI pagata/ordine, nessuna modifica a classici o SHORT.

**Prossimo:** correzioni isolate V5 e riesecuzione test originali + 11 indipendenti, poi nuova verifica di compatibilità e solo eventuale proposta di integrazione Brain consultiva con approvazione esplicita.
