# SuperBot V3 — Regola permanente: solo migliorie incrementali, scanner e liquidità

Checkpoint: 6 novembre 2026 — ChatGPT GPT-6.

## Direttiva esplicita dell'utente
Qualsiasi video, analisi, esempio, idea esterna o proposta dell'utente è soltanto una candidata integrazione. SuperBot NON va ricostruito da zero. Il coordinatore verifica se una funzione esiste già, valuta beneficio rispetto a costi, compatibilità e rischio, decide GO/DEFER/NO-GO e applica la modifica compatibile più piccola, reversibile e opt-in. Se non conviene, spiega perché. Evitare mesi di backtest di profittabilità prima del PAPER; misurare poi le strategie in forward PAPER, ma verificare stop, contabilità, rischio e recovery prima dell'avvio.

## Audit concreto
Verificati PR #57 head e25c8dd8db88fd6994e3b7a75ecfdec5ff258421 e PR #61 head a9044b6759da327b44da04f9e7f51e211d44e03f (ancora draft separate).
- Il file backend/v3/runner/runner_config.json configura cycle_minutes=60 (non è una verifica della VPS).
- Il runner già analizza i simboli in rotazione con L5 e BrainEngine: NO secondo motore AI.
- backend/v3/risk.py calcola quote/rischio e dimensionamento: NO secondo sizer.
- backend/v3/runner/feed.py contiene CandleStore 1m per monitor uscite: scanner futuro deve riusare la cache nei limiti di chiamate.
- Non c'è un provider validato di depth/spread nel ramo: NO inventare book liquidity.

## Componenti nuovi, puri, solo in sandbox; NON attivi nel runner
- backend/v3/observability/opportunity_scan.py e __init__.py: classificazione osservativa ogni slot 5m (richiede chiamante), 25 candele 1m chiuse, classifica LONG/SHORT da 5m price/volume e freschezza; niente trading/AI/network/journal.
- backend/v3/observability/liquidity_quote.py: quote osservativa bid/ask e impatto VWAP dato un libro ordini reale, restituisce UNKNOWN/INVALID/INSUFFICIENT se dati insufficienti; non è filtro esecutivo e non è collegata a Bitget.
- backend/tests/test_v3_observability_incremental.py: 25 unit test.
Decisione: GO scanner come osservatore opzionale, GO solo funzione matematica liquidità, DEFER l'applicazione come filtro finché non si verifica feed book e contratto. NO cambiare DeepSeek a ogni 5m, NO secondo Sizer, NO ricostruire SuperBot.

## Test e archiviazione
- 25 unit test nuovi PASS, 692 regression/compatibility mirati PASS, 0 fail.
- Tutti 385 file originali dello ZIP PR57 invariati byte per byte. Nessuna suite completa 4k+ ripetuta per questi soli moduli disattivati; nessuna CI/Jest/VPS/DeepSeek reale.
- Archivio Libreria: /SuperBot-Trading/SuperBot-V3-Scanner-Liquidita-Incrementali-2026-11-06.zip, SHA256 4ba6d156876afe95057e6077a9c77672da93126b19cdf60a82323f3fbe340af9, libfile_64befc1e16cc8191bf029714b8ac38f6.
- Documento Libreria: /SuperBot-Trading/IDEE-INCREMENTALI-NON-RIFARE-2026-11-06.md, libfile_f2b10694d9748191bc7f978411be9f93.

## Priorità
Completare integrazione sicura runner/exit-sidecar, chiusura e dashboard. Poi collegare scanner come osservatore in PAPER con budget rete e logging; liquidità solo dopo verifica feed. Validazione profit strategy tramite paper trading con storico misurabile, non backtest infinito. No merge/deploy/riavvio senza OK esplicito. Risk policy 2% per trade, 5% open, floor 450 USDT invariati.