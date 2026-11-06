# Checkpoint — Market Quality Monitor SHADOW, incremento minimo SuperBot V3
Data 6 novembre 2026 · Autore GPT-6 · PAPER esclusivo · **solo sandbox locale; nessun merge, deploy, VPS, avvio, branch codice, modifica strategie/storico/rischio**.

## Decisione sulla consulenza esterna
Accolto solo il riferimento concettuale A / poly-maker: quality microstructure pretrade in SHADOW. Non importato né copiato codice di terzi. FreqAI/P10 già coperti per gran parte dal laboratorio V3 con embargo, walk-forward e outcome per regime. Condor/Hummingbot solo checklist architetturale. HOLD cryptofeed e feed L2 Bitget finché non validato; NO nuovi bot o Risk/Sizer paralleli.

## Codice sviluppato, non ancora montato
- **Unico nuovo modulo funzionale**: `backend/v3/observability/market_quality.py`, dipende dal precedente `liquidity_quote.py` riutilizzato in modo byte-identico; solo Python stdlib. Fonte: libro L2 FULL normalizzato, provato da adapter esterno, qty in BASE, venue BITGET USDT_PERPETUAL, `seq/pseq`, epoch/connection_id, event/receive timestamps. I book con origine incerta, sequenza interrotta, stale, reconnect privo di snapshot, orari anomali e quantità errate diventano UNKNOWN/INVALID e non vengono utilizzati come attestazione di liquidità.
- Metriche osservate: spread bp, bid/ask depth ±10bp in USDT, imbalance top5, microprice delta, entry/exit impatto snapshot e roundtrip fee+impatto **solo se fee esplicita**. Funding e prezzi futuri non inclusi. Stati OBSERVED/UNKNOWN/INVALID/INSUFFICIENT, nessun APPROVED, veto/risk effect, network, DB o chiamata AI.
- Separazione netta `mid_markout_after` 30/60s: risultato EX-POST sull'andamento del midpoint, non PnL di fill, non campo disponibile al momento della decisione (evita future leakage).
- **Non** c'è adapter UTA V3 né test data Bitget in tempo reale; `source_version` da solo non autentica un feed. Nessun wiring su runner, dashboard, S1/EventJournal o servizio uscite. Il modulo rimane default OFF e non ritarda primo avvio PAPER.

## Risultati effettivamente verificati
- `PYTHONPATH=.:backend python -m pytest backend/tests/test_v3_runner_cycle.py backend/tests/test_v3_runner_e2e.py backend/tests/test_v3_runner_runner.py backend/tests/test_v3_runner_feed_monitor.py backend/tests/test_v3_runner_config_metering.py backend/tests/test_v3_runner_contracts.py backend/tests/test_v3_risk.py backend/tests/test_v3_brain_market_l5.py backend/tests/test_v3_observability_incremental.py backend/tests/test_v3_market_quality_shadow.py -q -p no:cacheprovider --disable-warnings` -> **737 PASS in 11.01s** (Python 3.13), exit 0.
- 385 file originali dello ZIP `superbot-trading-e25c8dd.zip` tutti byte-identici; `liquidity_quote.py` e `__init__.py` nel nuovo pacchetto byte-identici anche al precedente ZIP Scanner/Liquidita.
- **NON testati:** API/websocket Bitget, feed sequencer, PnL su dati reali, Jest/CRA, suite V3 completa, VPS, systemd, DeepSeek o risultati profittevoli. Il backend in esecuzione non è cambiato.

## Artefatti salvati nella Library ChatGPT `/SuperBot-Trading`
- `SuperBot-V3-Market-Quality-SHADOW-Incrementale-2026-11-06.zip`, SHA256 `1e2624636668c64b2f0b3ded1b8452fc1f78b994a725eade5663ed8f4506e037`, libfile `libfile_e54a45e35a108191959eb937a4df03ec`.
- `RAPPORTO_SuperBot_V3_Market_Quality_SHADOW_2026-11-06.md`, SHA256 `51482db9290be895ae70fcd58dc39482ab4ab51d51d311637b53189e27f62176`, libfile `libfile_84b6fa0b5a7481918a5ac670eb1759ce`.

**Prossima priorità:** runner/exit sidecar consolidati e dashboard/CI PAPER, senza ritardare avvio per nuovi filtri. In futuro solo se feed Bitget L2 affidabile esiste già o adapter piccolissimo validato: aggiungere collegamento read-only a S1, registrare snapshot per trade/NO_TRADE/scarti, confrontare markout post-evento e costi; non creare secondo writer né cambiare decisioni senza ulteriore gate. Soglie 2% per trade, 5% rischio totale, floor 450 USDT, alert 35% halt 50% intatte.