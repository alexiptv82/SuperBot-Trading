# Audit startup LONG Shadow su capture reale Bitget 15m — 2026-11-01

**Input verificato**: `SuperBot_LONG_LIVE_MTF_RESULT_20261101T161618Z.zip`, SHA256 `33eb490e34d7dbfbb208827d3f85edc48f327a3619ca2e33f3a5dfb5d5a84cb2`. Il controllo è stato rieseguito offline sullo ZIP allegato nella conversazione (nessun nuovo download o trading).

Per ogni simbolo e timeframe, il primo snapshot WS riporta 500 barre; **499 erano già temporalmente chiuse al momento della ricezione** e **1 era ancora in formazione, esclusa dall'analisi**.

| Simbolo | Snapshot 1m ricevuto (Unix ms) | 15m | 1H | 4H | Prima BBO dopo tutti gli snapshot |
|---|---:|---:|---:|---:|---:|
| BTCUSDT | 1793549781799 | 1793549781946 | 1793549782098 | 1793549782099 | 1793549782244 |
| ETHUSDT | 1793549782100 | 1793549782102 | 1793549782241 | 1793549782243 | 1793549782244 |

Ritardo della prima BBO dopo ultimo snapshot: BTC 145 ms, ETH 1 ms. Il motore congelato V6.1.1 è stato già verificato nella ricerca precedente (82/82 test); il probe iniziale documentato nei laboratori con wallet **ipotetici**, non autorevoli, aveva dato 12 `NO_TRADE` (`SETUP_ABSENT`). **Non trattare questi come trade reali o decisioni basate su wallet effettivi.**

**Significato di causalità**: i dati OHLCV storici contenuti nello snapshot diventano disponibili solo all'istante di ricezione elencato, non nel rispettivo passato. Gli aggiornamenti del periodo corrente non equivalgono a un flag di chiusura. La finestra di 15 minuti non attraversa un rollover orario o a quattro ore.

**Audit nuove sorgenti Brain**: nel `backend/brain_free_api.py` della base main, il percorso default di Brain Free è `BRAIN_FREE_DATA_DIR` oppure `/opt/superbot-brain-free`. Nel `backend/desk/brain_view.py` il vecchio Pilot legge la directory `BRAIN_DATA_DIR` o `/opt/superbot-desk-data/brain`, e `status.json` con `mode=paper`, `applied=false` e `ts_ms` per il heartbeat. Le due origini NON sono la stessa directory e NON devono essere mescolate. `backend/long_shadow_api.py` e `backend/long_shadow_readonly.py` nel ramo isolato sono stati corretti coerentemente. La sorgente Brain effettivamente *attiva* su VPS resta non verificata: nessuna selezione automatica.

**Gates**: archivio 15m / ricevute startup MTF PASS; full live close 1H/4H NOT_OBSERVED; real Brain wallet binding UNVERIFIED; full app CI UNVERIFIED; ONLINE_LONG_SHADOW=OFF; REAL_EXECUTION=UNVERIFIED; ECONOMIC_EVIDENCE=INSUFFICIENT; PAPER_ELIGIBLE=NO.

Nessun merge, deploy, ordini o modifiche al comportamento SHORT/Brain/Hawk/Bull.