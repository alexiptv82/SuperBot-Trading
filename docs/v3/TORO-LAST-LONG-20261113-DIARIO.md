# Diario SuperBot — Ultimo tentativo Toro LONG, 13 novembre 2026

**Stato**: ricerca in laboratorio, nessun bot modificato o avviato, nessun deploy. Brain PAPER operativo secondo ultima prova utente; Falco SHORT da verificare prima di riavvio; Toro non ancora approvato.

**Ricerca esterna ricevuta**: 5 famiglie LONG (Donchian BTC regime 4H, BinHV45 5M, Supertrend 15M/1H, TrendRider, Squeeze e momentum 4H/1D), non valide di per sé come evidenze di redditività Bitget. Studi già negativi PR#93, #94, #96; funding storico Binance non equiparabile a Bitget secondo proxy gate PR#98 (29,68% <70%), l'ipotesi funding stessa non fu backtestata.

## Decisione ultima ricerca
Un solo candidato Supertrend 15M + 1H, long only, scelto perché più coerente con incasso rapido rispetto a Donchian 4H e senza copiare stop 3% del BinHV45 spot con leva 20x. PR **#99 DRAFT**: https://github.com/alexiptv82/SuperBot-Trading/pull/99

**PRE-REG PRIMA DEL NUOVO RISULTATO:** commit `0c8471a8d189e09fbd7d3f39825a997f2c1cff65`, file `docs/v3/TORO-LAST-LONG-SUPERTREND-PREREG-20261113.md`; filtro Supertrend 10/3 1h rialzista, flip 15m rialzista, EMA200, RSI45–75, volume ≥1,2 medie20; ingresso dopo chiusura 15m, stop ST−0,25 ATR14, TP2R, time exit max12h, cost16bp+1bp funding per evento 8h, stress30bp; universe BTC ETH SOL BNB XRP; valutazione dati Bitget 365g fino 13/11 16Z. Almeno150 trade, PF>1,15, net positivo in sottoperiodi e 3/5 asset, superare random matched 1000; stop alla ricerca rules-only se il candidato FAIL. Il passato è parzialmente già osservato; un PASS storico **NON OOS** richiede 30 giorni forward shadow prima di qualunque adozione. Rischio ipotetico futuro 12 USDT/trade, 24 aggregati; nessuna modifica config.

**Codice isolato preparato ma NON ANCORA ESEGUITO:** `deploy/scripts/toro_last_supertrend_replay_20261113.py` git commit `8dfacbdb8da76e53bc0148ed928b2ef330ad2c10`; launcher detached `deploy/scripts/toro_last_supertrend_start_detached_20261113.sh` commit `4b06716546f91b1bb9f34bfc9256d57f321f1d84`. Launcher SHA-pinned con preflight Python+synthetic, solo dati pubblici Bitget, separato su VPS in `/opt/superbot-toro-research/supertrend-last-20261113/`, nessuna modifica stage, zero ordini, no Actions. CPUQuota 65%, Nice15, MemoryMax850M. **Prima vera esecuzione ancora da confermare via screenshot Termius**, non affermare test PASS. Report progettato fail-closed: non certifica MTM DD né lookahead incrementale senza audit supplementare e non attiva Toro automaticamente.

**No MERGE, no LIVE, no servizio trading riavviato, Brain/Falco non toccati.**

## AGGIORNAMENTO DEFINITIVO — 13 novembre 2026 ore 22:20 CET — NO-GO SUPERtrend LAST

Evidenza screenshot Termius del servizio di ricerca separato su VPS:
`TORO_ST_FINAL event=REPLAY_COMPLETE trades=361 avg_net_bp=-32.455 profit_factor=0.5938 drawdown_close_only=0.8973 random_p95_bp=-9.0233 stress30_avg_bp=-46.455`.
`TORO_ST_FINAL result=NO_AUTOMATIC_GO critical_checks_met=1 critical_checks=8 report=/opt/superbot-toro-research/supertrend-last-20261113/report.json paper_orders=0 no_bot_changes=1`.

- **361 trade simulati** sui cinque asset del protocollo Supertrend 15m/1h.
- Expectancy media netta **−0,32455% del nozionale** per trade (−32,455 bp).
- Profit Factor **0,5938**, inferiore alla soglia pre-registrata >1,15.
- Benchmark random matched p95 **−9,0233 bp**, migliore della media strategia **−32,455 bp**.
- Drawdown riportato su curva delle **sole chiusure 89,73%**, NON audit completo drawdown mark-to-market; valore molto elevato nel modello di replay.
- Media netta con stress costo 30 bp **−0,46455%** per trade.
- **Solo 1 su 8 gate soddisfatti**. Alcuni gate sono fail-closed per verifiche non eseguite, ma le metriche disponibili bastano al NO-GO pre-registrato.

Decisione conforme al documento bloccato PR #99 commit `0c8471a8d189e09fbd7d3f39825a997f2c1cff65`: **STOP a ulteriori varianti price-only rules-first Toro LONG in questa iniziativa**, nessuna modifica post-hoc per salvare il backtest, nessun deploy/install Toro. Il fallimento non dimostra che tutti i futuri ingressi LONG siano privi di vantaggio; il protocollo testato qui è respinto. Il report completo esiste sulla VPS e non è stato letto direttamente dall'assistente, soltanto il log mostrato dall'utente.

**Operatività**: replay soltanto di ricerca, ordini=0, nessuna modifica al funzionamento Falco SHORT originale, Brain AI PAPER o Toro. Audit reale Brain (heartbeat, feed 1m, posizioni) resta separato e non è fornito da questo screenshot. Nessun LIVE.
