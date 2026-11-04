# 2026-11-04 (sera) — P9a: rilevatori a sole candele → Candidate per P5 (PR #51, bozza)

**Claude Sonnet 5.5 — coordinatore tecnico** · modulo: codice di **ChatGPT** (Grok ha finito il tempo di utilizzo; stesso prompt, Modalità B: consegna come testo, applicata invariata) · funzioni pure, nessun collegamento col Brain, col journal, coi prompt, con soglie o limiti

`backend/v3/detectors/`: `common.py` (`RiskSpec`, `build_candidates`: cooldown, stop/obiettivo da ATR non arrotondati, `signal_time_ms = apertura + candle_ms`, id `S07:BTCUSDT:<ms>:L`), `breakout.py` (S07 Donchian sulle `n` barre precedenti, filtro EMA opzionale), `reversal.py` (S05 Bollinger %B + MACD), `trend.py` (S02 incrocio EMA + ADX minimo). **Nessuna soglia, periodo o moltiplicatore nel codice**: argomenti obbligatori.

## Cosa ho trovato
**Nessun difetto di codice.** Consegna di ChatGPT la migliore finora: 347 test, mutazione **102/102** eseguita da lui, rapporto completo. Unica correzione, nei test: la prova di velocità basata sul **rapporto fra tempi** (tempi di pochi ms) è instabile (6,77 da `/tmp` contro un limite di 6): sostituita da una prova **deterministica** (conta le letture di barre e lati a 2 000 e 4 000 elementi; due mutanti quadratici uccisi). Stesso errore, mio, trovato prima in P6 (9,3 su una macchina esterna): lo avevo scritto io, ChatGPT si è fermato sulla baseline e l'ho corretto (`6db4cc2`).
Limite del contratto, dichiarato da ChatGPT: un `open_time_ms` assurdo (`10**150·60000`) dà un id di 169 caratteri, rifiutato da P5; irrilevante per timestamp reali.

## Verifica
- Commit: `86ec465` ChatGPT invariato · `b437bc0` velocità deterministica · `8f123a2` miei 26 test.
- **381 test** nei due file; suite V3 3179 → **3560 passed**, 3 xfailed; 3 failed per `fastapi` mancante, invariati. Passa dalla radice (due volte) e da `cd /tmp`.
- Verifica **leggera** (come concordato con l'utente): regole riscritte da zero con altri parametri e semi = candidati identici su 12 serie da 1 200 barre; nessun look-ahead con indicatori veri (6 prefissi per rilevatore, con meta-test); candidati accettati ed etichettati da `label_candidates`; mutazione leggera dei miei test 11/12 (il sopravvissuto è coperto dai test di ChatGPT).

## Limiti
Nessun dato di mercato reale; nessuna prova di redditività; nessun filtro multi-timeframe (serve un modulo di ricampionamento, P9b); stop/obiettivo senza tick size; ingresso al `close` della barra di segnale.

## Prossimo
- **Catena minima per la prima risposta vera** («queste 3 strategie hanno un vantaggio netto fuori campione su BTC/ETH?»): caricatore dello storico BTC/ETH via GitHub Actions (da qui Bitget non è raggiungibile; deve spezzare i dati ai buchi) → collegamento etichette P5 → statistica P4/P6 + rapporto. Poi **ci si ferma**: le altre 9 schede (P9b) solo se il rapporto dice che vale la pena.
- Decisioni dell'utente aperte (non bloccano): le 4 soglie di `RegimeParams`; le soglie statistiche di P6; i parametri dei 3 rilevatori (periodi, soglie, moltiplicatori di stop/obiettivo, cooldown) per il primo rapporto; politica di esplorazione del Brain in PAPER; tocchi ambigui stop/target (`stop_first` consigliato); L1 e L4 richiedono OK esplicito; certificazione backup F0 e import dei 534 trade legacy (richiedono OK e VPS).

⛔ Nessun merge/deploy · `DESK_MODE=paper` invariato · Hawk/Bull non toccati · cervello intatto.
