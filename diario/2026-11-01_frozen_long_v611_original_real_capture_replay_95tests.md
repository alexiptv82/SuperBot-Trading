# 2026-11-01 — Frozen LONG V6.1.1 original: replay reale REST+WS registrati PASS

**Mandato utente**: 'ok procediamo' dopo collaudo Bitget pubblico e synthetic wallet E2E. Priorità: terminare integrazione LONG shadow PR #26, non ancora consentiti merge, deploy, ordini o accessi wallet reali. PR #27 per close single trade per ID resta Draft separata; Brain nuovo rules-controlled futuro; OLD Brain libero bocciato per prossimo rilascio.

### Test offline sul V6.1.1 autentico

Il laboratorio allegato dall'utente `/mnt/data/SuperBot_LONG_MTF_15m_Audit_Shadow_Ready_01/.../superbot_long_lab/engine.py` è stato aperto localmente. SHA256 **`36f8c62be8d205d909ae16f5652209710de56ae710fedb6b75a601b96486fe72`** (identico pin di progetto). **82/82 unittest originali PASS**. Dati reali precedentemente acquisiti `SuperBot_LONG_LIVE_MTF_RESULT_20261101T161618Z.zip`, SHA256 **`33eb490e34d7dbfbb208827d3f85edc48f327a3619ca2e33f3a5dfb5d5a84cb2`**.

Il replay ha letto le 8 vere risposte REST (BTC,ETH × 1m/15m/1H/4H) e tutte le quote WS registrate, validato SHA di ogni risposta e frame, rispettato timestamp di **ricezione** come inizio della disponibilità bar, usato bid/ask effettivamente registrati dopo il REST. Tre wallet **esplicitamente sintetici**: Hawk SHORT BTC, Bull LONG ETH, Brain vuoto; NON rappresentano wallet VPS. Valutato congelato V6.1.1 vero (NON stub) 12 volte = **12 NO_TRADE (`SETUP_ABSENT`)**, 0 CANDIDATE, 0 ordini e nessuna autorità di modificare punteggi/trade/SL. Il test è STORICO OFFLINE e non prova risultato con V6.1.1 su dati LIVE attuali.

Due gate negativi `FROZEN_ENGINE_SHA_MISMATCH` e `REST_SHA_MISMATCH` scattano correttamente. Package riproducibile generato in chat `SuperBot_LONG_Frozen_V611_Recorded_Replay_Verification_01.zip`, SHA256 **`2d9e9549c2b88fc8226d15aa4244a022128b1e1c22d794a5308e1b5a39e3eb88`**, contiene capture, frozen engine originale, runner, report, JSON decisioni e checksum; rilanciato indipendentemente dalla cartella estratta, 12 record identici.

### Codice e CI GitHub

Branch `work/long-shadow-app-observation-20261101`, PR **#26 DRAFT non mergiata**: pubblicati `backend/long_shadow_frozen_recorded_replay.py` e `backend/tests/test_long_shadow_frozen_recorded_replay.py` e documentazione `docs/long-shadow-frozen-v611-real-capture-offline-replay-20261101.md`. Il test CI del ramo usa ZIP sintetici auto-costruiti per garantire formato/integrità; NON dispone del ZIP reale privato dell'utente. **GitHub Actions run 41345386619** al commit `40da47631cc62434a7db3fa50999b2f64a5ea25f`: 95/95 backend tests PASS in 10 suite, no-order static guard PASS, frontend React tests/build PASS. Il replay vero è stato eseguito localmente sui byte verificati dell'utente, non su runner CI.

### Limiti e prossimi gate

- `FROZEN_ORIGINAL_RECORDED_REPLAY=PASS`; `PUBLIC_REST_WS_SYNTHETIC_WALLET_E2E_WITH_STUB=PASS` (precedente Actions #41344252298), ma **FULL_LIVE_ORIGINAL_ENGINE_E2E=NOT_DONE**.
- Nessun accesso alla VPS, quindi **ACTIVE_BRAIN_WALLET_SOURCE/PROCESS=UNVERIFIED**; non scegliere automaticamente Free/Pilot e non confondere file compatibile con owner runtime. Utente non deve copiare chiavi o saldi.
- `LIVE_15M_1H_4H_CONTINUITY=NOT_PROVEN`, `ECONOMIC_EDGE=INSUFFICIENT`, `PAPER_ELIGIBLE=NO`, `DEPLOY=NO`, `MERGE=NO`. LONG classici non autorizzato, Brain non modificato. SHORT e floor 450 USDT invariati.

Prossima attività dopo queste prove: unire l'originale V6.1.1 al test **live pubblico** su un runner effettivamente collegato a Bitget (serve fornire il file frozen in modo verificabile senza cambiarlo), confermare il Brain attivo sulla VPS in sola lettura con riscontro del processo; poi staging e chiedere OK esplicito prima di qualunque deploy shadow. La PR #27 (close solo trade ID) rimane separata.