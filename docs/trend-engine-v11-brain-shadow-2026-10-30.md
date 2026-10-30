# Trend Engine v1.1 — Integrazione Brain in sola osservazione
30 ottobre 2026 · [skip ci]

## Decisione vincolante dell'utente
Lettura precoce delle possibili inversioni SHORT→LONG e LONG→SHORT. **Non e' una strategia di ingresso, non puo' aprire o bloccare trade, non deve aumentare per forza il numero di LONG, non puo' muovere stop, TP, budget o pesi dello scoring.** DeepSeek rimane l'analista principale Brain H24, Claude secondo parere selettivo. Modalita' solo PAPER.

## Implementazione
- Ramo: `work/brain-trend-v11-shadow-20261030`, basato su `work/brain-trend-awareness-20261030`.
- `backend/director/trend_engine_v11.py`: adattamento *stateless* del motore v1.1 fornito nello ZIP dell'utente. Conserva EMA9/21, ATR14, livelli swing confermati 2 barre dopo, scoring e isteresi della classificazione 1m/5m (WARMUP, TRANSITION_UP/DOWN, BULLISH/BEARISH, NEUTRAL); nessuna funzione `adjust_scores` trasferita. L'indicatore non contiene punti LONG/SHORT e la presunta forza non e' una probabilita' predittiva calibrata.
- Input Bitget V2: Unix ms di apertura, 1m OHLCV con base volume e quote turnover ignorato (NON e' taker-buy volume); solo barre chiuse, contigue, finite, con controlli su duplicati/revisioni/stale. Warmup minimo 50 candele 1m e 50 candele 5m (250 minuti 1m) per conferma multi-timeframe; durante il warmup 5m e' esplicitamente `five_minute_ready:false`.
- `backend/director/trend_shadow.py`: `ThreadPoolExecutor(max_workers=1)` indipendente, al massimo un job; non attende il worker nel tick e scarta indicatori non freschi.
- `BrainService.tick` legge solamente le barre 1m gia' rese disponibili dal feeder esistente (normalmente 120 per simbolo senza posizioni). Calcolo off-thread e risultato opzionale, che viene inserito tramite `PaperSupervisor.step(regime_v11=...)` nei candidati AI.
- `ai_context.py`: `regime_v11_indicator` sanificato, con `status` available/unavailable/not_supplied, schema rigoroso per clock/bias/flags. Un avviso BEARISH non esclude LONG. Non viene aggiunta alcuna regola di ammissione e non cambia i progetti condizionali ammessi dallo scanner.
- L'adapter *non replica* il checkpoint/export JSON della libreria utente: ricostruisce da un massimo di 300 barre pubbliche ad ogni calcolo per causalita' deterministica. Non legge segnali non confermati e non salva nuove memorie di trading.

## CI e limite dimostrativo
Run `41047000619`: SUCCESS su Python 3.10 e 3.11, 41 test di integrazione e 175 test motore per versione. Test paralleli (mock) verificano parity su replay sintetico v1.1, ignorare la candela corrente, gap, revisioni conflittuali, assenza di implicazioni sui trade, pipeline AI candidati LONG preservati.
Nessun backtest reale Bitget e nessun P&L live provato: false inversioni, latenze e vantaggio dell'avviso vanno ancora misurati su dati fuori campione.

## Limitazioni aperte
- Il Brain dispone normalmente di ~120 barre 1m per simbolo non aperto: l'indicatore 1m e' gia' utilizzabile, la componente 5m (50 aggregati) rimane `five_minute_ready:false` finche' non sono raccolte 250 barre 1m contigue. Un ampliamento del feed 1m per tutti i simboli deve essere asincrono/rate-limited, non rallentare le protezioni.
- Il Brain invia analisi DeepSeek quando lo scanner presenta candidati: l'indicatore non crea candidati e non aggira lo scanner. Questa e' una limitazione nota, coerente con la richiesta dell'utente di non obbligare aperture.
- UI Brain sul ramo separato `work/brain-simple-dashboard-20261030`: non modificata in questa integrazione.

**Nessun merge o deploy.** Nessun dato storico, posizione, wallet, VPS o chiave toccati. Solo ramo di lavoro GitHub.
AI: chatgpt
