# 2026-11-01 — LONG Shadow: E2E reale Bitget REST+WebSocket con wallet PAPER sintetici, diagnostica Brain

## Decisione e confini

User 'ok procediamo' per passo successivo LONG senza deploy/merge/ordini. PR #26 DRAFT `work/long-shadow-app-observation-20261101` e PR #27 DRAFT (chiusura singola trade per ID) entrambe NON merged. Nessun accesso account/portafogli dell'utente o VPS e nessuna API Bitget privata, nessun ordine, nessun cambiamento LONG V6.1.1, SHORT, protezione 450 USDT o Brain.

## Nuova prova INTEGRATA reale (rete pubblica) PASS

PR #26 file `backend/long_shadow_live_public_synthetic_wallet_smoke.py` e workflow `.github/workflows/long-shadow-real-public-synthetic-e2e.yml`. GitHub Actions run **41344252298** completed/success (ripetuto success su run **41344497930**), link https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41344252298.

Una singola sessione: 8 GET REST public Bitget BTC/ETH × 1m/15m/1H/4H con validazione closed-bar causal; solo dopo il REST nuova connessione WebSocket pubblica `wss://ws.bitget.com/v3/ws/public`, subscribe `books1` BTC/ETH con **2 ACK**, 4 frame fino a quote bid/ask fresche, verifica clock e receipt, nessun quote buffered vecchio. Wallet PAPER sintetici creati in `tempfile.TemporaryDirectory()` per Hawk e Bull formato `state_v2.json`+heartbeat e Brain Free formato sqlite `brain.sqlite3`+heartbeat; nessun saldo/posizione reale. Observer produce 12 record `NO_TRADE`, writer only diagnostic separate da wallet, read-only dashboard proietta 3 portafogli. Stato report: `status=PASS, rest_closed_series=8, books1_ack_count=2, books1_received_frames=4, evaluated_records=12, visible_consumer_count=3, orders_created=0, paper_eligible=false`.

**Fondamentale**: nella prova E2E è stato utilizzato un **motore esplicitamente stub NO_TRADE**, NON il vero frozen LONG V6.1.1: `engine=STUB_NO_TRADE_NOT_REAL_V611`, `frozen_engine_evaluated=false`. È prova di pipeline pubblica reale + wallet sintetici, NON prova strategia/edge, NÉ test end-to-end su VPS. Il LONG frozen V6.1.1 hash `36f8c62be8d205d909ae16f5652209710de56ae710fedb6b75a601b96486fe72` rimane invariato nel pacchetto laboratorio.

## Nuova diagnostica formato Brain

PR #26 `backend/long_shadow_brain_source_diagnostic.py`, test `backend/tests/test_long_shadow_brain_source_diagnostic.py` (10). Legge entrambi i possibili Brain PAPER `free` e `pilot` in modalità read-only, con identità e heartbeat; restituisce solo metadati di validità, non simboli, capitale, saldi, posizioni né percorsi. Stati `NO_VALID_SOURCE`, `SINGLE_VALID_SOURCE_NOT_RUNTIME_CONFIRMED`, `MULTIPLE_VALID_SOURCES_AMBIGUOUS`. **Nessuna fonte selezionata automaticamente** e in ogni risposta `active_process_owner_confirmed=false`: una directory valida non attesta il processo attivo sulla VPS. Non eseguito contro wallet reali.

**CI GitHub Actions** al commit `a9adc6ed6803f1d903e2fc1b356c7e514d01b0c8`: 4 workflow completed/success: E2E pubblico+wallet sintetici **41344497930**, 8 serie live REST **41344497837**, full PR26 backend/frontend **41344497835** (backend **91/91 test** su 9 suite e no-orders guard, test React e build PASS), rollover 1m BTC/ETH live **41344497838**. Primo tentativo YAML del workflow E2E era fallito prima dell'esecuzione (etichetta colon non quotata); corretto e CI successiva verde, nessun bug di trading o alterazione dei portafogli.

**Runbook sviluppo** `docs/long-shadow-live-public-synthetic-e2e-brain-source-audit-20261101.md` nello stesso ramo.

## Gate e lavoro residuo

DATA_REST_WS_PUBLIC_LIVE_E2E=PASS, SYNTHETIC_WALLETS_3_FORMATS=PASS, OBSERVER_WITH_STUB=PASS, FROZEN_LONG_V611_IN_PUBLIC_E2E=**NOT TESTED**, REAL_BRAIN_WALLET_OWNER=**UNVERIFIED**, USER_PAPER_WALLETS=**NOT ACCESSED**, 15M/1H/4H_CONTINUOUS_ROLLOVER=**NOT VERIFIED**, H24_SERVICE=**OFF**, VPS_DEPLOY=NO, MAIN_MERGE=NO, EXECUTION_ECONOMICS=INSUFFICIENT, PAPER_ELIGIBLE=NO.

Prossimo passo: collegare in staging il V6.1.1 hash-pinned originale alla pipeline di feed + wallet di test e verificare la chiusura 15m/1H/4H; verificare quale istanza Brain è realmente attiva con riscontro processo senza esporre segreti. Solo dopo valutare e chiedere autorizzazione esplicita per deploy shadow; PAPER ancora separato.