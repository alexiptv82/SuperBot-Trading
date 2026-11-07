# SuperBot V3 — PR #68, Brain consulta Falco/Toro come osservatori PAPER

**Stato DRAFT, OFFLINE, OPT-IN DISATTIVATO PER DEFAULT. Nessun merge, deploy, avvio o ordine.**

## Contratto di consultazione

- `backend/v3/brain_market/classic_peers.py` legge **esclusivamente** `heartbeat.json` e `state_v2.json` delle directory classic **esplicitamente configurate**; nessun accesso a segreti, ordini, network, strategie, ledger AI o altri processi.
- I segnali ammessi sono `LONG_POSITION`, `SHORT_POSITION` e `FLAT`: indicano **posizioni PAPER osservate**, NON previsione del trend o raccomandazione. Ogni record è limitato a 6 campi codificati: `portfolio`, `symbol`, `source`, `observation`, `asof_ms`, `open_positions`.
- Una fonte entra nel contesto AI **solo** se il suo heartbeat dichiara `portfolio=hawk|bull`, `exec_mode=paper`, timestamp non oltre 60 secondi nel passato né 2 nel futuro, contatore coerente, file validi, nessun segnale ambiguo.
- Se i vecchi container sono fermi con heartbeat obsoleto, il Brain riceve **NO_DATA** sui classici e continua il proprio processo autonomo. Non si riavviano i classici per generare segnali.
- `MarketContext.falco_signal` e `MarketContext.toro_signal` (già presenti nella V3) sono ora valorizzati opzionalmente; `DeepSeekL5Analyst` serializza solo i campi ammessi nel blocco `peer_paper_positions`. Il sistema è istruito a NON copiare un trade dei classici. `context_hash` del trade e `sources` della decisione tracciano l'osservazione davvero consumata.
- **L'analista non riceve capitale, PnL, chiavi, comandi o potere di esecuzione dei classici.** La scelta finale LONG/SHORT/NO_TRADE è del Brain sotto i suoi controlli rischio e mandato già in vigore. Nessun trasferimento fondi, hedging forzato o apertura obbligatoria.
- Gli input non devono essere considerati una *strategia appresa*: per promuovere o adattare strategie servono prove statistiche con esiti del Journal e validazione indipendente, non un semplice segnale di posizione.

## Attivazione controllata, non eseguita

`V3_BRAIN_PEER_OBSERVATIONS` resta `disabled` se non dichiarata. Al futuro rilascio PAPER il proprietario dell'ambiente potrà impostare **solo dopo collaudo e autorizzazione**:

```text
V3_BRAIN_PEER_OBSERVATIONS=paper_readonly
V3_FALCO_DATA_DIR=<volume PAPER Falco esistente, verificato>
V3_TORO_DATA_DIR=<volume PAPER Toro esistente, verificato>
```

Nessuna directory è dedotta per default; i volumi dei classici devono essere distinti tra loro e da quello del Brain. Se i dati non sono freschi, non entra niente nel prompt. L'impostazione NON modifica i bot in esecuzione.

## Verifiche

CI `.github/workflows/v3-brain-peer-signals-ci.yml` copre lettura in sola lettura, heartbeat vecchi/futuri, LIVE, identità errata, conteggi incoerenti, file o simboli malformati, injection nei campi extra, provenienza separata Falco/Toro, L5 payload e `context_hash`, ciclo Brain e regressioni L5. Nessuna rete AI reale né VPS.

## Restanti gate prima del GO

Controllo del profilo run Brain 2.000 USDT, backup locale fresco e restore isolato, web mobile uniformata (#66/#67), exit-only legacy (#65), validazione AI e monitoraggio della qualità e dei costi, snapshot dei classici realmente freschi, startup PAUSED e autorizzazione separata dell'utente per merge/deploy/restart. La VPS e le 8 posizioni PAPER legacy rimangono intatte.
