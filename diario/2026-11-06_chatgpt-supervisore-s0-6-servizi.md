# SuperBot V3 — 6 novembre 2026 — Supervisore sei servizi, S0 (ChatGPT)

**Stato:** audit del commit `e25c8dd8db88fd6994e3b7a75ecfdec5ff258421` e sviluppo **isolato** di S0 completati; **codice NON pushato o integrato, nessun merge/deploy/VPS**.
**Dashboard esistente:** PR #61 `a9044b6759da327b44da04f9e7f51e211d44e03f` (separata dalla PR #57).

## Decisione del titolare
Integrare il Supervisore SuperBot V3 e le sei responsabilità (Scanner, Controllore, Sizer, Executor PAPER, Registro decisioni, Equity/Valutazione), con Falco/Toro meccanici e Brain autonomo, tracciabilità e apprendimento dimostrabile; riuso delle fondamenta e nessuna modifica ai bot in esecuzione.

## Audit
Esistono già detector/feature/regimi, F1 quote risk, esecuzione PAPER e chiusure, EventJournal, L1-L5, outcomes e learning expectancy/opportunity/walkforward. **Manca** l'archiviazione completa dei dati visti al momento di ogni decisione, dei controlli e delle evidenze sulla memoria; le decisioni scartate prima di engine.step possono non essere nel journal. Il runner corrente usa `NoReviewer`, non asserire revisore Claude in funzione.

## S0 realizzato e testato LOCALMENTE
Nuovo pacchetto esclusivamente in ZIP: `backend/v3/supervisor/{__init__.py,trace.py}`, `backend/tests/test_v3_supervisor_trace.py`, piano `docs/v3/SUPERVISORE-SEI-SERVIZI-2026-11-06.md`.
- `read_brain_timeline`: verifica hash chain, legge il journal Brain in sola lettura, usa `extract_outcomes` ufficiale.
- Schede `brain_decision` con identificativo/hash, regime, tipo, codice motivazione, strategia, link a posizione e esito netto verificato se presente; NO_TRADE/AI unavailable/risk block distinti.
- Non inventa snapshot/quote di rischio/memoria/invalidazione: campi `not_recorded`; manual close visibile ma esclusa da statistiche per strategia.
- **31/31 test** sia dalla radice (0,98 s) sia da /tmp (0,93 s); compatibilità con journal, L1, manual close e daily loss: **339/339 test** (6,49 s).
- Sorgenti in `SuperBot-V3-Supervisore-S0-6-Servizi-2026-11-06.zip`, SHA-256 `99788dafe1e09d24ae1a61da58b959e5a55c19b294c9cee84acce51753473d14`; rapporto in `RAPPORTO_SUPERBOT_V3_SUPERVISORE_S0_2026-11-06.md`, SHA-256 `71d8262481c7da8fef1726a96779f717e893d716ec5edd1ab40ed7f8efbda2df`. File negli allegati di questa chat.

## Roadmap
S1: eventi evidenza al momento decisione, incl. candidati scartati, vista mercato e codici strutturati. S2: API GET autenticata e terminale mobile sulla PR #61, metriche rischio/margine separate e 6 stati veritieri. S3: esperimenti e confronto OOS con costi, promozione esplicita. Tre portafogli isolati. 43% equity del video non replicato.

**Test non eseguiti:** suite completa da 6k+, Jest, VPS, deploy. Soglie attuali INVARIATE: trade 2%, open 5%, giornaliero warn 35% e halt 50%, floor 450 USDT. Nessun lancio del Brain o redeploy classici senza OK utente.
