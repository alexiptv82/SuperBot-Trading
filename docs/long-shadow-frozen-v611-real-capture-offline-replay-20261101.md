# Frozen LONG V6.1.1 — replay storico REST + WS reali (1 novembre 2026)

**Obiettivo:** usare il motore LONG V6.1.1 ORIGINALE, hash-pinned, non il precedente stub NO_TRADE, su dati Bitget realmente acquisiti e tre wallet PAPER esplicitamente sintetici, senza ordini/chiavi/API private o deploy. Questo è un test **OFFLINE STORICO**, non un servizio live.

## Input e verifica

- Fonte originale dalla conversazione dell'utente `SuperBot_LONG_MTF_15m_Audit_Shadow_Ready_01.zip`: `engine/SuperBot_Long_Lab_v6_1/superbot_long_lab/engine.py`, SHA-256 `36f8c62be8d205d909ae16f5652209710de56ae710fedb6b75a601b96486fe72`.
- Capture reale `SuperBot_LONG_LIVE_MTF_RESULT_20261101T161618Z.zip`, SHA-256 `33eb490e34d7dbfbb208827d3f85edc48f327a3619ca2e33f3a5dfb5d5a84cb2`.
- Otto serie REST pubbliche realmente registrate (`rest_responses.jsonl`) e frame WS books1 (`ws_raw_frames_00001.jsonl`). Ogni risposta REST e ogni raw frame WS riletto con SHA-256 originale valido; timestamp HTTP di invio/ricezione e timestamp di ricezione WS rispettati. Le barre chiuse diventano disponibili alla **ricezione REST**, non retroattivamente alla chiusura storica. Il primo bid/ask successivo è stato usato senza costruire quote fittizie. Differenza ultima REST → primo BBO: BTC 2453 ms, ETH 1534 ms; il vincolo BBO è di freschezza rispetto al **momento di valutazione**, non una distanza massima arbitraria tra GET e BBO.
- Tre scenari wallet PAPER esplicitamente sintetici: Falco con flag SHORT BTC, Toro con flag LONG ETH, Brain con posizioni vuote. Nessuna attestazione di wallet reali / processi VPS.

## Risultati registrati

- **82/82 test originali V6.1.1 PASS** (`PYTHONPATH=. python -m unittest discover -s tests -q`).
- **12 valutazioni reali del motore originale**: 2 simboli × 3 destinatari × 2 setup (CONTINUATION, REVERSAL), modalità classic=shadow, brain=advisory.
- **12/12 `NO_TRADE`, motivo `SETUP_ABSENT`**, nessun `CANDIDATE`, nessun ordine. Il risultato non è stato indotto modificando parametri o imponendo soglie più permissive.
- Autorità `advisory_only`, quattro flag di permesso non attivi; SHA motore pin verificato. Due test negativi locali rifiutano `FROZEN_ENGINE_SHA_MISMATCH` e `REST_SHA_MISMATCH`.
- Kit riproducibile consegnato nella stessa conversazione: `SuperBot_LONG_Frozen_V611_Recorded_Replay_Verification_01.zip`, SHA256 `2d9e9549c2b88fc8226d15aa4244a022128b1e1c22d794a5308e1b5a39e3eb88`. Include motore originale, input ZIP, script, risultati JSON, report, manifesto; ricalcolo a freddo ha prodotto output JSON identico.

## Codice pubblicato nel branch (non production)

`backend/long_shadow_frozen_recorded_replay.py` accetta `--capture` e `--engine` come percorsi **espliciti**; usa `long_shadow_offline_probe.frozen_engine` che impedisce motori con SHA errato; valida le otto risposte REST e raw WS, produce 12 advisory in stdout sintetico, senza scrivere file wallet o fare chiamate di rete. `backend/tests/test_long_shadow_frozen_recorded_replay.py`: quattro prove su ZIP di test sintetico (12 record, hash REST alterato, hash WS alterato, mismatch motore) aggiunte alla workflow CI. Si precisa che il codice repo viene esercitato in CI con fixture sintetiche, mentre il replay reale V6.1.1 è stato effettuato sul pacchetto utente esterno: **non** sostenere che lo ZIP privato sia nell'Actions runner.

**GitHub Actions** run `41345386619` sul commit `40da47631cc62434a7db3fa50999b2f64a5ea25f`: backend **95/95 PASS** su 10 suite e static no-order guard PASS, frontend React test e build PASS. Il test reale V6.1.1 resta un replay offline riprodotto con la copia del file dell'utente, NON la pipeline corrente di GitHub del motore con dati appena arrivati.

## Gate rimasti

LONG_FROZEN_ORIGINAL_CAPTURE_REPLAY=**PASS**; LIVE_PUBLIC_BITGET_REST_WS_SYNTHETIC_WALLET_STUB_E2E=**PASS** (GitHub run 41344252298); **FULL_LIVE_ORIGINAL_ENGINE_E2E=NOT_DONE**; **ACTIVE_BRAIN_PROCESS_OWNER=UNVERIFIED**; **REAL_USER_WALLETS=NOT_ACCESSED**; 15m/1H/4H long-term live closed rollover continuity = NOT_VALIDATED. Non dimostra vantaggio economico. `PAPER_ELIGIBLE=NO`, `DEPLOY=NO`, `MERGE=NO`, `ORDERS_CREATED=0`. PR #27 per chiusura del singolo trade per ID resta DRAFT separata.