# LONG Shadow — E2E pubblico Bitget e wallet sintetici + diagnosi fonte Brain (1 novembre 2026)

## Scopo

Verificare l'intera catena **quotazioni pubbliche Bitget** (`books1`) + **8 serie candele chiuse REST reali** + **wallet PAPER di test** + **12 consigli per Falco/Toro/Brain** + **read-only dashboard projection**, senza toccare i wallet VPS e senza aprire ordini. NON presentare come test economico del motore LONG originale.

## Prova E2E reale con tre wallet sintetici — PASS

Script `backend/long_shadow_live_public_synthetic_wallet_smoke.py`, workflow `.github/workflows/long-shadow-real-public-synthetic-e2e.yml`. Run GitHub Actions: **41344252298**, SUCCESS, https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41344252298. Log esatto: `rest_closed_series=8`, `books1_ack_count=2`, `books1_received_frames=4`, `evaluated_records=12`, `visible_consumer_count=3`, `status=PASS`, `orders_created=0`, `paper_eligible=false`, `wallets=SYNTHETIC_PAPER_ONLY`.

Modello utilizzato nella prova E2E: `STUB_NO_TRADE_NOT_REAL_V611` (stub solo per verificare contratti e pipeline). Il motore LONG frozen originale **NON** è stato esercitato in questo run: `frozen_engine_evaluated=false`. Il sorgente originale V6.1.1 resta nel pacchetto di laboratorio `SuperBot_LONG_MTF_15m_Audit_Shadow_Ready_01.zip` con hash richiesto `36f8c62be8d205d909ae16f5652209710de56ae710fedb6b75a601b96486fe72`; non viene sostituito dallo stub per una vera strategia.

Sequenza esatta: otto GET REST pubblici e validati → si apre DOPO il batch un WebSocket **nuovo**, per evitare quote stale già bufferizzate → subscribe `usdt-futures/books1` BTCUSDT/ETHUSDT, due ACK e BBO ricevute e timestampate localmente → tempdir di prova con `state_v2.json` + heartbeat per Hawk/Bull e `brain.sqlite3` PAPER per Brain Free → `evaluate_observation` con motore stub `NO_TRADE` per 12 record → `publish_observation` in directory diversa dal wallet → `read_dashboard` verifica 3 wallet e 3 consigli. Non contiene informazioni dei wallet reali, chiavi o prezzi nei log.

## Diagnostica sola lettura Brain Free / Pilot

File `backend/long_shadow_brain_source_diagnostic.py` e `backend/tests/test_long_shadow_brain_source_diagnostic.py`, 10 test. Esegue `wallet_snapshot` separato per due percorsi eventualmente noti, legge formato e heartbeat ma NON emette PnL, saldi, credenziali, posizioni, simboli o percorsi. Se due archivi validi → `MULTIPLE_VALID_SOURCES_AMBIGUOUS`; se uno → `SINGLE_VALID_SOURCE_NOT_RUNTIME_CONFIRMED`; nessuno → `NO_VALID_SOURCE`. Mai selezione automatica, `active_process_owner_confirmed=false` **sempre**, perché validità dei file NON prova servizio attualmente in esecuzione.

Modalità non operativa di diagnosi (esempio, NON eseguito sulla VPS):

```bash
PYTHONPATH=backend python backend/long_shadow_brain_source_diagnostic.py \
  --brain-free-dir /opt/superbot-brain-free \
  --brain-pilot-dir /opt/superbot-desk-data/brain
```

**Non copiare in chat segreti, volumi, path privati o screenshot di chiavi.** La diagnosi da sola non autorizza il collegamento di produzione; serve attestare anche quale processo/servizio è owner del Brain. Solo allora impostare esplicitamente `LONG_SHADOW_BRAIN_SOURCE` su `free` o `pilot`, mai auto-guess.

## Gate residui

- Public market (REST+WS) LIVE E2E synthetic PASS, vera V6.1.1 non esercitata nel run nuovo e nessun wallet reale testato.
- Brain runtime source = UNVERIFIED; restano test applicativi su staging con wallet autentici **solo in lettura**, con autorizzazione separata prima di ogni deploy.
- LONG 15m/1H/4H rollover continuativo H24 = NOT_VALIDATED. Da non presentare come prova di economic edge.
- PR #26 e PR #27 entrambe Draft / non merge. Brain completamente libero bocciato per futuro rilascio: redesign rules-controlled dopo il LONG.
- Ordini = zero, API exchange private = zero, `PAPER_ELIGIBLE=NO`, no deploy / no VPS changes.