## 05/11 (14:30) — L5 PRONTO PER CHATGPT: IL BRAIN VEDRÀ IL MERCATO (INDICATORI E REGIME SU 15 m / 1 h / 4 h)

**Claude Sonnet 5.5 — coordinatore** · solo documenti, nessun codice nuovo · punto di partenza per ChatGPT: `cab064e` (PR #54)

Prompt `claude/prompt-chatgpt-l5-market-view-2026-11-05.md`: `backend/v3/brain_market/` (parametri, vista di mercato pura sulle sole candele chiuse, `DeepSeekL5Analyst`). Il regime del tabellone, del journal e del modello diventa **uno solo** (`regime_for_context`); senza dati sul timeframe base il Brain **non chiama il modello** (NO_TRADE); barra non chiusa = errore (`future_bar`); test anti look-ahead contro le funzioni vere sulla serie completa. Parametri (EMA 20/50, ATR 14, RSI 14, MACD 12/26/9, Bollinger 20/2, Donchian 20, ADX 14, `pct_window` ~30 giorni per timeframe, soglie del regime come in P10) **proposti da Claude, modificabili dall'utente**, solo in `market_view_params.json` (sha256 `612168ce…6398`); testo di sistema sha256 `4a5721c9…0d0c`.
**Prerequisito per usarlo davvero:** una sorgente di candele chiuse a 15 m/1 h/4 h (circa 2 900 barre a 15 m, 730 a 1 h, 190 a 4 h) nel ciclo del Brain: è parte del collegamento (feed) e non è ancora costruita. Nessun deploy.

## Aggiornamento 17:00 — consegna di ChatGPT applicata e verificata (PR #55)

Codice applicato invariato (`8dcf3e5`); mia verifica indipendente `57f2a5f` (66 test, periodi tutti diversi). Mutanti: i suoi 78 → 76/78 (2 equivalenti); 38 di collegamento → suoi 25, miei 36, insieme 38. Suite completa 4783 passed (3 failure `fastapi` note). Dettagli in `STATO.md` (voce delle 17:00) e nella PR #55 (draft, impilata su #54).

