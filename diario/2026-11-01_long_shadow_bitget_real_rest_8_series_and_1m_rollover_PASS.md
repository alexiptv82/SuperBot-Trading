# 2026-11-01 — Prova REST LIVE Bitget reale 8/8 + rollover 1m BTC/ETH PASS

**Mandato dell'utente**: 'ok perfetto procedi' per completare LONG prima della revisione Brain rules-governed e chiusura manuale ID esatto. Autorizza sviluppo/test read-only, NON merge, deploy, ordini PAPER/LIVE né modifiche production Brain/Falco/Toro/SHORT/protezione 450 USDT.

## Codice e localizzazione

Ramo `work/long-shadow-app-observation-20261101` PR **Draft #26**. Nuovo file `backend/long_shadow_rest_live_smoke.py` e workflow `.github/workflows/long-shadow-public-rest-smoke.yml` per test reale **8 richieste GET anonime** (BTC/ETH × 1m/15m/1H/4H) contro endpoint Bitget v3 `https://api.bitget.com/api/v3/market/candles`; nessuna chiave, nessun trading, nessun body o prezzo nei log. Riutilizza `public_candles()` e `parse_closed_response()` del codice PR26, controlla **almeno 200 barre chiuse, timestamp, OHLCV finiti, integrità e nessun lookahead**.

Secondo test `backend/long_shadow_rest_1m_rollover_smoke.py` + `.github/workflows/long-shadow-public-1m-rollover.yml`: due coppie di GET pubblici BTC/ETH 1m separate da ≥67 secondi, verifica che **ultimo close timestamp cresca di ≥60.000 ms e sia multiplo del minuto**, entrambe le risposte con timestamp reali di ricezione. Nessun dato finanziario segreto; nessun ordine.

## Risultati GitHub Actions verificati (log reali)

**Primo live smoke** run ID `41342844355`: completed / SUCCESS, 8/8 serie REST PASS, 499 candlestick chiusi ciascuna, zero ordini. BTC lag ultima chiusura in secondi: 1m 45.048, 15m 585.481, 1H 2385.918, 4H 13186.444. ETH: 1m 46.875, 15m 587.309, 1H 2387.749, 4H 13188.190. Tutti `available_at_ms` corrispondono a ricezione GitHub, non vengono retrodatati. Link: `https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41342844355`.

**Live smoke sul commit successivo** run `41343047218`: completed / SUCCESS, rinnova controllo 8/8.

**Rollover reale 1m** run ID `41343047252`: completed / SUCCESS. BTC e ETH entrambi da `first_close_ms=1793562120000` a `second_close_ms=1793562180000`: incremento ESATTO **1 minuto**, 499 barre chiuse su entrambe le letture, disponibilità dichiarata solo dopo ricezione. Quattro GET pubbliche in totale, nessun ordine. Link: `https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41343047252`.

**CI ramo LONG** run `41343047160`: completed / SUCCESS, job isolated-contract backend PASS (suite di ricerca precedenti **81/81** e safety static no-orders), job frontend-shadow-render PASS test React/build. Link: `https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41343047160`.

## Verdetto

- BITGET_PUBLIC_REST_LIVE_SCHEMA = **PASS** (2 simboli × 4 TF, 8 serie reali).
- BITGET_1M_CLOSE_ADVANCE_LIVE = **PASS** (BTC/ETH, due letture ≥67s).
- LONG_READONLY_BRANCH_CI = **PASS** (81 backend + React).
- BITGET_15M_1H_4H_LIVE_ROLLOVER = **NOT_OBSERVED** (solo snapshot; servirebbero i rispettivi confini, non pretendere prova H24).
- LONG_AI_ECONOMIC_EDGE = **INSUFFICIENT**, PAPER_ELIGIBLE = **NO**.
- ONLINE_OBSERVER_INSTALLED=**NO**, BRANCH_MERGED=**NO**, PROD_DEPLOY=**NO**, ORDER_CREATED=**0**, WALLET_REAL_BRAIN_SOURCE=**UNVERIFIED**.

**Prossima attività operativa necessaria prima di qualsiasi richiesta deploy:** attestare quale Brain (Free o Pilot) è realmente in esecuzione e quale wallet è autorevole; provare l'accoppiamento real-time collector WS books1 + REST closed MTF + wallet read-only in staging isolato senza scrittura. Continuare la PR #26 in Draft, nessuna attivazione PAPER. PR Draft #27 per chiudere singolo trade esatto resta separata, non eseguita. Redesign Brain rule-governed solo dopo LONG.